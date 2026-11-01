import json
import os
import subprocess

import psutil
import pytest

from app.emulators import runtime_docker
from app.emulators.runtime import ProcessControlError, RuntimeMarkers
from app.soap.client import SoapError

CONTAINER = "warcrafted-ac-pruebas-1"
STARTED_AT = "2026-10-31T22:24:06.296694548Z"


def _completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


class FakeDocker:
    """Simula la CLI de docker: state de `inspect`, consumo de `stats` y errores globales."""

    def __init__(
        self,
        *,
        running=True,
        pid=None,
        started_at=STARTED_AT,
        cpu="103.10%",
        memory="3.139GiB / 8GiB",
        inspect_error=None,
        info_error=None,
        compose_error=None,
    ):
        self.running = running
        self.pid = pid
        self.started_at = started_at
        self.cpu = cpu
        self.memory = memory
        self.inspect_error = inspect_error
        self.info_error = info_error
        self.compose_error = compose_error
        self.calls: list[list[str]] = []

    def run(self, args, **kwargs):
        self.calls.append(list(args))
        command = args[1]
        if command == "info":
            if self.info_error:
                return _completed(args, 1, "", self.info_error)
            return _completed(args, 0, "29.9.2\n")
        if command == "inspect":
            if self.inspect_error:
                return _completed(args, 1, "", self.inspect_error)
            state = {
                "Running": self.running,
                "Pid": self.pid if self.running else 0,
                "StartedAt": self.started_at,
                "ExitCode": 0 if self.running else 137,
            }
            return _completed(args, 0, json.dumps(state))
        if command == "stats":
            return _completed(args, 0, json.dumps({"CPUPerc": self.cpu, "MemUsage": self.memory}) + "\n")
        if command == "compose":
            if self.compose_error:
                return _completed(args, 1, "", self.compose_error)
            return _completed(args, 0, "ok\n")
        if command == "kill":
            return _completed(args, 0)
        raise AssertionError(f"comando de docker inesperado: {args}")

    def commands(self, name):
        """Llamadas cuyo primer subcomando de docker es `name`."""
        return [call for call in self.calls if len(call) > 1 and call[1] == name]


def make_runtime(tmp_path, ready=False, **kwargs):
    ready_file = tmp_path / "instance.ready"
    stopping_file = tmp_path / "instance.stopping"
    if ready:
        ready_file.touch()
    return runtime_docker.DockerRuntime(
        name="Desarrollo-Pruebas",
        markers=RuntimeMarkers(
            ready_file=ready_file,
            stopping_file=stopping_file,
            is_ready=lambda: ready_file.exists(),
        ),
        **kwargs,
    )


@pytest.fixture
def project_dir(tmp_path):
    (tmp_path / "compose.yaml").write_text(
        "name: warcrafted\nservices:\n  ac-pruebas:\n    image: warcrafted/ac-worldserver:test\n"
    )
    return tmp_path


@pytest.fixture
def fake_docker(monkeypatch):
    docker = FakeDocker(pid=os.getpid())

    def install(**overrides):
        for key, value in overrides.items():
            setattr(docker, key, value)
        return docker

    monkeypatch.setattr(runtime_docker.subprocess, "run", docker.run)
    return install


def test_estado_en_marcha_listo_es_online_con_pid_y_memoria(project_dir, fake_docker):
    fake_docker()
    runtime = make_runtime(
        project_dir, ready=True, service="ac-pruebas", project_dir=str(project_dir), profile="pruebas"
    )

    status = runtime.get_status()

    assert status["state"] == "online"
    assert status["pid"] == os.getpid()
    assert status["cpu_percent"] == pytest.approx(103.1)
    assert status["memory_mb"] == pytest.approx(3.139 * 1024, rel=1e-3)
    assert "error" not in status


def test_estado_en_marcha_sin_log_listo_es_starting(project_dir, fake_docker):
    fake_docker()
    runtime = make_runtime(project_dir, service="ac-pruebas", project_dir=str(project_dir))

    assert runtime.get_status()["state"] == "starting"


def test_estado_parado_es_offline_y_limpia_marcadores(project_dir, fake_docker):
    docker = fake_docker(running=False)
    runtime = make_runtime(project_dir, ready=True, service="ac-pruebas", project_dir=str(project_dir))
    runtime.markers.stopping_file.touch()

    status = runtime.get_status()

    assert status["state"] == "offline"
    assert status["pid"] is None
    assert status["memory_mb"] is None
    assert not runtime.markers.ready_file.exists()
    assert not runtime.markers.stopping_file.exists()
    assert docker.commands("stats") == []


def test_sin_permisos_devuelve_error_legible_sin_excepcion(project_dir, fake_docker):
    denied = "permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock"
    fake_docker(inspect_error=denied, info_error=denied)
    runtime = make_runtime(project_dir, ready=True, service="ac-pruebas", project_dir=str(project_dir))

    status = runtime.get_status()

    assert status["state"] == "offline"
    assert status["pid"] is None
    assert "docker" in status["error"].lower()
    assert "grupo 'docker'" in status["error"]
    # El marcador de listo no se toca: el fallo es de docker, no del reino.
    assert runtime.markers.ready_file.exists()


def test_find_process_devuelve_el_pid_del_contenedor(project_dir, fake_docker):
    fake_docker()
    runtime = make_runtime(project_dir, service="ac-pruebas", project_dir=str(project_dir))

    proc = runtime.find_process()

    assert proc is not None
    assert proc.pid == os.getpid()
    assert isinstance(proc, psutil.Process)


