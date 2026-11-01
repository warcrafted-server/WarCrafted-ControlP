import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from fastapi import HTTPException, status

from app.config import BASE_DIR
from app.fs_utils import extract_tarball, overlay_copy
from app.github_client import download_tarball, fetch_repo_file

logger = logging.getLogger(__name__)

VERSION_FILE = BASE_DIR / "VERSION"
REQUIREMENTS_FILE = BASE_DIR / "requirements.txt"

_CHANGELOG_HEADER_RE = re.compile(r"^## \[", re.MULTILINE)


def current_version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return "0.0.0"


def _version_tuple(version: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in version.split("-")[0].split("."))
    except ValueError:
        return None


def _is_newer(remote: str, installed: str) -> bool:
    """Solo ofrece actualizar si el remoto es mayor: con `!=` una copia local por delante
    de GitHub (aun sin subir) se presentaba como actualizacion y bajaba de version."""
    remote_t, installed_t = _version_tuple(remote), _version_tuple(installed)
    if remote_t is None or installed_t is None:
        return remote != installed
    return remote_t > installed_t


def _extract_changelog_section(changelog_text: str, version: str) -> str:
    """Extrae el bloque de un CHANGELOG.md (formato Keep a Changelog) para `version`."""
    match = re.search(rf"^## \[{re.escape(version)}\].*$", changelog_text, re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    rest = changelog_text[start:]
    next_header = _CHANGELOG_HEADER_RE.search(rest)
    section = rest[: next_header.start()] if next_header else rest
    return re.sub(r"^### +", "", section.strip(), flags=re.MULTILINE)


def check_update(token: str, repo: str) -> dict:
    """Compara la version instalada del panel con el archivo VERSION del repo remoto."""
    remote_version = fetch_repo_file(token, repo, "VERSION")
    if remote_version is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo leer VERSION de {repo}. Comprueba que el token tambien tenga acceso a ese repositorio.",
        )
    remote_version = remote_version.strip()
    installed = current_version()
    update_available = _is_newer(remote_version, installed)

    changelog = ""
    if update_available:
        changelog_text = fetch_repo_file(token, repo, "CHANGELOG.md")
        if changelog_text:
            changelog = _extract_changelog_section(changelog_text, remote_version)

    return {
        "installed_version": installed,
        "remote_version": remote_version,
        "update_available": update_available,
        "changelog": changelog,
    }


def apply_update(token: str, repo: str) -> dict:
    """Descarga la version actual del panel y la fusiona sobre la instalacion activa.

    Nunca borra nada que no venga en el tarball: `.env`, `data/`, `.venv/` y los
    plugins instalados via la Tienda quedan intactos porque no forman parte de este
    repo. Si `requirements.txt` cambio, reinstala dependencias en el mismo venv antes
    de devolver el resultado; si esa instalacion falla, no se debe reiniciar el panel
    (el codigo nuevo puede depender de paquetes que aun no estan instalados).
    """
    old_version = current_version()
    old_requirements = REQUIREMENTS_FILE.read_text() if REQUIREMENTS_FILE.exists() else ""

    tarball = download_tarball(token, repo)

    tmp_dir = Path(tempfile.mkdtemp(prefix="controlp-update-"))
    try:
        found = extract_tarball(tarball, tmp_dir, subpath=None)
        if not found:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="El tarball del repositorio esta vacio")
        overlay_copy(tmp_dir, BASE_DIR)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    new_version = current_version()
    new_requirements = REQUIREMENTS_FILE.read_text() if REQUIREMENTS_FILE.exists() else ""
    requirements_changed = new_requirements != old_requirements

    pip_output = ""
    if requirements_changed:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)],
            capture_output=True, text=True, timeout=300, cwd=BASE_DIR,
        )
        pip_output = (result.stdout + result.stderr)[-4000:]
        if result.returncode != 0:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"El codigo se actualizo a v{new_version} pero fallo la instalacion de dependencias nuevas. "
                    "NO reinicies el panel todavia: revisa el error e instala a mano con "
                    f"'pip install -r requirements.txt'. Salida de pip:\n{pip_output}"
                ),
            )

    return {
        "old_version": old_version,
        "new_version": new_version,
        "requirements_changed": requirements_changed,
        "pip_output": pip_output,
    }


def schedule_restart(delay_seconds: float = 1.5) -> None:
    """Programa el reinicio del proceso actual; requiere un supervisor externo para volver a levantarlo.

    Sale con codigo de error a proposito: bajo `Restart=on-failure` en systemd eso
    tambien dispara el reinicio, no solo bajo `Restart=always` (mas recomendado para
    este caso, ver INSTALL.md). Si el panel no corre bajo un supervisor asi, quedara
    caido hasta que alguien lo arranque a mano.
    """

    def _restart():
        time.sleep(delay_seconds)
        logger.warning("Reiniciando el panel para aplicar una actualizacion...")
        os._exit(1)

    threading.Thread(target=_restart, daemon=True).start()
