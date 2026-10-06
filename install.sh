#!/bin/zsh
# Validates .env, then installs and starts the launchd job (every 5 min while the Mac is awake).
set -e
cd "$(dirname "$0")"
DIR="$PWD"
set -a; source ./.env; set +a
for v in FIRST_NAME LAST_NAME DOB EMAIL NTFY_TOPIC; do
  [ -n "${(P)v}" ] || { echo ".env is missing $v"; exit 1; }
done
[ "$DOB" != "DD/MM/YYYY" ] || { echo "Set DOB in .env"; exit 1; }
LABEL=com.benefron.leuven-sniper
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>$DIR/run.sh</string></array>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/snipe.log</string>
  <key>StandardErrorPath</key><string>$DIR/snipe.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. Log: $DIR/snipe.log"
