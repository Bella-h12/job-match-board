#!/bin/bash
# 一条命令把某个工作区从打分跑到看板：bash scripts/build.sh workspace/<名字>
set -e
WS="$1"; [ -d "$WS" ] || { echo "用法：bash scripts/build.sh workspace/<名字>"; exit 1; }
D="$(cd "$(dirname "$0")" && pwd)"
python3 "$D/run.py" "$WS"
python3 "$D/enrich.py" "$WS"                 # 没 key 会自动跳过
python3 "$D/board/make_board_json.py" "$WS"
python3 "$D/board/render.py" "$WS" > /dev/null
python3 "$D/board/assemble.py" "$WS"
echo "→ $WS/board.html"
