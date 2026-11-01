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

## Rutas del host (hallazgo, obligatorio)

`app/deps.py` (líneas ~131, 144, 738) y los plugins derivan `etc/`, `etc/modules/`, `lua_scripts/` y la copia de `bin/` como `Path(WORKDIR).parent / ...`. En Docker `WORKDIR` es `/azerothcore` (ruta del contenedor, inexistente en el host) y eso rompería editor de `.conf`, módulos, Lua y copias de seguridad. Solución: `InstanceConfig` gana `host_root` (`INSTANCE_<N>_HOST_ROOT`, p. ej. `/opt/vps-apps/azerothcore/pruebas`, con `bin/`, `etc/`, `logs/`) y propiedades `bin_dir`, `etc_dir`, `logs_dir`, `lua_dir` que usan `host_root` si existe y `workdir.parent` si no. Todo el código y los plugins deben usar esas propiedades, nunca `workdir.parent`.

## Matriz plugin → qué necesita en modo Docker

| Plugin | Depende de | Acción |
|---|---|---|
| Panel (iniciar/parar/estado) | proceso por nombre+WORKDIR | `DockerRuntime` |
| `modules_manager` (editar .conf) | `etc_dir`, SOAP reload | usar `etc_dir` (host_root) |
| `db_manager` (backups) | MySQL del host | sin cambio; comprobar `mysqldump` |
| `character_forge`, `gm_commander`, `migration` | SOAP y BD | sin cambio; verificar con SOAP real |
| `metrics_history`, `web-notifications` | estado de instancia | sin cambio si el runtime da CPU/RAM |
| `core_updater` | repos git + cmake en `repos.json`/perfiles | perfil con `build_backend=docker`: `BUILD_CMD` (construir.sh + compose up) y repos de `~/Repos` |
| `fork_watch` | git remoto | sin cambio |

Los dos reinos (pruebas y producción) deben quedar operativos en ambos modos; producción se compila con su `.lock`, pruebas primero.

## Pasos

1. **Interfaz de runtime y `host_root`, sin cambio de comportamiento por defecto** — `app/emulators/runtime.py` (nuevo), `app/deps.py` (usar `etc_dir`/`lua_dir`/`bin_dir`), `base.py`, `process_control.py`, `auth_service.py`, `manager.py`, `config.py`. Terminado: con `APP_RUNTIME` ausente todo funciona exactamente igual; probar arranque y tarjetas. Ejecutor: AgentRelay, Sonnet, esfuerzo medio. Versión 0.23.0 (menor: refactor + preparación); CHANGELOG «Cambiado».
2. **`DockerRuntime`** — `app/emulators/runtime_docker.py`, parseo de `.env` nuevo en `manager.py`, `.env.example`. Terminado: contra los contenedores reales de este VPS (`ac-pruebas`, `ac-auth`; ver `~/Repos/WarCrafted-Deploy/compose.yaml`) se ven estado, CPU/RAM, iniciar y detener. Pruebas unitarias con `docker` simulado. Ejecutor: AgentRelay, Sonnet, esfuerzo medio. Versión 0.24.0 (menor); CHANGELOG «Añadido».
3. **Instaladores** — `install.sh`, `install.bat`: preguntar modo (nativo/docker); en docker comprobar `docker` + `docker compose` + permisos y pedir proyecto compose y servicios, sin instalar paquetes. Terminado: ambas rutas dejan un `.env` válido. Ejecutor: AgentRelay, Sonnet, bajo. Versión 0.25.0 (menor).
4. **Compilar/actualizar en modo docker** — repo `WarCraftedCP-plugins`, `core_updater` (y lo que toque `modules_manager`). **Cruza de repo: exige permiso explícito del usuario antes de empezar.** Leer primero ambos `CLAUDE.md`/`AGENTS.md`. Terminado: botón de compilar lanza `BUILD_CMD` con salida en vivo y recrea el servicio; en nativo, sin cambios. Subir versión del plugin y su CHANGELOG. Ejecutor: Opus o Sonnet alto (diseño sobre código ajeno).
5. **Documentación** — `README.md`, `INSTALL.md` (sección «Elegir runtime», variables nuevas, requisitos Docker, ejemplo con dos reinos y authserver compartido), `USER_GUIDE.md`, `docs/` si INSTALL pasa de una pantalla por variantes, y `TODO.md` (crearlo: no existe). Ejecutor: AgentRelay, Haiku/Sonnet bajo. Versión 0.25.1 (parche, solo docs) si no se agrupa con el 3.
6. **Despliegue en este VPS** — `.env` con las dos instancias en modo docker (SOAP y BD leídos de los `.conf`, sin mostrar secretos), servicio systemd (necesita `sudo` del usuario), proxy HTTPS y token de GitHub. Lo hace la sesión principal con el usuario.

## Fuera de alcance
Otros runtimes (Podman, systemd units, Kubernetes) y mover los reinos entre modos. Push, tags y licencia: solo con aprobación del usuario.
