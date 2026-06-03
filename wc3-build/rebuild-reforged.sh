#!/bin/bash
# 重制版一键打包：改完 v17-source-reforged/war3map.j 后跑
set -e
cd /data/ufo/Warcraft-III-/wc3-build
./stormpatch v17-source-reforged/orig.w3x \
  /data/ufo/Warcraft-III-/converted-1.27/UD-decisive-reforged-MYBUILD.w3x \
  war3map.j \
  v17-source-reforged/war3map.j
echo "✓ done: /data/ufo/Warcraft-III-/converted-1.27/UD-decisive-reforged-MYBUILD.w3x"
ls -la /data/ufo/Warcraft-III-/converted-1.27/UD-decisive-reforged-MYBUILD.w3x
