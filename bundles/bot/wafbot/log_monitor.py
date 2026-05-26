"""ModSecurity audit log monitor — tails the JSON log and sends alerts via Telegram."""

import asyncio
import json
import logging
import re
import html
from datetime import datetime
from pathlib import Path
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import TelegramError

from . import config
from .db import insert_attack_log

logger = logging.getLogger(__name__)


def _fmt_time(raw: str) -> str:
    """Convert 'Thu Mar 19 21:49:08 2026' to '2026-03-19 21:49:08'."""
    try:
        dt = datetime.strptime(raw.strip(), "%a %b %d %H:%M:%S %Y")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return raw


def _severity_emoji(severity) -> str:
    try:
        s = int(severity)
    except (ValueError, TypeError):
        return "⚠️"
    if s <= 2:
        return "🔴"
    if s <= 4:
        return "🟠"
    if s <= 6:
        return "🟡"
    return "⚪"


def _get_attack_type(messages: list) -> str:
    """Derive a short attack type label from rule messages only."""
    for msg in messages:
        text = msg.get("message", "")
        if "SQL" in text or "sqli" in text.lower():
            return "SQL注入"
        if "PHP" in text:
            return "PHP注入"
        if "XSS" in text or "xss" in text.lower():
            return "XSS攻击"
        if "LFI" in text or "Restricted File" in text or "Path Traversal" in text:
            return "文件访问"
        if "RCE" in text or "Remote Command" in text:
            return "命令执行"
        if "Scanner" in text or "scanner" in text:
            return "扫描探测"
        if "Upload" in text or "File Upload" in text:
            return "文件上传"
        if "Traversal" in text or "traversal" in text:
            return "路径穿越"
        if "Injection" in text or "injection" in text:
            return "注入攻击"
    return "异常请求"


def _e(s) -> str:
    """HTML-escape a value for safe embedding in Telegram HTML messages."""
    return html.escape(str(s))


def _is_total_score_five(messages: list) -> bool:
    """Return True when CRS reports exactly Total Score: 5."""
    for msg in messages:
        text = msg.get("message", "")
        if re.search(r"\bTotal Score:\s*5\b", text):
            return True
    return False


def format_alert(entry: dict) -> Optional[str]:
    """Format a modsec JSON log entry into a Telegram HTML message."""
    try:
        # All fields are nested inside 'transaction'
        transaction = entry.get("transaction", {})
        messages = transaction.get("messages", [])
        request = transaction.get("request", {})
        response = transaction.get("response", {})

        client_ip = transaction.get("client_ip", "?")
        timestamp = transaction.get("time_stamp", "")
        headers = request.get("headers", {})
        host = headers.get("Host", "?")
        uri = request.get("uri", "?")
        method = request.get("method", "?")
        http_code = response.get("http_code", "?")
        country = headers.get("CF-IPCountry", "?")

        # Build rule lines
        rule_lines = []
        for msg in messages:
            details = msg.get("details", {})
            rule_id = details.get("ruleId", "?")
            severity = details.get("severity", "9")
            message = msg.get("message", details.get("msg", ""))
            emoji = _severity_emoji(severity)
            short_msg = message[:120] + "..." if len(message) > 120 else message
            rule_lines.append(f"{emoji} <b>{_e(rule_id)}</b> {_e(short_msg)}")

        attack_type = _get_attack_type(messages)
        display_uri = _e(uri[:120] + "..." if len(uri) > 120 else uri)

        # Only send alert if there are matched rules
        if not rule_lines:
            return None

        rules_text = "\n".join(rule_lines)
        rules_section = f"\n\n<b>触发规则:</b>\n{rules_text}"

        text = (
            f"🚨 <b>WAF 日志 — {_e(attack_type)}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🕐 <code>{_fmt_time(timestamp)}</code>\n"
            f"🌐 <code>{_e(host)}</code>  🏳️ <code>{_e(country)}</code>\n"
            f"📍 IP: <code>{_e(client_ip)}</code>\n"
            f"📝 <code>{_e(method)} {display_uri}</code>\n"
            f"📊 响应码: <code>{_e(http_code)}</code>"
            f"{rules_section}"
        )
        # Telegram max message length is 4096
        if len(text) > 4096:
            text = text[:4090] + "..."
        return text
    except Exception as e:
        logger.warning(f"Failed to format log entry: {e}")
        return None


