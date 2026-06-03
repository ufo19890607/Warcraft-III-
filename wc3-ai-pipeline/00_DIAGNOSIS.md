# UD 决战操作图 AI 触发器诊断报告

> 基于 `UD决战操作训练-入门与精通.w3x` 反编译后的 `war3map.j`（32653 行）分析
> 调研时间：2026-05-30
>
> ⚠️ **作者勘误（2026-05-31 凌晨与 windyu 澄清后）**：
> 下面被标记为 "bug" 的 3、4、5 号其实是 **作者的故意设计**，不是 bug：
> - **DK / 远程对中立敌对生物**：是为了模拟前期"抢中立怪"的补刀训练
> - **TC "无脑战争践踏"**：是 windyu 用蓝量道具堆出来的近似方案，而非 GetAttacker bug
>   （Computer2 Func021A 是 GetEnumUnit 写法，正常生效；Computer1 Func019A 是 GUI 默认填充）
>
> 真正还需要修的只有：
> - Bug #1: TC 战争践踏的智能化（→ 已交付 `03_smart_war_stomp.j`）
> - Bug #2: 步兵 defend 的 GetAttacker bug（待确认 windyu 是否要修）

---

## 1. 顶层架构

| 项 | 值 |
|---|---|
| AI 主触发器 | `gg_trg_Computer1Combat_AI` (P0) + `gg_trg_Computer2Combat_AI` (P1) |
| 触发频率 | **每 1.0 秒**（`TriggerRegisterTimerEventPeriodic`）|
| 启用条件 | `udg_P1Con == false`（玩家断线时停 AI）|
| 总函数数 | 3008 |
| 全局变量数 | ~280 |

每次 tick 做的事（精简版）：
```
1. 全军 attack 随机敌方非建筑单位      ← ❌ 平A的根本原因
2. 蜘蛛地刺/苏醒（仅第10关彩蛋启用）
3. 按单位类型 ID 分发：
   for each hero/caster type:
       call Func0XXA  // 释放该英雄/兵种特定技能
```

---

## 2. 关键发现：5 个真 bug + 12 个改进点

### 🔴 严重 bug（必修）

#### Bug #1: TC 战争践踏永远不生效
**位置**：`Trig_Computer1Combat_AI_Func019A`
```jass
function Trig_Computer1Combat_AI_Func019A takes nothing returns nothing
    call IssueImmediateOrderBJ(GetAttacker(), "stomp")  // ❌ 双重错误
endfunction
```
**问题**：
1. `GetAttacker()` 在 `ForGroupBJ` 上下文里**返回 null**（这函数只在"单位被攻击"事件里有效）
2. `"stomp"` 不是有效 order，TC 战争践踏的真实 order 是 `"warstomp"`

**症状**：你 README 里说"AI 必须撞到对方英雄才会放战争践踏" —— **这是因为这条触发器从未生效**，TC 释放战争践踏完全靠魔兽默认 AI（默认 AI 只在"被打到"才放）

**修复**：
```jass
function Trig_Computer1Combat_AI_Func019A takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real x = GetUnitX(u)
    local real y = GetUnitY(u)
    // 250 码内 ≥3 个敌方地面单位才放
    if CountUnitsInRangeMatching(x, y, 250.0, IsEnemyGround) >= 3 then
        call IssueImmediateOrder(u, "warstomp")
    endif
endfunction
```

#### Bug #2: 步兵防御命令也用了 GetAttacker()
**位置**：`Func012A`（hfoo = 步兵）
```jass
call IssueImmediateOrderBJ(GetAttacker(), "defend")  // ❌
```
**问题**：同 Bug #1，`GetAttacker()` 是 null。**步兵从来没自动开盾过**。

**修复**：改成 `GetEnumUnit()` 即可。

