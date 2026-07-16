# DEGRADE.md — Reforged → 1.27 降级坑记录

_记录所有踩过的坑，下次直接查这里，不要再二分。_

---

## 坑 1：BlzCreateUnitWithSkin 第5个参数 `face` 被 sed 吃掉

**现象**：1.27 地图能进大厅但看不到玩家，或进去后 .j 加载失败。

**根因**：
- `BlzCreateUnitWithSkin(p, id, x, y, face, skinId)` 是6个参数
- 老的 sed 正则只抓4个参数：`(\1,\2,\3,\4)` → face 和 skinId 一起被删
- `CreateUnit` 需要5个参数，少了 `face` 导致 pjass 报错、1.27 引擎加载失败

**修复**：
```bash
# 错误写法（漏掉 face）
sed 's/BlzCreateUnitWithSkin(\([^,]*\),\([^,]*\),\([^,]*\),\([^,]*\),[^)]*)/CreateUnit(\1,\2,\3,\4)/g'

# 正确写法（保留 face）
sed 's/BlzCreateUnitWithSkin(\([^,]*\),\([^,]*\),\([^,]*\),\([^,]*\),\([^,]*\),[^)]*)/CreateUnit(\1,\2,\3,\4,\5)/g'
```

---

## 坑 2：repack 降级后地图进大厅看不到玩家

**现象**：地图能进大厅，但看不到玩家槽，无法选种族。

**排查过程（二分）**：
- w3i 降级 → OK
- war3map.doo 降级 → OK
- warmap.doo + units.doo → OK
- wts/w3a/w3u/w3r/w3s → OK
- war3map.wtg → OK
- **war3map.j → 失败** ← 元凶

**根因**：即坑1，`BlzCreateUnitWithSkin` sed 正则漏掉 `face` 参数。

**教训**：以后怀疑降级问题，**先用 pjass 检查 .j**，不要上来就二分文件。

---

## 坑 3：reforged-only 文件 `Scripts\` 目录未删除

**现象**：1.27 引擎加载异常（`Scripts\Blizzard.j`、`Scripts\common.ai` 等是 reforged-only）。

**修复**：降级时删除这些文件：
```bash
rm -f "$DG_DIR/conversation.json"
rm -f "$DG_DIR/war3mapSkin.w3a" "$DG_DIR/war3mapSkin.w3h" "$DG_DIR/war3mapSkin.w3q" "$DG_DIR/war3mapSkin.w3u"
find "$DG_DIR" -maxdepth 1 -name "Scripts" -type d -exec rm -rf {} + 2>/dev/null || true
```

---

## 坑 4：w3a/w3h/w3q/w3u 对象数据未降级 → CustomObjectField 崩溃

**现象**：进入游戏后崩溃，报 `Object: CustomObjectField`，内存访问越界。

**根因**：`war3map.w3a`（技能）、`war3map.w3u`（单位）等对象数据文件是 v3 格式（reforged），1.27 只认 v2，字段偏移错位导致崩溃。

**修复**：降级流水线里必须对这4个文件调用 `w3_objdata_downgrade.py`：
```bash
for _ext in w3a w3h w3q w3u; do
    [ -f "$DG_DIR/war3map.$_ext" ] && python3 "$W3OBJ_DG" "$DG_DIR/war3map.$_ext" "$DG_DIR/war3map.$_ext.tmp" \
        && mv "$DG_DIR/war3map.$_ext.tmp" "$DG_DIR/war3map.$_ext"
done
```

---

## 坑 5：不同底座图的 AI dispatch 函数名不同导致 stomp hook 失败

**现象**：build 日志里没有 `hooked stomp` 输出，TC 践踏未注入。

**根因**：`inject_tc_stomp_salvo.py` 的 stomp 正则期望 `GetEnumUnit()` 形式，但某些底座图用 `GetAttackedUnitBJ()` 形式。

**修复**：新增 pattern3 匹配 `GetAttackedUnitBJ()` 形式：
```python
pattern3 = re.compile(
    r'function (Trig_Computer\d+Combat_AI_Func\d+A) takes nothing returns nothing'
    + re.escape(nl)
    + r'(\s*call IssueImmediateOrderBJ\(\s*GetAttackedUnitBJ\(\),\s*"stomp"\s*\))'
    + re.escape(nl)
    + r'endfunction'
)
```

**教训**：换底座图后必须检查 build 日志里 `hooked stomp` 是否出现。

---

## 坑 6：guard 注入只覆盖 Computer2，漏掉 Computer1

**现象**：某战役配置下（如底座图 Player(0) 为 AI），第一关 AI 冷却后不出兵。

**根因**：`inject_ai_creep_control.py` 只 patch 了 `Computer2Combat_AI_Actions`，漏掉 `Computer1Combat_AI_Actions`。

**修复**：两个函数都要 patch。

---

## 坑 7：Round1Mode 跨局不重置导致 HVU 第一关 AI 冻结

**现象**：HVU 第一关冷却时间到了但 AI 不出兵、不攻击。

**根因**：guard 条件是 `CreepMode >= 1 or Round1Mode == 1`。`Round1Mode` 是围杀模式开关，围杀激活时阻塞 Combat AI 是**正确行为**（防止 attack 命令打乱围杀队形）。但 Round1Mode 跨局不重置，上一局用了 `-surround` 后，下一局第一关 Round1Mode 仍然是 1，导致 Combat AI 永久被封、CreepControl 没野怪可打，AI 彻底瘫痪。

**修复**：guard 条件**保持不变**（两个条件都需要），只在 `// Variable Reset` 块里注入5行重置：
```jass
set udg_aiml_Round1Mode = 0
set udg_aiml_CreepMode = 0
set udg_aiml_SurroundStillTicks = 0
set udg_aiml_SurroundAttacking = false
set udg_aiml_SurroundTarget = null
```

