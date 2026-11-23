#!/usr/bin/env python3
"""
note.com 非公式APIラッパー。

note.comには公式の記事投稿APIが存在しない。このモジュールは、ブラウザの
エディタが実際に叩いているのと同じ内部APIを、ログイン済みCookieを使って
直接呼び出すことで下書き作成を自動化する。

前提:
- .secrets/note.cookie に、ブラウザDevTools > Network > (draft_saveなどの)
  リクエストを「Copy as cURL」した際の Cookie ヘッダの値(生文字列)を
  保存しておくこと。 .gitignore で除外済み。
- 認証の要は Cookie 内の note_gql_auth_token (JWT) で、有効期限は約30分と短い。
  失効すると draft_save などは **HTTP 201を返しつつレスポンス本文にerrorが入る**
  という紛らわしい壊れ方をするため、このモジュールの関数はレスポンス本文を
  必ずチェックし、失効時は NoteAuthError を投げる。
"""
import json
import subprocess
import urllib.parse
import uuid
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import channel as _channel

# パスはチャンネル設定(channels/{NOTE_CHANNEL}/channel.json)から取る。既定は sample。
CHANNEL = _channel.load()
ROOT = _channel.ROOT
COOKIE_PATH = CHANNEL.path("cookie")
ARTICLES_DIR = CHANNEL.path("articles")
META_DIR = CHANNEL.path("meta")

COMMON_HEADERS = [
    "-H", "accept: */*",
    "-H", "origin: https://editor.note.com",
    "-H", "referer: https://editor.note.com/",
    "-H", "x-requested-with: XMLHttpRequest",
    "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
]


class NoteAuthError(Exception):
    """Cookie失効などの認証エラー"""


def load_cookie() -> str:
    if not COOKIE_PATH.exists():
        sys.exit(
            f"Cookieファイルが見つかりません: {COOKIE_PATH}\n"
            "SKILL.mdの手順に従って、ブラウザからCookieをキャプチャしてください。"
        )
    cookie = COOKIE_PATH.read_text().strip()
    if not cookie:
        sys.exit(f"Cookieファイルが空です: {COOKIE_PATH}")
    return cookie


def save_cookie(raw_cookie_header: str) -> None:
    """cURLの -b '...' から抜き出したCookie文字列をそのまま保存する"""
    COOKIE_PATH.parent.mkdir(exist_ok=True)
    COOKIE_PATH.write_text(raw_cookie_header.strip() + "\n")


def _curl_json(cmd: list[str]) -> dict:
    """
    重要: curlは -b の値を必ずコマンドライン引数(変数展開)として渡すこと。
    `-b @file` のようなファイル参照構文は、curlがNetscape cookie-jar形式だと
    誤解釈してCookieが一切送られない(=常にnot_loginになる)バグを踏んだ実績あり。
    """
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"JSONとして解釈できないレスポンス: {result.stdout[:500]}")
    if isinstance(data, dict) and "error" in data:
        raise NoteAuthError(
            f"note APIがエラーを返しました: {data['error']}\n"
            "note_gql_auth_token が失効している可能性が高いです。Cookieを再キャプチャしてください。"
        )
    return data


def check_cookie_valid(cookie: str) -> bool:
    """本格的な処理(画像アップロード等)を始める前に、Cookieがまだ生きているか軽量チェックする"""
    cmd = ["curl", "-s", "-b", cookie, *COMMON_HEADERS, "https://note.com/api/v3/users/user_features"]
    try:
        _curl_json(cmd)
        return True
    except (NoteAuthError, RuntimeError):
        return False


def note_meta_path(video_id: str) -> pathlib.Path:
    """video_id ↔ 下書きの紐づけ(articles/meta/{video_id}.note.json)。
    ハイフン始まりのIDでもディレクトリ配下なのでオプション誤認が起きない。"""
    return META_DIR / f"{video_id}.note.json"


