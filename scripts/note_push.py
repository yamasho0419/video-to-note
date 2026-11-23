#!/usr/bin/env python3
"""
記事mdを note.com の下書きに反映する(新規作成も更新もこれ1本)。公開・予約はしない。

使い方:
  python3 scripts/note_push.py <番号> [--dry-run] [--eyecatch] [--force-remote] [--reupload=03_a.jpg,05_b.jpg]
  --reupload: 同じファイル名のまま差し替えた画像(目チェック)を上げ直す
  --eyecatch: 見出し画像を設定し直す(新規作成時は自動で設定する)

流れ:
  1. 管理表の行と記事mdを特定し、lint の ERROR が無いことを確かめる
  2. meta が無ければ: 空の下書きを作成 → 画像アップロード → 見出し画像(00_thumbnail.jpg)→ meta 保存
                       → 表に noteのURL と 下書き☑
     meta があれば: note.com の状態を GET し、予約済み・公開済みなら止める(予約本文は draft_save で変わらないため)
                    前回送った後に note.com 側だけ手で直されていたら止める(--force-remote で無視)
                    旧手順の下書き(remote_sha が無い)も止める。本文を見比べてから --force-remote で送る
  3. 本文HTMLを組み立てて draft_save → GET し直して題名と本文を確かめる
  4. meta に pushed_sha(記事mdのハッシュ)と remote_sha(note.com 側本文のハッシュ)を記録する

チャンネルは NOTE_CHANNEL(既定 sample)。フッターのリンク規則は channels/{c}/channel.json の footer.links。
"""
import hashlib
import html
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import channel as _channel
import lint_article
import note_api

CH = note_api.CHANNEL
ROOT = note_api.ROOT
BACKUP_DIR = ROOT / ".tmp_subs"


class PushStop(Exception):
    """人間の判断が要るので止める"""


def md_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def remote_sha(body_html: str) -> str:
    """note.com の本文から、タグ・空白・埋め込みの中身を除いた文字列のハッシュ(手直しの検出用)"""
    body = re.sub(r"<figure[^>]*embedded-service[^>]*>.*?</figure>", "", body_html or "", flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "", body))
    return hashlib.sha256(re.sub(r"\s+", "", text).encode()).hexdigest()[:16]


def inline(text: str) -> str:
    """エスケープ + **太字** + フッターのインラインリンク(チャンネル設定)"""
    t = html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", lambda m: note_api.b(m.group(1)), t)
    for rule in CH.cfg.get("footer", {}).get("links", []):
        if t.startswith(rule["para_prefix"]) and rule["find"] in t:
            linked = rule["find"].replace(rule["text"], note_api.a(rule["text"], rule["url"]), 1)
            t = t.replace(rule["find"], rule.get("prefix_html", "") + linked, 1)
    return t


def build_body(md_path: pathlib.Path, video_id: str, cookie: str, note_key: str, image_urls: dict):
    lines = md_path.read_text(encoding="utf-8").split("\n")
    embed_after = CH.cfg.get("footer", {}).get("video_embed_after")
    title, parts, i, skipping_toc = None, [], 0, False
    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            i += 1
            continue
        if skipping_toc and not line.startswith("- "):
            skipping_toc = False
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
        elif line.startswith("## "):
            heading = line[3:].strip()
            if heading == "目次":
                parts.append(note_api.toc())
                skipping_toc = True
            else:
                parts.append(note_api.h2(inline(heading)))
        elif line.startswith("### "):
            parts.append(note_api.h3(inline(line[4:].strip())))
        elif skipping_toc and line.startswith("- "):
            pass
        elif m := re.match(r"!\[.*?\]\(images/[^/]+/([^)]+)\)", line):
            parts.append(note_api.figure(image_urls[m.group(1)]))
        elif line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(inline(lines[i][2:].strip()))
                i += 1
            parts.append(note_api.ul(items))
            continue
        elif re.match(r"\d+\. ", line):
            items = []
            while i < len(lines) and re.match(r"\d+\. ", lines[i]):
                items.append(inline(re.sub(r"^\d+\. ", "", lines[i]).strip()))
                i += 1
            parts.append(note_api.ol(items))
            continue
        elif line.startswith("> "):
            quoted = []
            while i < len(lines) and lines[i].startswith("> "):
                quoted.append(inline(lines[i][2:].strip()))
                i += 1
            parts.append(note_api.quote("".join(quoted)))
            continue
        elif re.fullmatch(r"https?://\S+", line):
            # URLだけの行(書籍告知のAmazon・楽天など)はURLそのものをリンクにした段落にする
            parts.append(note_api.p(note_api.a(html.escape(line, quote=False), html.escape(line))))
        else:
            parts.append(note_api.p(inline(line)))
            if embed_after and line.startswith(embed_after):
                if cookie:
                    parts.append(note_api.link_card(cookie, note_key, f"https://www.youtube.com/watch?v={video_id}"))
                else:
                    parts.append("<!-- dry-run: YouTube埋め込み -->")
        i += 1
    if not title:
        raise SystemExit("タイトル(# 行)が見つからない")
    return title, "".join(parts)


