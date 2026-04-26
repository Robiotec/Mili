#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/common.sh"

APP_DIR="$ROOT_DIR/objetivos"
load_env_file "$APP_DIR/.env"

export OBJETIVOS_DIR="${OBJETIVOS_DIR:-$APP_DIR}"
LOG_FILE="${OBJETIVOS_LOG_FILE:-$LOGS_DIR/objetivos.log}"

cd "$APP_DIR"
run_logged "$LOG_FILE" python3 -u objetivos_service.py
