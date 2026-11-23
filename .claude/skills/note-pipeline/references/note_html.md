# note.com の下書き・予約の仕組みと落とし穴

note.com に公式の投稿 API は無い。ブラウザのエディタが使う内部 API を、ログイン済み Cookie で呼んでいる
(`scripts/note_api.py`)。ふだんは `note_push.py`(下書き)と `note_schedule.py`(予約)を使えばよく、
HTML を手で組み立てる必要は無い。ここは、スクリプトを直すときや想定外の挙動に当たったときに読む。

## md → HTML の対応(note_push.py の build_body)

| md | note.com |
|---|---|
| `# 題名`(1行目) | 下書きの題名 |
| `## 目次` + 箇条書き | `toc()`(ネイティブの目次ブロック。箇条書きは捨て、本文の h2/h3 から自動生成される) |
| `## ` / `### ` | h2 / h3 |
| `![alt](images/{フォルダ}/NN_x.jpg)` | 画像(meta の image_urls にあれば使い回し、無ければアップロード) |
| `- ` / `1. ` | ul / ol |
| `> ` | 引用 |
| `**太字**` | `<strong>` |
| 空行で区切らない改行 | **別の段落になる**(1行=1段落として扱う) |
| フッターの指定の段落 | チャンネル設定の footer.links でインラインリンク化。video_embed_after の段落の直後に YouTube プレーヤーを埋め込む |

使えるタグは実測した構造だけ(`note_api.py` の `p h2 h3 b a ul ol toc quote figure link_card`)。
当てずっぽうで新しいタグを足さない(埋め込みは見た目以上に複雑な内部状態を持つ)。

リンクの使い分け: 文中の一部をリンクにするときは `a()`(SNS など)、
独立した告知文の直後に置く動画や出典は `link_card()`(YouTube は再生できるプレーヤーになる)。

## 状態と安全装置

| 状態 | 確かめ方 | 書き込み |
|---|---|---|
| 下書き | GET `/api/v3/notes/{key}` の is_reserved・is_published が false | `note_push.py` で更新してよい |
| 予約済み | is_reserved が true | **draft_save しても予約本文は変わらない**(題名も旧いまま)。`note_push.py` は止まる。直す必要が出たら human_review |
| 公開済み | is_published が true | 本文を書き換えない |

- 即時公開する関数は作っていない。予約は `note_schedule.py <番号> --commit` だけで、送ったあと GET して予約日時を確かめる
- 予約の題名は管理表の「note記事の名前」列
- `draft_save` などは、認証が切れても **HTTP 201 を返しつつ本文に error が入る**。`note_api._curl_json` が本文を見て `NoteAuthError` を投げる
- curl に Cookie を渡すときは `-b "$COOKIE"`(値そのもの)。`-b @file` は cookie-jar 形式と解釈されて何も送られない
- 別のアカウントで作った下書きは「他のユーザーの下書きは編集できません」になる。作り直すかは human_review で確認してから
- 編集画面をブラウザで開いたまま API で書くと、エディタの自動保存に上書きされることがある
- 見出し画像は 1280:670 の比率しか受け付けない。`set_eyecatch()` が中央クロップする
- 動作確認などで作った空の下書きが残ったら、消すかどうかユーザーに確認する(API で消さない)

## Cookie

`.secrets/` 以下(チャンネル設定の paths.cookie)に置く。中身をログ・報告・スキルに書かない。
`NoteAuthError` が出たときだけ、ユーザーに取り直しを頼む(手順: note.com のエディタを開く → DevTools の Network →
本文に1文字打って自動保存 → `draft_save` を Copy as cURL → 貼ってもらい、`-b '...'` の中身を `note_api.save_cookie()` で保存)。
エラーが出ていないときは Cookie の有効期限の話をしない。
