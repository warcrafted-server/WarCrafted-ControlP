#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source .venv/bin/activate

set -a
[ -f .env ] && source .env
set +a

# Relanza el panel solo si se cierra por su cuenta (p.ej. tras autoactualizarse);
# con Ctrl+C el trap corta el bucle en vez de reiniciar.
set +e
stop=0
trap 'stop=1; kill "$child" 2>/dev/null' INT TERM

while [ "$stop" -eq 0 ]; do
  uvicorn app.main:app --host "${APP_HOST:-0.0.0.0}" --port "${APP_PORT:-8000}" --proxy-headers --forwarded-allow-ips 127.0.0.1 &
  child=$!
  wait "$child"
  if [ "$stop" -eq 0 ]; then
    echo "El panel se detuvo; reiniciando en 2s... (Ctrl+C para salir)"
    sleep 2
  fi
done
