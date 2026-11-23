#!/bin/bash
# 使い方: prep_video.sh <番号> <短縮名> -> 字幕/動画/サムネ取得+文字起こしmd生成
# 置き場所はチャンネル設定(NOTE_CHANNEL、既定 sample)に従う
set -e
cd "$(dirname "$0")/.."
P() { python3 scripts/channel.py path "$1"; }
TABLE=$(P table); TR=$(P transcripts); VD=$(P videos); IMG=$(P images)
NO=$1; SHORT=$2
ROW=$(grep -E "^\| $NO \|" "$TABLE")
URL=$(echo "$ROW" | awk -F'|' '{gsub(/ /,"",$3);print $3}')
TITLE=$(echo "$ROW" | awk -F'|' '{sub(/^ +/,"",$4);sub(/ +$/,"",$4);print $4}')
VID=$(echo "$URL" | sed 's/.*v=//')
NAME=$(printf "%02d" $NO)_$SHORT
mkdir -p "$TR" "$VD"
yt-dlp -q --skip-download --write-auto-sub --ignore-errors --sub-lang ja --sub-format vtt -o "$TR/%(id)s.%(ext)s" "$URL"
yt-dlp -q --skip-download --print "%(description)s" "$URL" > "${SCRATCH:-/tmp}/desc_$VID.txt" 2>/dev/null || true
yt-dlp -q -f "bv*[height<=1080]+ba/b[height<=1080]" -o "$VD/%(id)s.%(ext)s" "$URL"
mkdir -p "$IMG/$NAME"
yt-dlp -q --skip-download --write-thumbnail -o "$IMG/$NAME/00_thumbnail" "$URL"
sips -s format jpeg "$IMG/$NAME/00_thumbnail.webp" --out "$IMG/$NAME/00_thumbnail.jpg" >/dev/null && rm "$IMG/$NAME/00_thumbnail.webp"
if [ -f "$TR/$VID.ja.vtt" ]; then
  python3 scripts/vtt_to_md.py "$VID" "$NAME" "$TITLE" "$URL"
else
  # 字幕なし→音声から文字起こし(WHISPER_PY=mlx-whisperの入ったpython)
  "${WHISPER_PY:?字幕なし: WHISPER_PYを指定}" scripts/whisper_to_md.py "$VID" "$NAME" "$TITLE" "$URL"
fi
echo "VID=$VID NAME=$NAME"
