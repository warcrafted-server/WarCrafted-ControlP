import logging
import re
import resource
import shlex
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.config import DATA_DIR, get_settings
from app.emulators import log_manager, process_control
from app.soap.client import SoapClient, SoapError

logger = logging.getLogger(__name__)

PID_DIR = DATA_DIR / "pids"

_UPDATE_DIFF_RE = re.compile(r"Update time diff:\s*(\d+)ms")


def _allow_core_dumps() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))


class ProcessControlError(Exception):
    """Error al iniciar o detener el proceso de una instancia."""


@dataclass
class InstanceConfig:
    id: str
    name: str
    type: str
    enabled: bool
    world_process: str
    auth_process: str
    start_cmd: str
    auth_start_cmd: str
    workdir: str
    soap_host: str
    soap_port: int
    soap_user: str
    soap_pass: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    db_characters: str
    auth_service_id: str
    acore_logs_dir: str = ""
    log_categories: str = ""
    db_auth: str = "acore_auth"
    db_world: str = "acore_world"
    db_playerbots: str = ""  # vacio = instancia sin mod-playerbots, esa base no existe


class BaseEmulatorDriver(ABC):
    """Interfaz comun para todos los drivers de emulador."""

    def __init__(self, config: InstanceConfig):
        self.config = config
        settings = get_settings()
        self._logs_root = Path(settings.instances_logs_dir)
        self._retention_days = settings.logs_retention_days
        self._max_runs = settings.logs_max_runs
        self.soap = SoapClient(
            host=config.soap_host,
            port=config.soap_port,
            username=config.soap_user,
            password=config.soap_pass,
        )
        PID_DIR.mkdir(parents=True, exist_ok=True)
        self._log_instance_dir().mkdir(parents=True, exist_ok=True)
        self._stop_generation = 0

    def _pid_file(self) -> Path:
        return PID_DIR / f"{self.config.id}.pid"

    def _ready_file(self) -> Path:
        return PID_DIR / f"{self.config.id}.ready"

    def _stopping_file(self) -> Path:
        return PID_DIR / f"{self.config.id}.stopping"

    def _log_instance_dir(self) -> Path:
        return self._logs_root / self.config.id

    def _log_categories(self) -> list[str]:
        raw = self.config.log_categories.strip()
        if not raw:
            return []
        return [category.strip().lower() for category in raw.split(",") if category.strip()]

    def current_console_log(self) -> Path | None:
        """Fichero de consola del run activo (el mas reciente), para el streaming en vivo."""
        for run in log_manager.list_runs(self._log_instance_dir()):
            if run["category"] == log_manager.CONSOLE_CATEGORY:
                return self._log_instance_dir() / run["filename"]
        return None

    def list_log_runs(self) -> list[dict]:
        native = (
            log_manager.scan_native_logs(Path(self.config.acore_logs_dir))
            if self.config.acore_logs_dir
            else []
        )
        return log_manager.list_runs(self._log_instance_dir()) + native

    def log_run_path(self, filename: str) -> Path | None:
        if filename.startswith(log_manager.NATIVE_PREFIX):
            if not self.config.acore_logs_dir:
                return None
            base_dir = Path(self.config.acore_logs_dir)
            name = filename.removeprefix(log_manager.NATIVE_PREFIX)
        else:
            base_dir = self._log_instance_dir()
            name = filename
        path = log_manager.resolve_safe(base_dir, name)
        if path is None or not path.is_file():
            return None
        return path

    def read_log_run_preview(self, filename: str) -> dict | None:
        path = self.log_run_path(filename)
        if path is None:
            return None
        try:
            content, truncated, total_size_bytes = log_manager.read_preview(path)
        except OSError:
            return None
        return {"content": content, "truncated": truncated, "total_size_bytes": total_size_bytes}

    def _read_pid(self) -> int | None:
        return process_control.read_pid(self._pid_file())

    def _write_pid(self, pid: int) -> None:
        process_control.write_pid(self._pid_file(), pid)

    def _clear_pid(self) -> None:
        process_control.clear_pid(self._pid_file())

    def find_process(self) -> psutil.Process | None:
        return process_control.find_process(self._pid_file(), self.config.world_process, self.config.workdir)

    def _is_ready(self) -> bool:
        """Ya se puede entrar al reino (mundo, red y SOAP cargados), no solo que el proceso exista."""
        if self._ready_file().exists():
            return True
        log_path = self.current_console_log()
        if log_path and log_manager.contains_ready_marker(log_path):
            self._ready_file().touch()
            return True
        return False

    def get_process_status(self) -> dict:
        proc = self.find_process()
        if not proc:
            self._ready_file().unlink(missing_ok=True)
            self._stopping_file().unlink(missing_ok=True)
            return {"state": "offline", "pid": None, "cpu_percent": None, "cpu_percent_host": None, "memory_mb": None}
        try:
            # cpu_percent(interval=...) hace una medicion "antes/despues" con sleep real;
            # llamarlo dentro de oneshot() reutiliza el valor "antes" cacheado y siempre da 0%.
            # Esta normalizado a 1 nucleo = 100%, asi que un proceso multihilo puede superar
            # el 100% (ej. 179% con 2 nucleos casi saturados); cpu_percent_host lo reexpresa
            # como % de la capacidad total del host, comparable con el CPU del host del dashboard.
            cpu_percent = proc.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count() or 1
            cpu_percent_host = round(cpu_percent / cpu_count, 1)
            with proc.oneshot():
                memory_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {"state": "offline", "pid": None, "cpu_percent": None, "cpu_percent_host": None, "memory_mb": None}

        if self._stopping_file().exists():
            state = "stopping"
        elif self._is_ready():
            state = "online"
        else:
            state = "starting"

        return {
            "state": state,
            "pid": proc.pid,
            "cpu_percent": cpu_percent,
            "cpu_percent_host": cpu_percent_host,
            "memory_mb": memory_mb,
        }

    def execute_soap_command(self, command: str) -> str:
        return self.soap.execute(command)

    def get_update_diff_ms(self) -> int | None:
        """Retraso del bucle principal (comando GM 'server info'); None si SOAP no responde."""
        try:
            output = self.execute_soap_command("server info")
        except SoapError:
            return None
        match = _UPDATE_DIFF_RE.search(output)
        return int(match.group(1)) if match else None

    def start(self) -> dict:
        existing = self.find_process()
        if existing:
            return {"success": True, "detail": "El servidor ya esta en ejecucion.", "pid": existing.pid}

        if not self.config.start_cmd:
            raise ProcessControlError("No hay START_CMD configurado para esta instancia.")

        workdir = Path(self.config.workdir) if self.config.workdir else None
        if workdir and not workdir.is_dir():
            raise ProcessControlError(f"El directorio de trabajo (WORKDIR) no existe: {workdir}")

        try:
            args = shlex.split(self.config.start_cmd)
        except ValueError as exc:
            raise ProcessControlError(f"START_CMD invalido: {exc}") from exc

        self._ready_file().unlink(missing_ok=True)
        self._stopping_file().unlink(missing_ok=True)

        instance_dir = self._log_instance_dir()
        instance_dir.mkdir(parents=True, exist_ok=True)

        categories = self._log_categories()
        if self.config.acore_logs_dir and categories:
            log_manager.archive_native_logs(instance_dir, Path(self.config.acore_logs_dir), categories)

        console_log_path = instance_dir / log_manager.run_log_filename(
            log_manager.CONSOLE_CATEGORY, log_manager.timestamp_now()
        )
        try:
            log_fh = console_log_path.open("w", buffering=1)
        except OSError as exc:
            raise ProcessControlError(f"No se pudo abrir el archivo de log: {exc}") from exc

        try:
            log_fh.write(f"--- Inicio {self.config.name} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
            log_fh.flush()
            process = subprocess.Popen(
                args,
                cwd=str(workdir) if workdir else None,
                # PIPE, no DEVNULL: si stdin da EOF inmediato, el CliThread de worldserver
                # (readline en bucle) gira a maxima velocidad y termina bloqueando la
                # consola para el resto de hilos. Con PIPE sin escritor se queda esperando.
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
                preexec_fn=_allow_core_dumps,
            )
        except OSError as exc:
            log_fh.close()
            logger.error("Fallo al iniciar '%s': %s", self.config.name, exc)
            raise ProcessControlError(f"No se pudo ejecutar '{self.config.start_cmd}': {exc}") from exc

        # El hilo lee stdout/stderr del proceso mientras vive, limpia ANSI y corta
        # repeticiones (ver log_manager.pump_console_output); es quien cierra log_fh.
        threading.Thread(
            target=log_manager.pump_console_output,
            args=(process.stdout, log_fh),
            daemon=True,
        ).start()

        time.sleep(0.5)
        return_code = process.poll()
        if return_code is not None:
            tail = log_manager.tail_file(console_log_path)
            message = f"El proceso finalizo inmediatamente (codigo {return_code})."
            if tail:
                message += f" Ultimas lineas del log:\n{tail}"
            logger.error("Fallo al iniciar '%s': %s", self.config.name, message)
            raise ProcessControlError(message)

        self._write_pid(process.pid)
        log_manager.purge_old_logs(instance_dir, self._retention_days, self._max_runs)
        logger.info("Instancia '%s' iniciada con PID %s", self.config.name, process.pid)
        return {"success": True, "detail": "Servidor iniciado correctamente.", "pid": process.pid}

    def _force_stop(self) -> dict:
        """Segundo intento (o posterior): ya se pidio un apagado antes y sigue vivo.

        No reintenta SOAP (si el apagado normal no funciono, repetir el mismo
        comando no suele arreglarlo) — manda SIGTERM y, si no responde en 5s
        (proceso realmente colgado, visto con AzerothCore + muchos bots online),
        escala a SIGKILL.
        """
        proc = self.find_process()
        if not proc:
            self._stopping_file().unlink(missing_ok=True)
            return {"success": False, "detail": "El servidor no estaba en ejecucion."}
        try:
            proc.terminate()
            _, alive = psutil.wait_procs([proc], timeout=5)
            if alive:
                proc.kill()
                detail = f"El proceso (PID {proc.pid}) no respondio a la señal de apagado; se forzo el cierre (SIGKILL)."
            else:
                detail = f"Se reenvio la señal de apagado al proceso (PID {proc.pid})."
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            self._stopping_file().unlink(missing_ok=True)
            logger.error("Fallo al forzar la detencion de '%s': %s", self.config.name, exc)
            raise ProcessControlError(f"No se pudo detener el proceso (PID {proc.pid}): {exc}") from exc
        self._clear_pid()
        logger.warning("Detencion forzada de '%s' (PID %s): %s", self.config.name, proc.pid, detail)
        return {"success": True, "detail": detail}

    def _schedule_auto_force_stop(self, generation: int, delay: float) -> None:
        timer = threading.Timer(delay, self._auto_force_stop_if_stuck, args=(generation,))
        timer.daemon = True
        timer.start()

    def _auto_force_stop_if_stuck(self, generation: int) -> None:
        # Un stop() o scheduled_stop() posterior sube _stop_generation: si ya no coincide,
        # este watchdog es de un ciclo de apagado viejo (ya resuelto o sustituido) y no debe actuar.
        if generation != self._stop_generation or not self._stopping_file().exists():
            return
        logger.warning(
            "Instancia '%s' seguia colgada tras el apagado normal; forzando cierre automaticamente.",
            self.config.name,
        )
        try:
            self._force_stop()
        except ProcessControlError as exc:
            logger.error("Fallo el forzado automatico de '%s': %s", self.config.name, exc)

    def stop(self) -> dict:
        if self._stopping_file().exists():
            return self._force_stop()

        self._stopping_file().touch()
        self._stop_generation += 1
        generation = self._stop_generation
        try:
            output = self.execute_soap_command("server shutdown 5")
            logger.info("Instancia '%s' detenida via SOAP.", self.config.name)
            self._schedule_auto_force_stop(generation, delay=15.0)
            return {"success": True, "detail": output}
        except SoapError as exc:
            proc = self.find_process()
            if not proc:
                self._stopping_file().unlink(missing_ok=True)
                return {"success": False, "detail": f"El servidor no estaba en ejecucion. ({exc})"}
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as term_exc:
                self._stopping_file().unlink(missing_ok=True)
                logger.error("Fallo al detener '%s': %s", self.config.name, term_exc)
                raise ProcessControlError(
                    f"No se pudo detener el proceso (PID {proc.pid}): {term_exc}"
                ) from term_exc
            self._clear_pid()
            logger.warning(
                "SOAP fallo para '%s' (%s); proceso PID %s detenido con SIGTERM.", self.config.name, exc, proc.pid
            )
            return {
                "success": True,
                "detail": f"El comando SOAP fallo ({exc}); se envio senal de apagado directamente al proceso (PID {proc.pid}).",
            }

    def scheduled_stop(self, delay_seconds: int, message: str) -> dict:
        """Parada avisada: mensaje simultaneo por chat (announce) y pantalla (notify),
        mas el countdown nativo de AzerothCore (que solo avisa el tiempo restante).

        `server shutdown <segundos> <exitcode> <motivo>` existe, pero si se le da un
        exitcode explicito AzerothCore ignora el motivo por completo, y sin exitcode la
        primera palabra del motivo se intenta leer como exitcode si parece un numero
        ("10 minutos..." se comeria el "10"). Para no depender de esa ambiguedad, el
        motivo se manda aparte por announce y el shutdown va sin motivo ni exitcode.

        A diferencia de stop(), una segunda llamada mientras ya hay una parada en marcha
        no fuerza el cierre: AzerothCore permite reprogramar el temporizador con un nuevo
        "server shutdown", asi que aqui una segunda pulsacion sustituye tiempo y mensaje
        (forzar sigue estando en el boton "Detener").
        """
        already_stopping = self._stopping_file().exists()
        self._stopping_file().touch()
        self._stop_generation += 1
        generation = self._stop_generation
        for warn_cmd in (f"notify {message}", f"announce {message}"):
            try:
                self.execute_soap_command(warn_cmd)
            except SoapError:
                pass  # el aviso es un plus; si falla, seguimos con la parada igualmente
        try:
            output = self.execute_soap_command(f"server shutdown {delay_seconds}")
        except SoapError as exc:
            if not already_stopping:
                self._stopping_file().unlink(missing_ok=True)
            raise ProcessControlError(
                f"No se pudo programar la parada via SOAP: {exc}"
            ) from exc
        logger.info(
            "Parada programada de '%s' en %ss: %s", self.config.name, delay_seconds, message
        )
        self._schedule_auto_force_stop(generation, delay=delay_seconds + 15.0)
        return {"success": True, "detail": output}

    @abstractmethod
    def get_online_players(self) -> int | None:
        """Numero de jugadores conectados segun el esquema del emulador."""

    def get_status(self) -> dict:
        status = self.get_process_status()
        online = status["state"] == "online"
        status["players_online"] = self.get_online_players() if online else None
        status["update_diff_ms"] = self.get_update_diff_ms() if online else None
        return status