#### Bug #3: DK 死亡缠绕目标错误
**位置**：`Func036A`
```jass
call IssueTargetOrderBJ(GetEnumUnit(), "deathcoil",
    GroupPickRandomUnit(GetUnitsOfPlayerMatching(
        Player(PLAYER_NEUTRAL_AGGRESSIVE),  // ❌ 中立敌对
        ...)))
```
**问题**：`PLAYER_NEUTRAL_AGGRESSIVE` 是中立敌对玩家（野怪），不是对手玩家 1。这张图没野怪 → DK 永远找不到目标 → **DK 几乎从不放死亡缠绕**。

**修复**：改成 `Player(1)`，且把目标条件加上"血量低"过滤。

#### Bug #4: 大法师攻击目标错误（同样的中立敌对 bug）
**位置**：`Func005A`、`Func014A`（先知）、`Func015A`（小Y）、`Func016A`（萨满）、`Func027A`（弓箭手）、`Func013A`/`Func023A`/`Func031A` 等多处
**症状**：第 1 个 `attack` 命令打到中立敌对玩家身上（图里没有），实际无效。

**修复**：批量替换 `Player(PLAYER_NEUTRAL_AGGRESSIVE)` → `Player(1)`。

#### Bug #5: U009 死亡缠绕目标方错误
**位置**：`Func035A`（U009 应该是某个自定义 DK 单位）
```jass
call IssueTargetOrderBJ(GetEnumUnit(), "deathcoil",
    GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(0), ...)))  // ❌ Player(0) 是自己
```
**问题**：death coil 给"自己人"用是为了治疗友军不死族单位（合理），但**目标过滤条件 + 全 3 条都打 Player(0)** —— 结果是只能治疗，不能伤害敌人。

**修复**：3 条命令拆分：1 条治疗友方残血，2 条攻击敌方残血/虚化目标。

### 🟡 设计层"哑炮"（不算 bug 但效果差）

#### Issue #1: 全军平A的根本原因
```jass
// 主调度器第 1 行，每秒执行：
GroupPointOrderLocBJ(... "attack",
    GetUnitLoc(GroupPickRandomUnit(...)))
//                ↑ 随机选一个敌方单位作为目标点
```
**症状**：每秒 AI 全军换一个随机目标 → 你看到 AI **平A、目标飘忽、永远不集火**。

**解决方案**：
- 不是简单"选血最少"，是 **"选一个，锁住 ≥1.5 秒，除非死了再选下一个"**
- 用 `udg_aiml_FocusTarget` 全局变量保存当前集火目标
- 每秒检查：目标死了 → 重选血最低；活着 → 全军继续打它

#### Issue #2: 巫妖霜冻新星的 3 次释放是同时发出
```jass
call IssueTargetOrderBJ(... "frostnova", target1)
call IssueTargetOrderBJ(... "frostnova", target2)  // 立即覆盖上一条
call IssueTargetOrderBJ(... "frostnova", target3)  // 又覆盖
```
**症状**：3 条 order 在同一 tick 发出，**只有最后一条生效**。这是经典 GUI 触发器写法的误区。

**正解**：用条件判断"哪个目标最适合"，只发 1 条。或者用 `TriggerSleepAction(2.0)` 等技能 CD 再发下一条（但 CD 跟具体 mana 绑定，麻烦）。

#### Issue #3: TC 震荡波目标随机
```jass
// Func018A
call IssuePointOrderLocBJ(GetEnumUnit(), "shockwave", GetUnitLoc(GroupPickRandomUnit(...)))
```
**症状**：震荡波打随机一个单位的位置，根本没利用震荡波"直线穿透多个单位"的特性。

**正解**：找"最长的敌方单位连线"作为震荡波方向。算法：
1. 找敌军重心点 C
2. 选离 C 最远的敌方单位 F
3. 从 TC 位置往 F 方向放震荡波（这条线大概率穿过最多敌人）

#### Issue #4: 大法师暴风雪打错地方
```jass
// Func005A
call IssuePointOrderLocBJ(... "blizzard", GetUnitLoc(GroupPickRandomUnit(non-hero)))
```
**症状**：暴风雪打到"随机一个敌方非英雄单位"位置 —— 经常浪费在游兵身上。

