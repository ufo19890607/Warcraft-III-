# Warcraft III 重制版 → 1.27 转换流水线

## 你的实际工作流（推荐）

你**只在重制版的 .w3x 上改东西**，然后跑一个脚本一键转出 1.27 版。

```
                     reforged-to-127.sh
重制版 .w3x  ─────────────────────────────►  1.27 版 .w3x
(在重制版里改/保存)                         (直接拷到 1.27 整合包测试)
```

## 最简用法

```bash
# 输入: 任意一张重制版 .w3x
# 输出: 一张同功能的 1.27 .w3x

cd /root/.openclaw/workspace/scripts/wc3-ai/
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
