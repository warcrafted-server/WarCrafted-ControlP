import gzip
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pymysql
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.config import BASE_DIR
from app.database import SessionLocal
from app.emulators.manager import get_manager
from app.security import decode_access_token
from app.soap.client import SoapError

_login_attempts = defaultdict(list)
_cleanup_last = 0


def _cleanup_old_attempts() -> None:
    global _cleanup_last
    now = time.time()
    if now - _cleanup_last < 60:
        return
    _cleanup_last = now
    for key in list(_login_attempts.keys()):
        _login_attempts[key] = [t for t in _login_attempts[key] if now - t < 900]
        if not _login_attempts[key]:
            del _login_attempts[key]


def check_login_rate_limit(request: Request, username: str) -> None:
    _cleanup_old_attempts()
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{username}"
    now = time.time()
    _login_attempts[key] = [t for t in _login_attempts[key] if now - t < 900]
    if len(_login_attempts[key]) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos de inicio de sesion. Intenta de nuevo mas tarde."
        )


def record_login_attempt(request: Request, username: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{username}"
    _login_attempts[key].append(time.time())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _extract_token(request: Request) -> str | None:
    token = request.cookies.get("access_token")
    if token:
        return token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ")
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido o expirado")
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    return user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requiere permisos de administrador")
    return current_user


def get_servers_snapshot() -> list[dict]:
    """Estado actual (CPU/RAM/jugadores/diff) de las instancias habilitadas.

    Pensada para tareas en segundo plano de plugins (hilos propios, sin
    request HTTP ni usuario autenticado) que necesiten leer estos datos
    igual que ya hace GET /api/servers, sin acceder directamente a
    EmulatorManager (fuera del contrato de importaciones de los plugins).
    """
    snapshot = []
    for driver in get_manager().list_drivers():
        if not driver.config.enabled:
            continue
        status_info = driver.get_status()
        snapshot.append(
            {
                "id": driver.config.id,
                "name": driver.config.name,
                "state": status_info["state"],
                "cpu_percent": status_info["cpu_percent"],
                "cpu_percent_host": status_info["cpu_percent_host"],
                "memory_mb": status_info["memory_mb"],
                "players_online": status_info["players_online"],
                "update_diff_ms": status_info["update_diff_ms"],
            }
        )
    return snapshot


def get_instance_modules_conf_dir(instance_id: str) -> Path | None:
    """Directorio etc/modules/ de una instancia habilitada, o None si no existe.

    Deriva la ruta del WORKDIR (etc/ es hermano de bin/), para que un plugin
    pueda listar/editar los .conf de los modulos sin conocer el layout de
    AzerothCore ni importar EmulatorManager directamente.
    """
    driver = get_manager().get_driver(instance_id)
    if not driver or not driver.config.enabled or not driver.config.workdir:
        return None
    conf_dir = Path(driver.config.workdir).parent / "etc" / "modules"
    return conf_dir if conf_dir.is_dir() else None


def get_instance_etc_dir(instance_id: str) -> Path | None:
    """Directorio etc/ de una instancia habilitada (padre de etc/modules/), o None si no existe.

    Da acceso a worldserver.conf/authserver.conf, separado de
    get_instance_modules_conf_dir() porque un plugin puede querer solo uno de los dos.
    """
    driver = get_manager().get_driver(instance_id)
    if not driver or not driver.config.enabled or not driver.config.workdir:
        return None
    etc_dir = Path(driver.config.workdir).parent / "etc"
    return etc_dir if etc_dir.is_dir() else None


def reload_instance_config(instance_id: str) -> str:
    """Envia 'reload config' via SOAP a una instancia habilitada y devuelve la salida.

    Fijo a ese comando exacto (no un ejecutor generico) para que un plugin
    pueda aplicar cambios de configuracion sin abrir una via de ejecucion
    arbitraria de comandos GM.
    """
    driver = get_manager().get_driver(instance_id)
    if not driver or not driver.config.enabled:
        raise RuntimeError("Instancia no encontrada o deshabilitada.")
    try:
        return driver.execute_soap_command("reload config")
    except SoapError as exc:
        raise RuntimeError(f"No se pudo recargar la configuracion via SOAP: {exc}") from exc


def execute_gm_command(instance_id: str, command: str) -> str:
    """Ejecuta cualquier comando GM via SOAP en una instancia habilitada.

    A diferencia de reload_instance_config(), este acepta el comando que le pase
    el plugin: es la misma superficie que ya tiene la consola nativa del panel
    (`/ws/console`), aqui protegida ademas con require_admin. El plugin que lo
    use es responsable de construir cadenas seguras (citar y escapar texto libre).
    """
    driver = get_manager().get_driver(instance_id)
    if not driver or not driver.config.enabled:
        raise RuntimeError("Instancia no encontrada o deshabilitada.")
    try:
        return driver.execute_soap_command(command)
    except SoapError as exc:
        raise RuntimeError(f"Comando SOAP fallido: {exc}") from exc


def _connect_db(driver, database: str) -> pymysql.connections.Connection | None:
    if not driver or not driver.config.enabled or not database:
        return None
    try:
        return pymysql.connect(
            host=driver.config.db_host,
            port=driver.config.db_port,
            user=driver.config.db_user,
            password=driver.config.db_pass,
            database=database,
            connect_timeout=3,
        )
    except Exception:
        return None


def list_online_players(instance_id: str) -> list[dict]:
    """Nombre/raza/clase/nivel/mapa/guid de los personajes conectados (db_characters).

    Sin ping/latencia: AzerothCore no lo guarda en base de datos, vive solo en
    memoria del worldserver (WorldSession::m_latency) mientras dura la sesion.
    """
    driver = get_manager().get_driver(instance_id)
    conn = _connect_db(driver, driver.config.db_characters if driver else "")
    if not conn:
        return []
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT guid, name, race, class, level, map FROM characters WHERE online = 1"
                )
                columns = ["guid", "name", "race", "class", "level", "map"]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception:
        return []