**注意**：`Round1Mode == 1` 在 guard 里是必须的，不能去掉。

---

## 坑 8：`udg_aiml_DebugMode` 初始值被临时改为 true 忘记改回

**现象**：出的图默认开启 debug 打印，和 V39.06 行为不一致。

**修复**：`inject_tc_stomp_salvo.py` 里 `udg_aiml_DebugMode = false` 是正式出包的默认值，临时改为 true 测试后必须改回。

---

## 坑 9：injection guard 用调用处误触发，应检测函数定义

**现象**：某个功能被 skip，日志显示已注入但实际没有。

**根因**：guard 检测字符串如 `"Trig_AIML_SurroundTick"` 会匹配到调用处，应检测 `"function Trig_AIML_SurroundTick"` 确认函数定义。

---

## 降级完整流水线（正确顺序）

```
1. stormtool extract reforged.w3x → tmpdir/
2. 删除 reforged-only 文件（conversation.json / war3mapSkin.* / Scripts/）
3. doo_downgrade.py war3map.doo
4. units_doo_downgrade.py war3mapUnits.doo
5. w3i_downgrade.py war3map.w3i
6. w3_objdata_downgrade.py war3map.w3a/w3h/w3q/w3u （必须！否则 CustomObjectField 崩溃）
7. sed BlzCreateUnitWithSkin → CreateUnit（保留5个参数！）
8. w3e_downgrade.py war3map.w3e（v12→v11，新底座必须！）
9. inject AIML
10. repack tmpdir/ hm3w_header.bin output.w3x
```

### 降级步骤文件-工具对照表

| 文件 | 工具 | 备注 |
|---|---|---|
| `war3map.doo` | `doo_downgrade.py` | 装饰物格式 |
| `war3mapUnits.doo` | `units_doo_downgrade.py` | 单位放置 |
| `war3map.w3i` | `w3i_downgrade.py` | 地图信息 |
| `war3map.w3a/h/q/u` | `w3_objdata_downgrade.py` | 对象数据 |
| `war3map.w3e` | `w3e_downgrade.py` | 地形（v12→v11，2026-06 补加） |
| `war3map.j` | `sed` BlzCreateUnitWithSkin 替换 | JASS 兼容 |
| `conversation.json` | 直接删除 | Reforged-only |
| `war3mapSkin.*` | 直接删除 | Reforged-only |

## 快速诊断清单

| 现象 | 先查这里 |
|---|---|
| 进大厅看不到玩家 | pjass 检查 .j，看 `CreateUnit` 参数数量 |
| CustomObjectField 崩溃 | w3a/w3h/w3q/w3u 有没有降级 |
| hooked stomp 没输出 | stomp 函数用的是 GetEnumUnit 还是 GetAttackedUnitBJ |
| 某关 AI 冻结不动 | guard 条件是否包含了 Round1Mode；Variable Reset 是否重置了所有状态 |
| debug 打印异常多/少 | DebugMode 默认值是否为 false |
| 功能 skip 日志但实际没注入 | guard 检测是否用了 `function` 前缀 |


---

## 坑 10：war3map.w3e v12 → v11 降级缺失

**发现时间**：2026-06-06

**现象**：新底座地图通过流水线出包后，在 WC3 1.27 中加载时报"**无效的地图文件**"，无法进入游戏。

**根因**：

Reforged 客户端（新版本）导出的地图，`war3map.w3e`（地形文件）使用 **v12 格式**（每个 cell 8 字节）。WC3 1.27 只认识 **v11 格式**（每个 cell 7 字节）。

旧底座的 `w3e` 碰巧是 v11（出自 1.27 时代的地图编辑器），所以流水线从未需要降级它，bug 一直隐藏。新底座用 Reforged 编辑器重置后变成了 v12，问题暴露。

| | 旧底座 | 新底座（2026-06 更新）|
|---|---|---|
| w3e 版本 | v11（0x0B）| v12（0x0C）|
| w3e 大小 | 87,660 bytes | 100,173 bytes |
| 降级后大小 | — | 87,660 bytes |

**修复**：

在流水线降级步骤末尾补上 `w3e_downgrade.py`：

```bash
[ -f "$DG_DIR/war3map.w3e" ] \
    && python3 "$W3E_DG" "$DG_DIR/war3map.w3e" "$DG_DIR/war3map.w3e.tmp" \
    && mv "$DG_DIR/war3map.w3e.tmp" "$DG_DIR/war3map.w3e"
```

`w3e_downgrade.py` 已有 v11 检测，若输入已是 v11 则直接 copy，不会重复处理。

**对应 commit**：`48a3702`

---

## 坑 11：war3map.j 体积超限（脚本内存 crash）

**发现时间**：2026-06-06

**现象**：地图能加载但进游戏后立即 crash，WinError 提示内存不能 read。

**根因**：

新底座比旧底座新增了约 28 个 Combat AI 函数（新兵种支持：`Obla`/`ucry`/`osw1`/`ucry` 等），底座本身的 `war3map.j` 就多了约 6.5KB。加上流水线注入的 AIML 代码，总体积超过 WC3 引擎对 JASS 脚本的隐性内存上限。

| 阶段 | 旧底座 | 新底座 |
|---|---|---|
| 底座原始 | 1,435,672 bytes | 1,442,119 bytes |
| 注入后（原始注入脚本）| 1,444,911 bytes ✅ | 1,451,261 bytes ❌ |
| 注入后（精简注释后）| — | 1,445,097 bytes ✅ |

**临时修复**（如需要）：

对注入脚本的 JASS 字符串块做注释精简，可节省约 7KB：
- 删除注入 JASS 里的 `//` 纯注释行
- 删除 `DisplayTextToForce` debug 输出行（**注意：会影响调试能力**）

