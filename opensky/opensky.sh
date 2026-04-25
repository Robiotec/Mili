#!/bin/bash
# Servicio OpenSky - Tráfico aéreo Ecuador
# Logs guardados en la misma carpeta: opensky.log

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/opensky.log"

exec python3 -u "$SCRIPT_DIR/opensky_fetch.py" >> "$LOG_FILE" 2>&1
