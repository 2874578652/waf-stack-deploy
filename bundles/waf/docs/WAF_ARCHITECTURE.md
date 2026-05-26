# WAF Architecture And Operations Notes

Last verified: 2026-05-21 13:56 CST

This file is for the next AI/operator that connects to this server. It describes the local WAF deployment, request protection flow, Telegram bot push mechanism, and bot operating logic. Do not print or expose `/opt/wafbot/.env` secrets such as `BOT_TOKEN`, `ALLOWED_USERS`, or `ALERT_CHAT_ID`.

## 0. Mandatory Maintenance Rule

Any AI/operator that modifies this WAF, Nginx ModSecurity configuration, CRS/custom rules, site routing, whitelist/blacklist behavior, Telegram bot code, bot systemd service, bot environment variables, log handling, or SQLite schema must update this file in the same work session.

每次 AI 或人工对 WAF、Nginx ModSecurity 配置、CRS/自定义规则、站点转发、黑白名单逻辑、Telegram 机器人代码、机器人 systemd 服务、机器人环境变量、日志处理或 SQLite 表结构做任何修改后，都必须同步更新 `/root/WAF_ARCHITECTURE.md`。

The update must record:

- What changed and why.
- Exact files or services changed.
- Whether `nginx -t`, `systemctl reload nginx`, `systemctl restart wafbot`, or other verification was run.
- Current protection impact, especially which domains are protected or bypassed.
- Any new commands or operational notes future AI/operators need.

Never write secret values into this document. Record environment variable names only, and redact values such as Telegram tokens, chat IDs, and admin user IDs.

## 0.1 Current Baseline Backup

Before later WAF hardening work, the current known-good state was saved here:

```text
/root/waf-backups/20260429-111707
```

Backup contents:

- `/etc/nginx` full Nginx and ModSecurity configuration.
- `/opt/wafbot` full Telegram bot directory, including local virtualenv, database, and `.env`.
- `/etc/systemd/system/wafbot.service`.
- `snapshots/` with service status, network listeners, `nginx -t`, `nginx -T`, iptables/nft, Docker, and dpkg outputs.
- `MANIFEST.sha256` file checksums.
- `rollback.sh` helper script.

Rollback command, if a future change breaks the WAF or bot:

```bash
cd /root/waf-backups/20260429-111707
bash rollback.sh --restore
```

The rollback script first creates a safety copy of the then-current state under `/root/waf-backups/pre-rollback-*`, then restores `/etc/nginx`, `/opt/wafbot`, and `wafbot.service`, runs `nginx -t`, reloads Nginx, and restarts `wafbot`.

## 0.2 Change Log

2026-05-21 13:56 CST - CC whitelist source unified into the WAF whitelist.

Changed files:

```text
/etc/nginx/conf.d/00-waf-cc-limit-zones.conf
/etc/nginx/modsec/custom/ipwhitelist_cc.inc
/opt/wafbot/wafbot/config.py
/opt/wafbot/wafbot/ip_manager.py
/opt/wafbot/wafbot/whitelist_sync.py
/root/WAF_MANAGEMENT.md
/root/WAF_ARCHITECTURE.md
```

Behavior changed: Stage 2 Nginx CC protection now uses `/etc/nginx/modsec/custom/ipwhitelist.data` as the only whitelist source of truth. A generated include file `/etc/nginx/modsec/custom/ipwhitelist_cc.inc` is rendered from that source for Nginx `geo` / `map` syntax, and `/etc/nginx/modsec/custom/ipwhitelist_cc.data` is no longer used. The wafbot whitelist management code now updates `ipwhitelist.data` and regenerates `ipwhitelist_cc.inc`. CC thresholds, site routing, CRS behavior, blacklist logic, and SQLite schema were not changed.

Verification: `/opt/wafbot/venv/bin/python3 -m wafbot.whitelist_sync` synced 1 whitelist entry; Python compile check passed for `/opt/wafbot/wafbot/config.py`, `/opt/wafbot/wafbot/ip_manager.py`, and `/opt/wafbot/wafbot/whitelist_sync.py`; `nginx -t` passed; `systemctl reload nginx` succeeded; `systemctl restart wafbot` succeeded; `nginx.service` and `wafbot.service` are active (running). `journalctl -u wafbot -n 20` still contains the pre-existing duplicate polling conflict from the old process before restart, but the new process started successfully and the log monitor resumed.

Rollback backup:

```text
/root/waf-backups/whitelist-single-source-pre-20260521-1352
```

2026-05-21 10:56 CST - IP whitelist now bypasses Stage 2 CC protection.

Changed files:

```text
/etc/nginx/conf.d/00-waf-cc-limit-zones.conf
/etc/nginx/modsec/custom/ipwhitelist_cc.data
/opt/wafbot/wafbot/config.py
/opt/wafbot/wafbot/ip_manager.py
/root/WAF_MANAGEMENT.md
/root/WAF_ARCHITECTURE.md
```