参考 commit `6d683c6`（已 revert，按需取用）。

**当前状态**：新底座注入后 ~1,445,097 bytes，距旧底座安全线仅余 ~6KB 裕量。若未来底座继续膨胀，需重新评估。

---

## 坑 12：UnitRemoveAbility 无法破除疾风步隐身

**发现时间**：2026-06-17

**现象**：`UnitRemoveAbility(bm, 'Bwkb')` 调用后 BM 仍处于隐身状态，后续 attack 指令不生效。

**根因**：
- `UnitRemoveAbility` 移除的是**技能（ability）**，疾风步激活挂的是**buff**，两者 handle 类型不同，rawcode 猜对了也无效。
- AI 单位的 `IssueTargetOrder("attack")` 在隐身状态下不会自动破隐（人类玩家单位才会）。

**修复**：
```jass
if IsUnitInvisible(bm, enemyP) then
    call UnitRemoveBuffs(bm, true, false)  // 移除所有正面 buff，不依赖 rawcode
endif
call IssueTargetOrder(bm, "attack", target)
```

---

## 坑 13：AI 单位 attack 指令后不持续攻击（NORMAL 冷却空窗）

**发现时间**：2026-06-17

**现象**：BM 破隐后打了一下就停了，站着不动约 1s。

**根因**：
- `IssueTargetOrder("attack", target)` 是一次性指令，BM 打完一下无后续指令维持。
- 母调度（`Computer*Combat_AI_Actions`）每 1s 才接管一次，BM 处于 NORMAL 冷却（safeTicks -10→0）期间我们的 tick 只计数不下指令，形成 1s 空窗。

**修复**：NORMAL 冷却期每 3 tick（0.3s）补发一次 AttackNearest：
```jass
if ModuloInteger(safeTicks, 3) == 0 then
    call Trig_AIML_BM_AttackNearest(bm, enemyP)
endif
```

---

## 坑 14：隐身状态下 attack 远处目标会卡死 —— 必须"先靠近再攻击"（V39.21 核心突破）

**发现时间**：2026-06-17

**现象**：剑圣释放疾风步后，对残血英雄下 `IssueTargetOrder(bm, "attack", target)`（即使先 `UnitRemoveBuffs` 破隐），BM 仍然站着不动 / 原地转圈，根本不攻击。前后试了 N 个版本（EVADE 状态机、HUNT 状态机、各种破隐时机）都无法解决。

**根因**：
- AI 单位在**隐身状态**（或刚破隐的瞬间）对**距离较远**的目标下 `attack` 指令时，引擎寻路 + 破隐 + 攻击三件事冲突，导致指令静默失败，BM 卡住。
- 之前所有方案的错误都在于：**在远距离就尝试 attack**，把"靠近"和"攻击"耦合在一条 attack 指令里，交给引擎自己处理 —— 而引擎处理不好。

**修复（统一 DASH 突进执行器）**：把"靠近"和"攻击"彻底拆开，分两个阶段：
```jass
// 阶段1：DASH 突进 —— 只 move，绝不 attack（保持隐身穿身）
if dist >= 100.0 then
    call IssuePointOrder(bm, "move", GetUnitX(target), GetUnitY(target))
// 阶段2：到达后才破隐攻击
else
    call UnitRemoveBuffs(bm, true, false)
    call IssueTargetOrder(bm, "attack", target)
endif
```

**验证**：
```
[BM] HUNT! target=黑暗游侠 hp=291
[BM] windwalk OK -> DASH
[BM] DASH reached (d=83) STRIKE 黑暗游侠 hp=281   ← 突进到83码现身攻击，成功！
```

**经验教训**：
1. WC3 AI 单位的 attack 指令对"距离"敏感，远距离 + 隐身 = 必失败。把移动与攻击拆成两个明确阶段，用距离阈值（< 100 码）切换，是最可靠的做法。
2. `move` 指令在 AI 单位上"绝不开火"的特性（见 README 指令行为表）正好用于隐身穿身，不会打断隐身。
3. 这个"先靠近再攻击"模式可作为所有近战 AI 突进的通用执行器。


---

## 坑 15：Combat_AI 完全 DisableTrigger / guard 导致不出兵（V40 核心坑）

**发现时间**：2026-06-27

**现象**：输入 `-surround`/`-escape`/`-creep` 任何命令后，倒计时结束不出兵。只有什么都不输入时才正常。

**根因**：

`Computer1/2Combat_AI_Actions` 不仅仅是"战斗调度"——它包含**所有单位的 AI 指令**：

1. **前两行**：`GroupPointOrderLocBJ(全军, "attack", 敌方基地)` — 全军攻击
2. **英雄调度**：Hamg/Ofar/Ekee 等每个英雄的独立行为
3. **农民造塔**：`hpea` → `IssueBuildOrderByIdLocBJ('hwtw')`（人族农民造守卫塔）
4. **苦工造塔**：`opeo` → `IssueBuildOrderByIdLocBJ('owtw')`（兽族苦工造箭塔）
5. **水元素/萨满/巫医/步兵等**：各兵种的独立指令

V40 之前尝试过的方案全部失败：

| 方案 | 问题 |
|------|------|
| `if Round1Mode >= 1 then return` guard | 截断**全部** Actions → 农民不造塔 → 不出兵 |
| `DisableTrigger(Combat_AI)` | 同上，trigger 被关后没有任何指令发出 |
| `DisableTrigger` + Variable Reset 里 `EnableTrigger` | Enable 回来了，但 guard 还是在 return |
| 让 Combat_AI 运行，靠 Tick 频率覆盖 | 全军攻击指令覆盖逃跑方向，英雄往敌方基地冲 |
| Toggle 只设 Pref，Mode 延迟到 Variable Reset | 第一次输入命令当轮不生效 |

