# video-to-note

解説系の YouTube 動画を文字起こしして、note.com の記事(本文+画像)にし、下書き保存と予約投稿までを自動化するシステムです。
Claude Code のスキルと Python / シェルスクリプトで構成しています。

- 作業の分担は **AI が9割、人間が1割**。AI は予約投稿の設定まで行い、即時公開はしません
- AI が判断できないこと(字幕の誤変換の疑い、事実の食い違いなど)は「要人間確認」として止め、人が判断してから予約します
- 話者が言っていないことを記事に足さないよう、執筆・添削・ファクトチェックを別々の工程に分けています

> インターン先で運用している仕組みから、汎用部分を切り出して公開しています。そのためコミットは1件です。
> このリポジトリはコードと仕組みだけを置いています。記事・字幕・動画などのデータは含みません。
> `channels/sample/` は設定の書き方を示すための空のサンプルです。

## 解決した課題

動画1本を記事にするには、字幕の取得、文字起こしの整形、スクショ選び、執筆、校正、下書き作成、予約設定と、手作業が多くあります。
本数が増えると、品質のばらつき、途中で止まった作業の把握、同じミスの繰り返しが問題になります。

そこで次のように作りました。

- **工程を8つに分け、各工程の「済み」をファイルから判定する**ので、途中で止まってもどこからでも再開できる
- **過去の添削記録から失敗パターンを抜き出してルール化**し、機械で判定できるものは lint で検出する
- **ファクトチェックは執筆とは別のエージェントに任せ**、書いた本人の思い込みで見落とさないようにする
- **note.com への書き込みは1か所から順番に**行い、二重作成や管理表の書き換えの競合を防ぐ

## 処理の流れ

```text
管理表(Markdown の表)の行            ← 新しい動画は scripts/add_video.py で追加
    ↓
1 fetch    字幕・概要欄・動画・サムネ取得       scripts/prep_video.sh
2 title    題名を5つの観点で作り表に記入       scripts/channel.py set <番号> note記事の名前 "…"
3 write    スクショ選び(目の開き確認)+執筆   scripts/burst.sh / extract_shots.sh
4 lint     機械判定できるルールの検査           scripts/lint_article.py
5 critique 添削+別エージェントのファクトチェック
6 eye      全画像の目チェックと差し替え
    ↓(要人間確認があればここで止まる)
7 push     note.com 下書きの作成・更新          scripts/note_push.py
8 reserve  予約投稿                             scripts/note_schedule.py --commit
```

進み具合は `python3 scripts/pipeline_status.py <番号|範囲|--pending>` で確認できます。

## 構成

```text
.claude/skills/        Claude Code のスキル(工程の進め方とルール)
channels/              チャンネルごとの設定(sample と _template)
scripts/               素材の準備・lint・状態判定・note.com 連携
viewer/                管理表をブラウザで見て操作する Next.js アプリ
```

### Claude Code スキル

| スキル | 役割 |
|---|---|
| `note-pipeline` | 統括。対象の指定(1本/範囲/未処理を全部)、工程1〜8、複数本の並列処理、最後の一覧報告 |
| `youtube-to-note` | 動画1本を下書きまで |
| `note-critique` | 既存記事の添削と下書きへの反映 |
| `note-eye-fix` | 目が半開きの画像の差し替えと反映 |

ルールの本文は `note-pipeline/references/` にまとめ、ほかのスキルはそこを参照します。

| ファイル | 中身 |
|---|---|
| `writing_rules.md` | 執筆ルール。添削記録から抜き出した失敗パターン(事実の扱い・構成・読みやすさ・画像)と題名の付け方 |
| `fact_check.md` | 別エージェントへのファクトチェックの頼み方 |
| `eye_check.md` | スクショの選び方、目の判定基準、差し替え手順 |
| `critique.md` | 添削の手順と記録の書式 |
| `note_html.md` | note.com の下書き・予約の仕組みと落とし穴 |
| `add_channel.md` | 新しいチャンネルを追加する手順 |