Behavior changed: IPs listed in the whitelist now bypass both ModSecurity and Stage 2 Nginx CC protection. A generated Nginx data file `/etc/nginx/modsec/custom/ipwhitelist_cc.data` is now used by the Stage 2 CC config through `geo` and `map` so whitelisted IPs receive an empty CC limit key and are not counted by `limit_req` or `limit_conn`. The wafbot whitelist management code now keeps both `ipwhitelist.data` and `ipwhitelist_cc.data` in sync. CC thresholds, site routing, CRS behavior, blacklist logic, and SQLite schema were not changed.

Verification: `nginx -t` passed; `systemctl reload nginx` succeeded; Python compile check passed for `/opt/wafbot/wafbot/config.py` and `/opt/wafbot/wafbot/ip_manager.py`; `systemctl restart wafbot` succeeded; `nginx.service` and `wafbot.service` are active (running). `journalctl -u wafbot` still shows `telegram.error.Conflict: terminated by other getUpdates request`, which is the pre-existing duplicate polling issue and not caused by the whitelist/CC change.

Rollback backup:

```text
/root/waf-backups/whitelist-cc-bypass-pre-20260521-1056
```

2026-05-21 10:44 CST - Telegram bot group mode restricted to one configured group.

Changed files:

```text
/opt/wafbot/.env
/root/WAF_MANAGEMENT.md
/root/WAF_ARCHITECTURE.md
```

Behavior changed: the optional environment variable name `ALLOWED_GROUPS` is now configured with one allowed group/supergroup chat ID. Group mode is no longer open to any group the bot joins. Only that configured group can use the group read-only behavior, and the `ALLOWED_USERS` admins can operate there. Private-chat behavior, WAF runtime configuration, CC thresholds, site routing, and SQLite schema were not changed.

Verification: redacted `.env` check confirmed `ALLOWED_GROUPS` exists; `systemctl restart wafbot` succeeded; `wafbot.service` is active (running). `journalctl -u wafbot` still shows `telegram.error.Conflict: terminated by other getUpdates request`, which indicates another bot instance is polling with the same token elsewhere. The group restriction is configured, but live Telegram interaction verification remains blocked until that duplicate polling instance stops.

Rollback backup:

```text
/root/waf-backups/bot-allow-group-pre-20260521-1044
```

2026-05-21 10:32 CST - Telegram bot group read-only mode enabled, admin actions kept restricted.

Changed files:

```text
/opt/wafbot/wafbot/config.py
/opt/wafbot/wafbot/bot.py
/root/WAF_MANAGEMENT.md
/root/WAF_ARCHITECTURE.md
```

Behavior changed: the bot no longer accepts commands only in private chat. It now registers private, group, and supergroup commands. In groups, `/start`, `/help`, `/waf_status`, `/recent [N]`, and `/cc_status [N]` are readable by group members. Mutating and sensitive actions such as blacklist/whitelist changes, WAF mode changes, list clears, and one-click block-IP alert buttons remain restricted to the Telegram user IDs listed in `ALLOWED_USERS`. A new optional environment variable name `ALLOWED_GROUPS` is supported to restrict which group chat IDs may use group mode. Runtime WAF rules, Nginx/ModSecurity configuration, CC thresholds, site routing, and SQLite schema were not changed.

Verification: Python compile check passed for `/opt/wafbot/wafbot/config.py` and `/opt/wafbot/wafbot/bot.py`; `systemctl restart wafbot` succeeded; `wafbot.service` is active (running). `journalctl -u wafbot` still shows `telegram.error.Conflict: terminated by other getUpdates request`, which indicates another bot instance is polling with the same token elsewhere. The code deployment succeeded, but live Telegram interaction verification remains blocked until that duplicate polling instance stops.

Rollback backup:

```text
/root/waf-backups/bot-group-read-pre-20260521-1032
```

2026-05-13 17:54 CST - Public WAF configuration repository created.

Changed files:

```text
/root/.code/waf
/root/WAF_MANAGEMENT.md
/root/WAF_ARCHITECTURE.md
```

Behavior changed: a public GitHub repository worktree was created at `/root/.code/waf` for WAF/Nginx/ModSecurity configuration packaging and handoff. It contains Nginx configuration, ModSecurity configuration, local custom rules, documentation, and helper verification scripts. Runtime secrets, bot `.env`, databases, logs, SSH keys, and virtualenvs were intentionally excluded. Runtime WAF behavior, Nginx service configuration, ModSecurity rules, CC thresholds, Telegram bot behavior, and site routing were not changed.

Repository:

```text
https://github.com/2874578652/waf.git
```

Verification: `scripts/verify.sh` passed inside `/root/.code/waf`; obvious sensitive filename and token scans were run before push; no `nginx -t`, Nginx reload, or wafbot restart was required because this was packaging/documentation only.

2026-05-13 14:20 CST - CC status helper moved under wafbot directory.

Changed files:

