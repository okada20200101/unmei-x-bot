#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# --- 二重投稿ガード: 今日(JST)すでに投稿済みなら何もしない ---
if [ "${DRY_RUN:-0}" != "1" ] && [ "${PROBE:-0}" != "1" ]; then
  if curl -fsS --max-time 20 "https://unmei-x-trigger.t-okada-a39.workers.dev/posted_today" | grep -q '"posted":true'; then
    echo "[skip] already posted today (JST)"
    exit 0
  fi
fi
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt
python3 -m playwright install --with-deps chromium
python3 -m playwright install chrome || echo "[warn] chrome install skipped; using runner chrome"
python3 daily_run.py 2>&1 | tee -a last_run.log
