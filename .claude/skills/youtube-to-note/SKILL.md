---
name: youtube-to-note
description: YouTube動画1本からnote.comの下書き記事(本文+画像)を作る。字幕・概要欄の取得(yt-dlp)、スクリーンショットの抽出(FFmpeg)、記事本文の執筆、note.comの非公式APIでの下書き作成・画像アップロードまで。「この動画からnote書いて」「〜の動画をnoteの下書きにして」「note用に記事化して」など、動画1本を記事・下書きにするところまでの依頼で使う。予約まで進める・複数本をまとめて処理する・続きから再開する依頼は note-pipeline スキルを使う。
---

# YouTube → note 下書き(1本)

統括スキル `note-pipeline` の工程1〜7(取得から下書き反映まで)を、動画1本について行う入口。
**手順とルールの本文は `note-pipeline` 側にある。** ここに独自のルールを書き足さない(以前はルールが3か所に分かれて食い違った)。

1. `.claude/skills/note-pipeline/SKILL.md` を読み、§0(チャンネル)・§1(対象)・§2(状態)のとおりに進める
2. 工程1〜6(fetch → title → write → lint → critique → eye)を行う。読むもの:
   - `.claude/skills/note-pipeline/references/writing_rules.md`
   - チャンネルの `channels/{名前}/voice.md`・`glossary.md`・`footer.md`
   - スクショ: `references/eye_check.md`、添削: `references/critique.md`、ファクトチェック: `references/fact_check.md`
3. 工程7: `python3 scripts/note_push.py <番号>` で下書きを作る
4. 予約を頼まれていなければここで止め、下書きURL(`https://editor.note.com/notes/{note_key}/edit/`)と、
   human_review があればその内容を報告する。公開ボタンは押さない

note.com の仕組み・HTML・落とし穴は `references/note_html.md`。