```text
/opt/wafbot/cc_status.sh
/opt/wafbot/wafbot/bot.py
/root/WAF_MANAGEMENT.md
/root/WAF_ARCHITECTURE.md
```

Behavior changed: the read-only CC status helper was moved from `/root/waf-tools/cc_status.sh` to `/opt/wafbot/cc_status.sh`, and the Telegram bot now calls the new path. The old `/root/waf-tools/cc_status.sh` path was removed. Bot command behavior, output format, Nginx CC thresholds, WAF rules, site routing, and SQLite schema were not changed.

Verification: `/opt/wafbot/cc_status.sh 100` ran successfully; Python compile check passed for `/opt/wafbot/wafbot/bot.py`; the bot formatter test passed; `systemctl restart wafbot` succeeded; `wafbot.service` is active (running). No `nginx -t` was required because Nginx and ModSecurity configuration were not changed.

Rollback backup:

```text
/root/waf-backups/cc-status-script-move-pre-20260513-1420
```

2026-05-13 14:01 CST - Telegram bot CC status command added.

Changed files:

```text
/opt/wafbot/wafbot/bot.py
/root/WAF_MANAGEMENT.md
/root/WAF_ARCHITECTURE.md
```

Behavior changed: the Telegram bot now exposes a beautified `/cc_status [N]` command and a `CC 状态` menu button. The command runs the read-only `/opt/wafbot/cc_status.sh` helper with a bounded line count (`100` to `50000`, default `20000`), parses the output, and returns a Telegram-friendly summary by site, including total requests, CC/429 hits, Top IP, Top URI, and recent Nginx limit warnings. It does not change Nginx, ModSecurity, WAF rules, CC thresholds, blacklist/whitelist files, SQLite schema, or site routing.

Verification: Python compile check passed for `/opt/wafbot/wafbot/bot.py`; `systemctl restart wafbot` succeeded; `wafbot.service` is active (running). No `nginx -t` was required because Nginx and ModSecurity configuration were not changed.

Rollback backup:

```text
/root/waf-backups/bot-cc-status-pre-20260513-1401
```

2026-05-13 11:16 CST - Stage 2.1 CC observability improved.

Changed files:

```text
/etc/nginx/nginx.conf
/etc/nginx/sites-enabled/devxxl.top.conf
/etc/nginx/sites-enabled/fnstocktest.top.conf
/etc/nginx/sites-enabled/microtalk.top.conf
/opt/wafbot/cc_status.sh
/root/WAF_MANAGEMENT.md
/root/WAF_ARCHITECTURE.md
```

Behavior changed: `devxxl.top`, `fnstocktest.top`, and `microtalk.top` now write access logs with the `cloudflare_cc` log format. The format keeps the previous Cloudflare fields and appends `host=`, `rt=`, `lrs=$limit_req_status`, and `lcs=$limit_conn_status` so Nginx CC limit decisions can be counted from access logs. A read-only helper `/opt/wafbot/cc_status.sh [lines]` was added to summarize recent 429 / CC rejects by site, IP, and URI, and to show recent Nginx limit warnings. CC thresholds, site routing, WAF rules, Telegram bot code, and `financedev.xyz` behavior were not changed.

Verification: `nginx -t` passed; `systemctl reload nginx` succeeded; normal local requests for `web.devxxl.top`, `web.fnstocktest.top`, and `web.microtalk.top` returned 200; `financedev.xyz` remained without `limit_req` / `limit_conn`; `/opt/wafbot/cc_status.sh 1000` ran successfully.

Rollback backup:

```text
/root/waf-backups/stage2-1-pre-20260513-1116
```

2026-04-29 16:01 CST - Stage 2 Nginx CC protection enabled.

Changed files:

```text
/etc/nginx/conf.d/00-waf-cc-limit-zones.conf
/etc/nginx/sites-enabled/devxxl.top.conf
/etc/nginx/sites-enabled/fnstocktest.top.conf
/etc/nginx/sites-enabled/microtalk.top.conf
/root/WAF_MANAGEMENT.md
/root/WAF_ARCHITECTURE.md
```

Behavior changed: `devxxl.top`, `fnstocktest.top`, and `microtalk.top` now have Nginx `limit_req` / `limit_conn` CC protection. Normal pages, API paths, auth paths, and scanner-sensitive paths use separate rate-limit zones. Over-limit requests return HTTP 429. `financedev.xyz` was left unchanged and has no Stage 2 CC rules. Lua was not used.

Verification: `nginx -t` passed; `systemctl reload nginx` succeeded; normal local requests for all three protected hosts returned 200; 120 concurrent local requests to `web.devxxl.top/wp-login.php` produced 9 x 200 and 111 x 429 with `cc_sensitive` warnings in `/var/log/nginx/devxxl.top.error.log`.

Rollback backup:

```text
/root/waf-backups/stage2-pre-20260429-155935
```

2026-04-29 15:52 CST - Scanner observe-only Telegram alerts suppressed.

Changed files:

