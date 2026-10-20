#!/usr/bin/env bash
# 二重投稿の排他。claims/<key>.lock を git push で勝ち取った1本だけが投稿を続行する。
set -uo pipefail
KEY="${1:?usage: claim.sh <YYYY-MM-DD|test:name>}"
cd "$(dirname "$0")/../.."
git config user.name  "x-bot"
git config user.email "x-bot@users.noreply.github.com"
git fetch origin main -q || true
git reset --hard origin/main -q || true
if [ "${KEY#test:}" != "$KEY" ]; then
  C="automation/x_daily/claims/_test/${KEY#test:}.lock"
else
  LAST=$(awk 'NR==1{print $1}' automation/x_daily/last_post.txt 2>/dev/null || true)
  echo "[claim] origin last_post=${LAST:-none} key=$KEY"
  if [ "$LAST" = "$KEY" ]; then echo "[claim] 本日は投稿済み → 中止"; exit 0; fi
  C="automation/x_daily/claims/$KEY.lock"
fi
if [ -f "$C" ]; then echo "[claim] 既にクレーム済み ($C) → 中止"; exit 0; fi
mkdir -p "$(dirname "$C")"
printf 'key=%s run=%s started=%s\n' "$KEY" "${GITHUB_RUN_ID:-local}" "$(date -u +%FT%TZ)" > "$C"
git add "$C"
git commit -q -m "claim $KEY run ${GITHUB_RUN_ID:-local}"
if ! git push origin HEAD:main -q 2>/tmp/claim_push.err; then
  echo "[claim] LOST key=$KEY run=${GITHUB_RUN_ID:-local}"; sed -n '1,6p' /tmp/claim_push.err; exit 0
fi
echo "[claim] WON key=$KEY run=${GITHUB_RUN_ID:-local}"
