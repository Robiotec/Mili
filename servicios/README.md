# Servicios SVI

Carpeta central de arranque y operación de servicios.

## Scripts principales

- `apicentral.sh`
- `dashboard.sh`
- `objetivos.sh`
- `opensky.sh`
- `robiotec-telemetry.sh`
- `arcom_update.sh`

Cada script:

- carga el `.env` de su carpeta principal
- escribe logs en `servicios/logs/`
- ejecuta el entrypoint real del servicio

## Units systemd

- `apicentral.service`
- `dashboard.service`
- `objetivos.service`
- `opensky.service`
- `robiotec-telemetry.service`
- `arcom_update.service`
- `arcom_update.timer`

## Logs

- `servicios/logs/apicentral.log`
- `servicios/logs/dashboard.log`
- `servicios/logs/objetivos.log`
- `servicios/logs/opensky.log`
- `servicios/logs/robiotec-telemetry.log`
- `servicios/logs/arcom_update.log`