def article_path(video_id: str) -> pathlib.Path:
    """記事mdのパス。meta/{video_id}.note.json の channel_no から articles/{番号}_*.md を探す。
    動画ID名のmdも残っていれば(旧形式)そちらを使う。"""
    legacy = ARTICLES_DIR / f"{video_id}.md"
    if legacy.exists():
        return legacy
    meta = load_note_meta(video_id)
    if meta and meta.get("channel_no") is not None:
        hits = sorted(ARTICLES_DIR.glob(f"{int(meta['channel_no']):02d}_*.md"))
        if len(hits) == 1:
            return hits[0]
    raise FileNotFoundError(f"{video_id} の記事mdが見つからない")


def save_note_meta(
    video_id: str,
    note_id: str,
    note_key: str,
    image_urls: dict,
    channel_no: int | None = None,
    channel_url: str | None = None,
    channel_title: str | None = None,
    **extra,
) -> None:
    """
    どのvideo_idがnote.comのどの下書き(note_id/note_key)に紐づいているか、
    どの画像ファイルが既にどのURLにアップロード済みかを記録する。
    これが無いと、後から記事を更新するたびに新しい下書きを作ってしまったり、
    画像を毎回アップロードし直すことになる(note_critiqueスキルが更新時に使う)。

    channel_no/channel_url/channel_titleは、プロジェクト直下の`channel_url.md`
    (チャンネル内の全動画一覧)における対象動画の行番号・URL・タイトル。
    channel_url.mdのどの行が既に記事化済みかを後から追える(既存のmetaを
    上書きする際は、既にある値を保持したいときは呼び出し側でload_note_metaの
    値を引き継ぐこと)。

    extra には pushed_sha(最後に下書きへ送った記事mdのハッシュ)など、パイプラインの記録を入れる。
    既存の meta にある extra 系のキーは、渡されなければそのまま残す。
    """
    path = note_meta_path(video_id)
    path.parent.mkdir(exist_ok=True)
    old = load_note_meta(video_id) or {}
    base = {"note_id", "note_key", "image_urls", "channel_no", "channel_url", "channel_title"}
    data = {k: v for k, v in old.items() if k not in base}
    data.update({"note_id": note_id, "note_key": note_key, "image_urls": image_urls})
    if channel_no is not None:
        data["channel_no"] = channel_no
    if channel_url is not None:
        data["channel_url"] = channel_url
    if channel_title is not None:
        data["channel_title"] = channel_title
    data.update(extra)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def load_note_meta(video_id: str) -> dict | None:
    path = note_meta_path(video_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def get_note(cookie: str, note_key: str) -> dict:
    """下書き・予約・公開の状態と本文を読む(読み取りのみ)。is_reserved / is_published / name / body など"""
    cmd = ["curl", "-s", "-b", cookie, *COMMON_HEADERS, f"https://note.com/api/v3/notes/{note_key}"]
    return _curl_json(cmd)["data"]


def create_note(cookie: str) -> tuple[str, str]:
    """新規の空下書きを作成し、(id, key) を返す。keyは編集画面URLのnote_key部分。"""
    cmd = [
        "curl", "-s", "-b", cookie,
        "-H", "content-type: application/json",
        *COMMON_HEADERS,
        "--data-raw", '{"template_key":null}',
        "https://note.com/api/v1/text_notes",
    ]
    data = _curl_json(cmd)["data"]
    return str(data["id"]), data["key"]


def upload_image(cookie: str, image_path: pathlib.Path) -> str:
    """presigned_post取得 -> S3へ直接アップロード -> 完成後の画像URL(assets.st-note.com)を返す"""
    presign_cmd = [
        "curl", "-s", "-b", cookie,
        *COMMON_HEADERS,
        "-F", f"filename={image_path.name}",
        "https://note.com/api/v3/images/upload/presigned_post",
    ]
    presigned = _curl_json(presign_cmd)["data"]

    action_url = presigned["action"]
    final_url = presigned["url"]
    post_fields = presigned["post"]

    # S3のpresigned POSTは fields の後に file が来る必要がある(フィールド順を保つ)
    s3_cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}"]
    for key, value in post_fields.items():
        s3_cmd += ["-F", f"{key}={value}"]
    s3_cmd += ["-F", f"file=@{image_path}", action_url]

    result = subprocess.run(s3_cmd, capture_output=True, text=True, check=True)
    status = result.stdout.strip()
    if not status.startswith("2"):
        raise RuntimeError(f"S3アップロード失敗 ({image_path.name}): status={status}")

    return final_url


