#!/usr/bin/env python3
"""
運命の命式 X自動投稿（X APIの従量課金を通さない = ブラウザ操作ルート）
対象アカウント: @unmei_meishiki_

流れ:
  1) 素材サーバーから当日の1本(動画URL + 投稿文2本)を取得
  2) セッション(storage_state)で x.com に入り、本文入力→動画添付→1投稿目
  3) 投稿時に返ってくる tweet id を使い、その投稿へスレッド返信で2投稿目
  4) 成功したら素材サーバーのカーソルを進める

必要な GitHub Secrets:
  X_STORAGE_STATE / POSTS_ENDPOINT / ADVANCE_ENDPOINT / ADVANCE_TOKEN

環境変数:
  DRY_RUN=1       : 取得のみ（投稿しない）
  PROBE=1         : 添付テストのみ（投稿しない）
  REQUIRE_MEDIA=1 : 動画が付かなければ投稿せず中止（カーソル温存）

改訂メモ (2026-10-12 動画添付の修正):
  - Playwright同梱ChromiumはH.264等の独自コーデックを含まず、動画の前処理が
    失敗して添付できないことがあるため、実Chrome(channel="chrome")を優先使用。
    起動できなければ同梱Chromiumに戻す。
  - 添付は set_input_files 直後に input.files.length を実測。0 の場合は
    CDP(DOM.setFileInputFiles) で再試行する。
  - 「uploading」判定から [role=progressbar]（常時存在で誤検知）を撤去し、
    video要素 / [data-testid=attachments] の出現のみを実シグナルにする。
  - 本文は添付より先に入力（長時間待機でコンポーザがリセットされる事故を防ぐ）。
"""
import json, os, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
DRY = os.environ.get("DRY_RUN", "0") == "1"
PROBE = os.environ.get("PROBE", "0") == "1"
REQUIRE_MEDIA = os.environ.get("REQUIRE_MEDIA", "0") == "1"
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
  if (att && att.querySelector('video, img')) return 'ready';
  if (scope.querySelector('video')) return 'ready';
  if (att) return 'attached';
  return 'none';
}
"""

TOAST_JS = """
() => [...document.querySelectorAll('[data-testid="toast"]')].map(e => e.innerText).join(' || ')
"""

FILES_LEN_JS = """
(s) => { const e = document.querySelector(s); return e && e.files ? e.files.length : -1; }
"""

AVC_PROBE_JS = """() => document.createElement('video').canPlayType('video/mp4; codecs="avc1.42E01E"')"""

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


def launch_browser(p):
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--autoplay-policy=no-user-gesture-required"]
    for kw in ({"channel": "chrome"}, {}):
        try:
            b = p.chromium.launch(args=args, **kw)
            log("[browser] launch", "chrome-channel" if kw else "bundled-chromium")
            return b
        except Exception as e:
            log("[warn] launch 失敗", (kw or "chromium"), repr(e)[:140])
    raise RuntimeError("browser launch failed")


def fill_composer(page, text):
    ok = page.evaluate(FOCUS_COMPOSER_JS)
    if not ok:
        page.locator('div[data-testid="tweetTextarea_0"]').first.click()
    page.wait_for_timeout(300)
    page.keyboard.type(text, delay=8)


def wait_media(page, timeout=90):
    steps = max(1, timeout // 3)
    last = None
    for _ in range(steps):
        st = page.evaluate(MEDIA_JS)
        if st in ("ready", "attached"):
            log("[media]", st)
            page.wait_for_timeout(3000)
            return True
        if st != last:
            log("[media]", st)
            last = st
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


def attach_video(page, video):
    log("[media] file size", os.path.getsize(video))
    try:
        log("[diag] avc1 canPlayType:", repr(page.evaluate(AVC_PROBE_JS)))
    except Exception as e:
        log("[diag] canPlayType 失敗", repr(e)[:80])
    vabs = str(Path(video).resolve())
    for sel in ('input[data-testid="fileInput"]', 'input[type="file"]'):
        try:
            loc = page.locator(sel)
            if loc.count() == 0:
                continue
            try:
                loc.first.set_input_files(video)
            except Exception as e:
                log("[media] set_input_files 例外", sel, repr(e)[:140])
            n = page.evaluate(FILES_LEN_JS, sel)
            log("[media] set_input_files", sel, "-> files n:", n)
            if isinstance(n, int) and n > 0:
                return True
        except Exception as e:
            log("[media] 失敗", sel, repr(e)[:140])
    try:
        cdp = page.context.new_cdp_session(page)
        root = cdp.send("DOM.getDocument", {"depth": -1})["root"]["nodeId"]
        nid = cdp.send("DOM.querySelector",
                       {"nodeId": root, "selector": 'input[data-testid="fileInput"]'})["nodeId"]
        if nid:
            cdp.send("DOM.setFileInputFiles", {"files": [vabs], "nodeId": nid})
            n = page.evaluate(FILES_LEN_JS, 'input[data-testid="fileInput"]')
            log("[media] CDP setFileInputFiles -> files n:", n)
            if isinstance(n, int) and n > 0:
                return True
    except Exception as e:
        log("[media] CDP 失敗", repr(e)[:160])
    return False


def media_diag(page):
    try:
        log("[media] dialog_text:",
            page.locator('[role="dialog"]').first.inner_text()[:300].replace("\n", " | "))
    except Exception as e:
        log("[media] dialog_text 取得失敗:", repr(e)[:120])
    try:
        log("[media] toast:", (page.evaluate(TOAST_JS) or "")[:200])
    except Exception:
        pass
    try:
        d = page.evaluate("""() => {
          const r = document.querySelector('[role="dialog"]') || document;
          return {videos: r.querySelectorAll('video').length,
                  atts: r.querySelectorAll('[data-testid="attachments"]').length,
                  inputs: [...r.querySelectorAll('input')].map(e => ({t: e.type, tid: e.getAttribute('data-testid'), ac: e.accept, hid: !(e.offsetWidth||e.offsetHeight), n: e.files ? e.files.length : -1}))};
        }""")
        log("[dump] videos", d.get("videos"), "atts", d.get("atts"))
        log("[dump] inputs", json.dumps(d.get("inputs"), ensure_ascii=False)[:700])
    except Exception as e:
        log("[dump] 失敗:", repr(e)[:200])


def shot(page, name):
    try:
        page.screenshot(path=str(HERE / name))
        log("[shot]", name)
    except Exception as e:
        log("[shot] 失敗", name, repr(e)[:80])


def post_first(page, video, text):
    page.goto("https://x.com/compose/post", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    if PROBE:
        log("[probe] 添付前DIAG"); media_diag(page)
    fill_composer(page, text)          # 先に本文（コンポーザの取りこぼし防止）
    page.wait_for_timeout(1500)
    attach_video(page, video)
    page.wait_for_timeout(2500)
    ok = wait_media(page, timeout=90)
    log("[media] attached:", ok)
    if not ok:
        media_diag(page)
        shot(page, "media_fail.png")
    if PROBE:
        shot(page, "probe.png")
        log("[probe] 添付テストのみで終了（投稿しない）")
        return False
    if REQUIRE_MEDIA and not ok:
        log("[media] REQUIRE_MEDIA=1 のため投稿せず中止（カーソル温存）")
        return False
    click_post(page)
    page.wait_for_timeout(12000)
    return True


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
    log("[diag] flags PROBE", PROBE, "REQUIRE_MEDIA", REQUIRE_MEDIA, "DRY", DRY)

    state = os.environ.get("X_STORAGE_STATE")
    if not state:
        log("[skip] X_STORAGE_STATE 未設定")
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
        b = launch_browser(p)
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
            if not post_first(page, video, item["post1"]):
                log("[probe] 終了")
                ctx.close(); b.close(); return 0
            log("[post1] 実行")
        except Exception as e:
            log("[error] 1投稿目に失敗:", repr(e)[:300])
            shot(page, "err_post1.png")
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
