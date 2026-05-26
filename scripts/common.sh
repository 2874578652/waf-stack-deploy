#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${WAF_STACK_COMMON_LOADED:-}" ]]; then
    return 0
fi
export WAF_STACK_COMMON_LOADED=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STACK_ENV="${STACK_ENV:-${STACK_ROOT}/stack.env}"

if [[ ! -f "${STACK_ENV}" ]]; then
    echo "Missing stack env file: ${STACK_ENV}" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "${STACK_ENV}"

: "${WAF_REPO_BRANCH:=main}"
: "${BOT_REPO_BRANCH:=main}"
: "${WAF_SRC_DIR:=/opt/src/waf}"
: "${BOT_SRC_DIR:=/opt/src/wafbot}"
: "${WAF_INSTALL_NGINX_DIR:=/etc/nginx}"
: "${WAF_INSTALL_MODSEC_DIR:=/etc/nginx/modsec}"
: "${BOT_INSTALL_DIR:=/opt/wafbot}"
: "${NGINX_SERVICE:=nginx}"
: "${NGINX_BIN:=nginx}"
: "${BOT_SERVICE_NAME:=wafbot}"
: "${INSTALL_SYSTEM_PACKAGES:=1}"
: "${SYSTEM_PACKAGES:=ca-certificates curl git rsync nginx python3 python3-venv python3-pip libnginx-mod-http-modsecurity}"
: "${INSTALL_CRS:=1}"
: "${CRS_REPO_URL:=https://github.com/coreruleset/coreruleset.git}"
: "${CRS_GIT_REF:=v4.24.1}"
: "${CRS_INSTALL_DIR:=/etc/nginx/modsec/coreruleset-4.24.1}"
: "${WAF_BACKUP_ROOT:=/root/waf-stack-backups}"
: "${BOT_ENV_FILE:=}"
: "${BOT_AUTO_START:=1}"
: "${START_NGINX:=1}"
: "${RELOAD_NGINX:=1}"
: "${RUN_STACK_CHECK:=1}"
: "${STACK_RUN_ID:=$(date +%Y%m%d-%H%M%S)}"

log() {
    printf '[INFO] %s\n' "$*"
}

warn() {
    printf '[WARN] %s\n' "$*" >&2
}

die() {
    printf '[ERROR] %s\n' "$*" >&2
    exit 1
}

require_root() {
    [[ "${EUID}" -eq 0 ]] || die "Run this script as root or with sudo."
}

install_system_packages_if_needed() {
    if [[ "${INSTALL_SYSTEM_PACKAGES}" != "1" ]]; then
        log "Skipping package install."
        return 0
    fi

    if ! command -v apt-get >/dev/null 2>&1; then
        die "Only Debian/Ubuntu-style apt-get installs are implemented here."
    fi

    local -a packages
    IFS=' ' read -r -a packages <<< "${SYSTEM_PACKAGES}"

    export DEBIAN_FRONTEND=noninteractive
    log "Installing system packages."
    apt-get update
    apt-get install -y "${packages[@]}"
}

clone_or_update() {
    local repo_url="$1"
    local repo_branch="$2"
    local repo_dir="$3"

    mkdir -p "$(dirname "${repo_dir}")"
    if [[ -d "${repo_dir}/.git" ]]; then
        log "Updating ${repo_dir}"
        git -C "${repo_dir}" fetch origin
        git -C "${repo_dir}" checkout "${repo_branch}"
        git -C "${repo_dir}" pull --ff-only origin "${repo_branch}"
    else
        log "Cloning ${repo_url} into ${repo_dir}"
        git clone --branch "${repo_branch}" "${repo_url}" "${repo_dir}"
    fi
}

backup_path() {
    local src="$1"
    local dest

    [[ -e "${src}" ]] || return 0

    dest="${WAF_BACKUP_ROOT}/${STACK_RUN_ID}${src}"
    mkdir -p "$(dirname "${dest}")"

    if [[ -d "${src}" ]]; then
        rsync -a "${src}/" "${dest}/"
    else
        cp -a "${src}" "${dest}"
    fi

    log "Backed up ${src} -> ${dest}"
}

ensure_crs() {
    if [[ "${INSTALL_CRS}" != "1" ]]; then
        log "Skipping CRS install."
        return 0
    fi

    if [[ -d "${CRS_INSTALL_DIR}/rules" ]]; then
        log "CRS already present at ${CRS_INSTALL_DIR}"
    else
        mkdir -p "$(dirname "${CRS_INSTALL_DIR}")"
        log "Cloning CRS ${CRS_GIT_REF} into ${CRS_INSTALL_DIR}"
        git clone --depth 1 --branch "${CRS_GIT_REF}" "${CRS_REPO_URL}" "${CRS_INSTALL_DIR}"
    fi

    if [[ ! -f "${CRS_INSTALL_DIR}/crs-setup.conf" && -f "${CRS_INSTALL_DIR}/crs-setup.conf.example" ]]; then
        cp -a "${CRS_INSTALL_DIR}/crs-setup.conf.example" "${CRS_INSTALL_DIR}/crs-setup.conf"
        log "Initialized ${CRS_INSTALL_DIR}/crs-setup.conf from example."
    fi
}

