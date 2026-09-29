#!/bin/bash
set -euo pipefail
LABEL="${HOMEPAGE_LABEL:-local.homepage}"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed $LABEL"
