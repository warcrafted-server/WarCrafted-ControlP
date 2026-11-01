# Manual de instalacion

## Requisitos previos

- **Python 3.11 o superior** (recomendado; funciona desde 3.10).
- Acceso de red a los puertos SOAP (por defecto `7878`) y a la base de datos MySQL/MariaDB de cada emulador que quieras monitorizar.
- En Linux: `python3-venv` y `python3-pip` (el instalador los requiere; instalalos con `sudo apt install python3-venv python3-pip` si faltan).
- En Windows: Python instalado desde [python.org](https://www.python.org/downloads/) con la opcion "Add python.exe to PATH" activada.

## Instalacion automatica

### Linux (Debian/Ubuntu)

```bash
git clone <url-del-repositorio>
cd WarCrafted-ControlP
./install.sh
```

El script:
1. Verifica que Python 3 este disponible.
2. Crea un entorno virtual en `.venv`.
3. Instala las dependencias de `requirements.txt`.
4. Crea `.env` a partir de `.env.example` (si no existe) y genera una `SECRET_KEY` aleatoria.
5. Crea la carpeta `data/` para la base de datos interna del panel.
6. Pide un usuario y contrasena para crear el administrador del panel.

### Windows

```bat
git clone <url-del-repositorio>
cd WarCrafted-ControlP
install.bat
```

El script realiza los mismos pasos que en Linux, adaptados a `cmd.exe`.

> En Windows, `set /p` no oculta la contrasena mientras se escribe. Si necesitas ocultarla, crea el usuario administrador manualmente despues con `python -m app.cli create-admin` desde una consola con el entorno virtual activado.

## Instalacion manual (paso a paso)

Si prefieres no usar los scripts, o necesitas mas control sobre el proceso:

```bash
# 1. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate        # En Windows: .venv\Scripts\activate.bat

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Edita .env y define SECRET_KEY, las instancias de emulador, etc.

# 4. Crear el usuario administrador
python -m app.cli create-admin

# 5. Arrancar el panel
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Configuracion de `.env`

### Variables de aplicacion

| Variable | Descripcion | Valor por defecto |
|---|---|---|
| `APP_NAME` | Nombre mostrado en la interfaz | `WarCrafted-ControlP` |
| `APP_HOST` / `APP_PORT` | Host y puerto donde escucha el panel | `0.0.0.0` / `8000` |
| `SECRET_KEY` | Clave usada para firmar los tokens JWT | *(generada por el instalador)* |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Duracion de la sesion | `120` |
| `COOKIE_SECURE` | Marca la cookie de sesion como `Secure` (requiere HTTPS) | `false` |
| `APP_DB_URL` | Cadena de conexion de la base de datos interna del panel | `sqlite:///./data/app.db` |
| `SHUTDOWN_STUCK_TIMEOUT` | Segundos que un apagado en curso puede pasar sin escribir nada en el log antes de que el panel remate el proceso. Con las bases de datos ya cerradas el margen baja a 30 segundos fijos (`0` desactiva la vigilancia) | `180` |

### Instancias de emulador

Cada instancia se define con variables numeradas usando el prefijo `INSTANCE_<N>_`, donde `<N>` es un numero entero (1, 2, 3...). Puedes definir tantas como necesites.

| Variable | Descripcion |
|---|---|
| `INSTANCE_<N>_ENABLED` | `true`/`false`, activa o desactiva la instancia sin borrarla |
| `INSTANCE_<N>_NAME` | Nombre mostrado en el panel |
| `INSTANCE_<N>_TYPE` | `azerothcore` o `playerbots` (tambien se aceptan variantes que contengan esas palabras, p. ej. `playerbots-acore`) |
| `INSTANCE_<N>_WORLD_PROCESS` | Nombre del proceso del worldserver a monitorizar |
| `INSTANCE_<N>_AUTH_PROCESS` | Nombre del proceso del authserver |
| `INSTANCE_<N>_START_CMD` | Ruta al ejecutable usado para iniciar el worldserver |
| `INSTANCE_<N>_AUTH_START_CMD` | Ruta al ejecutable del authserver propio de esta instancia (opcional; se ignora si usas `AUTH_SERVICE_ID`, ver mas abajo) |
| `INSTANCE_<N>_AUTH_SERVICE_ID` | Opcional: id de un `AUTH_SERVICE_<M>_*` para que esta instancia comparta authserver con otras, en vez de tener el suyo propio |
| `INSTANCE_<N>_WORKDIR` | Directorio de trabajo al ejecutar `START_CMD`/`AUTH_START_CMD` |
| `INSTANCE_<N>_SOAP_HOST` / `SOAP_PORT` | Host y puerto del servicio SOAP |
| `INSTANCE_<N>_SOAP_USER` / `SOAP_PASS` | Credenciales de la cuenta GM habilitada para SOAP |
| `INSTANCE_<N>_DB_HOST` / `DB_PORT` | Host y puerto de la base de datos MySQL/MariaDB |
| `INSTANCE_<N>_DB_USER` / `DB_PASS` | Credenciales de solo lectura para la base de datos |
| `INSTANCE_<N>_DB_CHARACTERS` | Nombre de la base de datos `characters` del emulador |
| `INSTANCE_<N>_DB_AUTH` | Nombre de la base de datos de cuentas (por defecto `acore_auth`), para las cifras de la tarjeta del authserver |
| `INSTANCE_<N>_RUNTIME` | `native` o `docker`; si falta, hereda `APP_RUNTIME` (por defecto `native`) |
| `INSTANCE_<N>_DOCKER_SERVICE` | Modo Docker: servicio de docker compose (p. ej. `ac-pruebas`) |
| `INSTANCE_<N>_DOCKER_PROJECT_DIR` | Modo Docker: carpeta con el `compose.yaml` (p. ej. el repo WarCrafted-Deploy) |
| `INSTANCE_<N>_DOCKER_PROFILE` | Modo Docker: perfil de compose del servicio, si lo tiene (opcional) |
| `INSTANCE_<N>_HOST_ROOT` | Raiz del arbol del servidor en el host (con `bin/`, `etc/`, `logs/`, `lua_scripts/`). Obligatoria en modo Docker, donde `WORKDIR` es una ruta del contenedor; en nativo se deduce de `WORKDIR` |
| `INSTANCE_<N>_DB_WORLD` | Nombre de la base de datos de mundo (por defecto `acore_world`); solo la usan plugins de autocompletado (objetos, hechizos, ubicaciones) |

Consulta `.env.example` para ver un ejemplo completo con dos instancias (una AzerothCore y una Playerbots).

**Authserver compartido:** si dos o mas reinos usan el mismo proceso authserver, en vez de definirlo por instancia declaralo una vez con `AUTH_SERVICE_<M>_NAME`/`ENABLED`/`PROCESS`/`START_CMD`/`WORKDIR`/`DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASS`/`DB_NAME`, y pon `INSTANCE_<N>_AUTH_SERVICE_ID=auth-service-<M>` en cada instancia que lo use. El dashboard muestra entonces una unica tarjeta de authserver con los reinos vinculados, en vez de una por reino. Ver ejemplo en `.env.example`.

> **Importante:** si dos instancias comparten el mismo `WORLD_PROCESS` (p.ej. ambas usan el binario `worldserver`), el panel las distingue por su `WORKDIR`. Define siempre `INSTANCE_<N>_WORKDIR` con la ruta absoluta y distinta de cada instalacion; si se omite, el panel no puede garantizar que "Iniciar"/"Detener" actuen solo sobre esa instancia.

### Habilitar el servicio SOAP en AzerothCore

En `worldserver.conf`, asegurate de tener:

```
SOAP.Enabled = 1
SOAP.IP = 127.0.0.1
SOAP.Port = 7878
```

La cuenta usada en `SOAP_USER`/`SOAP_PASS` debe tener nivel de GM suficiente (`GMLEVEL`) en la base de datos `auth`.

## Arranque

```bash
./run.sh          # Linux
run.bat           # Windows
```

Ambos scripts activan el entorno virtual, cargan `.env` y arrancan Uvicorn en el host/puerto configurados.

## Elegir como se ejecutan los emuladores: nativo o Docker

El panel controla cada instancia de una de dos maneras, que se elige al instalar (`install.sh` / `install.bat` lo preguntan y escriben `APP_RUNTIME`) y se puede cambiar por instancia con `INSTANCE_<N>_RUNTIME`:

- **Nativo** (por defecto): `worldserver`/`authserver` son procesos del propio equipo, localizados por nombre y `WORKDIR`. Iniciar, detener y compilar (cmake) actuan sobre ellos.
- **Docker**: cada reino es un servicio de docker compose (se espera el despliegue de [WarCrafted-Deploy](https://github.com/warcrafted-server)). Estado, CPU/RAM, iniciar (`docker compose up -d`), detener (SOAP y, si falla, `docker compose stop`) y forzar (`docker kill`) usan solo la CLI de `docker`. Requisitos: `docker` y `docker compose` instalados y el usuario del panel en el grupo `docker`; el panel no instala nada.

Ejemplo de dos reinos con un authserver compartido, en Docker (los contenedores usan `network_mode: host`, asi que SOAP y MySQL se ven en `127.0.0.1`):

```
APP_RUNTIME=docker

AUTH_SERVICE_1_NAME=Authserver
AUTH_SERVICE_1_ENABLED=true
AUTH_SERVICE_1_RUNTIME=docker
AUTH_SERVICE_1_DOCKER_SERVICE=ac-auth
AUTH_SERVICE_1_DOCKER_PROJECT_DIR=/ruta/a/WarCrafted-Deploy
# ... AUTH_SERVICE_1_DB_* como en .env.example

INSTANCE_1_ENABLED=true
INSTANCE_1_NAME=Produccion
INSTANCE_1_TYPE=playerbots
INSTANCE_1_AUTH_SERVICE_ID=auth-service-1
INSTANCE_1_RUNTIME=docker
INSTANCE_1_DOCKER_SERVICE=ac-produccion
INSTANCE_1_DOCKER_PROJECT_DIR=/ruta/a/WarCrafted-Deploy
INSTANCE_1_HOST_ROOT=/opt/vps-apps/azerothcore/produccion
INSTANCE_1_SOAP_HOST=127.0.0.1
INSTANCE_1_SOAP_PORT=7878
# ... SOAP_USER/PASS, DB_*, ACORE_LOGS_DIR como en .env.example
```

> El `.env` lo carga `run.sh` con bash: los valores no pueden llevar parentesis ni espacios sin comillas (p. ej. `INSTANCE_1_NAME=Produccion`, no `Produccion (main)`).

**Compilar y actualizar en Docker:** en el plugin *Actualizacion del Core* cada configuracion de build elige su backend. Con *Docker* se indican la carpeta de WarCrafted-Deploy, la de los clones (`~/Repos`) y el reino; *Compilar* ejecuta `scripts/construir.sh` (no toca el reino en marcha), *Fijar commits* escribe en `builds/<reino>.lock` el commit de cada clon (en produccion copia los de pruebas) y *Desplegar* recrea el reino (en produccion con `promocionar.sh`: volcado de bases, aviso por SOAP y vuelta atras a `:prod-anterior`). Ver `USER_GUIDE.md`.

## Instalacion de plugins

Los modulos (plugins) se desarrollan en el repositorio independiente `WarCraftedCP-plugins`. El panel los descubre automaticamente si sus carpetas quedan como hijas directas de `app/plugins/`.

### Opcion A: desde la Tienda de Plugins (recomendado)

Con el panel en marcha, entra como administrador y abre **Tienda** en la barra superior:

1. La primera vez, pulsa **Token de GitHub** y sigue las instrucciones para generar un *Personal Access Token* (fine-grained) con permiso **Contents: Read-only** sobre `WarCraftedCP-plugins`. Se valida y se guarda en `.env` (`GITHUB_PLUGIN_TOKEN`) automaticamente.
2. La tienda lista los modulos del repositorio; pulsa **Instalar** en el que quieras. Se descarga, se extrae en `app/plugins/<nombre>/` y se monta en caliente, sin reiniciar el panel.

### Opcion B: manual

```bash
# Desde la raiz de WarCrafted-ControlP
rm -rf app/plugins/migration app/plugins/<otro-modulo>   # si ya existian versiones previas
git clone <url-de-WarCraftedCP-plugins> /tmp/warcraftedcp-plugins
cp -r /tmp/warcraftedcp-plugins/<nombre-modulo> app/plugins/
```

O bien, para tener el monorepo entero sincronizado por git dentro de `app/plugins/`:

```bash
git clone <url-de-WarCraftedCP-plugins> app/plugins
```

Los modulos no traen `requirements.txt` propio: sus dependencias de terceros ya estan incluidas en el `requirements.txt` del panel (comparten el mismo venv). Si un modulo nuevo requiere una libreria que aun no esta instalada, anadela ahi.

Reinicia el panel (`./run.sh` / `run.bat`, o `systemctl restart warcrafted-controlp` si corre como servicio) para que `app/plugins/loader.py` los detecte; la carga manual solo ocurre al arrancar (la Tienda, en cambio, monta el modulo sin reiniciar). Cada modulo queda montado en `/api/v1/plugins/<nombre-de-carpeta>`. Revisa el log de arranque para confirmar `Plugin '<nombre>' vX.X.X cargado desde <carpeta>`; si un modulo no aparece, falta `router.py` (o no exporta un `APIRouter` valido).

## Ejecucion como servicio (opcional, Linux con systemd)

Crea `/etc/systemd/system/warcrafted-controlp.service`:

```ini
[Unit]
Description=WarCrafted-ControlP
After=network.target

[Service]
Type=simple
WorkingDirectory=/ruta/a/WarCrafted-ControlP
ExecStart=/ruta/a/WarCrafted-ControlP/run.sh
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now warcrafted-controlp
```

`Restart=always` (no `on-failure`) es importante: la autoactualizacion del panel (ver mas abajo) reinicia el proceso a proposito para aplicar cambios, y necesita que systemd lo vuelva a levantar siempre, no solo cuando detecta un fallo.

## HTTPS (recomendado)

Sirve el panel detras de un proxy inverso con TLS en vez de exponer uvicorn directamente. Sin HTTPS (o sin acceder como `localhost`), los navegadores consideran la pagina un "contexto inseguro" y bloquean funciones como las notificaciones de escritorio (ver plugin `web-notifications`) sin llegar a preguntar.

- **Sin proxy inverso todavia:** [Caddy](https://caddyfile.dev/) gestiona el certificado (Let's Encrypt) solo, con un `Caddyfile` de 3 lineas:
  ```
  panel.tudominio.com {
    reverse_proxy 127.0.0.1:8000
  }
  ```
- **Ya tienes Apache o nginx con certbot para otros sitios:** anade un vhost mas con el mismo patron que ya uses (reverse proxy a `127.0.0.1:8000`, incluyendo `/ws/` para los WebSockets de consola y logs en vivo) y pide el certificado con `certbot --apache -d panel.tudominio.com` (o `--nginx`).

Cuando el panel ya responda por HTTPS, pon `COOKIE_SECURE=true` en `.env` y reinicia — antes de eso rompe el login, porque el navegador no envia una cookie `Secure` por HTTP.

## Autoactualizacion del panel

Con el token de GitHub configurado (ver "Instalacion de plugins" arriba; el mismo token sirve para ambos repos si le das acceso a los dos), entra en **Tienda** como administrador. Arriba del catalogo aparece la tarjeta **Panel principal** con la version instalada y, si hay una distinta en `WarCrafted-ControlP`, un boton **Actualizar**:

1. Descarga el repo, fusiona los archivos sobre la instalacion activa (nunca toca `.env`, `data/` ni los plugins ya instalados, porque no forman parte de ese repo) y, si `requirements.txt` cambio, reinstala dependencias en el mismo venv automaticamente.
2. Si la instalacion de dependencias falla, la actualizacion se detiene ahi y el aviso lo dice explicitamente: no reinicies hasta arreglarlo a mano (`pip install -r requirements.txt`), o el panel arrancaria con codigo nuevo y dependencias viejas.
3. Si todo fue bien, aparece un boton **Reiniciar panel**. Al pulsarlo el proceso se cierra a proposito; systemd (con `Restart=always`, como arriba) o el propio bucle de `./run.sh` (ver mas abajo) lo vuelven a levantar en segundos ya con el codigo nuevo. Sin ninguno de los dos (p. ej. `run.bat` en Windows, o el proceso lanzado de otra forma), el panel se queda caido hasta que lo arranques a mano.

Sin servicio systemd, `./run.sh` ya relanza el panel solo si el proceso se cierra por su cuenta (como al pulsar **Reiniciar panel**): corre en un bucle dentro de la misma terminal, sin arrancar con el sistema ni quedar gestionado por systemd. Un `Ctrl+C` sigue cortando el bucle y cerrando el panel del todo — no reinicia. `run.bat` (Windows) no tiene este bucle; ahi reinicia tu mismo el proceso cuando te convenga.

## Logs y espacio en disco

- El panel purga cada hora el historico de `INSTANCES_LOGS_DIR` y las copias rotadas de la carpeta de logs nativa de cada instancia (`ACORE_LOGS_DIR`) con `LOGS_RETENTION_DAYS`, `LOGS_MAX_RUNS` y `LOGS_MAX_TOTAL_MB`.
- Los ficheros activos de AzerothCore (`Server.log`, `Playerbots.log`...) no se truncan desde fuera: limita su tamano en `worldserver.conf` con el sexto campo del Appender (p. ej. `Appender.Server=2,5,0,Server.log,w,104857600`).
- En Docker, rota tambien el log de cada contenedor (`logging: options: max-size/max-file` en el compose; WarCrafted-Deploy ya lo trae).

## Despliegue con Apache y systemd

La carpeta `deploy/` trae un vhost de Apache (proxy a `127.0.0.1:8000`, con `/ws/` por WebSocket) y una unidad systemd de ejemplo. Con `APP_HOST=127.0.0.1` el panel solo es accesible por el proxy; `run.sh` arranca uvicorn con `--proxy-headers` para que el limite de intentos de login use la IP real del cliente.

## Diagnostico de arranque

Si el boton "Iniciar" de una instancia falla, el panel devuelve el error exacto (binario no encontrado, proceso terminado al instante, etc.) tanto en el aviso del dashboard como en el log del servidor. Ademas, cada instancia escribe la salida de su proceso en `data/logs/<id-instancia>.log` (p. ej. `data/logs/instance-1.log`), util para ver por que `worldserver` no arranco.

## Solucion de problemas

| Sintoma | Posible causa |
|---|---|
| Las tarjetas muestran "-" en CPU/RAM | El proceso no esta en ejecucion, o `WORLD_PROCESS`/`WORKDIR` no coinciden con el proceso real |
| Una instancia aparece como tarjeta roja con un error | `INSTANCE_<N>_TYPE` no se pudo interpretar como `azerothcore` ni `playerbots`; revisa el valor en `.env` |
| Jugadores online no se actualiza | Credenciales o host de `DB_*` incorrectos, o el usuario MySQL no tiene permisos sobre la base `characters` |
| La consola GM devuelve error de conexion | El servicio SOAP no esta habilitado, el puerto esta bloqueado por firewall, o `SOAP_USER`/`SOAP_PASS` son incorrectos |
| "401 No autenticado" al recargar el panel | La sesion expiro (`ACCESS_TOKEN_EXPIRE_MINUTES`) o `SECRET_KEY` cambio; vuelve a iniciar sesion |
