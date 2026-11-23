#!/usr/bin/env python3
"""
channel_url.md の「投稿予定日時」列に従って、note.comの下書きを予約投稿に設定する。

使い方:
  python3 scripts/note_schedule.py status            # 全件の予約状態を読み取り表示(読み取りのみ)
  python3 scripts/note_schedule.py next [件数]       # 次に予約すべき下書きを番号順に表示(既定4件、エディタURL付き)
  python3 scripts/note_schedule.py 14 15 16          # 番号指定: dry-run(送信内容の表示のみ)
  python3 scripts/note_schedule.py 14 15 16 --commit # 実際に予約を設定する

仕組み(2026-10-02 に DevTools で実測した、エディタの「予約投稿」確定リクエスト):
  PUT https://note.com/api/v1/text_notes/{note_id}
  body: {..., "status": "reserved", "publish_at": "2026-10-05T03:00:00.000Z", "free_body": <本文HTML>, ...}
  publish_at はUTC。channel_url.mdはJSTで書くので変換する。
  読み取りは GET https://note.com/api/v3/notes/{note_key} (reserved_publish_at がJST)。

題名: 予約のときに管理表の「note記事の名前」列の題名で送る(空なら下書きの題名のまま)。
予約に成功したら管理表の「予約投稿完了」を☑にする。
管理表・Cookie・meta の場所はチャンネル設定(NOTE_CHANNEL、既定 sample)に従う。

安全装置:
  - 既定はdry-run。--commit が無い限りPUTしない
  - 過去日時は拒否 / すでに reserved/公開済みの記事はスキップ
  - 予約後にGETし直して reserved_publish_at が一致するか検証、不一致なら異常終了
"""
import html
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import note_api

import channel as _channel

ROOT = note_api.ROOT
CH = note_api.CHANNEL
JST = timezone(timedelta(hours=9))


def load_schedule() -> dict[int, dict]:
    """投稿予定日時がある行だけ。title は「note記事の名前」列(空なら None)"""
    rows = {}
    for no, r in CH.rows().items():
        at = r.get(_channel.COL_AT, "")
        if r["_broken"] or not r["video_id"] or not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", at):
            continue
        rows[no] = {
            "video_id": r["video_id"],
            "at": datetime.strptime(at, "%Y-%m-%d %H:%M").replace(tzinfo=JST),
            "title": r.get(_channel.COL_NOTE_TITLE) or None,
        }
    return rows


get_note = note_api.get_note


def normalize_body(body: str) -> str:
    """GETで返る表示用HTMLを、エディタがPUTで送る形に戻す(実測した差分のみ)"""
    body = re.sub(r' contenteditable="false"| draggable="false"', "", body)
    # 埋め込みfigure(YouTube等)は中身のiframeを落とし、空にして送られていた
    body = re.sub(
        r'(<figure[^>]*embedded-service="[^"]+"[^>]*>).*?(</figure>)', r"\1  \2", body, flags=re.S
    )
    return body


def build_payload(note: dict, at: datetime, title: str | None = None) -> dict:
    free_body = normalize_body(note["body"])
    text_len = len(html.unescape(re.sub(r"<[^>]+>", "", free_body)))
    return {
        "author_ids": [],
        "body_length": text_len,
        "disable_comment": False,
        "exclude_from_creator_top": False,
        "exclude_ai_learning_reward": False,
        "free_body": free_body,
        "hashtags": [h["hashtag"]["name"] for h in note.get("hashtag_notes", [])],
        "image_keys": re.findall(r"assets\.st-note\.com/img/([\w-]+)\.", free_body),
        "index": True,
        "is_refund": False,
        "limited": False,
        "magazine_ids": [],
        "magazine_keys": [],
        "name": title or note["name"],
        "pay_body": "",
        "price": 0,
        "send_notifications_flag": True,
        "separator": None,
        "slug": f"slug-{note['key']}",
        "status": "reserved",
        "publish_at": at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "circle_permissions": [],
        "discount_campaigns": [],
        "lead_form": {"is_active": False, "consent_url": ""},
        "line_add_friend": {"is_active": False, "keyword": "", "add_friend_url": ""},
        "line_add_friend_access_token": note.get("line_add_friend_access_token", ""),
        "pro_coupon_keys": [],
    }