**最终方案（选择性 guard）**：

只截断前两行 `GroupPointOrderLocBJ("attack")`，保留其余所有逻辑：

```jass
function Trig_Computer1Combat_AI_Actions takes nothing returns nothing
    if not (udg_RoundNo == 1 and udg_aiml_Round1Mode >= 1) then
        call GroupPointOrderLocBJ(全队, "attack", 敌方基地)   // ← 只截这两行
        call GroupPointOrderLocBJ(起始区, "attack", 敌方基地)
    endif
    // 英雄调度、农民造塔、单位指令全部正常 ↓
    call ForGroupBJ('Hamg', Func004A)
    ...
    call ForGroupBJ('hpea', Func023A)  // 农民造塔 ← 出兵！
    ...
endfunction
```

**关键洞察**（来自 windyu 的 `-g` 线索）：

- 输入 `-g`（ready 命令）后出兵正常 → 说明 Combat_AI 运行 = 出兵
- 不输入 `-g`、只输入模式命令后不出兵 → 说明我们的 Disable/guard 截断了 Combat_AI
- **全军攻击指令是唯一跟逃跑冲突的**，其他指令（英雄调度、农民造塔）不影响逃跑

**教训**：
1. "截断 Combat_AI"不等于"截断战斗调度"，它还负责**出兵**
2. 不能用 DisableTrigger 或整体 guard，必须**精确到行级**截断
3. 模式切换必须**立即生效**（同时设 Mode + Pref），否则当轮不生效
4. POC 的 DisableTrigger 能用是因为 POC 不验证出兵，正式图必须保留出兵

---

## 坑 16：IsTerrainPathable 无法检测树木（destructable）

**发现时间**：2026-06-27（escape AI 开发过程中）

**现象**：`IsTerrainPathable(x, y, PATHING_TYPE_WALKABILITY)` 对树旁边的点返回 true（可通过），但实际有树挡路。

**根因**：

WC3 引擎中，树木是 **destructable**，不属于 terrain pathing map。`IsTerrainPathable` 只检测地形级别的不可通行（悬崖、水域、建筑地基），不检测 destructable。

`EnumDestructablesInRect` 能检测树木但太重（每秒 48 次调用导致卡顿）。

**最终方案**：

构建时从 `war3map.doo` 读取 LTlt 树坐标 → 88×43 grid array（3784 格，1240 格标记），运行时 `HasTreeAt(x, y)` O(1) 查表。

---

## 坑 17：linear scan 683 棵树超 WC3 ops 限制

**发现时间**：2026-06-27

**现象**：逃跑 AI 最初用 `ForGroup(683棵树, HasTreeAt×48次/tick)` 检测树木，导致引擎静默截断操作数，函数执行不完整。

**根因**：

WC3 引擎对每个 trigger action 有操作数上限（约 30000 ops）。线性遍历 683 点 × 48 次采样 = ~32000 ops，超出限制被静默截断。

**修复**：grid O(1) 查表替代线性遍历，每 tick ~40 次 `HasTreeAt` 调用，远低于 ops 限制。

---

## 坑 18：stuck 检测阈值 3 tick 太敏感，误触发 breakout

**发现时间**：2026-06-27

**现象**：英雄短暂路径停顿（0.5-1s 的寻路重算）就触发 breakout，全军集火错误目标。

**根因**：

stuck 阈值 3 tick（1.5s）太短，WC3 引擎寻路重算时常 1-2 tick 不移动，不是真正被围。

**修复**：阈值从 3 tick 改为 5 tick（2.5s），减少伪触发，真正被围时 2.5s 仍能可靠检测。

## 坑 19：原图 AntiCheat 每 50s 清 BM 蓝量，导致疾风步 AI 失效

**发现时间**：2026-06-28

**现象**：BM 释放疾风步后蓝量从 200+ 瞬间归零，疾风步释放频率异常高（蓝量永远不够用）。

**排查过程**：
1. 最初怀疑引擎自动释放了其他主动技能（毒蛇守卫/镜像），加了 mana debug 监控蓝量跳变
2. 第一版 debug 无效——`PrevMana1` 在 tick 开头就被覆盖，tick 结尾比对的是同一帧的值，永远检测不到跳变
3. 修正后（先比对再覆盖），抓到 `[MANA-BUG] 216->0 state=0`
4. grep 原图 `SetUnitManaPercentBJ.*0.00` → 找到 `AntiCheat_Computer1_BM` / `AntiCheat_Computer2_BM`

**根因**：
原图有两个 AntiCheat trigger：
- `Trig_AntiCheat_Computer1_BM`：每 50 秒对 Player(0) 的 Obla（BM）执行 `SetUnitManaPercentBJ(bm, 0.00)`
- `Trig_AntiCheat_Computer2_BM`：同上，对 Player(1) 的 BM

原意是防止 BM 用疾风步作弊（PvP 场景），但我们的 BM AI 恰恰靠疾风步做 EVADE/HUNT，每 50 秒清蓝直接废掉 AI。

**修复**：
在 `inject_ai_blademaster.py` 的 inject 流程中，将这两个 Actions 函数体清空：
```python
# 找到 Trig_AntiCheat_Computer{1,2}_BM_Actions 函数体
# 替换为空函数（保留声明，只清空逻辑）
```

**注意**：另外两个 `AntiCheat_Player{1,2}_LastUnit` trigger（最后单位透视，每 5s 检查对方只剩1个非建筑单位时开全图+ping 位置）**不要禁**，跟 BM 无关，保留正常功能。

