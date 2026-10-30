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
    log "[guard] 本日($TODAY)は投稿済み → 即終了"; exit 0
  fi
fi

# 3) 排他
CLAIMED=0
if [ "${DRY_RUN:-0}" = "1" ] || [ "${PROBE:-0}" = "1" ]; then
  log "[guard] 検証モード → 排他スキップ"
else
  OUT=$(bash "$A/claim.sh" "$TODAY" 2>&1 || true)
  printf '%s\n' "$OUT" | tee -a "$A/last_run.log"
  VERDICT=$(printf '%s\n' "$OUT" | grep -E '^(WON|POSTED|BUSY|LOST)$' | tail -n1)
  case "$VERDICT" in
    WON) CLAIMED=1; log "[guard] 排他確保" ;;
    POSTED) exit 0 ;;
    *) log "[guard] verdict=${VERDICT} → 即終了"; exit 0 ;;
  esac
fi

# 4) 依存（投稿する1本だけが払う）
sudo apt-get update -qq >/dev/null 2>&1 || true
sudo apt-get install -y -qq fonts-noto-cjk xvfb >/dev/null 2>&1 || echo "[warn] fonts failed"
if ! command -v xvfb-run >/dev/null 2>&1; then export HEADFUL=0; log "[warn] xvfb無し → headlessで実行"; fi
python3 -m pip install --quiet --disable-pip-version-check -r "$A/requirements.txt"
python3 -m playwright install --with-deps chromium
python3 -m playwright install chrome || echo "[warn] chrome skipped"

# 5) 発射時刻まで待つ（インストール後に待つので待機は数分）
if [ -n "${WAIT_UNTIL:-}" ]; then
  python3 - "$WAIT_UNTIL" <<'PYEOF' 2>&1 | tee -a "$A/last_run.log"
import sys, time, datetime
p=[int(x) for x in sys.argv[1].split(":")]
hh,mm = p[0],p[1]; ss = p[2] if len(p)>2 else 0
jst=datetime.timezone(datetime.timedelta(hours=9))
now=datetime.datetime.now(jst)
t=now.replace(hour=hh,minute=mm,second=ss,microsecond=0)
d=(t-now).total_seconds()
if d>16200:
    print(f"[wait] 待機過大({d:.0f}s) → 撤退"); sys.exit(3)
if d>0:
    print(f"[wait] {d:.0f}s until {sys.argv[1]} JST",flush=True); time.sleep(d)
print("[wait] release at",datetime.datetime.now(jst).strftime("%H:%M:%S JST"),flush=True)
PYEOF
fi

# 6) 投稿（3回まで自動再試行。1回の失敗で日を落とさない）
XVFB=""
if command -v xvfb-run >/dev/null 2>&1; then
  XVFB="xvfb-run -a"
  log "[cf] 実Chromeをheadful(Xvfb)で起動 → Cloudflare検証を通過させる"
fi
POSTED=0
RC=1
TRY=1
while [ "$TRY" -le 3 ]; do
  log "[post] attempt ${TRY}/3"
  set +e
  $XVFB python3 "$A/daily_run.py" 2>&1 | tee -a "$A/last_run.log"
  RC=${PIPESTATUS[0]}
  set -e
  if grep -q "\[capture\] tweet id" "$A/last_run.log"; then POSTED=1; break; fi
  if [ "$TRY" -lt 3 ]; then log "[post] 失敗 → 90秒後に再試行"; sleep 90; fi
  TRY=$((TRY+1))
done

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
  exit 0
fi

log "[post] 3回とも不成立 → クレーム返却（次の時間帯が引き継ぐ）"
if [ "$CLAIMED" = "1" ]; then
  bash "$A/release.sh" "$TODAY" 2>&1 | tee -a "$A/last_run.log" || true
fi
exit "$RC"
