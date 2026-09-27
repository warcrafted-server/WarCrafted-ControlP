from fastapi import APIRouter, Depends, HTTPException, Request, status

from app import models, schemas
from app.config import get_settings
from app.deps import get_current_user, require_admin
from app.github_client import verify_repo_access
from app.plugins import store
from app.plugins.loader import load_single_plugin

router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])


def _plugin_summary(slug: str, metadata) -> dict:
    return {
        "slug": slug,
        "name": metadata.name,
        "version": metadata.version,
        "description": metadata.description,
        "has_ui": metadata.has_ui,
        "title": metadata.ui_title or metadata.name,
        "route": metadata.ui_route,
        "icon": metadata.icon,
        "background_script": metadata.background_script,
    }


def _unmount_plugin_routes(app, prefix: str) -> None:
    """Quita del router activo las rutas ya montadas de un plugin, para poder remontarlo tras actualizarlo."""
    app.router.routes[:] = [
        r for r in app.router.routes
        if not (getattr(r, "path", "") == prefix or getattr(r, "path", "").startswith(prefix + "/"))
    ]


def _mount_plugin(app, loaded: tuple) -> None:
    """Monta (o remonta, si ya existia) un plugin en la app activa, sin reiniciar el panel."""
    slug, plugin_router, metadata = loaded
    prefix = f"/api/v1/plugins/{slug}"
    _unmount_plugin_routes(app, prefix)
    app.include_router(plugin_router, prefix=prefix, tags=[f"plugin: {metadata.name}"])
    remaining = [(s, r, m) for s, r, m in app.state.plugins if s != slug]
    app.state.plugins = [*remaining, loaded]


@router.get("")
@router.get("/")
def list_plugins(request: Request, current_user: models.User = Depends(get_current_user)):
    """Lista los plugins activos y sus metadatos, para que la navbar arme el menu."""
    return [_plugin_summary(slug, metadata) for slug, _router, metadata in request.app.state.plugins]


@router.post("/setup-token")
def setup_token(payload: schemas.GithubTokenRequest, current_user: models.User = Depends(require_admin)):
    """Valida un token de GitHub contra el repo de plugins y lo guarda en .env."""
    repo = get_settings().github_plugin_repo
    verify_repo_access(payload.token, repo)
    store.write_token(payload.token)
    return {"success": True, "message": "Token guardado correctamente"}


@router.get("/catalog")
def get_catalog(request: Request, current_user: models.User = Depends(get_current_user)):
    """Lista el catalogo de plugins del repo de GitHub, indicando cuales ya estan instalados y si hay version nueva."""
    settings = get_settings()
    if not settings.github_plugin_token:
        return {"configured": False, "plugins": []}

    installed_versions = {slug: metadata.version for slug, _r, metadata in request.app.state.plugins}
    plugins = store.fetch_catalog(settings.github_plugin_token, settings.github_plugin_repo)
    for entry in plugins:
        installed_version = installed_versions.get(entry["slug"])
        entry["installed"] = installed_version is not None
        entry["installed_version"] = installed_version
        entry["update_available"] = installed_version is not None and installed_version != entry["version"]
    return {"configured": True, "plugins": plugins}


@router.post("/install/{plugin_name}")
def install_plugin(plugin_name: str, request: Request, current_user: models.User = Depends(require_admin)):
    """Descarga un plugin del catalogo y lo monta en caliente en la app activa, sin reiniciar el panel."""
    settings = get_settings()
    if not settings.github_plugin_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No hay un token de GitHub configurado")

    store.install_plugin(settings.github_plugin_token, settings.github_plugin_repo, plugin_name)

    loaded = load_single_plugin(plugin_name)
    if not loaded:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"El plugin '{plugin_name}' se descargo pero no expone un router.py valido",
        )

    _mount_plugin(request.app, loaded)
    slug, _router, metadata = loaded
    return {"success": True, "plugin": _plugin_summary(slug, metadata)}


@router.post("/update/{plugin_name}")
def update_plugin(plugin_name: str, request: Request, current_user: models.User = Depends(require_admin)):
    """Descarga la version actual de un plugin ya instalado y la remonta en caliente."""
    settings = get_settings()
    if not settings.github_plugin_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No hay un token de GitHub configurado")

    store.update_plugin(settings.github_plugin_token, settings.github_plugin_repo, plugin_name)

    loaded = load_single_plugin(plugin_name)
    if not loaded:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"El plugin '{plugin_name}' se actualizo pero no expone un router.py valido",
        )

    _mount_plugin(request.app, loaded)
    slug, _router, metadata = loaded
    return {"success": True, "plugin": _plugin_summary(slug, metadata)}