```text
/opt/wafbot/wafbot/log_monitor.py
/root/WAF_MANAGEMENT.md
/root/WAF_ARCHITECTURE.md
```

Behavior changed: Telegram alerts are no longer sent when the only matched rule is `54002 Scanner-like path observed`. These events are still saved to SQLite. Events that also match other rules still follow the normal push logic.

Verification performed: Python compile check passed; `systemctl restart wafbot` succeeded; `wafbot.service` is active (running). No `nginx -t` was required because Nginx/ModSecurity config was not changed.

Rollback backup:

```text
/root/waf-backups/manual-20260429-155138
```

2026-04-29 15:45 CST - WAF management runbook converted to Chinese.

`/root/WAF_MANAGEMENT.md` was rewritten as a Chinese daily management document. This was a documentation-only change; no WAF, Nginx, ModSecurity, Telegram bot, routing, alerting, blacklist, whitelist, or SQLite behavior changed.

2026-04-29 15:42 CST - Management runbook created.

A daily WAF and Telegram bot management runbook was created at:

```text
/root/WAF_MANAGEMENT.md
```

It records operational paths, safe commands, bot behavior, alert behavior, verification steps, rollback notes, and the required change-log template. Future WAF or bot changes must update `/root/WAF_MANAGEMENT.md` in the same work session; architecture-level behavior changes should continue to update this file as well.

Verification: documentation-only change; no Nginx reload or wafbot restart required.

2026-04-29 11:40 CST - Stage 1 precision access controls added.

Changed files:

```text
/etc/nginx/modsec/custom/07-ua-control.conf
/etc/nginx/modsec/custom/08-header-control.conf
/etc/nginx/modsec/custom/09-param-control.conf
/etc/nginx/modsec/custom/10-risky-path-rules.conf
/etc/nginx/modsec/custom/uablacklist.data
/etc/nginx/modsec/custom/headernameblacklist.data
/etc/nginx/modsec/custom/paramnameobserve.data
/etc/nginx/modsec/custom/sensitivepathblacklist.data
/etc/nginx/modsec/custom/sensitivepathobserve.data
/etc/nginx/modsec/custom/templates/README.md
```

Behavior added:

- Direct deny for known scanner/attack User-Agent substrings.
- Direct deny for selected dangerous request header names such as `X-Original-URL` and method override headers.
- Direct deny for missing/overlong Host headers.
- Direct deny for prototype-pollution style parameter names.
- Direct deny for high-confidence sensitive file/path probes such as `/.env`, `/.git`, `/etc/passwd`, `/phpmyadmin`, and `/server-status`.
- Observe-only logging for missing/empty User-Agent, sensitive command-like parameter names, and common CMS/framework scanner paths.

Verification:

```text
nginx -t: passed
ModSecurity rules loaded: 0/857/0
systemctl reload nginx: succeeded
Local block checks: sqlmap UA -> 403, /.env -> 403, X-Original-URL header -> 403
Local normal request check: normal UA / -> 301, not blocked by new rules
```

Stage-specific rollback point:

```text
/root/waf-backups/stage1-pre-20260429-113457
```

## 1. One-Screen Summary

This server is a WAF/reverse-proxy node.

```text
Public traffic
  -> 150.5.152.117
  -> VM private IP 172.31.0.10
  -> Nginx listens on 0.0.0.0:80
  -> Nginx loads ModSecurity-nginx module
  -> ModSecurity loads OWASP CRS + custom rules
  -> allowed traffic is proxied to private upstream services
  -> matched WAF audit events go to /var/log/modsec_audit.log
  -> /opt/wafbot tails that audit log and sends Telegram alerts
```

Core WAF:

- Nginx service: `nginx.service`
- WAF engine: ModSecurity v3 through `libnginx-mod-http-modsecurity`
- Rule set: OWASP Core Rule Set under `/etc/nginx/modsec/coreruleset-4.24.1`
- Custom WAF rules and lists: `/etc/nginx/modsec/custom`
- Audit log: `/var/log/modsec_audit.log`
- Telegram management/alert bot: `wafbot.service`, code under `/opt/wafbot`

Docker is installed, but `docker ps` showed no running containers. iptables did not show a local 80/443 NAT path for the WAF. The active WAF path is host Nginx + ModSecurity.

## 2. Important Paths

Nginx and ModSecurity:

```text
/etc/nginx/nginx.conf
/etc/nginx/modules-enabled/50-mod-http-modsecurity.conf
/etc/nginx/modsec/main.conf
/etc/nginx/modsec/modsecurity.conf
/etc/nginx/modsec/coreruleset-4.24.1/
/etc/nginx/modsec/custom/
/etc/nginx/sites-enabled/
```

Custom WAF data files:

```text
/etc/nginx/modsec/custom/ipwhitelist.data
/etc/nginx/modsec/custom/ipwhitelist_cc.inc
/etc/nginx/modsec/custom/ipblacklist.data
/etc/nginx/modsec/custom/uriwhitelist.data
/etc/nginx/modsec/custom/uriblacklist.data
```

