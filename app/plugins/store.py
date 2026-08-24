import json
import logging
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException, status

from app.config import BASE_DIR, get_settings
from app.fs_utils import extract_tarball, overlay_copy
from app.github_client import download_tarball, fetch_repo_file, list_repo_dir

logger = logging.getLogger(__name__)

ENV_PATH = BASE_DIR / ".env"
PLUGINS_DIR = BASE_DIR / "app" / "plugins"
PLUGIN_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def write_token(token: str) -> None:
    """Actualiza (o añade) GITHUB_PLUGIN_TOKEN en .env sin tocar el resto de variables."""
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    new_line = f"GITHUB_PLUGIN_TOKEN={token}"
    for i, line in enumerate(lines):
        if line.startswith("GITHUB_PLUGIN_TOKEN="):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)

    tmp_path = ENV_PATH.parent / f"{ENV_PATH.name}.tmp"
    tmp_path.write_text("\n".join(lines) + "\n")
    tmp_path.replace(ENV_PATH)

    os.environ["GITHUB_PLUGIN_TOKEN"] = token
    get_settings.cache_clear()


def _catalog_entry(token: str, repo: str, name: str) -> dict:
    manifest_raw = fetch_repo_file(token, repo, f"{name}/manifest.json")
    try:
        manifest = json.loads(manifest_raw) if manifest_raw else {}
    except json.JSONDecodeError:
        manifest = {}
    return {
        "slug": name,
        "name": manifest.get("name", name),
        "version": manifest.get("version", "0.0.0"),
        "description": manifest.get("description", ""),
        "changelog": manifest.get("changelog", ""),
        "installed": (PLUGINS_DIR / name).is_dir(),
    }


def fetch_catalog(token: str, repo: str) -> list[dict]:
    """Lista las carpetas de módulo del repo de plugins, marcando cuáles ya están instaladas.

    Un manifest.json por módulo, todos independientes entre si: se piden en paralelo
    (un hilo por módulo) en vez de uno detrás de otro, para que la Tienda no tarde mas
    cuanto mas crezca el catalogo.
    """
    names = [
        entry["name"]
        for entry in list_repo_dir(token, repo)
        if entry.get("type") == "dir" and not entry["name"].startswith((".", "_"))
    ]
    if not names:
        return []
    with ThreadPoolExecutor(max_workers=min(len(names), 8)) as pool:
        return list(pool.map(lambda name: _catalog_entry(token, repo, name), names))


def install_plugin(token: str, repo: str, plugin_name: str) -> None:
    """Descarga la carpeta `plugin_name` del repo y la extrae limpia en app/plugins/<plugin_name>/."""
    if not PLUGIN_NAME_RE.match(plugin_name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nombre de plugin invalido")

    target_dir = PLUGINS_DIR / plugin_name
    if target_dir.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"El plugin '{plugin_name}' ya esta instalado")

    tarball = download_tarball(token, repo)

    tmp_dir = target_dir.with_name(f".{plugin_name}.install-tmp")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True)

    try:
        found = extract_tarball(tarball, tmp_dir, subpath=plugin_name)
        if not found:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"'{plugin_name}' no existe en el repositorio")
        tmp_dir.replace(target_dir)
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Error al extraer el plugin: {exc}") from exc


def update_plugin(token: str, repo: str, plugin_name: str) -> None:
    """Descarga la version actual de `plugin_name` y la fusiona sobre la carpeta ya instalada.

    Nunca borra archivos que no vengan en el tarball (backups u otros datos que el
    propio plugin haya generado en tiempo de ejecucion quedan intactos).
    """
    if not PLUGIN_NAME_RE.match(plugin_name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nombre de plugin invalido")

    target_dir = PLUGINS_DIR / plugin_name
    if not target_dir.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"El plugin '{plugin_name}' no esta instalado")

    tarball = download_tarball(token, repo)

    tmp_dir = target_dir.with_name(f".{plugin_name}.update-tmp")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True)

    try:
        found = extract_tarball(tarball, tmp_dir, subpath=plugin_name)
        if not found:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"'{plugin_name}' no existe en el repositorio")
        overlay_copy(tmp_dir, target_dir)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Error al extraer la actualizacion: {exc}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
