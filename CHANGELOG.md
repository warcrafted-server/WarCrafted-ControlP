# Changelog

Todas las modificaciones relevantes de este proyecto se documentan en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto sigue [Versionado Semantico](https://semver.org/lang/es/).

## [Sin publicar]

## [0.16.1] - 2026-08-23

### Corregido
- Parada programada: el mensaje no llegaba al chat, solo la cuenta atras. Se debia a que
  `server shutdown <segundos> <exitcode> <motivo>` ignora el motivo por completo en cuanto
  se le da un exitcode explicito (lo haciamos para evitar que la primera palabra del
  mensaje se leyera como exitcode). Ahora el mensaje se manda aparte por `announce`
  (chat) ademas de `notify` (pantalla), y el shutdown va sin motivo ni exitcode.
- Ventana de parada programada: los campos de horas/minutos/segundos ahora llevan una
  etiqueta visible encima (antes solo tenian placeholder, que desaparecia con el valor
  por defecto ya puesto).

## [0.16.0] - 2026-08-23

### Añadido
- Nuevo botón "Parada programada" junto a Detener (mitad de espacio cada uno): abre una
  ventana con tiempo de espera (horas/minutos/segundos) y mensaje, y avisa a los jugadores
  a la vez por chat (`server shutdown`, con la cuenta atrás nativa de AzerothCore) y en
  pantalla (`notify`).
- Si tras un apagado normal el proceso sigue vivo pasados 15 segundos (o el tiempo de la
  parada programada más 15s), se fuerza el cierre automáticamente sin esperar a una
  segunda pulsación de "Forzar detencion" (que sigue funcionando igual).

## [0.15.1] - 2026-08-23

### Corregido
- `SoapClient.execute()` dejaba sin decodificar las referencias numericas de caracter
  (`&#xD;`, etc.) del XML de respuesta: `xml.sax.saxutils.unescape()` solo entiende
  `&amp;`/`&lt;`/`&gt;`, asi que un `\r` de fin de linea llegaba a la UI como el texto
  literal `&#xD;` en vez de un salto de linea. Se sustituye por `html.unescape()`, que
  decodifica tambien esas referencias numericas.

## [0.15.0] - 2026-08-19

### Anadido
- Cinco funciones nuevas en `app.deps` para plugins de moderacion/soporte:
  `execute_gm_command()` (cualquier comando GM por SOAP, `require_admin`; primer ejecutor
  general que se expone a un plugin, misma superficie que la consola nativa del panel pero
  mas restringida), `list_online_players()` (roster desde `db_characters`, sin ping: AzerothCore
  no lo guarda en base de datos), y `search_items()`/`search_spells()`/`search_teleports()`
  (autocompletado de solo lectura contra la base de datos de mundo).
- Nuevo campo `INSTANCE_<N>_DB_WORLD` (por defecto `acore_world`), la base de datos de mundo
  que usan esas tres ultimas funciones.

## [0.14.1] - 2026-08-19

### Corregido
- Layout del dashboard: las tarjetas de authserver y de reino vuelven a un unico grid
  (antes eran dos rejillas separadas con etiquetas "Instancias de authserver"/
  "Instancias de emulador" que rompian la alineacion con las 3 tarjetas de metricas del
  host). Ahora se intercalan por grupo (authserver seguido de sus reinos) y las columnas
  se ajustan al grupo mas grande: un authserver compartido por 2 reinos ocupa una fila de
  3 columnas junto a ambos; dos authservers independientes ocupan 2 filas de 2 columnas,
  cada uno junto a su reino.
- El `id` del contenedor del grid pasa de `servers-grid`/`auth-services-grid` a
  `instances-grid` (uno solo); el plugin `metrics_history`, que localizaba `servers-grid`
  para inyectar su mini-grafica, se actualiza a la vez (ver `WarCraftedCP-plugins`).

## [0.14.0] - 2026-08-19

### Cambiado
- Rediseño del authserver: pasa de ser 1:1 por reino a un servicio propio,
  referenciable por `INSTANCE_<N>_AUTH_SERVICE_ID`, que varios reinos pueden compartir
  (`AUTH_SERVICE_<M>_*` en `.env`). El dashboard le dedica una única tarjeta por servicio
  (no una por reino), con la lista de reinos vinculados. Sin `AUTH_SERVICE_ID`, cada reino
  sigue teniendo su propio authserver implícito, igual que hasta ahora — no hace falta
  tocar el `.env` de una instalación existente.
- **Rotura de API**: `POST /api/servers/{id}/auth/start|stop` desaparecen; el control del
  authserver pasa a `POST /api/servers/auth-services/{auth_service_id}/start|stop`. La
  respuesta de `GET /api/servers` ya no lleva `auth_state`/`accounts_total`/
  `accounts_online` (duplicaban esos datos por cada reino que comparte servicio); en su
  lugar lleva `auth_service_id`, y esos tres campos ahora viven en la respuesta nueva de
  `GET /api/servers/auth-services`.

## [0.13.0] - 2026-08-19

### Anadido
- Tarjeta del authserver en el dashboard, a la izquierda de la del worldserver de cada
  instancia: arrancar/parar (`AUTH_START_CMD` en `.env`) y cifras de cuentas creadas/conectadas
  (`DB_AUTH`, `acore_auth` por defecto). El authserver no tiene SOAP ni consola, asi que su
  parada es siempre SIGTERM con escalada a SIGKILL en la misma llamada (sin el paso intermedio
  "Forzar detencion" que si tiene el worldserver).
- Nueva funcion `app.deps.get_instance_etc_dir()`, mismo patron que
  `get_instance_modules_conf_dir()` pero para el propio `etc/` (worldserver.conf/
  authserver.conf).

## [0.12.0] - 2026-08-19

### Anadido
- Dos funciones nuevas en `app.deps` para que un plugin gestione archivos de
  configuracion de una instancia sin importar `EmulatorManager`:
  `get_instance_modules_conf_dir()` (ruta de `etc/modules/`) y
  `reload_instance_config()` (envia `reload config` por SOAP).

## [0.11.0] - 2026-08-19

### Anadido
- Nueva funcion `app.deps.get_servers_snapshot()`: da a los plugins el mismo
  estado (CPU/RAM/jugadores/diff) que ya devuelve `GET /api/servers`, pero
  callable desde una tarea en segundo plano propia (sin request HTTP ni
  usuario), sin tener que importar `EmulatorManager` directamente.

### Documentado
- `INSTALL.md`: nueva seccion "HTTPS (recomendado)" — sin HTTPS (ni acceder
  como `localhost`) el navegador bloquea funciones como las notificaciones
  de escritorio sin avisar. Ejemplo con Caddy y con Apache/nginx + certbot,
  y el aviso de activar `COOKIE_SECURE=true` solo despues de tener el panel
  detras de HTTPS.

## [0.10.0] - 2026-08-19

### Anadido
- Los plugins ya pueden declarar un `ui.background_script` opcional en su
  `manifest.json`: un script que se carga en segundo plano en **todas** las
  paginas del panel (no solo en la vista propia del plugin), pensado para
  vigilar el estado del panel y reaccionar aunque el usuario no tenga esa
  vista abierta. Cero coste para plugins que no lo declaren.

## [0.9.0] - 2026-08-19

### Anadido
- `run.sh` relanza el panel solo si el proceso se cierra por su cuenta (p.ej.
  tras pulsar **Reiniciar panel** despues de actualizar), sin necesitar
  systemd: corre en un bucle dentro de la misma terminal, y `Ctrl+C` sigue
  cortandolo del todo en vez de reiniciar.

## [0.8.0] - 2026-08-19

### Anadido
- Nueva metrica **Diff** en cada tarjeta de instancia: el retraso del bucle
  principal del `worldserver` (comando SOAP `server info`, campo "Update
  time diff"), en milisegundos, con color segun el rango (verde menos de
  50ms, ambar 50-150ms, rojo mas de 150ms). Solo se consulta con la instancia En
  linea; no anade peticiones nuevas, viaja en la misma respuesta de
  `GET /api/servers` que ya se pedia cada 5 segundos.

## [0.7.1] - 2026-08-19

### Corregido
- El boton **Detener** quedaba deshabilitado durante todo el estado
  Deteniendo, sin forma de insistir si el apagado se quedaba colgado (visto
  con AzerothCore + muchos bots online: el proceso puede quedarse sin hacer
  nada, con SOAP y el puerto de juego ya cerrados, sin llegar a salir). Ahora
  el boton pasa a **Forzar detencion** y sigue activo; un segundo clic se
  salta el SOAP (si el apagado normal no funciono, repetirlo tampoco lo
  hara) y manda SIGTERM, escalando a SIGKILL si no responde en 5 segundos.
- El HTML de cada pagina enlazaba sus `.js`/`.css` sin cache-busting; tras
  actualizar el panel (p.ej. a 0.7.0, que renombro `online` por `state` en
  `GET /api/servers`), un navegador con el `dashboard.js` viejo ya en cache
  seguia leyendo el campo que ya no existe y mostraba todo como Detenido
  aunque el backend estuviera bien. Ahora cada `<script>`/`<link>` de
  `/static/` lleva `?v=<VERSION>`, asi que una actualizacion del panel
  siempre fuerza a pedir el fichero nuevo. Si ya te paso, con recargar la
  pagina (Ctrl/Cmd+Shift+R) se soluciona sin esperar a este cambio.

## [0.7.0] - 2026-08-19

### Anadido
- El estado de cada instancia ya no es solo "en marcha/parada": el dashboard
  distingue **Arrancando** (proceso vivo pero el mundo aun no ha terminado
  de cargar) y **Deteniendo** (apagado en curso) de **En linea** y
  **Detenido**, con su etiqueta debajo del nombre. La deteccion de "ya se
  puede entrar al reino" busca en el log de consola la linea que AzerothCore
  imprime justo cuando terminan de cargar mundo, red y SOAP
  (`"(worldserver-daemon) ready"`). Iniciar se deshabilita salvo en
  Detenido; Detener se deshabilita en Detenido y Deteniendo.

### Corregido
- La captura de consola guardaba las secuencias ANSI/VT100 tal cual (colores,
  redibujados de "AC> "), y si el proceso no tenia una terminal real detras
  podia quedarse redibujando el prompt sin fin, llenando el log con cientos
  de MB de basura. Ahora un hilo lee la salida del proceso, limpia los
  codigos ANSI y corta una linea que se repite mas de 20 veces seguidas
  (deja un aviso y frena al proceso via backpressure del pipe). Tambien se
  limpian codigos ANSI al servir la vista previa y el "ver en vivo", por si
  quedan logs antiguos ya afectados.

### Anadido
- El modal **Logs** tambien lista y muestra los ficheros nativos que
  AzerothCore tenga en ese momento en su `LogsDir` (`Server.log`,
  `DBErrors.log`, `Char.log`, etc.), agrupados aparte como "AzerothCore (en
  vivo)" en el desplegable — ya no hace falta tenerlos pre-configurados en
  `LOG_CATEGORIES` para poder verlos.