Bot:

```text
/etc/systemd/system/wafbot.service
/opt/wafbot/
/opt/wafbot/.env
/opt/wafbot/run.py
/opt/wafbot/wafbot/bot.py
/opt/wafbot/wafbot/log_monitor.py
/opt/wafbot/wafbot/waf_manager.py
/opt/wafbot/wafbot/ip_manager.py
/opt/wafbot/wafbot/db.py
/opt/wafbot/wafbot.db
```

Logs:

```text
/var/log/modsec_audit.log
/var/log/nginx/error.log
/var/log/nginx/devxxl.top.access.log
/var/log/nginx/fnstocktest.top.access.log
/var/log/nginx/microtalk.top.access.log
/var/log/nginx/financedev.xyz.access.log
```

CC helper:

```text
/opt/wafbot/cc_status.sh
```

## 3. Nginx Entry And Site Routing

Nginx listens on port 80:

```text
0.0.0.0:80 -> nginx
```

`/etc/nginx/nginx.conf` globally enables ModSecurity:

```nginx
modsecurity on;
modsecurity_rules_file /etc/nginx/modsec/main.conf;
```

The default server block returns `444` for unknown hostnames:

```nginx
server {
    listen 80 default_server;
    server_name _;
    return 444;
}
```

Cloudflare real IP headers are configured in `nginx.conf`:

```nginx
real_ip_header CF-Connecting-IP;
```

This means WAF rules that use `REMOTE_ADDR` should normally see the Cloudflare-provided real client IP, not only the Cloudflare edge IP, provided the request actually came through Cloudflare.

Known site routing:

```text
.devxxl.top       -> proxy_pass http://172.31.0.3      -> WAF enabled, Stage 2 CC enabled
.fnstocktest.top  -> proxy_pass http://172.31.16.3     -> WAF enabled, Stage 2 CC enabled
.microtalk.top    -> proxy_pass http://172.31.16.6     -> WAF enabled, Stage 2 CC enabled
.financedev.xyz   -> proxy_pass http://172.31.0.6      -> WAF disabled, Stage 2 CC not enabled
```

`/etc/nginx/sites-enabled/financedev.xyz.conf` contains:

```nginx
modsecurity off;
```

So `financedev.xyz` bypasses ModSecurity even though ModSecurity is enabled globally in `nginx.conf`.

## 3.1 Stage 2 Nginx CC Protection

Stage 2 CC protection is implemented with native Nginx `limit_req` and `limit_conn`. Lua is not used for this stage; on 2026-05-13, `nginx -V` did not show an enabled Lua module.

Global zone file:

```text
/etc/nginx/conf.d/00-waf-cc-limit-zones.conf
```

Whitelist bypass include file:

```text
/etc/nginx/modsec/custom/ipwhitelist_cc.inc
```

Defined zones:

```text
cc_global      30r/s, burst=120
cc_page        15r/s, burst=80
cc_api         10r/s, burst=60
cc_auth        3r/s, burst=15
cc_sensitive   2r/s, burst=8
cc_conn_per_ip 80 concurrent connections per real client IP
```

Whitelist bypass behavior:

```text
ipwhitelist.data is the single whitelist source used by ModSecurity rule 10001.
ipwhitelist_cc.inc is generated from ipwhitelist.data for Nginx geo/map to produce an empty CC limit key.
Whitelisted IPs are therefore excluded from Stage 2 CC limit_req / limit_conn accounting.
```

Enabled site files:

```text
/etc/nginx/sites-enabled/devxxl.top.conf
/etc/nginx/sites-enabled/fnstocktest.top.conf
/etc/nginx/sites-enabled/microtalk.top.conf
```

`financedev.xyz` was intentionally left unchanged for this stage because its site file still has `modsecurity off`.

Layering:

```text
Normal pages: location / -> cc_global + cc_page
API paths: /api, /apis, /ajax, /graphql, /rest, /vN -> cc_global + cc_api
Auth paths: /login, /signin, /register, /auth, /oauth, /sso, /api/login and similar -> cc_global + cc_auth
Scanner-sensitive paths: /wp-login.php, /wp-admin, /xmlrpc.php, /phpmyadmin, /pma, /manager/html and similar -> cc_global + cc_sensitive
```

Over-limit response code:

```text
429
```

Stage 2.1 observability:

```text
Log format: cloudflare_cc
Protected sites using it: devxxl.top, fnstocktest.top, microtalk.top
Extra fields: host=$host rt=$request_time lrs=$limit_req_status lcs=$limit_conn_status
Helper: /opt/wafbot/cc_status.sh [lines]
```

`financedev.xyz` still uses the original access log behavior and remains outside Stage 2 CC protection.


## 4. Rule Loading Order

`/etc/nginx/modsec/main.conf` loads rules in this order:

