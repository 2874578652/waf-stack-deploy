"""ModSecurity WAF mode management (On/Off/DetectionOnly)."""

import re
import logging
from pathlib import Path

from . import config
from .ip_manager import reload_nginx

logger = logging.getLogger(__name__)

STATE_ON = "On"
STATE_OFF = "Off"
STATE_DETECT = "DetectionOnly"


def get_waf_state() -> str:
    path = Path(config.MODSEC_CONF)
    if not path.exists():
        return "unknown"
    text = path.read_text()
    match = re.search(r'^\s*SecRuleEngine\s+(\S+)', text, re.MULTILINE | re.IGNORECASE)
    if match:
        return match.group(1)
    return "unknown"


def set_waf_state(state: str) -> tuple[bool, str]:
    if state not in (STATE_ON, STATE_OFF, STATE_DETECT):
        return False, f"无效状态 <code>{state}</code>，请使用 On、Off 或 DetectionOnly。"

    path = Path(config.MODSEC_CONF)
    if not path.exists():
        return False, f"配置文件不存在: <code>{config.MODSEC_CONF}</code>"

    text = path.read_text()
    if re.search(r'^\s*SecRuleEngine\s+\S+', text, re.MULTILINE | re.IGNORECASE):
        new_text = re.sub(
            r'^(\s*SecRuleEngine\s+)\S+',
            lambda m: m.group(1) + state,
            text,
            count=1,
            flags=re.MULTILINE | re.IGNORECASE
        )
    else:
        new_text = text.rstrip() + f"\nSecRuleEngine {state}\n"

    path.write_text(new_text)

    # Test nginx config before reloading, rollback on failure
    from .ip_manager import _nginx_test
    ok, err = _nginx_test()
    if not ok:
        path.write_text(text)
        logger.error(f"nginx -t failed after setting WAF state to {state}: {err}")
        return False, f"❌ nginx 配置检查失败，已回滚。\n<pre>{err[:300]}</pre>"

    ok, msg = reload_nginx()
    if ok:
        return True, f"✅ WAF 模式已设置为 <b>{state}</b>，{config.NGINX_SERVICE} 已重载。"
    return False, f"WAF 模式已设置为 <b>{state}</b>，但 {config.NGINX_SERVICE} 重载失败: {msg}"


def waf_status_text() -> str:
    state = get_waf_state()
    emoji = {
        STATE_ON: "🟢",
        STATE_OFF: "🔴",
        STATE_DETECT: "🟡",
    }.get(state, "⚪")
    labels = {
        STATE_ON: "启用 (拦截模式)",
        STATE_OFF: "关闭",
        STATE_DETECT: "观察模式 (仅检测)",
    }
    label = labels.get(state, state)
    return f"{emoji} WAF 当前状态: <b>{label}</b>"
