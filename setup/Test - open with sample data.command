#!/bin/bash
# Opens the program on the SAMPLE data as if today were Fri Oct 30, 2026. Does not touch the real Data folder.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$(uname -m)" = "arm64" ]; then PY="$ROOT/python/mac-arm64/bin/python3.12"; else PY="$ROOT/python/mac-x64/bin/python3.12"; fi
[ -x "$PY" ] || PY="$(command -v python3)"
if [ -z "$PY" ]; then echo "Python was not found. Use the Mac download of Waitlist Match, which includes Python."; read -n1 -r -p "Press any key to close."; exit 1; fi
nohup "$PY" "$ROOT/app/main.py" --data "$ROOT/Sample data" --today 2026-10-30 >/dev/null 2>&1 &
echo "Waitlist Match (sample data) is opening. You can close this window."
