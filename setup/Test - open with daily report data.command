#!/bin/bash
# Opens the program on the DAILY REPORT test data as if it were 8:05 on Fri Oct 30, 2026.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$(uname -m)" = "arm64" ]; then PY="$ROOT/python/mac-arm64/bin/python3.12"; else PY="$ROOT/python/mac-x64/bin/python3.12"; fi
[ -x "$PY" ] || PY="$(command -v python3)"
if [ -z "$PY" ]; then echo "Python was not found. Use the Mac download of Waitlist Match, which includes Python."; read -n1 -r -p "Press any key to close."; exit 1; fi
nohup "$PY" "$ROOT/app/main.py" --data "$ROOT/Test data/Daily report" --now 2026-10-30T08:05 >/dev/null 2>&1 &
echo "Waitlist Match (daily report test) is opening. You can close this window."
