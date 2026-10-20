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
python3 daily_run.py 2>&1 | tee -a last_run.log
