#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/common.sh"

APP_DIR="$ROOT_DIR/ApiCentral"
load_env_file "$APP_DIR/.env"

LOG_FILE="${API_LOG_FILE:-$LOGS_DIR/apicentral.log}"
UVICORN_BIN="${APICENTRAL_UVICORN_BIN:-$APP_DIR/.venv/bin/uvicorn}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8004}"

cd "$APP_DIR"
run_logged "$LOG_FILE" "$UVICORN_BIN" app.main:app --host "$API_HOST" --port "$API_PORT"
