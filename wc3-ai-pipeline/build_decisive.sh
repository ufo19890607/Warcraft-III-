#!/bin/bash
# build_decisive.sh
#
# UD 决战操作图 — 一键流水线
#
# 输入: 一张 reforged 版的 UD 决战操作图 .w3x
# 输出:
#   - <prefix>-Reforged.w3x  : 重制版 (注入了智能 TC + 齐射, 但保持 reforged 格式)
#   - <prefix>-1.27.w3x      : 1.27 兼容版 (注入 + 全套降级, 1.27 整合包能跑)
#
# 用法:
#   ./build_decisive.sh <input-reforged.w3x> <output-prefix>
#
# 例如:
#   ./build_decisive.sh /root/.openclaw/workspace/output/wc3-decisive/userinput/UD-决战-2.0.w3x \
#                       /root/.openclaw/workspace/output/wc3-decisive/UD-操作训练-V20
#   → 输出:
#       UD-操作训练-V20-Reforged.w3x
#       UD-操作训练-V20-1.27.w3x
#
# 流程:
#   1. 解包 reforged .w3x -> 临时目录 (用 stormtool)
#   2. 抽出 war3map.j -> 注入智能 TC 战争践踏 + 远程齐射 (inject_aiml_v2.py)
#   3. [Reforged 输出] 用 stormpatch 把注入后的 war3map.j 写回原 .w3x 副本
#      (保持 reforged 格式, 不动其他文件; reforged 编辑器/客户端可直接打开)
#   4. [1.27 输出] 跑全套降级 (reforged-to-127.sh):
#        doodad/units.doo skinId 砍掉
#        w3i v31 -> v25
#        w3a/w3h/w3q/w3u v3 -> v2
#        w3e v12 -> v11
#        BlzCreateUnitWithSkin -> CreateUnit
#        + 注入后的 war3map.j 替换原 .j
#        + 用 1.27 标准 hm3w_header.bin 重打包

set -euo pipefail