class LogMonitor:
    """Asynchronous tail-follow of the modsec audit log."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._stop = False
        self._file_pos = 0

    def stop(self):
        self._stop = True

    def _seek_to_end(self):
        """On start, seek to end of log so we only see new entries."""
        path = Path(config.MODSEC_AUDIT_LOG)
        if path.exists():
            self._file_pos = path.stat().st_size
        else:
            self._file_pos = 0

    async def _send_alert(self, text: str, client_ip: str = ""):
        if not config.ALERT_CHAT_ID:
            return
        try:
            reply_markup = None
            if client_ip:
                reply_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        f"🚫 拉黑 {client_ip}",
                        callback_data=f"block_ip_{client_ip}",
                    )
                ]])
            await self.bot.send_message(
                chat_id=config.ALERT_CHAT_ID,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        except TelegramError as e:
            logger.error(f"Failed to send alert: {e}")

    def _save_to_db(self, entry: dict):
        """Extract fields from log entry and persist to SQLite."""
        try:
            tx = entry.get("transaction", {})
            req = tx.get("request", {})
            resp = tx.get("response", {})
            headers = req.get("headers", {})
            messages = tx.get("messages", [])

            timestamp = _fmt_time(tx.get("time_stamp", ""))
            client_ip = tx.get("client_ip", "")
            country = headers.get("CF-IPCountry", "")
            host = headers.get("Host", "")
            method = req.get("method", "")
            uri = req.get("uri", "")
            http_code = int(resp.get("http_code", 0))
            attack_type = _get_attack_type(messages)
            raw_json = json.dumps(entry, ensure_ascii=False)

            rules = []
            for msg in messages:
                details = msg.get("details", {})
                rules.append({
                    "rule_id": str(details.get("ruleId", "")),
                    "severity": int(details.get("severity", 0) or 0),
                    "message": msg.get("message", ""),
                })

            insert_attack_log(
                timestamp, client_ip, country, host, method, uri,
                http_code, attack_type, raw_json, rules,
            )
        except Exception as e:
            logger.warning(f"Failed to save attack log to DB: {e}")

    async def run(self):
        """Main loop: poll the log file for new JSON lines."""
        self._seek_to_end()
        logger.info(f"Log monitor started. Watching {config.MODSEC_AUDIT_LOG} from pos={self._file_pos}")

        while not self._stop:
            await asyncio.sleep(config.ALERT_INTERVAL)
            path = Path(config.MODSEC_AUDIT_LOG)
            if not path.exists():
                continue

            current_size = path.stat().st_size
            if current_size < self._file_pos:
                self._file_pos = 0

            if current_size == self._file_pos:
                continue

            try:
                with open(path, "r", errors="replace") as f:
                    f.seek(self._file_pos)
                    new_data = f.read()
                    self._file_pos = f.tell()

                for line in new_data.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # 如果只触发了黑名单规则(20001)，跳过告警（IP已拉黑，无需重复通知）
                    messages = entry.get("transaction", {}).get("messages", [])
                    rule_ids = {str(m.get("details", {}).get("ruleId", "")) for m in messages}
                    if rule_ids and rule_ids <= {"20001"}:
                        self._save_to_db(entry)
                        continue

                    # 如果只触发扫描观察规则(54002)，跳过推送，只保存到数据库。
                    if rule_ids and rule_ids <= {"54002"}:
                        self._save_to_db(entry)
                        continue

                    if _is_total_score_five(messages):
                        self._save_to_db(entry)
                        continue

                    alert_text = format_alert(entry)
                    if alert_text:
                        self._save_to_db(entry)
                        client_ip = entry.get("transaction", {}).get("client_ip", "")
                        await self._send_alert(alert_text, client_ip)
            except Exception as e:
                logger.error(f"Log monitor error: {e}")
