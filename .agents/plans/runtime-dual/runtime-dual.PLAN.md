# Runtime dual: nativo o Docker (`runtime-dual`)

Objetivo: que el panel gestione cada instancia con **procesos nativos** o con **contenedores Docker**, a elegir al instalar (y por instancia en `.env`). Hoy solo soporta nativo (`psutil` + `WORKDIR`, `app/emulators/process_control.py`).
Versión de partida 0.22.0 (`VERSION`). Cada paso se commitea por separado; sin push sin aprobación. Marca cada paso hecho aquí; ante un imprevisto de diseño, para y anótalo.

## Diseño (decidido)

- `.env` global `APP_RUNTIME=native|docker` (por defecto `native`, compatible hacia atrás) y override por instancia/auth-service con `INSTANCE_<N>_RUNTIME` / `AUTH_SERVICE_<M>_RUNTIME`.
- Instancia `docker` añade: `INSTANCE_<N>_DOCKER_SERVICE` (servicio compose, p. ej. `ac-pruebas`), `INSTANCE_<N>_DOCKER_PROJECT_DIR` (carpeta con el `compose.yaml`) y opcional `INSTANCE_<N>_DOCKER_PROFILE`. `START_CMD`/`WORKDIR`/`*_PROCESS` pasan a ser opcionales en este modo.
- Se separa una interfaz `RuntimeBackend` (estado/CPU/RAM, start, stop, force-stop, existe) con dos implementaciones: `NativeRuntime` (el código actual de `process_control` + `start/_force_stop` de `base.py`) y `DockerRuntime` (CLI `docker`, sin dependencias nuevas: `docker compose up -d <svc>`, `docker compose stop -t N <svc>`, `docker kill`, `docker inspect` para estado y PID, `docker stats --no-stream --format json` para CPU/RAM).
- Todo lo demás (SOAP, BD, logs nativos, marcadores `.ready`/`.stopping`, apagado programado, watchdog) se comparte: en Docker los logs y los `.conf` ya viven en carpetas montadas del host, así que `ACORE_LOGS_DIR` sirve igual.
- Requisito en modo docker: el usuario del panel está en el grupo `docker`. Si no se puede ejecutar `docker info`, la tarjeta muestra el error, no falla el panel.
- Compilar/actualizar (`app/plugins/core_updater`, repo de plugins): backend `native` (cmake, actual) o `docker` (`BUILD_CMD` configurable por instancia, p. ej. `scripts/construir.sh <reino>` seguido de `docker compose up -d <svc>`), con salida en vivo igual que ahora.

## Pasos

1. **Interfaz y refactor sin cambio de comportamiento** — `app/emulators/runtime.py` (nuevo), `base.py`, `process_control.py`, `auth_service.py`, `manager.py`, `config.py`. Terminado: con `APP_RUNTIME` ausente todo funciona exactamente igual; probar arranque y tarjetas. Ejecutor: AgentRelay, Sonnet, esfuerzo medio. Versión 0.23.0 (menor: refactor + preparación); CHANGELOG «Cambiado».
2. **`DockerRuntime`** — `app/emulators/runtime_docker.py`, parseo de `.env` nuevo en `manager.py`, `.env.example`. Terminado: contra los contenedores reales de este VPS (`ac-pruebas`, `ac-auth`; ver `~/Repos/WarCrafted-Deploy/compose.yaml`) se ven estado, CPU/RAM, iniciar y detener. Pruebas unitarias con `docker` simulado. Ejecutor: AgentRelay, Sonnet, esfuerzo medio. Versión 0.24.0 (menor); CHANGELOG «Añadido».
3. **Instaladores** — `install.sh`, `install.bat`: preguntar modo (nativo/docker); en docker comprobar `docker` + `docker compose` + permisos y pedir proyecto compose y servicios, sin instalar paquetes. Terminado: ambas rutas dejan un `.env` válido. Ejecutor: AgentRelay, Sonnet, bajo. Versión 0.25.0 (menor).
4. **Compilar/actualizar en modo docker** — repo `WarCraftedCP-plugins`, `core_updater` (y lo que toque `modules_manager`). **Cruza de repo: exige permiso explícito del usuario antes de empezar.** Leer primero ambos `CLAUDE.md`/`AGENTS.md`. Terminado: botón de compilar lanza `BUILD_CMD` con salida en vivo y recrea el servicio; en nativo, sin cambios. Subir versión del plugin y su CHANGELOG. Ejecutor: Opus o Sonnet alto (diseño sobre código ajeno).
5. **Documentación** — `README.md`, `INSTALL.md` (sección «Elegir runtime», variables nuevas, requisitos Docker, ejemplo con dos reinos y authserver compartido), `USER_GUIDE.md`, `docs/` si INSTALL pasa de una pantalla por variantes, y `TODO.md` (crearlo: no existe). Ejecutor: AgentRelay, Haiku/Sonnet bajo. Versión 0.25.1 (parche, solo docs) si no se agrupa con el 3.
6. **Despliegue en este VPS** — `.env` con las dos instancias en modo docker (SOAP y BD leídos de los `.conf`, sin mostrar secretos), servicio systemd (necesita `sudo` del usuario), proxy HTTPS y token de GitHub. Lo hace la sesión principal con el usuario.

## Fuera de alcance
Otros runtimes (Podman, systemd units, Kubernetes) y mover los reinos entre modos. Push, tags y licencia: solo con aprobación del usuario.