def push(no: int, dry: bool = False, eyecatch: bool = False, force_remote: bool = False,
         reupload: tuple = ()) -> str:
    row = CH.row(no)
    vid = row["video_id"]
    md = CH.article(no)
    if not vid or md is None:
        raise SystemExit(f"{no}: URL か記事md が無い")
    errs = [i for i in lint_article.lint(md, CH) if i[0] == "ERROR"]
    if errs:
        raise SystemExit(f"{no}: lint ERROR があるので送らない: {errs[0][2]}")

    meta = note_api.load_note_meta(vid)
    cookie = None if dry else note_api.load_cookie()
    if cookie and not note_api.check_cookie_valid(cookie):
        raise note_api.NoteAuthError("Cookie が無効")

    if meta is None:
        if row.get(_channel.COL_NOTE_URL):
            raise PushStop(f"{no}: 表に noteのURL があるのに meta が無い。既存の下書きと紐づけてから送る")
        if dry:
            print(f"[dry-run] {no}: 新規下書きを作成する予定", file=sys.stderr)
            meta = {"note_id": "DRY", "note_key": "DRY", "image_urls": {}}
        else:
            note_id, note_key = note_api.create_note(cookie)
            meta = {"note_id": note_id, "note_key": note_key, "image_urls": {}}
            eyecatch = True
            note_api.save_note_meta(vid, note_id, note_key, {}, channel_no=no,
                                    channel_url=row[_channel.COL_URL], channel_title=row[_channel.COL_TITLE])
            CH.set_cell(no, _channel.COL_NOTE_URL, f"https://editor.note.com/notes/{note_key}/edit/")
            CH.set_cell(no, _channel.COL_DRAFT, _channel.CHECK_ON)
            print(f"新規下書き: https://editor.note.com/notes/{note_key}/edit/", file=sys.stderr)
    elif not dry:
        note = note_api.get_note(cookie, meta["note_key"])
        if note.get("is_published") or note.get("is_reserved"):
            raise PushStop(f"{no}: note.com 側が{'公開済み' if note.get('is_published') else '予約済み'}。"
                           "draft_save では予約本文が変わらないので止める")
        if not force_remote:
            if not meta.get("remote_sha"):
                raise PushStop(f"{no}: 前回送った本文の記録(remote_sha)が無い旧下書き。note.com 側だけ手で直されていないか"
                               "本文を見比べてから --force-remote で送る")
            if remote_sha(note.get("body", "")) != meta["remote_sha"]:
                raise PushStop(f"{no}: 前回送ったあとに note.com 側の本文が変わっている(手直しの可能性)")
        BACKUP_DIR.mkdir(exist_ok=True)
        (BACKUP_DIR / f"{vid}.before.json").write_text(json.dumps(note, ensure_ascii=False))

    # 目チェックで同じファイル名のまま差し替えた画像は、古いURLを捨てて上げ直す
    image_urls = {k: v for k, v in meta.get("image_urls", {}).items() if k not in reupload}
    text = md.read_text(encoding="utf-8")
    refs = re.findall(r"!\[.*?\]\(images/([^/]+)/([^)]+)\)", text)
    for d, name in refs:
        if name not in image_urls:
            path = CH.path("images") / d / name
            image_urls[name] = "https://example.invalid/" + name if dry else note_api.upload_image(cookie, path)
    thumb = CH.path("images") / md.stem / "00_thumbnail.jpg"
    if eyecatch and not dry:
        note_api.set_eyecatch(cookie, meta["note_id"], thumb)
        if "00_thumbnail.jpg" not in image_urls:
            image_urls["00_thumbnail.jpg"] = note_api.upload_image(cookie, thumb)

    title, body_html = build_body(md, vid, cookie, meta["note_key"], image_urls)
    print(f"{no}: title={title} body_len={len(body_html)} images={len(refs)}", file=sys.stderr)
    if dry:
        return meta["note_key"]

    note_api.save_draft(cookie, meta["note_id"], title, body_html)
    after = note_api.get_note(cookie, meta["note_key"])
    if after.get("name") != title:
        raise PushStop(f"{no}: 保存後の題名が「{after.get('name')}」で、送った題名と違う")
    note_api.save_note_meta(vid, meta["note_id"], meta["note_key"], image_urls,
                            channel_no=no, channel_url=row[_channel.COL_URL], channel_title=row[_channel.COL_TITLE],
                            pushed_sha=md_sha(md), remote_sha=remote_sha(after.get("body", "")))
    print(f"完了。編集画面: https://editor.note.com/notes/{meta['note_key']}/edit/", file=sys.stderr)
    return meta["note_key"]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1 or not args[0].isdigit():
        sys.exit(__doc__)
    try:
        push(int(args[0]), dry="--dry-run" in sys.argv, eyecatch="--eyecatch" in sys.argv,
             force_remote="--force-remote" in sys.argv,
             reupload=tuple(n for a in sys.argv if a.startswith("--reupload=") for n in a[11:].split(",") if n))
    except PushStop as e:
        sys.exit(f"要人間: {e}")


if __name__ == "__main__":
    main()
