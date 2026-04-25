#!/bin/bash
# Servicio de telemetría MAVLink → API Central
# Logs guardados en la misma carpeta: robiotecTelemetry.log

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/robiotecTelemetry.log"

[ -f "$SCRIPT_DIR/.env" ] && set -a && source "$SCRIPT_DIR/.env" && set +a

exec python3 -u "$SCRIPT_DIR/robiotecTelemetry.py" >> "$LOG_FILE" 2>&1
