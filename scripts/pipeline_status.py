#!/usr/bin/env python3
"""
動画ごとに、パイプラインのどの工程まで済んでいるかを判定する(読み取りのみ)。

使い方:
  python3 scripts/pipeline_status.py 12             # 1本
  python3 scripts/pipeline_status.py 10-20 5         # 範囲と番号の混在
  python3 scripts/pipeline_status.py --pending      # 次の工程が残っている行だけ
  python3 scripts/pipeline_status.py 12  --remote   # note.com の予約状態も GET で確かめる(読み取りのみ)
  python3 scripts/pipeline_status.py 12  --json     # 機械向け

工程と判定(SKILL.md の工程表と同じ):
  fetch     文字起こしmd・動画本体・00_thumbnail.jpg がある
  title     表の「note記事の名前」が空でない
  write     記事md がある
  lint      lint_article.py の ERROR が 0
  critique  critiques/{id}.md の状態ブロックに critiqued: がある
  eye       状態ブロックに eye_checked: がある
  push      meta がある、かつ meta の pushed_sha が記事mdのハッシュと一致
            (pushed_sha が無い旧記事は、表の noteのURL と 下書き☑ があれば済みとみなす)
  reserve   表の「予約投稿完了」が☑(--remote のときは note.com の is_reserved / is_published も見る)

human_review が空でない記事は、push までで止まり next=human になる。
旧記事(critiques が無い、または状態ブロックが無い)で、予約済みのものは critique/eye を
"legacy"(当時の手順で済ませた扱い)とし、やり直し対象にしない。
"""
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import channel
import lint_article

STEPS = ["fetch", "title", "write", "lint", "critique", "eye", "push", "reserve"]
LEGACY_META = "articles/{vid}.note.json"  # articles/meta/ 移動前の置き場所


def md_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def read_block(path: pathlib.Path) -> dict:
    """critiques/{id}.md 先頭の <!-- pipeline ... --> を dict にする"""
    if not path.exists():
        return {}
    m = re.search(r"<!--\s*pipeline\s*\n(.*?)-->", path.read_text(encoding="utf-8"), re.S)
    if not m:
        return {"_no_block": True}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.split("←")[0].strip()
    hr = out.get("human_review", "[]")
    out["human_review"] = [] if hr in ("", "[]") else [x.strip(" '\"") for x in hr.strip("[]").split(",") if x.strip()]
    return out


