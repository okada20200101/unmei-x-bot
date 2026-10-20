#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# --- WAIT_UNTIL: "05:00" が渡されたら、その時刻(JST)まで待ってから投稿 ---
# 早く起動した実行はここで待つ。5:00 を過ぎて起動した場合は待たずに即投稿。
if [ -n "${WAIT_UNTIL:-}" ]; then
  python3 - "$WAIT_UNTIL" <<'PYEOF' 2>&1 | tee -a last_run.log
import sys, time, datetime
hh, mm = [int(x) for x in sys.argv[1].split(":")]
jst = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(jst)
target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
d = (target - now).total_seconds()
if d > 0:
    if d > 21000:            # 5h50m 超は異常（job timeout 360分）
        print("[wait] 待機が長すぎる(%.0fs) → 中止" % d, flush=True); sys.exit(2)
    print("[wait] %.0fs until %s JST" % (d, sys.argv[1]), flush=True)
    time.sleep(d)
print("[wait] start at", datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S JST"), flush=True)
PYEOF
fi

sudo apt-get update -qq >/dev/null 2>&1 || true
sudo apt-get install -y -qq fonts-noto-cjk >/dev/null 2>&1 || echo "[warn] fonts install failed"
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt
python3 -m playwright install --with-deps chromium
python3 -m playwright install chrome || echo "[warn] chrome install skipped; using runner chrome"
# --- 投稿直前ガード: origin/main を直接読み、claims/<date>.lock を原子的に取れた1本だけ投稿 ---
if [ "${DRY_RUN:-0}" != "1" ] && [ "${PROBE:-0}" != "1" ] && [ -n "${GITHUB_RUN_ID:-}" ]; then
  TODAY=$(TZ=Asia/Tokyo date +%F)
  git config user.name  "x-bot"
  git config user.email "x-bot@users.noreply.github.com"
  git fetch origin main -q || true
  git reset --hard origin/main -q || true
  LAST=$(awk 'NR==1{print $1}' automation/x_daily/last_post.txt 2>/dev/null || true)
  echo "[guard2] origin last_post=${LAST:-none} today=$TODAY"
  if [ "$LAST" = "$TODAY" ]; then echo "[guard2] 本日は投稿済み → 中止"; exit 0; fi
  mkdir -p automation/x_daily/claims
  C="automation/x_daily/claims/$TODAY.lock"
  if [ -f "$C" ]; then echo "[guard2] クレーム済み ($C) → 中止"; exit 0; fi
  printf '%s run=%s started=%s\n' "$TODAY" "$GITHUB_RUN_ID" "$(date -u +%FT%TZ)" > "$C"
  git add "$C"
  git commit -q -m "claim $TODAY run $GITHUB_RUN_ID"
  if ! git push origin HEAD:main -q 2>/tmp/push.err; then
    echo "[guard2] クレーム競合で敗退 → 中止"; cat /tmp/push.err; exit 0
  fi
  echo "[guard2] クレーム獲得 → 投稿へ"
fi

python3 daily_run.py 2>&1 | tee -a last_run.log
