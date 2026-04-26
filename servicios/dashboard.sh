#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/common.sh"

APP_DIR="$ROOT_DIR/DashBoard"
load_env_file "$APP_DIR/.env"

LOG_FILE="${DASHBOARD_LOG_FILE:-$LOGS_DIR/dashboard.log}"
PYTHON_BIN="${DASHBOARD_PYTHON_BIN:-$APP_DIR/.venv/bin/python3}"

cd "$APP_DIR"
run_logged "$LOG_FILE" "$PYTHON_BIN" -u web_app.py
