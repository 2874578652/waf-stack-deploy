"""ModSecurity WAF Telegram Bot — main entry point."""

import asyncio
import html
import logging
import re
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from . import config
from . import ip_manager
from . import waf_manager
from .log_monitor import LogMonitor

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
audit = logging.getLogger("audit")

CC_STATUS_SCRIPT = "/opt/wafbot/cc_status.sh"
CC_STATUS_DEFAULT_LINES = 20000
CC_STATUS_MIN_LINES = 100
CC_STATUS_MAX_LINES = 50000
CC_STATUS_TIMEOUT = 15


def _audit(update: Update, action: str):
    """Log an audit record: who did what."""
    user = update.effective_user
    if user:
        audit.info(f"[{user.id}] @{user.username or user.full_name} — {action}")
    else:
        audit.info(f"[unknown] — {action}")

# ─── Auth decorator ────────────────────────────────────────────────────────────

READ_ONLY_CALLBACKS = {"menu_cc_status", "menu_main", "menu_recent", "menu_waf", "noop"}


def _is_private_chat(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == "private")


def _is_group_chat(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in {"group", "supergroup"})


def _is_authorized_user(update: Update) -> bool:
    user_id = update.effective_user.id if update.effective_user else None
    return bool(config.ALLOWED_USERS and user_id in config.ALLOWED_USERS)


def _is_allowed_group_chat(update: Update) -> bool:
    chat = update.effective_chat
    if not chat or not _is_group_chat(update):
        return False
    if not config.ALLOWED_GROUPS:
        return True
    return chat.id in config.ALLOWED_GROUPS


def _is_supported_chat(update: Update) -> bool:
    return _is_private_chat(update) or _is_allowed_group_chat(update)


async def _reply_access_denied(update: Update, text: str):
    if update.callback_query:
        await update.callback_query.answer(text, show_alert=True)
    elif update.message:
        await update.message.reply_text(text)


def restricted(func):
    """Only allow users in ALLOWED_USERS to execute the handler."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_supported_chat(update):
            await _reply_access_denied(update, "⛔ 当前聊天未授权使用机器人。")
            return
        if not _is_authorized_user(update):
            await _reply_access_denied(update, "⛔ 仅允许管理员执行该操作。")
            return
        return await func(update, context)
    return wrapper


def group_readable(func):
    """Allow read-only access in allowed groups and admin-only access in private chats."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_supported_chat(update):
            await _reply_access_denied(update, "⛔ 当前聊天未授权使用机器人。")
            return
        if _is_private_chat(update) and not _is_authorized_user(update):
            await _reply_access_denied(update, "⛔ 私聊模式仅允许管理员使用。")
            return
        return await func(update, context)
    return wrapper


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _validate_ip(ip: str) -> bool:
    """Strict IPv4 / IPv4 CIDR validation."""
    ip = ip.strip()
    m = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:/(\d{1,2}))?$', ip)
    if not m:
        return False
    octets = m.group(1).split('.')
    if any(int(o) > 255 or (len(o) > 1 and o[0] == '0') for o in octets):
        return False
    if m.group(2) is not None and int(m.group(2)) > 32:
        return False
    return True


