#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
TODAY=$(TZ=Asia/Tokyo date +%F)

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
    if d > 21000:
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

# --- 投稿直前ガード（唯一の排他） ---
# 投稿の直前に origin/main を読み直し、claims/<JST日付>.lock を git push で
# 勝ち取った1本だけが投稿を続行する。push はサーバー側で直列化されるため、
# 何本同時に起動しても「投稿まで到達するのは1本」になる。
if [ "${DRY_RUN:-0}" != "1" ] && [ "${PROBE:-0}" != "1" ] && [ -n "${GITHUB_RUN_ID:-}" ]; then
  OUT=$(bash ./claim.sh "$TODAY" 2>&1)
  echo "$OUT" | tee -a last_run.log
  case "$OUT" in
    *"[claim] WON"*) echo "[guard2] クレーム獲得 → 投稿へ" ;;
    *)               echo "[guard2] クレームを取れず → 投稿せず終了"; exit 0 ;;
  esac
fi

set +e
python3 daily_run.py 2>&1 | tee -a last_run.log
RC=${PIPESTATUS[0]}
set -e

# 投稿前に失敗した場合だけクレームを返却する（投稿済みなら返却しない＝二重投稿を防ぐ）
if [ "$RC" -ne 0 ]; then
  if grep -q "\[capture\] tweet id" last_run.log; then
    echo "[guard2] 失敗だが投稿は成立 → クレーム保持（再投稿しない）"
  else
    echo "[guard2] 投稿前に失敗 → クレームを返却"
    git rm -q --ignore-unmatch "automation/x_daily/claims/${TODAY}.lock" || true
    git commit -q -m "release claim ${TODAY} (failed before post)" || true
    git push origin HEAD:main -q || true
  fi
fi
exit "$RC"
