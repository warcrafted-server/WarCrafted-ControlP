import logging
from dataclasses import dataclass
from pathlib import Path

import psutil
import pymysql

from app.config import DATA_DIR
from app.emulators import process_control
from app.emulators.base import ProcessControlError
from app.emulators.runtime import NativeRuntime, RuntimeMarkers

logger = logging.getLogger(__name__)

PID_DIR = DATA_DIR / "pids"


@dataclass
class AuthServiceConfig:
    id: str
    name: str
    enabled: bool
    process_name: str
    start_cmd: str
    workdir: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    db_name: str = "acore_auth"


class AuthServiceDriver:
    """Controla un proceso authserver, compartido opcionalmente por varios worldservers.

    Sin SOAP ni consola (el authserver de AzerothCore no expone ninguno de los dos): el
    estado es solo si el proceso existe, y la parada es siempre SIGTERM con escalada a
    SIGKILL en la misma llamada.
    """

    def __init__(self, config: AuthServiceConfig):
        self.config = config
        PID_DIR.mkdir(parents=True, exist_ok=True)
        self.runtime = NativeRuntime(
            name=config.name,
            process_name=config.process_name,
            workdir=config.workdir,
            start_cmd=config.start_cmd,
            pid_file=self._pid_file(),
            markers=RuntimeMarkers(stopping_file=self._stopping_file()),
        )

    def _pid_file(self) -> Path:
        return PID_DIR / f"authsvc-{self.config.id}.pid"

    def _stopping_file(self) -> Path:
        return PID_DIR / f"authsvc-{self.config.id}.stopping"

    def find_process(self) -> psutil.Process | None:
        return self.runtime.find_process()

    def get_status(self) -> dict:
        proc = self.find_process()
        if not proc:
            self._stopping_file().unlink(missing_ok=True)
            return {"state": "offline", "pid": None}
        if self._stopping_file().exists():
            return {"state": "stopping", "pid": proc.pid}
        return {"state": "online", "pid": proc.pid}

    def start(self) -> dict:
        existing = self.find_process()
        if existing:
            return {"success": True, "detail": "El authserver ya esta en ejecucion.", "pid": existing.pid}

        if not self.config.start_cmd:
            raise ProcessControlError(f"No hay START_CMD configurado para el authserver '{self.config.name}'.")

        started = self.runtime.start(subject="El authserver")
        return {"success": True, "detail": "Authserver iniciado correctamente.", "pid": started["pid"]}

    def stop(self) -> dict:
        proc = self.find_process()
        if not proc:
            self._stopping_file().unlink(missing_ok=True)
            return {"success": False, "detail": "El authserver no estaba en ejecucion."}

        self._stopping_file().touch()
        try:
            forced = self.runtime.terminate_process(proc)
            if forced:
                detail = f"El authserver (PID {proc.pid}) no respondio a la señal de apagado; se forzo el cierre (SIGKILL)."
            else:
                detail = f"Authserver detenido (PID {proc.pid})."
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            self._stopping_file().unlink(missing_ok=True)
            logger.error("Fallo al detener el authserver '%s': %s", self.config.name, exc)
            raise ProcessControlError(f"No se pudo detener el authserver (PID {proc.pid}): {exc}") from exc
        process_control.clear_pid(self._pid_file())
        self._stopping_file().unlink(missing_ok=True)
        logger.info("Authserver '%s' detenido (PID %s): %s", self.config.name, proc.pid, detail)
        return {"success": True, "detail": detail}

    def get_account_stats(self) -> dict:
        """Cuentas totales y conectadas (acore_auth.account); None si la BD no responde."""
        cfg = self.config
        try:
            conn = pymysql.connect(
                host=cfg.db_host,
                port=cfg.db_port,
                user=cfg.db_user,
                password=cfg.db_pass,
                database=cfg.db_name,
                connect_timeout=3,
            )
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM account")
                    total = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM account WHERE online > 0")
                    online = cursor.fetchone()[0]
                    return {"accounts_total": int(total), "accounts_online": int(online)}
        except Exception:
            return {"accounts_total": None, "accounts_online": None}
