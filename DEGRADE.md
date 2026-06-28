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
