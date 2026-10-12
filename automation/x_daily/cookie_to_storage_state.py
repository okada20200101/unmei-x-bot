#!/usr/bin/env python3
"""Cookie-Editor の Export JSON → Playwright storage_state.json 変換
対象アカウント: @unmei_meiseki_（@iching_kobo のCookieは使わない）
使い方: python3 cookie_to_storage_state.py cookies.json > storage_state.json
"""
import json, sys
SS = {"no_restriction": "None", "unspecified": "Lax", "lax": "Lax", "strict": "Strict", "none": "None"}
def main():
    src = json.load(open(sys.argv[1], encoding="utf-8"))
    if isinstance(src, dict) and "cookies" in src:
        src = src["cookies"]
    out = []
    for c in src:
        exp = c.get("expirationDate", c.get("expires"))
        out.append({
            "name": c["name"], "value": c["value"], "domain": c["domain"],
            "path": c.get("path", "/"),
            "expires": -1 if exp in (None, "", "session") else int(exp),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", True)),
            "sameSite": SS.get(str(c.get("sameSite", "")).lower(), "Lax"),
        })
    json.dump({"cookies": out, "origins": []}, sys.stdout, ensure_ascii=False)
if __name__ == "__main__":
    main()
