1#!/bin/bash
# Servicio de telemetría MAVLink → API Central
# Logs guardados en la misma carpeta: robiotecTelemetry.log

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/robiotecTelemetry.log"

exec python3 -u "$SCRIPT_DIR/robiotecTelemetry.py" >> "$LOG_FILE" 2>&1
