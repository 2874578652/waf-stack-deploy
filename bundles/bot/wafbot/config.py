import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _parse_int_list(name: str) -> list[int]:
    values = []
    for raw in os.getenv(name, "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            values.append(int(raw))
        except ValueError:
            continue
    return values


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALLOWED_USERS = _parse_int_list("ALLOWED_USERS")
ALERT_CHAT_ID = int(os.getenv("ALERT_CHAT_ID", "0"))
ALLOWED_GROUPS = _parse_int_list("ALLOWED_GROUPS")
MODSEC_AUDIT_LOG = os.getenv("MODSEC_AUDIT_LOG", "/var/log/modsec_audit.log")
ALERT_INTERVAL = int(os.getenv("ALERT_INTERVAL", "30"))

# Nginx / OpenResty
NGINX_BIN = os.getenv("NGINX_BIN", "nginx")          # e.g. openresty
NGINX_SERVICE = os.getenv("NGINX_SERVICE", "nginx")   # systemd service name

# File paths
IP_BLACKLIST = os.getenv("IP_BLACKLIST", "/etc/nginx/modsec/custom/ipblacklist.data")
IP_WHITELIST = os.getenv("IP_WHITELIST", "/etc/nginx/modsec/custom/ipwhitelist.data")
CC_WHITELIST_INCLUDE = os.getenv("CC_WHITELIST_INCLUDE", "/etc/nginx/modsec/custom/ipwhitelist_cc.inc")
MODSEC_CONF = os.getenv("MODSEC_CONF", "/etc/nginx/modsec/modsecurity.conf")
DB_PATH = os.getenv("DB_PATH", "")
