#!/usr/bin/env python3
"""
チャンネルごとの設定(channels/{名前}/channel.json)と管理表(channel_url.md 等)の読み書き。

どのチャンネルを扱うかは環境変数 NOTE_CHANNEL で指定する(既定は sample)。
  NOTE_CHANNEL=sample python3 scripts/pipeline_status.py 1-10

管理表は見出し行の列名で列を引く(列の並びに依存しない)。必須の列名:
  # / URL / 元の動画の名前 / note記事の名前 / 投稿予定日時 / noteのURL / 下書き / 予約投稿完了
書き換えは指定したセルだけ。書く前にプロジェクト直下の .backup/ に退避し、列数が見出しと合わない行は触らない。
"""
import json
import os
import pathlib
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHANNELS_DIR = ROOT / "channels"
DEFAULT = "sample"

COL_NO, COL_URL, COL_TITLE, COL_NOTE_TITLE = "#", "URL", "元の動画の名前", "note記事の名前"
COL_AT, COL_NOTE_URL, COL_DRAFT, COL_RESERVED = "投稿予定日時", "noteのURL", "下書き", "予約投稿完了"
CHECK_ON, CHECK_OFF = "☑", "☐"


class Channel:
    def __init__(self, name: str | None = None):
        self.name = name or os.environ.get("NOTE_CHANNEL") or DEFAULT
        cfg_path = CHANNELS_DIR / self.name / "channel.json"
        if not cfg_path.exists():
            raise SystemExit(f"チャンネル設定が無い: {cfg_path.relative_to(ROOT)}")
        self.cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        self.dir = cfg_path.parent

    def path(self, key: str) -> pathlib.Path:
        return ROOT / self.cfg["paths"][key]

    def feature(self, key: str) -> bool:
        return bool(self.cfg.get("features", {}).get(key))

    # ---- 管理表 ----

    def _lines(self) -> list[str]:
        return self.path("table").read_text(encoding="utf-8").split("\n")

    @staticmethod
    def _cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    def header(self) -> list[str]:
        return self._cells(next(l for l in self._lines() if l.startswith("|")))

    def rows(self) -> dict[int, dict]:
        """番号 → {列名: 値, "video_id": ...}。列数が見出しと合わない行は "_broken": True"""
        head = self.header()
        out = {}
        for line in self._lines():
            m = re.match(r"\|\s*(\d+)\s*\|", line)
            if not m:
                continue
            cells = self._cells(line)
            row = dict(zip(head, cells))
            row["_broken"] = len(cells) != len(head)
            vm = re.search(r"v=([\w-]{11})", row.get(COL_URL, ""))
            row["video_id"] = vm.group(1) if vm else None
            out[int(m.group(1))] = row
        return out

    def row(self, no: int) -> dict:
        rows = self.rows()
        if no not in rows:
            raise SystemExit(f"{self.cfg['paths']['table']} に {no} 番の行が無い")
        return rows[no]

    def set_cell(self, no: int, column: str, value: str) -> None:
        """no番の行の column 列だけを書き換える。他の行・セルは1文字も変えない。"""
        table = self.path("table")
        text = table.read_text(encoding="utf-8")
        lines = text.split("\n")
        head = self.header()
        if column not in head:
            raise SystemExit(f"列が見つからない: {column}")
        ci = head.index(column)
        li = next((i for i, l in enumerate(lines) if re.match(rf"\|\s*{no}\s*\|", l)), None)
        if li is None:
            raise SystemExit(f"{no} 番の行が無い")
        cells = lines[li].split("|")  # 先頭と末尾は空文字
        if len(cells) - 2 != len(head):
            raise SystemExit(f"{no} 番の行は列数が見出しと合わないので書き換えを中止")
        cells[ci + 1] = f" {value} " if value else " "
        lines[li] = "|".join(cells)
        backup = ROOT / ".backup"
        backup.mkdir(exist_ok=True)
        shutil.copy(table, backup / f"{table.name}.bak")
        tmp = table.with_suffix(".tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(table)

    # ---- 記事ファイル ----

    def article(self, no: int) -> pathlib.Path | None:
        hits = sorted(self.path("articles").glob(f"{no:02d}_*.md"))
        return hits[0] if len(hits) == 1 else None

    def meta_path(self, video_id: str) -> pathlib.Path:
        return self.path("meta") / f"{video_id}.note.json"

    def load_meta(self, video_id: str) -> dict | None:
        p = self.meta_path(video_id)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load(name: str | None = None) -> Channel:
    return Channel(name)


if __name__ == "__main__":
    # シェルスクリプト用: python3 scripts/channel.py path videos → 絶対パスを出力
    import sys
    # 管理表のセルを1つ書く:     python3 scripts/channel.py set 320 note記事の名前 "題名"
    if len(sys.argv) == 3 and sys.argv[1] == "path":
        print(load().path(sys.argv[2]))
    elif len(sys.argv) == 5 and sys.argv[1] == "set":
        value = sys.argv[4]
        if "|" in value:
            sys.exit("半角の「|」は表を壊すので使えない(全角「｜」にする)")
        load().set_cell(int(sys.argv[2]), sys.argv[3], value)
    else:
        sys.exit("使い方: channel.py path <table|articles|meta|images|transcripts|videos|critiques|...>\n"
                 "        channel.py set <番号> <列名> <値>")
