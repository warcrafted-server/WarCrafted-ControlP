import base64
import logging

import requests
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 15

# Sesion compartida: reutiliza la conexion TCP/TLS a api.github.com entre llamadas
# (el catalogo de la Tienda hace una por modulo) en vez de abrir una nueva cada vez.
_session = requests.Session()


def headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def verify_repo_access(token: str, repo: str) -> None:
    """Comprueba que el token es valido y da acceso de lectura al repo indicado."""
    try:
        response = _session.get(f"{GITHUB_API}/repos/{repo}", headers=headers(token), timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"No se pudo contactar con GitHub: {exc}") from exc

    if response.status_code == 401:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Token de GitHub invalido")
    if response.status_code == 404:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"El token es valido pero no tiene acceso al repositorio {repo}",
        )
    if not response.ok:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub respondio con error {response.status_code} al verificar el token",
        )


def list_repo_dir(token: str, repo: str, path: str = "") -> list[dict]:
    """Contenido de un directorio del repo (formato de la API 'contents' de GitHub)."""
    try:
        response = _session.get(
            f"{GITHUB_API}/repos/{repo}/contents/{path}", headers=headers(token), timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"No se pudo contactar con GitHub: {exc}") from exc

    if not response.ok:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub respondio con error {response.status_code} al listar {repo}/{path}",
        )
    return response.json()


def fetch_repo_file(token: str, repo: str, path: str) -> str | None:
    """Contenido de texto de un archivo del repo, o None si no existe o no se pudo leer."""
    try:
        response = _session.get(
            f"{GITHUB_API}/repos/{repo}/contents/{path}", headers=headers(token), timeout=REQUEST_TIMEOUT
        )
        if response.ok:
            content = response.json()
            return base64.b64decode(content["content"]).decode("utf-8")
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning(f"No se pudo leer {path} de {repo}: {exc}")
    return None


def download_tarball(token: str, repo: str) -> bytes:
    try:
        response = _session.get(f"{GITHUB_API}/repos/{repo}/tarball", headers=headers(token), timeout=60)
    except requests.RequestException as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"No se pudo descargar {repo}: {exc}") from exc

    if not response.ok:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub respondio con error {response.status_code} al descargar {repo}",
        )
    return response.content
