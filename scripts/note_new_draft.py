#!/usr/bin/env python3
"""
旧コマンドの互換用。新規下書きの作成(画像・見出し画像・meta・本文まで)は note_push.py に統合した。
使い方: python3 scripts/note_new_draft.py <video_id> <channel_no>   (= note_push.py <番号>)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import note_api
import note_push

vid, no = sys.argv[1], int(sys.argv[2])
assert note_api.load_note_meta(vid) is None, "既に下書きあり"
try:
    print(note_push.push(no))
except note_push.PushStop as e:
    sys.exit(f"要人間: {e}")
