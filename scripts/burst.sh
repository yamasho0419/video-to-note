#!/bin/bash
# 使い方: burst.sh <video_id> <out.jpg> <中心秒>... : 各中心の+0,0.3,0.6,0.9秒を行にした確認シート(目の開き確認用)
V=$(ls "$(python3 "$(dirname "$0")/channel.py" path videos)"/$1.*|head -1); OUT=$2; shift 2; TMP=$(mktemp -d); n=0
for c in "$@"; do for o in 0 0.3 0.6 0.9; do t=$(echo "$c+$o"|bc -l); ffmpeg -loglevel error -y -ss $t -i "$V" -frames:v 1 -vf scale=480:-1 $(printf "$TMP/%03d.jpg" $n); n=$((n+1)); done; done
ffmpeg -loglevel error -y -pattern_type glob -i "$TMP/*.jpg" -vf "tile=4x$#" "$OUT"; rm -rf $TMP
