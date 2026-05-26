# WAF Bot

Telegram bot for operating an Nginx + ModSecurity WAF node.

It manages WAF mode changes, IP blacklist/whitelist files, Stage 2 CC whitelist sync, recent alert queries, CC status summaries, and real-time alert delivery from ModSecurity audit logs.

## What is in this repository

- Live bot code from the production WAF node
- `wafbot.service` systemd unit
- `wafbot.sh` install/update helper
- `.env.example` template for deployment
- `scripts/bootstrap-debian.sh` for one-command Debian/Ubuntu bootstrap

This repository intentionally does not store production secrets or runtime data such as:

- real `.env` values
- Telegram token / chat IDs / admin IDs
- `wafbot.db`
- `venv/`
- journal or audit logs

## Features

- Admin-only WAF mode control: `On`, `Off`, `DetectionOnly`
- Admin-only IP blacklist and whitelist management
- Whitelist sync into Nginx CC include via `wafbot.whitelist_sync`
- Real-time ModSecurity audit log monitoring and Telegram alerts
- Read-only group mode for `/start`, `/help`, `/waf_status`, `/recent`, `/cc_status`
- Recent alerts from SQLite
- CC status summary via `cc_status.sh`
- Safe Nginx update flow with `nginx -t` before reload and rollback on failure

## Repository layout

```text
.
├── .env.example
├── cc_status.sh
├── requirements.txt
├── run.py
├── scripts/
│   └── bootstrap-debian.sh
├── wafbot/
├── wafbot.service
└── wafbot.sh
```

## Prerequisites on the target host

This bot expects to run on the same host as the WAF and needs these paths or equivalents:

- `/var/log/modsec_audit.log`
- `/etc/nginx/modsec/custom/ipblacklist.data`
- `/etc/nginx/modsec/custom/ipwhitelist.data`
- `/etc/nginx/modsec/custom/ipwhitelist_cc.inc`
- `/etc/nginx/modsec/modsecurity.conf`
- working `nginx -t`
- working `systemctl reload nginx`

If your new machine uses different paths, change them in `/opt/wafbot/.env` after install.

## Quick deploy

### Option 1: one command on Debian/Ubuntu

```bash
curl -fsSL https://raw.githubusercontent.com/2874578652/bot/main/scripts/bootstrap-debian.sh | sudo bash
```

Then edit `/opt/wafbot/.env` and restart the service:

```bash
cp /opt/wafbot/.env.example /opt/wafbot/.env
vi /opt/wafbot/.env
systemctl restart wafbot
systemctl status wafbot --no-pager
```

### Option 2: clone and install manually

```bash
git clone https://github.com/2874578652/bot.git /opt/src/wafbot
cd /opt/src/wafbot
sudo bash wafbot.sh install
cp /opt/wafbot/.env.example /opt/wafbot/.env
vi /opt/wafbot/.env
systemctl restart wafbot
```

## Update on an existing host

```bash
cd /opt/src/wafbot
sudo bash wafbot.sh update
systemctl status wafbot --no-pager
```

## Main environment variables

- `BOT_TOKEN`: Telegram bot token
- `ALLOWED_USERS`: admin Telegram user IDs, comma-separated
- `ALLOWED_GROUPS`: optional allowed group chat IDs, comma-separated
- `ALERT_CHAT_ID`: alert target chat ID
- `MODSEC_AUDIT_LOG`: ModSecurity JSON audit log path
- `ALERT_INTERVAL`: log polling interval in seconds
- `NGINX_BIN`: usually `nginx`
- `NGINX_SERVICE`: usually `nginx`
- `IP_BLACKLIST`: ModSecurity blacklist data file
- `IP_WHITELIST`: ModSecurity whitelist data file
- `CC_WHITELIST_INCLUDE`: generated Nginx CC whitelist include file
- `MODSEC_CONF`: ModSecurity engine config file
- `DB_PATH`: optional SQLite path override

## Verification after install

```bash
systemctl status wafbot --no-pager
journalctl -u wafbot --no-pager -n 100
/opt/wafbot/venv/bin/python3 -m py_compile /opt/wafbot/wafbot/*.py
```

If whitelist sync is enabled, you can also run:

```bash
cd /opt/wafbot
/opt/wafbot/venv/bin/python3 -m wafbot.whitelist_sync
```
