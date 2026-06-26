#!/bin/bash
# build_train_devcloud.sh - 训练图一键注入流水线 (devcloud 本地版)
#
# 用法: ./build_train_devcloud.sh <input.w3x> <output-prefix>
#
# 示例:
#   ./build_train_devcloud.sh $war3_dir/UD-decisive-micro-reforged.w3x UD-decisive-V41
#
# 输出:
#   <output-prefix>-Reforged.w3x
#   <output-prefix>-1.27.w3x
#
# 注入顺序（7项功能）:
#   [2] 齐射                    inject_salvo.py
#   [3] 英雄魔法(TC践踏+暗影猎手) inject_hero_magic.py
#   [4] 集火后撤                inject_ai_focus_retreat.py
#   [5] 补刀(重写SalvoTick)     inject_ai_creep_control.py
#   [6] 围杀                    inject_ai_surround.py
#   [7] 剑圣逃脱                inject_ai_blademaster.py
#   [8] Debug命令（可选）       inject_debug.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STORMTOOL="$SCRIPT_DIR/tools/stormtool"
STORMPATCH="$SCRIPT_DIR/tools/stormpatch"
PJASS="$SCRIPT_DIR/tools/pjass"
COMMON_J="$SCRIPT_DIR/refs/common-127-clean.j"
BLIZZARD_J="$SCRIPT_DIR/refs/Blizzard.j"

INJECTOR_SALVO="$SCRIPT_DIR/inject_salvo.py"
INJECTOR_MAGIC="$SCRIPT_DIR/inject_hero_magic.py"
INJECTOR_FOCUS="$SCRIPT_DIR/inject_ai_focus_retreat.py"
INJECTOR_CREEP="$SCRIPT_DIR/inject_ai_creep_control.py"
INJECTOR_SURROUND="$SCRIPT_DIR/inject_ai_surround.py"
INJECTOR_BM="$SCRIPT_DIR/inject_ai_blademaster.py"
INJECTOR_ESCAPE="$SCRIPT_DIR/inject_ai_escape.py"
INJECTOR_DEBUG="$SCRIPT_DIR/inject_debug.py"
REPACK="$SCRIPT_DIR/tools/repack"
HEADER_BIN="$SCRIPT_DIR/../base-1.27/base-1.27.w3x"  # 1.27 header source (stable, do not delete)
DOO_DG="$SCRIPT_DIR/tools/doo_downgrade.py"
UNITS_DG="$SCRIPT_DIR/tools/units_doo_downgrade.py"
W3I_DG="$SCRIPT_DIR/tools/w3i_downgrade.py"
W3E_DG="$SCRIPT_DIR/tools/w3e_downgrade.py"
W3OBJ_DG="$SCRIPT_DIR/tools/w3_objdata_downgrade.py"

