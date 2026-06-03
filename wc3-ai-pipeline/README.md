# UD 决战操作图 — AI 注入流水线

## 一键流水线（**主入口，推荐使用**）

```bash
cd /root/.openclaw/workspace/scripts/wc3-ai/
./build_decisive.sh <input-reforged.w3x> <output-prefix>
```

输入一张重制版 UD 决战操作图，**同时**产出两个版本：

- `<prefix>-Reforged.w3x` — 重制版（注入了智能 TC + 齐射，保持 reforged 格式）
- `<prefix>-1.27.w3x` — 1.27 兼容版（注入 + 全套降级，1.27 整合包能跑）

注入的 AI 能力：

- **智能 TC 战争践踏** — 替换原图里所有 dumb stomp，改成判断周围敌方人数 / 附近是否有低血英雄才释放
- **远程齐射** — 每 0.5 秒选出「前排最危险的低血英雄 / 远程」，指挥所有远程部队集火
- **[V19] Hit-and-run kite** — 敌方近战+飞行占比 ≥60%时，贴脸的远程部队边退边打（远离敌方重心方向，每次退 100 码 ≈0.78 个 tile）
- 远程单位白名单可改 → `inject_aiml_v3.py` 文件顶部的 `RANGED_TROOPS` / `RANGED_HEROES`

例子：

```bash
./build_decisive.sh \
    /tmp/UD-决战-2.0.w3x \
    /root/.openclaw/workspace/output/wc3-decisive/UD-操作训练-V20
```

产出：

```
/root/.openclaw/workspace/output/wc3-decisive/UD-操作训练-V20-Reforged.w3x  ← 在重制版里打
/root/.openclaw/workspace/output/wc3-decisive/UD-操作训练-V20-1.27.w3x       ← 在 1.27 里打
```

## 在哪里改"智能"的参数

所有可调阈值都在 `inject_aiml_v3.py` 里 `AIML_GLOBALS`：

```
udg_aiml_StompMinEnemies = 2          # 周围 ≥2 个有效敌人才践踏
udg_aiml_StompRadius = 250.00         # 践踏判定半径
udg_aiml_StompManaCost = 100.00       # 至少要这么多法力才会触发
udg_aiml_StompHeroBypassRadius = 250  # 附近有敌方英雄 → 直接践踏（必中）
udg_aiml_SalvoMajorityRatio = 0.50    # 远程占总兵力 ≥50% 才齐射
udg_aiml_SalvoFrontRowCount = 4       # "前排" 取最近的 4 个敌人
# [V19] Kite 参数
udg_aiml_KiteEnabled = true           # 总开关
udg_aiml_KiteMeleeAirRatio = 0.60     # 敌方近战+飞行 ≥60% 才启动 kite
udg_aiml_KiteThreshold = 350.00       # 远程单位离 focus < 350 才退
udg_aiml_KiteStep = 100.00            # 每次退 100 码（0.78 个 tile）
udg_aiml_KiteMinMapBound = 200.00     # 退到地图边缘 200 内不再退
```

## 仅降级、不注入（老脚本）

如果只想做格式转换、不要任何 AI 注入：

```bash
./reforged-to-127.sh input-reforged.w3x output-1.27.w3x
```

## 流水线实际做了什么

1. **解包** — 用 `stormtool` 把重制版 .w3x 解开成一堆文件
2. **降级 .doo** — `war3map.doo` 里 doodad 的 skinId 字段（重制版加的）被砍掉
3. **降级 Units.doo** — 单位摆放数据同样降级
4. **降级 .w3i** — 地图信息文件 format version 从 31 降到 25，砍掉新增字段
5. **替换 header** — 用一份已知好用的 1.27 标准 hm3w_header.bin 替换前 512 字节
6. **重打包** — 用 `repack` 把所有文件压回 .w3x

## 已经测试过的输入/输出

| 输入 (reforged) | 输出 (1.27) | 状态 |
|---|---|---|
| `UD-decisive-reforged-V17-StompOnly.w3x` (772KB) | 通过流水线产物 (540KB) | ✓ 文件结构正确 |

