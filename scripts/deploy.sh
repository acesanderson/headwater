#!/usr/bin/env bash
# Deploy headwater code changes to remote servers.
#
# Usage:
#   ./scripts/deploy.sh [--no-push] [--sync-deps] [caruana|alphablue|botvinnik|lasker|all]
#
# Targets:
#   caruana   — headwaterrouter (8081) + bywater (8080)
#   alphablue — deepwater (8080)
#   botvinnik — backwater (8080)
#   lasker    — hw_log + hw_vitals + headwater-dash (no /ping check)
#   all       — all four (default)
#
# Flags:
#   --no-push    skip the local "git push to origin"; just pull on remotes
#   --sync-deps  run `uv sync` on the remote after pulling (needed when
#                pyproject.toml or uv.lock changed; skipped by default).
#                Not applied to lasker.
#
# Auth: SSH-based git auth.
#   - Each host's repo must have origin set to the SSH URL
#     (git@github.com:acesanderson/headwater.git).
#   - Each host loads middlegame via keychain in ~/.bash_profile.
#   - Remote git/uv invocations are wrapped in `bash -lc` so the
#     keychain-managed ssh-agent and ~/.local/bin are visible.
#
# Precondition: the repo must already be cloned on each target host at the
# paths listed in REMOTE_REPO below. This script does NOT clone — the human
# clones manually as a one-time bootstrap per host.

set -euo pipefail

LOCAL_REPO="$HOME/Brian_Code/headwater"
SERVER_SUBDIR="headwater-server"
SSH_CLONE_URL="git@github.com:acesanderson/headwater.git"

declare -A REMOTE_REPO=(
    [caruana]="/home/bianders/Brian_Code/headwater"
    [alphablue]="/home/fishhouses/Brian_Code/headwater"
    [botvinnik]="/home/fishhouses/Brian_Code/headwater"
    [lasker]="/home/fishhouses/Brian_Code/headwater"
)

# --- parse args ---
NO_PUSH=0
SYNC_DEPS=0
TARGET="all"

for arg in "$@"; do
    case "$arg" in
        --no-push) NO_PUSH=1 ;;
        --sync-deps) SYNC_DEPS=1 ;;
        caruana|alphablue|botvinnik|lasker|all) TARGET="$arg" ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

case "$TARGET" in
    caruana)   HOSTS=(caruana) ;;
    alphablue) HOSTS=(alphablue) ;;
    botvinnik) HOSTS=(botvinnik) ;;
    lasker)    HOSTS=(lasker) ;;
    all)       HOSTS=(caruana alphablue botvinnik lasker) ;;
esac

# --- preflight: repo cloned on each target ---
for host in "${HOSTS[@]}"; do
    repo="${REMOTE_REPO[$host]}"
    ssh "$host" "test -d $repo/.git" || {
        echo "ERR: cannot verify repo on $host at $repo" >&2
        echo "     Either the host is unreachable, or the repo needs to be cloned:" >&2
        echo "     ssh $host && git clone $SSH_CLONE_URL $repo" >&2
        exit 1
    }
done

# --- preflight: local in sync with origin (skipped under --no-push) ---
if [[ $NO_PUSH -eq 0 ]]; then
    git -C "$LOCAL_REPO" fetch
    local_sha=$(git -C "$LOCAL_REPO" rev-parse HEAD)
    upstream_sha=$(git -C "$LOCAL_REPO" rev-parse '@{u}')
    base_sha=$(git -C "$LOCAL_REPO" merge-base HEAD '@{u}')

    if [[ "$local_sha" == "$upstream_sha" ]]; then
        :
    elif [[ "$base_sha" == "$upstream_sha" ]]; then
        :
    elif [[ "$base_sha" == "$local_sha" ]]; then
        echo "ERR: local is behind origin. Pull first." >&2
        exit 1
    else
        echo "ERR: local and origin have diverged. Reconcile before deploying." >&2
        echo "     local:    $local_sha" >&2
        echo "     upstream: $upstream_sha" >&2
        exit 1
    fi
fi

# --- push ---
if [[ $NO_PUSH -eq 0 ]]; then
    echo "==> pushing to origin..."
    git -C "$LOCAL_REPO" push
else
    echo "==> skipping push (--no-push)"
fi

# --- helpers ---
remote_deploy() {
    local host="$1"; shift
    local services=("$@")
    local port
    local repo="${REMOTE_REPO[$host]}"

    echo "==> [$host] pulling code..."
    ssh "$host" "bash -lc 'git -C $repo pull --ff-only'"

    if [[ "$SYNC_DEPS" -eq 1 ]]; then
        echo "==> [$host] syncing deps..."
        ssh "$host" "bash -lc 'cd $repo/$SERVER_SUBDIR && uv sync'"
    fi

    for svc in "${services[@]}"; do
        echo "==> [$host] restarting $svc..."
        ssh "$host" "sudo systemctl restart $svc"
    done

    for svc in "${services[@]}"; do
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

lasker_deploy() {
    local repo="${REMOTE_REPO[lasker]}"
    echo "==> [lasker] pulling code..."
    ssh lasker "bash -lc 'git -C $repo pull --ff-only'"
    echo "==> [lasker] restarting hw_log + hw_vitals..."
    ssh lasker "bash $repo/scripts/lasker/restart_hw.sh"
    echo "==> [lasker] restarting headwater-dash..."
    ssh lasker "sudo systemctl restart headwater-dash"
}

# --- deploy ---
for host in "${HOSTS[@]}"; do
    case "$host" in
        caruana)   remote_deploy caruana headwaterrouter bywater ;;
        alphablue) remote_deploy alphablue deepwater ;;
        botvinnik) remote_deploy botvinnik backwater ;;
        lasker)    lasker_deploy ;;
    esac
done

# --- verification ---
echo
for host in "${HOSTS[@]}"; do
    repo="${REMOTE_REPO[$host]}"
    sha=$(ssh "$host" "git -C $repo rev-parse --short HEAD")
    echo "==> [$host] now at $sha"
done

echo "==> deploy complete"
