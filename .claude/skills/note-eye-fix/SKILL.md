---
name: note-eye-fix
description: note.comの下書きURL(editor.note.com/notes/{note_key}/edit)や記事番号を受け取り、記事のスクリーンショットを全枚Readで目視確認して、人物の目が半開き・瞬きの途中の画像を元動画の前後フレームから目の開いた画像に差し替え、ローカルとnote.comの下書きの両方に反映する。「目が半開きの画像を直して」「写真の目を確認して」「スクショの表情チェックして」「下書きの画像を差し替えて」「この下書きの目チェックして」など、記事画像の表情・目の開きの確認や撮り直しの依頼で使う。
---

# 記事画像の目チェック・差し替え

統括スキル `note-pipeline` の工程6(目チェック)と工程7(下書き反映)を、記事1本について行う入口。
**判定基準と手順の本文は `.claude/skills/note-pipeline/references/eye_check.md`。** ここに書き足さない。

1. 記事を特定する。下書きURLなら `grep -l '"note_key": "{note_key}"' articles/meta/*.note.json` で video_id を引き、
   `channel_no` から記事md と画像フォルダを決める。**一致する meta が無ければ推測せず確かめる**(別の記事を差し替える事故を防ぐ)
2. `python3 scripts/pipeline_status.py <番号> --remote` で状態を見る。予約済み・公開済みなら、
   差し替えはローカルにとどめ、note.com に反映できないことを報告する
3. `eye_check.md` §2〜§3 で全画像を Read で見て、対象を一覧にしてから差し替える
4. `python3 scripts/note_push.py <番号> --reupload=<差し替えた画像名,...>` で下書きに反映する(見出し画像なら `--eyecatch` も)
5. 確認した枚数・半開きだった枚数・差し替えた画像(元の時刻→新しい時刻)・差し替えられなかった画像と理由・下書きURLを報告する。
   `critiques/{video_id}.md` の状態ブロックに `eye_checked` を書く。公開ボタンは押さない

確認していない画像を「問題なし」と報告しない。