**正解**：找**敌方单位密度最高的点**（K-means 或简单地找"半径 300 内单位最多的位置"）。

### 🟢 已经写得不错的设计（保留）

- **Hmkg 风暴之锤**：先打虚化单位（`UNIT_TYPE_ETHEREAL`，被霜冻新星变虚的目标），再打血量 ≤300 非召唤物（抢人头）—— **这逻辑很专业**
- **Hpal 圣光**：3 个目标条件分级，应该是"打不死族 → 救友军 → 攻击其他"的优先级
- **Oshd 暗影猎手**：对 DK 变身 → 治疗 —— **完美解 UD 双英雄起手**
- **edot 角鹰兽骑士**：旋风对 DK —— UD 杀手锏
- **Udre 恐惧魔王**：睡眠 DK 和 Lich —— 经典反 UD
- **Edem 恶魔猎手**：法力燃烧目标过滤 —— 应该用得不错

---

## 3. 单位 ID 速查表（你这张图里出现的）

| ID | 中文 | Func | 当前 AI 行为 | 改进优先级 |
|---|---|---|---|---|
| `Hamg` | 大法师 | 005A | 召水元素 + 暴风雪打随机点 | ⭐⭐⭐ 暴风雪打热点 |
| `Hblm` | 血法师 | 006A | 放逐 + 法力虹吸 | ⭐ |
| `Hmkg` | 山丘之王 | 007A | 风暴之锤 + 雷霆一击 | ⭐⭐ 雷霆一击加密度判断 |
| `Hpal` | 圣骑士 | 008A | 3 个圣光分级目标 | ⭐ |
| `hdhw` | 龙鹰 | 009A | 魔法束缚 | - |
| `hgtw` | 狮鹫 | 010A | 普攻 | - |
| `hmtm` | 飞机 | 011A | 普攻 | - |
| `hfoo` | 步兵 | 012A | ❌ defend 不生效 | 🔴 修 GetAttacker bug |
| `Ofar` | 先知 | 014A | 召狼 + 闪电链 | ⭐⭐ 闪电链找密集 |
| `ohun` | 猎头 | 015A | 普攻 | - |
| `osw1` | 小猎头 | 016A | 普攻 | - |
| `Oshd` | 暗影猎手 | 017A | 变 DK + 治疗波 | ✅ 保留 |
| `Otch` | **牛头人酋长** | 018A+019A | 震荡波 + ❌ stomp 不生效 | 🔴🔴 你最关心的 |
| `orai` | 狼骑 | 020A | 诱捕 | ⭐ |
| `otbr` | 自爆蝙蝠 | 021A | 自爆 | - |
| `oshm` | 萨满 | 022A | 嗜血 | ⭐ 加目标过滤 |
| `Nngs` | 娜迦海妖 | 024A | 寒冰箭头 | - |
| `Edem` | 恶魔猎手 | 025A | 法力燃烧 | ⭐ |
| `ewsp` | 小鹿 | 026A | 自爆 | - |
| `earc` | 弓箭手 | 027A | 普攻 | - |
| `edot` | 角鹰骑士 | 028A | 旋风 DK | ✅ 保留 |
| `edoc` | 熊德 | 029A | 复苏 + 战吼 | ✅ 保留 |
| `edry` | 树妖 | 030A | 自动驱散 | ✅ 保留 |
| `N001` | 黑暗游侠（女妖？）| 032A | 沉默 + 黑箭 | ⭐ |
| `Ulic` | **巫妖** | 033A | ❌ 3 个新星同 tick | 🔴 改成单一最佳目标 |
| `Udre` | **恐惧魔王** | 034A | 睡眠 DK/Lich | ✅ 保留 |
| `U009` | （自定义 DK?）| 035A | ❌ 治疗目标错 | 🔴 |
| `Udea` | **死亡骑士** | 036A | ❌ 中立敌对 bug | 🔴🔴 |
| `Ucrl` | 地穴领主 | 037A | 召腐尸甲虫 | ✅ |
| `u005` | （蜘蛛？）| 040A | 普攻 | - |
| `uban` | 女妖（未变身）| 043A | 反魔法外壳 | ⭐ 加目标判断 |
| `Nfir` | 火焰领主 | 045A | 火元素 + 燃烧之箭 | ✅ |

