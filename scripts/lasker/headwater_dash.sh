#!/usr/bin/env bash
# Attach to (or create) a shared tmux session serving both TUI dashboards.
# Invoked by ttyd — each browser connection attaches to the same live session.
UV=/home/fishhouses/.local/bin/uv
REPO=/home/fishhouses/Brian_Code/headwater
SESSION=headwater_dash

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux new-session -d -s "$SESSION" \
        "$UV run $REPO/scripts/tui/hw_log.py"
    tmux split-window -h -t "$SESSION" \
        "$UV run $REPO/scripts/tui/hw_vitals.py"
fi

exec tmux attach-session -t "$SESSION"
