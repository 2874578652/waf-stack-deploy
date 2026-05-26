# WAF Stack Deploy

This directory is a deployment orchestrator for your full WAF stack:

- `waf` repository for Nginx + ModSecurity + custom rules
- `bot` repository for the Telegram management bot

It is designed for rebuilding a new server with one controlled install flow instead of manually copying files from the old machine.

## Goal

On a new server, the final operator flow should be:

1. Prepare deploy keys for the private repositories.
2. Copy a real bot `.env` file onto the new server.
3. Edit one stack config file.
4. Run one install command.

Example:

```bash
cp stack.env.example stack.env
vi stack.env
sudo bash install-stack.sh
```

## Repository Layout

```text
waf-stack-deploy/
├── install-stack.sh
├── stack.env.example
├── docs/
│   └── private-repo-ssh-config.example
└── scripts/
    ├── check-stack.sh
    ├── common.sh
    ├── install-bot.sh
    └── install-waf.sh
```

## What This Solves

- Installs system packages needed by the WAF and bot
- Clones or updates the `waf` and `bot` repositories
- Installs or updates OWASP CRS into the path expected by your WAF config
- Syncs WAF repo files into `/etc/nginx` and `/etc/nginx/modsec`
- Installs the bot into `/opt/wafbot`
- Optionally copies a prepared real bot `.env` into place
- Runs `nginx -t`, Python compile checks, and service status checks
- Keeps timestamped backups under `/root/waf-stack-backups`

## Recommended Model

Keep three repositories:

1. `waf`
   Holds Nginx, ModSecurity, custom rules, docs.
2. `bot`
   Holds bot code, `wafbot.service`, `.env.example`, install scripts.
3. `waf-stack-deploy`
   Holds only deployment orchestration and machine bootstrap logic.

This separation keeps runtime secrets out of Git while still letting you rebuild a machine quickly.

## Private Repository Deployment

If `waf` and `bot` are private, use one deploy key per repository and SSH host aliases.

See [private-repo-ssh-config.example](docs/private-repo-ssh-config.example).

Typical clone aliases:

```bash
git clone git@github-waf:2874578652/waf.git
git clone git@github-bot:2874578652/bot.git
```

## Bot Secrets

Do not store the real bot `.env` in Git.

Instead:

1. Keep a real `.env` file in a secure path on the target host, for example:
   `/root/secrets/wafbot.env`
2. Set `BOT_ENV_FILE=/root/secrets/wafbot.env` in `stack.env`
3. Let `install-stack.sh` copy it into `/opt/wafbot/.env`

That gives you one-shot deployment without exposing `BOT_TOKEN`, admin IDs, or chat IDs in Git history.

## First Run On A New Server

1. Prepare deploy keys under `~/.ssh/`.
2. Add SSH config aliases for `github-waf` and `github-bot`.
3. Put the real bot env file on disk, for example:

```bash
mkdir -p /root/secrets
vi /root/secrets/wafbot.env
chmod 600 /root/secrets/wafbot.env
```

4. Edit stack config:

```bash
cp stack.env.example stack.env
vi stack.env
```

5. Run install:

```bash
sudo bash install-stack.sh
```

## Notes

- The WAF repo is still a config package, not a whole OS image.
- `install-stack.sh` assumes a Debian/Ubuntu-like system for package install.
- The WAF config expects CRS under `/etc/nginx/modsec/coreruleset-4.24.1` by default.
- If your upstream `proxy_pass` targets or domains change, update the `waf` repo first.

