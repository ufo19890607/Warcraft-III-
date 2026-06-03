#!/bin/bash
# build_train.sh - 训练图一键流水线
# 用法: ./build_train.sh <input.w3x> <output-prefix>
#
# 输入: 重制版训练图 .w3x (已含原始触发器)
# 输出:
#   <output-prefix>-Reforged.w3x  — 重制版 (注入了 AIML)
#   <output-prefix>-1.27.w3x     — 1.27 版 (降级 + 注入了 AIML)
#
# 注入功能:
#   1. 智能 TC 战争践踏 (inject_aiml_v3.py 的 TC stomp 部分)
#   2. 单体走位齐射 (per-unit kite)
#   3. 先知智能闪电链 (stop 阶段对残血/低血英雄)
#   4. 先知加点: 2CL + 1Wolf (替换 Far Sight)
#   5. TC 只学 War Stomp (替换 Shockwave)
#   6. 暗影猎手加点修复 (ComputerSkill2 加 Hex)
#   7. -debug 命令开关
#
# 依赖:
#   - stormtool / stormpatch (在 scripts/wc3-trigger-extract/)
#   - inject_aiml_v3.py (TC stomp + salvo)
#   - inject_aiml_kite.py (kite + 英雄技能修复)
#   - reforged-to-127.sh (重制版→1.27降级)
#   - pjass (语法检查)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTRACT_DIR="$SCRIPT_DIR/../wc3-trigger-extract"
INJECTOR_STOMP="$SCRIPT_DIR/inject_aiml_v3.py"
INJECTOR_KITE="$SCRIPT_DIR/inject_aiml_kite.py"
INJECTOR_CREEP="$SCRIPT_DIR/inject_creep_control.py"
INJECTOR_FOCUS="$SCRIPT_DIR/inject_focus_retreat.py"
REFORGED_TO_127="$SCRIPT_DIR/reforged-to-127.sh"
PJASS="/tmp/pjass/pjass"
COMMON_J="$SCRIPT_DIR/refs/common-127-clean.j"
BLIZZARD_J="$(cd "$SCRIPT_DIR/../../output/wc3-decisive/ref-template" && pwd)/Scripts\\Blizzard.j"