def search_items(instance_id: str, query: str, limit: int = 20) -> list[dict]:
    """Objetos cuyo nombre contiene `query` (db_world.item_template), para autocompletado."""
    driver = get_manager().get_driver(instance_id)
    conn = _connect_db(driver, driver.config.db_world if driver else "")
    if not conn or not query:
        return []
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT entry, name FROM item_template WHERE name LIKE %s ORDER BY name LIMIT %s",
                    (f"%{query}%", limit),
                )
                return [{"entry": row[0], "name": row[1]} for row in cursor.fetchall()]
    except Exception:
        return []


def search_spells(instance_id: str, query: str, limit: int = 20) -> list[dict]:
    """Hechizos cuyo nombre contiene `query` (db_world.spell_dbc), para autocompletado."""
    driver = get_manager().get_driver(instance_id)
    conn = _connect_db(driver, driver.config.db_world if driver else "")
    if not conn or not query:
        return []
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT ID, Name_Lang_enUS FROM spell_dbc WHERE Name_Lang_enUS LIKE %s ORDER BY Name_Lang_enUS LIMIT %s",
                    (f"%{query}%", limit),
                )
                return [{"id": row[0], "name": row[1]} for row in cursor.fetchall()]
    except Exception:
        return []


def search_teleports(instance_id: str, query: str, limit: int = 20) -> list[dict]:
    """Ubicaciones guardadas cuyo nombre contiene `query` (db_world.game_tele)."""
    driver = get_manager().get_driver(instance_id)
    conn = _connect_db(driver, driver.config.db_world if driver else "")
    if not conn or not query:
        return []
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT name, map FROM game_tele WHERE name LIKE %s ORDER BY name LIMIT %s",
                    (f"%{query}%", limit),
                )
                return [{"name": row[0], "map": row[1]} for row in cursor.fetchall()]
    except Exception:
        return []


_DB_SCOPE_FIELD = {
    "auth": "db_auth",
    "characters": "db_characters",
    "world": "db_world",
    "playerbots": "db_playerbots",  # opcional: solo si la instancia usa mod-playerbots
}


def _db_name_for_scope(driver, scope: str) -> str:
    return getattr(driver.config, _DB_SCOPE_FIELD.get(scope, ""), "") if driver else ""


def get_instance_database_scopes(instance_id: str) -> list[str]:
    """Bases de datos configuradas para esta instancia: "auth", "characters", "world".

    Los tres campos ya existen en toda instancia habilitada; una lista vacia solo
    significa que la instancia no existe o esta deshabilitada.
    """
    driver = get_manager().get_driver(instance_id)
    if not driver or not driver.config.enabled:
        return []
    return [scope for scope in _DB_SCOPE_FIELD if _db_name_for_scope(driver, scope)]


