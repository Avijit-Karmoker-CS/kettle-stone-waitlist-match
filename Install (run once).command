#!/bin/bash
# Kettle & Stone Waitlist Match - one-time setup on a Mac.
# Adds "Waitlist Match" to the Desktop, sets the morning list for 8:00 on weekdays,
# and runs the self-check. Nothing is downloaded and nothing is sent anywhere.
ROOT="$(cd "$(dirname "$0")" && pwd)"
echo ""
echo "Setting up Waitlist Match in: $ROOT"
# Files from a download are marked "from the internet". Clear that mark for this folder.
xattr -dr com.apple.quarantine "$ROOT" 2>/dev/null
chmod +x "$ROOT"/*.command "$ROOT"/setup/*.command "$ROOT"/python/mac-*/bin/python3.12 2>/dev/null
if [ "$(uname -m)" = "arm64" ]; then PY="$ROOT/python/mac-arm64/bin/python3.12"; else PY="$ROOT/python/mac-x64/bin/python3.12"; fi
[ -x "$PY" ] || PY="$(command -v python3)"
if [ -z "$PY" ]; then echo "Python was not found. Use the full download of Waitlist Match, which includes Python."; read -n1 -r -p "Press any key to close."; exit 1; fi

# 1. Desktop app
APP="$HOME/Desktop/Waitlist Match.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$ROOT/app/waitlist_match/ui/icon.icns" "$APP/Contents/Resources/icon.icns"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Waitlist Match</string>
<key>CFBundleIdentifier</key><string>com.kettlestone.waitlistmatch</string>
<key>CFBundleExecutable</key><string>waitlist-match</string>
<key>CFBundleIconFile</key><string>icon</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
</dict></plist>
PLIST
printf '#!/bin/bash\nexec "%s" "%s/app/main.py" "$@"\n' "$PY" "$ROOT" > "$APP/Contents/MacOS/waitlist-match"
chmod +x "$APP/Contents/MacOS/waitlist-match"
echo "  - Desktop app added: Waitlist Match"

# 2. Morning list at 8:00, Monday to Friday
esc() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
PL="$HOME/Library/LaunchAgents/com.kettlestone.waitlistmatch.morning.plist"
mkdir -p "$HOME/Library/LaunchAgents"
{
  echo '<?xml version="1.0" encoding="UTF-8"?>'
  echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
  echo '<plist version="1.0"><dict>'
  echo '<key>Label</key><string>com.kettlestone.waitlistmatch.morning</string>'
  echo "<key>ProgramArguments</key><array><string>$(esc "$PY")</string><string>$(esc "$ROOT/app/main.py")</string><string>--morning</string></array>"
  echo "<key>WorkingDirectory</key><string>$(esc "$ROOT")</string>"
  echo '<key>StartCalendarInterval</key><array>'
  for d in 1 2 3 4 5; do echo "<dict><key>Weekday</key><integer>$d</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>"; done
  echo '</array></dict></plist>'
} > "$PL"
launchctl unload "$PL" 2>/dev/null
if launchctl load "$PL" 2>/dev/null; then echo "  - Morning list set for 8:00, Monday to Friday"; else echo "  - Could not add the 8:00 task. The program still works from the Desktop app."; fi

# 3. Self-check
echo ""
echo "Self-check:"
"$PY" "$ROOT/app/main.py" --self-check
echo ""
echo "Done. Double-click 'Waitlist Match' on the Desktop to start."
read -n1 -r -p "Press any key to close."
