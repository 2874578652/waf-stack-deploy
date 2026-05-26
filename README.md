# WAF Stack Deploy

This directory is a deployment orchestrator for your full WAF stack:

- `waf` repository for Nginx + ModSecurity + custom rules
- `bot` repository for the Telegram management bot

It is designed for rebuilding a new server with one controlled install flow instead of manually copying files from the old machine.

It supports two deployment modes:

1. Repository mode
   Pull `waf` and `bot` from their own repositories.
2. Bundle mode
   Ship exact copies of `waf` and `bot` inside this repository and deploy from one repo only.

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
├── bundles/
│   ├── bot/
│   └── waf/
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
- Or deploys from `bundles/waf` and `bundles/bot` if you choose bundle mode
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

## Fastest Practical One-Command Model

If you want the deployment side to feel truly "one click", use bundle mode.
This repository is now prepared for that path by default.

1. Keep `waf` and `bot` as source repositories for normal development.
2. Before a release, copy the exact deployable contents into:
   - `bundles/waf/`
   - `bundles/bot/`
3. Keep `USE_LOCAL_BUNDLES=1` in `stack.env`

Then a new server only needs:

```bash
git clone <waf-stack-deploy repo>
cd waf-stack-deploy
sudo bash install-stack.sh
```

That reduces deployment-time complexity to:

- one repository
- one secret file for the bot
- one install command

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

## Bundle Mode On A New Server

If this repository already contains `bundles/waf` and `bundles/bot`, you can avoid the extra repository clones.

Default:

```bash
USE_LOCAL_BUNDLES=1
```

Then the deployment path becomes:

```bash
git clone <waf-stack-deploy repo>
cd waf-stack-deploy
cp stack.env.example stack.env
vi stack.env   # usually only BOT_ENV_FILE or branch/path overrides
sudo bash install-stack.sh
```

If you later update the source `waf` or `bot` repositories, refresh the bundled copies before pushing a new deployment release:

```bash
bash scripts/refresh-bundles.sh
git add bundles README.md stack.env.example scripts/
git commit -m "Refresh bundled waf and bot"
git push
```

## Notes

- The WAF repo is still a config package, not a whole OS image.
- `install-stack.sh` assumes a Debian/Ubuntu-like system for package install.
- The WAF config expects CRS under `/etc/nginx/modsec/coreruleset-4.24.1` by default.
- If your upstream `proxy_pass` targets or domains change, update the `waf` repo first.
