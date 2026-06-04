# UD 决战操作图 AI 触发器诊断报告

> 基于原始 UD 操作训练图 `war3map.j` 分析
> 初稿：2026-05-30 | 最后更新：2026-06-03

---

## 原始图问题汇总

### Bug #1：TC 战争践踏永远不生效（已修复）

**位置**：`Trig_Computer1Combat_AI_Func019A`

```jass
// 原始代码（错误）
call IssueImmediateOrderBJ(GetAttacker(), "stomp")
```

**问题**：
1. `GetAttacker()` 在 `ForGroupBJ` 上下文里返回 null
2. `"stomp"` 不是有效 order，正确是 `"warstomp"`

**结果**：TC 战争践踏完全靠引擎默认 AI（只在被打到时触发），效果极差

**修复**：`inject_tc_stomp_salvo.py` — 改为判断周围敌方数量 + 英雄距离后主动释放

---

### 设计意图（非 bug，请勿修改）

以下行为**看起来异常，实为作者故意设计**：

- **DK / 远程打中立敌对生物** — 模拟前期补刀训练，故意的
- **TC 无脑战争践踏** — windyu 用蓝量道具堆出来的近似方案，`Computer2 Func021A` 的 GetEnumUnit 写法正常生效
- **第一关兵种配置**  — 专门为训练场景裁剪，不是"漏配"

---

## 功能演进记录

### 已废弃功能

#### Kite（风筝）— V19～V25，共 7 个版本，最终废弃

**尝试方案**：`IssuePointOrder("attack", retreatPoint)` 实现边退边打

**失败原因**：WC3 引擎对 AI 玩家（Computer）控制的单位，`"attack"` 指令静默失败——AI 内部每秒重发的目标决策覆盖了 trigger 指令。V22 debug 日志确认：退路点计算正确，但单位完全不动。

**教训**：AI 单位只响应 `"smart"` 和 `"move"` 点指令，以及 `IssueTargetOrder("attack", unit)` 目标指令。不能用点指令做 attack-move。

#### 残血撤退 — 废弃

**原因**：
1. 依赖 `"attack"` 指令，受同样限制
2. 撤退时单位停止输出，训练效果下降
3. windyu 明确决定：不要单体走位，专注集火和围杀

#### 走位（per-unit kite）— 废弃

同 kite，AI 单位指令限制导致无效。

---

## 当前注入功能架构（V39）

```
SalvoTick（每 0.5 秒）
├── Round 1
│   ├── Round1Mode == 1（-surround）→ SurroundTick
│   │   ├── 兵力 < 8 → fallback CreepControlForPlayer
│   │   ├── 目标静止 >= 6 tick → SurroundAttacking = true → 全军 attack
│   │   ├── Phase 2（四象限包围）→ 全军 move 到目标中心
│   │   └── Phase 1 → 全军 move 到目标对侧（穿越包围）
│   └── Round1Mode == 0（-creep，默认）→ CreepControlForPlayer
│       ├── 野怪 HP < 120 → 全军 attack（水元素除外）
│       ├── 野怪 HP 120-200，DK > 1600 → 全军 attack
│       └── 野怪 HP 120-200，DK <= 1600 → 近战围住，英雄+水元素自由
└── Round 2+
    ├── FocusRetreatForPlayer（集火后撤）
    └── SalvoForPlayer（齐射）

Computer1/2Combat_AI_Actions（每 1 秒）
├── Round 1 + 任意模式激活 → early return（不干扰 trigger）
└── Round 2+ → 正常执行
```

---

## 关键全局变量

| 变量 | 用途 |
|---|---|
| `udg_aiml_DebugMode` | debug 文字输出总开关（`-debug`）|
| `udg_aiml_Round1Mode` | 0=补刀，1=围杀（`-creep` / `-surround`）|
| `udg_aiml_CreepMode` | 补刀系统状态（0=idle，1=approach，3=all-in）|
| `udg_aiml_CreepTarget` | 当前补刀目标野怪 |
| `udg_aiml_SurroundTarget` | 当前围杀目标 |
| `udg_aiml_SurroundStillTicks` | 目标静止计数 |
| `udg_aiml_SurroundAttacking` | true = 目标被卡死，改为 attack |
