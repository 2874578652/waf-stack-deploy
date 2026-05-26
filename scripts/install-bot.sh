#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_root

clone_or_update "${BOT_REPO_URL}" "${BOT_REPO_BRANCH}" "${BOT_SRC_DIR}"

backup_path "${BOT_INSTALL_DIR}"
backup_path "/etc/systemd/system/${BOT_SERVICE_NAME}.service"

log "Installing bot from ${BOT_SRC_DIR}"
bash "${BOT_SRC_DIR}/wafbot.sh" install

if [[ -n "${BOT_ENV_FILE}" ]]; then
    if [[ -f "${BOT_ENV_FILE}" ]]; then
        cp -a "${BOT_ENV_FILE}" "${BOT_INSTALL_DIR}/.env"
        chmod 600 "${BOT_INSTALL_DIR}/.env"
        log "Copied real bot env file into ${BOT_INSTALL_DIR}/.env"
    else
        warn "BOT_ENV_FILE is set but missing: ${BOT_ENV_FILE}"
    fi
else
    warn "BOT_ENV_FILE is empty; using template env until you replace it."
fi

if [[ "${BOT_AUTO_START}" == "1" && -f "${BOT_INSTALL_DIR}/.env" ]]; then
    systemctl restart "${BOT_SERVICE_NAME}"
fi

log "Bot install step complete."

