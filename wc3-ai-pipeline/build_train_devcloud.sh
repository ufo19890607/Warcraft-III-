#!/bin/bash
# build_train_devcloud.sh - 训练图一键注入流水线 (devcloud 本地版)
#
# 用法: ./build_train_devcloud.sh <input.w3x> <output-prefix>
#
# 示例:
#   ./build_train_devcloud.sh /data/ufo/Warcraft-III-/UD决战-原始.w3x \
#       /data/ufo/Warcraft-III-/converted-reforged/UD-decisive-V40
#
# 输出:
#   <output-prefix>-Reforged.w3x
#   <output-prefix>-1.27.w3x
#
# 注入顺序（5项功能）:
#   [2] TC战争践踏 + 齐射       inject_tc_stomp_salvo.py
#   [3] 集火后撤                inject_ai_focus_retreat.py
#   [4] 围杀                    inject_ai_surround.py
#   [5] 补刀(重写SalvoTick)     inject_ai_creep_control.py
#   [6] 英雄技能修复（可选）     inject_hero_skills.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STORMTOOL="$SCRIPT_DIR/tools/stormtool"
STORMPATCH="$SCRIPT_DIR/tools/stormpatch"
PJASS="$SCRIPT_DIR/tools/pjass"
COMMON_J="$SCRIPT_DIR/refs/common-127-clean.j"
BLIZZARD_J="$SCRIPT_DIR/refs/Blizzard.j"

INJECTOR_TC="$SCRIPT_DIR/inject_tc_stomp_salvo.py"
INJECTOR_FOCUS="$SCRIPT_DIR/inject_ai_focus_retreat.py"
INJECTOR_CREEP="$SCRIPT_DIR/inject_ai_creep_control.py"
INJECTOR_SURROUND="$SCRIPT_DIR/inject_ai_surround.py"
INJECTOR_HERO="$SCRIPT_DIR/inject_hero_skills.py"

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

# 检查必要工具和脚本
for f in "$STORMTOOL" "$STORMPATCH" "$INJECTOR_TC" "$INJECTOR_FOCUS" "$INJECTOR_CREEP" "$INJECTOR_SURROUND"; do
    if [ ! -e "$f" ]; then
        echo "ERROR: 缺少: $f"
        exit 1
    fi
done
chmod +x "$STORMTOOL" "$STORMPATCH" 2>/dev/null || true
[ -f "$PJASS" ] && chmod +x "$PJASS" 2>/dev/null || true

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "=========================================="
echo " 训练图 AIML 注入流水线"
echo "=========================================="
echo "输入: $INPUT_W3X"
echo ""

# [1] 解包
echo "[1/7] 解包 war3map.j..."
"$STORMTOOL" extract-one "$INPUT_W3X" "war3map.j" "$TMP_DIR/war3map.j" > /dev/null
J="$TMP_DIR/war3map.j"
echo "    $(wc -l < "$J") 行"

# [2] TC战争践踏 + 齐射
if grep -q "function Trig_AIML_SalvoForPlayer" "$J"; then
    echo "[2/7] TC+齐射已存在，跳过"
else
    echo "[2/7] 注入 TC战争践踏 + 齐射..."
    python3 "$INJECTOR_TC" "$J" "$J"
fi

# [3] 集火后撤（函数注入，SalvoTick 由 creep_control 统一重写）
if grep -q "function Trig_AIML_FocusRetreatForPlayer" "$J"; then
    echo "[3/7] 集火后撤已存在，跳过"
else
    echo "[3/7] 注入集火后撤..."
    python3 "$INJECTOR_FOCUS" "$J"
fi

# [4] 补刀 / 防补刀（重写 SalvoTick，必须在围杀之前）
if grep -q "function Trig_AIML_CreepControlForPlayer" "$J"; then
    echo "[4/7] 补刀已存在，跳过"
else
    echo "[4/7] 注入补刀 / 防补刀..."
    python3 "$INJECTOR_CREEP" "$J"
fi

# [5] 围杀（依赖 CreepControlForPlayer，必须在补刀之后）
if grep -q "function Trig_AIML_SurroundTick" "$J"; then
    echo "[5/7] 围杀已存在，跳过"
else
    echo "[5/7] 注入围杀..."
    python3 "$INJECTOR_SURROUND" "$J"
fi

# [6] 英雄技能修复（可选）
if [ -f "$INJECTOR_HERO" ]; then
    if grep -q "function Trig_AIML_HeroSkillInit" "$J"; then
        echo "[6/7] 英雄技能已存在，跳过"
    else
        echo "[6/7] 注入英雄技能修复..."
        python3 "$INJECTOR_HERO" "$J"
    fi
else
    echo "[6/7] inject_hero_skills.py 不存在，跳过"
fi

# [7] pjass 语法检查
if [ -f "$PJASS" ] && [ -f "$COMMON_J" ] && [ -f "$BLIZZARD_J" ]; then
    echo "[7/7] pjass 语法检查..."
    ERRORS=$("$PJASS" "$COMMON_J" "$BLIZZARD_J" "$J" 2>&1 | grep -c "$(basename "$J"):" || true)
    if [ "$ERRORS" -gt 0 ]; then
        echo "ERROR: $ERRORS 个语法错误:"
        "$PJASS" "$COMMON_J" "$BLIZZARD_J" "$J" 2>&1 | grep "$(basename "$J"):" | head -10
        exit 1
    fi
    echo "    0 errors ✓"
else
    echo "[7/7] pjass 不可用，跳过语法检查"
fi

# 打包 Reforged
echo ""
echo "打包 Reforged..."
"$STORMPATCH" "$INPUT_W3X" "$OUT_REFORGED" "war3map.j" "$J" > /dev/null
echo "    $OUT_REFORGED ($(du -h "$OUT_REFORGED" | cut -f1))"

# 打包 1.27（降级 reforged-only API）
echo "打包 1.27..."
if grep -q 'BlzCreateUnitWithSkin' "$J"; then
    sed 's/BlzCreateUnitWithSkin(\([^,]*\),\([^,]*\),\([^,]*\),\([^,]*\),[^)]*)/CreateUnit(\1,\2,\3,\4)/g' "$J" > "$TMP_DIR/war3map_127.j"
    "$STORMPATCH" "$INPUT_W3X" "$OUT_127" "war3map.j" "$TMP_DIR/war3map_127.j" > /dev/null
else
    "$STORMPATCH" "$INPUT_W3X" "$OUT_127" "war3map.j" "$J" > /dev/null
fi
echo "    $OUT_127 ($(du -h "$OUT_127" | cut -f1))"

echo ""
echo "=========================================="
echo " 完成!"
echo " 功能：TC践踏 | 齐射 | 集火后撤 | 补刀 | 围杀"
echo " 命令：-debug | -creep | -surround"
echo "=========================================="