**教训**：
1. **原图的"反作弊"trigger 必须逐一审查**——AI 接管了英雄行为后，任何"限制英雄"的原逻辑都可能冲突
2. **mana debug 的正确做法**：在 tick 开头**先比对上一 tick 存的值再覆盖**，而不是覆盖后再在 tick 结尾检查
3. **WC3 里蓝量跳变为 0**（不是某个技能消耗值）→ 优先查 `SetUnitManaPercentBJ` 调用

## 坑 20：科多兽吞噬 AI 的 N 个坑（V42 调试全记录）

**发现时间**：2026-06-29

### 坑 20a：IssueTargetOrder("devour") 在 AI 单位 attack 状态下返回 false

**现象**：`Trig_AIML_KodoFindTarget` 找到了目标，`IssueTargetOrder(kodo, "devour", target)` 返回 false。

**根因**：AI 单位在 `order=attack` 状态下，引擎拒绝 trigger 下发的新指令。只有空闲状态（`order=0`）时才接受。

**修复**：下发 devour 前先 `IssueImmediateOrder(kodo, "stop")`。

### 坑 20b：stop 打断了正在执行的吞噬施法，科多永远吞不到

**现象**：每个 tick 都 stop + devour，科多反复"张嘴走向目标 → 0.5s 后被 stop 打断 → 重新张嘴"循环。

**根因**：吞噬有施法过程（科多走向目标），0.5s 一次的 stop 打断了施法，Bdev buff 永远不会出现。

**修复**：不要无条件 stop。用冷却计数器或 `GetUnitCurrentOrder` 检查，只在科多空闲/攻击时才 stop + 重新下发。

### 坑 20c：Bdev buff 检测不到——自定义地图的 buff rawcode 不可靠

**现象**：`GetUnitAbilityLevel(kodo, Bdev)` 始终返回 0，即使科多已经成功吞噬。

**根因**：不确定（可能是自定义地图改了 buff ID，也可能是引擎内部 buff 对 JASS API 不可见）。

**修复**：不用 buff 检测，改用**追踪吞噬目标单位** + `IsUnitHidden(target)` 检测。被吞的单位会被引擎隐藏，这是最可靠的信号。

### 坑 20d：穴居恶魔的 rawcode 不是标准 Uspi

**现象**：科多优先吞女妖，忽略场上的穴居恶魔。

**根因**：本地图的单位 rawcode 跟标准 WC3 完全不同。穴居恶魔是 `ucry`（0x75637279）不是 `Uspi`，憎恶是 `uabo` 不是 `Uabo`。`GetUnitTypeId` 返回的是小写 rawcode。

**修复**：代码中同时匹配 `Uspi/uspi/ubsp/ucry`。调试方法：打印 `I2S(GetUnitTypeId(u))` + `GetUnitName(u)` 对照，用 hex 反推 rawcode。

### 坑 20e：引擎 AI 每秒覆盖吞噬指令——从母调度排除科多才是根因解

**现象**：科多下完 devour 走向目标，0.5-1s 后被引擎 AI 的 `GroupPointOrderLocBJ(全军, "attack")` 覆盖成攻击指令，放弃吞噬转去攻击。

**根因**：`Computer1/2Combat_AI_Actions` 每秒给**所有单位**下发 attack 指令，包括科多。我们的 0.5s tick 抢不过 1s 的母调度。

**最终修复**（windyu 的建议）：在 Combat_AI 的 `GetUnitsOfPlayerMatching` filter 里排除科多兽（`GetUnitTypeId(GetFilterUnit()) != okod`），跟先知的处理逻辑一致。引擎不再给科多发任何指令，我们的 devour AI 完全掌控科多行为。

**教训**：
1. **治本比治标好**：之前试了 stop+devour、冷却计数器、GetUnitCurrentOrder 检测……都是在跟引擎抢。从 filter 里排除科多，引擎根本不会给科多发指令，不存在抢的问题
2. **自定义地图的 rawcode 必须实测**：不能用标准 WC3 rawcode 猜，必须用 `I2S(GetUnitTypeId)` + `GetUnitName` 对照确认
3. **WC3 吞噬成功的检测**：`IsUnitHidden(target)` 比 buff 检测更可靠

## 坑 21：JASS 1.27 不支持 `%` 取模运算符——pjass 漏检，WC3 编译失败

**发现时间**：2026-07-02

**现象**：地图无法加载（种族选择界面不显示），没有任何错误提示。pjass 语法检查通过。

**排查过程**：
1. 增量二分定位：step4a（Find+赋值）OK → step4b（GetUnitX/Y + SquareRoot）OK → step4e（Atan2 + 角度归一化循环）OK → step4f（加 Cos/Sin + blockX/blockY + `udg_blk_TickCount % 3 * 2`）崩
2. 注意到 `udg_blk_Enabled = false`，Tick 函数一开始就 return，Cos/Sin 和 `%` 都不会被执行
3. 意识到问题在编译阶段（WC3 加载地图时预编译所有 JASS 代码）
4. 搜索 war3map.j 找到 `udg_blk_TickCount % 3 * 2` 这一行
5. JASS 1.24-1.27 不支持 `%` 运算符（Reforged 才加的），pjass 工具没检查出来

**根因**：

JASS 1.27（Classic WC3）的运算符集合里**没有 `%`（取模/模运算）**。pjass 作为语法检查工具对此漏检（可能是 pjass 支持 Reforged 语法），但 WC3 1.27 的内置 JASS 编译器在加载地图时遇到 `%` 字符直接报错，导致整个脚本编译失败，地图无法加载。

**关键特征**：
- pjass 语法检查**通过**（不会报错！）
- WC3 1.27 加载地图时**静默失败**（无明显错误提示，只是地图不显示在列表或种族选择不出现）
- 即使包含 `%` 的代码在运行时不会被执行（如 `if false then ... endif` 分支内），编译阶段仍然失败

**修复**：

