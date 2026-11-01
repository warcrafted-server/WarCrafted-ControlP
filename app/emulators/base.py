import logging
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.config import DATA_DIR, get_settings
from app.emulators import log_manager
from app.emulators.runtime import NativeRuntime, ProcessControlError, RuntimeBackend, RuntimeMarkers
from app.emulators.runtime_docker import DockerRuntime
from app.soap.client import SoapClient, SoapError

logger = logging.getLogger(__name__)

PID_DIR = DATA_DIR / "pids"

# Segundos de cortesia cuando el apagado ya cerro las bases de datos: es la parte del
# cierre que no deberia tardar nada, asi que no hace falta el margen largo del .env.
DB_CLOSED_GRACE_SECONDS = 30

_UPDATE_DIFF_RE = re.compile(r"Update time diff:\s*(\d+)ms")

__all__ = ["BaseEmulatorDriver", "InstanceConfig", "ProcessControlError"]


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
    host_root: str = ""
    runtime: str = "native"
    docker_service: str = ""
    docker_project_dir: str = ""
    docker_profile: str = ""

    @property
    def host_base(self) -> Path | None:
        """Raiz del arbol del servidor en el host (padre de bin/ y etc/).

        `host_root` manda cuando existe: en Docker WORKDIR es una ruta del
        contenedor que no existe en el host. Sin el, se mantiene la derivacion
        de siempre desde WORKDIR.
        """
        if self.host_root:
            return Path(self.host_root)
        return Path(self.workdir).parent if self.workdir else None

    @property
    def bin_dir(self) -> Path | None:
        base = self.host_base
        return base / "bin" if base else None

    @property
    def etc_dir(self) -> Path | None:
        base = self.host_base
        return base / "etc" if base else None

    @property
    def logs_dir(self) -> Path | None:
        base = self.host_base
        return base / "logs" if base else None

    @property
    def lua_dir(self) -> Path | None:
        base = self.host_base
        return base / "lua_scripts" if base else None