def set_eyecatch(cookie: str, note_id: str, image_path: pathlib.Path) -> str:
    """
    見出し画像(記事一覧・SNSシェア時のサムネイル。本文中の画像とは別枠)を設定する。

    note.comは1280:670の比率の画像しか受け付けない(実測済み: 比率が違うと
    {"error":{"code":"invalid","message":"見出し画像は1280:670の縦横比の画像を
    設定してください"}}が返る)。動画のスクリーンショット(16:9等)はそのままでは
    通らないため、macOSの`sips`コマンドで中央クロップ+リサイズしてから
    `https://note.com/api/v1/image_upload/note_eyecatch`にマルチパートで
    直接アップロードする(本文画像のような presigned_post 経由のS3アップロードでは
    ないので注意)。
    """
    import tempfile

    probe = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(image_path)],
        capture_output=True, text=True, check=True,
    )
    dims = {}
    for line in probe.stdout.splitlines():
        line = line.strip()
        if line.startswith("pixelWidth:"):
            dims["w"] = int(line.split(":")[1])
        elif line.startswith("pixelHeight:"):
            dims["h"] = int(line.split(":")[1])

    target_ratio = 1280 / 670
    w, h = dims["w"], dims["h"]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        cropped = tmpdir / "cropped.jpg"
        final = tmpdir / "eyecatch.jpg"

        if w / h > target_ratio:
            new_w = round(h * target_ratio)
            subprocess.run(
                ["sips", "-c", str(h), str(new_w), str(image_path), "--out", str(cropped)],
                capture_output=True, check=True,
            )
        else:
            new_h = round(w / target_ratio)
            subprocess.run(
                ["sips", "-c", str(new_h), str(w), str(image_path), "--out", str(cropped)],
                capture_output=True, check=True,
            )
        subprocess.run(
            ["sips", "-z", "670", "1280", str(cropped), "--out", str(final)],
            capture_output=True, check=True,
        )

        cmd = [
            "curl", "-s", "-b", cookie,
            *COMMON_HEADERS,
            "-F", f"note_id={note_id}",
            "-F", f"file=@{final};type=image/jpeg",
            "https://note.com/api/v1/image_upload/note_eyecatch",
        ]
        return _curl_json(cmd)["data"]["url"]


def save_draft(cookie: str, note_id: str, title: str, body_html: str) -> dict:
    """本文HTMLを下書きに保存する(is_temp_saved=trueだが、noteの通常の自動保存と同じ扱い)"""
    payload = {
        "body": body_html,
        "body_length": len(body_html),
        "name": title,
        "index": False,
        "is_lead_form": False,
    }
    payload_path = ROOT / ".secrets" / "_payload_tmp.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False))
    try:
        cmd = [
            "curl", "-s",
            "--url", f"https://note.com/api/v1/text_notes/draft_save?id={note_id}&is_temp_saved=true",
            "-H", "content-type: application/json",
            "-b", cookie,
            *COMMON_HEADERS,
            "--data-binary", f"@{payload_path}",
        ]
        return _curl_json(cmd)
    finally:
        payload_path.unlink(missing_ok=True)


# ---- 本文HTML組み立てヘルパー ----
# noteのエディタが生成するHTMLと同じタグ構造。各ブロックにUUIDのname/id属性が必要。

def _uid() -> str:
    return str(uuid.uuid4())


def p(text: str) -> str:
    i = _uid()
    return f'<p name="{i}" id="{i}">{text}</p>'


def h2(text: str) -> str:
    i = _uid()
    return f'<h2 name="{i}" id="{i}">{text}</h2>'