```apache
Include /etc/nginx/modsec/modsecurity.conf
Include /etc/nginx/modsec/coreruleset-4.24.1/crs-setup.conf
Include /etc/nginx/modsec/custom/*.conf
Include /etc/nginx/modsec/coreruleset-4.24.1/rules/*.conf
```

This means:

1. ModSecurity engine config is read first.
2. CRS setup is read next.
3. Custom local controls are loaded before CRS rules.
4. CRS detection and blocking rules are loaded last.

`nginx -t` reported after the 2026-04-29 stage 1 rule additions:

```text
ModSecurity-nginx v1.0.3 (rules loaded inline/local/remote: 0/857/0)
```

## 5. WAF Protection Flow

The normal request path is:

```text
Client request
  -> Nginx accepts request on port 80
  -> Hostname is matched against /etc/nginx/sites-enabled/*.conf
  -> If site has modsecurity off, skip WAF for that server block
  -> Otherwise ModSecurity inspects request headers, URI, args, body, JSON/XML/multipart where configured
  -> Custom whitelist/blacklist rules run
  -> OWASP CRS rules run and build anomaly scores
  -> CRS blocking evaluation checks scores
  -> If blocked, client gets deny response, usually 403
  -> If allowed, Nginx reverse proxies request to upstream private IP
  -> ModSecurity writes JSON audit entries to /var/log/modsec_audit.log for relevant 4xx/5xx and matched events
```

Current global engine mode is controlled by:

```text
/etc/nginx/modsec/modsecurity.conf
SecRuleEngine On
```

Mode meanings:

```text
On             Inspect and block when rules say to block
DetectionOnly  Inspect and log, but do not enforce disruptive actions
Off            Disable rule engine
```

The Telegram bot can switch this value via `/waf_on`, `/waf_detect`, and `/waf_off`.

## 6. CRS Scoring Protection

The main OWASP CRS protection is anomaly-score based.

Default active values are set by CRS initialization when not overridden:

```text
tx.inbound_anomaly_score_threshold=5
tx.outbound_anomaly_score_threshold=4
tx.blocking_paranoia_level=1
tx.detection_paranoia_level=tx.blocking_paranoia_level
tx.critical_anomaly_score=5
tx.error_anomaly_score=4
tx.warning_anomaly_score=3
tx.notice_anomaly_score=2
```

The checked file was:

```text
/etc/nginx/modsec/coreruleset-4.24.1/rules/REQUEST-901-INITIALIZATION.conf
```

No active override was found in `crs-setup.conf` or custom rules; the threshold examples in `crs-setup.conf` are commented out.

CRS request blocking is evaluated in:

```text
/etc/nginx/modsec/coreruleset-4.24.1/rules/REQUEST-949-BLOCKING-EVALUATION.conf
```

CRS response blocking is evaluated in:

```text
/etc/nginx/modsec/coreruleset-4.24.1/rules/RESPONSE-959-BLOCKING-EVALUATION.conf
```

Practical meaning:

```text
One critical inbound rule match usually adds 5 points
Inbound threshold is 5
So one critical match can be enough to block the request
```

CRS covers common classes such as SQL injection, XSS, path traversal, command injection, scanner behavior, protocol anomalies, file upload issues, PHP injection patterns, and other known web attack signatures.

## 7. Custom Direct Controls

These custom rules do not rely on CRS anomaly score. They are direct pass/deny controls.

IP whitelist:

```text
Rule file: /etc/nginx/modsec/custom/01-ip-whitelist.conf
Data file: /etc/nginx/modsec/custom/ipwhitelist.data
Rule ID: 10001
Effect: if REMOTE_ADDR matches, ctl:ruleEngine=Off, skip WAF detection; the same whitelist source is rendered into /etc/nginx/modsec/custom/ipwhitelist_cc.inc so Stage 2 CC is bypassed too
```

IP blacklist:

```text
Rule file: /etc/nginx/modsec/custom/02-ip-blacklist.conf
Data file: /etc/nginx/modsec/custom/ipblacklist.data
Rule ID: 20001
Effect: if REMOTE_ADDR matches, deny with status 403 and log
```

URI whitelist:

```text
Rule file: /etc/nginx/modsec/custom/03-uri-whitelist.conf
Data file: /etc/nginx/modsec/custom/uriwhitelist.data
Rule ID: 30001
Effect: if REQUEST_URI contains a listed string, ctl:ruleEngine=Off, skip WAF detection
```

URI blacklist:

```text
Rule file: /etc/nginx/modsec/custom/04-uri-blacklist.conf
Data file: /etc/nginx/modsec/custom/uriblacklist.data
Rule ID: 40001
Effect: if REQUEST_URI contains a listed string, deny with status 403 and log
```

Fine-grained false-positive exception:

```text
Rule file: /etc/nginx/modsec/custom/05-custom-rules.conf
Rule ID: 50001
Match: REQUEST_URI @rx ^/api/[^/]+/sys/sys/
Effect: ctl:ruleRemoveById=930130
```

`06-diy-rules.conf` existed and was empty at verification time.

