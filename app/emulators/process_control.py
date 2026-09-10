from pathlib import Path

import psutil

# Cuanto se parece un proceso al emulador buscado.
MATCH_NONE = 0
MATCH_WRAPPER = 1  # solo lo nombra: tmux, "sh -c ... && ./worldserver", un script de arranque
MATCH_BINARY = 2  # es el propio ejecutable


def match_rank(proc: psutil.Process, process_name: str, workdir: str) -> int:
    """Identifica un proceso por nombre + WORKDIR, no solo por el binario: varias
    instancias pueden compartir el mismo nombre de proceso (p.ej. "worldserver").

    Un envoltorio no vale lo mismo que el emulador: su RAM no es la del servidor, y al
    detener la instancia la senal le llegaria a el, dejando vivo al proceso de verdad.
    """
    target = process_name.lower()
    try:
        if proc.status() == psutil.STATUS_ZOMBIE:
            return MATCH_NONE
        name = (proc.name() or "").lower()
        # El "comm" del proceso puede truncarse o ser el del interprete
        # (p.ej. wrappers/scripts); si no coincide, se prueba con cmdline.
        if target in name:
            rank = MATCH_BINARY
        elif target in " ".join(proc.cmdline()).lower():
            rank = MATCH_WRAPPER
        else:
            return MATCH_NONE
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return MATCH_NONE

    if workdir:
        try:
            proc_cwd = Path(proc.cwd()).resolve()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return MATCH_NONE
        if proc_cwd != Path(workdir).resolve():
            return MATCH_NONE

    return rank


def read_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def write_pid(pid_file: Path, pid: int) -> None:
    pid_file.write_text(str(pid))


def clear_pid(pid_file: Path) -> None:
    pid_file.unlink(missing_ok=True)


def find_process(pid_file: Path, process_name: str, workdir: str) -> psutil.Process | None:
    """El proceso de la instancia, por el PID guardado o escaneando si no cuadra.

    Un envoltorio solo se da por bueno si no aparece el binario: arrancando desde tmux
    (`sh -c cd bin && ./worldserver`) la `sh` tiene el PID mas bajo y gana el escaneo.
    """
    best = None
    best_rank = MATCH_NONE

    pid = read_pid(pid_file)
    if pid is not None and psutil.pid_exists(pid):
        try:
            proc = psutil.Process(pid)
            rank = match_rank(proc, process_name, workdir)
            if rank == MATCH_BINARY:
                return proc
            if rank == MATCH_WRAPPER:
                best, best_rank = proc, rank
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    for proc in psutil.process_iter():
        rank = match_rank(proc, process_name, workdir)
        if rank > best_rank:
            best, best_rank = proc, rank
            if rank == MATCH_BINARY:
                break

    if best is None:
        clear_pid(pid_file)
        return None
    write_pid(pid_file, best.pid)
    return best