if [ $# -lt 2 ]; then
    echo "用法: $0 <input.w3x> <output-prefix>"
    echo ""
    echo "示例: $0 xxx.w3x UD-decisive-V41"
    echo "  → converted-reforged/UD-V40-Reforged.w3x"
    echo "  → converted-1.27/UD-V40-1.27.w3x"
    exit 1
fi

INPUT_W3X="$(realpath "$1")"
OUT_PREFIX="$2"
_BASENAME="$(basename "$OUT_PREFIX")"
_DIR_REFORGED="$SCRIPT_DIR/../converted-reforged"
_DIR_127="$SCRIPT_DIR/../converted-1.27"
mkdir -p "$_DIR_REFORGED" "$_DIR_127"
OUT_REFORGED="$_DIR_REFORGED/${_BASENAME}-Reforged.w3x"
OUT_127="$_DIR_127/${_BASENAME}-1.27.w3x"

# 检查必要工具和脚本
for f in "$STORMTOOL" "$STORMPATCH" "$INJECTOR_SALVO" "$INJECTOR_MAGIC" "$INJECTOR_FOCUS" "$INJECTOR_CREEP" "$INJECTOR_SURROUND" "$INJECTOR_BM"; do
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
echo "[1/10] 解包 war3map.j + war3map.doo..."
"$STORMTOOL" extract-one "$INPUT_W3X" "war3map.j" "$TMP_DIR/war3map.j" > /dev/null
"$STORMTOOL" extract-one "$INPUT_W3X" "war3map.doo" "$TMP_DIR/war3map.doo" > /dev/null
J="$TMP_DIR/war3map.j"
DOO="$TMP_DIR/war3map.doo"
echo "    $(wc -l < "$J") 行"

# [2] 齐射
if grep -q "function Trig_AIML_SalvoForPlayer" "$J"; then
    echo "[2/10] 齐射已存在，跳过"
else
    echo "[2/10] 注入齐射..."
    python3 "$INJECTOR_SALVO" "$J" "$J"
fi

# [3] 英雄魔法（TC践踏 + 暗影猎手）
if grep -q "function Trig_AIML_TC_Stomp_Logic" "$J"; then
    echo "[3/10] 英雄魔法已存在，跳过"
else
    echo "[3/10] 注入英雄魔法（TC践踏 + 暗影猎手）..."
    python3 "$INJECTOR_MAGIC" "$J" "$J"
fi

# [4] 集火后撤
if grep -q "function Trig_AIML_FocusRetreatForPlayer" "$J"; then
    echo "[4/10] 集火后撤已存在，跳过"
else
    echo "[4/10] 注入集火后撤..."
    python3 "$INJECTOR_FOCUS" "$J"
fi

# [5] 补刀 / 防补刀
if grep -q "function Trig_AIML_CreepControlForPlayer" "$J"; then
    echo "[5/10] 补刀已存在，跳过"
else
    echo "[5/10] 注入补刀 / 防补刀..."
    python3 "$INJECTOR_CREEP" "$J"
fi

# [6] 围杀
if grep -q "function Trig_AIML_SurroundTick" "$J"; then
    echo "[6/10] 围杀已存在，跳过"
else
    echo "[6/10] 注入围杀..."
    python3 "$INJECTOR_SURROUND" "$J"
fi

# [7/10] 逃跑（依赖 SurroundInit 锚点）
if grep -q "function Trig_AIML_EscapeTick" "$J"; then
    echo "[7/10] 逃跑已存在，跳过"
else
    echo "[7/10] 注入逃跑..."
    python3 "$INJECTOR_ESCAPE" "$J" "$DOO"
fi

# [8/10] 剑圣逃脱（依赖 SH_Tick，必须在英雄魔法之后）
if grep -q "function Trig_AIML_BM_Tick" "$J"; then
    echo "[8/10] 剑圣逃脱已存在，跳过"
else
    echo "[8/10] 注入剑圣逃脱..."
    python3 "$INJECTOR_BM" "$J"
fi

# [8] Debug命令（可选）
if [ -f "$INJECTOR_DEBUG" ]; then
    if grep -q "function Trig_AIML_DebugToggle" "$J"; then
        echo "[9/10] Debug命令已存在，跳过"
    else
        echo "[9/10] 注入Debug命令..."
        python3 "$INJECTOR_DEBUG" "$J"
    fi
else
    echo "[9/10] inject_debug.py 不存在，跳过"
fi

# [9] pjass 语法检查
if [ -f "$PJASS" ] && [ -f "$COMMON_J" ] && [ -f "$BLIZZARD_J" ]; then
    echo "[10/10] pjass 语法检查..."
    ERRORS=$("$PJASS" "$COMMON_J" "$BLIZZARD_J" "$J" 2>&1 | grep -c "$(basename "$J"):" || true)
    if [ "$ERRORS" -gt 0 ]; then
        echo "ERROR: $ERRORS 个语法错误:"
        "$PJASS" "$COMMON_J" "$BLIZZARD_J" "$J" 2>&1 | grep "$(basename "$J"):" | head -10
        exit 1
    fi
    echo "    0 errors ✓"
else
    echo "[9/10] pjass 不可用，跳过语法检查"
fi

# 打包 Reforged
echo ""
echo "打包 Reforged..."
"$STORMPATCH" "$INPUT_W3X" "$OUT_REFORGED" "war3map.j" "$J" > /dev/null
echo "    $OUT_REFORGED ($(du -h "$OUT_REFORGED" | cut -f1))"

# 打包 1.27
echo "打包 1.27..."
DG_DIR="$TMP_DIR/downgrade"
mkdir -p "$DG_DIR"

"$STORMTOOL" extract "$INPUT_W3X" "$DG_DIR" > /dev/null

rm -f "$DG_DIR/conversation.json"
rm -f "$DG_DIR/war3mapSkin.w3a" "$DG_DIR/war3mapSkin.w3h" "$DG_DIR/war3mapSkin.w3q" "$DG_DIR/war3mapSkin.w3u"
find "$DG_DIR" -maxdepth 1 -name "Scripts" -type d -exec rm -rf {} + 2>/dev/null || true

[ -f "$DG_DIR/war3map.doo" ]      && python3 "$DOO_DG"   "$DG_DIR/war3map.doo"      "$DG_DIR/war3map.doo.tmp"      && mv "$DG_DIR/war3map.doo.tmp"      "$DG_DIR/war3map.doo"
[ -f "$DG_DIR/war3mapUnits.doo" ] && python3 "$UNITS_DG" "$DG_DIR/war3mapUnits.doo" "$DG_DIR/war3mapUnits.doo.tmp" && mv "$DG_DIR/war3mapUnits.doo.tmp" "$DG_DIR/war3mapUnits.doo"
[ -f "$DG_DIR/war3map.w3i" ]      && python3 "$W3I_DG"   "$DG_DIR/war3map.w3i"      "$DG_DIR/war3map.w3i.tmp"      && mv "$DG_DIR/war3map.w3i.tmp"      "$DG_DIR/war3map.w3i"
for _ext in w3a w3h w3q w3u; do
    [ -f "$DG_DIR/war3map.$_ext" ] && python3 "$W3OBJ_DG" "$DG_DIR/war3map.$_ext" "$DG_DIR/war3map.$_ext.tmp" && mv "$DG_DIR/war3map.$_ext.tmp" "$DG_DIR/war3map.$_ext"
done
[ -f "$DG_DIR/war3map.w3e" ]      && python3 "$W3E_DG"  "$DG_DIR/war3map.w3e"       "$DG_DIR/war3map.w3e.tmp"       && mv "$DG_DIR/war3map.w3e.tmp"       "$DG_DIR/war3map.w3e"

if grep -q 'BlzCreateUnitWithSkin' "$J"; then
    sed 's/BlzCreateUnitWithSkin(\([^,]*\),\([^,]*\),\([^,]*\),\([^,]*\),\([^,]*\),[^)]*)/CreateUnit(\1,\2,\3,\4,\5)/g' "$J" > "$DG_DIR/war3map.j"
else
    cp "$J" "$DG_DIR/war3map.j"
fi

"$REPACK" "$DG_DIR" "$HEADER_BIN" "$OUT_127"
echo "    $OUT_127 ($(du -h $OUT_127 | cut -f1))"

echo ""
echo "=========================================="
echo " 完成!"
echo " 功能：TC践踏 | 齐射 | 集火后撤 | 补刀 | 围杀 | 逃跑 | 剑圣逃脱"
echo " 命令：-debug | -creep | -surround | -escape"
echo "=========================================="