## [0.6.1] - 2026-08-19

### Corregido
- Abrir un log grande en el modal **Logs** del dashboard colgaba la pestaña
  del navegador: se cargaba y renderizaba el archivo entero. Ahora
  `GET /api/servers/{id}/logs/{filename}` solo devuelve el ultimo medio MB
  (`log_manager.PREVIEW_MAX_BYTES`), leido con un `seek` desde el final del
  archivo, y avisa en el modal si el contenido esta recortado. El boton
  **Descargar** ya no depende de lo cargado en el navegador: enlaza
  directamente a `GET /api/servers/{id}/logs/{filename}/download`, que sirve
  el archivo completo desde disco. En "ver en vivo" tambien se limita el
  buffer a las ultimas 2000 lineas para no acumular memoria sin fin en
  sesiones largas.

## [0.6.0] - 2026-08-19

### Anadido
- Historico de logs por instancia: cada arranque genera su propio fichero
  (`GET /api/servers/{id}/logs` los lista, `GET /api/servers/{id}/logs/{filename}`
  lee uno), con purga automatica configurable (`LOGS_RETENTION_DAYS`,
  `LOGS_MAX_RUNS`). Si se indica `INSTANCE_<N>_ACORE_LOGS_DIR`, tambien se
  archivan copias de los logs nativos de AzerothCore de las categorias
  elegidas en `INSTANCE_<N>_LOG_CATEGORIES` (server, errors, playerbots, gm,
  chat).