if [ $# -ne 2 ]; then
    cat <<EOF
用法: $0 <input-reforged.w3x> <output-prefix>

例如:
  $0 ~/UD-决战-2.0.w3x /root/.openclaw/workspace/output/wc3-decisive/UD-操作训练-V20

→ 会产出:
    /root/.openclaw/workspace/output/wc3-decisive/UD-操作训练-V20-Reforged.w3x
    /root/.openclaw/workspace/output/wc3-decisive/UD-操作训练-V20-1.27.w3x
EOF
    exit 64
fi

INPUT_W3X="$(realpath "$1")"
OUT_PREFIX="$2"

OUT_REFORGED="${OUT_PREFIX}-Reforged.w3x"
OUT_127="${OUT_PREFIX}-1.27.w3x"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTRACT_DIR="$SCRIPT_DIR/../wc3-trigger-extract"
INJECTOR="$SCRIPT_DIR/inject_aiml_v3.py"
REFORGED_TO_127="$SCRIPT_DIR/reforged-to-127.sh"

# Sanity checks
for f in "$EXTRACT_DIR/stormtool" "$EXTRACT_DIR/stormpatch" "$INJECTOR" "$REFORGED_TO_127"; do
    if [ ! -e "$f" ]; then
        echo "ERROR: 必需依赖缺失: $f"
        exit 1
    fi
done

if [ ! -f "$INPUT_W3X" ]; then
    echo "ERROR: 输入图不存在: $INPUT_W3X"
    exit 1
fi

# Make output directory if needed
mkdir -p "$(dirname "$OUT_REFORGED")"

TMP_DIR="$(mktemp -d -t build-decisive.XXXXXX)"
trap "rm -rf '$TMP_DIR'" EXIT

echo "============================================================"
echo "[输入]  $INPUT_W3X"
echo "[输出]  Reforged: $OUT_REFORGED"
echo "        1.27:     $OUT_127"
echo "[临时]  $TMP_DIR"
echo "============================================================"

# ---------- 1. 解包 ----------
echo
echo "[1/5] 解包 reforged .w3x..."
mkdir -p "$TMP_DIR/extracted"
"$EXTRACT_DIR/stormtool" extract "$INPUT_W3X" "$TMP_DIR/extracted" >/dev/null

if [ ! -f "$TMP_DIR/extracted/war3map.j" ]; then
    echo "ERROR: 解包后没找到 war3map.j (可能 input 不是有效 .w3x)"
    exit 1
fi

J_ORIG="$TMP_DIR/extracted/war3map.j"
J_INJECTED="$TMP_DIR/war3map.injected.j"

ORIG_SIZE=$(wc -c < "$J_ORIG")
echo "    war3map.j 原始: $ORIG_SIZE bytes"

# ---------- 2. 注入 AIML ----------
echo
echo "[2/5] 注入智能 TC 战争践踏 + 远程齐射 (inject_aiml_v2.py)..."
python3 "$INJECTOR" "$J_ORIG" "$J_INJECTED"

INJ_SIZE=$(wc -c < "$J_INJECTED")
DELTA=$((INJ_SIZE - ORIG_SIZE))
echo "    war3map.j 注入后: $INJ_SIZE bytes (+$DELTA)"

# ---------- 3. Reforged 输出: stormpatch 单文件替换 ----------
echo
echo "[3/5] [Reforged] 用 stormpatch 把注入后的 .j 写回原图..."
"$EXTRACT_DIR/stormpatch" "$INPUT_W3X" "$OUT_REFORGED" "war3map.j" "$J_INJECTED"

# ---------- 4. 1.27 输出: 全套降级 + 注入 ----------
echo
echo "[4/5] [1.27] 调用 reforged-to-127.sh 做全套降级 + 把注入版 .j 替换进去..."
# reforged-to-127.sh 接受 [extra-j-injection.j], 但它的实现是"在 endglobals 后追加 extra"
# 我们需要的是"用注入版 .j 整体替换", 所以这里走的路径是:
#   先让 reforged-to-127.sh 跑完默认转换 (它会保留原 .j 并做 BlzCreateUnitWithSkin sed)
#   然后我们用 stormpatch 把注入版 .j 覆盖进 1.27 输出图
#
# 但是更简洁的做法是: 直接复用 reforged-to-127.sh 的全部降级流程, 然后单独把
# 注入版 .j 替换原图的 .j。我们需要的"先注入再降级" vs "先降级再注入"是有差别的:
#   - inject_aiml_v2.py 用的 API (CreateGroup, GroupEnumUnitsInRange,
#     IssueImmediateOrder, GetWidgetLife, IsUnitType, ...) 全部是 1.27 兼容的.
#   - 但原图的 .j 里如果有 BlzCreateUnitWithSkin, 是 reforged 写法, 1.27 不认.
# 所以正确顺序: 先对原 .j 做 1.27 兼容化 (sed BlzCreateUnitWithSkin -> CreateUnit),
# 再注入 AIML。这样最终的 .j 就是 1.27 兼容的。
J_127_BASE="$TMP_DIR/war3map.127base.j"
J_127_FINAL="$TMP_DIR/war3map.127final.j"

cp "$J_ORIG" "$J_127_BASE"

# 4a. 1.27 兼容化 (BlzCreateUnitWithSkin -> CreateUnit)
python3 - "$J_127_BASE" <<'PY'
import sys, re
p = sys.argv[1]
with open(p, 'r', encoding='latin-1') as f:
    src = f.read()
new_src, n = re.subn(
    r"BlzCreateUnitWithSkin\(\s*([^,]+,\s*[^,]+,\s*[^,]+,\s*[^,]+,\s*[^,]+),\s*[^)]+\)",
    r"CreateUnit( \1 )",
    src
)
if n > 0:
    with open(p, 'w', encoding='latin-1') as f:
        f.write(new_src)
    print(f"    BlzCreateUnitWithSkin -> CreateUnit: {n} 处")
else:
    print(f"    BlzCreateUnitWithSkin -> CreateUnit: 0 处 (本图未使用)")
PY

# 4b. 在 1.27 兼容版 .j 上注入 AIML
python3 "$INJECTOR" "$J_127_BASE" "$J_127_FINAL" >/dev/null

# 4c. 跑 reforged-to-127.sh 做整图降级 (产出"无 AIML 但 1.27 兼容"的 .w3x)
TMP_127_BARE="$TMP_DIR/_127_bare.w3x"
"$REFORGED_TO_127" "$INPUT_W3X" "$TMP_127_BARE" >/dev/null

# 4d. 用注入版 .j 单文件替换覆盖进去
"$EXTRACT_DIR/stormpatch" "$TMP_127_BARE" "$OUT_127" "war3map.j" "$J_127_FINAL"

# ---------- 5. 完成报告 ----------
echo
echo "[5/5] 完成"
echo "============================================================"
echo "✓ Reforged 版: $OUT_REFORGED  ($(stat -c %s "$OUT_REFORGED") bytes)"
echo "✓ 1.27 版:    $OUT_127         ($(stat -c %s "$OUT_127") bytes)"
echo "============================================================"
echo
echo "已注入的功能:"
echo "  - 智能 TC 战争践踏 (Trig_AIML_TC_Stomp_Logic)"
echo "  - 远程齐射 (Trig_AIML_SalvoTick, 0.5 秒一次)"
echo "  - [V19] Hit-and-run kite — 敌方近战+飞行 ≥60% 时, 贴脸的远程边退边打"
echo "  - 自定义远程白名单见 inject_aiml_v3.py 顶部"