def _admin_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🚫 黑名单管理", callback_data="menu_blacklist"),
            InlineKeyboardButton("✅ 白名单管理", callback_data="menu_whitelist"),
        ],
        [
            InlineKeyboardButton("🛡️ WAF 状态/模式", callback_data="menu_waf"),
            InlineKeyboardButton("📋 最近告警", callback_data="menu_recent"),
        ],
        [
            InlineKeyboardButton("📊 CC 状态", callback_data="menu_cc_status"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def _read_only_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🛡️ WAF 状态", callback_data="menu_waf"),
            InlineKeyboardButton("📋 最近告警", callback_data="menu_recent"),
        ],
        [
            InlineKeyboardButton("📊 CC 状态", callback_data="menu_cc_status"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def _main_menu_payload(can_manage: bool) -> tuple[str, InlineKeyboardMarkup]:
    if can_manage:
        text = (
            "🛡️ <b>ModSecurity WAF 管理机器人</b>\n\n"
            "请从下方菜单选择操作，或直接使用命令:\n\n"
            "<b>IP 管理</b>\n"
            "<code>/blacklist_add &lt;IP&gt;</code> — 加入黑名单\n"
            "<code>/blacklist_del &lt;IP&gt;</code> — 移出黑名单\n"
            "<code>/blacklist</code> — 查看黑名单\n"
            "<code>/blacklist_clear</code> — 清空黑名单\n"
            "<code>/whitelist_add &lt;IP&gt;</code> — 加入白名单\n"
            "<code>/whitelist_del &lt;IP&gt;</code> — 移出白名单\n"
            "<code>/whitelist</code> — 查看白名单\n"
            "<code>/whitelist_clear</code> — 清空白名单\n\n"
            "<b>WAF 控制</b>\n"
            "<code>/waf_status</code> — 查看当前状态\n"
            "<code>/waf_on</code> — 开启拦截模式\n"
            "<code>/waf_off</code> — 关闭 WAF\n"
            "<code>/waf_detect</code> — 开启观察模式\n\n"
            "<b>日志</b>\n"
            "<code>/recent [N]</code> — 最近 N 条告警 (默认5)\n"
            "<code>/cc_status [N]</code> — 查看最近 N 行 CC 命中统计 (默认20000)\n"
        )
        return text, _admin_menu_keyboard()

    text = (
        "🛡️ <b>ModSecurity WAF 只读模式</b>\n\n"
        "当前群可公开查看状态和告警摘要。\n"
        "只有 <code>ALLOWED_USERS</code> 中的管理员用户可以执行拉黑、白名单变更和 WAF 模式切换。\n\n"
        "<b>只读命令</b>\n"
        "<code>/waf_status</code> — 查看当前状态\n"
        "<code>/recent [N]</code> — 最近 N 条告警 (默认5)\n"
        "<code>/cc_status [N]</code> — 查看最近 N 行 CC 命中统计 (默认20000)\n"
    )
    return text, _read_only_menu_keyboard()


# ─── Command: /start /help ──────────────────────────────────────────────────────

@group_readable
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, keyboard = _main_menu_payload(_is_authorized_user(update))
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


# ─── Blacklist commands ─────────────────────────────────────────────────────────

@restricted
async def cmd_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        ip_manager.list_blacklist(), parse_mode=ParseMode.HTML
    )


@restricted
async def cmd_blacklist_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("用法: <code>/blacklist_add &lt;IP&gt;</code>", parse_mode=ParseMode.HTML)
        return
    ip = context.args[0].strip()
    if not _validate_ip(ip):
        await update.message.reply_text(f"❌ 无效的 IP 地址: <code>{ip}</code>", parse_mode=ParseMode.HTML)
        return
    ok, msg = ip_manager.add_ip_to_blacklist(ip)
    _audit(update, f"加入黑名单: {ip}")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


@restricted
async def cmd_blacklist_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("用法: <code>/blacklist_del &lt;IP&gt;</code>", parse_mode=ParseMode.HTML)
        return
    ip = context.args[0].strip()
    if not _validate_ip(ip):
        await update.message.reply_text(f"❌ 无效的 IP 地址: <code>{ip}</code>", parse_mode=ParseMode.HTML)
        return
    ok, msg = ip_manager.remove_ip_from_blacklist(ip)
    _audit(update, f"移出黑名单: {ip}")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# ─── Whitelist commands ─────────────────────────────────────────────────────────

@restricted
async def cmd_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        ip_manager.list_whitelist(), parse_mode=ParseMode.HTML
    )


@restricted
async def cmd_whitelist_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("用法: <code>/whitelist_add &lt;IP&gt;</code>", parse_mode=ParseMode.HTML)
        return
    ip = context.args[0].strip()
    if not _validate_ip(ip):
        await update.message.reply_text(f"❌ 无效的 IP 地址: <code>{ip}</code>", parse_mode=ParseMode.HTML)
        return
    ok, msg = ip_manager.add_ip_to_whitelist(ip)
    _audit(update, f"加入白名单: {ip}")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


@restricted
async def cmd_whitelist_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("用法: <code>/whitelist_del &lt;IP&gt;</code>", parse_mode=ParseMode.HTML)
        return
    ip = context.args[0].strip()
    if not _validate_ip(ip):
        await update.message.reply_text(f"❌ 无效的 IP 地址: <code>{ip}</code>", parse_mode=ParseMode.HTML)
        return
    ok, msg = ip_manager.remove_ip_from_whitelist(ip)
    _audit(update, f"移出白名单: {ip}")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# ─── WAF mode commands ──────────────────────────────────────────────────────────

@group_readable
async def cmd_waf_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        waf_manager.waf_status_text(), parse_mode=ParseMode.HTML
    )