def put_reserve(cookie: str, note_id: str, payload: dict) -> dict:
    path = ROOT / ".secrets" / "_payload_tmp.json"
    path.write_text(json.dumps(payload, ensure_ascii=False))
    try:
        cmd = [
            "curl", "-s", "-X", "PUT", f"https://note.com/api/v1/text_notes/{note_id}",
            "-H", "content-type: application/json", "-b", cookie, *note_api.COMMON_HEADERS,
            "--data-binary", f"@{path}",
        ]
        return note_api._curl_json(cmd)
    finally:
        path.unlink(missing_ok=True)


def state(note: dict) -> str:
    if note.get("is_published"):
        return "公開済み"
    if note.get("is_reserved"):
        return f"予約済み {note.get('reserved_publish_at')}"
    return "下書き"


def main() -> None:
    args = sys.argv[1:]
    commit = "--commit" in args
    args = [a for a in args if a != "--commit"]
    if not args:
        sys.exit(__doc__)
    schedule = load_schedule()
    cookie = note_api.load_cookie()
    if not note_api.check_cookie_valid(cookie):
        sys.exit("Cookieが無効です。再キャプチャしてください。")

    if args == ["status"]:
        for no in sorted(schedule):
            meta = note_api.load_note_meta(schedule[no]["video_id"])
            if not meta:
                print(f"{no:>3} 下書きなし(note未作成) 予定 {schedule[no]['at']:%m/%d %H:%M}")
                continue
            try:
                note = get_note(cookie, meta["note_key"])
            except note_api.NoteAuthError:
                print(f"{no:>3} noteが見つからない(削除済み?) key={meta['note_key']}")
                continue
            print(f"{no:>3} {state(note)} / 予定 {schedule[no]['at']:%m/%d %H:%M} / {note['name'][:30]}")
        return

    if args[0] == "next":
        limit = int(args[1]) if len(args) > 1 else 4
        shown = 0
        for no in sorted(schedule):
            if shown >= limit:
                break
            meta = note_api.load_note_meta(schedule[no]["video_id"])
            if not meta:
                continue
            note = get_note(cookie, meta["note_key"])
            if note.get("is_published") or note.get("is_reserved"):
                continue
            print(f"{no:>3} 予定 {schedule[no]['at']:%m/%d %H:%M} {note['name'][:30]}")
            print(f"    https://editor.note.com/notes/{meta['note_key']}/edit/")
            shown += 1
        return

    now = datetime.now(JST)
    for no in map(int, args):
        s = schedule.get(no)
        if not s:
            print(f"{no}: channel_url.md に投稿予定日時が無い。スキップ"); continue
        meta = note_api.load_note_meta(s["video_id"])
        if not meta:
            print(f"{no}: .note.json が無い(下書き未作成)。スキップ"); continue
        if s["at"] <= now:
            print(f"{no}: 予定 {s['at']:%Y-%m-%d %H:%M} は過去。スキップ"); continue
        note = get_note(cookie, meta["note_key"])
        if note.get("is_published") or note.get("is_reserved"):
            print(f"{no}: すでに {state(note)}。スキップ"); continue
        payload = build_payload(note, s["at"], s["title"])
        print(f"{no}: 題名「{payload['name']}」 → {s['at']:%Y-%m-%d %H:%M} JST (publish_at={payload['publish_at']}) "
              f"本文{len(payload['free_body'])}字 画像{len(payload['image_keys'])}枚")
        if not s["title"]:
            print("   注意: 「note記事の名前」が空なので、下書きの題名のまま予約する")
        if not commit:
            print("   dry-run: 送信しない(--commit で実行)"); continue
        put_reserve(cookie, meta["note_id"], payload)
        after = get_note(cookie, meta["note_key"])
        want = s["at"].strftime("%Y-%m-%dT%H:%M")
        if not after.get("is_reserved") or not str(after.get("reserved_publish_at", "")).startswith(want):
            sys.exit(f"{no}: 予約後の検証に失敗: {state(after)}。note.comで状態を確認してください")
        if after.get("name") != payload["name"]:
            print(f"   注意: 予約後の題名が「{after.get('name')}」で、送った題名と違う")
        CH.set_cell(no, _channel.COL_RESERVED, _channel.CHECK_ON)
        print(f"   OK: {state(after)}(表の「予約投稿完了」を☑にした)")


if __name__ == "__main__":
    main()
