import asyncio
import logging
import time
from pathlib import Path

from app.config import get_settings
from app.emulators import log_manager
from app.emulators.manager import get_manager

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 3600

_ACTIVE_NAMES = set(log_manager.NATIVE_CATEGORIES.values())


def purge_native_dir(logs_dir: Path, retention_days: int, max_total_mb: int) -> int:
    """Borra de la carpeta de logs nativa los ficheros rotados o antiguos.

    Los activos (Server.log, Errors.log...) no se tocan: el worldserver los tiene abiertos
    y truncarlos desde fuera deja huecos. Su tamano lo acota el limite del Appender en el
    .conf. Aqui solo caen las copias que AzerothCore deja al rotar y los ficheros con fecha.
    """
    if not logs_dir.is_dir():
        return 0
    removed = 0
    cutoff = time.time() - retention_days * 86400
    rotated = []
    for path in logs_dir.iterdir():
        if not path.is_file() or path.name in _ACTIVE_NAMES:
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
            else:
                rotated.append(path)
        except OSError:
            continue
    if max_total_mb > 0:
        rotated.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        total = 0
        for path in rotated:
            try:
                total += path.stat().st_size
                if total > max_total_mb * 1_000_000:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    return removed


def sweep() -> None:
    settings = get_settings()
    for driver in get_manager().list_drivers():
        cfg = driver.config
        try:
            log_manager.purge_old_logs(
                driver._log_instance_dir(), settings.logs_retention_days, settings.logs_max_runs, settings.logs_max_total_mb
            )
            if cfg.acore_logs_dir:
                removed = purge_native_dir(Path(cfg.acore_logs_dir), settings.logs_retention_days, settings.logs_max_total_mb)
                if removed:
                    logger.info("Logs nativos de '%s': %d ficheros antiguos borrados.", cfg.name, removed)
        except OSError as exc:
            logger.error("No se pudieron purgar los logs de '%s': %s", cfg.name, exc)


async def watch() -> None:
    """Purga los logs viejos cada hora; sin esto solo se purgaba al iniciar una instancia desde el panel."""
    while True:
        try:
            await asyncio.to_thread(sweep)
        except Exception:
            logger.exception("Fallo la purga periodica de logs.")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
