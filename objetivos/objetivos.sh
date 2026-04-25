#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export OBJETIVOS_DIR="${OBJETIVOS_DIR:-$ROOT_DIR}"
export OBJETIVO_ID="${OBJETIVO_ID:-DRONE}"
export OBJETIVO_API_URL="${OBJETIVO_API_URL:-http://45.32.167.86:8004/objetivo/${OBJETIVO_ID}/}"

exec python3 "$ROOT_DIR/objetivos_service.py"