class BaseEmulatorDriver(ABC):
    """Interfaz comun para todos los drivers de emulador."""

    def __init__(self, config: InstanceConfig):
        self.config = config
        settings = get_settings()
        self._logs_root = Path(settings.instances_logs_dir)
        self._retention_days = settings.logs_retention_days
        self._max_runs = settings.logs_max_runs
        self._max_total_mb = settings.logs_max_total_mb
        self.soap = SoapClient(
            host=config.soap_host,
            port=config.soap_port,
            username=config.soap_user,
            password=config.soap_pass,
        )
        PID_DIR.mkdir(parents=True, exist_ok=True)
        self._log_instance_dir().mkdir(parents=True, exist_ok=True)
        self._stop_generation = 0
        # El runtime se rehace en cada reload del manager, asi que puede leer los
        # marcadores por referencia y no hace falta mantenerlos sincronizados.
        self.runtime = self._build_runtime()

    def _build_runtime(self) -> RuntimeBackend:
        if self.config.runtime == "docker":
            return DockerRuntime(
                name=self.config.name,
                service=self.config.docker_service,
                project_dir=self.config.docker_project_dir,
                profile=self.config.docker_profile,
                markers=RuntimeMarkers(
                    ready_file=self._ready_file(),
                    stopping_file=self._stopping_file(),
                    is_ready=self._is_ready,
                ),
            )
        return NativeRuntime(
            name=self.config.name,
            process_name=self.config.world_process,
            workdir=self.config.workdir,
            start_cmd=self.config.start_cmd,
            pid_file=self._pid_file(),
            markers=RuntimeMarkers(
                ready_file=self._ready_file(),
                stopping_file=self._stopping_file(),
                is_ready=self._is_ready,
            ),
        )

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

    def find_process(self) -> psutil.Process | None:
        return self.runtime.find_process()

    def _status_log_path(self) -> Path | None:
        """Log donde leer por donde va la instancia (arranque terminado, apagado en marcha).

        El Server.log nativo primero: existe aunque el worldserver no lo haya
        arrancado el panel (tmux, systemd...), que es justo cuando no hay log de consola.
        """
        if self.config.acore_logs_dir:
            native = Path(self.config.acore_logs_dir) / log_manager.NATIVE_CATEGORIES["server"]
            if native.is_file():
                return native
        return self.current_console_log()

    def _is_ready(self) -> bool:
        """Ya se puede entrar al reino (mundo, red y SOAP cargados), no solo que el proceso exista."""
        if self._ready_file().exists():
            return True
        log_path = self._status_log_path()
        if log_path and log_manager.contains_ready_marker(log_path):
            self._ready_file().touch()
            return True
        return False

    def get_process_status(self) -> dict:
        return self.runtime.get_status()

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

        if not self.config.start_cmd and self.config.runtime != "docker":
            raise ProcessControlError("No hay START_CMD configurado para esta instancia.")

        instance_dir = self._log_instance_dir()
        instance_dir.mkdir(parents=True, exist_ok=True)

        categories = self._log_categories()
        if self.config.acore_logs_dir and categories:
            log_manager.archive_native_logs(instance_dir, Path(self.config.acore_logs_dir), categories)

        console_log_path = instance_dir / log_manager.run_log_filename(
            log_manager.CONSOLE_CATEGORY, log_manager.timestamp_now()
        )
        started = self.runtime.start(
            console_path=console_log_path,
            subject="El proceso",
            core_dumps=True,
        )
        log_manager.purge_old_logs(instance_dir, self._retention_days, self._max_runs, self._max_total_mb)
        return {"success": True, "detail": "Servidor iniciado correctamente.", "pid": started["pid"]}

    def _force_stop(self) -> dict:
        return self.runtime.force_stop()

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

    def force_stop_if_shutdown_stuck(self, stale_after: float) -> str | None:
        """Mata la instancia si un apagado ya empezado se queda sin avanzar.

        AzerothCore puede colgarse despues de cerrar limpiamente sus pools: los hilos no
        acaban de unirse y el proceso no sale nunca. Ni SIGTERM ni repetir el shutdown lo
        mueven, solo SIGKILL. Se detecta por el log, porque cada paso del cierre escribe
        una linea: log parado = apagado parado.

        Sirve venga de donde venga el apagado (panel, consola GM, un script por SOAP);
        el watchdog de `stop()` solo cubre los que salen del propio panel.

        Devuelve el detalle de la parada, o None si no habia nada que forzar.
        """
        proc = self.find_process()
        if not proc:
            return None
        log_path = self._status_log_path()
        if log_path is None:
            return None
        shutting_down, db_closed = log_manager.read_shutdown_state(log_path)
        if not shutting_down:
            return None

        # El apagado no lo ha pedido el panel, asi que marcalo para que el dashboard
        # no siga mostrando la instancia como si estuviera en linea.
        self._stopping_file().touch()
        try:
            idle_seconds = time.time() - log_path.stat().st_mtime
        except OSError:
            return None

        # El margen largo es para no cortar un cierre lento pero vivo: vaciar los pools
        # puede tardar minutos con miles de consultas encoladas. Cerrados ya los pools no
        # queda nada que guardar, solo salir, y eso o es inmediato o no pasa nunca.
        deadline = min(DB_CLOSED_GRACE_SECONDS, stale_after) if db_closed else stale_after
        if idle_seconds < deadline:
            return None

        logger.warning(
            "El apagado de '%s' (PID %s) lleva %ss sin avanzar; forzando el cierre.",
            self.config.name,
            proc.pid,
            int(idle_seconds),
        )
        return self._force_stop()["detail"]

    def stop(self) -> dict:
        if self._stopping_file().exists():
            return self._force_stop()

        self._stop_generation += 1
        generation = self._stop_generation
        return self.runtime.stop(
            graceful_shutdown=lambda: self.execute_soap_command("server shutdown 5"),
            on_graceful=lambda: self._schedule_auto_force_stop(generation, delay=15.0),
        )

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
