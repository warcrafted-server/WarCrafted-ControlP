# WarCrafted-ControlP

Panel de control web modular para la gestion remota de multiples emuladores de World of Warcraft (**AzerothCore** estandar y **AzerothCore + Playerbots**).

Permite monitorizar el estado de los procesos, consultar jugadores conectados, iniciar/detener instancias y ejecutar comandos GM en tiempo real desde una interfaz web moderna con tema claro y oscuro.

## Caracteristicas

- **Multi-emulador**: gestiona varias instancias de AzerothCore y AzerothCore + Playerbots desde un unico panel.
- **Arquitectura de drivers extensible**: cada tipo de emulador implementa una interfaz comun (`app/emulators/base.py`), lo que permite anadir nuevos tipos sin tocar el resto de la aplicacion.
- **Consola GM en tiempo real** via WebSocket + Xterm.js, como panel flotante movible y redimensionable, con historial de comandos (↑/↓) y ejecucion via SOAP.
- **Tarjetas de estado**: CPU, RAM y jugadores online por instancia, ademas de estadisticas del host. Cada instancia se identifica por su propio PID y `WORKDIR`, evitando cruces entre instancias que comparten el mismo binario.
- **Autenticacion segura**: usuario/contrasena con hash bcrypt y sesiones JWT en cookie httpOnly.
- **Tema claro/oscuro** intercambiable con un clic, con persistencia en el navegador.
- **Autoinstalacion** multiplataforma (`install.sh` / `install.bat`).

## Stack tecnico

| Capa       | Tecnologia                                  |
|------------|----------------------------------------------|
| Backend    | Python 3.11+, FastAPI, SQLAlchemy, Uvicorn   |
| Frontend   | Jinja2, TailwindCSS, Xterm.js                |
| Auth       | JWT (python-jose), bcrypt (passlib)          |
| Datos      | SQLite (panel), MySQL/MariaDB (emuladores)   |
| Comunicacion en tiempo real | WebSockets                 |
| Comandos GM | SOAP (AzerothCore)                          |

## Estructura del proyecto

```
WarCrafted-ControlP/
├── app/
│   ├── api/          # Routers REST y WebSocket (auth, servers, system, console)
│   ├── emulators/     # Drivers de emulador (base, azerothcore, playerbots) + manager
│   ├── soap/          # Cliente SOAP para comandos GM
│   ├── static/         # CSS y JS del panel
│   ├── templates/      # Vistas Jinja2 (login, dashboard, consola)
│   ├── cli.py           # Herramienta de linea de comandos (crear admin)
│   ├── config.py         # Configuracion (.env)
│   ├── database.py        # Motor SQLAlchemy y sesion
│   ├── main.py             # Aplicacion FastAPI
│   ├── models.py            # Modelos de base de datos
│   ├── schemas.py            # Esquemas Pydantic
│   └── security.py            # Hash de contrasenas y JWT
├── data/                # Base de datos SQLite, PIDs y logs por instancia (no versionada)
├── install.sh / install.bat  # Autoinstalacion Linux / Windows
├── run.sh / run.bat          # Arranque del panel
├── requirements.txt
└── .env.example
```

## Inicio rapido

```bash
git clone <url-del-repositorio>
cd WarCrafted-ControlP
./install.sh          # Linux/Debian/Ubuntu
# o install.bat en Windows
./run.sh               # Arranca el panel en http://localhost:8000
```

Consulta [`INSTALL.md`](INSTALL.md) para el detalle completo de instalacion y configuracion, y [`USER_GUIDE.md`](USER_GUIDE.md) para aprender a usar la interfaz.

## Seguridad

- El archivo `.gitignore` excluye estrictamente `.env`, credenciales, bases de datos locales y cualquier rastro de herramientas de IA.
- Las contrasenas se almacenan con hash bcrypt, nunca en texto plano.
- Las sesiones usan JWT en cookies `httpOnly`; activa `COOKIE_SECURE=true` en `.env` si sirves el panel detras de HTTPS.

## Licencia

**WNCL-P-1.0** — Licencia Privada No Comercial WarCrafted

Copyright © 2025-2026 WarCrafted

Este proyecto es software privado de uso exclusivo. **Solo WarCrafted tiene derecho de uso. Está prohibido:**
- Usar sin autorización escrita explícita de WarCrafted
- Modificar o crear versiones derivadas
- Redistribuir, publicar o compartir con terceros
- Vender, revender o explotar comercialmente el software

Si alguien desea usar este software, debe contactar a WarCrafted para solicitar una licencia específica, que puede estar sujeta a términos y compensación.

Consulta el archivo [`LICENSE`](LICENSE) para el texto legal completo.
