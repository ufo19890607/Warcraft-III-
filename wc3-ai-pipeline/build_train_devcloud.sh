#!/bin/bash
# build_train_devcloud.sh - 训练图一键流水线 (devcloud 本地版)
# 用法: ./build_train_devcloud.sh <input.w3x> <output-prefix>
#
# 示例:
#   ./build_train_devcloud.sh /data/ufo/Warcraft-III-/UD决战-reforged.w3x \
#       /data/ufo/Warcraft-III-/converted-reforged/UD-decisive-V40
#
# 输出:
#   <output-prefix>-Reforged.w3x
#   <output-prefix>-1.27.w3x
#
# 智能功能注入顺序:
#   [2] TC战争践踏 + 齐射 (inject_aiml_v3.py)
#   [3] 走位 + 英雄技能 (inject_aiml_kite.py)
#   [4] 补刀 / 防补刀 (inject_creep_control.py)
#   [5] 集火后撤 (inject_focus_retreat.py)
#   [6] 围杀 (inject_surround.py)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STORMTOOL="$SCRIPT_DIR/tools/stormtool"
STORMPATCH="$SCRIPT_DIR/tools/stormpatch"
PJASS="$SCRIPT_DIR/tools/pjass"
COMMON_J="$SCRIPT_DIR/refs/common-127-clean.j"
BLIZZARD_J="$SCRIPT_DIR/refs/Blizzard.j"

INJECTOR_V3="$SCRIPT_DIR/inject_aiml_v3.py"
INJECTOR_KITE="$SCRIPT_DIR/inject_aiml_kite.py"
INJECTOR_CREEP="$SCRIPT_DIR/inject_creep_control.py"
INJECTOR_FOCUS="$SCRIPT_DIR/inject_focus_retreat.py"
INJECTOR_SURROUND="$SCRIPT_DIR/inject_surround.py"

if [ $# -lt 2 ]; then
    echo "用法: $0 <input.w3x> <output-prefix>"
    echo ""
    echo "示例: $0 /data/ufo/Warcraft-III-/UD决战.w3x /data/ufo/Warcraft-III-/converted-reforged/UD-V40"
    echo "  → UD-V40-Reforged.w3x + UD-V40-1.27.w3x"
    exit 1
fi

INPUT_W3X="$(realpath "$1")"
OUT_PREFIX="$2"
OUT_REFORGED="${OUT_PREFIX}-Reforged.w3x"
OUT_127="${OUT_PREFIX}-1.27.w3x"

# Sanity checks
for f in "$STORMTOOL" "$STORMPATCH" "$INJECTOR_V3" "$INJECTOR_KITE" "$INJECTOR_CREEP" "$INJECTOR_FOCUS" "$INJECTOR_SURROUND"; do
    if [ ! -e "$f" ]; then
        echo "ERROR: 缺少: $f"
        exit 1
    fi
done
chmod +x "$STORMTOOL" "$STORMPATCH" "$PJASS" 2>/dev/null || true

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "=========================================="
echo " 训练图 AIML 注入流水线 (devcloud)"
echo "=========================================="
echo "输入: $INPUT_W3X"
echo ""

# 1. 解包
echo "[1/8] 解包 war3map.j..."
"$STORMTOOL" extract-one "$INPUT_W3X" "war3map.j" "$TMP_DIR/war3map.j" > /dev/null
J="$TMP_DIR/war3map.j"
echo "    $(wc -l < "$J") lines"

# 2. TC + 齐射
if grep -q "Trig_AIML_SalvoForPlayer" "$J"; then
    echo "[2/8] TC+齐射已存在, 跳过"
else
    echo "[2/8] 注入 TC + 齐射..."
    python3 "$INJECTOR_V3" "$J" > /dev/null
fi

# 3. Kite + 英雄技能
if grep -q "Trig_AIML_PerUnitKiteCB" "$J"; then
    echo "[3/8] Kite+技能已存在, 跳过"
else
    echo "[3/8] 注入走位 + 英雄技能..."
    python3 "$INJECTOR_KITE" "$J"
fi

# 4. 补刀 / 防补刀
if grep -q "Trig_AIML_CreepControlForPlayer" "$J"; then
    echo "[4/8] 补刀已存在, 跳过"
else
    echo "[4/8] 注入补刀 / 防补刀..."
    python3 "$INJECTOR_CREEP" "$J"
fi

# 5. 集火后撤
if grep -q "Trig_AIML_FocusRetreatForPlayer" "$J"; then
    echo "[5/8] 集火后撤已存在, 跳过"
else
    echo "[5/8] 注入集火后撤..."
    python3 "$INJECTOR_FOCUS" "$J"
fi

# 6. 围杀
if grep -q "Trig_AIML_SurroundTick" "$J"; then
    echo "[6/8] 围杀已存在, 跳过"
else
    echo "[6/8] 注入围杀..."
    python3 "$INJECTOR_SURROUND" "$J"
fi

# 7. pjass 语法检查
echo "[7/8] pjass 检查..."
ERRORS=$("$PJASS" "$COMMON_J" "$BLIZZARD_J" "$J" 2>&1 | grep "$(basename "$J"):" | wc -l || true)
if [ "$ERRORS" -gt 0 ]; then
    echo "ERROR: $ERRORS 个语法错误:"
    "$PJASS" "$COMMON_J" "$BLIZZARD_J" "$J" 2>&1 | grep "$(basename "$J"):" | head -10
    exit 1
fi
echo "    0 errors ✓"

# 8. 打包
echo "[8/8] 打包..."

# Reforged
"$STORMPATCH" "$INPUT_W3X" "$OUT_REFORGED" "war3map.j" "$J" > /dev/null
echo "    $OUT_REFORGED ($(du -h "$OUT_REFORGED" | cut -f1))"

# 1.27 (降级 reforged-only API)
if grep -q 'BlzCreateUnitWithSkin' "$J"; then
    sed -i 's/BlzCreateUnitWithSkin(\([^,]*\),\([^,]*\),\([^,]*\),\([^,]*\),\([^)]*\))/CreateUnit(\1,\2,\3,\4)/g' "$J"
fi
"$STORMPATCH" "$INPUT_W3X" "$OUT_127" "war3map.j" "$J" > /dev/null
echo "    $OUT_127 ($(du -h "$OUT_127" | cut -f1))"

echo ""
echo "=========================================="
echo " 完成!"
echo "   智能功能: TC践踏 | 齐射 | 走位 | 补刀 | 集火后撤 | 围杀"
echo "   调试命令: -debug | -creep | -surround"
echo "=========================================="
