# WAF

Nginx + ModSecurity v3 + OWASP CRS WAF configuration package.

This repository contains the current WAF layout from the source server:

- Nginx entry, site, proxy, security, and CC rate-limit configuration
- ModSecurity engine configuration and local custom rules
- WAF architecture and operations documentation
- Helper scripts for layout verification

Sensitive runtime data is intentionally excluded from this repository, including
Telegram bot secrets, SQLite databases, logs, SSH keys, and Python virtualenvs.

## Layout

```text
nginx/
  nginx.conf
  conf.d/
  nginxconfig.io/
  sites-enabled/

modsec/
  main.conf
  modsecurity.conf
  custom/

docs/
  WAF_ARCHITECTURE.md
  WAF_MANAGEMENT.md

scripts/
  verify.sh
```

## Current Protection Model

- ModSecurity is enabled globally by Nginx.
- OWASP CRS is loaded from `/etc/nginx/modsec/coreruleset-4.24.1`.
- Local controls live under `/etc/nginx/modsec/custom`.
- Stage 2 CC protection uses Nginx `limit_req` and `limit_conn`.
- `devxxl.top`, `fnstocktest.top`, and `microtalk.top` are protected.
- `financedev.xyz` is intentionally configured with `modsecurity off` in the source environment.

Before using this on another server, review and replace:

- domain names
- upstream private IPs
- Cloudflare real IP assumptions
- whitelist and blacklist data
- Stage 2 CC whitelist include sync from modsec/custom/ipwhitelist.data into modsec/custom/ipwhitelist_cc.inc
- log paths
- CRS installation path and version

## Verify

After installing the files into a target server layout, run:

```bash
bash scripts/verify.sh
```

On a live server, also run:

```bash
nginx -t
systemctl reload nginx
```

