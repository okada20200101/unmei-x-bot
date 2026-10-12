#!/usr/bin/env python3
"""
運命の命式 X自動投稿（X APIの従量課金を通さない = ブラウザ操作ルート）
対象アカウント: @unmei_meiseki_（@iching_kobo とは別アカウント・独立運用）

流れ:
  1) 素材サーバーから当日の1本(動画URL + 投稿文2本)を取得
  2) セッション(storage_state)で x.com に入り、動画を添付して1投稿目
  3) 続けて2投稿目をスレッド返信で投稿
  4) 成功したら素材サーバーのカーソルを進める

必要な GitHub Secrets:
  X_STORAGE_STATE / POSTS_ENDPOINT / ADVANCE_ENDPOINT / ADVANCE_TOKEN
注意: Xの画面セレクタ(data-testid)は変わりうる。初回は DRY_RUN=1 で検証する。
"""
import json, os, sys, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HERE = Path(__file__).resolve().parent
DRY = os.environ.get("DRY_RUN", "0") == "1"

def log(*a):
    print(*a, flush=True)

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "unmei-bot"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "unmei-bot"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        f.write(r.read())

def post_text(page, text):
    page.locator('div[data-testid="tweetTextarea_0"]').click()
    page.keyboard.type(text, delay=8)

def click_post(page):
    btn = page.locator('[data-testid="tweetButtonInline"], [data-testid="tweetButton"]').first
    btn.wait_for(state="visible", timeout=20000)
    btn.click()

def main():
    state = os.environ.get("X_STORAGE_STATE")
    if not state:
        log("[skip] X_STORAGE_STATE 未設定（@unmei_meiseki_ のCookieをSecretに登録してください）"); return 0
    (HERE / "storage_state.json").write_text(state, encoding="utf-8")

    item = fetch_json(os.environ["POSTS_ENDPOINT"])
    log("[item]", item.get("n"), item.get("next"))
    video = str(HERE / "today.mp4")
    download(item["video_url"], video)

    if DRY:
        log("[dry] 取得のみ（投稿しない）"); return 0

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox"])
        ctx = b.new_context(storage_state=str(HERE / "storage_state.json"),
                            viewport={"width": 1360, "height": 960},
                            locale="ja-JP", timezone_id="Asia/Tokyo")
        page = ctx.new_page()
        page.goto("https://x.com/home", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        if "/login" in page.url:
            log("[error] セッションが無効（cookie期限切れ）→ Cookieを再取得してSecretを更新"); return 1

        # --- 1投稿目（動画つき） ---
        page.goto("https://x.com/compose/post", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.set_input_files('input[type="file"]', video)
        page.wait_for_timeout(8000)   # 動画アップロード完了待ち
        post_text(page, item["post1"])
        page.wait_for_timeout(1500)
        click_post(page)
        page.wait_for_timeout(8000)

        # --- 2投稿目（スレッド返信） ---
        page.goto("https://x.com/home", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        try:
            page.locator('article[data-testid="tweet"]').first.click()
            page.wait_for_timeout(2500)
            page.locator('div[data-testid="tweetTextarea_0"]').first.click()
            page.keyboard.type(item["post2"], delay=8)
            page.wait_for_timeout(1200)
            click_post(page)
            page.wait_for_timeout(6000)
        except PWTimeout as e:
            log("[warn] スレッド返信に失敗:", e)

        ctx.close(); b.close()

    adv = os.environ.get("ADVANCE_ENDPOINT")
    if adv:
        req = urllib.request.Request(adv, method="POST",
              headers={"x-token": os.environ.get("ADVANCE_TOKEN", "")})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                log("[advance]", r.read().decode()[:120])
        except Exception as e:
            log("[warn] advance失敗:", e)
    return 0

if __name__ == "__main__":
    sys.exit(main())