### チャンネル設定(channels/)

複数のチャンネルを同じ仕組みで扱えるように、チャンネル固有のことは設定ファイルに分けています。
環境変数 `NOTE_CHANNEL` で切り替えます(既定は `sample`)。

| ファイル | 中身 |
|---|---|
| `channel.json` | 管理表・記事・画像などの置き場所、Cookie の場所、投稿の時間枠、フッターのリンク規則、lint の設定 |
| `voice.md` | 話者・一人称・定型の自己紹介・文体の型・導線の方針 |
| `footer.md` | 記事末尾の固定フッター |
| `glossary.md` | 字幕の誤変換を直すときの正しい表記 |
| `table.md` | 管理表(番号・URL・題名・投稿予定日時・note の URL・下書き・予約投稿完了) |

### スクリプト(scripts/)

| スクリプト | 用途 |
|---|---|
| `prep_video.sh <番号> <短縮名>` | 字幕・概要欄・動画・サムネを取得し、文字起こし md を作る |
| `vtt_to_md.py` / `whisper_to_md.py` | 文字起こしを `[MM:SS]` 行形式に整形(字幕が無い動画は mlx-whisper) |
| `sheet.sh` / `burst.sh` / `extract_shots.sh` | スクショ選び用の一覧シート、目の開き確認シート、画像の書き出し |
| `channel.py` | チャンネル設定と管理表の読み書き(列は見出し名で引く。書く前に退避) |
| `pipeline_status.py` | 番号ごとに工程1〜8のどこまで済んだかを表示 |
| `add_video.py` | 管理表に動画を追加(投稿予定日時は次の空き枠) |
| `lint_article.py` | 機械判定できるルールの検査。ERROR があれば終了コード1 |
| `note_api.py` | note.com の API ラッパー(下書き保存・画像アップロード・状態の取得) |
| `note_push.py` | 下書きの新規作成・更新。予約済み・公開済み・手直しされた下書きには書き込まずに止まる |
| `note_schedule.py` | 予約投稿の設定。既定は dry-run で、`--commit` を付けたときだけ送信し、設定後に日時を検証する |

## 工夫した点

- **安全側に倒す**: 予約投稿の設定は既定で dry-run。公開済み・予約済み・ブラウザで手直しされた下書きは、本文のハッシュで検出して上書きしない
- **認証切れの検出**: note.com の API は認証が切れても HTTP 201 を返し、本文にエラーを入れてくるため、本文を見て例外を投げる
- **管理表の書き換え**: 列の並びに依存せず見出し名で列を引き、書き換えは指定したセルだけ。書く前に退避する
- **ルールの一元化**: 執筆ルールを1か所にまとめ、スキルと lint が同じ番号(F1、S6 など)で参照する

## セットアップ

必要なもの:

- Python 3(標準ライブラリのみ。HTTP 通信は `curl`)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)、[FFmpeg](https://ffmpeg.org/)
- [mlx-whisper](https://github.com/ml-explore/mlx-examples)(字幕のない動画を文字起こしする場合。Apple Silicon)
- Node.js(viewer を使う場合)
- [Claude Code](https://claude.com/claude-code)(スキルを使う場合)

### note.com の認証

note.com には公式の投稿 API がないため、ブラウザのエディタが使う API をログイン済みの Cookie で呼び出しています。

1. ブラウザで note.com にログインし、エディタを開く
2. DevTools > Network で `draft_save` などのリクエストの Cookie ヘッダの値をコピーする
3. `channel.json` の `paths.cookie` の場所(既定は `.secrets/sample.cookie`)に保存する

`.secrets/` は `.gitignore` で除外しています。

### viewer

```bash
cd viewer
npm install
npm run dev   # http://localhost:3000
```

管理表の「下書き」「予約投稿完了」をクリックで切り替えると、Markdown の表に直接書き戻します。
表の場所は環境変数 `TABLE_PATH` で変えられます(既定は `channels/sample/table.md`)。
