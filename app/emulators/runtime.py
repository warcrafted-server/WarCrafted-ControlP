import logging
import resource
import shlex
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import psutil

from app.emulators import log_manager, process_control
from app.soap.client import SoapError

logger = logging.getLogger(__name__)


class ProcessControlError(Exception):
    """Error al iniciar o detener el proceso de una instancia."""


@dataclass(frozen=True)
class RuntimeMarkers:
    """Ficheros de estado que comparten los runtimes (los escribe el driver).

    `is_ready` y `ready_file` solo los usa el runtime nativo: en Docker el estado
    online/starting se deduce del propio contenedor, no de un log del host.
    """

    ready_file: Path | None = None
    stopping_file: Path | None = None
    is_ready: Callable[[], bool] | None = None


class RuntimeBackend(ABC):
    """Interfaz comun de control de una instancia: existe, estado, arranque y parada."""

    @abstractmethod
    def find_process(self) -> psutil.Process | None:
        """El proceso vivo de la instancia, o None si no esta en ejecucion."""

    @abstractmethod
    def get_status(self) -> dict:
        """Estado, PID y consumo de la instancia."""

    @abstractmethod
    def start(self) -> dict:
        """Arranca la instancia y devuelve {"success", "pid"}."""

    @abstractmethod
    def stop(
        self,
        graceful_shutdown: Callable[[], str] | None = None,
        on_graceful: Callable[[], None] | None = None,
    ) -> dict:
        """Pide un apagado ordenado y, si no responde, fuerza el cierre."""

    @abstractmethod
    def force_stop(self) -> dict:
        """Cierra la instancia sin intentar el apagado ordenado."""


def _allow_core_dumps() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))


