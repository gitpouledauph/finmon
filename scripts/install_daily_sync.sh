#!/bin/zsh
# Installe une tâche launchd qui, chaque jour à 7h30,
# met à jour cours + taux de change (aucune connexion aux banques ni aux courtiers).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/local.finmon.sync.plist"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.finmon.sync</string>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>ProgramArguments</key><array>
    <string>$ROOT/.venv-finmon/bin/python</string><string>-m</string><string>finmon</string>
    <string>prices</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>$ROOT/data/sync.log</string>
  <key>StandardErrorPath</key><string>$ROOT/data/sync.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Tâche installée : $PLIST (désinstaller : launchctl unload \"$PLIST\" && rm \"$PLIST\")"