@restricted
async def cmd_waf_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, msg = waf_manager.set_waf_state(waf_manager.STATE_ON)
    _audit(update, "开启WAF拦截模式")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


@restricted
async def cmd_waf_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Confirmation step
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ 确认关闭 WAF", callback_data="waf_off_confirm"),
            InlineKeyboardButton("取消", callback_data="waf_cancel"),
        ]
    ])
    await update.message.reply_text(
        "⚠️ 你确定要<b>关闭 WAF</b>吗？关闭后所有请求将不经过规则检测。",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


@restricted
async def cmd_waf_detect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, msg = waf_manager.set_waf_state(waf_manager.STATE_DETECT)
    _audit(update, "开启WAF观察模式")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


@restricted
async def cmd_blacklist_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ 确认清空黑名单", callback_data="blacklist_clear_confirm"),
        InlineKeyboardButton("取消", callback_data="cancel_clear"),
    ]])
    await update.message.reply_text(
        "⚠️ 确认要<b>清空全部黑名单</b>吗？",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


@restricted
async def cmd_whitelist_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ 确认清空白名单", callback_data="whitelist_clear_confirm"),
        InlineKeyboardButton("取消", callback_data="cancel_clear"),
    ]])
    await update.message.reply_text(
        "⚠️ 确认要<b>清空全部白名单</b>吗？",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


# ─── Recent alerts command ──────────────────────────────────────────────────────

@group_readable
async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = 5
    if context.args:
        try:
            n = max(1, min(100, int(context.args[0])))
        except ValueError:
            pass
    await _send_recent_alerts(update.message.reply_text, n)


async def _send_recent_alerts(reply_fn, n: int):
    """Query last N attack logs from the database and send as a single message."""
    from .log_monitor import _severity_emoji, _e
    from .db import get_recent_logs

    logs = get_recent_logs(n)
    if not logs:
        await reply_fn("暂无告警记录。")
        return

    header = f"📋 <b>最近 {len(logs)} 条告警</b>\n━━━━━━━━━━━━━━━━"
    items = []
    for i, log in enumerate(logs, 1):
        # Pick the highest-severity emoji from rules
        rule_ids = []
        top_emoji = "⚪"
        for r in log["rules"]:
            rule_ids.append(str(r["rule_id"]))
            top_emoji = _severity_emoji(r["severity"])

        uri = log["uri"]
        short_uri = uri[:60] + "..." if len(uri) > 60 else uri
        ts = log["timestamp"]
        short_ts = ts[5:16] if len(ts) >= 16 else ts  # "03-20 12:30"
        rules_str = ",".join(rule_ids[:3])
        if len(rule_ids) > 3:
            rules_str += f"…+{len(rule_ids) - 3}"

        item = (
            f"\n<b>{i}.</b> {top_emoji} <b>{_e(log['attack_type'])}</b>"
            f" | <code>{_e(log['client_ip'])}</code>"
            f" {'🏳️ ' + _e(log['country']) if log['country'] else ''}\n"
            f"   <code>{_e(log['method'])} {_e(short_uri)}</code>\n"
            f"   🕐 {_e(short_ts)} | {_e(log['http_code'])} | 规则: <code>{_e(rules_str)}</code>"
        )
        items.append(item)

    # Build message, split into multiple if exceeding 4096
    messages = []
    current = header
    for item in items:
        if len(current) + len(item) > 4000:
            messages.append(current)
            current = ""
        current += item
    if current:
        messages.append(current)

    for msg in messages:
        await reply_fn(msg, parse_mode=ParseMode.HTML)


# ─── CC status command ─────────────────────────────────────────────────────────

def _e_text(value) -> str:
    return html.escape(str(value), quote=False)


def _parse_count_item(line: str):
    m = re.match(r"^\s*(\d+)\s+(.+?)\s*$", line)
    if not m:
        return None
    return int(m.group(1)), m.group(2)


def _parse_cc_status_output(raw: str) -> dict:
    data = {"time": "", "lines": "", "sites": {}, "warnings": {}}
    current_site = None
    mode = None

    for raw_line in raw.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        m = re.match(r"^time=(.*?)\s+lines=(\d+)$", line)
        if m:
            data["time"] = m.group(1)
            data["lines"] = m.group(2)
            continue

        m = re.match(r"^==\s+(.+?)\s+access log\s+==$", line)
        if m:
            current_site = m.group(1)
            data["sites"].setdefault(
                current_site,
                {"total": 0, "hits": 0, "top_ips": [], "top_uris": []},
            )
            mode = "site"
            continue

        m = re.match(r"^==\s+(.+?)\s+recent limit warnings\s+==$", line)
        if m:
            current_site = m.group(1)
            data["warnings"].setdefault(current_site, [])
            mode = "warnings"
            continue

        if mode == "site" and current_site:
            m = re.match(r"^total=(\d+)\s+cc_or_429=(\d+)$", line)
            if m:
                data["sites"][current_site]["total"] = int(m.group(1))
                data["sites"][current_site]["hits"] = int(m.group(2))
                continue
            if line == "top_ips:":
                mode = "top_ips"
                continue
            if line == "top_uris:":
                mode = "top_uris"
                continue

        if mode in {"top_ips", "top_uris"} and current_site:
            if line == "top_ips:":
                mode = "top_ips"
                continue
            if line == "top_uris:":
                mode = "top_uris"
                continue
            if line.startswith("== "):
                current_site = None
                mode = None
                continue
            item = _parse_count_item(line)
            if item:
                key = "top_ips" if mode == "top_ips" else "top_uris"
                data["sites"][current_site][key].append(item)
                continue

        if mode == "warnings" and current_site:
            data["warnings"][current_site].append(line)

    return data


def _format_count_list(items, empty_text="无", limit=5) -> str:
    if not items:
        return empty_text
    lines = []
    for count, value in items[:limit]:
        short_value = value if len(value) <= 90 else value[:87] + "..."
        lines.append(f"<code>{_e_text(short_value)}</code> - <b>{count}</b> 次")
    return "\n".join(lines)


def _format_cc_status(raw: str, requested_lines: int) -> str:
    data = _parse_cc_status_output(raw)
    lines = data.get("lines") or str(requested_lines)
    checked_at = data.get("time") or "未知"

    parts = [
        "📊 <b>CC 防护状态</b>",
        f"统计范围：最近 <code>{_e_text(lines)}</code> 行 access log",
        f"时间：<code>{_e_text(checked_at)}</code>",
    ]

    for site, info in data["sites"].items():
        hits = int(info.get("hits", 0))
        total = int(info.get("total", 0))
        state = "✅ 最近未见 CC 拦截" if hits == 0 else "⚠️ 发现 CC / 429 命中"
        parts.append(
            "\n"
            f"<b>{_e_text(site)}</b>\n"
            f"状态：{state}\n"
            f"请求总数：<code>{total}</code>\n"
            f"CC/429 命中：<code>{hits}</code>\n\n"
            f"<b>Top IP</b>\n{_format_count_list(info.get('top_ips', []))}\n\n"
            f"<b>Top URI</b>\n{_format_count_list(info.get('top_uris', []))}"
        )

    warning_blocks = []
    for site, warnings in data["warnings"].items():
        if not warnings:
            continue
        trimmed = []
        for warning in warnings[-2:]:
            short = warning if len(warning) <= 180 else warning[:177] + "..."
            trimmed.append(f"<code>{_e_text(short)}</code>")
        warning_blocks.append(f"<b>{_e_text(site)}</b>\n" + "\n".join(trimmed))
    if warning_blocks:
        parts.append("\n<b>最近 Nginx limit warning</b>\n" + "\n\n".join(warning_blocks))
    else:
        parts.append("\n<b>最近 Nginx limit warning</b>\n无")

    text = "\n".join(parts)
    if len(text) > 3900:
        text = text[:3850] + "\n\n输出过长，已截断。可用 <code>/cc_status 1000</code> 缩小范围。"
    return text


async def _run_cc_status_script(lines: int) -> tuple[bool, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            CC_STATUS_SCRIPT,
            str(lines),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=CC_STATUS_TIMEOUT
        )
    except FileNotFoundError:
        return False, f"找不到脚本: {CC_STATUS_SCRIPT}"
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        return False, f"CC 状态脚本超过 {CC_STATUS_TIMEOUT} 秒未返回。"

    out_text = stdout.decode("utf-8", errors="replace")
    err_text = stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        return False, err_text or out_text or f"脚本退出码: {proc.returncode}"
    return True, out_text


async def _send_cc_status(reply_fn, lines: int):
    ok, output = await _run_cc_status_script(lines)
    if not ok:
        await reply_fn(
            f"❌ CC 状态读取失败：<code>{_e_text(output)}</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    await reply_fn(_format_cc_status(output, lines), parse_mode=ParseMode.HTML)


@group_readable
async def cmd_cc_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = CC_STATUS_DEFAULT_LINES
    if context.args:
        try:
            lines = int(context.args[0])
        except ValueError:
            await update.message.reply_text(
                "用法: <code>/cc_status [100-50000]</code>",
                parse_mode=ParseMode.HTML,
            )
            return
    lines = max(CC_STATUS_MIN_LINES, min(CC_STATUS_MAX_LINES, lines))
    _audit(update, f"查看CC状态: lines={lines}")
    await _send_cc_status(update.message.reply_text, lines)


# ─── Inline keyboard callbacks ──────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_supported_chat(update):
        await _reply_access_denied(update, "⛔ 当前聊天未授权使用机器人。")
        return

    query = update.callback_query
    data = query.data
    can_manage = _is_authorized_user(update)
    if not can_manage and data not in READ_ONLY_CALLBACKS:
        await query.answer("⛔ 仅允许管理员执行该操作。", show_alert=True)
        return

    await query.answer()

    # ── WAF confirmations ──
    if data == "waf_off_confirm":
        ok, msg = waf_manager.set_waf_state(waf_manager.STATE_OFF)
        _audit(update, "关闭WAF（已确认）")
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)

    elif data == "waf_cancel":
        await query.edit_message_text("操作已取消。")

    elif data == "cancel_clear":
        await query.edit_message_text("操作已取消。")

    elif data == "blacklist_clear_confirm":
        ok, msg = ip_manager.clear_blacklist()
        _audit(update, "清空黑名单")
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)

    elif data == "whitelist_clear_confirm":
        ok, msg = ip_manager.clear_whitelist()
        _audit(update, "清空白名单")
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)

    # ── WAF menu ──
    elif data == "menu_waf":
        state_text = waf_manager.waf_status_text()
        if can_manage:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🟢 启用拦截", callback_data="waf_set_on"),
                    InlineKeyboardButton("🟡 观察模式", callback_data="waf_set_detect"),
                    InlineKeyboardButton("🔴 关闭", callback_data="waf_set_off"),
                ],
                [InlineKeyboardButton("◀ 返回", callback_data="menu_main")],
            ])
            prompt = "请选择操作:"
        else:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("◀ 返回", callback_data="menu_main"),
            ]])
            prompt = "当前群仅开放只读查看。"
        await query.edit_message_text(
            f"{state_text}\n\n{prompt}",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    elif data == "waf_set_on":
        ok, msg = waf_manager.set_waf_state(waf_manager.STATE_ON)
        _audit(update, "开启WAF拦截模式（菜单）")
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)

    elif data == "waf_set_detect":
        ok, msg = waf_manager.set_waf_state(waf_manager.STATE_DETECT)
        _audit(update, "开启WAF观察模式（菜单）")
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)

    elif data == "waf_set_off":
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("⚠️ 确认关闭", callback_data="waf_off_confirm"),
            InlineKeyboardButton("取消", callback_data="menu_waf"),
        ]])
        await query.edit_message_text(
            "⚠️ 确认要<b>关闭 WAF</b>吗？关闭后所有请求将不经过检测。",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    # ── Blacklist menu ──
    elif data == "menu_blacklist":
        text = ip_manager.list_blacklist()
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ 返回", callback_data="menu_main"),
        ]])
        await query.edit_message_text(
            text + "\n\n使用命令 <code>/blacklist_add &lt;IP&gt;</code> 或 <code>/blacklist_del &lt;IP&gt;</code> 管理。",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    # ── Whitelist menu ──
    elif data == "menu_whitelist":
        text = ip_manager.list_whitelist()
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ 返回", callback_data="menu_main"),
        ]])
        await query.edit_message_text(
            text + "\n\n使用命令 <code>/whitelist_add &lt;IP&gt;</code> 或 <code>/whitelist_del &lt;IP&gt;</code> 管理。",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    # ── Recent alerts ──
    elif data == "menu_recent":
        await query.edit_message_text("正在读取最近告警...")
        await _send_recent_alerts(
            lambda text, **kw: query.message.reply_text(text, **kw), 5
        )

    # ── CC status ──
    elif data == "menu_cc_status":
        _audit(update, f"菜单查看CC状态: lines={CC_STATUS_DEFAULT_LINES}")
        await query.edit_message_text("正在读取 CC 防护状态...")
        await _send_cc_status(
            lambda text, **kw: query.message.reply_text(text, **kw),
            CC_STATUS_DEFAULT_LINES,
        )

    # ── Block IP from alert ──
    elif data.startswith("block_ip_"):
        ip = data[len("block_ip_"):]
        if not _validate_ip(ip):
            await query.edit_message_text(
                query.message.text + "\n\n❌ 无效的 IP 地址。",
                parse_mode=ParseMode.HTML,
            )
            return
        ok, msg = ip_manager.add_ip_to_blacklist(ip)
        _audit(update, f"告警按钮拉黑: {ip}")
        result_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"✅ 已拉黑 {ip}" if ok else f"⚠️ {ip}",
                callback_data="noop",
            )
        ]])
        await query.edit_message_text(
            query.message.text + f"\n\n{msg}",
            parse_mode=ParseMode.HTML,
            reply_markup=result_markup,
        )

    elif data == "noop":
        await query.answer("该 IP 已被拉黑。", show_alert=False)

    # ── Main menu ──
    elif data == "menu_main":
        text, keyboard = _main_menu_payload(can_manage)
        text = f"{text}\n\n{waf_manager.waf_status_text()}"
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )



