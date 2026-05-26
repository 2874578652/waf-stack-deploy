#!/usr/bin/env bash
set -euo pipefail

APP_NAME="wafbot"
INSTALL_DIR="/opt/${APP_NAME}"
VENV_DIR="${INSTALL_DIR}/venv"
SERVICE_FILE="${APP_NAME}.service"
SYSTEMD_DIR="/etc/systemd/system"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

need_root() {
    [[ $EUID -eq 0 ]] || error "请使用 root 用户或 sudo 执行此操作。"
}

script_dir() {
    cd "$(dirname "$0")" && pwd
}

copy_project_files() {
    local src
    src="$(script_dir)"
    mkdir -p "${INSTALL_DIR}"

    cp -a "${src}/run.py" "${INSTALL_DIR}/run.py"
    cp -a "${src}/requirements.txt" "${INSTALL_DIR}/requirements.txt"
    cp -a "${src}/cc_status.sh" "${INSTALL_DIR}/cc_status.sh"
    cp -a "${src}/wafbot.service" "${INSTALL_DIR}/wafbot.service"
    cp -a "${src}/README.md" "${INSTALL_DIR}/README.md"
    rm -rf "${INSTALL_DIR}/wafbot"
    cp -a "${src}/wafbot" "${INSTALL_DIR}/wafbot"

    if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
        cp -a "${src}/.env.example" "${INSTALL_DIR}/.env"
        info "已生成默认配置文件 ${INSTALL_DIR}/.env"
    fi
    cp -a "${src}/.env.example" "${INSTALL_DIR}/.env.example"
    chmod +x "${INSTALL_DIR}/cc_status.sh"
}

install_python_deps() {
    if [[ ! -d "${VENV_DIR}" ]]; then
        info "创建 Python 虚拟环境 ..."
        python3 -m venv "${VENV_DIR}"
    fi
    info "安装 Python 依赖 ..."
    "${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null
    "${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
}

sync_cc_whitelist_if_possible() {
    if [[ -f "${INSTALL_DIR}/.env" ]]; then
        if "${VENV_DIR}/bin/python3" -m wafbot.whitelist_sync >/tmp/wafbot-whitelist-sync.log 2>&1; then
            info "已同步 CC 白名单 include。"
        else
            warn "CC 白名单同步跳过或失败，可稍后手动执行: ${VENV_DIR}/bin/python3 -m wafbot.whitelist_sync"
            warn "详情见 /tmp/wafbot-whitelist-sync.log"
        fi
    fi
}

install_service() {
    cp -a "${INSTALL_DIR}/${SERVICE_FILE}" "${SYSTEMD_DIR}/${SERVICE_FILE}"
    systemctl daemon-reload
    systemctl enable "${APP_NAME}" >/dev/null
}

do_install() {
    need_root
    info "开始安装 ${APP_NAME} ..."
    copy_project_files
    install_python_deps
    sync_cc_whitelist_if_possible
    install_service
    info "安装完成。"
    warn "请检查 ${INSTALL_DIR}/.env 后执行: systemctl restart ${APP_NAME}"
}

do_uninstall() {
    need_root
    info "开始卸载 ${APP_NAME} ..."

    if systemctl is-active --quiet "${APP_NAME}" 2>/dev/null; then
        systemctl stop "${APP_NAME}"
    fi
    systemctl disable "${APP_NAME}" 2>/dev/null || true
    rm -f "${SYSTEMD_DIR}/${SERVICE_FILE}"
    systemctl daemon-reload

    read -rp "是否删除 ${INSTALL_DIR} ？(y/N) " confirm
    if [[ "${confirm}" =~ ^[Yy]$ ]]; then
        rm -rf "${INSTALL_DIR}"
        info "已删除 ${INSTALL_DIR}"
    else
        info "保留 ${INSTALL_DIR}"
    fi

    info "卸载完成。"
}

do_start() {
    need_root
    [[ -f "${SYSTEMD_DIR}/${SERVICE_FILE}" ]] || error "服务未安装，请先执行: $0 install"
    systemctl start "${APP_NAME}"
    info "${APP_NAME} 已启动。"
}

do_stop() {
    need_root
    systemctl stop "${APP_NAME}"
    info "${APP_NAME} 已停止。"
}

do_restart() {
    need_root
    systemctl restart "${APP_NAME}"
    info "${APP_NAME} 已重启。"
}

do_status() {
    systemctl status "${APP_NAME}" --no-pager || true
}

do_logs() {
    journalctl -u "${APP_NAME}" -f --no-pager
}

do_update() {
    need_root
    local src
    src="$(script_dir)"
    info "更新 ${APP_NAME} ..."
    if [[ -d "${src}/.git" ]]; then
        git -C "${src}" pull --ff-only || error "git pull 失败，请先处理仓库状态。"
    fi
    copy_project_files
    install_python_deps
    sync_cc_whitelist_if_possible
    install_service
    systemctl restart "${APP_NAME}"
    info "更新完成，服务已重启。"
}

usage() {
    echo "用法: $0 {install|uninstall|start|stop|restart|status|logs|update}"
}

case "${1:-}" in
    install)    do_install   ;;
    uninstall)  do_uninstall ;;
    start)      do_start     ;;
    stop)       do_stop      ;;
    restart)    do_restart   ;;
    status)     do_status    ;;
    logs)       do_logs      ;;
    update)     do_update    ;;
    *)          usage        ;;
esac
