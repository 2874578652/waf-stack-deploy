"""SQLite database for persisting WAF attack logs."""

import sqlite3
import logging
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)

_DB_PATH = getattr(config, "DB_PATH", None) or str(
    Path(__file__).resolve().parent.parent / "wafbot.db"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attack_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,               -- 原始时间戳，格式 YYYY-MM-DD HH:MM:SS
    client_ip   TEXT    NOT NULL,
    country     TEXT    DEFAULT '',              -- CF-IPCountry
    host        TEXT    DEFAULT '',
    method      TEXT    DEFAULT '',
    uri         TEXT    DEFAULT '',
    http_code   INTEGER DEFAULT 0,
    attack_type TEXT    DEFAULT '',              -- 派生的攻击类型：SQL注入、XSS攻击 等
    raw_json    TEXT    DEFAULT '',              -- 完整 JSON 原文，便于回溯
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matched_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id      INTEGER NOT NULL REFERENCES attack_logs(id) ON DELETE CASCADE,
    rule_id     TEXT    NOT NULL,
    severity    INTEGER DEFAULT 0,
    message     TEXT    DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_attack_logs_timestamp  ON attack_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_attack_logs_client_ip  ON attack_logs(client_ip);
CREATE INDEX IF NOT EXISTS idx_attack_logs_attack_type ON attack_logs(attack_type);
CREATE INDEX IF NOT EXISTS idx_matched_rules_log_id   ON matched_rules(log_id);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables and indexes if they don't exist."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
        logger.info(f"Database initialised at {_DB_PATH}")
    finally:
        conn.close()


def insert_attack_log(
    timestamp: str,
    client_ip: str,
    country: str,
    host: str,
    method: str,
    uri: str,
    http_code: int,
    attack_type: str,
    raw_json: str,
    rules: list[dict],
) -> int | None:
    """Insert an attack log and its matched rules. Returns the log id."""
    try:
        conn = get_connection()
        cur = conn.execute(
            """INSERT INTO attack_logs
               (timestamp, client_ip, country, host, method, uri, http_code, attack_type, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, client_ip, country, host, method, uri, http_code, attack_type, raw_json),
        )
        log_id = cur.lastrowid
        for rule in rules:
            conn.execute(
                """INSERT INTO matched_rules (log_id, rule_id, severity, message)
                   VALUES (?, ?, ?, ?)""",
                (log_id, rule.get("rule_id", ""), rule.get("severity", 0), rule.get("message", "")),
            )
        conn.commit()
        conn.close()
        return log_id
    except Exception as e:
        logger.error(f"Failed to insert attack log: {e}")
        return None


def get_recent_logs(n: int = 5) -> list[dict]:
    """Return the most recent N attack logs with their matched rules."""
    try:
        conn = get_connection()
        rows = conn.execute(
            """SELECT id, timestamp, client_ip, country, host, method, uri,
                      http_code, attack_type
               FROM attack_logs ORDER BY id DESC LIMIT ?""",
            (n,),
        ).fetchall()

        results = []
        for row in rows:
            log = dict(row)
            rules = conn.execute(
                """SELECT rule_id, severity, message
                   FROM matched_rules WHERE log_id = ?""",
                (log["id"],),
            ).fetchall()
            log["rules"] = [dict(r) for r in rules]
            results.append(log)

        conn.close()
        return results
    except Exception as e:
        logger.error(f"Failed to query recent logs: {e}")
        return []
