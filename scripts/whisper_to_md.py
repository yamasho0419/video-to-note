#!/usr/bin/env python3
"""YouTube字幕が無い動画用: videos/{video_id}.* をmlx-whisperで文字起こしし、[MM:SS] 行形式のmdにする。
mlx-whisperが入ったPythonで実行する。
使い方: <venv>/bin/python scripts/whisper_to_md.py <video_id> <番号_短縮タイトル> <動画タイトル> <URL>"""
import pathlib, sys
import mlx_whisper

vid, name, title, url = sys.argv[1:5]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import channel
ch = channel.load()
video = next((ch.path("videos")).glob(f"{vid}.*"))
res = mlx_whisper.transcribe(str(video), path_or_hf_repo="mlx-community/whisper-large-v3-turbo", language="ja")
out = [f"[{int(s['start'])//60:02d}:{int(s['start'])%60:02d}] {s['text'].strip()}" for s in res["segments"] if s["text"].strip()]
head = f"""# 文字起こし: {title}

- URL: {url}
- チャンネル: {ch.cfg["name"]}
- 字幕種別: YouTube字幕なしのため音声から文字起こし（mlx-whisper large-v3-turbo）
- 取得方法: yt-dlpで動画取得→mlx-whisper
- 注意: 音声認識のため誤変換あり

"""
(ch.path("transcripts") / f"{name}.md").write_text(head + "\n".join(out) + "\n", encoding="utf-8")
print(len(out), "lines")
