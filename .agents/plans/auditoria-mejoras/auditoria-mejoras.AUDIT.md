# Auditoría de mejoras — WarCrafted-ControlP y plugins

Fecha: 2026-09-27. Referencias de código: `WarCrafted-ControlP@106e7b0`,
`WarCraftedCP-plugins@8a978f6`. Servidor: Debian `warcrafted`, reinos IceTracks (producción,
`Servers/acore-playerbots`) y Desarrollo (`Servers/acore-test`).

Prioridad: **P1** hacer ya · **P2** próximo ciclo · **P3** cuando haya hueco.
Esfuerzo: **S** < 1 h · **M** medio día · **L** varios días.

## 1. Resumen: lo primero que haría

| # | Qué | Prio | Esf. |
|---|-----|------|------|
| 1 | Quitar la contraseña SOAP en claro de `Servers/reinici_programat.sh` y cambiarla | P1 | S |
| 2 | Verificar que 8001 (panel, HTTP) y 3306 (MySQL, `*:3306`) no llegan desde Internet | P1 | S |
| 3 | Gestionar los volcados `core.*` (~25 GB, disco al 80 %) y analizar las caídas | P1 | M |
| 4 | Avisos en el servidor (Discord/Telegram), no solo en el navegador | P1 | M |
| 5 | Reinicio automático del worldserver tras una caída | P2 | M |
| 6 | Copia de los backups fuera del servidor | P2 | M |

## 2. Seguridad

**S1 · Contraseña SOAP en texto plano — P1, S.** `Servers/reinici_programat.sh` lleva usuario y
contraseña de la cuenta SOAP dentro del `curl`. Es una cuenta GM con acceso total por SOAP.
Propuesta: cambiar la contraseña de esa cuenta; el script debe leerla de un fichero `chmod 600`
(o de `.env`) o, mejor, pasar a usar el reinicio programado del panel (ver F3) y borrar el script.

**S2 · Exposición de red — P1, S (verificar).** El panel escucha en `0.0.0.0:8001` por HTTP plano
(no pasa por el Apache del 443) con `COOKIE_SECURE=false`, y MySQL en `*:3306` (sin
`bind-address`). No se pudo comprobar el cortafuegos (requiere sudo). Propuesta: confirmar que el
router no reenvía 8001/3306; poner el panel detrás de Apache con HTTPS (`ProxyPass` +
`COOKIE_SECURE=true`) y `bind-address = 127.0.0.1` en MySQL si nada externo lo usa. HTTPS además
es requisito para las notificaciones de escritorio fuera de `localhost`.

**S3 · Todo usuario es admin — P2, S.** `app/models.py:15` pone `is_admin=True` por defecto y no hay
roles. Hoy solo hay un usuario, pero en cuanto se cree otro (p. ej. un GM) tendrá acceso total.
Propuesta: `default=False`, y un rol intermedio (GM: jugadores, correo, consola; sin compilar,
restaurar BD ni actualizar el panel).

**S4 · Endpoints de plugins sin `require_admin` — P2, S.** `migration/router.py` (6 endpoints, entre
ellos la migración que escribe en las bases de personajes) solo exige sesión. Inocuo mientras
todos sean admin (S3); se vuelve un agujero al introducir roles. Revisar también
`metrics_history` (solo lectura, aceptable).

**S5 · Sesiones sin revocación — P3, M.** JWT de 120 min (`app/security.py`); `logout`
(`app/api/auth.py:34`) solo borra la cookie, el token robado sigue valiendo. Propuesta: guardar un
`token_version` por usuario y comprobarlo en `get_current_user`; permite "cerrar todas las
sesiones" y cambiar contraseña desde la UI.

**S6 · `SECRET_KEY` por defecto — P3, S.** `app/config.py:16` usa `CHANGE_ME` si falta en `.env`.
En producción está bien puesta (verificado, 64 caracteres), pero una instalación nueva olvidada
permitiría falsificar sesiones. Propuesta: negarse a arrancar con `APP_ENV=production` y la clave
por defecto.

**S7 · Dependencias — P3, S.** `python-jose 3.3.0` tiene CVE conocidas (CVE-2024-33663,
CVE-2024-33664) y está sin mantenimiento; `passlib 1.7.4` también. Propuesta: `PyJWT` y `bcrypt`
directo. Conviven además dos drivers MySQL (`pymysql` en el core, `mysql-connector-python` solo en
`migration/migrate_character.py`); unificar en `pymysql`.

