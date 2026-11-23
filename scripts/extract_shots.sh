#!/bin/bash
# 使い方: extract_shots.sh <video_id> <画像フォルダ名 または 絶対パス> <秒> <ファイル名> [<秒> <ファイル名>...]  記事用スクショを抽出
# フォルダ名ならチャンネル設定の images の下、/ で始まる絶対パスならそこに書き出す。確認シートは CHECK_DIR(既定 $TMPDIR)に出す
cd "$(dirname "$0")/.."
V=$(ls "$(python3 scripts/channel.py path videos)"/$1.*|head -1)
case "$2" in /*) D="$2" ;; *) D="$(python3 scripts/channel.py path images)/$2" ;; esac
mkdir -p "$D"; shift 2
while [ $# -gt 0 ]; do ffmpeg -loglevel error -y -ss $1 -i "$V" -frames:v 1 -q:v 2 "$D/$2.jpg"; shift 2; done
OUT="${CHECK_DIR:-${TMPDIR:-/tmp}}/check_$(basename "$D").jpg"
ffmpeg -loglevel error -y -pattern_type glob -i "$D/0[1-9]*.jpg" -vf "scale=480:-1,tile=4x3" "$OUT"
echo "$OUT"
