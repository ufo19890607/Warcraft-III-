#!/bin/bash
# Reforged -> 1.27 转换流水线 (devcloud 版)
# 用法: ./reforged-to-127.sh <reforged.w3x> <output.w3x>

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: $0 <reforged.w3x> <output.w3x>"
    exit 64
fi

REFORGED_W3X="$(realpath "$1")"
OUTPUT_W3X="$(realpath -m "$2")"
SCRIPT_DIR="/data/ufo/Warcraft-III-/wc3-build"
HEADER_BIN="$SCRIPT_DIR/hm3w_header.bin"

if [ ! -f "$HEADER_BIN" ]; then
    echo "ERROR: 1.27 标准 header 缺失: $HEADER_BIN"
    exit 1
fi

TMP_DIR="$(mktemp -d -t reforged-to-127.XXXXXX)"
trap "rm -rf '$TMP_DIR'" EXIT
echo "[1/5] 工作目录: $TMP_DIR"

echo "[2/5] 解包 reforged .w3x..."
mkdir -p "$TMP_DIR/extracted"
"$SCRIPT_DIR/stormtool" extract "$REFORGED_W3X" "$TMP_DIR/extracted"

echo "[3/5] 降级数据文件..."
EX="$TMP_DIR/extracted"
[ -f "$EX/war3map.doo" ] && python3 "$SCRIPT_DIR/scripts/doo_downgrade.py" "$EX/war3map.doo" "$EX/war3map.doo.tmp" && mv "$EX/war3map.doo.tmp" "$EX/war3map.doo"
[ -f "$EX/war3mapUnits.doo" ] && python3 "$SCRIPT_DIR/scripts/units_doo_downgrade.py" "$EX/war3mapUnits.doo" "$EX/war3mapUnits.doo.tmp" && mv "$EX/war3mapUnits.doo.tmp" "$EX/war3mapUnits.doo"
[ -f "$EX/war3map.w3i" ] && python3 "$SCRIPT_DIR/scripts/w3i_downgrade.py" "$EX/war3map.w3i" "$EX/war3map.w3i.tmp" && mv "$EX/war3map.w3i.tmp" "$EX/war3map.w3i"

echo "[4/5] (跳过 .j 注入)"
echo "[5/5] 用 1.27 header 重打包..."
"$SCRIPT_DIR/repack" "$EX" "$HEADER_BIN" "$OUTPUT_W3X"

echo
echo "✓ 完成: $OUTPUT_W3X"
ls -la "$OUTPUT_W3X"
