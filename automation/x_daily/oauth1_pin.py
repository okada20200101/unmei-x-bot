#!/usr/bin/env python3
"""OAuth 1.0a の3-legged PINフロー（一度だけ実行すれば永久に使えるトークンが取れる）

  python3 oauth1_pin.py --start   … 認証URLを表示（CK/CSは環境変数）
  python3 oauth1_pin.py --finish 1234567 … PINを渡してアクセストークンを取得
"""
import json, os, sys
from pathlib import Path
from requests_oauthlib import OAuth1Session

HERE = Path(__file__).resolve().parent
STATE = HERE / ".oauth1_pin.json"
REQ = "https://api.x.com/oauth/request_token"
AUTH = "https://api.x.com/oauth/authorize"
ACC = "https://api.x.com/oauth/access_token"


def creds():
    ck = os.environ.get("X_API_KEY", "").strip()
    cs = os.environ.get("X_API_SECRET", "").strip()
    if not ck or not cs:
        print("[error] X_API_KEY / X_API_SECRET を環境変数で渡してください"); sys.exit(2)
    return ck, cs


def start():
    ck, cs = creds()
    s = OAuth1Session(ck, cs, callback_uri="oob")
    tok = s.fetch_request_token(REQ)
    STATE.write_text(json.dumps({"ck": ck, "cs": cs, "rt": tok["oauth_token"],
                                 "rs": tok["oauth_token_secret"]}), encoding="utf-8")
    print("[url] " + AUTH + "?oauth_token=" + tok["oauth_token"])
    print("[next] このURLをブラウザで開き、@unmei_meishiki_ で承認 → 表示された7桁のPINを控える")


def finish(pin):
    if not STATE.exists():
        print("[error] 先に --start を実行してください"); sys.exit(2)
    st = json.loads(STATE.read_text(encoding="utf-8"))
    s = OAuth1Session(st["ck"], st["cs"], resource_owner_key=st["rt"],
                      resource_owner_secret=st["rs"], verifier=pin)
    tok = s.fetch_access_token(ACC)
    print("[ok] X_ACCESS_TOKEN=" + tok["oauth_token"])
    print("[ok] X_ACCESS_SECRET=" + tok["oauth_token_secret"])
    print("[ok] screen_name=" + tok.get("screen_name", "?") + " user_id=" + tok.get("user_id", "?"))
    STATE.unlink(missing_ok=True)


if __name__ == "__main__":
    if "--start" in sys.argv:
        start()
    elif "--finish" in sys.argv:
        finish(sys.argv[sys.argv.index("--finish") + 1].strip())
    else:
        print(__doc__)
