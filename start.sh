#!/bin/bash
set -e

echo "[botmask] Installing package + browser ..."
pip install -e /app -q 2>/dev/null
patchright install chromium 2>/dev/null || true

echo "[botmask] Starting Brave with CDP ..."
exec python3 /app/src/botmask/_boot.py "$@"
