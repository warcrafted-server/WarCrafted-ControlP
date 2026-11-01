import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import psutil

from app.emulators.runtime import ProcessControlError, RuntimeBackend, RuntimeMarkers
from app.soap.client import SoapError

logger = logging.getLogger(__name__)

COMPOSE_FILE = "compose.yaml"

# SIGTERM y margen para que el worldserver cierre sus pools antes del SIGKILL de compose.
STOP_GRACE_SECONDS = 60

START_TIMEOUT_SECONDS = 300
QUERY_TIMEOUT_SECONDS = 30
INFO_TIMEOUT_SECONDS = 15

_PERCENT_RE = re.compile(r"([\d.]+)\s*%")
_MEMORY_RE = re.compile(r"([\d.]+)\s*([KMGTPE]i?B)")
_MEMORY_TO_MB = {
    "B": 1 / (1024 * 1024),
    "KIB": 1 / 1024,
    "MIB": 1,
    "GIB": 1024,
    "TIB": 1024**2,
    "PIB": 1024**3,
}
_STARTED_AT_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _parse_percent(value: str | None) -> float | None:
    match = _PERCENT_RE.search(value or "")
    return float(match.group(1)) if match else None


def _parse_memory_mb(value: str | None) -> float | None:
    """'3.139GiB / 8GiB' -> MB del primer valor (la parte usada, no el limite)."""
    used = (value or "").split("/")[0]
    match = _MEMORY_RE.search(used)
    if not match:
        return None
    amount, unit = match.groups()
    factor = _MEMORY_TO_MB.get(unit.upper())
    if factor is None:
        return None
    return round(float(amount) * factor, 1)


def _started_timestamp(value: str | None) -> float | None:
    """State.StartedAt de docker es UTC con fraccion de segundo."""
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], _STARTED_AT_FORMAT).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


