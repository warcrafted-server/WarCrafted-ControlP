# TODO

## Alta
- Arrancar `ac-produccion` en el VPS y dar nivel GM a la cuenta SOAP en el reino 1 (`account set gmlevel NOMBRE 3 1`).
- Recrear los contenedores para aplicar la rotacion de logs del compose y los limites de los Appender.
- Probar iniciar/detener y desplegar sobre contenedores reales (hasta ahora solo con simulacion y en solo lectura).

## Media
- Pantalla o comando para crear/borrar usuarios del panel (hoy solo `create-admin`).
- Instalar la unidad systemd y el vhost de `deploy/` desde un script (hoy son pasos manuales con sudo).
- Ayuda de `docs/INSTALACION.md` y `docs/USO.md` si INSTALL.md sigue creciendo.

## Descartado
- Otros runtimes (Podman, unidades systemd, Kubernetes): fuera de alcance del plan `runtime-dual`.
