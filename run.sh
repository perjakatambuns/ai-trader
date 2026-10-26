#!/usr/bin/env bash
set -e

# AI Trading Copilot Server Launcher
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [ -f "./venv/bin/activate" ]; then
    source ./venv/bin/activate
fi

PORT=${PORT:-8000}
HOST=${HOST:-"0.0.0.0"}

echo "=========================================================="
echo "🚀 Starting AI Trading Copilot (HFM MT5 + Web UI)"
echo "📍 Dashboard URL : http://localhost:${PORT}"
echo "👤 Default Login : admin"
echo "🔑 Default Pass  : password123 (configurable in config.json)"
echo "=========================================================="

python -m uvicorn main:app --host "$HOST" --port "$PORT" --reload
