#!/bin/bash
# Install the homepage as a per-user LaunchAgent on port 80.
# macOS (10.14+) lets unprivileged processes bind ports <1024 on all interfaces, so no root is needed.
set -euo pipefail

LABEL="${HOMEPAGE_LABEL:-local.homepage}"
PORT="${HOMEPAGE_PORT:-80}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/homepage.log"
DOMAIN="gui/$(id -u)"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$REPO/server.py</string>
    <string>--port</string>
    <string>$PORT</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>StandardOutPath</key>
  <string>$LOG</string>
  <key>StandardErrorPath</key>
  <string>$LOG</string>
</dict>
</plist>
PLIST
plutil -lint "$PLIST" >/dev/null
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null && sleep 1 || true
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "homepage running: http://$(scutil --get LocalHostName 2>/dev/null || hostname -s).local$([ "$PORT" = 80 ] || echo ":$PORT")/"
