#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
TODAY=$(TZ=Asia/Tokyo date +%F)

log(){ printf '%s\n' "$*" | tee -a last_run.log; }

# ============================================================
# 0) 本日すでに投稿済みなら、待機もインストールもせず即終了
#    （保険cronが数十秒で終わるようにする。実行枠の浪費を止める）
# ============================================================
if [ "${DRY_RUN:-0}" != "1" ] && [ "${PROBE:-0}" != "1" ]; then
  if [ -f last_post.txt ] && [ "$(cut -d' ' -f1 last_post.txt)" = "$TODAY" ]; then
    log "[guard] 本日($TODAY)は投稿済み → 即終了（待機しない）"
    exit 0
  fi
fi

# ============================================================
# 1) 排他を「待機より先に」取る。勝った1本だけが 05:00 まで待つ。
#    負けた側は即終了するので、6本が同時に5時間待つ事態にならない。
# ============================================================
CLAIMED=0
if [ "${DRY_RUN:-0}" = "1" ] || [ "${PROBE:-0}" = "1" ]; then
  log "[guard] 検証モード → 排他取得をスキップ"
else
  VERDICT=""
  OUT=$(bash ./claim.sh "$TODAY" 2>&1 || true)
  printf '%s\n' "$OUT" | tee -a last_run.log
  VERDICT=$(printf '%s\n' "$OUT" | grep -E '^(WON|POSTED|BUSY|LOST)$' | tail -n1)
  case "$VERDICT" in
    WON)
      CLAIMED=1
      log "[guard] 排他確保（この実行が本日の投稿を担当）" ;;
    POSTED)
      log "[guard] 本日は投稿済み → 終了"
      exit 0 ;;
    BUSY)
      log "[guard] 先行実行が稼働中 → この実行は即終了（待機しない）"
      exit 0 ;;
    LOST)
      log "[guard] 他が投稿を担当 → この実行は即終了（待機しない）"
      exit 0 ;;
    *)
      log "[guard] 判定不能（verdict='${VERDICT}'）→ 何もせず終了（次のcronが引き継ぐ）"
      exit 0 ;;
  esac
fi

# ============================================================
# 2) 05:00 まで待つ（排他を取った1本だけ。最大5時間30分）
# ============================================================
if [ -n "${WAIT_UNTIL:-}" ]; then
  python3 - "$WAIT_UNTIL" <<'PYEOF' 2>&1 | tee -a last_run.log
import sys, time, datetime
hh, mm = [int(x) for x in sys.argv[1].split(":")]
jst = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(jst)
target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
d = (target - now).total_seconds()
if d > 0:
    if d > 19800:
        print("[wait] 待機が長すぎる(%.0fs) → この実行は撤退" % d, flush=True); sys.exit(3)
    print("[wait] %.0fs until %s JST" % (d, sys.argv[1]), flush=True)
    time.sleep(d)
print("[wait] start at", datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S JST"), flush=True)
PYEOF
fi

# ============================================================
# 3) 依存インストール（待機の後。無駄な消費を避ける）
# ============================================================
sudo apt-get update -qq >/dev/null 2>&1 || true
sudo apt-get install -y -qq fonts-noto-cjk >/dev/null 2>&1 || echo "[warn] fonts install failed"
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt
python3 -m playwright install --with-deps chromium
python3 -m playwright install chrome || echo "[warn] chrome install skipped; using runner chrome"

# ============================================================
# 4) 投稿
# ============================================================
set +e
python3 daily_run.py 2>&1 | tee -a last_run.log
RC=${PIPESTATUS[0]}
set -e

POSTED=0
grep -q "\[capture\] tweet id" last_run.log && POSTED=1

if [ "$POSTED" = "1" ]; then
  # 投稿が成立した瞬間にマーカーを確定・push（後続失敗で二重投稿にしない）
  NOW=$(TZ=Asia/Tokyo date +'%F %H:%M')
  echo "${NOW%% *} ${EVENT_NAME:-schedule}" > automation/x_daily/last_post.txt
  echo "$NOW event=${EVENT_NAME:-schedule} run=${GITHUB_RUN_ID:-?} actor=${GITHUB_ACTOR:-?}" > automation/x_daily/last_trigger.txt
  POST_TIME="${NOW##* }" python3 automation/x_daily/record.py 2>&1 | tee -a last_run.log || true
  git config user.name  "x-bot"
  git config user.email "x-bot@users.noreply.github.com"
  touch automation/x_daily/history.jsonl
  git add -A automation/x_daily STATUS.md
  git commit -q -m "post $(cat automation/x_daily/last_post.txt)" || echo "[record] 差分なし"
  for i in 1 2 3 4 5; do
    if git push origin HEAD:main -q 2>/dev/null; then echo "[record] マーカー確定 push 成功"; break; fi
    git fetch origin main -q || true
    git rebase --autostash origin/main -q >/dev/null 2>&1 || true
    sleep 3
  done
elif [ "$CLAIMED" = "1" ]; then
  echo "[guard] 投稿が成立していない → クレームを返却（次の実行が引き継ぐ）"
  bash ./release.sh "$TODAY" 2>&1 | tee -a last_run.log || true
fi
exit "$RC"
