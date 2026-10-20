import os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
HERE = Path(__file__).resolve().parent
IDS = ["2112498833553006812","2112500311910924756"]
state = os.environ["X_STORAGE_STATE"]
(HERE/"ss.json").write_text(state, encoding="utf-8")
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox","--disable-dev-shm-usage"], channel="chrome")
    ctx = b.new_context(storage_state=str(HERE/"ss.json"), viewport={"width":1360,"height":960},
                        locale="ja-JP", timezone_id="Asia/Tokyo",
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
    pg = ctx.new_page()
    pg.goto("https://x.com/home", wait_until="domcontentloaded"); pg.wait_for_timeout(6000)
    print("[session]", pg.url, flush=True)
    for tid in IDS:
        pg.goto(f"https://x.com/unmei_meishiki_/status/{tid}", wait_until="domcontentloaded")
        try:
            pg.wait_for_selector("article", timeout=25000)
        except Exception:
            pass
        pg.wait_for_timeout(3000)
        t = pg.inner_text("body")
        n = pg.locator("article").count()
        gone = any(k in t for k in ["このポストは削除されています","このポストは利用できません","This Post was deleted","This Post is unavailable"])
        key = "-"
        for k in ["今日の自分に自信がない","静けさの中で答えを探す"]:
            if k in t: key = k
        print(f"[check] {tid} article={n} deleted_msg={gone} text={key}", flush=True)
    ctx.close(); b.close()
