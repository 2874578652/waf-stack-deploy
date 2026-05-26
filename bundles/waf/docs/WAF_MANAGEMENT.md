# WAF 与 Telegram 机器人管理手册

最后更新：2026-05-21 13:56 CST
服务器：`uat-waf-172.31.0.10`
公网 IP：`150.5.152.117`
内网 IP：`172.31.0.10`

这份文档是本机 WAF 和 Telegram 机器人的日常管理手册，用来记录关键路径、配置文件、服务命令、验证步骤、回滚说明和每次变更必须填写的记录格式。

不要把敏感值写进本文档。不要在聊天、工单、日志或 Markdown 文件里粘贴 Telegram bot token、chat ID、管理员用户 ID，或完整的 `/opt/wafbot/.env` 内容。

## 1. 强制变更记录规则

任何 AI 或人工运维人员，只要修改以下内容，必须在同一次操作会话里更新本文档：

- WAF 规则文件、自定义数据列表、CRS 配置、ModSecurity 引擎模式。
- Nginx 站点转发、上游地址、server block、`modsecurity on/off` 配置。
- Telegram 机器人代码、systemd 服务文件、环境变量、告警行为、命令行为、SQLite 表结构。
- 日志路径、审计日志格式、告警抑制规则、备份或回滚流程。
- 域名防护状态、绕过状态、黑名单或白名单行为。

如果变更影响整体架构或长期行为，还必须同步更新：

```text
/root/WAF_ARCHITECTURE.md
```

每条变更记录必须写清楚：

- 日期、时间和时区。
- 改了什么，为什么改。
- 修改了哪些文件或服务。
- 做了哪些验证，例如 `nginx -t`、`systemctl reload nginx`、`systemctl restart wafbot`、curl 测试或机器人命令测试。
- 对防护能力的影响，特别是哪些域名受保护、绕过、拦截或仅观察。
- 如有回滚方式，写清楚备份路径或回滚命令。

## 2. 系统一页概览

这台服务器是一个基于宿主机 Nginx 的 WAF / 反向代理节点。

```text
公网流量
  -> 150.5.152.117
  -> 虚拟机内网 IP 172.31.0.10
  -> Nginx 监听 0.0.0.0:80
  -> Nginx 加载 ModSecurity-nginx 模块
  -> ModSecurity 加载 OWASP CRS 和本机自定义规则
  -> 允许的流量反向代理到内网上游服务
  -> WAF 事件写入 /var/log/modsec_audit.log
  -> /opt/wafbot 监听审计日志并推送 Telegram 告警
```

核心服务：

```text
nginx.service    Nginx 反向代理和 ModSecurity 入口
wafbot.service   Telegram 管理和告警机器人
```

Docker 已安装，但当前文档记录的实际 WAF 链路是宿主机 Nginx + ModSecurity，不是 Docker NAT。

## 3. 当前站点转发状态

本文档创建时已知站点转发如下：

```text
.devxxl.top       -> proxy_pass http://172.31.0.3      -> WAF 已启用，Stage 2 CC 已启用
.fnstocktest.top  -> proxy_pass http://172.31.16.3     -> WAF 已启用，Stage 2 CC 已启用
.microtalk.top    -> proxy_pass http://172.31.16.6     -> WAF 已启用，Stage 2 CC 已启用
.financedev.xyz   -> proxy_pass http://172.31.0.6      -> WAF 已关闭，本轮未启用 CC
```

注意这个文件：

```text
/etc/nginx/sites-enabled/financedev.xyz.conf
```

其中包含：

```nginx
modsecurity off;
```

所以 `financedev.xyz` 当前会绕过 ModSecurity，即使 `/etc/nginx/nginx.conf` 中全局开启了 ModSecurity。

## 4. 核心配置路径

Nginx：

```text
/etc/nginx/nginx.conf
/etc/nginx/sites-enabled/
/etc/nginx/sites-available/
/etc/nginx/modules-enabled/50-mod-http-modsecurity.conf
```

ModSecurity 和 CRS：

```text
/etc/nginx/modsec/main.conf
/etc/nginx/modsec/modsecurity.conf
/etc/nginx/modsec/coreruleset-4.24.1/
/etc/nginx/modsec/coreruleset-4.24.1/crs-setup.conf
/etc/nginx/modsec/coreruleset-4.24.1/rules/
```

自定义 WAF 规则文件：

```text
/etc/nginx/modsec/custom/
/etc/nginx/modsec/custom/01-ip-whitelist.conf
/etc/nginx/modsec/custom/02-ip-blacklist.conf
/etc/nginx/modsec/custom/03-uri-whitelist.conf
/etc/nginx/modsec/custom/04-uri-blacklist.conf
/etc/nginx/modsec/custom/05-custom-rules.conf
/etc/nginx/modsec/custom/06-diy-rules.conf
/etc/nginx/modsec/custom/07-ua-control.conf
/etc/nginx/modsec/custom/08-header-control.conf
/etc/nginx/modsec/custom/09-param-control.conf
/etc/nginx/modsec/custom/10-risky-path-rules.conf
```

自定义数据文件：

```text
/etc/nginx/modsec/custom/ipwhitelist.data
/etc/nginx/modsec/custom/ipwhitelist_cc.inc
/etc/nginx/modsec/custom/ipblacklist.data
/etc/nginx/modsec/custom/uriwhitelist.data
/etc/nginx/modsec/custom/uriblacklist.data
/etc/nginx/modsec/custom/uablacklist.data
/etc/nginx/modsec/custom/headernameblacklist.data
/etc/nginx/modsec/custom/paramnameobserve.data
/etc/nginx/modsec/custom/sensitivepathblacklist.data
/etc/nginx/modsec/custom/sensitivepathobserve.data
```

规则模板和说明：

```text
/etc/nginx/modsec/custom/templates/README.md
```

日志路径：

