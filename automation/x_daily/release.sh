#!/usr/bin/env bash
# 投稿に至らなかった実行がクレームを返却する（次に来た実行が引き継げるように）
set -uo pipefail
KEY="${1:?usage: release.sh <YYYY-MM-DD>}"
cd "$(dirname "$0")/../.."
git config user.name  "x-bot"
git config user.email "x-bot@users.noreply.github.com"
git fetch origin main -q || true
git reset --hard origin/main -q || true
F="automation/x_daily/claims/$KEY.lock"
git rm -q --ignore-unmatch "$F" || true
git commit -q -m "release claim $KEY run ${GITHUB_RUN_ID:-local}" || true
for i in 1 2 3; do
  if git push origin HEAD:main -q 2>/dev/null; then echo "[release] 返却した $KEY"; exit 0; fi
  git fetch origin main -q || true; git rebase --autostash origin/main -q >/dev/null 2>&1 || true
  sleep 3
done
echo "[release] 返却に失敗（ロックは残る）"