class DockerRuntime(RuntimeBackend):
    """Reino en un contenedor de docker compose, controlado solo con la CLI `docker`.

    El estado y el consumo salen de `docker inspect` y `docker stats`: psutil solo
    aporta el PID del contenedor, no el arbol de procesos interno. El "listo" se lee
    del Server.log que AzerothCore escribe en una carpeta montada del host.
    """

    def __init__(
        self,
        *,
        name: str,
        service: str,
        project_dir: str,
        profile: str = "",
        markers: RuntimeMarkers | None = None,
    ):
        self.name = name
        self.service = service
        self.project_dir = project_dir
        self.profile = profile
        self.markers = markers or RuntimeMarkers()
        self._project_name_cache: str | None = None
        self._last_error: str | None = None

    # --- configuracion y nombres -------------------------------------------------

    def _compose_file(self) -> Path:
        return Path(self.project_dir) / COMPOSE_FILE

    def _config_error(self) -> str | None:
        """Un .env a medias no debe tumbar el panel: se devuelve como estado de error."""
        if not self.service:
            return (
                f"Falta el servicio de docker compose de '{self.name}' "
                "(INSTANCE_<N>_DOCKER_SERVICE o AUTH_SERVICE_<M>_DOCKER_SERVICE)."
            )
        if not self.project_dir:
            return (
                f"Falta la carpeta del compose de '{self.name}' "
                "(INSTANCE_<N>_DOCKER_PROJECT_DIR o AUTH_SERVICE_<M>_DOCKER_PROJECT_DIR)."
            )
        if not self._compose_file().is_file():
            return f"No existe el compose de '{self.name}': {self._compose_file()}"
        return None

    def _project_name(self) -> str:
        """Nombre del proyecto compose: el `name:` del compose o la carpeta, como hace compose."""
        if self._project_name_cache is None:
            project = ""
            try:
                for line in self._compose_file().read_text(errors="replace").splitlines():
                    match = re.match(r"^name:\s*([^#\s]+)", line)
                    if match:
                        project = match.group(1).strip("\"'")
                        break
            except OSError:
                project = ""
            self._project_name_cache = project or Path(self.project_dir).name
        return self._project_name_cache

    def _container_name(self) -> str:
        return f"{self._project_name()}-{self.service}-1"

    def _compose(self, *args: str) -> list[str]:
        cmd = ["docker", "compose", "-f", str(self._compose_file())]
        if self.profile:
            cmd += ["--profile", self.profile]
        return cmd + list(args)

    # --- ejecucion ---------------------------------------------------------------

    def _run(self, args: list[str], timeout: float = QUERY_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)

    def _docker_error(self) -> str | None:
        """Fallo global de docker (demonio parado, usuario fuera del grupo) o None si responde."""
        try:
            result = self._run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=INFO_TIMEOUT_SECONDS)
        except FileNotFoundError:
            return "No se encontro la CLI de docker en el host."
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"No se pudo ejecutar 'docker info': {exc}"
        if result.returncode == 0:
            return None
        lines = (result.stderr or result.stdout).strip().splitlines()
        detail = lines[-1] if lines else f"codigo {result.returncode}"
        return (
            f"No se pudo conectar con el demonio de docker ({detail}). Comprueba que esta "
            "en marcha y que el usuario del panel pertenece al grupo 'docker'."
        )

    def _inspect(self) -> tuple[dict | None, str | None]:
        """State del contenedor; (None, None) si el contenedor no existe."""
        config_error = self._config_error()
        if config_error:
            return None, config_error
        name = self._container_name()
        try:
            result = self._run(["docker", "inspect", "--format", "{{json .State}}", name])
        except FileNotFoundError:
            return None, "No se encontro la CLI de docker en el host."
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"No se pudo ejecutar 'docker inspect': {exc}"
        if result.returncode == 0:
            try:
                return json.loads(result.stdout), None
            except ValueError:
                return None, f"Salida de 'docker inspect' no valida para '{name}'."
        if "no such" in (result.stderr or "").lower():
            return None, None
        # Cualquier otro fallo puede ser del contenedor o de docker entero: `docker info`
        # distingue un demonio inaccesible de un nombre de servicio equivocado.
        return None, self._docker_error() or f"No se pudo consultar el contenedor '{name}': {(result.stderr or '').strip()}"

    def _stats(self) -> tuple[float | None, float | None, float | None]:
        """(CPU normalizada a 1 nucleo, % del host, MB de RAM) del contenedor en marcha."""
        try:
            result = self._run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", self._container_name()]
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, None, None
        if result.returncode != 0 or not result.stdout.strip():
            return None, None, None
        try:
            data = json.loads(result.stdout.strip().splitlines()[0])
        except ValueError:
            return None, None, None
        cpu_percent = _parse_percent(data.get("CPUPerc"))
        memory_mb = _parse_memory_mb(data.get("MemUsage"))
        cpu_percent_host = None
        if cpu_percent is not None:
            cpu_percent_host = round(cpu_percent / (psutil.cpu_count() or 1), 1)
        return cpu_percent, cpu_percent_host, memory_mb

    # --- marcadores --------------------------------------------------------------

    def _clear_markers(self) -> None:
        for marker in (self.markers.ready_file, self.markers.stopping_file):
            if marker is not None:
                marker.unlink(missing_ok=True)

    def _drop_stale_markers(self, started_at: float | None) -> None:
        """Los .ready/.stopping sobreviven al contenedor: si son mas viejos que su
        arranque actual, son de un run anterior y mienten sobre el estado."""
        if started_at is None:
            return
        for marker in (self.markers.ready_file, self.markers.stopping_file):
            if marker is None:
                continue
            try:
                if marker.stat().st_mtime < started_at:
                    marker.unlink(missing_ok=True)
            except OSError:
                continue

    # --- interfaz RuntimeBackend -------------------------------------------------

    def find_process(self) -> psutil.Process | None:
        state, error = self._inspect()
        if error or not state or not state.get("Running"):
            return None
        pid = state.get("Pid")
        if not pid:
            return None
        try:
            return psutil.Process(pid)
        except psutil.NoSuchProcess:
            return None

    def get_status(self) -> dict:
        state, error = self._inspect()
        if error:
            if error != self._last_error:
                logger.warning("Runtime docker de '%s': %s", self.name, error)
                self._last_error = error
            return {
                "state": "offline",
                "pid": None,
                "cpu_percent": None,
                "cpu_percent_host": None,
                "memory_mb": None,
                "error": error,
            }
        self._last_error = None

        if not state or not state.get("Running"):
            self._clear_markers()
            return {"state": "offline", "pid": None, "cpu_percent": None, "cpu_percent_host": None, "memory_mb": None}

        self._drop_stale_markers(_started_timestamp(state.get("StartedAt")))
        cpu_percent, cpu_percent_host, memory_mb = self._stats()

        # State.Health solo aparece si la imagen define HEALTHCHECK (las de AzerothCore
        # no lo hacen), asi que el "listo" se sigue leyendo del log montado en el host.
        stopping = self.markers.stopping_file
        if stopping is not None and stopping.exists():
            current = "stopping"
        elif self.markers.is_ready is not None and self.markers.is_ready():
            current = "online"
        else:
            current = "starting"

        return {
            "state": current,
            "pid": state.get("Pid"),
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
        """`docker compose up -d`: la consola y los core dumps los gestiona el contenedor."""
        error = self._config_error() or self._docker_error()
        if error:
            raise ProcessControlError(error)

        self._clear_markers()
        args = self._compose("up", "-d", self.service)
        logger.info("Arrancando '%s' con: %s", self.name, " ".join(args))
        try:
            result = self._run(args, timeout=START_TIMEOUT_SECONDS)
        except FileNotFoundError as exc:
            raise ProcessControlError("No se encontro la CLI de docker en el host.") from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProcessControlError(f"No se pudo ejecutar 'docker compose up': {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ProcessControlError(
                f"No se pudo arrancar '{self.name}': {detail or f'codigo {result.returncode}'}"
            )

        proc = self.find_process()
        pid = proc.pid if proc else None
        logger.info("Contenedor de '%s' arrancado (PID %s).", self.name, pid)
        return {"success": True, "pid": pid}

    def _compose_stop(self, reason: SoapError | None = None) -> dict:
        # Se consulta el contenedor antes de nada para que un docker caido se reporte como
        # error y no como "no estaba en ejecucion".
        state, error = self._inspect()
        if error:
            raise ProcessControlError(error)
        if not state or not state.get("Running"):
            self._clear_markers()
            suffix = f" ({reason})" if reason is not None else ""
            return {"success": False, "detail": f"El servidor no estaba en ejecucion.{suffix}"}

        args = self._compose("stop", "-t", str(STOP_GRACE_SECONDS), self.service)
        try:
            result = self._run(args, timeout=STOP_GRACE_SECONDS + QUERY_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProcessControlError(f"No se pudo detener '{self.name}': {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ProcessControlError(
                f"No se pudo detener '{self.name}': {detail or f'codigo {result.returncode}'}"
            )

        self._clear_markers()
        if reason is not None:
            logger.warning("SOAP fallo para '%s' (%s); contenedor detenido con 'docker compose stop'.", self.name, reason)
            return {
                "success": True,
                "detail": f"El comando SOAP fallo ({reason}); se detuvo el contenedor con 'docker compose stop'.",
            }
        return {"success": True, "detail": "Contenedor detenido con 'docker compose stop'."}

    def stop(
        self,
        graceful_shutdown: Callable[[], str] | None = None,
        on_graceful: Callable[[], None] | None = None,
    ) -> dict:
        """Apagado ordenado via SOAP; si falla, `docker compose stop` (SIGTERM y margen).

        Sin callback SOAP (el authserver no tiene) se usa directamente `docker compose stop`.
        """
        stopping = self.markers.stopping_file
        if stopping is not None:
            stopping.touch()

        if graceful_shutdown is None:
            return self._compose_stop()

        try:
            output = graceful_shutdown()
        except SoapError as exc:
            return self._compose_stop(exc)

        logger.info("Instancia '%s' detenida via SOAP.", self.name)
        if on_graceful is not None:
            on_graceful()
        return {"success": True, "detail": output}

    def force_stop(self) -> dict:
        """`docker kill`: ya se intento el apagado ordenado y el reino sigue vivo."""
        state, error = self._inspect()
        if error:
            raise ProcessControlError(error)
        if not state or not state.get("Running"):
            self._clear_markers()
            return {"success": False, "detail": "El servidor no estaba en ejecucion."}

        args = ["docker", "kill", self._container_name()]
        try:
            result = self._run(args)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProcessControlError(f"No se pudo forzar la detencion de '{self.name}': {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ProcessControlError(
                f"No se pudo forzar la detencion de '{self.name}': {detail or f'codigo {result.returncode}'}"
            )

        self._clear_markers()
        detail = "Contenedor detenido a la fuerza (docker kill)."
        logger.warning("Detencion forzada de '%s' (PID %s): %s", self.name, state.get("Pid"), detail)
        return {"success": True, "detail": detail}
