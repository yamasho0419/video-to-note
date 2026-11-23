#!/usr/bin/env python3
"""
管理表の末尾に動画の行を足す。番号は最大+1、題名は yt-dlp で取る。
投稿予定日時は、表で一番遅い日時の次の空き枠(チャンネル設定の slots)を入れる。

使い方:
  python3 scripts/add_video.py <URL>... [--dry-run] [--no-date]
既に表にある動画IDは足さない。
"""
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import channel as _channel


def next_slot(latest: datetime, slots: list[str]) -> datetime:
    times = sorted(datetime.strptime(s, "%H:%M").time() for s in slots)
    day = latest.date()
    for _ in range(366):
        for t in times:
            cand = datetime.combine(day, t)
            if cand > latest:
                return cand
        day += timedelta(days=1)
    raise SystemExit("空き枠が見つからない")


def main():
    urls = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry, no_date = "--dry-run" in sys.argv, "--no-date" in sys.argv
    if not urls:
        sys.exit(__doc__)
    ch = _channel.load()
    rows = ch.rows()
    have = {r["video_id"] for r in rows.values()}
    head = ch.header()
    dates = [datetime.strptime(r[_channel.COL_AT], "%Y-%m-%d %H:%M") for r in rows.values()
             if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", r.get(_channel.COL_AT, ""))]
    latest = max(dates) if dates else datetime.now()
    no = max(rows) if rows else 0
    new_lines = []
    for url in urls:
        m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
        if not m:
            print(f"動画IDが読めない: {url}"); continue
        vid = m.group(1)
        if vid in have:
            print(f"表に既にある: {vid}"); continue
        title = subprocess.run(["yt-dlp", "--skip-download", "--print", "%(title)s", url],
                               capture_output=True, text=True).stdout.strip()
        if not title:
            print(f"題名が取れない(yt-dlp 失敗): {url}"); continue
        title = title.replace("|", "｜")  # 半角の縦線は表を壊す
        no += 1
        at = "" if no_date else next_slot(latest, ch.cfg.get("slots", ["12:00"]))
        if at:
            latest = at
        cell = {_channel.COL_NO: str(no), _channel.COL_URL: f"https://www.youtube.com/watch?v={vid}",
                _channel.COL_TITLE: title, _channel.COL_AT: at.strftime("%Y-%m-%d %H:%M") if at else "",
                _channel.COL_DRAFT: _channel.CHECK_OFF, _channel.COL_RESERVED: _channel.CHECK_OFF}
        new_lines.append("| " + " | ".join(cell.get(h, "") for h in head) + " |")
        have.add(vid)
        print(f"{no}: {title} / 予定 {cell[_channel.COL_AT] or '(なし)'}")
    if dry or not new_lines:
        return
    table = ch.path("table")
    text = table.read_text(encoding="utf-8")
    table.write_text(text.rstrip("\n") + "\n" + "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""),
                     encoding="utf-8")


if __name__ == "__main__":
    main()