- Streaming en vivo del log de consola activo por WebSocket
  (`/ws/servers/{id}/logs`).

### Cambiado
- El boton **Log** del dashboard pasa a llamarse **Logs** y abre un modal con
  selector de historico, copiar, descargar y "ver en vivo", sustituyendo el
  visor simple de la version anterior.

## [0.5.0] - 2026-08-19

### Anadido
- Boton **Log** en cada tarjeta de instancia (`GET /api/servers/{id}/log`): muestra en una ventana lo que el proceso `worldserver` escribe por stdout/stderr, desde el arranque, guardado en `data/logs/<instancia>.log`. Se actualiza sola cada 3 segundos mientras esta abierta.

### Cambiado
- Los botones **Iniciar** y **Detener** del dashboard se deshabilitan (sombreados) segun el estado real de la instancia, para no poder iniciar dos veces un servidor ya en marcha ni detener uno que ya esta parado.

## [0.4.1] - 2026-08-18

### Corregido
- El aviso de actualizaciones del dashboard principal solo miraba los plugins; ahora tambien consulta `GET /api/system/update-check`, asi que un punto rojo sobre "Tienda" avisa igual si lo que cambio es el propio panel.
- `extract_tarball` no preservaba los permisos de los archivos del repo: `run.sh` e `install.sh` perdian el bit `+x` al instalar o actualizar el panel. Si ya te paso, ejecuta `chmod +x run.sh install.sh` a mano una vez; las proximas actualizaciones ya lo mantienen.

## [0.4.0] - 2026-08-18