def get_instance_database_sizes(instance_id: str) -> dict[str, dict]:
    """Tamaño en MB y nº de tablas de cada base de datos configurada (information_schema)."""
    driver = get_manager().get_driver(instance_id)
    if not driver or not driver.config.enabled:
        return {}
    sizes = {}
    for scope in _DB_SCOPE_FIELD:
        db_name = _db_name_for_scope(driver, scope)
        if not db_name:
            continue
        conn = _connect_db(driver, "information_schema")
        if not conn:
            continue
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*), COALESCE(SUM(data_length + index_length), 0) "
                        "FROM information_schema.tables WHERE table_schema = %s",
                        (db_name,),
                    )
                    table_count, total_bytes = cursor.fetchone()
                    sizes[scope] = {
                        "database": db_name,
                        "table_count": table_count,
                        "size_mb": round(float(total_bytes) / (1024 * 1024), 1),
                    }
        except Exception:
            continue
    return sizes


def _mysql_defaults_file(driver) -> str:
    """--defaults-extra-file temporal: evita pasar la contraseña en argv (visible en `ps`)."""
    fh = tempfile.NamedTemporaryFile(mode="w", suffix=".cnf", delete=False)
    fh.write(
        f"[client]\nhost={driver.config.db_host}\nport={driver.config.db_port}\n"
        f"user={driver.config.db_user}\npassword={driver.config.db_pass}\n"
    )
    fh.close()
    os.chmod(fh.name, 0o600)
    return fh.name


# Backups (base de datos y ejecutables del core) siempre en el mismo sitio dentro del
# propio panel, no en la carpeta de un plugin: existen tengamos el plugin instalado o no,
# y sobreviven a que se desinstale/reinstale. Los plugins solo deciden cuándo respaldar y
# con qué política de retención; el core es quien sabe dónde y cómo.
BACKUPS_DIR = BASE_DIR / "app" / "backups"
DB_BACKUPS_DIR = BACKUPS_DIR / "db"
CORE_BACKUPS_DIR = BACKUPS_DIR / "core"
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _db_backup_dir(instance_id: str, scope: str) -> Path:
    d = DB_BACKUPS_DIR / _SAFE_NAME_RE.sub("_", instance_id) / scope
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_backup_file(instance_id: str, scope: str, filename: str) -> Path:
    backup_dir = _db_backup_dir(instance_id, scope)
    candidate = (backup_dir / filename).resolve()
    if candidate.parent != backup_dir.resolve() or not candidate.is_file():
        raise RuntimeError("El archivo de backup no existe.")
    return candidate


