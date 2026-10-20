import os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
HERE = Path(__file__).resolve().parent
IDS = ["2112498833553006812","2112500311910924756","2112500415602245925"]
state = os.environ["X_STORAGE_STATE"]
(HERE/"ss.json").write_text(state, encoding="utf-8")
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox","--disable-dev-shm-usage"], channel="chrome")
    ctx = b.new_context(storage_state=str(HERE/"ss.json"), viewport={"width":1360,"height":960}, locale="ja-JP", timezone_id="Asia/Tokyo")
    pg = ctx.new_page()
    pg.goto("https://x.com/home", wait_until="domcontentloaded"); pg.wait_for_timeout(5000)
    print("[session]", pg.url, flush=True)
    for tid in IDS:
        pg.goto(f"https://x.com/unmei_meishiki_/status/{tid}", wait_until="domcontentloaded")
        pg.wait_for_timeout(5000)
        t = pg.inner_text("body")
        arts = pg.locator('article').count()
        alive = ("このポストは削除されています" not in t) and ("このポストは利用できません" not in t) and arts > 0
        snippet = ""
        for k in ["今日の自分に自信がない","静けさの中で答えを探す","迷いの半分は"]:
            if k in t: snippet = k
        print(f"[check] {tid} alive={alive} articles={arts} snippet={snippet or '-'} url={pg.url}", flush=True)
    ctx.close(); b.close()
