#!/bin/bash
# 使い方: sheet.sh <video_id> <out.jpg> <開始秒> <刻み秒> <枚数> [列数]  -> 時刻付き(ファイル名順)の一覧シート
V=$(ls "$(python3 "$(dirname "$0")/channel.py" path videos)"/$1.*|head -1); OUT=$2; S=$3; STEP=$4; N=$5; COLS=${6:-4}
TMP=$(mktemp -d)
for ((k=0;k<N;k++)); do t=$(echo "$S+$k*$STEP"|bc -l); f=$(printf "$TMP/%03d.jpg" $k)
 ffmpeg -loglevel error -y -ss $t -i "$V" -frames:v 1 -vf "scale=480:-1,drawtext=text='$t':fontcolor=yellow:fontsize=28:box=1:boxcolor=black@0.6:x=5:y=5" $f 2>/dev/null || ffmpeg -loglevel error -y -ss $t -i "$V" -frames:v 1 -vf "scale=480:-1" $f; done
ROWS=$(( (N+COLS-1)/COLS ))
ffmpeg -loglevel error -y -pattern_type glob -i "$TMP/*.jpg" -vf "tile=${COLS}x${ROWS}" "$OUT"; rm -rf $TMP
