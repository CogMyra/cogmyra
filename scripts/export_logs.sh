cat > ~/Library/LaunchAgents/com.cogmyra.export-logs.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key> <string>com.cogmyra.export-logs</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>~/cogmyra-dev/scripts/export_logs.sh</string>
  </array>

  <!-- Run once when loaded, then every hour at minute 5 -->
  <key>RunAtLoad</key> <true/>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Minute</key> <integer>5</integer>
  </dict>

  <key>StandardOutPath</key> <string>/tmp/com.cogmyra.export-logs.out</string>
  <key>StandardErrorPath</key> <string>/tmp/com.cogmyra.export-logs.err</string>
  <key>KeepAlive</key> <false/>
</dict>
</plist>
PLIST

chmod 600 ~/Library/LaunchAgents/com.cogmyra.export-logs.plist
