#!/usr/bin/env python3
"""素材動画のエンドカードを現状に合わせて修正する。

素材サーバーの160本はすべて「Google Play ボタン＋まもなく公開」のエンドカードで
書き出されている。アプリは既に公開済みなので、投稿直前に該当行だけ差し替える
（元動画のデザイン・動きはそのまま、1行だけ描き替える）。

  python3 media_fix.py in.mp4 out.mp4 [--label "Google Play で配信中"]
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

OLD = "まもなく公開"
NEW = "Google Play で配信中"
FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]
# 720x1280 実測 → 相対値。テキスト行は中央やや下。
BX, BY, BW, BH = 0.233, 0.7785, 0.534, 0.038
TX, TY = 0.5, 0.7845
FSIZE = 0.0305
BG = "0xF7F1EA"
FG = "0x2A3350"


def log(*a):
    print(*a, flush=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or b"").decode("utf-8", "ignore")[-400:])
    return r.stdout


def probe(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height", "-show_entries", "format=duration",
               "-of", "json", path])
    d = json.loads(out)
    st = d["streams"][0]
    return int(st["width"]), int(st["height"]), float(d["format"]["duration"])


def frame_at(src, t, dest):
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.3f" % t, "-i", src,
         "-frames:v", "1", "-q:v", "2", dest])


def text_present(png):
    """テキスト行の領域に背景以外の画素があるか。PIL が無ければ True 扱い（=修正する）。"""
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return True
    im = np.array(Image.open(png).convert("RGB")).astype(int)
    h, w, _ = im.shape
    y0, y1 = int(h * (BY - 0.004)), int(h * (BY + BH + 0.004))
    x0, x1 = int(w * BX), int(w * (BX + BW))
    bg = np.array([247, 241, 234])
    return int((np.abs(im[y0:y1, x0:x1] - bg).sum(axis=2) > 40).sum()) > 60


def find_start(src, dur, lo=None, hi=0.995, step=0.10):
    """エンドカードのテキストが出る最初の時刻を探す。見つからなければ None。"""
    # エンドカードは末尾 3.5 秒にしか出ない（本編の文字を拾わないよう範囲を限定）
    t = max(0.0, dur - 3.5) if lo is None else dur * lo
    tmp = tempfile.mkdtemp()
    hit = None
    try:
        while t <= dur * hi:
            p = os.path.join(tmp, "f.png")
            frame_at(src, t, p)
            if os.path.exists(p) and text_present(p):
                hit = t
                break
            t += step
    except Exception as e:
        log("[fix] 検出失敗:", repr(e)[:120])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return hit


def font_arg():
    for f in FONTS:
        if os.path.exists(f):
            return f
    return ""


def fix(src, dst, label=NEW):
    w, h, dur = probe(src)
    start = find_start(src, dur)
    if start is None:
        log("[fix] エンドカードのテキストを検出せず → そのまま使用")
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copyfile(src, dst)
        return False
    t0 = max(0.0, start - 0.12)
    f = font_arg()
    if not f:
        log("[fix] 日本語フォント無し → そのまま使用")
        shutil.copyfile(src, dst)
        return False
    # drawtext の fontsize は数値のみ（ih*… は評価されない）→ 実寸から算出
    fs = max(10, int(round(h * FSIZE)))
    ty = int(round(h * TY))
    box = ("drawbox=x=iw*%f:y=ih*%f:w=iw*%f:h=ih*%f:color=%s@1:t=fill:enable='gte(t,%.3f)'"
           % (BX, BY, BW, BH, BG, t0))
    txt = ("drawtext=fontfile=%s:text='%s':fontcolor=%s:fontsize=%d"
           ":x=(w-text_w)/2:y=%d:enable='gte(t,%.3f)'"
           % (f, label.replace(":", "\\:").replace("'", ""), FG, fs, ty, t0))
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart"]
    # 2つのフィルタを同時に渡すと評価順で落ちる環境があるため2パスに分ける
    tmp = str(Path(dst).with_suffix(".step1.mp4"))
    try:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", box] + enc + [tmp])
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-vf", txt] + enc + [dst])
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    log("[fix] 「%s」→「%s」 t>=%.2fs (%dx%d fs=%d)" % (OLD, label, t0, w, h, fs))
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    a, b = sys.argv[1], sys.argv[2]
    lab = NEW
    if "--label" in sys.argv:
        lab = sys.argv[sys.argv.index("--label") + 1]
    fix(a, b, lab)
