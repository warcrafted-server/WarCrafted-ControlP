import re
import shutil
import time
from pathlib import Path

CONSOLE_CATEGORY = "worldserver"

# Vista previa acotada: leer solo el final del archivo evita cargar logs de
# varios MB/GB enteros en memoria y congelar el navegador al renderizarlos.
PREVIEW_MAX_BYTES = 512_000

# Prefijo que marca un "filename" como archivo nativo de AzerothCore (vive en
# ACORE_LOGS_DIR, no en la carpeta de historico de esta instancia).
NATIVE_PREFIX = "native:"

NATIVE_CATEGORIES: dict[str, str] = {
    "server": "Server.log",
    "errors": "Errors.log",
    "playerbots": "Playerbots.log",
    "gm": "GM.log",
    "chat": "chat.log",
}

_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})_([a-z0-9]+)\.log$")

# Secuencias de escape ANSI/VT100 (colores, "AC> " redibujandose con codigos
# como "\x1b[?2004l" cuando el proceso no tiene una terminal real detras).
_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text)


def timestamp_now() -> str:
    return time.strftime("%Y-%m-%d_%H-%M-%S")


def _timestamp_from_mtime(path: Path) -> str:
    return time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(path.stat().st_mtime))


def run_log_filename(category: str, timestamp: str) -> str:
    return f"{timestamp}_{category}.log"


def _parse_run_log_filename(filename: str) -> tuple[str, str] | None:
    match = _FILENAME_RE.match(filename)
    if not match:
        return None
    timestamp, category = match.groups()
    return timestamp, category


def resolve_safe(instance_dir: Path, filename: str) -> Path | None:
    """Resuelve `filename` dentro de `instance_dir`; None si el nombre intenta escapar de ella."""
    base = instance_dir.resolve()
    candidate = (instance_dir / filename).resolve()
    if candidate != base and base not in candidate.parents:
        return None
    return candidate


def archive_native_logs(instance_dir: Path, acore_logs_dir: Path, categories: list[str]) -> None:
    """Copia al historico los ficheros nativos de AzerothCore del run que acaba de terminar.

    AzerothCore sobreescribe estos ficheros (Mode=w) al arrancar, asi que este es el
    unico momento seguro para archivarlos: justo antes de lanzar el proceso nuevo.
    """
    for category in categories:
        native_name = NATIVE_CATEGORIES.get(category)
        if not native_name:
            continue
        native_path = acore_logs_dir / native_name
        if not native_path.is_file():
            continue
        dest = instance_dir / run_log_filename(category, _timestamp_from_mtime(native_path))
        if dest.exists():
            continue
        try:
            shutil.copy2(native_path, dest)
        except OSError:
            continue


def purge_old_logs(instance_dir: Path, retention_days: int, max_runs: int, max_total_mb: int = 0) -> None:
    if not instance_dir.is_dir():
        return
    by_category: dict[str, list[Path]] = {}
    for path in instance_dir.glob("*.log"):
        parsed = _parse_run_log_filename(path.name)
        if not parsed:
            continue
        by_category.setdefault(parsed[1], []).append(path)

    cutoff = time.time() - retention_days * 86400
    max_total_bytes = max_total_mb * 1_000_000
    for files in by_category.values():
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        survivors = []
        for path in files:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
            else:
                survivors.append(path)
        for path in survivors[max_runs:]:
            path.unlink(missing_ok=True)
        survivors = survivors[:max_runs]

        # Ademas de dias y numero de runs, se acota el peso total por categoria:
        # un unico run puede pesar cientos de MB y saltarse ambos limites.
        if max_total_bytes > 0:
            total = 0
            for path in survivors:
                total += path.stat().st_size
                if total > max_total_bytes:
                    path.unlink(missing_ok=True)


def list_runs(instance_dir: Path) -> list[dict]:
    if not instance_dir.is_dir():
        return []
    runs = []
    for path in instance_dir.glob("*.log"):
        parsed = _parse_run_log_filename(path.name)
        if not parsed:
            continue
        timestamp, category = parsed
        try:
            size_bytes = path.stat().st_size
        except OSError:
            continue
        runs.append(
            {
                "filename": path.name,
                "category": category,
                "started_at": timestamp,
                "size_bytes": size_bytes,
                "source": "historico",
            }
        )
    runs.sort(key=lambda r: r["started_at"], reverse=True)
    return runs


