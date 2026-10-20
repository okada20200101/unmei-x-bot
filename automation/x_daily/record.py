#!/usr/bin/env python3
"""投稿結果を history.jsonl に追記し、STATUS.md を再生成する。"""
import json, sys, datetime, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rotation import payload, JST

HERE = Path(__file__).resolve().parent
HIST = HERE / "history.jsonl"
STATUS = Path(__file__).resolve().parents[2] / "STATUS.md"


def load():
    if not HIST.exists():
        return []
    out = []
    for ln in HIST.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def write_status(rows):
    today = datetime.datetime.now(JST).date()
    last = rows[-1] if rows else None
    ev = os.environ.get("EVENT_NAME", "-")
    L = ["# 運命の命式 X自動投稿 — 稼働状況", ""]
    if last:
        L += [f"**最終投稿**: `{last['date']}` {last.get('time','')} JST / "
              f"**{last['ganshi']}日** / **{last['persona']}** / event=`{last.get('event','-')}`", ""]
    else:
        L += ["**最終投稿**: 記録なし（このファイルは初回投稿時に自動生成されます）", ""]
    L += ["## 直近の投稿", "", "| 日付 | 命式 | 偉人 | 十干 | 発火元 |", "|---|---|---|---|---|"]
    for r in rows[-14:][::-1]:
        L.append(f"| {r['date']} | {r['ganshi']}日 | {r['persona']} | {r['stem']} | `{r.get('event','-')}` |")
    L += ["", "## 今後7日（自動算出）", "", "| 日付 | 命式 | 偉人 | 動画n |", "|---|---|---|---|"]
    for i in range(7):
        j = payload(today + datetime.timedelta(days=i))
        L.append(f"| {j['date']} | {j['ganshi']}日 | {j['persona']} | {j['n']} |")
    L += ["", "---", "",
          "毎朝 **05:00 JST** に1本だけ投稿します。日付から命式と偉人を決定論的に算出し、",
          "素材サーバーの該当動画（16偉人 × 10十干 = 160本）を取得して添付します。", ""]
    STATUS.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    append = "--no-append" not in sys.argv
    rows = load()
    if append:
        j = payload(datetime.datetime.now(JST).date())
        rec = {k: j[k] for k in ("date", "ganshi", "persona", "stem", "n")}
        rec["time"] = os.environ.get("POST_TIME", datetime.datetime.now(JST).strftime("%H:%M"))
        rec["event"] = os.environ.get("EVENT_NAME", "-")
        rows = [r for r in rows if r.get("date") != rec["date"]] + [rec]
        rows.sort(key=lambda r: r["date"])
        HIST.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        print("[record]", rec)
    write_status(rows)
    print("[status] wrote", STATUS, STATUS.stat().st_size, "bytes")
