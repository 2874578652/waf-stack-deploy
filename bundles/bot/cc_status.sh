#!/usr/bin/env bash
set -euo pipefail

LINES="${1:-20000}"
LOGS=(
  /var/log/nginx/devxxl.top.access.log
  /var/log/nginx/fnstocktest.top.access.log
  /var/log/nginx/microtalk.top.access.log
)
ERROR_LOGS=(
  /var/log/nginx/devxxl.top.error.log
  /var/log/nginx/fnstocktest.top.error.log
  /var/log/nginx/microtalk.top.error.log
)

echo "Stage 2 CC status summary"
echo "time=$(date '+%Y-%m-%d %H:%M:%S %Z') lines=${LINES}"
echo

for log in "${LOGS[@]}"; do
  site="$(basename "$log" .access.log)"
  echo "== ${site} access log =="
  if [[ ! -r "$log" ]]; then
    echo "missing_or_unreadable ${log}"
    echo
    continue
  fi

  tail -n "$LINES" "$log" | awk '
    {
      total++
      code=$9
      lrs=""; lcs=""; host=""
      for (i=1; i<=NF; i++) {
        if ($i ~ /^lrs=/) { lrs=substr($i,5) }
        if ($i ~ /^lcs=/) { lcs=substr($i,5) }
        if ($i ~ /^host=/) { host=substr($i,6) }
      }
      if (code == 429 || lrs ~ /REJECTED/ || lcs ~ /REJECTED/) {
        blocked++
      }
    }
    END {
      printf("total=%d cc_or_429=%d\n", total+0, blocked+0)
    }
  '
  echo "top_ips:"
  tail -n "$LINES" "$log" | awk '
    {
      code=$9; lrs=""; lcs=""
      for (i=1; i<=NF; i++) {
        if ($i ~ /^lrs=/) { lrs=substr($i,5) }
        if ($i ~ /^lcs=/) { lcs=substr($i,5) }
      }
      if (code == 429 || lrs ~ /REJECTED/ || lcs ~ /REJECTED/) print $1
    }
  ' | sort | uniq -c | sort -nr | sed -n '1,10p'
  echo "top_uris:"
  tail -n "$LINES" "$log" | awk '
    {
      code=$9; lrs=""; lcs=""
      for (i=1; i<=NF; i++) {
        if ($i ~ /^lrs=/) { lrs=substr($i,5) }
        if ($i ~ /^lcs=/) { lcs=substr($i,5) }
      }
      if (code == 429 || lrs ~ /REJECTED/ || lcs ~ /REJECTED/) print $7
    }
  ' | sort | uniq -c | sort -nr | sed -n '1,10p'
  echo
done

for log in "${ERROR_LOGS[@]}"; do
  site="$(basename "$log" .error.log)"
  echo "== ${site} recent limit warnings =="
  if [[ ! -r "$log" ]]; then
    echo "missing_or_unreadable ${log}"
    echo
    continue
  fi
  grep -E 'limiting requests|limiting connections' "$log" | tail -n 20 || true
  echo
done
