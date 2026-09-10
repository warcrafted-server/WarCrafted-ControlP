# Manual de usuario

## Acceso al panel

Abre en tu navegador la direccion donde este publicado el panel (por ejemplo `http://localhost:8000` en una instalacion local). Se mostrara la pantalla de inicio de sesion.

Introduce el usuario y contrasena creados durante la instalacion (o con `python -m app.cli create-admin`). Tras iniciar sesion, la sesion se mantiene mediante una cookie segura durante el tiempo definido en `ACCESS_TOKEN_EXPIRE_MINUTES` (por defecto, 2 horas).

## Tema claro / oscuro

En la esquina superior derecha de cualquier pantalla encontraras un boton con un icono de luna/sol. Al pulsarlo, cambia entre tema claro y oscuro; la preferencia se guarda en el navegador y se recuerda en tu proxima visita.

## Panel principal (dashboard)

Al iniciar sesion accedes al panel principal, dividido en dos zonas:

### Estadisticas del host

Tres tarjetas en la parte superior muestran el estado general del servidor donde corre el panel:

- **CPU del host**: porcentaje de uso de CPU.
- **Memoria**: porcentaje de uso y detalle en MB usados/totales.
- **Disco**: porcentaje de uso del disco principal.

Estos datos se actualizan automaticamente cada 5 segundos.

### Instancias de emulador

Cada instancia configurada en `.env` aparece como una tarjeta con:

- **Indicador de estado**: punto y etiqueta bajo el nombre con 4 estados posibles:
  - **Detenido** (gris): no hay proceso en ejecucion.
  - **Arrancando** (ambar): el proceso ya esta vivo pero el mundo todavia no ha
    terminado de cargar — el reino aun no es accesible.
  - **En linea** (verde): mundo, red y SOAP ya cargados, se puede entrar.
  - **Deteniendo** (ambar): apagado en curso, esperando a que el proceso termine.
- **Tipo de emulador**: etiqueta "AzerothCore" o "Playerbots".
- **CPU / RAM**: consumo real del proceso `worldserver` de esa instancia (cada instancia se identifica por su propio PID y su `WORKDIR`, asi que dos instancias que comparten el mismo binario no se mezclan entre si). El % de CPU esta normalizado a 1 nucleo = 100% (puede superar el 100% en un proceso multihilo con varios nucleos ocupados); debajo aparece el mismo dato como % de la capacidad total del host, comparable con el CPU del host de las tarjetas de arriba.
- **Jugadores**: numero de personajes conectados. En instancias Playerbots, las cuentas de bots se excluyen del conteo para reflejar solo jugadores humanos.
- **Diff**: retraso del bucle principal del `worldserver` en milisegundos (comando SOAP `server info`, "Update time diff"). Verde por debajo de 50ms, ambar entre 50 y 150ms, rojo por encima de 150ms. Solo se muestra con la instancia En linea.

Si una instancia tiene una configuracion invalida (por ejemplo `INSTANCE_<N>_TYPE` no reconocible), aparece igualmente en el dashboard como una tarjeta roja con el motivo del error, en vez de desaparecer sin explicacion.

Cada tarjeta incluye cuatro acciones:

| Boton | Accion |
|---|---|
| **Iniciar** | Lanza el proceso `worldserver` usando el comando configurado en `INSTANCE_<N>_START_CMD`. Deshabilitado salvo en estado Detenido. |
| **Detener** | Envia un apagado controlado via SOAP (`server shutdown`); si el servicio SOAP no responde, intenta detener el proceso directamente. Deshabilitado solo en Detenido. Si la instancia se queda colgada en Deteniendo (puede pasar con muchos bots online), el boton pasa a **Forzar detencion**: un clic manda SIGTERM y, si no responde en 5 segundos, SIGKILL. |
| **Consola** | Abre la consola GM interactiva de esa instancia. |
| **Logs** | Abre el historico de logs de esa instancia (ver siguiente seccion). |

No hace falta estar delante para rematar un apagado colgado: el panel vigila en segundo
plano cualquier apagado en curso, aunque no lo haya pedido el, y cuando deja de avanzar lo
fuerza el solo (SIGTERM y, si no responde, SIGKILL). Asi un `server shutdown` lanzado por
SOAP desde un script de reinicio nocturno tampoco se queda a medias.

