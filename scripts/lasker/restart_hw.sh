#!/usr/bin/env bash
SOCK=$(find /run/user/1000 -name "sway-ipc*.sock" 2>/dev/null | head -1)
if [[ -z "$SOCK" ]]; then
    echo "sway socket not found"
    exit 1
fi
pkill -f "hw_log.py" 2>/dev/null || true
pkill -f "hw_vitals.py" 2>/dev/null || true
sleep 1
SWAYSOCK="$SOCK" swaymsg exec "foot --app-id=foot-log /home/fishhouses/.local/bin/uv run /home/fishhouses/Brian_Code/headwater/scripts/tui/hw_log.py"
SWAYSOCK="$SOCK" swaymsg exec "foot --app-id=foot-vitals /home/fishhouses/.local/bin/uv run /home/fishhouses/Brian_Code/headwater/scripts/tui/hw_vitals.py"
echo "restarted"
