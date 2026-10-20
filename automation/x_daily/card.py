#!/usr/bin/env python3
"""投稿カード(1080x1350 PNG)を日付データから描画する。外部アセット不要。"""
import os
from pathlib import Path

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{width:1080px;height:1350px;background:#0a0d18;
 background-image:radial-gradient(circle at 50% 0%,rgba(198,163,92,.20),transparent 55%),
 radial-gradient(circle at 50% 100%,rgba(198,163,92,.10),transparent 60%);
 color:#f2ead9;font-family:"Noto Serif CJK JP","Noto Serif JP",serif;
 display:flex;flex-direction:column;padding:86px 84px}
.rule{height:1px;background:linear-gradient(90deg,transparent,#c6a35c,transparent);opacity:.75}
.top{display:flex;justify-content:space-between;align-items:baseline;
 font-size:27px;letter-spacing:.34em;color:#c6a35c}
.kanshi{font-size:250px;line-height:1.02;letter-spacing:.06em;color:#f7f0dd;
 text-align:center;margin:34px 0 6px;font-weight:600}
.kana{text-align:center;font-size:31px;letter-spacing:.30em;color:#9aa2b8;margin-bottom:40px}
.persona{text-align:center;font-size:74px;letter-spacing:.10em;color:#f2ead9;font-weight:600;margin:18px 0 8px}
.role{text-align:center;font-size:26px;letter-spacing:.24em;color:#c6a35c;margin-bottom:44px}
.quote{font-size:41px;line-height:1.86;text-align:center;color:#e6ddc9;padding:0 12px;letter-spacing:.03em}
.spacer{flex:1}
.foot{display:flex;justify-content:space-between;align-items:flex-end;
 font-size:26px;letter-spacing:.18em;color:#8e8b7f}
.brand{font-size:33px;letter-spacing:.44em;color:#c6a35c}
"""

def build_html(it):
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>{CSS}</style></head>
<body>
<div class="top"><span>今日の十干</span><span>{it['date'].replace('-','.')}</span></div>
<div class="rule" style="margin-top:22px"></div>
<div class="kanshi">{it['ganshi']}</div>
<div class="kana">{it['kana']}・{it['wuxing']}の{it['yinyang']}</div>
<div class="rule"></div>
<div class="persona">{it['persona']}</div>
<div class="role">今日の命式を読む</div>
<div class="quote">{it['quote']}</div>
<div class="spacer"></div>
<div class="rule" style="margin-bottom:30px"></div>
<div class="foot"><span class="brand">運命の命式</span><span>{it['ganshi']}日</span></div>
</body></html>"""

def render_card(it, out):
    from playwright.sync_api import sync_playwright
    out = str(out)
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--font-render-hinting=none"])
        pg = b.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        pg.set_content(build_html(it), wait_until="load")
        pg.wait_for_timeout(1200)
        pg.evaluate("() => document.fonts.ready")
        pg.wait_for_timeout(400)
        pg.screenshot(path=out, clip={"x": 0, "y": 0, "width": 1080, "height": 1350})
        b.close()
    return Path(out)

if __name__ == "__main__":
    from rotation import payload
    import sys
    it = payload(sys.argv[1] if len(sys.argv) > 1 else None)
    Path("/tmp/opencode/preview.html").write_text(build_html(it), encoding="utf-8")
    print("wrote /tmp/opencode/preview.html for", it["date"], it["ganshi"], it["persona"])