---

## 4. 修改方案（兼容方案 B：不动原触发器）

### 思路：3 个新触发器 + 不动原 AI

```
┌─────────────────────────────────────────────────────┐
│ 原 gg_trg_Computer1Combat_AI （1.0 秒）              │ ← 不删，但 Action 改 1 个字符
│  ├─ 改：第 1 行的 GroupPointOrderLocBJ → 改用       │
│  │      udg_aiml_FocusTarget1（如果非空）            │
│  └─ 修：5 个 bug（GetAttacker / 中立敌对）           │
└─────────────────────────────────────────────────────┘
              ↑（提供 AI 单位列表）
              │
┌─────────────────────────────────────────────────────┐
│ 新 gg_trg_AIML_FocusFire （0.5 秒）                  │
│  ├─ 重新计算"最佳集火目标"                          │
│  ├─ 写入 udg_aiml_FocusTarget1（P0 用）             │
│  └─ 写入 udg_aiml_FocusTarget2（P1 用）             │
└─────────────────────────────────────────────────────┘
              ↑（独立运行）
              │
┌─────────────────────────────────────────────────────┐
│ 新 gg_trg_AIML_HeroSkillsBoost （0.3 秒）            │
│  └─ 补强 5 个核心英雄技能（不替换原 AI 触发器）     │
│     - TC 战争践踏（密度判断）                        │
│     - Lich 霜冻新星（密集点最优）                    │
│     - Archmage 暴风雪（热点搜索）                    │
│     - DK 死亡缠绕（治疗 OR 抢人头）                  │
│     - MK 风暴之锤（残血英雄优先）                    │
└─────────────────────────────────────────────────────┘
```

### 为什么 Bug 修复必须动原触发器，不能完全外挂

5 个 bug 中有 3 个是"目标方错误"（中立敌对）+ 2 个是 `GetAttacker()` —— 这些**必须改原函数**，没法外挂。但改动量极小：
- 5 个 bug 修复 = 改 5 行代码
- 集火功能新增 = 加 1 行代码（在 Func001 前面加个 if 判断）

剩下的所有改进都做成新增触发器，对你原图的兼容性破坏 = 0。

---

## 5. 下一步交付清单

我会给你这一套：

```
scripts/wc3-ai/
├── 00_DIAGNOSIS.md                # 本报告
├── 01_BUGFIX.md                   # 5 个 bug 的精确补丁（行号 + diff）
├── 02_FOCUS_FIRE.j                # 集火 AI（约 80 行 JASS）
├── 03_HERO_SKILLS_BOOST.j         # 5 个英雄技能补强（约 200 行）
├── 04_helpers.j                   # 共享工具函数（找最近、找密集点等）
├── 05_DEPLOY_GUIDE.md             # 部署到 .w3x 的完整步骤
└── 06_DEBUG.md                    # 怎么开图调试 + 加调试输出
```

每个文件都会有：
- 复制粘贴即用的代码
- 中文注释（我注意到你 README 也用中文）
- 命名前缀 `aiml_` / `Trig_AIML_` 避免冲突
- 难度档位（普通/困难，全局开关）

---

## 总结：你的图 AI 现状打分

- **架构设计**：⭐⭐⭐⭐ 分单位类型分发的思路非常专业
- **执行细节**：⭐⭐ 5 个 bug + 多处随机化导致效果打折
- **战术深度**：⭐⭐⭐ 部分英雄（MK / Oshd / Udre）的优先级写得很懂行
- **总改进空间**：很大，**修完 bug + 加集火 + 改进 5 个核心技能，AI 能从"业余"提升到"高级业余"水平**

---