def test_find_process_sin_contenedor_es_none(project_dir, fake_docker):
    fake_docker(running=False)
    runtime = make_runtime(project_dir, service="ac-pruebas", project_dir=str(project_dir))

    assert runtime.find_process() is None


def test_start_lanza_compose_up_con_servicio_y_perfil(project_dir, fake_docker):
    docker = fake_docker(running=True)
    runtime = make_runtime(
        project_dir, service="ac-pruebas", project_dir=str(project_dir), profile="pruebas"
    )

    result = runtime.start()

    up = [call for call in docker.commands("compose") if "up" in call]
    assert len(up) == 1
    assert up[0] == [
        "docker",
        "compose",
        "-f",
        str(project_dir / "compose.yaml"),
        "--profile",
        "pruebas",
        "up",
        "-d",
        "ac-pruebas",
    ]
    assert result == {"success": True, "pid": os.getpid()}


def test_stop_con_soap_ok_no_toca_compose(project_dir, fake_docker):
    docker = fake_docker()
    runtime = make_runtime(project_dir, service="ac-pruebas", project_dir=str(project_dir))
    graceful_calls = []

    result = runtime.stop(graceful_shutdown=lambda: "Shutting down...", on_graceful=lambda: graceful_calls.append(1))

    assert result == {"success": True, "detail": "Shutting down..."}
    assert graceful_calls == [1]
    assert docker.commands("compose") == []


def test_stop_con_soap_fallido_detiene_el_contenedor(project_dir, fake_docker):
    docker = fake_docker()

    def failing_shutdown():
        raise SoapError("connection refused")

    runtime = make_runtime(project_dir, service="ac-pruebas", project_dir=str(project_dir))

    result = runtime.stop(graceful_shutdown=failing_shutdown)

    stop = [call for call in docker.commands("compose") if "stop" in call]
    assert len(stop) == 1
    assert stop[0] == [
        "docker",
        "compose",
        "-f",
        str(project_dir / "compose.yaml"),
        "stop",
        "-t",
        "60",
        "ac-pruebas",
    ]
    assert result["success"] is True
    assert "connection refused" in result["detail"]


def test_stop_sin_soap_usa_compose_stop(project_dir, fake_docker):
    docker = fake_docker()
    runtime = make_runtime(project_dir, service="ac-pruebas", project_dir=str(project_dir))

    result = runtime.stop()

    assert result["success"] is True
    assert [call for call in docker.commands("compose") if "stop" in call]


def test_force_stop_mata_el_contenedor(project_dir, fake_docker):
    docker = fake_docker()
    runtime = make_runtime(project_dir, service="ac-pruebas", project_dir=str(project_dir))

    result = runtime.force_stop()

    assert result["success"] is True
    assert docker.commands("kill") == [["docker", "kill", CONTAINER]]


def test_force_stop_sin_contenedor_no_ejecuta_nada(project_dir, fake_docker):
    docker = fake_docker(running=False)
    runtime = make_runtime(project_dir, service="ac-pruebas", project_dir=str(project_dir))

    result = runtime.force_stop()

    assert result["success"] is False
    assert docker.commands("kill") == []


def test_falta_el_servicio_se_reporta_como_estado_de_error(project_dir, fake_docker):
    docker = fake_docker()
    runtime = make_runtime(project_dir, service="", project_dir=str(project_dir))

    status = runtime.get_status()

    assert status["state"] == "offline"
    assert "DOCKER_SERVICE" in status["error"]
    assert docker.calls == []


def test_start_con_docker_caido_lanza_error_controlado(project_dir, fake_docker):
    denied = "permission denied while trying to connect to the Docker daemon socket"
    fake_docker(info_error=denied, inspect_error=denied)
    runtime = make_runtime(project_dir, service="ac-pruebas", project_dir=str(project_dir))

    with pytest.raises(ProcessControlError):
        runtime.start()


def test_stop_con_docker_caido_lanza_error_controlado(project_dir, fake_docker):
    denied = "permission denied while trying to connect to the Docker daemon socket"
    fake_docker(info_error=denied, inspect_error=denied)
    runtime = make_runtime(project_dir, service="ac-pruebas", project_dir=str(project_dir))

    with pytest.raises(ProcessControlError) as excinfo:
        runtime.stop()

    assert "docker" in str(excinfo.value).lower()


def test_nombre_de_contenedor_sale_del_name_del_compose(tmp_path):
    (tmp_path / "compose.yaml").write_text("name: otro-proyecto\nservices: {}\n")
    runtime = make_runtime(tmp_path, service="ac-auth", project_dir=str(tmp_path))

    assert runtime._container_name() == "otro-proyecto-ac-auth-1"


def test_nombre_de_contenedor_sin_name_usa_la_carpeta(tmp_path):
    (tmp_path / "compose.yaml").write_text("services: {}\n")
    runtime = make_runtime(tmp_path, service="ac-auth", project_dir=str(tmp_path))

    assert runtime._container_name() == f"{tmp_path.name}-ac-auth-1"


def test_parseo_de_memoria_y_cpu():
    assert runtime_docker._parse_memory_mb("512MiB / 1GiB") == 512.0
    assert runtime_docker._parse_memory_mb("1.5GiB / 8GiB") == 1536.0
    assert runtime_docker._parse_memory_mb("") is None
    assert runtime_docker._parse_percent("103.10%") == pytest.approx(103.1)
    assert runtime_docker._parse_percent(None) is None