def h3(text: str) -> str:
    i = _uid()
    return f'<h3 name="{i}" id="{i}">{text}</h3>'


def b(text: str) -> str:
    """太字。p()に渡す文字列の一部として埋め込んで使う(例: p(f"通常は{b('太字')}です"))"""
    return f'<strong>{text}</strong>'


def toc() -> str:
    """
    目次のネイティブブロック。中身は空(<br>のみ)で、note.com側が本文中の見出し(h2/h3)
    から自動生成して表示する。実測済み: <table-of-contents name="{uuid}" id="{uuid}"><br></table-of-contents>
    """
    i = _uid()
    return f'<table-of-contents name="{i}" id="{i}"><br></table-of-contents>'


def ul(items: list[str]) -> str:
    i = _uid()
    lis = "".join(f"<li>{p(item)}</li>" for item in items)
    return f'<ul name="{i}" id="{i}">{lis}</ul>'


def ol(items: list[str]) -> str:
    i = _uid()
    lis = "".join(f"<li>{p(item)}</li>" for item in items)
    return f'<ol data-start="1" name="{i}" id="{i}">{lis}</ol>'


def quote(text: str, caption: str = "") -> str:
    """引用ブロック。captionは出典表記(省略可)"""
    i = _uid()
    return (
        f'<figure name="{i}" id="{i}"><blockquote>{p(text)}</blockquote>'
        f'<figcaption>{caption}<br></figcaption></figure>'
    )


def figure(url: str, width: int = 620, height: int = 349) -> str:
    i = _uid()
    return (
        f'<figure name="{i}" id="{i}">'
        f'<img src="{url}" alt="" width="{width}" height="{height}" contenteditable="false" draggable="false">'
        f'<figcaption></figcaption></figure>'
    )


def a(text: str, url: str) -> str:
    """
    インラインのテキストリンク。p()に渡す文字列の一部として埋め込んで使う
    (例: p(f'{a("Instagram", url)}では毎日...')) 。カード埋め込みにしたくない
    (文中の一部だけをリンクにしたい)場合はこちらを使う。
    """
    return f'<a href="{url}" target="_blank" rel="noopener">{text}</a>'


_YOUTUBE_HOSTS = ("youtube.com", "youtu.be")


def link_card(cookie: str, note_key: str, url: str) -> str:
    """
    URLをブロック単位の埋め込みにする。

    note.comエディタでURLを貼るとき、実際は `draft_save` とは別に
    `GET /api/v2/embed_by_external_api?url=...&service=...&embeddable_key={note_key}` が
    呼ばれ、{"data": {"key": "...", "html_for_embed": "..."}} を返す。この key が
    本文HTML側の embedded-content-key、html_for_embed が <figure>の中身になる
    (実測済み)。note_keyはcreate_note()の戻り値の2番目(下書き編集URLのnote_key部分)。

    YouTubeのURL(youtube.com / youtu.be)は自動的に service=youtube を使い、
    OGPカードではなく実際に再生できる動画プレーヤー(iframe)を埋め込む
    (service=external-articleのままだとタイトル・サムネイルだけのカードになり、
    再生はできない。実測済み)。それ以外のURLは service=external-article を使う。
    """
    host = urllib.parse.urlparse(url).netloc.lower()
    service = "youtube" if any(h in host for h in _YOUTUBE_HOSTS) else "external-article"
    encoded = urllib.parse.quote(url, safe="")
    endpoint = (
        f"https://note.com/api/v2/embed_by_external_api?url={encoded}"
        f"&service={service}&embeddable_key={note_key}&embeddable_type=Note"
    )
    cmd = ["curl", "-s", "-b", cookie, *COMMON_HEADERS, endpoint]
    data = _curl_json(cmd)["data"]
    i = _uid()
    return (
        f'<figure name="{i}" id="{i}" data-src="{url}" data-identifier="null" '
        f'embedded-service="{service}" embedded-content-key="{data["key"]}">'
        f'{data["html_for_embed"]}</figure>'
    )
