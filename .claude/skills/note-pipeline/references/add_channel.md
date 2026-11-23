# 新しいチャンネルを追加する

同じ仕組みで複数のチャンネルを扱える。note のアカウントはチャンネルごとに分けられる。

## 手順

1. 名前を決める(英小文字。例: `tech_talk`)。`channels/_template/` を `channels/{名前}/` にコピーする
2. `channel.json` を埋める
   - paths: 置き場所。`channels/{名前}/` の下にまとめる(table・articles・transcripts・videos・critiques)
   - paths.cookie: `.secrets/{名前}.cookie`(そのチャンネルの note アカウントの Cookie)
   - slots: 投稿の時間枠
   - features: self_intro(定型の自己紹介を使うか)
   - footer: start・markers・links・video_embed_after(footer.md の文面と合わせる)
   - lint: name_typos(話者・固有名詞の誤記)、body_cta(本文中の相談導線を検出する正規表現。不要なら空)
3. `footer.md`・`voice.md`・`glossary.md` を埋める。**分からない項目は推測で埋めず、ユーザーに確認する**
   (話者の肩書き、一人称、自己紹介の固定文、フッターの文面とリンク先)
4. `.gitignore` に `channels/{名前}/videos/` を足す(動画本体はコミットしない)
5. 管理表 `channels/{名前}/table.md` に動画を足す: `NOTE_CHANNEL={名前} python3 scripts/add_video.py <URL>...`
6. 確認: `NOTE_CHANNEL={名前} python3 scripts/pipeline_status.py --pending` で全行が fetch から始まること
7. 最初の1本は、各工程のあとで出来を確かめながら進める(特に voice.md が想定どおりに効いているか)

## 決めておくこと(ユーザーへの質問リスト)

- 記事はどの note アカウントで公開するか(Cookie の取得を誰が行うか)
- 話者は誰で、一人称は何か。定型の自己紹介を入れるか
- フッターに入れる導線(YouTube・SNS・問い合わせ)とリンク先
- 結びの温度感(相談を受け付けているか、情報提供だけか)
- 投稿の時間枠と、1日の本数
