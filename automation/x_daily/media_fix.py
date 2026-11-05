#!/usr/bin/env python3
"""素材動画のエンドカードを現状に合わせて修正する。

素材サーバーの160本はすべて「Google Play ボタン＋まもなく公開」のエンドカードで
書き出されている。アプリは既に公開済みなので、投稿直前に該当行だけ差し替える
（元動画のデザイン・動きはそのまま、文字だけ描き替える）。

さらに音声が末尾で切れているため、末尾を保持して少しだけ尺を延ばし、
語尾が唐突に切れないよう短いフェードをかける。

  python3 media_fix.py in.mp4 out.mp4 [--label "1行目\n2行目"]
"""
import json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

OLD = "まもなく公開"
# 音声の末尾に残る「まもなく公開」も消す（映像だけ直しても音声が残る）
ACUT_FALLBACK = 0.75              # 無音ギャップを検出できなかった時の保険（秒・末尾から）
NEW = "四柱推命を、もっと深く。\n無料でダウンロード。"
FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]
# 検出は元の1行の位置（既存素材のテキストがある場所）
DX, DY, DW, DH = 0.233, 0.7760, 0.534, 0.0430
# 描き替えは2行分の帯（ボタン下端 0.7672 の下、画面下に余白あり）
BX, BY, BW, BH = 0.233, 0.7729, 0.534, 0.0700
FSIZE = 0.0229                    # 元テキストと同じ 44px @1080
LINE_Y = [0.7839, 0.8161]         # 1行目・2行目の上端（行間 62px）
TAIL = 1.2                        # 末尾を保持して延ばす秒数
FADE = 0.15                       # 語尾のフェード長
BG = "0xF7F1EA"
FG = "0x8A8177"


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
    y0, y1 = int(h * (DY - 0.004)), int(h * (DY + DH + 0.004))
    x0, x1 = int(w * DX), int(w * (DX + DW))
    bg = np.array([247, 241, 234])
    return int((np.abs(im[y0:y1, x0:x1] - bg).sum(axis=2) > 40).sum()) > 60


def find_start(src, dur, hi=0.995, step=0.10):
    """エンドカードのテキストが出る最初の時刻を探す。見つからなければ None。"""
    # エンドカードは末尾 3.5 秒にしか出ない（本編の文字を拾わないよう範囲を限定）
    t = max(0.0, dur - 3.5)
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


def last_sentence_start(src, dur):
    """音声末尾の「まもなく公開。」を除去する切断位置を求める。

    最後の長い無音（間）の「開始」＝直前の発話の終わり を切る。
    文末の句の後ろに必ず間が入るため、その間ごと最終文を落とせる。
    """
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src,
                            "-af", "silencedetect=noise=-30dB:d=0.30", "-f", "null", "-"],
                           capture_output=True)
        txt = (r.stderr or b"").decode("utf-8", "ignore")
        starts = [float(x) for x in re.findall(r"silence_start:\s*([\d.]+)", txt)]
        ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", txt)]
        best = None
        for i in range(min(len(starts), len(ends))):
            st, en = starts[i], ends[i]
            # 末尾1.9秒以内に終わる「間」で、0.30秒以上のもの → その開始が直前発話の終わり
            if en >= dur - 1.9 and en <= dur - 0.05 and (en - st) >= 0.30:
                best = st
        if best is not None and 0.4 <= (dur - best) <= 2.6:
            return max(0.0, best + 0.02)
    except Exception as e:
        log("[fix] 音声ギャップ検出失敗:", repr(e)[:120])
    return max(0.0, dur - ACUT_FALLBACK)


def font_arg():
    for f in FONTS:
        if os.path.exists(f):
            return f
    return ""


# ---- エンドカードのナレーション（映像の文字と同じ内容を読み上げる）----
VOICES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "end_voice.mp3"),
    "/tmp/fr/end.mp3",
]
VOICE_GAP = 0.45      # 直前の文が終わってから読み上げ開始までの間
VOICE_PAD = 0.50      # 読み上げ後、動画を伸ばす余白


