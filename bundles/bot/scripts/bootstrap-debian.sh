#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/2874578652/bot.git}"
SRC_DIR="${SRC_DIR:-/opt/src/wafbot}"
BRANCH="${BRANCH:-main}"

if [[ $EUID -ne 0 ]]; then
    echo "请使用 root 或 sudo 执行此脚本。" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git python3 python3-venv python3-pip

mkdir -p "$(dirname "$SRC_DIR")"
if [[ -d "$SRC_DIR/.git" ]]; then
    git -C "$SRC_DIR" fetch origin
    git -C "$SRC_DIR" checkout "$BRANCH"
    git -C "$SRC_DIR" pull --ff-only origin "$BRANCH"
else
    git clone --branch "$BRANCH" "$REPO_URL" "$SRC_DIR"
fi

cd "$SRC_DIR"
bash wafbot.sh install

echo
echo "Next steps:"
echo "1. cp /opt/wafbot/.env.example /opt/wafbot/.env"
echo "2. edit /opt/wafbot/.env with BOT_TOKEN and chat/user IDs"
echo "3. systemctl restart wafbot && systemctl status wafbot --no-pager"
