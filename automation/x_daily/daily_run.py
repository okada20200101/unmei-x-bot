#!/usr/bin/env python3
"""
運命の命式 X自動投稿（X APIの従量課金を通さない = ブラウザ操作ルート）
対象アカウント: @unmei_meishiki_（@iching_kobo とは別アカウント・独立運用）

流れ:
  1) 素材サーバーから当日の1本(動画URL + 投稿文2本)を取得
  2) セッション(storage_state)で x.com に入り、動画を添付して1投稿目
  3) プロフィールの最新ポストを開き、返信ボタンから2投稿目（スレッド）
  4) 成功したら素材サーバーのカーソルを進める

必要な GitHub Secrets:
  X_STORAGE_STATE / POSTS_ENDPOINT / ADVANCE_ENDPOINT / ADVANCE_TOKEN

改訂メモ (2026-10-12):
  - 投稿欄 tweetTextarea_0 が「モーダル」と「primaryColumn内インライン」の2箇所に
    存在し strict mode violation になったため、モーダル側を JS で明示的に狙う。
  - 動画待ちは「添付サムネイルの出現」を実シグナルとして判定（progressbar誤検知対策）。
  - スレッド返信はプロフィールの最新ツイートの返信ボタンから行う方式に変更。
"""
import json, os, sys, time, urllib.request
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

MEDIA_JS = """
() => {
  const d = document.querySelector('[role="dialog"]');
  const scope = d || document;
  const att = scope.querySelector('[data-testid="attachments"]');
  if (att && att.querySelector('img, video')) return 'ready';
  if (att) return 'attached';
  return scope.querySelector('[role="progressbar"]') ? 'uploading' : 'none';
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
    ok = page.evaluate(FOCUS_COMPOSER_JS)
    if not ok:
        page.locator('div[data-testid="tweetTextarea_0"]').first.click()
    page.wait_for_timeout(300)
    page.keyboard.type(text, delay=8)


def wait_media(page, timeout=180):
    """添付サムネイル(img/video)の出現を待つ。出れば完了。"""
    steps = max(1, timeout // 3)
    for i in range(steps):
        st = page.evaluate(MEDIA_JS)
        if st in ("ready", "attached"):
            log("[media]", st)
            page.wait_for_timeout(2000)
            return True
        if i % 4 == 0:
            log("[media]", st)
        page.wait_for_timeout(3000)
    log("[media] timeout (続行)")
    return False


def click_post(page):
    ok = page.evaluate(CLICK_POST_JS)
    if not ok:
        page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]').first.click()


def post_first(page, video, text):
    page.goto("https://x.com/compose/post", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    page.set_input_files('input[type="file"]', video)
    page.wait_for_timeout(3000)
    wait_media(page, timeout=180)
    fill_composer(page, text)
    page.wait_for_timeout(1500)
    click_post(page)
    page.wait_for_timeout(10000)


def post_reply(page, handle, text):
    """プロフィールの最新ポストを開き、返信ボタンからスレッド2投目"""
    page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('article[data-testid="tweet"]', timeout=45000)
    except PWTimeout:
        log("[reply] 再読込")
        page.goto(f"https://x.com/{handle}", wait_until="load")
        page.wait_for_selector('article[data-testid="tweet"]', timeout=45000)
    page.wait_for_timeout(2500)
    rb = page.locator('article[data-testid="tweet"] [data-testid="reply"]').first
    rb.wait_for(state="visible", timeout=20000)
    rb.click()
    page.wait_for_timeout(3500)
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
        if "i/flow/login" in page.url or page.url.rstrip("/").endswith("/login"):
            log("[error] セッションが無効（cookie期限切れ）→ Cookieを再取得してSecretを更新")
            return 1

        try:
            post_first(page, video, item["post1"])
            log("[post1] 実行")
        except Exception as e:
            log("[error] 1投稿目に失敗:", repr(e)[:300])
            try:
                page.screenshot(path=str(HERE / "err_post1.png"))
            except Exception:
                pass
            return 1

        try:
            post_reply(page, handle, item["post2"])
            log("[post2] 実行")
        except Exception as e:
            log("[warn] スレッド返信に失敗:", repr(e)[:200])

        ctx.close()
        b.close()

    adv = os.environ.get("ADVANCE_ENDPOINT")
    if adv:
        for attempt in range(4):
            req = urllib.request.Request(adv, method="POST",
                                         headers={"x-token": os.environ.get("ADVANCE_TOKEN", "")})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    log("[advance]", r.read().decode()[:120])
                break
            except Exception as e:
                log("[warn] advance失敗", attempt + 1, repr(e)[:120])
                time.sleep(5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
