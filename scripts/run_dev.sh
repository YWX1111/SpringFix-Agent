#!/usr/bin/env bash
# SpringFix Agent dev launcher (WSL / Linux / macOS)
# Usage:
#   ./scripts/run_dev.sh
# Prerequisites:
#   uv sync

set -euo pipefail

echo "[run_dev] Starting SpringFix Agent (M0)..."

# Ensure dependencies are synced
if ! uv sync --extra dev > /dev/null 2>&1; then
    echo "[run_dev] uv sync failed" >&2
    exit 1
fi

# Load HOST/PORT from .env if present, fallback to defaults
HOST="0.0.0.0"
PORT="8000"
if [ -f ".env" ]; then
    while IFS='=' read -r key value; do
        case "$key" in
            HOST) HOST="$value" ;;
            PORT) PORT="$value" ;;
        esac
    done < ".env"
fi

echo "[run_dev] Listening on http://${HOST}:${PORT}"
echo "[run_dev] Health: http://localhost:${PORT}/api/v1/health"
echo "[run_dev] Docs:    http://localhost:${PORT}/docs"

exec uv run uvicorn springfix_agent.main:app --host "${HOST}" --port "${PORT}" --reload
