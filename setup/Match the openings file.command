#!/bin/bash
# Matches every opening in the late-openings file in the Data folder; saves Data/reports/matches.csv.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$(uname -m)" = "arm64" ]; then PY="$ROOT/python/mac-arm64/bin/python3.12"; else PY="$ROOT/python/mac-x64/bin/python3.12"; fi
[ -x "$PY" ] || PY="$(command -v python3)"
if [ -z "$PY" ]; then echo "Python was not found. Use the Mac download of Waitlist Match, which includes Python."; read -n1 -r -p "Press any key to close."; exit 1; fi
"$PY" "$ROOT/app/main.py" --cli
echo
read -n1 -r -p "Press any key to close."