不用 `%` 取模，改用累加+重置方式：
```jass
// 错误：JASS 1.27 不支持
if udg_blk_TickCount % 3 * 2 < 3 then

// 正确：手动实现取模
set udg_blk_SideToggle = udg_blk_SideToggle + 1
if udg_blk_SideToggle >= 3 then
    set udg_blk_SideToggle = 0
endif
if udg_blk_SideToggle < 2 then
    set offsetSign = 1.0
else
    set offsetSign = -1.0
endif
```

**补充：同类问题**：
- JASS 不支持 `;` 分号作为语句分隔符（每条语句必须独立一行）
- JASS 不支持跨行表达式（如 `BJDebugMsg("a"` + 换行 + `+ "b")`）
- 这两个问题 pjass **会报错**（Unrecognized character `;`），比 `%` 容易发现

**教训**：
1. **pjass 不能100%保证 WC3 1.27 兼容**——它可能支持 Reforged 语法特性
2. **编译阶段失败不依赖运行时路径**——即使代码永远不会执行，只要存在非法语法就编译失败
3. **WC3 1.27 可用运算符**：`+` `-` `*` `/`（算术）、`==` `!=` `<` `>` `<=` `>=`（比较）、`and` `or` `not`（逻辑）——**没有 `%`**

# AI Rules — 注入模块开发铁律

## 核心原则：改动前先看已有设计，别自己发明做法

### Round1 互斥机制（踩坑 N 次）

**规则：** 新增 Round 1 模式的 toggle 命令时：
- ✅ **只设 Round1Pref，不设 Round1Mode**
- ❌ 禁止直接修改 Round1Mode
- 原因：Round1Mode 由倒计时结束回调统一应用 (`Round1Mode = Round1Pref`)，
  提前修改会导致 Combat_AI guard 截断全军攻击 → AI 不出兵

**已有模式（抄就对了）：**
```
function Trig_AIML_SurroundToggle takes nothing returns nothing
    set udg_aiml_Round1Mode = 1   ← V42 的风格（立即生效）
    set udg_aiml_Round1Pref = 1
```

**但更稳妥的做法（V43/V40 理念）：**
```
function Trig_AIML_XxxToggle takes nothing returns nothing
    set udg_aiml_Round1Pref = N   ← 只设 Pref
    // 不要动 Round1Mode！让倒计时回调处理
```

### Combat_AI guard

- 条件：`Round1Mode >= 1` 时截断全军 attack 指令
- Combat_AI 同时负责：农民造塔、单位生产 → 不能完全禁用
- 所以 Round1Mode 的值直接影响出兵

### 构建验证清单（每次改注入脚本后必做）

1. pjass 0 errors ✅
2. 选择底座图正确：`origin-reforged/UD-decisive-optimized.w3x`（不是 base-1.27）
3. 测试：不输入任何命令 → 倒计时结束 AI 正常出兵
4. 测试：先 `-creep` → 出兵正常
5. 测试：先 `-block` 再 `-creep` → 出兵正常
6. 测试：先 `-block` → 卡位工作，然后 `-creep` → 卡位停止

### 过去踩过的坑（禁止再犯）

| # | 问题 | 根因 | 日期 |
|---|------|------|------|
| 1 | 底座图用错 base-1.27 导致缺少模块 | 忘了底座是 origin-reforged | V43 早期 |
| 2 | block 注入导致 creep 不出兵 | block toggle 直接设 Round1Mode | V43 fix |
| 3 | blockdebug 没删除 | 代码清理不完整 | V12 |

## 坑 22：TC 践踏 hook 失败的 N 种死法（2026-07-04 血泪总结）

**发现时间**：2026-07-04

**现象**：新底座图 UD-decisive-111（现 base-reforged.w3x）注入 TC 智能践踏后，TC 完全不踩地板，或者偶尔踩。调试了整整一天。

### 死法 1：清空 Func008A 函数体（V2）

**做法**：把 Func008A 函数体改为 `return`。
**结果**：Combat_AI_Actions 的 `ForGroupBJ(..., Func008A)` 调用链还在，函数进去就 return，TC 永远不会踩。
**为什么错**：破坏了调用链。正确做法是**替换函数体内容，保留函数名和调用链**。

### 死法 2：在 Actions 末尾追加 dispatch 但不删除旧调用（V1）

**做法**：在 Combat_AI_Actions 末尾追加 `ForGroupBJ(udg_Race1Player, Otch, Trig_AIML_TC_Stomp_Dispatch)`，但没有处理旧的 `Func008A` 调用。
**结果**：TC 同时走两条路径——无脑 Func008A 仍然在踩，智能 Dispatch 也在跑，两套逻辑互相干扰。
**为什么错**：追加不替换，旧的无脑逻辑仍然生效。

### 死法 3：正则替换调用时破坏函数结构（V2-V3 尝试）

**做法**：用 `src.replace(old_call, "")` 删除旧的 Func008A 调用行。
**结果**：删除后 `endfunction` 和下一个函数挤在一起，pjass 报语法错误。
**为什么错**：文本删除破坏了函数边界的换行结构。

### 正确方案（V17c，来自 Box AI inject_hero_magic.py）：

1. **不要动 Combat_AI_Actions 的调用链**
2. **用正则匹配 Func008A 的函数定义**（`function Trig_ComputerXCombat_AI_Func008A takes nothing returns nothing` → `IssueImmediateOrderBJ(GetEnumUnit(), "stomp")`）
3. **保留函数名，替换函数体**为 `call Trig_AIML_TC_Stomp_Logic(GetEnumUnit())`
4. 注入新函数 `Trig_AIML_TC_Stomp_Logic`（智能践踏判断）到 endglobals 之后

