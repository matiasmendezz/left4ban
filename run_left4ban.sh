#!/usr/bin/env bash
set -e

# Left4Ban Linux Launcher
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ -f "$DIR/dist/Left4Ban" ]; then
    echo "[Left4Ban] Launching standalone binary..."
    chmod +x "$DIR/dist/Left4Ban"
    exec "$DIR/dist/Left4Ban"
fi

if [ -d "$DIR/.venv" ]; then
    PYTHON="$DIR/.venv/bin/python"
elif [ -d "$DIR/venv" ]; then
    PYTHON="$DIR/venv/bin/python"
else
    PYTHON="python3"
fi

echo "[Left4Ban] Starting Left 4 Ban web application..."
exec "$PYTHON" app.py