## 限制 / 注意事项

### 必须避开的 1.27 JASS 雷区
你在重制版 World Editor 里写脚本时，**不能用**这几样，1.27 编译器会拒绝：

| ❌ 重制版能用，1.27 不能用 | ✅ 1.27 兼容写法 |
|---|---|
| `1.0e18`, `1.5e9` (科学计数法) | `999999999.0` |
| `IsUnitInvulnerable(u)` | 这个 native 1.27 没有，删掉这条检查 |
| `GroupAddGroup(a, b)` | 用 `GroupEnumUnitsInRange` + filter 重新枚举 |
| `BlzXxx*` 系列（Blizzard API） | 1.27 全部没有 |

### 重制版编辑器的"陷阱"
**不要**在重制版 World Editor 里直接修改 `.w3x` 里的 .j 后保存——重制版会从 `war3map.wtg` 重新生成 .j，你在 .j 里手写的 JASS 会被冲掉。

正确做法：
- 简单改动 → 直接编辑 .w3x 里抽出来的 `war3map.j`，跑流水线
- 复杂改动 → 用重制版编辑器改触发器 (.wtg)，让它自动生成 .j；但 .j 里如果有自定义 JASS（AIML 这种），需要把这块 .j 抽出来作为 inject 文件

### 流水线已知的"信息损失"
- doodad/unit 的 skinId 字段被丢弃（1.27 没皮肤系统）
- 1.32+ 引入的新字段（item drops 在 doodad 上 / 第二技能槽 / 新地图属性）会丢
- 重制版独占的 4K 贴图 / 新模型也会丢

通常这些损失对游戏功能没影响。

## 静态检查 (推荐, 但非必需)

如果你想在打包**前**就发现 1.27 兼容性问题，可以装 pjass：

```bash
# 装 pjass (一次)
git clone https://github.com/lep/pjass.git /tmp/pjass
cd /tmp/pjass && make

# 检查一份 .j
/tmp/pjass/pjass /tmp/pjass-check/minimal.j /path/to/war3map.j
```

我已经在 OpenClaw 容器里搭好了 (`/tmp/pjass/pjass`)，你需要用就直接调用。

## 故障排除

| 现象 | 原因 | 修复 |
|---|---|---|
| 脚本报 "1.27 标准 header 缺失" | 没有 `output/wc3-decisive/hm3w_header.bin` | 找一张 1.27 .w3x 抠 512 字节: `dd if=foo.w3x of=hm3w_header.bin bs=1 count=512` |
| 1.27 能加载但 trigger 不工作 | reforged 的 .wtg 引用了 1.27 没有的 GUI action | 简单脚本: 重制版直接写自定义 JASS, 不用图形化 trigger |
| 1.27 一启动就崩 / 无法进游戏 | .j 里有 1.27 不支持的语法或 native | 用 pjass 静态检查; 看上面"必须避开的 1.27 JASS 雷区" |
| 1.27 加载界面卡死 | .doo / Units.doo 降级时数据丢失 | doodad/unit 有 item drops 时会丢; 大部分图无影响 |

## 文件位置速查

```
/root/.openclaw/workspace/scripts/wc3-ai/
  reforged-to-127.sh          ← 主流水线脚本
  README.md                   ← 本文档

/root/.openclaw/workspace/scripts/wc3-trigger-extract/
  stormtool                   ← MPQ 解包器
  repack                      ← MPQ 打包器
  stormpatch                  ← 单文件替换工具 (本流水线没用; 用于增量补丁)
  doo_downgrade.py            ← war3map.doo 降级
  units_doo_downgrade.py      ← Units.doo 降级
  w3i_downgrade.py            ← .w3i 降级

/root/.openclaw/workspace/output/wc3-decisive/
  hm3w_header.bin             ← 1.27 标准 512 字节 header
  versionJ_TC/war3map.j       ← V11 baseline (已知 1.27 能跑, 可作 reference)
```