def status(ch, no: int, row: dict, remote_cookie=None) -> dict:
    vid = row["video_id"]
    s = {"no": no, "video_id": vid, "done": {}, "notes": [], "human_review": []}
    d = s["done"]
    art = ch.article(no)
    stem = art.stem if art else None

    if not vid:
        s["notes"].append("URLが無い")
    tr = list(ch.path("transcripts").glob(f"{no:02d}_*.md")) + (
        list(ch.path("transcripts").glob(f"{vid}.*vtt")) if vid else [])
    vids = list(ch.path("videos").glob(f"{vid}.*")) if vid else []
    thumb = (ch.path("images") / stem / "00_thumbnail.jpg").exists() if stem else bool(
        list(ch.path("images").glob(f"{no:02d}_*/00_thumbnail.jpg")))
    d["fetch"] = bool(tr) and thumb
    if tr and thumb and not vids:
        s["notes"].append("動画本体が無い(目チェックの差し替えに必要)")

    d["title"] = bool(row.get(channel.COL_NOTE_TITLE))
    d["write"] = art is not None

    if art:
        errs = [i for i in lint_article.lint(art, ch) if i[0] == "ERROR"]
        d["lint"] = not errs
        if errs:
            s["notes"].append("lint ERROR: " + " / ".join(m for _, _, m in errs[:3]))
    else:
        d["lint"] = False

    meta = ch.load_meta(vid) if vid else None
    if vid and meta is None and (channel.ROOT / LEGACY_META.format(vid=vid)).exists():
        s["notes"].append(f"meta が旧パス {LEGACY_META.format(vid=vid)} にある(articles/meta/ へ移す)")

    reserved_table = row.get(channel.COL_RESERVED) == channel.CHECK_ON
    block = read_block(ch.path("critiques") / f"{vid}.md") if vid else {}
    # 旧手順で下書きまで作った記事(meta に pushed_sha が無い)は、添削・目チェックを当時の手順で済ませた扱い
    old_flow = bool(meta) and not meta.get("pushed_sha") and row.get(channel.COL_DRAFT) == channel.CHECK_ON
    legacy = reserved_table or old_flow
    d["critique"] = bool(block.get("critiqued")) or ("legacy" if legacy else False)
    d["eye"] = bool(block.get("eye_checked")) or ("legacy" if legacy else False)
    s["human_review"] = block.get("human_review", [])

    if meta:
        if meta.get("pushed_sha"):
            d["push"] = art is not None and meta["pushed_sha"] == md_sha(art)
            if not d["push"]:
                s["notes"].append("記事mdが最後に下書きへ送った版から変わっている")
        else:
            d["push"] = "legacy" if (row.get(channel.COL_NOTE_URL) and row.get(channel.COL_DRAFT) == channel.CHECK_ON) else False
    else:
        d["push"] = False
        if row.get(channel.COL_DRAFT) == channel.CHECK_ON:
            s["notes"].append("表は下書き☑だが meta が無い")

    d["reserve"] = reserved_table
    if remote_cookie and meta:
        import note_api
        try:
            note = note_api.get_note(remote_cookie, meta["note_key"])
            s["remote"] = "公開済み" if note.get("is_published") else (
                f"予約済み {note.get('reserved_publish_at')}" if note.get("is_reserved") else "下書き")
            if (note.get("is_reserved") or note.get("is_published")) != reserved_table:
                s["notes"].append(f"表の予約☑と note.com の状態({s['remote']})が食い違う")
        except note_api.NoteAuthError as e:
            s["remote"] = f"取得できない: {str(e).splitlines()[0]}"

    # 予約まで済んでいれば、前の工程の成果物が欠けていても(動画を消した等)完了とする
    s["next"] = None if d["reserve"] else next((st for st in STEPS if not d.get(st)), None)
    if d["reserve"]:
        s["notes"] = [n for n in s["notes"] if not n.startswith("動画本体が無い")]
    if s["human_review"] and s["next"] in ("push", "reserve"):
        s["next"] = "human"
    return s


def parse_targets(args: list[str], rows: dict) -> list[int]:
    out = []
    for a in args:
        m = re.fullmatch(r"(\d+)[-〜~](\d+)", a)
        if m:
            out += [n for n in range(int(m[1]), int(m[2]) + 1) if n in rows]
        elif a.isdigit():
            out.append(int(a))
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    ch = channel.load()
    rows = ch.rows()
    targets = parse_targets(args, rows) or (sorted(rows) if "--pending" in flags else [])
    if not targets:
        sys.exit(__doc__)
    cookie = None
    if "--remote" in flags:
        import note_api
        cookie = note_api.load_cookie()
    results = []
    for no in targets:
        if no not in rows:
            results.append({"no": no, "next": None, "notes": ["表に無い番号"], "done": {}, "human_review": []})
            continue
        results.append(status(ch, no, rows[no], cookie))
    if "--pending" in flags:
        results = [r for r in results if r["next"]]
    if "--json" in flags:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return 0
    mark = {True: "○", False: "×", "legacy": "旧"}
    print(f"[{ch.name}]  " + " ".join(f"{s:>8}" for s in STEPS) + "   次の工程")
    for r in results:
        cols = " ".join(f"{mark.get(r['done'].get(s), '-'):>8}" for s in STEPS)
        print(f"{r['no']:>4} {cols}   {r['next'] or '完了'}"
              + (f"  remote={r['remote']}" if r.get("remote") else ""))
        for n in r["notes"] + [f"要人間: {h}" for h in r["human_review"]]:
            print(f"       - {n}")
    print(f"\n{len(results)}本  次の工程が残っている: {sum(1 for r in results if r['next'])}本")
    return 0


if __name__ == "__main__":
    sys.exit(main())
