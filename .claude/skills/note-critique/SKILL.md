---
name: note-critique
description: 作成済みのnote記事(articles/{番号}_{短縮タイトル}.md と画像)を執筆ルールに沿って添削し、別エージェントのファクトチェックを通して、修正版をローカルとnote.comの下書きの両方に反映する。本文だけでなく画像の内容・配置も見て、引用+修正例つきで添削記録(critiques/{video_id}.md)を残す。「この記事添削して」「さっきの記事見てほしい」「読みにくくない?」「投稿前にチェックして」「この下書き大丈夫か見て」「添削してnoteに反映して」など、既存記事の添削・修正反映の依頼で使う。
---

# note 記事の添削・反映

統括スキル `note-pipeline` の工程4〜7(lint → 添削+ファクトチェック → 目チェック → 下書き反映)を、既存の記事1本について行う入口。
**手順とルールの本文は `note-pipeline` 側にある。** ここで独自の執筆ルールを作らない。

1. 対象を決める。番号・URL・video_id・記事パスのどれかで渡される。
   video_id から記事を引くときは `articles/meta/{video_id}.note.json` の `channel_no`。
   示されていなければ直前の会話や、更新日時が新しい記事から推測し、違っていたら確かめる
2. `python3 scripts/pipeline_status.py <番号> --remote` で状態を見る。**予約済み・公開済みなら本文を書き換えない**
   (予約本文は draft_save で変わらない)。直す必要があれば、何をどう直したいかをユーザーに伝えて判断を仰ぐ
3. `.claude/skills/note-pipeline/references/critique.md` の手順で添削し、`fact_check.md` で別エージェントに事実確認を頼む。
   基準は `references/writing_rules.md` とチャンネルの `voice.md`
4. 画像は全部 Read で見る。目チェックは `references/eye_check.md`
5. `python3 scripts/note_push.py <番号>` で下書きに反映する(止まったら、その理由をユーザーに伝える)
6. 添削結果の要点、ファクトチェックの指摘と反映したかどうか(反映しなかった理由)、下書きURLを報告する。公開ボタンは押さない

既存記事のフッター・CTA の扱い(古い形式をどこまで直すか)はチャンネルの `voice.md` の「既存記事の扱い」に従う。