def adur(p):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", p],
                           capture_output=True)
        return float((r.stdout or b"0").decode().strip() or 0)
    except Exception:
        return 0.0


def end_voice():
    for v in VOICES:
        try:
            if os.path.exists(v) and os.path.getsize(v) > 1000:
                return v
        except Exception:
            pass
    return None


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
    fs = max(10, int(round(h * FSIZE)))
    box = ("drawbox=x=iw*%f:y=ih*%f:w=iw*%f:h=ih*%f:color=%s@1:t=fill:enable='gte(t,%.3f)'"
           % (BX, BY, BW, BH, BG, t0))
    cut = last_sentence_start(src, dur)

    voice = end_voice()
    vdur = adur(voice) if voice else 0.0
    if voice and vdur > 0.3:
        delay = cut + VOICE_GAP
        total = delay + vdur + VOICE_PAD
    else:
        voice, vdur, delay = None, 0.0, 0.0
        total = dur + TAIL
    tail = max(0.2, total - dur)

    pad = "tpad=stop_mode=clone:stop_duration=%.2f" % tail
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    acopy = ["-c:a", "copy"]
    lines = [x for x in label.split("\n") if x.strip()]
    steps = [box] + ["drawtext=fontfile=%s:text='%s':fontcolor=%s:fontsize=%d"
                     ":x=(w-text_w)/2:y=%d:enable='gte(t,%.3f)'"
                     % (f, s.replace("'", "").replace(":", "\\:"), FG, fs,
                        int(round(h * LINE_Y[min(i, len(LINE_Y) - 1)])), t0)
                     for i, s in enumerate(lines)] + [pad]
    cur = src
    tmps = []
    try:
        for i, flt in enumerate(steps):
            last = (i == len(steps) - 1)
            nxt = dst if last else str(Path(dst).with_suffix(".step%d.mp4" % i))
            if not last:
                tmps.append(nxt)
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", cur, "-vf", flt]
            cmd += (["-c:a", "copy"] if i == 0 else acopy)
            run(cmd + enc + [nxt])
            cur = nxt
    finally:
        for p in tmps:
            if os.path.exists(p):
                os.unlink(p)

    # 音声だけ差し替え（映像は無劣化コピー）
    # 末尾の「まもなく公開」を切って、代わりにエンドカードの読み上げを載せる
    tmpa = str(Path(dst).with_suffix(".audio.mp4"))
    try:
        if voice:
            fc = ("[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                  "atrim=end=%.3f,asetpts=PTS-STARTPTS,afade=t=out:st=%.3f:d=0.25[m];"
                  "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                  "adelay=%d|%d[v];"
                  "[m][v]amix=inputs=2:duration=longest:normalize=0,"
                  "apad=whole_dur=%.3f[a]"
                  % (cut, max(0.0, cut - 0.25), int(delay * 1000), int(delay * 1000), total))
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", dst, "-i", voice,
                 "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", tmpa])
        else:
            af = ("atrim=end=%.3f,asetpts=PTS-STARTPTS,"
                  "afade=t=out:st=%.3f:d=0.25,apad=whole_dur=%.3f"
                  % (cut, max(0.0, cut - 0.25), total))
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", dst, "-c:v", "copy",
                 "-af", af, "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", tmpa])
        shutil.move(tmpa, dst)
    finally:
        if os.path.exists(tmpa):
            try:
                os.unlink(tmpa)
            except Exception:
                pass

    log("[fix] 映像「%s」→「%s」 t>=%.2fs (%dx%d fs=%d) 尺 %.2fs→%.2fs"
        % (OLD, " / ".join(lines), t0, w, h, fs, dur, total))
    if voice:
        log("[fix] 音声 末尾発話(まもなく公開)を %.2fs で切断 → %.2fs から読み上げ「%s」%.2fs"
            % (cut, delay, label.replace("\n", " "), vdur))
    else:
        log("[fix] 音声 末尾発話(まもなく公開)を %.2fs で切断 → %.2fs まで無音で保持"
            " (end_voice.mp3 未配置)" % (cut, total))
    return True
