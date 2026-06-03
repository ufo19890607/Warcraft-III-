#!/bin/bash
# reforged-to-127.sh
# 把一张 reforged 版的 .w3x 地图转成 1.27 兼容的 .w3x
#
# 用法:
#   ./reforged-to-127.sh <reforged.w3x> <output.w3x> [extra-j-injection.j]
#
# 例如:
#   ./reforged-to-127.sh UD-decisive-reforged.w3x UD-decisive-1.27.w3x
#   ./reforged-to-127.sh UD-decisive-reforged.w3x UD-decisive-1.27-AI.w3x my-aiml.j
#
# 流程:
#   1. 解包 reforged .w3x 到临时目录
#   2. 用 doo_downgrade / units_doo_downgrade / w3i_downgrade 把数据文件降级到 1.27 layout
#   3. 用 1.27 标准 hm3w_header.bin 替换 header
#   4. (可选) 把 extra-j-injection.j 的内容注入到 war3map.j
#   5. 用 repack 重打包成新的 .w3x
#
# 依赖:
#   ../wc3-trigger-extract/stormtool   (解包)
#   ../wc3-trigger-extract/repack      (打包)
#   ../wc3-trigger-extract/doo_downgrade.py
#   ../wc3-trigger-extract/units_doo_downgrade.py
#   ../wc3-trigger-extract/w3i_downgrade.py
#   ../wc3-trigger-extract/build/StormLib
#   <workspace>/output/wc3-decisive/hm3w_header.bin   (1.27 标准 header)

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: $0 <reforged.w3x> <output.w3x> [extra-j-injection.j]"
    exit 64
fi

REFORGED_W3X="$(realpath "$1")"
OUTPUT_W3X="$(realpath -m "$2")"
EXTRA_J="${3:-}"
[ -n "$EXTRA_J" ] && EXTRA_J="$(realpath "$EXTRA_J")"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTRACT_DIR="$SCRIPT_DIR/../wc3-trigger-extract"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
HEADER_BIN="$WORKSPACE/output/wc3-decisive/hm3w_header.bin"

if [ ! -f "$HEADER_BIN" ]; then
    echo "ERROR: 1.27 标准 header 缺失: $HEADER_BIN"
    echo "  这个文件是从一张已知 1.27 .w3x 的前 512 字节抠出来的。"
    echo "  如果丢了, 需要找一张 1.27 .w3x 重新生成: dd if=foo.w3x of=hm3w_header.bin bs=1 count=512"
    exit 1
fi

TMP_DIR="$(mktemp -d -t reforged-to-127.XXXXXX)"
trap "rm -rf '$TMP_DIR'" EXIT
echo "[1/5] 工作目录: $TMP_DIR"

echo "[2/5] 解包 reforged .w3x..."
mkdir -p "$TMP_DIR/extracted"
"$EXTRACT_DIR/stormtool" extract "$REFORGED_W3X" "$TMP_DIR/extracted"

echo "[3/5] 降级数据文件 (reforged 1.32+ -> 1.27 layout)..."
EX="$TMP_DIR/extracted"

# 删除 reforged-only 文件 (1.27 不识别)
rm -f "$EX/conversation.json" \
      "$EX/war3mapSkin.w3a" "$EX/war3mapSkin.w3h" \
      "$EX/war3mapSkin.w3q" "$EX/war3mapSkin.w3u"

# war3map.doo: 砍掉 doodad 的 skinId 字段
if [ -f "$EX/war3map.doo" ]; then
    python3 "$EXTRACT_DIR/doo_downgrade.py" "$EX/war3map.doo" "$EX/war3map.doo.tmp"
    mv "$EX/war3map.doo.tmp" "$EX/war3map.doo"
fi

# war3mapUnits.doo: 砍掉 unit 的 skinId 字段
if [ -f "$EX/war3mapUnits.doo" ]; then
    python3 "$EXTRACT_DIR/units_doo_downgrade.py" "$EX/war3mapUnits.doo" "$EX/war3mapUnits.doo.tmp"
    mv "$EX/war3mapUnits.doo.tmp" "$EX/war3mapUnits.doo"
fi

# war3map.w3i: format version 降到 25, 砍掉新增字段
if [ -f "$EX/war3map.w3i" ]; then
    python3 "$EXTRACT_DIR/w3i_downgrade.py" "$EX/war3map.w3i" "$EX/war3map.w3i.tmp"
    mv "$EX/war3map.w3i.tmp" "$EX/war3map.w3i"
fi

# war3map.w3e: terrain v12 -> v11 (flags 字段从 1 字节扩到 2 字节, 需要按公式合并)
if [ -f "$EX/war3map.w3e" ]; then
    python3 "$EXTRACT_DIR/w3e_downgrade.py" "$EX/war3map.w3e" "$EX/war3map.w3e.tmp"
    mv "$EX/war3map.w3e.tmp" "$EX/war3map.w3e"
fi

# war3map.w3a/.w3h/.w3q/.w3u: object data v3 -> v2
#   每个 entry 在 new_id 后多 2 个 uint32 字段, 砍掉它们
for f in war3map.w3a war3map.w3h war3map.w3q war3map.w3u; do
    if [ -f "$EX/$f" ]; then
        python3 "$EXTRACT_DIR/w3_objdata_downgrade.py" "$EX/$f" "$EX/$f.tmp"
        mv "$EX/$f.tmp" "$EX/$f"
    fi
done

# war3map.j: 替换 reforged-only API
#   BlzCreateUnitWithSkin(p, id, x, y, f, skinId) -> CreateUnit(p, id, x, y, f)
if [ -f "$EX/war3map.j" ]; then
    python3 - "$EX/war3map.j" <<'PY'
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
    print(f"  patched {n} BlzCreateUnitWithSkin -> CreateUnit in war3map.j")
PY
fi

echo "[4/5] (可选) 注入自定义 JASS..."
if [ -n "$EXTRA_J" ] && [ -f "$EXTRA_J" ]; then
    if [ -f "$EX/war3map.j" ]; then
        # 在 endglobals 后注入用户的 JASS
        python3 - "$EX/war3map.j" "$EXTRA_J" <<'PY'
import sys
target_j, extra_j = sys.argv[1], sys.argv[2]
with open(target_j, 'rb') as f:
    src = f.read().decode('latin-1')
with open(extra_j, 'rb') as f:
    extra = f.read().decode('latin-1')
# 注入到 endglobals 之后
marker = 'endglobals\n'
if marker in src:
    idx = src.find(marker) + len(marker)
    src = src[:idx] + '\n' + extra + '\n' + src[idx:]
    with open(target_j, 'wb') as f:
        f.write(src.encode('latin-1'))
    print(f"injected {len(extra)} bytes into {target_j}")
else:
    print(f"WARN: no endglobals in {target_j}, skip inject")
PY
    fi
else
    echo "  (无额外 JASS 注入)"
fi

echo "[5/5] 用 1.27 header 重打包..."
"$EXTRACT_DIR/repack" "$EX" "$HEADER_BIN" "$OUTPUT_W3X"

echo
echo "✓ 完成: $OUTPUT_W3X"
ls -la "$OUTPUT_W3X"
