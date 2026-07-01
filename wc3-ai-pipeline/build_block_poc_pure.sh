#!/bin/bash
# build_block_poc_pure.sh - 纯卡位POC出包（只注入body block，不注入其他AI）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STORMTOOL="$SCRIPT_DIR/tools/stormtool"
STORMPATCH="$SCRIPT_DIR/tools/stormpatch"
INJECTOR_BLK="$SCRIPT_DIR/inject_ai_body_block.py"
REPACK="$SCRIPT_DIR/tools/repack"
HEADER_BIN="$SCRIPT_DIR/../base-1.27/base-1.27.w3x"
DOO_DG="$SCRIPT_DIR/tools/doo_downgrade.py"
UNITS_DG="$SCRIPT_DIR/tools/units_doo_downgrade.py"
W3I_DG="$SCRIPT_DIR/tools/w3i_downgrade.py"
W3E_DG="$SCRIPT_DIR/tools/w3e_downgrade.py"
W3OBJ_DG="$SCRIPT_DIR/tools/w3_objdata_downgrade.py"
PJASS="$SCRIPT_DIR/tools/pjass"
COMMON_J="$SCRIPT_DIR/refs/common-127-clean.j"
BLIZZARD_J="$SCRIPT_DIR/refs/Blizzard.j"

if [ $# -lt 2 ]; then
    echo "用法: $0 <input.w3x> <output-prefix>"
    exit 1
fi

INPUT_W3X="$(realpath "$1")"
_BASENAME="$(basename "$2")"
_DIR_REFORGED="$SCRIPT_DIR/../converted-reforged"
_DIR_127="$SCRIPT_DIR/../converted-1.27"
mkdir -p "$_DIR_REFORGED" "$_DIR_127"
OUT_REFORGED="$_DIR_REFORGED/${_BASENAME}-Reforged.w3x"
OUT_127="$_DIR_127/${_BASENAME}-1.27.w3x"

TMP_DIR=$(mktemp -d)

echo "=========================================="
echo " 纯卡位POC出包（仅body block）"
echo "=========================================="
echo "输入: $INPUT_W3X"
echo ""

# [1] 解包
echo "[1/4] 解包 war3map.j + war3map.doo..."
"$STORMTOOL" extract-one "$INPUT_W3X" "war3map.j" "$TMP_DIR/war3map.j" > /dev/null
"$STORMTOOL" extract-one "$INPUT_W3X" "war3map.doo" "$TMP_DIR/war3map.doo" > /dev/null
J="$TMP_DIR/war3map.j"
echo "    $(wc -l < "$J") 行"

# [2] 注入卡位
if grep -q "function Trig_BLK_Tick" "$J"; then
    echo "[2/4] 卡位已存在，跳过"
else
    echo "[2/4] 注入卡位..."
    python3 "$INJECTOR_BLK" "$J"
fi

# [3] pjass
if [ -f "$PJASS" ] && [ -f "$COMMON_J" ] && [ -f "$BLIZZARD_J" ]; then
    echo "[3/4] pjass 语法检查..."
    ERRORS=$("$PJASS" "$COMMON_J" "$BLIZZARD_J" "$J" 2>&1 | grep -c "$(basename "$J"):" || true)
    if [ "$ERRORS" -gt 0 ]; then
        echo "ERROR: $ERRORS 个语法错误:"
        "$PJASS" "$COMMON_J" "$BLIZZARD_J" "$J" 2>&1 | grep "$(basename "$J"):" | head -10
        exit 1
    fi
    echo "    0 errors ✓"
fi

# [4] 打包
echo "[4/4] 打包..."
"$STORMPATCH" "$INPUT_W3X" "$OUT_REFORGED" "war3map.j" "$J" > /dev/null
echo "    Reforged: $OUT_REFORGED ($(du -h "$OUT_REFORGED" | cut -f1))"

# 1.27降级
DG_DIR="$TMP_DIR/downgrade"
mkdir -p "$DG_DIR"
"$STORMTOOL" extract "$INPUT_W3X" "$DG_DIR" > /dev/null

rm -f "$DG_DIR/conversation.json" 2>/dev/null || true
rm -f "$DG_DIR/war3mapSkin.w3a" "$DG_DIR/war3mapSkin.w3h" "$DG_DIR/war3mapSkin.w3q" "$DG_DIR/war3mapSkin.w3u" 2>/dev/null || true
find "$DG_DIR" -maxdepth 1 -name "Scripts" -type d -exec rm -rf {} + 2>/dev/null || true

[ -f "$DG_DIR/war3map.doo" ]      && python3 "$DOO_DG"   "$DG_DIR/war3map.doo"      "$DG_DIR/war3map.doo.tmp"      && mv "$DG_DIR/war3map.doo.tmp"      "$DG_DIR/war3map.doo"
[ -f "$DG_DIR/war3mapUnits.doo" ] && python3 "$UNITS_DG" "$DG_DIR/war3mapUnits.doo" "$DG_DIR/war3mapUnits.doo.tmp" && mv "$DG_DIR/war3mapUnits.doo.tmp" "$DG_DIR/war3mapUnits.doo"
[ -f "$DG_DIR/war3map.w3i" ]      && python3 "$W3I_DG"   "$DG_DIR/war3map.w3i"      "$DG_DIR/war3map.w3i.tmp"      && mv "$DG_DIR/war3map.w3i.tmp"      "$DG_DIR/war3map.w3i"
for _ext in w3a w3h w3q w3u; do
    [ -f "$DG_DIR/war3map.$_ext" ] && python3 "$W3OBJ_DG" "$DG_DIR/war3map.$_ext" "$DG_DIR/war3map.$_ext.tmp" && mv "$DG_DIR/war3map.$_ext.tmp" "$DG_DIR/war3map.$_ext"
done
[ -f "$DG_DIR/war3map.w3e" ]      && python3 "$W3E_DG"  "$DG_DIR/war3map.w3e"       "$DG_DIR/war3map.w3e.tmp"       && mv "$DG_DIR/war3map.w3e.tmp"       "$DG_DIR/war3map.w3e"

if grep -q 'BlzCreateUnitWithSkin' "$J"; then
    sed "s/BlzCreateUnitWithSkin(\([^,]*\),\([^,]*\),\([^,]*\),\([^,]*\),\([^,]*\),[^)]*)/CreateUnit(\1,\2,\3,\4,\5)/g" "$J" > "$DG_DIR/war3map.j"
else
    cp "$J" "$DG_DIR/war3map.j"
fi

"$REPACK" "$DG_DIR" "$HEADER_BIN" "$OUT_127"
echo "    1.27:    $OUT_127 ($(du -h "$OUT_127" | cut -f1))"

echo ""
echo "=========================================="
echo " 纯卡位POC完成！"
echo " 仅含：body block（-block/-noblock/-blockdebug）"
echo "=========================================="
