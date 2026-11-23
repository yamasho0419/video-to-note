#!/usr/bin/env python3
"""管理表の該当番号行のチェック列を☑/☐にする。列は見出し名で引く。
使い方: set_check.py <番号> <列名(下書き|予約投稿完了)> on|off"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import channel

no, col, val = int(sys.argv[1]), sys.argv[2], sys.argv[3]
if col not in (channel.COL_DRAFT, channel.COL_RESERVED) or val not in ("on", "off"):
    sys.exit(__doc__)
channel.load().set_cell(no, col, channel.CHECK_ON if val == "on" else channel.CHECK_OFF)
