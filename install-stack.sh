#!/usr/bin/env bash
set -euo pipefail

STACK_ROOT="$(cd "$(dirname "$0")" && pwd)"
STACK_ENV="${1:-${STACK_ENV:-${STACK_ROOT}/stack.env}}"

if [[ ! -f "${STACK_ENV}" ]]; then
    echo "Missing stack env file: ${STACK_ENV}" >&2
    echo "Copy stack.env.example to stack.env and edit it first." >&2
    exit 1
fi

export STACK_ENV

# shellcheck source=scripts/common.sh
source "${STACK_ROOT}/scripts/common.sh"

require_root
install_system_packages_if_needed

bash "${STACK_ROOT}/scripts/install-waf.sh"
bash "${STACK_ROOT}/scripts/install-bot.sh"

if [[ "${RUN_STACK_CHECK}" == "1" ]]; then
    bash "${STACK_ROOT}/scripts/check-stack.sh"
fi

log "Stack deployment finished."
if [[ -z "${BOT_ENV_FILE}" || ! -f "${BOT_ENV_FILE}" ]]; then
    warn "No real bot env file was copied. Edit ${BOT_INSTALL_DIR}/.env before starting the bot."
fi