Stage 1 precision controls:

```text
Rule file: /etc/nginx/modsec/custom/07-ua-control.conf
Data file: /etc/nginx/modsec/custom/uablacklist.data
Rule IDs: 51001-51004
Effect: block known scanner/attack User-Agents and overlong User-Agent values; observe missing/empty User-Agent.
```

```text
Rule file: /etc/nginx/modsec/custom/08-header-control.conf
Data file: /etc/nginx/modsec/custom/headernameblacklist.data
Rule IDs: 52001-52003
Effect: block selected client-supplied override headers, missing Host, and overlong Host.
```

```text
Rule file: /etc/nginx/modsec/custom/09-param-control.conf
Data file: /etc/nginx/modsec/custom/paramnameobserve.data
Rule IDs: 53001-53002
Effect: block prototype-pollution parameter names; observe command-like parameter names.
```

```text
Rule file: /etc/nginx/modsec/custom/10-risky-path-rules.conf
Data files:
  /etc/nginx/modsec/custom/sensitivepathblacklist.data
  /etc/nginx/modsec/custom/sensitivepathobserve.data
Rule IDs: 54001-54002
Effect: block high-confidence sensitive file/path probes; observe common CMS/framework scanner paths.
```

## 8. Telegram Bot Service

The Telegram bot is a systemd service:

```ini
[Service]
Type=simple
User=root
WorkingDirectory=/opt/wafbot
EnvironmentFile=/opt/wafbot/.env
ExecStart=/opt/wafbot/venv/bin/python3 /opt/wafbot/run.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=wafbot
```

Service status at verification time:

```text
wafbot.service active running
Main process: /opt/wafbot/venv/bin/python3 /opt/wafbot/run.py
```

Bot config is read from `/opt/wafbot/.env`. Known variable names:

```text
BOT_TOKEN
ALLOWED_USERS
ALLOWED_GROUPS
ALERT_CHAT_ID
MODSEC_AUDIT_LOG
ALERT_INTERVAL
NGINX_BIN
NGINX_SERVICE
IP_BLACKLIST
IP_WHITELIST
CC_WHITELIST_INCLUDE
MODSEC_CONF
```

Do not reveal the values. If documenting or debugging, redact them.

## 9. Bot Runtime Model

Entrypoint:

```text
/opt/wafbot/run.py
  -> from wafbot.bot import main
  -> main()
```

Main logic:

```text
/opt/wafbot/wafbot/bot.py
```

The bot uses `python-telegram-bot` and starts with:

```python
app.run_polling(allowed_updates=Update.ALL_TYPES)
```

So the bot is not using a webhook. It connects outward to Telegram and receives updates by long polling.

Access control:

```text
Private, group, and supergroup commands are registered.
Read-only handlers use group_readable().
Private chat remains admin-only: if the user ID is not in ALLOWED_USERS, the bot rejects the request.
Mutating/sensitive handlers use restricted() and still require the user ID to be listed in ALLOWED_USERS.
In groups, /start, /help, /waf_status, /recent [N], and /cc_status [N] are readable by group members.
If ALLOWED_GROUPS is configured, only those group chat IDs may use group mode; if ALLOWED_GROUPS is empty, any group the bot joins can use group mode.
```

Supported command groups:

```text
/start, /help
/blacklist, /blacklist_add <IP>, /blacklist_del <IP>, /blacklist_clear
/whitelist, /whitelist_add <IP>, /whitelist_del <IP>, /whitelist_clear
/waf_status, /waf_on, /waf_off, /waf_detect
/recent [N]
/cc_status [N]
```

The bot also uses inline keyboards for:

```text
blacklist management
whitelist management
WAF status/mode
recent alerts
CC status
one-click "block this IP" from an alert
```

## 10. Bot WAF Mode Change Logic

Code:

```text
/opt/wafbot/wafbot/waf_manager.py
```

Flow when changing WAF mode:

```text
Telegram command/callback
  -> waf_manager.set_waf_state(On|Off|DetectionOnly)
  -> edit /etc/nginx/modsec/modsecurity.conf
  -> replace or append SecRuleEngine <state>
  -> run nginx -t
  -> if nginx -t fails, restore original file
  -> if nginx -t succeeds, systemctl reload nginx
  -> report result back to Telegram
```

This is a relatively safe flow because it validates Nginx config before reload and rolls back the file if validation fails.

## 11. Bot IP List Management Logic

Code:

```text
/opt/wafbot/wafbot/ip_manager.py
```

Flow for adding/removing IPs:

```text
Telegram command/callback
  -> validate IPv4 or IPv4 CIDR
  -> acquire file lock /tmp/wafbot_iplist.lock
  -> read current list
  -> add/remove the requested IP/CIDR
  -> write the list file
  -> run nginx -t
  -> if nginx -t fails, restore the original list
  -> if nginx -t succeeds, systemctl reload nginx
  -> report result back to Telegram
```

Black/white list files:

