#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# --- WAIT_UNTIL: 例 "05:00" が渡されたら、その時刻(JST)まで待ってから投稿 ---
if [ -n "${WAIT_UNTIL:-}" ]; then
  python3 - "$WAIT_UNTIL" <<'PYEOF' 2>&1 | tee -a last_run.log
import sys, time, datetime
hh, mm = [int(x) for x in sys.argv[1].split(":")]
jst = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(jst)
target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
d = (target - now).total_seconds()
if d > 0:
    print("[wait] %.0fs until %s JST" % (d, sys.argv[1]), flush=True)
    time.sleep(d)
print("[wait] start at", datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S JST"), flush=True)
PYEOF
fi

# --- 二重投稿ガード: 直近30分に別の実行があれば skip ---
if [ "${DRY_RUN:-0}" != "1" ] && [ "${PROBE:-0}" != "1" ] && [ -n "${GITHUB_RUN_ID:-}" ]; then
  SINCE=$(date -u -d '-30 minutes' +%Y-%m-%dT%H:%M:%SZ)
  OTHER=$(curl -fsS --max-time 20 -H "Authorization: Bearer ${GITHUB_TOKEN}" -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${GITHUB_REPOSITORY}/actions/runs?created=%3E%3D${SINCE}&per_page=30" \
    | python3 -c "import sys,json,os;cur=os.environ.get('GITHUB_RUN_ID');d=json.load(sys.stdin);print(' '.join(str(x['id']) for x in d.get('workflow_runs',[]) if str(x['id'])!=cur))" 2>/dev/null || true)
  if [ -n "$OTHER" ]; then echo "[skip] another run within 30min: $OTHER"; exit 0; fi
fi
# 日本語フォント（カード描画用・無いと豆腐になる）
sudo apt-get update -qq >/dev/null 2>&1 || true
sudo apt-get install -y -qq fonts-noto-cjk >/dev/null 2>&1 || echo "[warn] fonts install failed"
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt
python3 -m playwright install --with-deps chromium
python3 -m playwright install chrome || echo "[warn] chrome install skipped; using runner chrome"
python3 daily_run.py 2>&1 | tee -a last_run.log