```jass
// 替换后的 Func008A：
function Trig_Computer1Combat_AI_Func008A takes nothing returns nothing
    call Trig_AIML_TC_Stomp_Logic(GetEnumUnit())
endfunction
```

### 关键原则

- **hook ≠ wipe**：替换函数体内容，不是清空函数
- **保留调用链**：Combat_AI_Actions 里的 `ForGroupBJ(..., Func008A)` 一行都不要动
- **用 raw order ID**：`IssueImmediateOrderById(tc, 852127)` 而不是 `IssueImmediateOrder(tc, "stomp")`，字符串在不同版本可能有歧义
- **底座图依赖**：必须是有 Func008A（无脑 `IssueImmediateOrderBJ(GetEnumUnit(), "stomp")`）的底座图。如果底座图没有这个函数（或被删），注入器会静默跳过，TC 不会踩

### 验证方法

build 日志必须看到：
```
[HERO-MAGIC] hooked stomp: Trig_Computer1Combat_AI_Func008A
[HERO-MAGIC] hooked stomp: Trig_Computer2Combat_AI_Func008A
```

两个都出现才算成功。缺少任何一个都是底座图不匹配或正则没命中。


## Pit 23: Invulnerability buff rawcode is Bvul (not Avul/Bivs/Bpin)

**Found**: 2026-07-11

**Symptom**: BM EXECUTE/STRIKE checks for invulnerability using standard
buff IDs (Avul, Bivs, Bpin, Bphs, Bpsd) all returned 0. Lich using Potion
of Invulnerability (pnvl item) was not detected as invulnerable, BM kept
attacking invulnerable target.

**Root cause**: This custom map uses non-standard buff rawcode for
invulnerability. Same issue as pit 20d (Crypt Fiend ucry vs standard Uspi).
The actual buff ID is **Bvul**, confirmed via per-tick diagnostic scan of
21 candidate buff IDs.

**Standard WC3 invul buff IDs that DO NOT work on this map**:
- Avul (Invulnerable ability) - NOT this map's invul pot
- Bivs (Tornado invul) - no
- Bpin (Potion of Invulnerability standard) - no
- Bphs (Phase Shift) - no
- Bpsd (Hex/Burrow) - no

**Working buff ID**:  - detected via GetUnitAbilityLevel(target, 'Bvul') > 0

**Fix**: All invulnerability checks use single Bvul ID:
- STRIKE state exit (target invul -> release to NORMAL)
- EXECUTE locked target release
- EXECUTE new trigger skip
- FindHuntTarget filter (skip invulnerable units)
- FindLowestHpHero filter (skip invulnerable heroes)

**Diagnostic method**: per-tick scan all enemy heroes for 21 candidate
buff IDs, print any non-zero. Screenshot confirmed Bvul=1 when Lich uses
invul pot.

**Lesson**: Custom maps may override standard buff rawcodes. Always verify
with runtime diagnostic, never assume standard IDs (same as pit 20d).
Additional confirmed non-standard rawcodes on this map: Bspl (Spirit Link,
standard Bslf, see pit 28), Bcrs (Curse, standard Bcur, see pit 28).


## 坑 24：底座图用错 —— UD-decisive-multiplayer.w3x vs UD-decisive-base.w3x

**发现时间**：2026-07-16

**现象**：V51 起出包后灵魂行者(ospw)脱队、部分 AI 行为异常。

**根因**：

V51 commit `994b681` 起误用了 `UD-decisive-multiplayer.w3x` 作为底座图（该图另有用途，结构与正式底座不同）。V42-V49 一直使用的是 `UD-decisive-base.w3x`。

| 底座图 | 大小 | 用途 | 正确？ |
|---|---|---|---|
| `UD-decisive-base.w3x` | 523K | 正式底座图，V42-V49 一直使用 | ✅ |
| `UD-decisive-multiplayer.w3x` | 524K | 另有用途（多人测试？） | ❌ |
| `base-reforged.w3x` | 523K | 早期底座 | ❌ |

**修复**：构建脚本参数改回 `UD-decisive-base.w3x`。

**教训**：底座图不能随意更换。更换底座图后必须全量回归测试（出兵、英雄调度、齐射、BM、Kodo、SW 全部验证）。

---

## 坑 25：Ofar 在 Salvo RANGED_HEROES 白名单中打断闪电链施法

**发现时间**：2026-07-16

**现象**：先知(Ofar)突然不放闪电链。

**根因**：

`Ofar` 在 Salvo 的 `RANGED_HEROES` 白名单中，Salvo 每 0.5s 对所有远程英雄下发 `IssueTargetOrder(u, "smart", focusTarget)` 指令。`smart` 指令等同于右键点击目标，会打断正在进行的施法前摇。

闪电链有施法前摇（~0.5s），恰好被 Salvo 的 0.5s tick 周期打断，永远无法释放。

**修复**：从 `RANGED_HEROES` 移除 `'Ofar'`。先知由 WC3 默认 AI 自行判断施放闪电链。

**同类问题**：`'Oshd'`（暗影猎手）此前已因同样原因从 `RANGED_HEROES` 移除。所有有主动施法能力的英雄都不应在 Salvo 白名单中。

**教训**：Salvo 的 `smart` 指令对施法型英雄是致命的。白名单只应包含纯远程输出单位（猎头者、风骑士等），不应包含任何有主动技能的英雄。

---

## 坑 26：BM 跟随 Salvo focus target 导致攻击卡顿

**发现时间**：2026-07-16

**现象**：剑圣攻击时"一卡一卡的不动"，攻击动画不断被打断。

**根因**：

V49/V50 设计了 BM-Salvo 双向跟随：
- Salvo 跟随 BM 目标（BM in DASH/STRIKE → Salvo focus = BM target）
- BM 跟随 Salvo focus target（BM NORMAL fallback → target = udg_aiml_FocusTarget1/2）