def backup_instance_database(instance_id: str, scope: str) -> Path:
    """Vuelca (mysqldump) la base `scope` de la instancia, comprimida con gzip, bajo
    app/backups/db/<instancia>/<scope>/ (siempre ahí, lo dispare el plugin que lo dispare).
    """
    driver = get_manager().get_driver(instance_id)
    if not driver or not driver.config.enabled:
        raise RuntimeError("Instancia no encontrada o deshabilitada.")
    db_name = _db_name_for_scope(driver, scope)
    if not db_name:
        raise RuntimeError(f"La instancia no tiene configurada la base de datos '{scope}'.")

    # Microsegundos en el nombre: dos backups del mismo segundo (p.ej. el de seguridad
    # justo antes de una restauracion) no deben poder pisarse el uno al otro.
    dest_path = _db_backup_dir(instance_id, scope) / f"{scope}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.sql.gz"
    defaults_file = _mysql_defaults_file(driver)
    try:
        try:
            proc = subprocess.Popen(
                ["mysqldump", f"--defaults-extra-file={defaults_file}", "--single-transaction", "--quick", db_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("No se encontro el comando 'mysqldump' en el servidor.") from exc
        with proc:
            with gzip.open(dest_path, "wb") as gz:
                shutil.copyfileobj(proc.stdout, gz)
            stderr = proc.stderr.read()
            if proc.wait() != 0:
                dest_path.unlink(missing_ok=True)
                raise RuntimeError(f"mysqldump fallo ({proc.returncode}): {stderr.decode(errors='replace')[:500]}")
    finally:
        os.unlink(defaults_file)
    return dest_path


def list_instance_database_backups(instance_id: str, scope: str) -> list[dict]:
    backup_dir = _db_backup_dir(instance_id, scope)
    files = [
        {"filename": p.name, "size_bytes": p.stat().st_size, "created_at": int(p.stat().st_mtime)}
        for p in backup_dir.glob("*.sql.gz")
    ]
    files.sort(key=lambda f: f["created_at"], reverse=True)
    return files


def get_instance_database_backup_path(instance_id: str, scope: str, filename: str) -> Path:
    """Ruta ya validada (sin traversal) de un backup existente, para servirlo/descargarlo."""
    return _resolve_backup_file(instance_id, scope, filename)


def delete_instance_database_backup(instance_id: str, scope: str, filename: str) -> None:
    _resolve_backup_file(instance_id, scope, filename).unlink(missing_ok=True)


def purge_instance_database_backups(instance_id: str, scope: str, retention_days: int, max_count: int) -> None:
    """Purga backups por antigüedad y por cantidad. La politica (dias/cantidad) la decide
    quien llama (la configuracion de un plugin); aqui solo se aplica.
    """
    backup_dir = _db_backup_dir(instance_id, scope)
    cutoff = time.time() - retention_days * 86400
    survivors = []
    for path in backup_dir.glob("*.sql.gz"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
        else:
            survivors.append(path)
    survivors.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for path in survivors[max_count:]:
        path.unlink(missing_ok=True)


def restore_instance_database(instance_id: str, scope: str, filename: str) -> None:
    """Restaura sobre la base `scope` un volcado .sql.gz creado por backup_instance_database()
    (busca `filename` bajo app/backups/db/<instancia>/<scope>/).

    Sobreescribe los datos actuales de esa base: quien llame a esto debe haber
    confirmado la accion explicitamente con el usuario, no es reversible desde aqui.
    """
    driver = get_manager().get_driver(instance_id)
    if not driver or not driver.config.enabled:
        raise RuntimeError("Instancia no encontrada o deshabilitada.")
    db_name = _db_name_for_scope(driver, scope)
    if not db_name:
        raise RuntimeError(f"La instancia no tiene configurada la base de datos '{scope}'.")
    source_path = _resolve_backup_file(instance_id, scope, filename)

    defaults_file = _mysql_defaults_file(driver)
    try:
        try:
            proc = subprocess.Popen(
                ["mysql", f"--defaults-extra-file={defaults_file}", db_name],
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("No se encontro el comando 'mysql' en el servidor.") from exc
        with proc:
            with gzip.open(source_path, "rb") as gz:
                shutil.copyfileobj(gz, proc.stdin)
            proc.stdin.close()
            stderr = proc.stderr.read()
            if proc.wait() != 0:
                raise RuntimeError(f"mysql (restore) fallo ({proc.returncode}): {stderr.decode(errors='replace')[:500]}")
    finally:
        os.unlink(defaults_file)


def _core_backups_dir(label: str = "") -> Path:
    """`label` separa los ejecutables de distintos cores/builds (p.ej. dos reinos con
    binarios independientes) en app/backups/core/<label>/; sin label, todo va junto.
    """
    return CORE_BACKUPS_DIR / _SAFE_NAME_RE.sub("_", label) if label else CORE_BACKUPS_DIR


def backup_core_executables(source_bin_dir: Path, label: str = "") -> Path:
    """Copia `source_bin_dir` (los binarios recien compilados, antes de que un nuevo
    `cmake --install` los sobreescriba) a app/backups/core/[<label>/]<timestamp>/bin/.
    """
    if not source_bin_dir.is_dir():
        raise RuntimeError(f"No existe el directorio de binarios: {source_bin_dir}")
    dest = _core_backups_dir(label) / time.strftime("%Y%m%d_%H%M%S")
    shutil.copytree(source_bin_dir, dest / "bin")
    return dest


def list_core_executable_backups(label: str = "") -> list[dict]:
    base = _core_backups_dir(label)
    if not base.is_dir():
        return []
    backups = [{"name": p.name, "created_at": int(p.stat().st_mtime)} for p in base.iterdir() if p.is_dir()]
    backups.sort(key=lambda b: b["created_at"], reverse=True)
    return backups


def purge_core_executable_backups(max_count: int, label: str = "") -> None:
    base = _core_backups_dir(label)
    if not base.is_dir():
        return
    backups = sorted((p for p in base.glob("*") if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[max_count:]:
        shutil.rmtree(old, ignore_errors=True)


def get_current_user_ws(token: str | None, db: Session) -> models.User | None:
    if not token:
        return None
    username = decode_access_token(token)
    if not username:
        return None
    return db.query(models.User).filter(models.User.username == username).first()