### Anadido
- Las tarjetas de instancia muestran tambien el % de CPU como capacidad del host (ademas del % por-proceso, normalizado a 1 nucleo = 100%), para que no parezca un error ver, p. ej., 179% de CPU en una instancia con el host al 68%.
- Antes de aplicar cualquier actualizacion (de un plugin o del propio panel) aparece un modal con la version actual, la disponible, y un resumen en texto de que cambia (la seccion correspondiente de `CHANGELOG.md` para el panel, o el campo opcional `changelog` del `manifest.json` para plugins), con opcion de aceptar o demorarla.

## [0.3.0] - 2026-08-18

### Anadido
- Menu desplegable "Plugins" en la barra superior del panel: consume `GET /api/v1/plugins/` y enlaza los modulos que declaren `ui.has_ui: true` en su `manifest.json` (titulo, ruta e icono definidos por cada plugin).
- El loader de plugins expone metadatos de interfaz (`ui.has_ui`, `ui.title`, `ui.route`, `ui.icon`) y el core los publica mediante `app/api/plugins.py`.
- Tienda de Plugins (`/plugins/store`): conecta un Personal Access Token de GitHub (`POST /api/v1/plugins/setup-token`, guardado en `GITHUB_PLUGIN_TOKEN` dentro de `.env`), lista el catalogo del repo `WarCraftedCP-plugins` (`GET /api/v1/plugins/catalog`) marcando que modulos ya estan instalados y si hay version nueva, instala uno con un clic (`POST /api/v1/plugins/install/{nombre}`) y lo actualiza (`POST /api/v1/plugins/update/{nombre}`) fusionando la version nueva sobre la carpeta existente sin borrar datos que el plugin haya generado (backups, etc.). Todo se monta o remonta en caliente, sin reiniciar el panel. Requiere permisos de administrador.
- Autoactualizacion del propio panel (`GET /api/system/update-check`, `POST /api/system/update`, `POST /api/system/restart`): compara el archivo `VERSION` local contra el del repo `WarCrafted-ControlP` en GitHub, descarga y fusiona la version nueva sin tocar `.env`, `data/` ni los plugins instalados, reinstala `requirements.txt` en el mismo venv si cambio, y permite reiniciar el proceso para aplicar los cambios (requiere un supervisor externo como systemd `Restart=always` para volver a levantarse).

## [0.2.0] - 2026-08-18

### Corregido
- Independencia de procesos entre instancias: la deteccion ya no se basa solo en el nombre del binario (`WORLD_PROCESS`), sino en un PID propio por instancia mas coincidencia por `WORKDIR` (con `cmdline` como respaldo). Antes, dos instancias con el mismo binario `worldserver` podian detenerse mutuamente.
- Medicion de CPU siempre en 0%: `psutil.Process.cpu_percent()` se invocaba dentro de un bloque `oneshot()`, que cacheaba la lectura "antes" y anulaba la comparacion "despues". Ahora la medicion se hace fuera de ese bloque y refleja el consumo real.
- El listado de instancias (`/api/servers`) recarga el `.env` en cada peticion, de forma que anadir o editar una instancia se refleja en el dashboard sin reiniciar el panel.
- `INSTANCE_<N>_TYPE` admite variantes del valor esperado (p. ej. `playerbots-acore`) mediante coincidencia parcial; una instancia con un tipo realmente no reconocido ya no desaparece del dashboard, se muestra como tarjeta de error con el motivo.

### Anadido
- Historial de comandos en la consola GM: las flechas Arriba/Abajo navegan por los comandos enviados anteriormente (Xterm.js).
- Consola GM como panel flotante: cabecera arrastrable para moverla y bordes/esquinas para redimensionarla, con reajuste automatico de Xterm.js (`fitAddon.fit()`) en cada cambio de tamano.
- Los fallos de arranque o parada de una instancia devuelven el error exacto en la respuesta JSON y quedan registrados tanto en el log del servidor como en `data/logs/<instancia>.log`.

## [0.1.0] - 2026-08-18

### Anadido
- Estructura inicial del proyecto con backend FastAPI y frontend TailwindCSS.
- Autenticacion con usuario/contrasena, hash bcrypt y sesiones JWT en cookie httpOnly.
- Arquitectura modular de drivers de emulador (`BaseEmulatorDriver`) con implementaciones para AzerothCore estandar y AzerothCore + Playerbots.
- Gestion de multiples instancias configurables desde `.env`.
- Cliente SOAP para ejecucion de comandos GM.
- Consola interactiva en tiempo real via WebSocket + Xterm.js.
- Panel con tarjetas de estado de CPU, RAM y jugadores online, y estadisticas del host.
- Tema claro/oscuro intercambiable con persistencia en el navegador.
- Scripts de autoinstalacion multiplataforma (`install.sh`, `install.bat`) y de arranque (`run.sh`, `run.bat`).
- Documentacion inicial: README, INSTALL y USER_GUIDE.
- `.gitignore` estricto para proteger credenciales y excluir rastros de herramientas de IA.
