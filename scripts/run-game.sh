#!/usr/bin/env bash
# 启动 Azur Promilia（Proton 封装）。需要先 `apfix apply`。
#
#   ./scripts/run-game.sh [--game-dir DIR] [-- extra proton args]
#
# 默认游戏目录：$AZUR_GAME_DIR，否则脚本上一级目录里的 AzurPromilia_Game。
set -euo pipefail

game_dir="${AZUR_GAME_DIR:-}"
extra=()

while [ $# -gt 0 ]; do
  case "$1" in
    --game-dir) game_dir="${2:?--game-dir needs a value}"; shift 2 ;;
    --game-dir=*) game_dir="${1#*=}"; shift ;;
    --) shift; extra=("$@"); break ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) extra+=("$1"); shift ;;
  esac
done

if [ -z "$game_dir" ]; then
  here="$(cd "$(dirname "$0")" && pwd)"
  for cand in "$here/AzurPromilia_Game" "$here/../AzurPromilia_Game"; do
    if [ -d "$cand" ]; then game_dir="$cand"; break; fi
  done
fi

if [ -z "$game_dir" ] || [ ! -d "$game_dir" ]; then
  echo "找不到游戏目录，用 --game-dir 指定" >&2
  exit 1
fi

exe="$game_dir/AzurPromilia.exe"
dll="$game_dir/AzurPromilia_Data/Plugins/mj_sdk/union_pcsdk.dll"

[ -f "$exe" ] || { echo "缺少 $exe" >&2; exit 1; }
[ -f "$dll" ] || { echo "缺少 $dll" >&2; exit 1; }

# 补丁自检交给 apfix（签名定位，不认偏移）。没有装 apfix 就跳过，只提示。
if command -v apfix >/dev/null; then
  if ! apfix status --game-dir "$game_dir" --quiet 2>/dev/null; then
    echo "警告：补丁未全部生效，先跑 'apfix apply --game-dir \"$game_dir\"'" >&2
  fi
fi

command -v dwproton >/dev/null || { echo "找不到 dwproton（Proton 封装脚本）" >&2; exit 1; }

cd "$game_dir"
# dwproton 在参数 ≥2 个时不会自动补 verb，必须显式写 waitforexitandrun
exec dwproton waitforexitandrun ./AzurPromilia.exe -start=azurpromilia_launcher "${extra[@]+"${extra[@]}"}"
