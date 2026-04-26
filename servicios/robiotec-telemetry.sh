#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/common.sh"

APP_DIR="$ROOT_DIR/robiotecTelemetry"
load_env_file "$APP_DIR/.env"

LOG_FILE="${TELEMETRY_LOG_FILE:-$LOGS_DIR/robiotec-telemetry.log}"

cd "$APP_DIR"
run_logged "$LOG_FILE" python3 -u robiotecTelemetry.py