def scan_native_logs(native_dir: Path) -> list[dict]:
    """Escanea en vivo el LogsDir real de AzerothCore (Server.log, Char.log,
    DBErrors.log...): a diferencia de `list_runs`, no depende de que la
    categoria este pre-configurada en `LOG_CATEGORIES` ni de haberla archivado
    antes; refleja el contenido actual, tal cual lo tiene AzerothCore ahora.
    """
    if not native_dir.is_dir():
        return []
    runs = []
    for path in native_dir.glob("*.log"):
        try:
            stat = path.stat()
        except OSError:
            continue
        runs.append(
            {
                "filename": f"{NATIVE_PREFIX}{path.name}",
                "category": path.stem,
                "started_at": _timestamp_from_mtime(path),
                "size_bytes": stat.st_size,
                "source": "nativo",
            }
        )
    runs.sort(key=lambda r: r["started_at"], reverse=True)
    return runs


def read_preview(path: Path, max_bytes: int = PREVIEW_MAX_BYTES) -> tuple[str, bool, int]:
    """Lee como mucho los ultimos `max_bytes` de `path` sin cargar el archivo entero.

    Devuelve (contenido, truncado, tamano_total_en_bytes). El seek desde el
    final hace que el coste de lectura no dependa del tamano del archivo.
    """
    size = path.stat().st_size
    truncated = size > max_bytes
    with path.open("rb") as fh:
        if truncated:
            fh.seek(size - max_bytes)
        raw = fh.read()
    if truncated:
        # la primera linea puede estar cortada a mitad; se descarta
        newline = raw.find(b"\n")
        if newline != -1:
            raw = raw[newline + 1 :]
    content = strip_ansi(raw.decode("utf-8", errors="replace"))
    return content, truncated, size


# AzerothCore imprime esta linea (Main.cpp) solo cuando ya cargo mundo,
# mapas, red y SOAP, y el realm queda unido en la DB (REALM_FLAG_VERSION_MISMATCH
# se limpia justo antes) — es la senal fiable de "ya se puede entrar al reino".
READY_MARKER = "(worldserver-daemon) ready"


def contains_ready_marker(path: Path) -> bool:
    try:
        with path.open("r", errors="replace") as fh:
            for line in fh:
                if READY_MARKER in line:
                    return True
    except OSError:
        return False
    return False


# Primera linea del cierre en AzerothCore (Main.cpp): a partir de aqui el proceso
# ya no atiende a nadie, solo le queda cerrar los pools de base de datos y salir.
HALT_MARKER = "Halting process..."

# Solo cuenta si el marcador esta al final: mas atras significa que ese apagado ya
# termino y lo que se ve despues es el arranque siguiente.
HALT_TAIL_BYTES = 32_768

# Cada pool cierra en dos lineas: "Closing down DatabasePool 'X'. Waiting for N
# queries to finish..." y esta al acabar.
_DB_CLOSED_RE = re.compile(r"All connections on DatabasePool '.*' closed\.")


def read_shutdown_state(path: Path, tail_bytes: int = HALT_TAIL_BYTES) -> tuple[bool, bool]:
    """Del final del log: (apagado en curso, bases de datos ya cerradas).

    Lo segundo dice si se puede matar el proceso sin perder nada: con los pools
    cerrados no queda ninguna partida por guardar. Se mira la ultima linea porque
    entre pool y pool no hay pausa; si la ultima es esa, ninguno esta a medias.
    """
    try:
        content, _, _ = read_preview(path, max_bytes=tail_bytes)
    except OSError:
        return False, False
    if HALT_MARKER not in content:
        return False, False
    lines = [line for line in content.splitlines() if line.strip()]
    return True, bool(lines) and _DB_CLOSED_RE.search(lines[-1]) is not None


def tail_file(path: Path, lines: int = 20) -> str:
    if not path.exists():
        return ""
    try:
        content = path.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])


def pump_console_output(stream, log_fh, max_repeat: int = 20) -> None:
    """Lee `stream` (stdout del proceso) linea a linea, limpia codigos ANSI y
    corta una linea que se repite sin fin.

    Sin esto, un proceso sin terminal real detras (p.ej. el hilo de consola
    de AzerothCore redibujando su prompt "AC>" contra un stdin ya cerrado)
    puede llenar el disco en minutos. Corre en un hilo mientras el proceso
    vive; termina solo cuando el proceso cierra su salida estandar.
    """
    last_line = None
    repeat_count = 0
    try:
        for raw_line in stream:
            line = strip_ansi(raw_line).rstrip("\r\n")
            if line == last_line:
                repeat_count += 1
                if repeat_count == max_repeat:
                    log_fh.write("[... linea repetida, se omiten mas repeticiones ...]\n")
                    log_fh.flush()
                if repeat_count >= max_repeat:
                    # Da tiempo a que el pipe se llene y frene al proceso que repite sin fin.
                    time.sleep(0.05)
                    continue
            else:
                last_line = line
                repeat_count = 0
            log_fh.write(line + "\n")
            log_fh.flush()
    except (OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass
        try:
            log_fh.close()
        except OSError:
            pass
