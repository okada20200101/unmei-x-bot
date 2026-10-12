#!/usr/bin/env python3
"""
運命の命式 X自動投稿（X APIの従量課金を通さない = ブラウザ操作ルート）
対象アカウント: @unmei_meishiki_（@iching_kobo とは別アカウント・独立運用）

流れ:
  1) 素材サーバーから当日の1本(動画URL + 投稿文2本)を取得
  2) セッション(storage_state)で x.com に入り、動画を添付して1投稿目
  3) 続けて2投稿目をスレッド返信で投稿
  4) 成功したら素材サーバーのカーソルを進める

必要な GitHub Secrets:
  X_STORAGE_STATE / POSTS_ENDPOINT / ADVANCE_ENDPOINT / ADVANCE_TOKEN
注意: Xの画面セレクタ(data-testid)は変わりうる。初回は DRY_RUN=1 で検証する。

改訂メモ (2026-10-12):
  投稿欄 tweetTextarea_0 が「モーダル」と「primaryColumn内のインライン」の2箇所に
  存在するため strict mode violation が発生した。DOM上で primaryColumn 配下でない
  方（＝モーダル側）を選ぶよう JS で明示的に狙う。
"""
import json, os, sys, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HERE = Path(__file__).resolve().parent
DRY = os.environ.get("DRY_RUN", "0") == "1"

FOCUS_COMPOSER_JS = """
() => {
  const els = [...document.querySelectorAll('div[data-testid="tweetTextarea_0"]')];
  if (!els.length) return false;
  const el = els.find(e => !e.closest('[data-testid="primaryColumn"]')) || els[0];
  el.scrollIntoView({block: 'center'});
  el.focus();
  const r = document.createRange(); r.selectNodeContents(el);
  const s = getSelection(); s.removeAllRanges(); s.addRange(r);
  return true;
}
"""

CLICK_POST_JS = """
() => {
  const usable = e => e && e.getAttribute('aria-disabled') !== 'true' && !e.disabled
                      && e.offsetWidth > 0 && e.offsetHeight > 0;
  const pick = tid => {
    const els = [...document.querySelectorAll(`[data-testid="${tid}"]`)];
    return els.find(e => usable(e) && e.closest('[role="dialog"]')) || els.find(usable);
  };
  const el = pick('tweetButton') || pick('tweetButtonInline');
  if (!el) return false;
  el.click();
  return true;
}
"""

UPLOAD_STATE_JS = """
() => {
  const d = document.querySelector('[role="dialog"]');
  if (!d) return 'nodialog';
  if (d.querySelector('[role="progressbar"]')) return 'uploading';
  const b = d.querySelector('[data-testid="tweetButton"]');
  if (!b) return 'nobtn';
  return b.getAttribute('aria-disabled') === 'true' ? 'disabled' : 'ready';
}
"""


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


def fill_composer(page, text):
    """モーダル側の投稿欄を狙って入力する（strict mode violation 回避）"""
    ok = page.evaluate(FOCUS_COMPOSER_JS)
    if not ok:
        # フォールバック: とにかく1つ目
        page.locator('div[data-testid="tweetTextarea_0"]').first.click()
    page.wait_for_timeout(300)
    page.keyboard.type(text, delay=8)


def wait_upload(page, timeout=180):
    """動画アップロード完了（progressbar消滅 & 投稿ボタン有効）を待つ"""
    steps = max(1, timeout // 3)
    for i in range(steps):
        st = page.evaluate(UPLOAD_STATE_JS)
        if st == "ready":
            log("[upload] ready")
            return True
        if i % 5 == 0:
            log("[upload]", st)
        page.wait_for_timeout(3000)
    log("[upload] timeout (続行)")
    return False


def click_post(page):
    ok = page.evaluate(CLICK_POST_JS)
    if not ok:
        page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]').first.click()
        ok = True
    return ok


def post_first(page, video, text):
    page.goto("https://x.com/compose/post", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    page.set_input_files('input[type="file"]', video)
    page.wait_for_timeout(4000)
    fill_composer(page, text)
    wait_upload(page, timeout=180)
    page.wait_for_timeout(1500)
    click_post(page)
    page.wait_for_timeout(9000)


def post_reply(page, handle, text):
    """プロフィールの最新ポストを開いてスレッド返信する（タイムライン依存を回避）"""
    page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    art = page.locator('article[data-testid="tweet"]').first
    art.wait_for(state="visible", timeout=20000)
    art.click()
    page.wait_for_timeout(3000)
    fill_composer(page, text)
    page.wait_for_timeout(1200)
    click_post(page)
    page.wait_for_timeout(7000)


def main():
    state = os.environ.get("X_STORAGE_STATE")
    if not state:
        log("[skip] X_STORAGE_STATE 未設定（@unmei_meishiki_ のCookieをSecretに登録してください）")
        return 0
    (HERE / "storage_state.json").write_text(state, encoding="utf-8")

    item = fetch_json(os.environ["POSTS_ENDPOINT"])
    log("[item]", item.get("n"), item.get("next"))
    handle = os.environ.get("X_HANDLE", "unmei_meishiki_")
    video = str(HERE / "today.mp4")
    download(item["video_url"], video)

    if DRY:
        log("[dry] 取得のみ（投稿しない）")
        return 0

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(storage_state=str(HERE / "storage_state.json"),
                            viewport={"width": 1360, "height": 960},
                            locale="ja-JP", timezone_id="Asia/Tokyo")
        page = ctx.new_page()
        page.goto("https://x.com/home", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        if "/login" in page.url or "i/flow/login" in page.url:
            log("[error] セッションが無効（cookie期限切れ）→ Cookieを再取得してSecretを更新")
            return 1

        # --- 1投稿目（動画つき） ---
        try:
            post_first(page, video, item["post1"])
            log("[post1] 実行")
        except Exception as e:
            log("[error] 1投稿目に失敗:", repr(e))
            page.screenshot(path=str(HERE / "err_post1.png"))
            return 1

        # --- 2投稿目（スレッド返信） ---
        try:
            post_reply(page, handle, item["post2"])
            log("[post2] 実行")
        except PWTimeout as e:
            log("[warn] スレッド返信に失敗:", e)
        except Exception as e:
            log("[warn] スレッド返信に失敗:", repr(e))

        ctx.close()
        b.close()

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
