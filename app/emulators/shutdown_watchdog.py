import asyncio
import logging

from app.config import get_settings
from app.emulators.base import ProcessControlError
from app.emulators.manager import get_manager

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 15


def sweep(stale_after: float) -> None:
    for driver in get_manager().list_drivers():
        if not driver.config.enabled:
            continue
        try:
            driver.force_stop_if_shutdown_stuck(stale_after)
        except (ProcessControlError, OSError) as exc:
            logger.error("No se pudo forzar el cierre de '%s': %s", driver.config.name, exc)


async def watch() -> None:
    """Vigila los apagados que se quedan colgados y los remata.

    Sin esto, un worldserver trabado al salir se queda en RAM para siempre: el reino
    no vuelve, y un reinicio nocturno que espere a que el proceso muera nunca llega a
    reiniciar la maquina.

    `SHUTDOWN_STUCK_TIMEOUT=0` lo desactiva.
    """
    stale_after = get_settings().shutdown_stuck_timeout
    if stale_after <= 0:
        logger.info("Vigilancia de apagados colgados desactivada (SHUTDOWN_STUCK_TIMEOUT=0).")
        return
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        try:
            # En un hilo: la comprobacion lee ficheros y la parada forzada espera
            # hasta 5s a que el proceso muera, y eso congelaria el panel entero.
            await asyncio.to_thread(sweep, stale_after)
        except Exception:
            logger.exception("Fallo la vigilancia de apagados colgados.")
