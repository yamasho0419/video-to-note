#!/usr/bin/env python3
"""transcripts/{名前}.md を1分ごとの区切り付きで1行表示。使い方: transcript_view.py <名前>"""
import pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import channel
ch = channel.load()
txt, last = "", -1
for l in (ch.path("transcripts") / f"{sys.argv[1]}.md").read_text(encoding="utf-8").split("\n"):
    m = re.match(r"\[(\d+):(\d+)\] (.*)", l)
    if m:
        t = int(m[1]) * 60 + int(m[2])
        if t // 60 != last:
            txt += f"\n<{t//60}分>"; last = t // 60
        txt += m[3]
print(txt)
