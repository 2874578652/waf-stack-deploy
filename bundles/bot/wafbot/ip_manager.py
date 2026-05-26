"""IP blacklist/whitelist management for ModSecurity WAF."""

import fcntl
import subprocess
import logging
from pathlib import Path

from . import config, whitelist_sync

logger = logging.getLogger(__name__)

_lock_path = Path("/tmp/wafbot_iplist.lock")
_lock_fd = None


class _FileLock:
    """Simple file-based lock for serialising IP list operations."""

    def __enter__(self):
        global _lock_fd
        _lock_fd = open(_lock_path, "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *args):
        global _lock_fd
        if _lock_fd:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
            _lock_fd = None


def _read_list(filepath: str) -> list[str]:
    path = Path(filepath)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def _write_list(filepath: str, ips: list[str]) -> None:
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(ips) + "\n" if ips else "", encoding="utf-8")


def _write_whitelist_source_and_cc_include(ips: list[str]) -> None:
    _write_list(config.IP_WHITELIST, ips)
    whitelist_sync.write_cc_whitelist_include(ips)


def _nginx_test() -> tuple[bool, str]:
    """Run nginx -t to verify config is valid."""
    try:
        result = subprocess.run(
            [config.NGINX_BIN, "-t"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or result.stdout).strip()
    except Exception as e:
        return False, str(e)


def reload_nginx() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["systemctl", "reload", config.NGINX_SERVICE],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return True, f"{config.NGINX_SERVICE} 已重载。"
        return False, (result.stderr or result.stdout).strip()
    except subprocess.TimeoutExpired:
        return False, "nginx 重载超时。"
    except Exception as e:
        return False, str(e)


def _update_list(filepath: str, ip: str, add: bool) -> tuple[bool, str]:
    """Add or remove an IP, test nginx config, rollback on failure."""
    with _FileLock():
        ips = _read_list(filepath)
        original = list(ips)
        is_whitelist = filepath == config.IP_WHITELIST

        if add:
            if ip in ips:
                return False, f"<code>{ip}</code> 已存在，无需重复添加。"
            ips.append(ip)
        else:
            if ip not in ips:
                return False, f"<code>{ip}</code> 不在列表中。"
            ips.remove(ip)

        if is_whitelist:
            _write_whitelist_source_and_cc_include(ips)
        else:
            _write_list(filepath, ips)

        ok, err = _nginx_test()
        if not ok:
            if is_whitelist:
                _write_whitelist_source_and_cc_include(original)
            else:
                _write_list(filepath, original)
            logger.error(f"nginx -t failed after updating {filepath}: {err}")
            return False, f"❌ nginx 配置检查失败，已回滚。\n<pre>{err[:300]}</pre>"

        ok, msg = reload_nginx()
        if ok:
            action = "加入" if add else "移除"
            list_name = "黑名单" if "black" in filepath else "白名单（WAF + CC）"
            return True, f"✅ <code>{ip}</code> 已{action}{list_name}，{msg}"
        return False, f"<code>{ip}</code> 已更新，但 nginx 重载失败: {msg}"


def _clear_list(filepath: str, list_name: str) -> tuple[bool, str]:
    """Clear all IPs from a list file, test nginx and reload."""
    with _FileLock():
        original = _read_list(filepath)
        is_whitelist = filepath == config.IP_WHITELIST
        if is_whitelist:
            _write_whitelist_source_and_cc_include([])
        else:
            _write_list(filepath, [])

        ok, err = _nginx_test()
        if not ok:
            if is_whitelist:
                _write_whitelist_source_and_cc_include(original)
            else:
                _write_list(filepath, original)
            logger.error(f"nginx -t failed after clearing {filepath}: {err}")
            return False, f"❌ nginx 配置检查失败，已回滚。\n<pre>{err[:300]}</pre>"

        ok, msg = reload_nginx()
        if ok:
            return True, f"✅ {list_name}已清空（共移除 {len(original)} 条），{msg}"
        return False, f"{list_name}已清空，但 nginx 重载失败: {msg}"


def add_ip_to_blacklist(ip: str) -> tuple[bool, str]:
    return _update_list(config.IP_BLACKLIST, ip, add=True)


def remove_ip_from_blacklist(ip: str) -> tuple[bool, str]:
    return _update_list(config.IP_BLACKLIST, ip, add=False)


def clear_blacklist() -> tuple[bool, str]:
    return _clear_list(config.IP_BLACKLIST, "黑名单")


def add_ip_to_whitelist(ip: str) -> tuple[bool, str]:
    return _update_list(config.IP_WHITELIST, ip, add=True)


def remove_ip_from_whitelist(ip: str) -> tuple[bool, str]:
    return _update_list(config.IP_WHITELIST, ip, add=False)


def clear_whitelist() -> tuple[bool, str]:
    return _clear_list(config.IP_WHITELIST, "白名单（WAF + CC）")


def list_blacklist() -> str:
    ips = _read_list(config.IP_BLACKLIST)
    if not ips:
        return "黑名单为空。"
    return "🚫 <b>黑名单 IP:</b>\n" + "\n".join(f"• <code>{ip}</code>" for ip in ips)


def list_whitelist() -> str:
    ips = _read_list(config.IP_WHITELIST)
    if not ips:
        return "白名单为空。"
    return "✅ <b>白名单 IP:</b>\n" + "\n".join(f"• <code>{ip}</code>" for ip in ips)
