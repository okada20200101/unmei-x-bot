#!/usr/bin/env python3
"""重複投稿（私が 20:04 に誤って出した2本）を、保存済みセッションで削除する。
対象IDは固定。本文の先頭一致を確認してから消す（誤削除防止）。"""
import os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
HANDLE = "unmei_meishiki_"
# 消す対象: (tweet_id, 本文の先頭20文字)  ※残すのは 2112498833553006812
TARGETS = [
    ("2112500415602245925", "迷いの半分は、古い地図のせいだ"),
    ("2112500311910924756", "静けさの中で答えを探すあなたへ"),
]

def log(*a):
    print(*a, flush=True)

def delete_one(page, tid, expect):
    url = f"https://x.com/{HANDLE}/status/{tid}"
    log("[open]", url)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)

    body = page.inner_text("body")
    if expect not in body:
        log("[abort]", tid, "本文が一致しないため削除しません")
        return False
    log("[verify] 本文一致 OK")

    try:
        caret = page.locator('[data-testid="caret"]').first
        caret.wait_for(state="visible", timeout=15000)
        caret.click()
        page.wait_for_timeout(2000)
    except Exception as e:
        log("[error] caret クリック失敗", repr(e)[:160])
        return False

    clicked = False
    for sel in ['[data-testid="Dropdown"] [role="menuitem"]:has-text("削除")',
                '[role="menuitem"]:has-text("削除")',
                '[data-testid="Dropdown"] [role="menuitem"]:has-text("Delete")',
                '[role="menuitem"]:has-text("Delete")']:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.click()
                clicked = True
                log("[menu] 削除をクリック", sel)
                break
        except Exception:
            continue
    if not clicked:
        log("[error] 削除メニューが見つからない")
        return False

    page.wait_for_timeout(2500)
    try:
        page.locator('[data-testid="confirmationSheetConfirm"]').first.click()
        log("[confirm] 削除を確定")
    except Exception as e:
        log("[error] 確定ボタン失敗", repr(e)[:160])
        return False
    page.wait_for_timeout(5000)
    return True

def main():
    state = os.environ.get("X_STORAGE_STATE")
    if not state:
        log("[skip] X_STORAGE_STATE 未設定")
        return 1
    (HERE / "storage_state.json").write_text(state, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"], channel="chrome")
        ctx = b.new_context(storage_state=str(HERE / "storage_state.json"),
                            viewport={"width": 1360, "height": 960},
                            locale="ja-JP", timezone_id="Asia/Tokyo")
        page = ctx.new_page()
        page.goto("https://x.com/home", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        if "i/flow/login" in page.url:
            log("[error] セッション無効")
            return 1
        ok = 0
        for tid, expect in TARGETS:
            try:
                if delete_one(page, tid, expect):
                    ok += 1
                    log("[done]", tid)
            except Exception as e:
                log("[error]", tid, repr(e)[:200])
        log("[summary] deleted", ok, "of", len(TARGETS))
        ctx.close(); b.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
