#!/usr/bin/env bash
# Deploy headwater code changes to remote servers.
#
# Usage:
#   ./scripts/deploy.sh [--sync-deps] [caruana|alphablue|botvinnik|lasker|all]
#
# Targets:
#   caruana   — headwaterrouter (8081) + bywater (8080)
#   alphablue — deepwater (8080)
#   botvinnik — backwater (8080)
#   lasker    — git pull only (no services)
#   all       — all four (default)
#
# --sync-deps: run `uv sync` on the remote after pulling (needed when
#              pyproject.toml or uv.lock changed; skipped by default)

set -euo pipefail

LOCAL_REPO="$HOME/Brian_Code/headwater"
SERVER_SUBDIR="headwater-server"

declare -A REMOTE_REPO=(
    [caruana]="/home/bianders/Brian_Code/headwater"
    [alphablue]="/home/fishhouses/Brian_Code/headwater"
    [botvinnik]="/home/fishhouses/Brian_Code/headwater"
    [lasker]="/home/fishhouses/Brian_Code/headwater"
)

# --- parse args ---
SYNC_DEPS=0
TARGET="all"

for arg in "$@"; do
    case "$arg" in
        --sync-deps) SYNC_DEPS=1 ;;
        caruana|alphablue|botvinnik|lasker|all) TARGET="$arg" ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# --- helpers ---
remote_deploy() {
    local host="$1"; shift
    local services=("$@")
    local port
    local repo="${REMOTE_REPO[$host]}"

    echo "==> [$host] pulling code..."
    ssh "$host" "git -C $repo pull --ff-only https://${GITHUB_PERSONAL_TOKEN}@github.com/acesanderson/headwater.git"

    if [[ "$SYNC_DEPS" -eq 1 ]]; then
        echo "==> [$host] syncing deps..."
        ssh "$host" "cd $repo/$SERVER_SUBDIR && uv sync"
    fi

    for svc in "${services[@]}"; do
        echo "==> [$host] restarting $svc..."
        ssh "$host" "sudo systemctl restart $svc"
    done

    for svc in "${services[@]}"; do
        # derive port from service name
        case "$svc" in
            headwaterrouter) port=8081 ;;
            *) port=8080 ;;
        esac
        echo -n "==> [$host] waiting for $svc on :$port ... "
        for i in $(seq 1 20); do
            if ssh "$host" "curl -sf http://localhost:$port/ping" > /dev/null 2>&1; then
                echo "up"
                break
            fi
            if [[ $i -eq 20 ]]; then
                echo "TIMEOUT after 20s"
                echo "    journalctl -u $svc -n 30 on $host for details"
                exit 1
            fi
            sleep 1
        done
    done
}

lasker_pull() {
    local repo="${REMOTE_REPO[lasker]}"
    echo "==> [lasker] pulling code..."
    ssh lasker "git -C $repo pull --ff-only https://${GITHUB_PERSONAL_TOKEN}@github.com/acesanderson/headwater.git"
    echo "==> [lasker] restarting hw_log + hw_vitals..."
    ssh lasker "bash $repo/scripts/lasker/restart_hw.sh"
    echo "==> [lasker] restarting headwater-dash..."
    ssh lasker "sudo systemctl restart headwater-dash"
}

# --- push local changes first ---
echo "==> pushing to origin..."
git -C "$LOCAL_REPO" push

# --- deploy ---
case "$TARGET" in
    caruana)
        remote_deploy caruana headwaterrouter bywater
        ;;
    alphablue)
        remote_deploy alphablue deepwater
        ;;
    botvinnik)
        remote_deploy botvinnik backwater
        ;;
    lasker)
        lasker_pull
        ;;
    all)
        remote_deploy caruana headwaterrouter bywater
        remote_deploy alphablue deepwater
        remote_deploy botvinnik backwater
        lasker_pull
        ;;
esac

echo "==> deploy complete"