Cuanto espera antes de rematarlo depende de por donde vaya el cierre. Mientras el
`worldserver` esta vaciando consultas pendientes en la base de datos le da 3 minutos sin
escribir nada en el log, porque ahi si que puede tardar de verdad y cortarlo perderia
partidas. En cuanto el log dice que ya ha cerrado las bases, 30 segundos: a esas alturas
solo le queda salir. El margen largo se ajusta con `SHUTDOWN_STUCK_TIMEOUT` en el `.env`,
y con `0` se desactiva la vigilancia.

### Tarjetas de authserver

Junto a las tarjetas de instancia, en el mismo grid, hay una tarjeta por cada authserver
configurado, con **Cuentas creadas** y **Cuentas conectadas** y botones **Iniciar**/
**Detener**. Si dos o mas reinos comparten el mismo authserver
(`INSTANCE_<N>_AUTH_SERVICE_ID` apuntando al mismo `AUTH_SERVICE_<M>_*`), aparece una unica
tarjeta con la lista de **reinos asociados**, en vez de una tarjeta por reino. El grid
agrupa cada authserver junto a sus reinos y ajusta el numero de columnas al grupo mas
grande, asi que un authserver privado queda junto a su reino, y uno compartido por varios
reinos encabeza la fila con todos ellos al lado. El authserver no tiene consola SOAP ni log
propio en el panel, asi que su estado es solo Detenido/En linea (el proceso existe o no) y
su parada es siempre inmediata: SIGTERM y, si no responde en 5 segundos, SIGKILL
directamente (sin el paso intermedio de "Forzar detencion" del worldserver).

### Historico de logs y "ver en vivo"

Cada vez que arrancas una instancia, el panel guarda la salida de consola
(stdout/stderr) del proceso en un fichero nuevo — no un unico log que crece
sin fin, sino uno por arranque, para poder comparar sesiones distintas.
Esta captura limpia los codigos de color/control ANSI y corta cualquier
linea que se repita mas de 20 veces seguidas (p.ej. un prompt que se
redibuja sin fin porque el proceso no tiene una terminal real detras), para
que un cuelgue asi no llene el disco.

Si ademas configuraste `INSTANCE_<N>_ACORE_LOGS_DIR` y
`INSTANCE_<N>_LOG_CATEGORIES` en el `.env` (ver `.env.example`), el panel
tambien guarda una copia de los logs nativos de AzerothCore de esas
categorias (`server`, `errors`, `playerbots`, `gm`, `chat`) del arranque
anterior, tomada justo antes de lanzar el proceso nuevo. Ademas, si solo
configuraste `INSTANCE_<N>_ACORE_LOGS_DIR`, el modal tambien muestra —
agrupados aparte como "AzerothCore (en vivo)" — todos los ficheros `.log`
que AzerothCore tenga ahora mismo en esa carpeta (`Server.log`,
`DBErrors.log`, `Char.log`, etc.), sin necesidad de listarlos en
`LOG_CATEGORIES`.

El boton **Logs** de cada tarjeta abre una ventana con:

- Un desplegable con todos los arranques guardados (mas reciente primero,
  identificados por categoria y fecha) y, si aplica, los ficheros nativos
  actuales de AzerothCore. Por rendimiento, el visor solo carga el ultimo
  medio MB de cada archivo; si el archivo es mas grande, aparece un aviso
  encima del visor.
- **Ver en vivo**: sigue en tiempo real el log de consola del arranque
  activo, mientras la instancia sigue en ejecucion (mantiene como maximo
  las ultimas 2000 lineas en pantalla).
- **Copiar**: copia al portapapeles lo que se ve en el visor (si el archivo
  esta recortado, copia solo esa parte).
- **Descargar**: descarga el archivo completo (no solo lo mostrado en
  pantalla) como `.txt`.

Por defecto se conservan como maximo 15 arranques por categoria, y se
purgan los que superen 7 dias — ajustable con `LOGS_RETENTION_DAYS` y
`LOGS_MAX_RUNS` en el `.env`.

## Menu de plugins

