#!/usr/bin/env python3
"""X API (v2) 経由の投稿。Cloudflare検証を一切通らないため、ブラウザ経路より確実。

必要な環境変数（GitHub Secrets）:
  X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_SECRET   （OAuth 1.0a ユーザーコンテキスト）

使い方:
  python3 api_post.py --check        … 認証確認のみ（/2/users/me）
"""
import os, sys, time
import requests
from requests_oauthlib import OAuth1Session

UPLOAD_HOSTS = ["https://upload.twitter.com", "https://upload.x.com"]
API_HOSTS = ["https://api.x.com", "https://api.twitter.com"]
CHUNK = 4 * 1024 * 1024


def log(*a):
    print(*a, flush=True)


def _creds():
    ks = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]
    vs = [os.environ.get(k, "").strip() for k in ks]
    return vs if all(vs) else None


def available():
    return _creds() is not None


def session():
    c = _creds()
    if not c:
        raise RuntimeError("X API キーが未設定")
    return OAuth1Session(c[0], c[1], c[2], c[3], timeout=180)


def _first_ok(fn):
    last = None
    for host in UPLOAD_HOSTS:
        try:
            return fn(host)
        except Exception as e:
            last = e
            log("[api] host失敗", host, repr(e)[:120])
    raise last


def upload_video(sess, path):
    size = os.path.getsize(path)
    log("[api] media INIT", size, "bytes")

    def init(host):
        r = sess.post(host + "/1.1/media/upload.json", data={
            "command": "INIT", "total_bytes": size,
            "media_type": "video/mp4", "media_category": "tweet_video"})
        r.raise_for_status()
        return host, r.json()["media_id_string"]

    host, media_id = _first_ok(init)
    log("[api] media_id", media_id)

    seg = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            r = sess.post(host + "/1.1/media/upload.json", data={
                "command": "APPEND", "media_id": media_id, "segment_index": seg},
                files={"media": ("blob", chunk)})
            r.raise_for_status()
            seg += 1
    log("[api] APPEND", seg, "segments")

    r = sess.post(host + "/1.1/media/upload.json",
                  data={"command": "FINALIZE", "media_id": media_id})
    r.raise_for_status()
    info = (r.json() or {}).get("processing_info")
    waited = 0
    while info and info.get("state") in ("pending", "in_progress"):
        wait = min(int(info.get("check_after_secs", 4)), 10)
        if waited > 300:
            raise RuntimeError("media processing timeout")
        time.sleep(wait)
        waited += wait
        r = sess.get(host + "/1.1/media/upload.json",
                     params={"command": "STATUS", "media_id": media_id})
        r.raise_for_status()
        info = (r.json() or {}).get("processing_info")
        log("[api] processing", info.get("state") if info else "done",
            info.get("progress_percent") if info else "")
    if info and info.get("state") == "failed":
        raise RuntimeError("media processing failed: %s" % info.get("error"))
    log("[api] media ready")
    return media_id


def create_post(sess, text, media_id=None, reply_to=None):
    payload = {"text": text}
    if media_id:
        payload["media"] = {"media_ids": [str(media_id)]}
    if reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": str(reply_to)}
    last = None
    for host in API_HOSTS:
        try:
            r = sess.post(host + "/2/tweets", json=payload)
            if r.status_code >= 400:
                raise RuntimeError("HTTP %s %s" % (r.status_code, r.text[:300]))
            return r.json()["data"]["id"]
        except Exception as e:
            last = e
            log("[api] post host失敗", host, repr(e)[:160])
    raise last


def post_thread(video, text1, text2):
    sess = session()
    mid = None
    if video and os.path.exists(video) and os.path.getsize(video) > 0:
        if video.lower().endswith(".mp4"):
            mid = upload_video(sess, video)
        else:
            log("[warn] 動画以外は添付しない:", video)
    id1 = create_post(sess, text1, media_id=mid)
    log("[api] post1 id", id1)
    id2 = None
    try:
        id2 = create_post(sess, text2, reply_to=id1)
        log("[api] post2 id", id2)
    except Exception as e:
        log("[warn] 返信失敗", repr(e)[:200])
    return id1, id2


if __name__ == "__main__":
    if "--check" in sys.argv:
        if not available():
            log("[api] キー未設定"); sys.exit(3)
        s = session()
        r = s.get(API_HOSTS[0] + "/2/users/me")
        log("[api] /2/users/me", r.status_code, r.text[:400])
        sys.exit(0 if r.status_code == 200 else 1)
    log("usage: api_post.py --check"); sys.exit(2)