# ─── Unknown command ────────────────────────────────────────────────────────────

@group_readable
async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_authorized_user(update):
        text = "未知命令。发送 /start 查看帮助。"
    else:
        text = "当前群只开放只读命令：/waf_status、/recent、/cc_status。"
    await update.message.reply_text(text)


# ─── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN 未配置，请检查 .env 文件。")

    app = Application.builder().token(config.BOT_TOKEN).build()

    # Register handlers for private chat and groups. Fine-grained permission checks
    # are enforced inside decorators and callback routing.
    _chats = filters.ChatType.PRIVATE | filters.ChatType.GROUPS
    app.add_handler(CommandHandler("start", cmd_start, filters=_chats))
    app.add_handler(CommandHandler("help", cmd_start, filters=_chats))

    app.add_handler(CommandHandler("blacklist", cmd_blacklist, filters=_chats))
    app.add_handler(CommandHandler("blacklist_add", cmd_blacklist_add, filters=_chats))
    app.add_handler(CommandHandler("blacklist_del", cmd_blacklist_del, filters=_chats))
    app.add_handler(CommandHandler("blacklist_clear", cmd_blacklist_clear, filters=_chats))

    app.add_handler(CommandHandler("whitelist", cmd_whitelist, filters=_chats))
    app.add_handler(CommandHandler("whitelist_add", cmd_whitelist_add, filters=_chats))
    app.add_handler(CommandHandler("whitelist_del", cmd_whitelist_del, filters=_chats))
    app.add_handler(CommandHandler("whitelist_clear", cmd_whitelist_clear, filters=_chats))

    app.add_handler(CommandHandler("waf_status", cmd_waf_status, filters=_chats))
    app.add_handler(CommandHandler("waf_on", cmd_waf_on, filters=_chats))
    app.add_handler(CommandHandler("waf_off", cmd_waf_off, filters=_chats))
    app.add_handler(CommandHandler("waf_detect", cmd_waf_detect, filters=_chats))

    app.add_handler(CommandHandler("recent", cmd_recent, filters=_chats))
    app.add_handler(CommandHandler("cc_status", cmd_cc_status, filters=_chats))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.COMMAND & _chats, cmd_unknown))


    # Start log monitor in background
    monitor = None

    async def post_init(application):
        nonlocal monitor
        monitor = LogMonitor(application.bot)
        asyncio.create_task(monitor.run())
        logger.info("Log monitor background task started.")

    async def post_shutdown(application):
        if monitor:
            monitor.stop()

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    from .db import init_db
    init_db()

    logger.info("WAF Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
