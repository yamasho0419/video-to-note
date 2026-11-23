#!/usr/bin/env python3
"""
記事mdの機械判定できる執筆ルールを一括チェックする(添削の前段)。
ルールの本文は .claude/skills/note-pipeline/references/writing_rules.md。記号(F1, S6 など)はそちらと対応する。

使い方:
  python3 scripts/lint_article.py 12             # 番号で指定
  python3 scripts/lint_article.py 12 13 --strict 
  python3 scripts/lint_article.py --all          # 記事フォルダの {番号}_*.md を全て
  python3 scripts/lint_article.py --all --errors-only
  python3 scripts/lint_article.py --all --summary # 種類ごとの件数だけ
チャンネルは NOTE_CHANNEL(既定 sample)。フッターの目印・誤記リストはチャンネル設定から読む。

判定項目:
  ERROR  title       1行目が「# 」見出しで、「無料」を含まない
  WARN   title       題名が45字超
  WARN   table_title 表の「note記事の名前」が45字超/「無料」/半角「|」を含む(予約時の題名になる)
  ERROR  image       ![](images/...) の参照先が存在する
  WARN   image_unused 画像フォルダにあるのに本文で使っていない画像(I4)
  WARN   image_dup   同じ画像を2回以上使っている(参照の取り違えの疑い)
  ERROR  footer      固定フッターの目印が順番どおりにあり、最後の行が注記
  WARN   footer_text フッターの段落が channels/{c}/footer.md と一字一句同じでない
  WARN   sentence    一文が100字超(目安は60字)(R6)
  WARN   paragraph   1段落が5文以上、または200字超(R1)
  WARN   comma       1文に読点が3つ以上(R3)
  WARN   pronoun     地の文で「僕」「俺」(鉤括弧の中は除く)(R5)
  WARN   cta         「一人で悩まず」など直接相談を促すCTA
  WARN   body_cta    本文中の問い合わせ誘導(チャンネル設定の正規表現)
  WARN   frequency   1回の質問・1人の発言を一般化する定型句(F1)
  WARN   indirect    「答えは『〜』でした」型の間接話法(S10)
  WARN   greeting    動画の挨拶が残っている(S9)
  WARN   other_article 「別の記事」(参照先が実在するか確認する)(F6)
  WARN   name        名前・名称の誤記(チャンネル設定)(F8)
  WARN   toc         目次の項目と h2 見出しが一致しない/目次が空(S6)
  WARN   h2_count    h2 が7個以上(S1)
  WARN   count       「Nつ」と書いた直後のリストの項目数が違う(S11)
  WARN   bold        太字が多すぎる(h2 1つあたり平均3か所超)(R4)
  WARN   zehi        結びの最後の段落に「ぜひ」(フッター冒頭の「ぜひ」と続く)(S12)

終了コード: ERRORがあれば1(--strict ならWARNでも1)。
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import channel as _channel

MAX_SENTENCE = 100
MAX_PARA_SENTENCES = 4  # 目安は1〜3文。4文までは許容、5文以上を警告
MAX_PARA_CHARS = 200
MAX_COMMAS = 2
MAX_TITLE = 45
MAX_H2 = 6
PRONOUN_RE = re.compile(r"(僕|俺)")
CTA_RE = re.compile(r"(一人で悩まず|一度(お)?話を聞かせて|まずはご相談ください)")
FREQ_RE = re.compile(r"(をいただくことがあります|と聞かれることがあります|よく聞かれ|こんな声を聞きます|と考えている方は多い|という方は多いです)")
INDIRECT_RE = re.compile(r"答えは『[^』]*』でした")
GREETING_RE = re.compile(r"(皆さんこんにちは|みなさんこんにちは|今日のテーマは)")
OTHER_RE = re.compile(r"別の記事")
KANSUJI = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
COUNT_RE = re.compile(r"([1-9]|[一二三四五六七八九十])つ(あります|です|ある|に分けて|紹介|解説|挙げ)")
LIST_RE = re.compile(r"^([-*]|\d+\.)\s")


def find_articles(arg: str, ch) -> list[pathlib.Path]:
    if arg.isdigit():
        return sorted(ch.path("articles").glob(f"{int(arg):02d}_*.md"))
    p = pathlib.Path(arg)
    return [p] if p.exists() else []


def split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[。！？])", text) if s.strip()]


def strip_quotes(text: str) -> str:
    return re.sub(r"「[^「」]*」|『[^『』]*』", "", text)


def footer_paragraphs(ch) -> list[str]:
    p = ch.path("footer")
    if not p.exists():
        return []
    return [x.strip() for x in re.split(r"\n\s*\n", p.read_text(encoding="utf-8")) if x.strip()]


def lint(path: pathlib.Path, ch=None) -> list[tuple[str, str, str]]:
    ch = ch or _channel.load()
    fcfg = ch.cfg.get("footer", {})
    markers, start = fcfg.get("markers", []), fcfg.get("start", "")
    lcfg = ch.cfg.get("lint", {})
    out = []
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    # title
    first = lines[0] if lines else ""
    title = first[2:].strip()
    if not first.startswith("# "):
        out.append(("ERROR", "title", "1行目が「# 」見出しではない"))
    elif "無料" in title:
        out.append(("ERROR", "title", f"題名に「無料」を含む: {title}"))
    elif len(title) > MAX_TITLE:
        out.append(("WARN", "title", f"題名が{len(title)}字(目安{MAX_TITLE}字以内)"))
    m = re.match(r"(\d+)_", path.name)
    if m:
        row = ch.rows().get(int(m.group(1)))
        nt = (row or {}).get(_channel.COL_NOTE_TITLE, "")
        if nt and (len(nt) > MAX_TITLE or "無料" in nt):
            out.append(("WARN", "table_title", f"表の「note記事の名前」: {len(nt)}字 {nt}"))

    # image
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    for ref in refs:
        if not ref.startswith("http") and not (path.parent / ref).exists():
            out.append(("ERROR", "image", f"参照切れ: {ref}"))
    for name, c in collections.Counter(pathlib.Path(r).name for r in refs).items():
        if c > 1:
            out.append(("WARN", "image_dup", f"同じ画像を{c}回使っている: {name}"))
    img_dir = ch.path("images") / path.stem
    if img_dir.is_dir():
        used = {pathlib.Path(r).name for r in refs}
        for f in sorted(img_dir.glob("*.jpg")):
            if f.name != "00_thumbnail.jpg" and f.name not in used:
                out.append(("WARN", "image_unused", f"本文で使っていない画像: {f.name}"))

    # footer
    pos = -1
    for mk in markers:
        i = text.find(mk, pos + 1)
        if i < 0:
            out.append(("ERROR", "footer", f"フッター欠落/順序違い: 「{mk}」"))
            break
        pos = i
    if markers and text.rstrip().splitlines()[-1].strip() != markers[-1]:
        out.append(("ERROR", "footer", f"末尾の行が「{markers[-1][:12]}〜」になっていない"))
    fi = text.find(start) if start else -1
    fixed = footer_paragraphs(ch)
    if fi >= 0 and fixed:
        actual = [x.strip() for x in re.split(r"\n\s*\n", text[fi:]) if x.strip()]
        diff = [f for f in fixed if f not in actual]
        if diff:
            out.append(("WARN", "footer_text", f"固定文面と違う段落 {len(diff)}個: {diff[0][:30]}…"))

    # body (フッター・見出し・画像・目次を除く)
    body = text[:fi] if fi >= 0 else text
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
    h2s = [b[3:].strip() for b in blocks if b.startswith("## ") and b[3:].strip() != "目次"]
    if len(h2s) > MAX_H2:
        out.append(("WARN", "h2_count", f"h2 が{len(h2s)}個(目安3〜6個。補足・細目は h3 に)"))

    toc_items, in_toc = [], False
    paras = []
    for bi, b in enumerate(blocks):
        if b.startswith("## 目次"):
            in_toc = True
            rest = b.split("\n")[1:]
            toc_items += [re.sub(r"^([-*]|\d+\.)\s*", "", x).strip() for x in rest if LIST_RE.match(x)]
            continue
        if in_toc and LIST_RE.match(b):
            toc_items += [re.sub(r"^([-*]|\d+\.)\s*", "", x).strip() for x in b.split("\n") if LIST_RE.match(x)]
            continue
        in_toc = False
        if b.startswith(("#", "![", ">")):
            continue
        if LIST_RE.match(b):
            continue
        paras.append((bi, b))
    if "## 目次" in body:
        if not toc_items:
            out.append(("WARN", "toc", "目次の箇条書きが空"))
        elif [re.sub(r"\*\*", "", t) for t in toc_items] != [re.sub(r"\*\*", "", h) for h in h2s]:
            out.append(("WARN", "toc", f"目次{len(toc_items)}項目と h2 {len(h2s)}個が一致しない"))

    for bi, p in paras:
        flat = p.replace("\n", "")
        sents = split_sentences(flat)
        for s in sents:
            if len(s) > MAX_SENTENCE:
                out.append(("WARN", "sentence", f"{len(s)}字: {s[:40]}…"))
            if s.count("、") > MAX_COMMAS:
                out.append(("WARN", "comma", f"読点{s.count('、')}個: {s[:40]}…"))
        if len(sents) > MAX_PARA_SENTENCES or len(flat) > MAX_PARA_CHARS:
            out.append(("WARN", "paragraph", f"{len(sents)}文{len(flat)}字: {flat[:40]}…"))
        bare = strip_quotes(flat)
        if mm := PRONOUN_RE.search(bare):
            out.append(("WARN", "pronoun", f"{mm.group(0)}: {flat[:40]}…"))
        for kind, rx in (("cta", CTA_RE), ("frequency", FREQ_RE), ("indirect", INDIRECT_RE),
                         ("greeting", GREETING_RE), ("other_article", OTHER_RE)):
            if mm := rx.search(flat):
                out.append(("WARN", kind, f"{mm.group(0)}: {flat[:40]}…"))
        if lcfg.get("body_cta") and (mm := re.search(lcfg["body_cta"], flat)):
            out.append(("WARN", "body_cta", f"{mm.group(0)}: {flat[:40]}…"))
        for typo in lcfg.get("name_typos", []):
            if typo in flat:
                out.append(("WARN", "name", f"誤記「{typo}」: {flat[:40]}…"))
        # 「Nつ」と直後のリスト
        if mm := COUNT_RE.search(flat):
            n = int(mm.group(1)) if mm.group(1).isdigit() else KANSUJI[mm.group(1)]
            nxt = next((b for b in blocks[bi + 1:] if not b.startswith("![")), "")
            if LIST_RE.match(nxt):
                items = sum(1 for x in nxt.split("\n") if LIST_RE.match(x))
                if items != n:
                    out.append(("WARN", "count", f"「{mm.group(0)}」の直後のリストが{items}項目"))

    if paras:
        last = paras[-1][1]
        if "ぜひ" in split_sentences(last.replace("\n", ""))[-1] and fi >= 0 and "ぜひ" in text[fi:fi + 80]:
            out.append(("WARN", "zehi", f"結びの最後の文に「ぜひ」: {last[-40:]}"))
    bold = len(re.findall(r"\*\*.+?\*\*", body))
    if bold > 3 * max(1, len(h2s)):
        out.append(("WARN", "bold", f"太字{bold}か所(h2 {len(h2s)}個。目安は1見出しあたり1〜2か所)"))
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv
    errors_only = "--errors-only" in sys.argv
    summary = "--summary" in sys.argv
    ch = _channel.load()
    arts = ch.path("articles")
    if "--all" in sys.argv:
        files = sorted((p for p in arts.glob("*.md") if p.name.split("_")[0].isdigit()),
                       key=lambda p: int(p.name.split("_")[0]))
    else:
        files = [f for a in args for f in find_articles(a, ch)]
    if not files:
        sys.exit("対象の記事が見つからない。使い方: lint_article.py <番号>... | --all")
    n_err = n_warn = n_bad = 0
    kinds = collections.Counter()
    for f in files:
        issues = lint(f, ch)
        if errors_only:
            issues = [i for i in issues if i[0] == "ERROR"]
        if not issues:
            continue
        n_bad += 1
        if not summary:
            f = f.resolve()
            print(f"\n{f.relative_to(_channel.ROOT) if f.is_relative_to(_channel.ROOT) else f}")
        for level, kind, msg in issues:
            if not summary:
                print(f"  {level:5} {kind:13} {msg}")
            kinds[(level, kind)] += 1
            n_err += level == "ERROR"
            n_warn += level == "WARN"
    if summary:
        for (level, kind), c in sorted(kinds.items()):
            print(f"  {level:5} {kind:13} {c}")
    print(f"\n{len(files)}本中 {n_bad}本に指摘 (ERROR {n_err} / WARN {n_warn})")
    return 1 if n_err or (strict and n_warn) else 0


if __name__ == "__main__":
    sys.exit(main())