Junto al nombre de usuario, el boton **Plugins** despliega un menu con los modulos instalados que tienen interfaz propia (los que declaran `ui.has_ui: true` en su `manifest.json`). Cada entrada enlaza directamente a la pantalla del plugin; si ninguno tiene interfaz, el menu lo indica.

## Tienda de Plugins

El boton **Tienda** (junto al menu de Plugins) abre el catalogo de modulos disponibles en el repositorio `WarCraftedCP-plugins`, para instalarlos sin tocar la linea de comandos.

- **Sin token de GitHub**: la tienda muestra un aviso para conectar uno. Pulsa **Configurar token de GitHub**, sigue las instrucciones del modal para crear un *Personal Access Token* (fine-grained) con permiso **Contents: Read-only** sobre ese repositorio (y sobre `WarCrafted-ControlP` tambien, si quieres poder actualizar el panel desde aqui), y pegalo. Se verifica contra GitHub y se guarda; nunca se muestra de nuevo una vez guardado.
- **Con token**: aparece una cuadricula con cada modulo (nombre, version, descripcion) y un boton **Instalar**, o su estado si ya esta presente en `app/plugins/`: **Instalado · actualizado** si coincide con la version del repo, o **v actual instalada** + boton **Actualizar** si hay una version distinta.
- Al instalar o actualizar, el modulo se descarga y se monta (o remonta) de inmediato — no hace falta reiniciar el panel. Aparece un enlace **Abrir** si el modulo tiene interfaz propia, y la proxima vez que cargues el menu **Plugins** ya lo veras ahi. El dashboard principal muestra un punto rojo sobre el boton **Tienda** si hay actualizaciones pendientes, ya sean de plugins o del propio panel, sin necesidad de entrar a comprobarlo.
- Actualizar nunca borra datos que el propio modulo haya generado (como los backups de personajes del plugin `migration`): solo sobrescribe los archivos que vienen en la version nueva.

Arriba del catalogo, la tarjeta **Panel principal** hace lo mismo para el propio panel — ver "Autoactualizacion del panel" en `INSTALL.md` para el detalle (incluye reiniciar el proceso para aplicar cambios).

Antes de aplicar cualquier actualizacion (de un plugin o del panel), un modal muestra la version actual, la disponible, y un resumen de que cambia; puedes **Aceptar y actualizar** o **Demorar** (no pasa nada si demoras: el boton de actualizar sigue ahi para la proxima vez).

Solo un administrador puede configurar el token, instalar/actualizar modulos, o actualizar/reiniciar el panel.

## Consola GM

La consola reproduce una terminal (basada en Xterm.js) conectada por WebSocket al panel. Cada linea que escribas y envies con **Enter** se ejecuta como comando GM contra el servicio SOAP de la instancia, y la respuesta del servidor se muestra a continuacion.

La consola es una ventana flotante dentro de la pagina:

- **Mover**: arrastra la cabecera superior ("Consola GM — ...") a cualquier punto de la pantalla.
- **Redimensionar**: arrastra cualquiera de los bordes o esquinas de la ventana; el terminal se reajusta automaticamente al nuevo tamano.
- **Historial de comandos**: usa las flechas **↑** / **↓** para recuperar comandos que ya enviaste, igual que en una terminal normal.

Ejemplos de comandos utiles:

```
server info
account set gmlevel <usuario> 3 -1
kick <personaje>
announce Mensaje para todo el servidor
```

Si el servicio SOAP no esta disponible, la consola mostrara un mensaje de error indicando el motivo (credenciales invalidas, conexion rechazada, etc.).

Para volver al panel principal, usa el enlace "← Panel" en la parte superior de la pantalla de consola.

## Cerrar sesion

Pulsa **Cerrar sesion** en la parte superior del panel para invalidar la cookie de sesion y volver a la pantalla de inicio de sesion.

## Buenas practicas de seguridad

- Cambia la contrasena de administrador periodicamente con `python -m app.cli create-admin` (crea el usuario si no existe, o actualiza la contrasena si ya existe).
- No compartas el archivo `.env`; contiene la clave de firma de sesiones y las credenciales SOAP/DB de tus emuladores.
- Si publicas el panel fuera de tu red local, hazlo detras de un proxy HTTPS y activa `COOKIE_SECURE=true` en `.env`.
