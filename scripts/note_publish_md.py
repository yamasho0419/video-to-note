#!/usr/bin/env python3
"""
旧コマンドの互換用。記事mdを既存の下書きに反映する処理は note_push.py に統合した。
使い方: python3 scripts/note_publish_md.py <video_id> [--dry-run]   (= note_push.py <番号>)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import note_api
import note_push

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) != 1:
    sys.exit(__doc__)
meta = note_api.load_note_meta(args[0])
if meta is None:
    sys.exit(f"{args[0]}.note.json が無い。既存の下書きと紐づいていないので中止")
try:
    note_push.push(int(meta["channel_no"]), dry="--dry-run" in sys.argv)
except note_push.PushStop as e:
    sys.exit(f"要人間: {e}")
