#!/bin/zsh
LABEL=com.benefron.leuven-sniper
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed."