```text
Blacklist: /etc/nginx/modsec/custom/ipblacklist.data
Whitelist: /etc/nginx/modsec/custom/ipwhitelist.data
```

The actual ModSecurity enforcement for those files is in:

```text
/etc/nginx/modsec/custom/01-ip-whitelist.conf
/etc/nginx/modsec/custom/02-ip-blacklist.conf
```

## 12. Bot Alert Push Mechanism

Code:

```text
/opt/wafbot/wafbot/log_monitor.py
```

Startup:

```text
bot.py main()
  -> init_db()
  -> app.post_init starts LogMonitor(application.bot) as a background asyncio task
```

Log monitor flow:

```text
LogMonitor starts
  -> seek to end of /var/log/modsec_audit.log
  -> every ALERT_INTERVAL seconds, check for appended data
  -> read new lines
  -> parse each line as JSON
  -> extract transaction, request, response, headers, messages
  -> derive attack type from rule messages
  -> save event and matched rules into SQLite
  -> format an HTML Telegram alert
  -> send to ALERT_CHAT_ID
```

Important behavior:

```text
On startup, LogMonitor seeks to the end of the audit log.
It does not replay older log lines from before bot startup.
```

Suppression rules in code:

```text
If the only matched rule is 20001, the event is saved to DB but Telegram alert is skipped.
Reason: rule 20001 is already-blacklisted IP, so repeated notifications are suppressed.

If the only matched rule is 54002, the event is saved to DB but Telegram alert is skipped.
Reason: rule 54002 is an observe-only scanner-like path rule, so push noise is suppressed while preserving database history.
If the same event also matches other rules, it can still be pushed.

If CRS message contains exactly "Total Score: 5", the event is saved to DB but Telegram alert is skipped.
Reason appears to be noise reduction for low-threshold score-5 events.
```

Alert format includes:

```text
attack type
timestamp
Host
CF-IPCountry
client IP
method and URI
HTTP response code
matched rule IDs and short messages
```

Each alert can include an inline button:

```text
block_ip_<client_ip>
```

Pressing it calls `ip_manager.add_ip_to_blacklist(ip)`, then tests and reloads Nginx.

## 13. SQLite Storage

Code:

```text
/opt/wafbot/wafbot/db.py
```

Default DB path:

```text
/opt/wafbot/wafbot.db
```

Tables:

```text
attack_logs
matched_rules
```

`attack_logs` stores:

```text
timestamp
client_ip
country
host
method
uri
http_code
attack_type
raw_json
created_at
```

`matched_rules` stores:

```text
log_id
rule_id
severity
message
```

The `/recent [N]` command reads from this SQLite database.

## 14. Safe Verification Commands

Use these to understand current status without changing config:

```bash
hostnamectl
ip -br addr
ss -lntup
systemctl --no-pager status nginx wafbot
systemctl cat wafbot.service
nginx -t
grep -RInE 'modsecurity|SecRuleEngine|modsecurity_rules_file' /etc/nginx/nginx.conf /etc/nginx/modsec
grep -RInE 'listen|server_name|modsecurity|proxy_pass' /etc/nginx/sites-enabled
ls -lh /var/log/modsec_audit.log /var/log/nginx/*.access.log 2>/dev/null
journalctl -u wafbot --no-pager -n 100
/opt/wafbot/cc_status.sh 20000
```

Use these to inspect bot code without revealing secrets:

```bash
sed -n '1,220p' /opt/wafbot/wafbot/config.py
sed -n '1,260p' /opt/wafbot/wafbot/log_monitor.py
sed -n '1,240p' /opt/wafbot/wafbot/waf_manager.py
sed -n '1,240p' /opt/wafbot/wafbot/ip_manager.py
sed 's/=.*$/=<redacted>/' /opt/wafbot/.env
```

## 15. Operational Notes

- The WAF is currently mainly anomaly-score based through OWASP CRS.
- Direct black/white list rules bypass or deny independently of CRS score.
- `financedev.xyz` has `modsecurity off`, so do not assume every Nginx site is protected.
- The bot runs as root because it edits `/etc/nginx/modsec/*` and reloads `nginx`.
- The bot validates with `nginx -t` before reload for WAF mode and IP list changes.
- `/opt/wafbot/.env` contains sensitive Telegram secrets. Do not paste it into chat or logs.
- `/var/log/modsec_audit.log` can be large and may contain request data. Treat it as sensitive.
- If changing CRS thresholds, prefer doing it explicitly in `crs-setup.conf` and always run `nginx -t` before reload.
- If adding custom rules, use the reserved custom rule ID ranges already described in the custom files.
- If troubleshooting missing Telegram alerts, check `journalctl -u wafbot`, `ALERT_CHAT_ID`, outbound network access to Telegram, and whether the event was suppressed by the rule-20001 or Total-Score-5 filters.
- If troubleshooting CC protection, check the protected site access logs for `lrs=` and `lcs=` fields, then run `/opt/wafbot/cc_status.sh 20000`.
