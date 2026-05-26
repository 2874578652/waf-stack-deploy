#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_root

if [[ "${USE_LOCAL_BUNDLES}" == "1" ]]; then
    WAF_BUNDLE_DIR="$(resolve_bundle_dir waf "${WAF_BUNDLE_DIR}")"
    sync_bundle_to_src "${WAF_BUNDLE_DIR}" "${WAF_SRC_DIR}"
else
    clone_or_update "${WAF_REPO_URL}" "${WAF_REPO_BRANCH}" "${WAF_SRC_DIR}"
fi

ensure_crs

if [[ -x "${WAF_SRC_DIR}/scripts/verify.sh" ]]; then
    log "Running WAF repository verify script."
    bash "${WAF_SRC_DIR}/scripts/verify.sh"
fi

backup_path "${WAF_INSTALL_NGINX_DIR}"
backup_path "${WAF_INSTALL_MODSEC_DIR}"

mkdir -p \
    "${WAF_INSTALL_NGINX_DIR}/conf.d" \
    "${WAF_INSTALL_NGINX_DIR}/sites-enabled" \
    "${WAF_INSTALL_NGINX_DIR}/nginxconfig.io" \
    "${WAF_INSTALL_MODSEC_DIR}"

log "Syncing WAF repo into ${WAF_INSTALL_NGINX_DIR} and ${WAF_INSTALL_MODSEC_DIR}"
cp -a "${WAF_SRC_DIR}/nginx/nginx.conf" "${WAF_INSTALL_NGINX_DIR}/nginx.conf"
rsync -a "${WAF_SRC_DIR}/nginx/conf.d/" "${WAF_INSTALL_NGINX_DIR}/conf.d/"
rsync -a "${WAF_SRC_DIR}/nginx/sites-enabled/" "${WAF_INSTALL_NGINX_DIR}/sites-enabled/"
rsync -a "${WAF_SRC_DIR}/nginx/nginxconfig.io/" "${WAF_INSTALL_NGINX_DIR}/nginxconfig.io/"
rsync -a "${WAF_SRC_DIR}/modsec/" "${WAF_INSTALL_MODSEC_DIR}/"

log "Validating nginx configuration."
"${NGINX_BIN}" -t

if [[ "${START_NGINX}" == "1" ]]; then
    systemctl enable "${NGINX_SERVICE}" >/dev/null 2>&1 || true
    if systemctl is-active --quiet "${NGINX_SERVICE}"; then
        if [[ "${RELOAD_NGINX}" == "1" ]]; then
            systemctl reload "${NGINX_SERVICE}"
        fi
    else
        systemctl start "${NGINX_SERVICE}"
    fi
fi

log "WAF install step complete."