```text
/var/log/modsec_audit.log
/var/log/nginx/error.log
/var/log/nginx/devxxl.top.access.log
/var/log/nginx/fnstocktest.top.access.log
/var/log/nginx/microtalk.top.access.log
/var/log/nginx/financedev.xyz.access.log
```

文档路径：

```text
/root/WAF_ARCHITECTURE.md
/root/WAF_MANAGEMENT.md
/WAF_ARCHITECTURE.before-stage1.md
```

Git 仓库：

```text
WAF 配置仓库：https://github.com/2874578652/waf.git
本机工作目录：/root/.code/waf
机器人仓库：git@git.dgtuthcy.top:sre/wafbot.git
机器人本机工作目录：/root/.code/wafbot
```

CC 状态辅助脚本：

```text
/opt/wafbot/cc_status.sh
```

备份路径：

```text
/root/waf-backups/20260429-111707
/root/waf-backups/stage1-pre-20260429-113457
/root/waf-backups/stage2-1-pre-20260513-1116
```

## 5. 规则加载顺序

主 include 文件：

```text
/etc/nginx/modsec/main.conf
```

预期加载顺序：

```apache
Include /etc/nginx/modsec/modsecurity.conf
Include /etc/nginx/modsec/coreruleset-4.24.1/crs-setup.conf
Include /etc/nginx/modsec/custom/*.conf
Include /etc/nginx/modsec/coreruleset-4.24.1/rules/*.conf
```

含义：

```text
1. 先加载 ModSecurity 引擎配置。
2. 再加载 CRS 基础配置。
3. 再加载本机自定义规则。
4. 最后加载 CRS 检测和阻断规则。
```

修改任何被 include 的规则或配置文件后，都必须运行：

```bash
nginx -t
```

## 6. WAF 引擎模式

引擎模式配置文件：

```text
/etc/nginx/modsec/modsecurity.conf
```

关键配置：

```apache
SecRuleEngine On
```

模式含义：

```text
On             检测并执行阻断。
DetectionOnly  只检测和记录，不执行阻断动作。
Off            关闭规则引擎。
```

Telegram 机器人可以通过以下命令切换模式：

```text
/waf_on
/waf_detect
/waf_off
```

人工修改时建议按这个流程：

```bash
cp /etc/nginx/modsec/modsecurity.conf /etc/nginx/modsec/modsecurity.conf.bak.$(date +%Y%m%d-%H%M%S)
vim /etc/nginx/modsec/modsecurity.conf
nginx -t
systemctl reload nginx
```

如果 `nginx -t` 失败，必须先恢复备份，不要 reload Nginx。

## 7. CRS 积分防护逻辑

本文档创建时 CRS 默认阈值如下：

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

实际含义：

```text
一个 critical 级别的 CRS 命中通常加 5 分。
入站阻断阈值是 5 分。
所以一次 critical 命中通常就足以拦截请求。
```

CRS 阻断评估文件：

```text
/etc/nginx/modsec/coreruleset-4.24.1/rules/REQUEST-949-BLOCKING-EVALUATION.conf
/etc/nginx/modsec/coreruleset-4.24.1/rules/RESPONSE-959-BLOCKING-EVALUATION.conf
```

如果需要改 CRS 阈值，优先在这个文件里显式配置：

```text
/etc/nginx/modsec/coreruleset-4.24.1/crs-setup.conf
```

改完必须更新本文档和 `/root/WAF_ARCHITECTURE.md`。

## 8. 自定义直接控制规则

这些是本机自定义规则，可能直接放行、拒绝、记录或绕过 WAF，不完全依赖 CRS 积分。

```text
10001  IP 白名单：ctl:ruleEngine=Off，匹配 REMOTE_ADDR 后跳过 WAF
20001  IP 黑名单：直接 deny，返回 403
30001  URI 白名单：ctl:ruleEngine=Off，匹配 REQUEST_URI 子串后跳过 WAF
40001  URI 黑名单：直接 deny，返回 403
50001  误报例外：匹配 ^/api/[^/]+/sys/sys/ 时移除 CRS 规则 930130
51001-51004  User-Agent 控制
52001-52003  请求头控制
53001-53002  参数名控制
54001  敏感路径直接拦截
54002  扫描类路径观察记录，不拦截
```

重点说明：

```text
54002 是 observe-only 规则：pass + log + severity 5。
它用于记录 CMS 或框架常见扫描路径，不会拦截请求。
当前机器人已抑制只命中 54002 的 Telegram 推送；事件仍会写入 SQLite。
```

补充说明：

```text
IP 白名单除了通过 10001 规则跳过 ModSecurity 外，还会同步写入 Nginx 的 CC 白名单数据文件。
因此白名单 IP 当前会同时绕过 WAF 和 Stage 2 CC 的 limit_req / limit_conn。
```

## 8.1 Stage 2 CC 防护配置

Stage 2 使用 Nginx 原生 `limit_req` 和 `limit_conn` 做基础 CC 防护，暂未启用 Lua 细粒度控制。

全局 zone 配置文件：

```text
/etc/nginx/conf.d/00-waf-cc-limit-zones.conf
```

CC 白名单 include 文件：

```text
/etc/nginx/modsec/custom/ipwhitelist_cc.inc
```

当前 zone 和阈值：

```text
cc_global      30r/s，burst=120
cc_page        15r/s，burst=80
cc_api         10r/s，burst=60
cc_auth        3r/s，burst=15
cc_sensitive   2r/s，burst=8
cc_conn_per_ip 每个真实客户端 IP 最多 80 个并发连接
```

白名单豁免逻辑：

```text
ipwhitelist.data 是唯一白名单来源，供 ModSecurity 白名单规则使用。
ipwhitelist_cc.inc 由 ipwhitelist.data 自动渲染，供 Nginx geo/map 生成空的 CC limit key。
匹配白名单的 IP 不再进入 Stage 2 CC 的 limit_req / limit_conn 计数。
```

启用站点：

