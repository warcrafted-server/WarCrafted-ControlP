@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo === WarCrafted-ControlP - Instalador (Windows) ===

where python >nul 2>nul
if errorlevel 1 (
    echo Python no esta instalado o no esta en el PATH.
    echo Descargalo desde https://www.python.org/downloads/ y vuelve a ejecutar este script.
    exit /b 1
)

if not exist ".venv" (
    echo Creando entorno virtual .venv...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Instalando dependencias...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt

if not exist ".env" (
    echo Creando archivo .env a partir de .env.example...
    copy /Y .env.example .env >nul
    for /f "delims=" %%K in ('python -c "import secrets; print(secrets.token_hex(32))"') do set SECRET_KEY=%%K
    powershell -Command "(Get-Content .env) -replace '^SECRET_KEY=.*', 'SECRET_KEY=%SECRET_KEY%' | Set-Content .env"
    echo Se genero una SECRET_KEY aleatoria en .env.
    echo.
    echo === Como se ejecutan los emuladores ===
    echo   1^) Nativo: procesos del propio equipo
    echo   2^) Docker: contenedores de docker compose
    set /p RUNTIME_CHOICE="Elige [1]: "
    if "!RUNTIME_CHOICE!"=="2" (
        where docker >nul 2>nul
        if errorlevel 1 (
            echo Docker no esta instalado; instalalo y cambia APP_RUNTIME en .env.
        ) else (
            docker info >nul 2>nul
            if errorlevel 1 echo Docker no responde; arranca Docker Desktop antes de iniciar el panel.
        )
        powershell -Command "(Get-Content .env) -replace '^# APP_RUNTIME=.*', 'APP_RUNTIME=docker' | Set-Content .env"
        echo APP_RUNTIME=docker. Define INSTANCE_N_DOCKER_SERVICE y INSTANCE_N_DOCKER_PROJECT_DIR por instancia.
    ) else (
        echo APP_RUNTIME=native ^(valor por defecto^).
    )
) else (
    echo .env ya existe, no se sobrescribe.
)

if not exist "data" mkdir data

echo.
echo === Creacion del usuario administrador ===
set /p ADMIN_USER="Usuario administrador [admin]: "
if "%ADMIN_USER%"=="" set ADMIN_USER=admin
set /p ADMIN_PASS="Contrasena: "

python -m app.cli create-admin --username "%ADMIN_USER%" --password "%ADMIN_PASS%"

echo.
echo Instalacion completada.
echo Edita el archivo .env para configurar tus instancias de emulador antes de arrancar.
echo Para iniciar el panel ejecuta: run.bat
