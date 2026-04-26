#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/common.sh"

APP_DIR="$ROOT_DIR/arcom"
load_env_file "$APP_DIR/.env"

LOG_FILE="${ARCOM_LOG_FILE:-$LOGS_DIR/arcom_update.log}"

cd "$APP_DIR"
run_logged "$LOG_FILE" python3 -u download_arcom.py
