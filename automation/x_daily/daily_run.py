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


STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || {runtime: {}};
Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP','ja','en-US']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
"""

CF_JS = """
() => {
  const t = document.title || '';
  const body = (document.body && document.body.innerText) || '';
  const hasFrame = [...document.querySelectorAll('iframe')]
      .some(f => (f.src || '').includes('challenges.cloudflare.com'));
  const challenge = /セキュリティ検証|Just a moment|Checking your browser|Verifying you are human|Ray ID/.test(t + ' ' + body)
      || hasFrame || !!document.querySelector('#challenge-form, #cf-challenge-running');
  const m = body.match(/Ray ID[:：]\\s*([0-9a-f]+)/i) || t.match(/Ray ID[:：]\\s*([0-9a-f]+)/i);
  return {challenge: challenge, url: location.href, title: t, ray: m ? m[1] : ''};
}
"""


def cf_check(page):
    try:
        return page.evaluate(CF_JS)
    except Exception:
        return {"challenge": False, "url": "", "title": "", "ray": ""}


def wait_cf(page, budget=120, tag=""):
    """Cloudflareの検証ページなら解けるまで待つ。最初から無ければ即True。"""
    st = cf_check(page)
    if not st.get("challenge"):
        return True
    log("[cf] challenge%s ray=%s url=%s" % (tag, st.get("ray") or "-", st.get("url") or "-"))
    t0 = time.time()
    tick = 0
    while time.time() - t0 < budget:
        page.wait_for_timeout(3000)
        tick += 1
        st = cf_check(page)
        if not st.get("challenge"):
            log("[cf] cleared in %ds" % int(time.time() - t0))
            return True
        try:
            page.mouse.move(240 + (tick * 37) % 400, 300 + (tick * 53) % 300, steps=8)
        except Exception:
            pass
        if tick % 5 == 0:
            try:
                shot(page, "cf_wait%d.png" % tick)
            except Exception:
                pass
            log("[cf] still challenged %ds" % int(time.time() - t0))
    log("[cf] 解けず %ds 経過" % budget)
    return False


def launch_browser(p):
    args = ["--no-sandbox", "--disable-dev-shm-usage",
            "--autoplay-policy=no-user-gesture-required",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1360,960"]
    headful = os.environ.get("HEADFUL", "1") == "1"
    for kw in ({"channel": "chrome"}, {}):
        try:
            b = p.chromium.launch(args=args, headless=not headful, **kw)
            log("[browser] launch", "chrome-channel" if kw else "bundled-chromium",
                "headful" if headful else "headless")
            return b
        except Exception as e:
            log("[warn] launch 失敗", (kw or "chromium"), repr(e)[:140])
    raise RuntimeError("browser launch failed")


def open_composer(page, url, tries=3):
    """コンポーザが描画されるまで待つ。未描画なら再読込して最大3回。"""
    last = None
    for i in range(1, tries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            last = e
            log("[composer] goto失敗", i, repr(e)[:120])
            continue
        try:
            page.wait_for_selector('div[data-testid="tweetTextarea_0"]', timeout=45000)
            log("[composer] ready", i)
            return True
        except Exception as e:
            last = e
            log("[composer] 未描画", i, repr(e)[:120])
            try:
                shot(page, "err_composer_%d.png" % i)
            except Exception:
                pass
            if "i/flow/login" in page.url:
                log("[error] セッションが無効（cookie期限切れ）→ Cookieを再取得してSecretを更新")
                return False
            page.wait_for_timeout(5000)
    log("[composer] 3回とも未描画:", repr(last)[:200])
    return False


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


def _cdp_set(page, video):
    cdp = page.context.new_cdp_session(page)
    root = cdp.send("DOM.getDocument", {"depth": -1})["root"]["nodeId"]
    nid = cdp.send("DOM.querySelector",
                   {"nodeId": root, "selector": 'input[data-testid="fileInput"]'})["nodeId"]
    cdp.send("DOM.setFileInputFiles", {"files": [str(Path(video).resolve())], "nodeId": nid})


def attach_video(page, video):
    log("[media] file size", os.path.getsize(video))
    try:
        log("[diag] avc1 canPlayType:", repr(page.evaluate(AVC_PROBE_JS)))
    except Exception as e:
        log("[diag] canPlayType 失敗", repr(e)[:80])
    # 手段を連続実行すると同じ動画が重複添付されるため、必ず1手段ずつ・成功したら止める
    try:
        page.locator('input[data-testid="fileInput"]').first.set_input_files(video)
        log("[media] set_input_files 実行")
    except Exception as e:
        log("[media] set_input_files 例外:", repr(e)[:140])
    if wait_media(page, timeout=45):
        return True
    log("[media] 再試行: CDP DOM.setFileInputFiles")
    try:
        _cdp_set(page, video)
    except Exception as e:
        log("[media] CDP 失敗", repr(e)[:160])
    return wait_media(page, timeout=45)


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
    if not open_composer(page, "https://x.com/compose/post"):
        raise RuntimeError("composer 未描画（ログイン切れ or X側の一時的な描画失敗）")
    page.wait_for_timeout(1500)
    if PROBE:
        log("[probe] 添付前DIAG"); media_diag(page)
    fill_composer(page, text)          # 先に本文（コンポーザの取りこぼし防止）
    page.wait_for_timeout(1500)
    ok = attach_video(page, video)
    log("[media] attached:", ok)
    if not ok:
        media_diag(page)
        shot(page, "media_fail.png")
    if PROBE:
        try:
            n = page.evaluate("""() => {const d = document.querySelector('[role="dialog"]') || document;
              return d.querySelectorAll('[data-testid="attachments"] video, [data-testid="attachments"] img').length;}""")
            log("[probe] attachments count:", n)
        except Exception:
            pass
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
    if not open_composer(page, f"https://x.com/{handle}/status/{rid}"):
        raise RuntimeError("返信画面のコンポーザ未描画")
    page.wait_for_timeout(1500)
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


def api_base():
    p = os.environ.get("POSTS_ENDPOINT", "")
    return p.split("/today")[0].rstrip("/") if p else None


def seek_and_fetch_media(target_n, dest):
    """素材サーバーのカーソルを target_n まで進め、その動画を保存する。"""
    base = api_base()
    if not base:
        log("[media] POSTS_ENDPOINT 未設定"); return False
    hdr = {"User-Agent": BROWSER_UA, "x-token": os.environ.get("ADVANCE_TOKEN", ""),
           "Accept": "*/*", "Content-Type": "application/json"}
    def get_cur():
        req = urllib.request.Request(base + "/status", headers=hdr)
        with urllib.request.urlopen(req, timeout=30) as r:
            return int(json.load(r).get("cursor"))
    try:
        cur = get_cur()
    except Exception as e:
        log("[media] /status 失敗", repr(e)[:140]); return False
    log("[media] cursor", cur, "→ target", target_n)
    errs = 0
    for _ in range(200):
        if cur == target_n:
            break
        req = urllib.request.Request(base + "/advance", method="POST", data=b"", headers=hdr)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                cur = int(json.load(r).get("cursor"))
            errs = 0
        except Exception as e:
            # 500 は一時的なことがある。カーソルは進んでいる場合があるので /status で読み直す
            errs += 1
            log("[media] /advance 失敗", errs, repr(e)[:100])
            if errs >= 5:
                log("[media] advance が連続失敗 → 中断"); return False
            time.sleep(2)
            try:
                cur = get_cur()
            except Exception:
                pass
            continue
    if cur != target_n:
        log("[media] 到達できず", cur, target_n); return False
    log("[media] cursor =", cur)
    try:
        download(base + "/media", dest)
    except Exception as e:
        log("[media] /media 取得失敗", repr(e)[:140]); return False
    size = os.path.getsize(dest)
    log("[media] downloaded", size, "bytes")
    return size > 200000


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

    # 回転エンジン（日付から決定論的に偉人・十干・干支を決める。素材サーバー非依存）
    sys.path.insert(0, str(HERE))
    from rotation import payload as _payload
    item = _payload(os.environ.get("FORCE_DATE") or None)
    log("[item]", item["ganshi"], item["persona"], item["date"],
        "(n=%s)" % item["n"])
    handle = os.environ.get("X_HANDLE", "unmei_meishiki_")
    # 素材サーバーの160本から、当日の n (=偉人x10+十干) を探して動画を取る
    video = str(HERE / "today.mp4")
    got = seek_and_fetch_media(item["n"], video)
    if not got:
        log("[media] 動画が取れない → カード画像で代替")
        from card import render_card
        video = str(HERE / "today_card.png")
        render_card(item, video)
    log("[media] use", video, os.path.getsize(video), "bytes")
    log("[post1]\n" + item["post1"])
    log("[post2]\n" + item["post2"])

    if DRY:
        log("[dry] 取得のみ（投稿しない）")
        return 0

    with sync_playwright() as p:
        b = launch_browser(p)
        ctx = b.new_context(storage_state=str(HERE / "storage_state.json"),
                            viewport={"width": 1360, "height": 960},
                            locale="ja-JP", timezone_id="Asia/Tokyo",
                            user_agent=BROWSER_UA)
        ctx.add_init_script(STEALTH_JS)
        page = ctx.new_page()
        page.on("response", on_response)
        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded")
        except Exception as e:
            log("[warn] goto失敗:", repr(e)[:160])
        page.wait_for_timeout(3000)
        cf_seen = not wait_cf(page, 150, " home")
        logged_in = False
        for i in range(4):
            if cf_check(page).get("challenge"):
                cf_seen = True
                wait_cf(page, 90, " loop%d" % i)
            try:
                page.wait_for_selector(
                    '[data-testid="SideNav_AccountSwitcher_Button"], div[data-testid="tweetTextarea_0"]',
                    timeout=20000)
                logged_in = True
                break
            except Exception:
                if "i/flow/login" in page.url:
                    log("[error] ログイン画面へ転送 → セッション無効")
                    break
                page.wait_for_timeout(5000)
                try:
                    page.reload(wait_until="domcontentloaded")
                except Exception:
                    pass
        if not logged_in:
            st = cf_check(page)
            if st.get("challenge") or cf_seen:
                log("[error] Cloudflareの検証でx.comに入れない（cookie期限切れではない）ray=%s url=%s"
                    % (st.get("ray") or "-", st.get("url") or "-"))
            else:
                log("[error] セッションが無効（cookie期限切れ or ゲスト表示）→ Cookieを再取得してSecretを更新")
            shot(page, "err_login.png")
            return 2

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

    # カーソルは日付から決まるため /advance は不要（素材サーバー非依存）
    return 0


if __name__ == "__main__":
    sys.exit(main())
