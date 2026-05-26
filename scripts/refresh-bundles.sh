#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STACK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

WAF_SOURCE_DIR="${WAF_SOURCE_DIR:-${STACK_ROOT}/../waf-github-local}"
BOT_SOURCE_DIR="${BOT_SOURCE_DIR:-${STACK_ROOT}/../bot-github-local}"
WAF_BUNDLE_DIR="${STACK_ROOT}/bundles/waf"
BOT_BUNDLE_DIR="${STACK_ROOT}/bundles/bot"
BUNDLE_README="${STACK_ROOT}/bundles/README.md"

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required command: $1" >&2
        exit 1
    }
}

need_cmd git
need_cmd rsync

[[ -d "${WAF_SOURCE_DIR}/.git" ]] || {
    echo "Missing WAF source repository: ${WAF_SOURCE_DIR}" >&2
    exit 1
}
[[ -d "${BOT_SOURCE_DIR}/.git" ]] || {
    echo "Missing bot source repository: ${BOT_SOURCE_DIR}" >&2
    exit 1
}

mkdir -p "${WAF_BUNDLE_DIR}" "${BOT_BUNDLE_DIR}"

rsync -a --delete --exclude '.git' "${WAF_SOURCE_DIR}/" "${WAF_BUNDLE_DIR}/"
rsync -a --delete --exclude '.git' --exclude '__pycache__' "${BOT_SOURCE_DIR}/" "${BOT_BUNDLE_DIR}/"

waf_commit="$(git -C "${WAF_SOURCE_DIR}" rev-parse --short HEAD)"
waf_subject="$(git -C "${WAF_SOURCE_DIR}" log -1 --pretty=%s)"
bot_commit="$(git -C "${BOT_SOURCE_DIR}" rev-parse --short HEAD)"
bot_subject="$(git -C "${BOT_SOURCE_DIR}" log -1 --pretty=%s)"

cat > "${BUNDLE_README}" <<EOF
# Bundled Deployment Sources

This directory holds exact deployable copies of the two runtime repositories so a new server can deploy from one repository only.

Current bundle contents:

- \`waf/\`
  - Source repository: \`2874578652/waf\`
  - Commit: \`${waf_commit}\`
  - Commit message: \`${waf_subject}\`
- \`bot/\`
  - Source repository: \`2874578652/bot\`
  - Commit: \`${bot_commit}\`
  - Commit message: \`${bot_subject}\`

When \`USE_LOCAL_BUNDLES=1\`, \`install-stack.sh\` deploys from these directories instead of cloning \`waf\` and \`bot\` during install.

To refresh these bundles after updating the source repositories, run:

\`\`\`bash
bash scripts/refresh-bundles.sh
\`\`\`
EOF

echo "Bundles refreshed:"
echo "  waf -> ${waf_commit}"
echo "  bot -> ${bot_commit}"