```text
/etc/nginx/sites-enabled/devxxl.top.conf
/etc/nginx/sites-enabled/fnstocktest.top.conf
/etc/nginx/sites-enabled/microtalk.top.conf
```

暂未启用站点：

```text
/etc/nginx/sites-enabled/financedev.xyz.conf
```

原因：`financedev.xyz` 当前明确配置 `modsecurity off`，本轮未改变它的防护边界。

分层策略：

```text
普通页面：location / 使用 cc_global + cc_page
API 路径：/api、/apis、/ajax、/graphql、/rest、/vN 使用 cc_global + cc_api
登录注册：/login、/signin、/register、/auth、/oauth、/sso、/api/login 等使用 cc_global + cc_auth
扫描敏感路径：/wp-login.php、/wp-admin、/xmlrpc.php、/phpmyadmin、/pma、/manager/html 等使用 cc_global + cc_sensitive
```

超限返回：

```text
HTTP 429
```

相关日志会进入各站点 error log，例如：

```text
/var/log/nginx/devxxl.top.error.log
/var/log/nginx/fnstocktest.top.error.log
/var/log/nginx/microtalk.top.error.log
```

Stage 2.1 可观测性增强：

```text
受保护站点 access_log 使用 cloudflare_cc 格式。
新增字段：host=$host rt=$request_time lrs=$limit_req_status lcs=$limit_conn_status
只读统计脚本：/opt/wafbot/cc_status.sh [lines]
```

常用 CC 状态检查：

```bash
/opt/wafbot/cc_status.sh 20000
grep -RInE 'limit_req|limit_conn|cloudflare_cc' /etc/nginx/nginx.conf /etc/nginx/conf.d /etc/nginx/sites-enabled
```

2026-05-13 检查 `nginx -V` 未看到 Lua 模块，因此本阶段继续使用 Nginx 原生限速能力，没有引入 Lua IP + URI 维度控制。

## 9. Telegram 机器人服务

systemd 服务文件：

```text
/etc/systemd/system/wafbot.service
```

服务定义摘要：

