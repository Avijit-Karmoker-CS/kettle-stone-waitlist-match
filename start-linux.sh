#!/bin/bash
# Linux (or any system with Python 3.10+): opens Waitlist Match in the browser.
# Usage: ./start-linux.sh            open the window
#        ./start-linux.sh --cli      match the openings file in Data
#        ./start-linux.sh --self-check
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3)"
if [ -z "$PY" ]; then echo "Please install Python 3.10 or later (for example: sudo apt install python3)."; exit 1; fi
exec "$PY" "$ROOT/app/main.py" "$@"
