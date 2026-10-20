#!/usr/bin/env python3
"""日付 → (偉人, 十干, 干支) を決定論的に決める回転エンジン。

素材サーバー(Worker/KV)には一切依存しない。日付だけが入力。
160通りを 80日周期で一巡（十干は日付で固定されるため、16偉人×10十干の
うち到達可能な組合せは80通り。これは暦の性質上そうなる）。
"""
import json, datetime, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
JST = datetime.timezone(datetime.timedelta(hours=9))
EPOCH = datetime.date(2000, 1, 1)   # この日は 戊午日（甲子=0で54番目）

GAN = "甲乙丙丁戊己庚辛壬癸"
SHI = "子丑寅卯辰巳午未申酉戌亥"
KANA = {"甲":("きのえ","木","陽"),"乙":("きのと","木","陰"),
        "丙":("ひのえ","火","陽"),"丁":("ひのと","火","陰"),
        "戊":("つちのえ","土","陽"),"己":("つちのと","土","陰"),
        "庚":("かのえ","金","陽"),"辛":("かのとの","金","陰"),
        "壬":("みずのえ","水","陽"),"癸":("みずのと","水","陰")}
MEANING = {"甲":"芽が張る日。始め時。","乙":"つるが巻きつく日。人と結ぶ。",
           "丙":"光が届く日。堂々と。","丁":"灯を守る日。繊細さが武器。",
           "戊":"山が動かぬ日。土台を固める。","己":"田を耕す日。整える。",
           "庚":"鋼を打つ日。決断と整理に最適。","辛":"刃を研ぐ日。研鑽と美。",
           "壬":"大河が流れる日。流れに乗る。","癸":"雨が沁みる日。内側を満たす。"}
ACTION = {"甲":"新しい一歩を、今日のうちに。","乙":"頼るべき人に、今日ひと声かけてみよ。",
          "丙":"隠さず、まっすぐに示してよい日。","丁":"小さな気遣いを、一つだけ丁寧に。",
          "戊":"目立たぬ用事ほど、今日は効く。","己":"散らかったものを、一つ片づけよ。",
          "庚":"ため込んだ用事を、今日こそ一刀両断に。","辛":"仕上げにこだわれば、明日の評価が変わる。",
          "壬":"重い腰を、流れに預けてしまえ。","癸":"答えを急がず、今日は養生を。"}

PERSONAS = json.loads((HERE/"personas.json").read_text(encoding="utf-8"))
QUOTES = json.loads((HERE/"quotes.json").read_text(encoding="utf-8"))


def ganshi(d):
    """その日の日柱(干支)。index = 甲子から数えた番号(0-59)。"""
    idx = (54 + (d - EPOCH).days) % 60
    return idx, GAN[idx % 10], SHI[idx % 12]


def payload(d=None):
    if d is None:
        d = datetime.datetime.now(JST).date()
    if isinstance(d, str):
        d = datetime.date.fromisoformat(d)
    idx, gan, shi = ganshi(d)
    p = PERSONAS[(d - EPOCH).days % len(PERSONAS)]
    kana, wuxing, yinyang = KANA[gan]
    name = p["name"]
    post1 = (f"{p['hook']}\n"
             f"【{name}が今日の十干を読む】\n"
             f"■ {gan}（{kana}・{wuxing}の{yinyang}）\n"
             f"{MEANING[gan]}\n"
             f"■ 一撃\n"
             f"{ACTION[gan]}\n"
             f"#四柱推命 #占い #今日の運勢 #運命の命式")
    post2 = (f"{QUOTES[p['romaji']]}\n\n"
             f"―― {name}\n\n"
             f"■ 今日の命式\n{gan}{shi}日")
    return {"date": d.isoformat(), "n": (d - EPOCH).days % 160,
            "persona": name, "romaji": p["romaji"], "hook": p["hook"],
            "stem": gan, "branch": shi, "ganshi": gan + shi, "ganshi_index": idx,
            "wuxing": wuxing, "yinyang": yinyang, "kana": kana,
            "meaning": MEANING[gan], "action": ACTION[gan],
            "quote": QUOTES[p["romaji"]],
            "post1": post1, "post2": post2}


if __name__ == "__main__":
    import sys
    for a in sys.argv[1:] or [None]:
        j = payload(a)
        print(json.dumps(j, ensure_ascii=False, indent=1) if len(sys.argv) < 2
              else f"{j['date']}  {j['ganshi']:<3} {j['persona']}")
