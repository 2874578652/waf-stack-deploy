#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required=(
  "nginx/nginx.conf"
  "nginx/conf.d/00-waf-cc-limit-zones.conf"
  "modsec/main.conf"
  "modsec/modsecurity.conf"
  "modsec/custom/01-ip-whitelist.conf"
  "modsec/custom/ipwhitelist_cc.inc"
  "modsec/custom/02-ip-blacklist.conf"
  "modsec/custom/07-ua-control.conf"
  "modsec/custom/10-risky-path-rules.conf"
  "docs/WAF_ARCHITECTURE.md"
  "docs/WAF_MANAGEMENT.md"
)

missing=0
for path in "${required[@]}"; do
  if [[ ! -e "${ROOT}/${path}" ]]; then
    echo "missing: ${path}"
    missing=1
  fi
done

if [[ "${missing}" -ne 0 ]]; then
  exit 1
fi

echo "layout ok: ${ROOT}"

