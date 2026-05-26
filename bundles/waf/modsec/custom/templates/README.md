# Custom WAF Rule Templates

Files in this directory are examples only. They are not loaded by Nginx because
`/etc/nginx/modsec/main.conf` includes only `/etc/nginx/modsec/custom/*.conf`.

Use these rules for future precise controls:

- Prefer data files for lists that the Telegram bot may manage later.
- Start application-dependent rules as `pass,log` before changing to `deny`.
- Keep custom rule IDs in the documented range for each file.
- Always run `nginx -t` before reloading Nginx.
- Update `/root/WAF_ARCHITECTURE.md` after any rule or behavior change.
