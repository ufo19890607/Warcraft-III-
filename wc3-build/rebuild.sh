#!/bin/bash
# 一键打包 1.27 .w3x: 改完 v16-source-1.27/war3map.j 后跑这个
set -e
cd /data/ufo/Warcraft-III-/wc3-build
./repack v16-source-1.27 hm3w_header.bin /data/ufo/Warcraft-III-/converted-1.27/UD-decisive-1.27-MYBUILD.w3x
echo "✓ done: /data/ufo/Warcraft-III-/converted-1.27/UD-decisive-1.27-MYBUILD.w3x"
ls -la /data/ufo/Warcraft-III-/converted-1.27/UD-decisive-1.27-MYBUILD.w3x