Salvo 每 0.5s 可能切换目标，BM 每 0.1s 重下 `IssueTargetOrder(bm, "attack", target)`。当 Salvo 切目标时，BM 的 attack 目标跟着变，攻击动画被重置。0.5s 的切换周期恰好打断 BM 的攻击前摇。

**修复（V51b）**：切断 BM -> Salvo 方向。BM NORMAL fallback 不再读取 `udg_aiml_FocusTarget1/2`，改为独立选目标。Salvo 仍可跟随 BM 目标（单向），数据流变为：

```
BM 独立选目标 -> udg_bm_Target1 -> Salvo 读取跟随（带 anti-kite 800 码检查）
```

**教训**：不同频率的 AI 模块之间不应做双向目标跟随。高频模块（BM 0.1s）跟随低频模块（Salvo 0.5s）的目标切换，必然导致高频侧的指令抖动。单向跟随（低频读高频）是安全的设计模式。

---

## 坑 27：灵魂行者(ospw) 在 Combat_AI 中无独立 dispatch 函数

**发现时间**：2026-07-16

**现象**：灵魂行者在 Round 1 特殊模式（卡位/围杀/逃跑）下完全脱队，原地发呆。

**根因**：

Combat_AI 的 `Computer1/2Combat_AI_Actions` 中，每个英雄类型有独立的 `ForGroupBJ` dispatch（如 Hamg -> Func004A, Ofar -> Func005A 等），但 `ospw` 没有独立 dispatch 函数。`ospw` 完全依赖军团攻击指令（`GroupPointOrderLocBJ("attack")`）来跟随大部队移动。

V40 守卫在 Round 1 `Round1Mode >= 1` 时跳过军团攻击指令 -> `ospw` 零指令 -> 原地发呆。

**修复（V51c）**：在 V40 守卫的 `endif` 之后，为 `ospw` 加一行独立的 `GroupPointOrderLocBJ` dispatch：

```jass
    // [V40] Skip army-attack in surround/escape mode
    if not (udg_RoundNo == 1 and udg_aiml_Round1Mode >= 1) then
        ...original army-attack...
    endif
    // [V51c] Spirit Walker always follows army (not guarded by V40)
    call GroupPointOrderLocBJ( GetUnitsOfPlayerAndTypeId(Player(0), 'ospw'), "attack", enemyLoc )
```

每 1s（Combat_AI timer 频率）触发一次，不受 V40 守卫限制。频率足够低，不会打断施法。

**教训**：自定义地图新增的兵种类型如果没有在 Combat_AI 的 dispatch 列表中，会完全脱离母调度。排查方法：grep `war3map.j` 中 `ForGroupBJ.*GetUnitsOfPlayerAndTypeId` 确认哪些兵种有独立 dispatch。不在列表中的兵种只靠军团攻击指令移动，V40 守卫一截断就脱队。


---

## 坑 28：灵魂链/诅咒 buff rawcode 非标准 —— Bslf→Bspl, Bcur→Bcrs

**发现时间**：2026-07-17

**现象**：

1. 灵魂行者一直释放灵魂链，即使部队已经挂上了灵魂链 buff。每 0.5s 重复施放，浪费蓝量。
2. 灵魂行者不释放驱散，即使我方单位已被敌方女妖施放了诅咒。

**根因**：

这张自定义地图修改了标准 buff rawcode：

| Buff | 标准 rawcode | 本图实际 | `GetUnitAbilityLevel` 结果 |
|------|-------------|---------|---------------------------|
| 灵魂链 (Spirit Link) | Bslf | **Bspl** | Bslf 始终返回 0 |
| 诅咒 (Curse) | Bcur | **Bcrs** | Bcur 始终返回 0 |

灵魂链检测用 `GetUnitAbilityLevel(u, 'Bslf')` 始终返回 0 → 脚本认为所有单位都没灵魂链 → 每 tick 重复施放。

诅咒检测用 `GetUnitAbilityLevel(u, 'Bcur')` 始终返回 0 → 脚本认为没有单位被诅咒 → 不触发驱散。

**诊断方法**：

在 `FindSpiritLinkTarget` / `FindDispelTarget` 中加入诊断扫描函数，遍历 20-28 个候选 buff ID，对每个我方单位调用 `GetUnitAbilityLevel(u, candidateId)`，将返回值 > 0 的 ID 打印到屏幕：

```
[SW-DIAG] 剑圣 buffs: Bspl           ← 确认灵魂链 = Bspl
[SW-DIAG2] 剑圣 DEBUFFS: Bcrs        ← 确认诅咒 = Bcrs
```

用户截图后即可确定实际 rawcode。

**修复**：

- `inject_ai_spirit_walker.py` 灵魂链检测：`Bslf` → `Bspl`
- `inject_ai_spirit_walker.py` 诅咒检测：`Bcur` → `Bcrs`
- 减速 (`Bslo`) rawcode 暂未确认，保留标准 ID，如需验证可用同样诊断方法

**教训**：

这张地图已确认 3 个非标准 buff rawcode（Bvul 无敌、Bspl 灵魂链、Bcrs 诅咒）。对自定义地图，**所有 buff 检测都应通过运行时诊断扫描验证 rawcode**，不能假设标准 ID。诊断方法：扫描候选 ID 列表，打印非零结果，用户截图确认。

已确认的本图 buff rawcode 汇总：

| Buff | 标准 | 本图 |
|------|------|------|
| 无敌 | Bvul | Bvul（碰巧一致） |
| 灵魂链 | Bslf | Bspl |
| 诅咒 | Bcur | Bcrs |
| 减速 | Bslo | 待确认 |

建议后续新建一个 `buff_rawcode_registry.py` 统一管理本图所有已确认的 buff rawcode，避免散落在各注入脚本中。
