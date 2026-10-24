#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
A=automation/x_daily
TODAY=$(TZ=Asia/Tokyo date +%F)
: > "$A/last_run.log"
log(){ printf '%s\n' "$*" | tee -a "$A/last_run.log"; }

# 1) 本日すでに投稿済み → 即終了
if [ "${DRY_RUN:-0}" != "1" ] && [ "${PROBE:-0}" != "1" ]; then
  if [ -f "$A/last_post.txt" ] && [ "$(cut -d' ' -f1 "$A/last_post.txt")" = "$TODAY" ]; then
    log "[guard] 本日($TODAY)は投稿済み → 即終了"
    exit 0
  fi
fi

# 2) 投稿窓ゲート（待機はしない。窓の外は即終了）
HM=$(TZ=Asia/Tokyo date +%H%M); HM=$((10#$HM))
if [ "${EVENT_NAME:-schedule}" = "schedule" ] && [ "$HM" -lt 500 ]; then
  log "[gate] $(TZ=Asia/Tokyo date +%H:%M) JST は窓(05:00)より前 → 即終了"
  exit 0
fi

# 3) 排他（秒で終わる）
CLAIMED=0
if [ "${DRY_RUN:-0}" = "1" ] || [ "${PROBE:-0}" = "1" ]; then
  log "[guard] 検証モード → 排他スキップ"
else
  OUT=$(bash "$A/claim.sh" "$TODAY" 2>&1 || true)
  printf '%s\n' "$OUT" | tee -a "$A/last_run.log"
  VERDICT=$(printf '%s\n' "$OUT" | grep -E '^(WON|POSTED|BUSY|LOST)$' | tail -n1)
  case "$VERDICT" in
    WON)  CLAIMED=1; log "[guard] 排他確保" ;;
    POSTED) exit 0 ;;
    *) log "[guard] verdict=${VERDICT} → 即終了"; exit 0 ;;
  esac
fi

# 4) 依存（投稿する1本だけが払う）
sudo apt-get update -qq >/dev/null 2>&1 || true
sudo apt-get install -y -qq fonts-noto-cjk >/dev/null 2>&1 || echo "[warn] fonts failed"
python3 -m pip install --quiet --disable-pip-version-check -r "$A/requirements.txt"
python3 -m playwright install --with-deps chromium
python3 -m playwright install chrome || echo "[warn] chrome skipped"

# 5) 投稿
set +e
python3 "$A/daily_run.py" 2>&1 | tee -a "$A/last_run.log"
RC=${PIPESTATUS[0]}
set -e

POSTED=0
grep -q "\[capture\] tweet id" "$A/last_run.log" && POSTED=1

if [ "$POSTED" = "1" ]; then
  NOW=$(TZ=Asia/Tokyo date +'%F %H:%M')
  echo "${NOW%% *} ${EVENT_NAME:-schedule}" > "$A/last_post.txt"
  echo "$NOW event=${EVENT_NAME:-schedule} run=${GITHUB_RUN_ID:-?}" > "$A/last_trigger.txt"
  POST_TIME="${NOW##* }" python3 "$A/record.py" 2>&1 | tee -a "$A/last_run.log" || true
  git config user.name "x-bot"; git config user.email "x-bot@users.noreply.github.com"
  touch "$A/history.jsonl"
  git add -A "$A" STATUS.md
  git commit -q -m "post $(cat "$A/last_post.txt")" || echo "[record] 差分なし"
  for i in 1 2 3 4 5; do
    git push origin HEAD:main -q 2>/dev/null && { log "[record] マーカー確定"; break; }
    git fetch origin main -q || true
    git rebase --autostash origin/main -q >/dev/null 2>&1 || true
    sleep 3
  done
elif [ "$CLAIMED" = "1" ]; then
  log "[guard] 投稿不成立 → クレーム返却"
  bash "$A/release.sh" "$TODAY" 2>&1 | tee -a "$A/last_run.log" || true
fi
exit "$RC"