class NativeRuntime(RuntimeBackend):
    """Runtime nativo: procesos del host localizados con psutil (comportamiento de siempre)."""

    def __init__(
        self,
        *,
        name: str,
        process_name: str,
        workdir: str,
        start_cmd: str,
        pid_file: Path,
        markers: RuntimeMarkers | None = None,
    ):
        self.name = name
        self.process_name = process_name
        self.workdir = workdir
        self.start_cmd = start_cmd
        self.pid_file = pid_file
        self.markers = markers or RuntimeMarkers()

    def _stopping_file(self) -> Path | None:
        return self.markers.stopping_file

    def _clear_markers(self) -> None:
        for marker in (self.markers.ready_file, self.markers.stopping_file):
            if marker is not None:
                marker.unlink(missing_ok=True)

    def _drop_stale_markers(self, proc: psutil.Process) -> None:
        """Tira los ficheros .ready/.stopping de un run anterior.

        Sobreviven al proceso y al reinicio de la maquina, asi que sin esto un
        worldserver recien arrancado sale como "Deteniendo" (o como listo antes de
        cargar el mundo) por un marcador que no tiene nada que ver con el.
        """
        try:
            started = proc.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        for marker in (self.markers.ready_file, self.markers.stopping_file):
            if marker is None:
                continue
            try:
                if marker.stat().st_mtime < started:
                    marker.unlink(missing_ok=True)
            except OSError:
                continue

    def find_process(self) -> psutil.Process | None:
        return process_control.find_process(self.pid_file, self.process_name, self.workdir)

    def get_status(self) -> dict:
        proc = self.find_process()
        if not proc:
            self._clear_markers()
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

        self._drop_stale_markers(proc)
        stopping = self._stopping_file()
        if stopping is not None and stopping.exists():
            state = "stopping"
        elif self.markers.is_ready is not None and self.markers.is_ready():
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

    def start(
        self,
        *,
        console_path: Path | None = None,
        subject: str = "El proceso",
        core_dumps: bool = False,
    ) -> dict:
        """Lanza START_CMD. Con `console_path` vuelca su salida a ese log (worldserver);
        sin el, descarta stdin/stdout/stderr (authserver).
        """
        workdir = Path(self.workdir) if self.workdir else None
        if workdir and not workdir.is_dir():
            raise ProcessControlError(f"El directorio de trabajo (WORKDIR) no existe: {workdir}")

        try:
            args = shlex.split(self.start_cmd)
        except ValueError as exc:
            raise ProcessControlError(f"START_CMD invalido: {exc}") from exc

        self._clear_markers()

        log_fh = None
        if console_path is not None:
            try:
                log_fh = console_path.open("w", buffering=1)
            except OSError as exc:
                raise ProcessControlError(f"No se pudo abrir el archivo de log: {exc}") from exc
            log_fh.write(f"--- Inicio {self.name} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
            log_fh.flush()

        try:
            process = subprocess.Popen(
                args,
                cwd=str(workdir) if workdir else None,
                # PIPE, no DEVNULL: si stdin da EOF inmediato, el CliThread de worldserver
                # (readline en bucle) gira a maxima velocidad y termina bloqueando la
                # consola para el resto de hilos. Con PIPE sin escritor se queda esperando.
                stdin=subprocess.PIPE if log_fh else subprocess.DEVNULL,
                stdout=subprocess.PIPE if log_fh else subprocess.DEVNULL,
                stderr=subprocess.STDOUT if log_fh else subprocess.DEVNULL,
                text=bool(log_fh),
                bufsize=1 if log_fh else -1,
                start_new_session=True,
                preexec_fn=_allow_core_dumps if core_dumps else None,
            )
        except OSError as exc:
            if log_fh:
                log_fh.close()
            logger.error("Fallo al iniciar '%s': %s", self.name, exc)
            raise ProcessControlError(f"No se pudo ejecutar '{self.start_cmd}': {exc}") from exc

        if log_fh:
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
            tail = log_manager.tail_file(console_path) if console_path is not None else ""
            message = f"{subject} finalizo inmediatamente (codigo {return_code})."
            if tail:
                message += f" Ultimas lineas del log:\n{tail}"
            logger.error("Fallo al iniciar '%s': %s", self.name, message)
            raise ProcessControlError(message)

        process_control.write_pid(self.pid_file, process.pid)
        logger.info("'%s' arrancado con PID %s", self.name, process.pid)
        return {"success": True, "pid": process.pid}

    def terminate_process(self, proc: psutil.Process) -> bool:
        """SIGTERM y, si no responde en 5s, SIGKILL (apagado forzado).

        AzerothCore con muchos bots online se cuelga y no sale con la señal normal;
        ahi se escala. Devuelve True si hubo que matarlo.
        """
        proc.terminate()
        _, alive = psutil.wait_procs([proc], timeout=5)
        if alive:
            proc.kill()
            return True
        return False

    def stop(
        self,
        graceful_shutdown: Callable[[], str] | None = None,
        on_graceful: Callable[[], None] | None = None,
    ) -> dict:
        """Apagado ordenado via `graceful_shutdown`; si SOAP falla, SIGTERM directo."""
        if graceful_shutdown is None:
            return self.force_stop()
        stopping = self._stopping_file()
        if stopping is not None:
            stopping.touch()
        try:
            output = graceful_shutdown()
            logger.info("Instancia '%s' detenida via SOAP.", self.name)
            if on_graceful is not None:
                on_graceful()
            return {"success": True, "detail": output}
        except SoapError as exc:
            proc = self.find_process()
            if not proc:
                if stopping is not None:
                    stopping.unlink(missing_ok=True)
                return {"success": False, "detail": f"El servidor no estaba en ejecucion. ({exc})"}
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as term_exc:
                if stopping is not None:
                    stopping.unlink(missing_ok=True)
                logger.error("Fallo al detener '%s': %s", self.name, term_exc)
                raise ProcessControlError(
                    f"No se pudo detener el proceso (PID {proc.pid}): {term_exc}"
                ) from term_exc
            process_control.clear_pid(self.pid_file)
            logger.warning(
                "SOAP fallo para '%s' (%s); proceso PID %s detenido con SIGTERM.", self.name, exc, proc.pid
            )
            return {
                "success": True,
                "detail": f"El comando SOAP fallo ({exc}); se envio senal de apagado directamente al proceso (PID {proc.pid}).",
            }

    def force_stop(self) -> dict:
        """Segundo intento (o posterior): ya se pidio un apagado antes y sigue vivo.

        No reintenta SOAP (si el apagado normal no funciono, repetir el mismo
        comando no suele arreglarlo) — manda SIGTERM y, si no responde en 5s
        (proceso realmente colgado, visto con AzerothCore + muchos bots online),
        escala a SIGKILL.
        """
        proc = self.find_process()
        stopping = self._stopping_file()
        if not proc:
            if stopping is not None:
                stopping.unlink(missing_ok=True)
            return {"success": False, "detail": "El servidor no estaba en ejecucion."}
        try:
            forced = self.terminate_process(proc)
            if forced:
                detail = f"El proceso (PID {proc.pid}) no respondio a la señal de apagado; se forzo el cierre (SIGKILL)."
            else:
                detail = f"Se reenvio la señal de apagado al proceso (PID {proc.pid})."
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            if stopping is not None:
                stopping.unlink(missing_ok=True)
            logger.error("Fallo al forzar la detencion de '%s': %s", self.name, exc)
            raise ProcessControlError(f"No se pudo detener el proceso (PID {proc.pid}): {exc}") from exc
        process_control.clear_pid(self.pid_file)
        logger.warning("Detencion forzada de '%s' (PID %s): %s", self.name, proc.pid, detail)
        return {"success": True, "detail": detail}
