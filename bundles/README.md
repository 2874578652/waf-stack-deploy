# Bundled Deployment Sources

This directory holds exact deployable copies of the two runtime repositories so a new server can deploy from one repository only.

Current bundle contents:

- `waf/`
  - Source repository: `2874578652/waf`
  - Commit: `82a7eed`
  - Commit message: `Sync live WAF config through 2026-05-21`
- `bot/`
  - Source repository: `2874578652/bot`
  - Commit: `3a83ae5`
  - Commit message: `Initial deployable wafbot sync`

When `USE_LOCAL_BUNDLES=1`, `install-stack.sh` deploys from these directories instead of cloning `waf` and `bot` during install.

To refresh these bundles after updating the source repositories, run:

```bash
bash scripts/refresh-bundles.sh
```
