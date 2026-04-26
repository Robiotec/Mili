#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS_DIR="$ROOT_DIR/servicios/logs"

load_env_file() {
  local env_file="$1"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
}

run_logged() {
  local log_file="$1"
  shift

  mkdir -p "$LOGS_DIR"
  mkdir -p "$(dirname "$log_file")"
  touch "$log_file"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') - starting $* ===" >> "$log_file"
  exec "$@" >> "$log_file" 2>&1
}
