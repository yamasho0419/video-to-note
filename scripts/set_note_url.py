#!/usr/bin/env python3
"""管理表の該当番号行のnoteURL列に下書きURLを書き、下書き列を☑にする。使い方: set_note_url.py <番号> <note_key>"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import channel

no, key = int(sys.argv[1]), sys.argv[2]
ch = channel.load()
ch.set_cell(no, channel.COL_NOTE_URL, f"https://editor.note.com/notes/{key}/edit/")
ch.set_cell(no, channel.COL_DRAFT, channel.CHECK_ON)