```ini
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

机器人目录：

```text
/opt/wafbot/
/opt/wafbot/run.py
/opt/wafbot/wafbot/
/opt/wafbot/wafbot/bot.py
/opt/wafbot/wafbot/config.py
/opt/wafbot/wafbot/log_monitor.py
/opt/wafbot/wafbot/waf_manager.py
/opt/wafbot/wafbot/ip_manager.py
/opt/wafbot/wafbot/db.py
/opt/wafbot/wafbot.db
/opt/wafbot/venv/
```

环境变量文件：

```text
/opt/wafbot/.env
```

已知变量名：

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

不要暴露变量值。需要查看配置摘要时使用脱敏命令：

```bash
sed 's/=.*$/=<redacted>/' /opt/wafbot/.env
```

本文档创建时的告警目标摘要：

```text
ALERT_CHAT_ID 指向一个 Telegram 群组。
通过 Telegram API 解析到的群标题：GOODING(Mike高防和WAF监控群）
真实 chat ID 存在 /opt/wafbot/.env 中，不要写入本文档。
```

本文档创建时的机器人权限摘要：

```text
ALLOWED_USERS 当前包含 4 个 Telegram 用户 ID。
这些用户可以操作机器人命令和内联按钮。
ALLOWED_GROUPS 为可选变量，用于限制允许使用群聊模式的 group / supergroup chat ID。
当前已配置 1 个允许的群聊 chat ID，用于限制群聊模式只在指定群内生效。
不要把真实用户 ID 写入本文档。
```

## 10. 机器人命令和行为

主要命令：

```text
/start
/help
/blacklist
/blacklist_add <IP 或 CIDR>
/blacklist_del <IP 或 CIDR>
/blacklist_clear
/whitelist
/whitelist_add <IP 或 CIDR>
/whitelist_del <IP 或 CIDR>
/whitelist_clear
/waf_status
/waf_on
/waf_off
/waf_detect
/recent [N]
/cc_status [N]
```

机器人使用 Telegram long polling，不使用 webhook：

```python
app.run_polling(allowed_updates=Update.ALL_TYPES)
```

权限控制：

```text
机器人会注册私聊和群聊命令。
私聊模式下，只有 ALLOWED_USERS 中的 Telegram 用户 ID 可以使用机器人。
群聊模式下，/start、/help、/waf_status、/recent、/cc_status 对群成员开放只读查看。
黑白名单变更、WAF 模式切换、清空列表、告警按钮拉黑等写操作仍然只允许 ALLOWED_USERS 中的 4 个管理员用户执行。
当前已配置 ALLOWED_GROUPS，因此 group / supergroup 仅允许被配置的指定群使用群聊模式。
```

CC 状态查询：

```text
/cc_status [N]
```

行为：

```text
调用只读脚本 /opt/wafbot/cc_status.sh。
N 为统计最近 access log 行数，允许范围 100 到 50000，默认 20000。
机器人会把脚本输出解析成站点维度摘要，包括请求总数、CC/429 命中、Top IP、Top URI 和近期 Nginx limit warning。
```

WAF 模式切换流程：

```text
Telegram 命令或按钮
  -> waf_manager.set_waf_state(On|Off|DetectionOnly)
  -> 修改 /etc/nginx/modsec/modsecurity.conf
  -> 执行 nginx -t
  -> 如果 nginx -t 失败，恢复旧文件
  -> 如果 nginx -t 成功，reload nginx
  -> 把结果回传 Telegram
```

IP 黑白名单管理流程：

```text
Telegram 命令或按钮
  -> 校验 IPv4 或 IPv4 CIDR
  -> 加锁 /tmp/wafbot_iplist.lock
  -> 黑名单：修改对应数据文件
  -> 白名单：同步修改 ModSecurity 白名单和 Nginx CC 白名单两个数据文件
  -> 执行 nginx -t
  -> 如果 nginx -t 失败，恢复旧文件
  -> 如果 nginx -t 成功，reload nginx
  -> 把结果回传 Telegram
```

## 11. 告警推送逻辑

告警监听代码：

```text
/opt/wafbot/wafbot/log_monitor.py
```

监听日志：

```text
/var/log/modsec_audit.log
```

启动行为：

```text
机器人启动时会 seek 到审计日志文件末尾。
它不会补发启动前的旧事件。
```

Telegram 告警内容包括：

```text
攻击类型
时间戳
Host
CF-IPCountry
客户端 IP
请求方法和 URI
HTTP 响应码
命中的规则 ID 和简短说明
一键拉黑客户端 IP 的内联按钮
```

当前告警抑制逻辑：

```text
如果只命中规则 20001，只保存到 SQLite，不推送 Telegram。
原因：该 IP 已经在黑名单中，重复通知意义不大。

如果只命中自定义扫描观察规则 54002，只保存到 SQLite，不推送 Telegram。
原因：54002 是 observe-only 的扫描路径记录，主要用于留痕，频繁推送会产生扫描噪音。
如果同一事件还命中其它规则，例如 SQL 注入、XSS、敏感路径拦截等，仍然会推送。

如果 CRS 消息中精确包含 "Total Score: 5"，只保存到 SQLite，不推送 Telegram。
原因：降低低阈值 CRS 事件的告警噪音。
```

重要区别：

```text
CRS 的 "Total Score: 5" 不等于自定义规则里的 "severity:5"。
例如 54002 是 severity 5 的观察型规则，但它仍可能被推送。
```

## 12. SQLite 存储

数据库路径：

```text
/opt/wafbot/wafbot.db
```

表：

```text
attack_logs
matched_rules
```

`attack_logs` 保存：

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

`matched_rules` 保存：

```text
log_id
rule_id
severity
message
```

安全只读查询：

```bash
sqlite3 /opt/wafbot/wafbot.db '.tables'
sqlite3 /opt/wafbot/wafbot.db 'select timestamp, client_ip, host, method, uri, http_code, attack_type from attack_logs order by id desc limit 20;'
```

`raw_json` 可能包含请求数据，按敏感信息处理。

## 13. 安全状态检查命令

以下命令只查看状态，不改配置：

```bash
hostnamectl
ip -br addr
ss -lntup
systemctl --no-pager --full status nginx wafbot
systemctl cat wafbot.service
nginx -t
grep -RInE 'modsecurity|SecRuleEngine|modsecurity_rules_file' /etc/nginx/nginx.conf /etc/nginx/modsec
grep -RInE 'listen|server_name|modsecurity|proxy_pass' /etc/nginx/sites-enabled
ls -lh /var/log/modsec_audit.log /var/log/nginx/*.access.log 2>/dev/null
journalctl -u wafbot --no-pager -n 100
/opt/wafbot/cc_status.sh 20000
```

查看机器人代码但不暴露 secret：

```bash
sed -n '1,220p' /opt/wafbot/wafbot/config.py
sed -n '1,280p' /opt/wafbot/wafbot/log_monitor.py
sed -n '1,260p' /opt/wafbot/wafbot/waf_manager.py
sed -n '1,260p' /opt/wafbot/wafbot/ip_manager.py
sed 's/=.*$/=<redacted>/' /opt/wafbot/.env
```

## 14. 安全变更流程

改 WAF、Nginx 或机器人行为前，先准备备份目录：

```bash
mkdir -p /root/waf-backups/manual-$(date +%Y%m%d-%H%M%S)
```

至少备份将要修改的文件。较大变更建议备份：

```text
/etc/nginx
/opt/wafbot
/etc/systemd/system/wafbot.service
```

Nginx 或 ModSecurity 变更后：

```bash
nginx -t
systemctl reload nginx
systemctl --no-pager --full status nginx
```

机器人代码、服务或环境变量变更后：

```bash
systemctl restart wafbot
systemctl --no-pager --full status wafbot
journalctl -u wafbot --no-pager -n 100
```

如果同时涉及 WAF 和机器人，尽量做端到端验证：

```bash
curl -i -H 'Host: web.devxxl.top' 'http://127.0.0.1/.env'
curl -i -H 'Host: web.devxxl.top' -A 'sqlmap' 'http://127.0.0.1/'
curl -i -H 'Host: web.devxxl.top' 'http://127.0.0.1/'
```

预期结果取决于当前站点转发和规则状态。必须把实际结果写入变更记录。

## 15. 常用操作

重启 Telegram 机器人：

```bash
systemctl restart wafbot
systemctl --no-pager --full status wafbot
journalctl -u wafbot --no-pager -n 100
```

Nginx 配置验证通过后 reload：

```bash
nginx -t
systemctl reload nginx
```

查看当前 WAF 引擎模式：

```bash
grep -n '^SecRuleEngine' /etc/nginx/modsec/modsecurity.conf
```

查看当前 CC 命中摘要：

```bash
/opt/wafbot/cc_status.sh 20000
```

查看自定义列表内容：

```bash
sed -n '1,200p' /etc/nginx/modsec/custom/ipblacklist.data
sed -n '1,200p' /etc/nginx/modsec/custom/ipwhitelist.data
sed -n '1,200p' /etc/nginx/modsec/custom/ipwhitelist_cc.inc
sed -n '1,200p' /etc/nginx/modsec/custom/uriwhitelist.data
sed -n '1,200p' /etc/nginx/modsec/custom/uriblacklist.data
```

谨慎查看近期 WAF 审计日志：

```bash
tail -n 20 /var/log/modsec_audit.log
```

审计日志可能包含请求参数、请求体或其它敏感数据，不要把原始日志直接贴到公开渠道。

## 16. 回滚说明

已知基线备份：

```text
/root/waf-backups/20260429-111707
```

回滚辅助命令：

```bash
cd /root/waf-backups/20260429-111707
bash rollback.sh --restore
```

已知 Stage 1 变更前备份：

```text
/root/waf-backups/stage1-pre-20260429-113457
```

执行回滚前，要确认目标备份内容，并清楚它会覆盖哪些文件。回滚后执行：

```bash
nginx -t
systemctl --no-pager --full status nginx wafbot
journalctl -u wafbot --no-pager -n 100
```

回滚完成后，必须更新本文档；如果架构或长期行为发生变化，也要更新 `/root/WAF_ARCHITECTURE.md`。

## 17. 变更记录模板

每次更新复制这个模板：

```text
### YYYY-MM-DD HH:MM CST - 简短标题

原因：
- 为什么需要这次变更。

修改的文件或服务：
- /path/to/file
- service-name.service

行为影响：
- 防护、转发、告警或机器人行为发生了什么变化。
- 哪些域名受保护、绕过、被拦截或仅观察。

验证：
- nginx -t：通过/失败/未执行
- systemctl reload nginx：成功/失败/未执行
- systemctl restart wafbot：成功/失败/未执行
- curl 或机器人测试：写清楚简短结果

回滚：
- 备份路径或回滚命令。

备注：
- 后续运维人员必须知道的事项。
```

## 18. 变更记录

### 2026-05-21 13:56 CST - Stage 2 CC 白名单改为复用 WAF 白名单

原因：
- 需要把 Stage 2 CC 的白名单来源收敛到 WAF 白名单，避免继续维护 `ipwhitelist_cc.data` 这份独立数据文件。

修改的文件或服务：
- `/etc/nginx/conf.d/00-waf-cc-limit-zones.conf`
- `/etc/nginx/modsec/custom/ipwhitelist_cc.inc`
- `/opt/wafbot/wafbot/config.py`
- `/opt/wafbot/wafbot/ip_manager.py`
- `/opt/wafbot/wafbot/whitelist_sync.py`
- `/root/WAF_MANAGEMENT.md`
- `/root/WAF_ARCHITECTURE.md`
- `nginx.service`
- `wafbot.service`

行为影响：
- `ipwhitelist.data` 现在是 WAF 和 Stage 2 CC 共用的唯一白名单来源。
- Nginx 继续通过 `geo` + `map` 实现 CC 白名单豁免，但读取的是由 `ipwhitelist.data` 自动渲染出的 `/etc/nginx/modsec/custom/ipwhitelist_cc.inc`。
- `/etc/nginx/modsec/custom/ipwhitelist_cc.data` 已停止使用并已删除。
- Telegram `/whitelist_add`、`/whitelist_del`、`/whitelist_clear` 仍然会同时影响 WAF 和 Stage 2 CC，只是现在改为写入 `ipwhitelist.data` 后自动刷新 `.inc` include 文件。
- 未修改 CRS 规则、站点转发、CC 阈值、黑名单逻辑或 SQLite 表结构。

验证：
- `/opt/wafbot/venv/bin/python3 -m wafbot.whitelist_sync`：成功，同步了 1 条白名单。
- `/opt/wafbot/venv/bin/python3 -m py_compile /opt/wafbot/wafbot/config.py /opt/wafbot/wafbot/ip_manager.py /opt/wafbot/wafbot/whitelist_sync.py`：通过。
- `nginx -t`：通过。
- `systemctl reload nginx`：成功。
- `systemctl restart wafbot`：成功。
- `systemctl --no-pager --full status nginx wafbot`：active (running)。
- `journalctl -u wafbot -n 20`：仍可见旧进程在重启前的 `telegram.error.Conflict` 历史日志，但新进程已成功启动并恢复日志监控。

回滚：
- 备份路径：`/root/waf-backups/whitelist-single-source-pre-20260521-1352`
- 恢复该备份中的 `00-waf-cc-limit-zones.conf`、`config.py`、`ip_manager.py` 和旧白名单文件，然后执行 `nginx -t`、`systemctl reload nginx`、`systemctl restart wafbot`。

备注：
- 后续如果手工编辑 `/etc/nginx/modsec/custom/ipwhitelist.data`，在 `nginx -t` / reload 前要先执行 `cd /opt/wafbot && /opt/wafbot/venv/bin/python3 -m wafbot.whitelist_sync` 刷新 `/etc/nginx/modsec/custom/ipwhitelist_cc.inc`。

### 2026-05-21 10:56 CST - 白名单 IP 同时绕过 Stage 2 CC 防护

原因：
- 当前白名单 IP 只绕过 ModSecurity，不绕过 Nginx Stage 2 CC，和运维预期不一致。

修改的文件或服务：
- `/etc/nginx/conf.d/00-waf-cc-limit-zones.conf`
- `/etc/nginx/modsec/custom/ipwhitelist_cc.data`
- `/opt/wafbot/wafbot/config.py`
- `/opt/wafbot/wafbot/ip_manager.py`
- `/root/WAF_MANAGEMENT.md`
- `/root/WAF_ARCHITECTURE.md`
- `nginx.service`
- `wafbot.service`

行为影响：
- 新增 Nginx 用的 CC 白名单数据文件 `/etc/nginx/modsec/custom/ipwhitelist_cc.data`。
- Stage 2 CC 现通过 `geo` + `map` 对白名单 IP 置空 `limit_req` / `limit_conn` key。
- `ipwhitelist.data` 中的白名单 IP 现在会同步绕过 ModSecurity 和 Stage 2 CC。
- 通过 Telegram `/whitelist_add`、`/whitelist_del`、`/whitelist_clear` 修改白名单时，会同步维护 ModSecurity 白名单文件和 Nginx CC 白名单文件。
- 未修改 CRS 规则、站点转发、CC 阈值、黑名单逻辑或 SQLite 表结构。

验证：
- `nginx -t`：通过。
- `systemctl reload nginx`：成功。
- `/opt/wafbot/venv/bin/python3 -m py_compile /opt/wafbot/wafbot/config.py /opt/wafbot/wafbot/ip_manager.py`：通过。
- `systemctl restart wafbot`：成功。
- `systemctl --no-pager --full status nginx wafbot`：active (running)。
- `journalctl -u wafbot -n 30`：仍可见 `telegram.error.Conflict: terminated by other getUpdates request`，这是既有 Bot Token 冲突问题，与本次白名单 CC 豁免改动无关。

回滚：
- 备份路径：`/root/waf-backups/whitelist-cc-bypass-pre-20260521-1056`
- 恢复该备份中的 `00-waf-cc-limit-zones.conf`、`config.py`、`ip_manager.py` 和 `ipwhitelist_cc.data`，然后执行 `nginx -t`、`systemctl reload nginx`、`systemctl restart wafbot`。

备注：
- `ipwhitelist_cc.data` 是生成型文件，后续不要手工只改其中一份白名单数据。

### 2026-05-21 10:44 CST - 机器人群聊范围收敛到指定群

原因：
- 需要把机器人群聊能力限制到单个指定群，避免其它群误用群只读或管理员群内操作能力。

修改的文件或服务：
- `/opt/wafbot/.env`
- `/root/WAF_MANAGEMENT.md`
- `/root/WAF_ARCHITECTURE.md`
- `wafbot.service`

行为影响：
- 已在 `.env` 中配置 `ALLOWED_GROUPS`。
- 机器人群聊模式现在只允许 1 个指定 group / supergroup chat ID 使用。
- 该指定群内仍保持“群成员可只读、ALLOWED_USERS 中 4 个管理员可操作”的权限模型。
- 私聊权限模型不变。
- 未修改 Nginx、ModSecurity、CRS、自定义 WAF 规则、CC 阈值、站点转发或 SQLite 表结构。

验证：
- `grep '^ALLOWED_GROUPS=' /opt/wafbot/.env | sed 's/=.*$/=<redacted>/'`：已确认变量存在。
- `systemctl restart wafbot`：成功。
- `systemctl --no-pager --full status wafbot`：active (running)。
- `nginx -t`：未执行，未修改 Nginx 或 ModSecurity 配置。
- `journalctl -u wafbot -n 30`：仍可见 `telegram.error.Conflict: terminated by other getUpdates request`，说明当前还有另一个使用同一 Bot Token 的轮询实例在运行。群范围配置已生效，但在线交互验证仍受该外部冲突实例影响。

回滚：
- 备份路径：`/root/waf-backups/bot-allow-group-pre-20260521-1044`
- 删除或回退 `.env` 中的 `ALLOWED_GROUPS` 后执行 `systemctl restart wafbot`。

备注：
- 文档中不要记录真实群 chat ID。

### 2026-05-21 10:32 CST - Telegram 机器人支持群聊只读 + 管理员群内操作

原因：
- 需要把机器人放进群聊使用，让群成员能直接查看 WAF 状态、最近告警和 CC 状态，同时保留管理员才能执行敏感操作。

修改的文件或服务：
- `/opt/wafbot/wafbot/config.py`
- `/opt/wafbot/wafbot/bot.py`
- `/root/WAF_MANAGEMENT.md`
- `/root/WAF_ARCHITECTURE.md`
- `wafbot.service`

行为影响：
- 机器人不再只接受私聊命令，现支持 private、group、supergroup。
- 群成员可在群里使用只读命令：`/start`、`/help`、`/waf_status`、`/recent [N]`、`/cc_status [N]`。
- 群内只读菜单开放 `WAF 状态`、`最近告警`、`CC 状态`。
- 黑白名单变更、清空列表、WAF 模式切换、告警按钮拉黑等写操作，仍然只允许 `ALLOWED_USERS` 中的 4 个管理员用户执行。
- 新增可选环境变量 `ALLOWED_GROUPS`，可用于收敛允许使用群聊模式的群 ID；本次变更时未在 `.env` 中配置，因此机器人加入的群默认都可使用群只读能力，4 个管理员也可在这些群里执行管理操作。
- 未修改 Nginx、ModSecurity、CRS、自定义 WAF 规则、CC 阈值、站点转发或 SQLite 表结构。

验证：
- `/opt/wafbot/venv/bin/python3 -m py_compile /opt/wafbot/wafbot/config.py /opt/wafbot/wafbot/bot.py`：通过。
- `systemctl restart wafbot`：成功。
- `systemctl --no-pager --full status wafbot`：active (running)。
- `nginx -t`：未执行，未修改 Nginx 或 ModSecurity 配置。
- `journalctl -u wafbot -n 30`：仍可见 `telegram.error.Conflict: terminated by other getUpdates request`，说明当前还有另一个使用同一 Bot Token 的轮询实例在运行。代码部署和服务重启已完成，但群聊交互功能需在外部冲突实例停止后才能完成在线验证。

回滚：
- 备份路径：`/root/waf-backups/bot-group-read-pre-20260521-1032`
- 恢复 `config.py` 和 `bot.py` 后执行 `systemctl restart wafbot`。

备注：
- 如果后续只希望指定群使用机器人，应在 `/opt/wafbot/.env` 中增加 `ALLOWED_GROUPS`，填入允许的 group / supergroup chat ID，再重启 `wafbot`。

### 2026-05-13 17:54 CST - 创建公开 WAF 配置仓库

原因：
- 为后续把这套 WAF 部署到其它服务器，创建一个独立的 WAF/Nginx/ModSecurity 配置仓库。

修改的文件或服务：
- `/root/.code/waf`
- `/root/WAF_MANAGEMENT.md`
- `/root/WAF_ARCHITECTURE.md`

行为影响：
- 新增本机 Git 工作目录 `/root/.code/waf`。
- 仓库目标地址：`https://github.com/2874578652/waf.git`。
- 仓库内容包括 Nginx 配置、ModSecurity 配置、自定义规则、两份文档和只读验证脚本。
- 未上传 Telegram bot `.env`、SQLite 数据库、日志、SSH key、Python virtualenv 或其它运行密钥。
- 未修改运行中的 Nginx、ModSecurity、WAF 规则、CC 阈值、Telegram bot、站点转发或 SQLite 结构。

验证：
- `/root/.code/waf/scripts/verify.sh`：通过。
- 敏感文件名扫描：未发现 `.env`、数据库、日志、私钥类文件。
- 明显 token 字符串扫描：未发现。
- `nginx -t`：未执行，未修改 Nginx 或 ModSecurity 配置。
- `systemctl reload nginx`：未执行。
- `systemctl restart wafbot`：未执行。

回滚：
- 如需移除本机仓库工作目录，可删除 `/root/.code/waf`。
- GitHub 远端仓库需要在 GitHub 上单独删除或清空。

备注：
- 这是公开仓库，后续提交前必须继续避免写入密钥、数据库、日志和私钥。

### 2026-05-13 14:20 CST - CC 状态脚本移入 wafbot 目录

原因：
- 将机器人使用的 CC 状态脚本放到机器人目录下，便于后续维护和交接。

修改的文件或服务：
- `/opt/wafbot/cc_status.sh`
- `/opt/wafbot/wafbot/bot.py`
- `/root/WAF_MANAGEMENT.md`
- `/root/WAF_ARCHITECTURE.md`
- `wafbot.service`

行为影响：
- `cc_status.sh` 从 `/root/waf-tools/cc_status.sh` 移到 `/opt/wafbot/cc_status.sh`。
- Telegram 机器人 `/cc_status [N]` 现在调用新路径。
- 删除旧路径 `/root/waf-tools/cc_status.sh`。
- 命令输出格式、CC 统计逻辑、Nginx CC 阈值、WAF 规则、站点转发、SQLite 结构均未改变。

验证：
- `/opt/wafbot/cc_status.sh 100`：运行成功。
- `/opt/wafbot/venv/bin/python3 -m py_compile /opt/wafbot/wafbot/bot.py`：通过。
- 机器人 CC 格式化测试：通过。
- `systemctl restart wafbot`：成功。
- `systemctl --no-pager --full status wafbot`：active (running)。
- `nginx -t`：未执行，未修改 Nginx 或 ModSecurity 配置。

回滚：
- 备份路径：`/root/waf-backups/cc-status-script-move-pre-20260513-1420`
- 可从该目录恢复 `/opt/wafbot/wafbot/bot.py`、两份文档和旧脚本位置，然后执行 `systemctl restart wafbot`。

备注：
- `/root/waf-tools` 目录如为空可以保留，不影响运行。

### 2026-05-13 14:01 CST - Telegram 机器人接入 CC 状态查询

原因：
- 将 Stage 2.1 的只读 CC 统计脚本接入 Telegram 机器人，方便管理员直接通过机器人查看 CC 防护状态。

修改的文件或服务：
- `/opt/wafbot/wafbot/bot.py`
- `/root/WAF_MANAGEMENT.md`
- `/root/WAF_ARCHITECTURE.md`
- `wafbot.service`

行为影响：
- 新增命令 `/cc_status [N]`，默认统计最近 20000 行 access log。
- 新增主菜单按钮 `CC 状态`。
- 机器人调用 `/opt/wafbot/cc_status.sh`，但不会把原始输出直接发送，而是解析成 Telegram HTML 摘要。
- 参数 `N` 只接受数字，并限制在 100 到 50000。
- 该功能只读日志，不修改 Nginx、ModSecurity、WAF 规则、CC 阈值、黑白名单、SQLite 或站点转发。

验证：
- `/opt/wafbot/venv/bin/python3 -m py_compile /opt/wafbot/wafbot/bot.py`：通过。
- `systemctl restart wafbot`：成功。
- `systemctl --no-pager --full status wafbot`：active (running)。
- `nginx -t`：未执行，未修改 Nginx 或 ModSecurity 配置。

回滚：
- 备份路径：`/root/waf-backups/bot-cc-status-pre-20260513-1401`
- 可从该目录恢复 `/opt/wafbot/wafbot/bot.py` 和两份文档，然后执行 `systemctl restart wafbot`。

备注：
- 后续如需把输出改为文件发送或增加 `/cc_top_ips`、`/cc_top_uris`，继续在同一命令族扩展。

### 2026-05-13 11:16 CST - Stage 2.1 CC 可观测性增强

原因：
- 继续完善第二阶段 CC 防护，让 `limit_req` / `limit_conn` 的命中结果可以从 access log 中直接统计，便于后续判断是否需要调阈值或升级到更细维度控制。

修改的文件或服务：
- `/etc/nginx/nginx.conf`
- `/etc/nginx/sites-enabled/devxxl.top.conf`
- `/etc/nginx/sites-enabled/fnstocktest.top.conf`
- `/etc/nginx/sites-enabled/microtalk.top.conf`
- `/opt/wafbot/cc_status.sh`
- `/root/WAF_MANAGEMENT.md`
- `/root/WAF_ARCHITECTURE.md`
- `nginx.service`

行为影响：
- 新增 `cloudflare_cc` access log 格式，保留原 Cloudflare 字段，并追加 `host=`、`rt=`、`lrs=$limit_req_status`、`lcs=$limit_conn_status`。
- `devxxl.top`、`fnstocktest.top`、`microtalk.top` 的 access log 切换为 `cloudflare_cc`。
- 新增只读脚本 `/opt/wafbot/cc_status.sh [lines]`，用于统计最近日志里的 429 / CC reject 来源 IP、URI 和 Nginx limit warning。
- CC 阈值、WAF 规则、站点上游、Telegram 机器人代码、SQLite 结构均未改变。
- `financedev.xyz` 保持原状，仍为 `modsecurity off`，未启用 Stage 2 CC。

验证：
- `nginx -t`：通过。
- `systemctl reload nginx`：成功。
- 正常请求：`web.devxxl.top`、`web.fnstocktest.top`、`web.microtalk.top` 首页均返回 200。
- `/opt/wafbot/cc_status.sh 1000`：运行成功。
- `financedev.xyz` 配置中未出现 `limit_req` 或 `limit_conn`。

回滚：
- 备份路径：`/root/waf-backups/stage2-1-pre-20260513-1116`
- 可从该目录恢复 `/etc/nginx/nginx.conf`、三份站点文件、两份文档，并删除 `/opt/wafbot/cc_status.sh`，然后执行 `nginx -t && systemctl reload nginx`。

备注：
- 2026-05-13 检查 `nginx -V` 未看到 Lua 模块，本阶段没有启用 Lua。

### 2026-04-29 16:01 CST - 第二阶段 CC 防护上线

原因：
- 按阶段计划启用基础 CC 防护，使用 Nginx `limit_req` / `limit_conn` 对普通页面、API、登录注册和扫描敏感路径做分层频控。

修改的文件或服务：
- `/etc/nginx/conf.d/00-waf-cc-limit-zones.conf`
- `/etc/nginx/sites-enabled/devxxl.top.conf`
- `/etc/nginx/sites-enabled/fnstocktest.top.conf`
- `/etc/nginx/sites-enabled/microtalk.top.conf`
- `/root/WAF_MANAGEMENT.md`
- `/root/WAF_ARCHITECTURE.md`
- `nginx.service`

行为影响：
- `devxxl.top`、`fnstocktest.top`、`microtalk.top` 启用 Nginx CC 频控。
- `financedev.xyz` 保持原状，仍为 `modsecurity off`，本轮未启用 CC。
- 超限请求返回 HTTP 429。
- 未启用 Lua，后续如需更细 IP + URI 维度控制再追加。

验证：
- `nginx -t`：通过。
- `systemctl reload nginx`：成功。
- 正常请求：`web.devxxl.top`、`web.fnstocktest.top`、`web.microtalk.top` 首页均返回 200。
- 并发请求 `web.devxxl.top/wp-login.php` 120 次：9 次 200，111 次 429，命中 `cc_sensitive`。
- `financedev.xyz` 配置中未出现 `limit_req` 或 `limit_conn`。

回滚：
- 备份路径：`/root/waf-backups/stage2-pre-20260429-155935`
- 可从该目录恢复 `/etc/nginx` 和两份文档，然后执行 `nginx -t && systemctl reload nginx`。

备注：
- 这是第二阶段基础 CC 防护，不包含 Lua 高级行为识别。

### 2026-04-29 15:52 CST - 抑制扫描观察类 Telegram 推送

原因：
- 减少扫描探测类告警噪音，尤其是只命中 `54002 Scanner-like path observed` 的观察型事件。

修改的文件或服务：
- `/opt/wafbot/wafbot/log_monitor.py`
- `/root/WAF_MANAGEMENT.md`
- `/root/WAF_ARCHITECTURE.md`
- `wafbot.service`

行为影响：
- 只命中规则 `54002` 的扫描观察事件会继续写入 SQLite，但不再推送 Telegram。
- 如果同一事件还命中其它规则，例如 SQL 注入、XSS、敏感路径拦截、IP 黑白名单等，仍按原逻辑处理和推送。
- WAF 拦截行为、Nginx 转发、CRS 积分和黑白名单行为未改变。

验证：
- `/opt/wafbot/venv/bin/python3 -m py_compile /opt/wafbot/wafbot/log_monitor.py`：通过。
- `systemctl restart wafbot`：成功。
- `systemctl status wafbot`：active (running)，主进程 `/opt/wafbot/venv/bin/python3 /opt/wafbot/run.py`。
- `nginx -t`：未执行，未修改 Nginx 或 ModSecurity 配置。

回滚：
- 备份路径：`/root/waf-backups/manual-20260429-155138`
- 可从该目录恢复 `log_monitor.py` 和两份文档。

备注：
- 这是机器人推送策略变更，不影响 WAF 记录和数据库入库。

### 2026-04-29 15:45 CST - 管理手册改为中文

原因：
- 按要求将 `/root/WAF_MANAGEMENT.md` 改为中文管理文档，便于后续中文运维人员阅读和维护。

修改的文件或服务：
- `/root/WAF_MANAGEMENT.md`

行为影响：
- 仅文档内容语言调整。
- 未修改 WAF、Nginx、ModSecurity、Telegram 机器人、转发、告警、黑名单、白名单或 SQLite 行为。

验证：
- 文档重写后执行 `wc -l`、`grep`、`sed` 检查。
- 不需要执行 `nginx -t`、Nginx reload 或 `wafbot` restart。

回滚：
- 如需恢复英文版，可从 shell 历史或备份中恢复旧内容；当前建议保留中文版本。

备注：
- 未来 WAF 或机器人相关变更仍必须同步更新本文档。
- 架构级行为变化仍应同步更新 `/root/WAF_ARCHITECTURE.md`。

### 2026-04-29 15:42 CST - 创建 WAF 管理手册

原因：
- 创建 WAF 和 Telegram 机器人日常管理文档，记录路径、配置位置、运维命令、告警行为和强制变更记录规则。

修改的文件或服务：
- `/root/WAF_MANAGEMENT.md`

行为影响：
- 未修改 WAF、Nginx、ModSecurity、Telegram 机器人、转发、告警、黑名单、白名单或 SQLite 行为。

验证：
- 文件创建后通过 `sed` 和 `grep` 做了读取检查。
- 文档类变更，不需要重启服务或 reload Nginx。

回滚：
- 如果本文档被其它文档替代，可以删除或替换 `/root/WAF_MANAGEMENT.md`。

备注：
- 后续 WAF 或机器人变更必须在同一次操作会话里更新本文档。
- 架构级行为变化也应同步更新 `/root/WAF_ARCHITECTURE.md`。
