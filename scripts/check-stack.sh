#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_root

if [[ -x "${WAF_SRC_DIR}/scripts/verify.sh" ]]; then
    log "Re-running WAF verify script."
    bash "${WAF_SRC_DIR}/scripts/verify.sh"
fi

log "Running nginx -t"
"${NGINX_BIN}" -t

if [[ -d "${BOT_INSTALL_DIR}/wafbot" && -x "${BOT_INSTALL_DIR}/venv/bin/python3" ]]; then
    log "Running bot Python compile check."
    "${BOT_INSTALL_DIR}/venv/bin/python3" -m py_compile \
        "${BOT_INSTALL_DIR}/run.py" \
        "${BOT_INSTALL_DIR}"/wafbot/*.py
fi

log "Nginx service status:"
systemctl --no-pager --full status "${NGINX_SERVICE}" || true

log "Bot service status:"
systemctl --no-pager --full status "${BOT_SERVICE_NAME}" || true

log "Stack checks finished."

