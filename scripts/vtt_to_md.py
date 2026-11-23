#!/usr/bin/env python3
"""transcripts/{video_id}.ja.vtt を [MM:SS] 行形式のmdに整形する。
使い方: python3 scripts/vtt_to_md.py <video_id> <番号_短縮タイトル> <動画タイトル> <URL>"""
import html, pathlib, re, sys

vid, name, title, url = sys.argv[1:5]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import channel
ch = channel.load()
vtt = (ch.path("transcripts") / f"{vid}.ja.vtt").read_text(encoding="utf-8")
out, last = [], None
for block in re.split(r"\n\n+", vtt):
    m = re.search(r"(\d+):(\d+):(\d+)\.\d+ --> ", block)
    if not m:
        continue
    h, mi, s = map(int, m.groups())
    lines = [html.unescape(re.sub(r"<[^>]+>", "", l)).strip() for l in block.split("\n")[1:]]
    for l in lines:
        if l and l != last and not l.startswith(("Kind:", "Language:")):
            out.append(f"[{h*60+mi:02d}:{s:02d}] {l}")
            last = l
head = f"""# 文字起こし: {title}

- URL: {url}
- チャンネル: {ch.cfg["name"]}
- 字幕種別: 自動生成（日本語, ASR）
- 取得方法: yt-dlp
- 注意: ASRのため誤変換あり

"""
(ch.path("transcripts") / f"{name}.md").write_text(head + "\n".join(out) + "\n", encoding="utf-8")
print(len(out), "lines")
