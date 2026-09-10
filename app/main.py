from dotenv import load_dotenv

load_dotenv()

import asyncio
import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models
from app.api import auth, console, plugins as plugins_api, servers, system
from app.config import BASE_DIR, get_settings
from app.core_update import current_version
from app.database import init_db
from app.deps import get_db
from app.emulators import shutdown_watchdog
from app.plugins.loader import load_plugins
from app.security import decode_access_token

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    watchdog = asyncio.create_task(shutdown_watchdog.watch())
    try:
        yield
    finally:
        watchdog.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")
# Cache-buster para /static/*: sin esto, un navegador con el JS/CSS ya cacheado
# sigue ejecutando la version vieja tras un `git pull` + reinicio del panel,
# aunque el servidor ya sirva el fichero nuevo (paso silenciosamente por esto
# en la 0.7.0: el frontend viejo leia un campo de la API que ya no existe).
templates.env.globals["app_version"] = current_version()

app.include_router(auth.router)
app.include_router(servers.router)
app.include_router(system.router)
app.include_router(console.router)
app.include_router(plugins_api.router)

loaded_plugins = load_plugins()
app.state.plugins = loaded_plugins

for plugin_name, router, metadata in loaded_plugins:
    prefix = f"/api/v1/plugins/{plugin_name}"
    app.include_router(router, prefix=prefix, tags=[f"plugin: {metadata.name}"])
    if metadata.description:
        logger.info(f"Plugin: {metadata.description}")


def _current_user_or_none(request: Request, db: Session) -> models.User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    username = decode_access_token(token)
    if not username:
        return None
    return db.query(models.User).filter(models.User.username == username).first()


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    if _current_user_or_none(request, db):
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")


@app.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    if _current_user_or_none(request, db):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {"request": request, "app_name": settings.app_name})


@app.get("/dashboard")
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "app_name": settings.app_name, "user": user}
    )


@app.get("/plugins/store")
def plugin_store_page(request: Request, db: Session = Depends(get_db)):
    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "plugin_store.html", {"request": request, "app_name": settings.app_name, "user": user}
    )


@app.get("/console/{instance_id}")
def console_page(request: Request, instance_id: str, db: Session = Depends(get_db)):
    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "console.html",
        {"request": request, "app_name": settings.app_name, "instance_id": instance_id},
    )