if [ $# -lt 2 ]; then
    echo "用法: $0 <input.w3x> <output-prefix>"
    echo ""
    echo "示例: $0 UD-train-reforged.w3x UD-decisive-V33"
    echo "  → UD-decisive-V33-Reforged.w3x"
    echo "  → UD-decisive-V33-1.27.w3x"
    exit 1
fi

INPUT_W3X="$(realpath "$1")"
OUT_PREFIX="$2"
OUT_REFORGED="${OUT_PREFIX}-Reforged.w3x"
OUT_127="${OUT_PREFIX}-1.27.w3x"

# Sanity checks
for f in "$EXTRACT_DIR/stormtool" "$EXTRACT_DIR/stormpatch" "$INJECTOR_STOMP" "$INJECTOR_KITE" "$REFORGED_TO_127"; do
    if [ ! -e "$f" ]; then
        echo "ERROR: 必需依赖缺失: $f"
        exit 1
    fi
done

if [ ! -f "$INPUT_W3X" ]; then
    echo "ERROR: 输入文件不存在: $INPUT_W3X"
    exit 1
fi

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "=========================================="
echo " 训练图 AIML 注入流水线"
echo "=========================================="
echo "输入: $INPUT_W3X"
echo "输出: $OUT_REFORGED"
echo "      $OUT_127"
echo ""

# ---------- 1. 解包 war3map.j ----------
echo "[1/5] 解包 war3map.j..."
"$EXTRACT_DIR/stormtool" extract-one "$INPUT_W3X" "war3map.j" "$TMP_DIR/war3map.j" > /dev/null
J_ORIG="$TMP_DIR/war3map.j"
ORIG_SIZE=$(wc -c < "$J_ORIG")
echo "    原始: $ORIG_SIZE bytes, $(wc -l < "$J_ORIG") lines"

# ---------- 2. 注入 TC Stomp + Salvo (inject_aiml_v3.py) ----------
# 只在没有现存 AIML 函数时注入（避免重复）
if grep -q "Trig_AIML_SalvoForPlayer" "$J_ORIG"; then
    echo "[2/5] TC Stomp + 齐射已存在, 跳过 inject_aiml_v3.py"
else
    echo "[2/5] 注入 TC Stomp + 远程齐射..."
    python3 "$INJECTOR_STOMP" "$J_ORIG" > /dev/null
fi

# ---------- 3. 注入 Kite + 英雄技能修复 (inject_aiml_kite.py) ----------
if grep -q "Trig_AIML_PerUnitKiteCB" "$J_ORIG"; then
    echo "[3/6] Kite 已存在, 跳过 inject_aiml_kite.py"
else
    echo "[3/6] 注入单体走位 + 英雄技能修复..."
    python3 "$INJECTOR_KITE" "$J_ORIG"
fi

# ---------- 4. 注入补刀+血线控制 (inject_creep_control.py) ----------
if grep -q "Trig_AIML_CreepControlForPlayer" "$J_ORIG"; then
    echo "[4/7] 补刀+血线控制已存在, 跳过"
else
    echo "[4/7] 注入补刀 + 血线控制..."
    python3 "$INJECTOR_CREEP" "$J_ORIG"
fi

# ---------- 5. 注入集火保护 (inject_focus_retreat.py) ----------
if grep -q "Trig_AIML_FocusRetreatForPlayer" "$J_ORIG"; then
    echo "[5/7] 集火保护已存在, 跳过"
else
    echo "[5/7] 注入集火保护 (被集火单位自动后撤)..."
    python3 "$INJECTOR_FOCUS" "$J_ORIG"
fi

# ---------- 6. pjass 语法检查 ----------
echo "[6/7] pjass 语法检查..."
ERRORS=$("$PJASS" "$COMMON_J" "$BLIZZARD_J" "$J_ORIG" 2>&1 | grep "$(basename "$J_ORIG"):" | wc -l || true)
if [ "$ERRORS" -gt 0 ]; then
    echo "ERROR: pjass 发现 $ERRORS 个错误:"
    "$PJASS" "$COMMON_J" "$BLIZZARD_J" "$J_ORIG" 2>&1 | grep "$(basename "$J_ORIG"):" | head -10
    exit 1
fi
echo "    pjass: 0 errors ✓"

INJECTED_SIZE=$(wc -c < "$J_ORIG")
echo "    注入后: $INJECTED_SIZE bytes (+$(( INJECTED_SIZE - ORIG_SIZE )) bytes)"

# ---------- 7. 打包输出 ----------
echo "[7/7] 打包..."

# 5a. Reforged 版: stormpatch 替换 war3map.j
"$EXTRACT_DIR/stormpatch" "$INPUT_W3X" "$OUT_REFORGED" "war3map.j" "$J_ORIG" > /dev/null
echo "    Reforged: $OUT_REFORGED ($(wc -c < "$OUT_REFORGED") bytes)"

# 5b. 1.27 版
# 如果输入本身就是 1.27 格式 (没有 reforged 特有的 skinId 等)，直接 stormpatch
if grep -q 'skinId' "$TMP_DIR/extracted/war3map.doo" 2>/dev/null || \
   grep -q 'REFORGED' "$INPUT_W3X" 2>/dev/null || \
   [ -f "$TMP_DIR/extracted/war3map.w3s" ]; then
    # 确实是 reforged，走降级流程
    bash "$REFORGED_TO_127" "$TMP_DIR/extracted" "$OUT_127" > /dev/null 2>&1
else
    # 已经是 1.27 格式，直接 stormpatch
    "$EXTRACT_DIR/stormpatch" "$INPUT_W3X" "$OUT_127" "war3map.j" "$J_ORIG" > /dev/null
fi
echo "    1.27:     $OUT_127 ($(wc -c < "$OUT_127") bytes)"

echo ""
echo "=========================================="
echo " 完成!"
echo "=========================================="
echo ""
echo "功能列表:"
echo "  ✓ 智能 TC 战争践踏 (600范围内3+敌人触发)"
echo "  ✓ 远程齐射 (focus-fire 集火最近残血)"
echo "  ✓ 单体走位 (被贴脸的远程兵向上/下闪避)"
echo "  ✓ 先知智能闪电链 (残血优先/英雄<100HP必放)"
echo "  ✓ 先知加点: 2级闪电链 + 1级狼"
echo "  ✓ TC 只学战争践踏 (不学震荡波)"
echo "  ✓ 暗影猎手: 变羊+医疗波+大招"
echo "  ✓ 补刀系统 (野怪<200靠近, <100集火)"
echo "  ✓ 血线控制 (DK在场时控血100-150, 诱骗DC)"
echo "  ✓ 集火保护 (单位0.5s掉>20%maxHP时后撤300码)"
echo "  ✓ -debug / -creep 命令开关"
echo ""
echo "调试: 游戏内输入 -debug 打开/关闭 AI 信息显示"
echo "      游戏内输入 -creep 打开/关闭 补刀+血线控制"