## 3. Fiabilidad y operación

**F1 · Volcados de memoria y caídas — P1, M.** En `Servers/acore-playerbots/bin/` hay 5 `core.*`
(1–6 GB cada uno, el último del 27/09 00:19) y 1 en `acore-test`. Son caídas reales del
worldserver que nadie está analizando, y llenan el disco (80 % usado). Propuesta: plugin
"Caídas" (ver P-3): lista los volcados, saca el backtrace con `gdb -batch -ex bt` contra el binario
del backup de ejecutables que corresponde a esa fecha, guarda el texto y borra el volcado con
retención configurable.

**F2 · Sin reinicio automático tras caída — P2, M.** El panel detecta procesos colgados al apagar
(`shutdown_watchdog`), pero si el worldserver crashea se queda parado. `web-notifications` avisa de
"caída inesperada", pero solo si hay un navegador abierto. Propuesta: opción por instancia
"reiniciar tras caída" (máx. N intentos en X minutos para no entrar en bucle), con aviso.

**F3 · Reinicio programado fuera del panel — P2, S.** `reinici_programat.sh` reinicia el Debian
entero tras `server shutdown 300`; no está en el crontab de `stark` (¿root o sin programar?). Su
comentario dice 330 s de espera pero hace `sleep 60`. El panel ya tiene "parada programada con
aviso" (`scheduled_stop`). Propuesta: "reinicio programado" en el panel (hora + días + aviso), que
use la parada con aviso y vuelva a arrancar la instancia, sin reiniciar el sistema operativo.

**F4 · Arranque tras reinicio del Debian fuera del panel — P3, M.** `@reboot` lanza authserver,
worldserver y panel en `tmux` (`arrancar_servidor.sh`), sin pasar por el panel: el histórico de
consola del arranque no queda en el panel. Propuesta: `systemd` solo para el panel
(`Restart=always`, ya documentado en `INSTALL.md`) y opción "arrancar al iniciar el panel" por
instancia.

**F5 · Avisos solo en el navegador — P1, M.** Todas las notificaciones (`web-notifications`) viven en
el navegador: si nadie tiene el panel abierto, una caída o un backup fallido a las 4:00 no avisa a
nadie, y el historial solo existe en ese navegador. Propuesta: canal de avisos en el servidor
(ver P-1), con historial en disco.

**F6 · Backups solo en el mismo disco — P2, M.** `app/backups/` (5,9 GB de ejecutables, 469 MB de BD)
está en el mismo disco que las bases. Un fallo de disco se lleva ambos. Propuesta: en
`db_manager`, destino remoto opcional (rsync/SFTP o rclone a un almacenamiento externo) tras cada
backup programado, y una prueba periódica de restauración en la BD `_test`.

**F7 · Cambios de código directos en producción — P2, proceso.** `mod-ale` ya está en
`acore-playerbots/modules/` (producción) pero no clonado en el perfil de Test. La norma del
proyecto es probar en Desarrollo antes. Propuesta: en `core_updater`, avisar si un repo existe en
el perfil de producción y no en el de pruebas.

## 4. Calidad y mantenimiento

**C1 · Sin tests ni CI — P2, M.** Ningún repo tiene `tests/` ni `.github/`. Hoy tres fallos llegaron a
producción que un test mínimo habría detectado (500 en `db_manager` por la dependencia síncrona,
`behind=None` en `core_updater`, `watch.js` cacheado). Propuesta: `pytest` con peticiones ASGI
contra cada router (importando el plugin con `app.deps` simulado) y un workflow de GitHub Actions
que ejecute `pytest` + `node --check` de los JS en cada push.

**C2 · Estáticos sin versión en los plugins — P2, S.** El core añade `?v={{ app_version }}` a sus JS;
los plugins no (`view.html` carga `/static/js/*.js` y sus propios scripts sin versión). Fue la causa
del fallo de `web-notifications`. Propuesta: exponer la versión del plugin a su plantilla y usarla
en todos los `<script src>`, o servir con `Cache-Control: no-cache`.

**C3 · Plantillas duplicadas — P3, M.** Las 8 vistas repiten `<head>`, config de Tailwind, script de
tema y enlaces de Font Awesome. Cualquier cambio global exige tocar 8 ficheros (pasó hoy dos
veces). Propuesta: que el core exponga un layout base para plugins (`app/templates/plugin_base.html`
+ helper en `app.deps`), heredado vía Jinja.

