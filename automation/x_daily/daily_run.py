#!/usr/bin/env python3
"""
運命の命式 X自動投稿（X APIの従量課金を通さない = ブラウザ操作ルート）
対象アカウント: @unmei_meishiki_（@iching_kobo とは別アカウント・独立運用）

流れ:
  1) 素材サーバーから当日の1本(動画URL + 投稿文2本)を取得
  2) セッション(storage_state)で x.com に入り、動画を添付して1投稿目
  3) 投稿時に返ってくる tweet id を使い、その投稿へスレッド返信で2投稿目
  4) 成功したら素材サーバーのカーソルを進める

必要な GitHub Secrets:
  X_STORAGE_STATE / POSTS_ENDPOINT / ADVANCE_ENDPOINT / ADVANCE_TOKEN

改訂メモ (2026-10-12):
  - 投稿欄 tweetTextarea_0 が「モーダル」と「primaryColumn内インライン」の2箇所に
    存在し strict mode violation になった → JSでモーダル側を明示的に狙う。
  - 動画待ちは「添付サムネイルの出現」を実シグナルに判定。
  - スレッド返信は CreateTweet レスポンスの tweet id を捕まえて直接開く方式。
  - /advance へはブラウザ相当の User-Agent で送る（Cloudflareが Python-urllib を
    403で弾くため）。
"""
import json, os, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HERE = Path(__file__).resolve().parent
DRY = os.environ.get("DRY_RUN", "0") == "1"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

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

CAPTURE = {"id": None}


def log(*a):
    print(*a, flush=True)


def http_post(url, token):
    req = urllib.request.Request(url, method="POST", data=b"",
                                 headers={"User-Agent": BROWSER_UA, "x-token": token,
                                          "Content-Type": "application/json", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        f.write(r.read())


def fill_composer(page, text):
    ok = page.evaluate(FOCUS_COMPOSER_JS)
    if not ok:
        page.locator('div[data-testid="tweetTextarea_0"]').first.click()
    page.wait_for_timeout(300)
    page.keyboard.type(text, delay=8)


def wait_media(page, timeout=180):
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


def on_response(r):
    try:
        if "CreateTweet" in r.url and r.request.method == "POST":
            j = r.json()
            res = (j.get("data", {}).get("create_tweet", {})
                    .get("tweet_results", {}).get("result", {}))
            rid = res.get("rest_id") or (res.get("tweet") or {}).get("rest_id")
            if rid:
                CAPTURE["id"] = rid
                log("[capture] tweet id", rid)
    except Exception:
        pass


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
    rid = CAPTURE.get("id")
    if not rid:
        raise RuntimeError("tweet id を取得できず（CreateTweet捕捉失敗）")
    page.goto(f"https://x.com/{handle}/status/{rid}", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    try:
        rb = page.locator('[data-testid="reply"]').first
        rb.wait_for(state="visible", timeout=20000)
        rb.click()
        page.wait_for_timeout(3500)
    except Exception as e:
        log("[reply] 返信ボタン操作をスキップ:", repr(e)[:120])
    fill_composer(page, text)
    page.wait_for_timeout(1200)
    click_post(page)
    page.wait_for_timeout(7000)


def main():
    import hashlib
    _tk = os.environ.get("ADVANCE_TOKEN", "")
    log("[diag] token_len", len(_tk), "token_sha", hashlib.sha256(_tk.encode()).hexdigest()[:16])

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
        page.on("response", on_response)
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
            try:
                log("[advance]", http_post(adv, os.environ.get("ADVANCE_TOKEN", ""))[:120])
                break
            except Exception as e:
                log("[warn] advance失敗", attempt + 1, repr(e)[:120])
                time.sleep(5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
