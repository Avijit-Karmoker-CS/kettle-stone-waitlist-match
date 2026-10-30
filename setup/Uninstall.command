#!/bin/bash
# Removes the desktop app and the 8:00 task. Does not touch the Data folder.
PL="$HOME/Library/LaunchAgents/com.kettlestone.waitlistmatch.morning.plist"
launchctl unload "$PL" 2>/dev/null; rm -f "$PL"
rm -rf "$HOME/Desktop/Waitlist Match.app"
echo "Desktop app and 8:00 task removed. You can now delete the program folder. Keep a copy of the Data folder if you need the waitlist."
read -n1 -r -p "Press any key to close."