**C4 · Tailwind por CDN — P3, S.** `cdn.tailwindcss.com` es la versión de desarrollo (compila en el
navegador, avisa en consola, depende de Internet). Propuesta: CSS precompilado servido en `/static`.

**C5 · Documentación desfasada — P2, S.** `USER_GUIDE.md` no refleja lo añadido hoy: barra de
navegación en todas las páginas, pantalla `/plugins/menu`, backups programados. `CLAUDE.md` exige
mantenerla al día.

## 5. Nuevos plugins

Ordenados por valor para este servidor.

**P-1 · Avisos a Discord/Telegram (servidor) — P1, M.** Hilo en el propio plugin que vigila
`get_servers_snapshot()` y los resúmenes de `core_updater`/`db_manager`, y envía a un webhook de
Discord o bot de Telegram: caída, reinicio, lag alto, backup fallido, actualizaciones del core,
disco > 90 %. Historial en disco consultable desde el panel. Sustituye la parte crítica de
`web-notifications` (que puede quedarse para avisos de escritorio).

**P-2 · Tickets y sanciones GM — P2, M.** Lee `gm_ticket` (characters) para ver y cerrar tickets de
jugadores sin entrar al juego, y `account_banned` / `ip_banned` / `character_banned` /
`account_muted` para listar sanciones activas con su motivo, autor y caducidad, y levantarlas.
Complementa a `gm_commander` (que ya puede aplicarlas).

**P-3 · Caídas (crash reports) — P1, M.** Ver F1: backtrace automático de cada `core.*`,
agrupado por firma (misma función en lo alto de la pila = mismo fallo), vinculado a la versión de
ejecutables y a los repos del perfil en ese momento. Permite ver si una actualización de
`mod-playerbots` introdujo caídas.

**P-4 · Estado público del reino — P2, M.** Página sin login (lectura) con estado online/offline de
cada reino, jugadores reales conectados (sin bots), uptime y próximo reinicio programado.
Útil para enlazar desde web/Discord. Cuidado: sin datos sensibles y con caché de 30–60 s.

**P-5 · Economía y subastas — P3, M.** Con `auctionhouse`, `mail` y `guild_bank_eventlog`: oro total
en circulación, top de fortunas, precios medios en subasta, volumen de `mod-ah-bot` frente al de
jugadores. Detecta exploits (oro que aparece de golpe) y ayuda a ajustar el AH bot.

**P-6 · Playerbots — P2, L.** El servidor gira en torno a `mod-playerbots`. Plugin para ver
cuántos bots hay por nivel y zona, activar/desactivar grupos de bots aleatorios y editar los
parámetros más usados de `playerbots.conf` con explicación (en vez del editor de texto de
`modules_manager`), aplicando con `reload config` cuando se pueda.

**P-7 · Eventos y calendario — P3, M.** Programar cosas con fecha: activar XP doble
(`mod-weekend-xp`), anuncios recurrentes (`.announce`), eventos de juego (`game_event`), el reinicio
programado de F3. Una sola vista de "qué va a pasar esta semana".

**P-8 · Arena y rankings — P3, S.** Con `arena_team`, `character_arena_stats` y `log_arena_fights`:
clasificación por temporada y combates recientes. Encaja con la página pública P-4.

## 6. Mejoras a plugins existentes

- **`core_updater`:** comparar un mismo repo entre el perfil de producción y el de pruebas ("Test va
  3 commits por delante de producción en `mod-playerbots`"); ver F7.
- **`db_manager`:** destino remoto (F6); mostrar el espacio total ocupado por backups y el libre en
  disco; prueba de restauración programada.
- **`character_forge`:** además del aviso de `mod-ale`, comprobar que `ALE.ScriptPath` apunta a
  donde el plugin escribe; hoy, si no coincide, el script se escribe en un sitio que ALE no lee sin
  ningún aviso.
- **`metrics_history`:** 7 días de retención es poco para ver tendencias; guardar agregados
  horarios más tiempo (p. ej. 90 días) aparte de las muestras por minuto.
- **`gm_commander`:** filtro "solo jugadores reales" activado por defecto (la lista muestra cientos
  de bots).
- **`modules_manager`:** la detección de `.conf` no compilados compara fechas; exponer en el core
  la lista real de módulos compilados (`.server debug` por SOAP, "List of enabled modules") y usarla
  cuando la instancia esté en marcha.
