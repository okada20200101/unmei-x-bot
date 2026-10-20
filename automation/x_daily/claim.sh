#!/usr/bin/env bash
# 二重投稿の排他。最終行に WON / POSTED / BUSY / LOST のいずれか1語を出す。
#   WON    : この実行が投稿してよい（排他取得に成功）
#   POSTED : 本日はすでに投稿済み
#   BUSY   : 別の実行が投稿処理中（終わるまで待つ）
#   LOST   : 同時実行に敗退（＝勝った側が投稿する）
set -uo pipefail
KEY="${1:?usage: claim.sh <YYYY-MM-DD|test:name>}"
cd "$(dirname "$0")/../.."

git config user.name  "x-bot"
git config user.email "x-bot@users.noreply.github.com"
git fetch origin main -q || true
git reset --hard origin/main -q || true

api_status() {  # $1=run id → queued|in_progress|completed|unknown
  [ -n "${1:-}" ] || { echo unknown; return; }
  curl -fsS --max-time 20 -H "Authorization: Bearer ${GITHUB_TOKEN:-}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${GITHUB_REPOSITORY}/actions/runs/$1" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin).get("status") or "unknown")' 2>/dev/null || echo unknown
}

if [ "${KEY#test:}" != "$KEY" ]; then
  C="automation/x_daily/claims/_test/${KEY#test:}.lock"
else
  LAST=$(awk 'NR==1{print $1}' automation/x_daily/last_post.txt 2>/dev/null || true)
  echo "[claim] last_post=${LAST:-none} key=$KEY"
  if [ "$LAST" = "$KEY" ]; then echo "[claim] 本日は投稿済み"; echo POSTED; exit 0; fi
  C="automation/x_daily/claims/$KEY.lock"
fi

if [ -f "$C" ]; then
  RID=$(sed -n 's/.*run=\([0-9][0-9]*\).*/\1/p' "$C" | head -n1)
  ST=$(api_status "$RID")
  echo "[claim] 既存ロック run=${RID:-?} status=$ST"
  case "$ST" in
    in_progress|queued|waiting|pending|requested)
      echo "[claim] 先行実行が進行中 → 待つ"; echo BUSY; exit 0 ;;
    *) echo "[claim] 先行実行は $ST で未投稿 → 引き継ぐ" ;;
  esac
fi

mkdir -p "$(dirname "$C")"
printf 'key=%s run=%s started=%s\n' "$KEY" "${GITHUB_RUN_ID:-local}" "$(date -u +%FT%TZ)" > "$C"
git add "$C"
git commit -q -m "claim $KEY run ${GITHUB_RUN_ID:-local}" || true
if ! git push origin HEAD:main -q 2>/tmp/claim_push.err; then
  echo "[claim] 敗退（他が先に取得）"; sed -n '1,3p' /tmp/claim_push.err; echo LOST; exit 0
fi
echo "[claim] 取得した key=$KEY run=${GITHUB_RUN_ID:-local}"; echo WON
