# UD 决战操作图 — AI 注入流水线

## 一键流水线（主入口）

```bash
cd /data/ufo/Warcraft-III/wc3-ai-pipeline/
./build_train_devcloud.sh <input.w3x> <output-prefix>
```

产出两个版本：
- `<prefix>-Reforged.w3x` — 重制版（可在重制版客户端打开）
- `<prefix>-1.27.w3x` — 1.27 兼容版（可在 1.27 整合包打开）

## 8 步注入流水线 & 对应脚本

| 步骤 | 功能 | 脚本 | 游戏内命令 |
|---|---|---|---|
| 1 | 解包 war3map.j | — | — |
| 2 | 远程齐射 | `inject_salvo.py` | — |
| 3 | TC 战争践踏 + 暗影猎手（Hex/治疗波） | `inject_hero_magic.py` | — |
| 4 | 集火后撤保护 | `inject_ai_focus_retreat.py` | — |
| 5 | 补刀 / 防补刀（Round 1） | `inject_ai_creep_control.py` | `-creep` |
| 6 | 围杀（Round 1） | `inject_ai_surround.py` | `-surround` |
| 7 | 剑圣逃脱（BM Escape） | `inject_ai_blademaster.py` | — |
| 8 | Debug 开关 | `inject_debug.py` | `-debug` |
| 9 | pjass 语法检查 + 打包 | — | — |

## Timer 架构

各模块使用独立 timer，tick 间隔集中在 `ai_config.py` 配置：

| Timer | tick | 驱动模块 | 说明 |
|---|---|---|---|
| SalvoTick | 0.50s | 齐射 + 集火后撤 | 避免打断攻击前摇；HP 下降检测需 0.5s 窗口 |
| HeroMagic (SH_Init) | 0.10s | TC 践踏 + 暗影猎手 Hex/Heal | 快速响应施法时机 |
| CreepTick | 0.30s | 补刀 | 独立 timer，精度与平滑的折中 |
| SurroundTimerTick | 0.30s | 围杀 | 独立 timer，仅 Round1 + 围杀模式开启时生效 |

### 围杀静止检测参数

DK 移速 ~270 码/秒，0.3s tick 下每 tick 移动 ~81 码。

| 参数 | 值 | 含义 |
|---|---|---|
| `SURROUND_STILL_THRESHOLD` | 900.0 | 平方距离阈值（30 码），低于此视为静止 |
| `SURROUND_STILL_TICKS` | 10 | 连续静止 tick 数后切换为攻击（10 × 0.3 = 3.0s） |

> **注意**：修改 `TICK_SURROUND` 后必须同步调整 still 参数，否则会误判移动中的目标为静止。

## 英雄魔法详情

### TC 战争践踏（inject_hero_magic.py）
- 自动检测范围内敌人，智能施放践踏

### 暗影猎手 AI（inject_hero_magic.py）
- **Hex**：仅对敌方 DK 施放
- **治疗波**：己方英雄单 tick HP 下降 ≥15% 时触发

### 齐射（inject_salvo.py）
- 远程单位集火目标英雄
- `'Oshd'`（暗影猎手）已从远程英雄白名单移除


## 剑圣逃脱 AI 详情（inject_ai_blademaster.py）

### 状态机

| 状态值 | 含义 |
|---|---|
| 0 | NORMAL（正常 / 冷却中）|
| 1 | WAIT（疾风步后撤退中）|

safeTicks 一变量两用：>=0 时为 WAIT 安全计数；<0 时为 NORMAL 1s 冷却倒数（-10 步进到 0）。

### 触发流程

每 0.1s tick 检查：NORMAL + safeTicks>=0 + 本tick掉血>=maxHP×15%
- 疾风步 OK：背向 enemyHero 方向 600码退路 → 进 WAIT（waitTick=0）
- 疾风步 CD/没蓝：直接 AttackNearest，safeTicks=-10，不进 WAIT

### WAIT 状态

- tick 1-3（min-run guard，0.3s）：强制 retreat，不计 safeTick
- tick 4 起：drop<=100 则 safeTick+1，否则归零
- safeTick>=5：STRIKE — 强制破隐 + IssueTargetOrder attack 独占该 tick
- 整个 WAIT 窗口约 0.8s（0.3s 跑路 + 0.5s 计数）

### NORMAL 冷却期维持攻击

safeTicks -10→0 的 1s 内，每 3 tick（0.3s）补发一次 AttackNearest，
防止破隐后 BM 等母调度接管期间站着不动。

### 关键踩坑记录

| 问题 | 原因 | 解法 |
|---|---|---|
| safeTick>=5 但 BM 不攻击 | retreat 和 attack 同 tick 打架，引擎只执行 retreat | safeTick>=5 时不发 retreat，attack 独占该 tick |
| IssueTargetOrder attack 后 BM 不破隐 | AI 单位不会自动因 attack 指令破隐 | UnitRemoveBuffs(bm, true, false) 强制移除所有正面 buff |
| UnitRemoveAbility(Bwkb) 无效 | 移除技能而非 buff，类型不同 | 改用 UnitRemoveBuffs |
| drop 出现负数 | 回血时 prevHp < curHp | clamp: drop = max(drop, 0) |
| STRIKE 后 BM 站着不动 | NORMAL 冷却期无攻击指令，母调度 1s 间隔太长 | 冷却期每 0.3s 补发 AttackNearest |

## 关键配置文件

| 文件 | 用途 |
|---|---|
| `ai_config.py` | 全局 tick 间隔 + 围杀参数 |
| `build_train_devcloud.sh` | 8 步注入流水线入口 |

## 文件结构

```
wc3-ai-pipeline/
  ai_config.py                ← 全局 tick 间隔 + 围杀参数配置
  build_train_devcloud.sh     ← 主入口（一键出图）
  inject_salvo.py             ← 远程齐射
  inject_hero_magic.py        ← TC践踏 + 暗影猎手 Hex/治疗波
  inject_ai_focus_retreat.py  ← 集火后撤
  inject_ai_creep_control.py  ← 补刀 / 防补刀 + CreepTick独立timer
  inject_ai_surround.py       ← 围杀 + SurroundTimerTick独立timer
  inject_ai_blademaster.py    ← 剑圣逃脱 BM Escape AI
  inject_debug.py             ← Debug命令（-debug）
  inject_ai_intercept.py      ← 卡位拦截（实验性，未纳入流水线）
  deprecated/                 ← 废弃脚本（仅供参考）
  tools/
    stormtool                 ← MPQ 解包
    stormpatch                ← 单文件替换打包
    pjass                     ← JASS 语法检查
    repack                    ← 重打包工具
  refs/
    common-127-clean.j        ← pjass 用
    Blizzard.j                ← pjass 用
```

## 废弃脚本说明

以下脚本**已废弃，不再使用**，保留仅供参考：

| 脚本 | 废弃原因 |
|---|---|
| `inject_aiml_v1_simple.py` | 早期原型，功能不完整 |
| `inject_aiml_v2.py` | 已重命名为 `inject_salvo.py` |
| `inject_aiml_v3.py` | 包含 kite（风筝）功能，已废弃（见下）|
| `inject_aiml_kite.py` | kite 功能废弃（见下）|
| `inject_aiml_enhance.py` | 实验性增强，已被新脚本覆盖 |
| `inject_retreat_v31.py` | 残血撤退功能，已废弃（见下）|
| `inject_creep_control.py` | 已重命名为 `inject_ai_creep_control.py` |
| `inject_focus_retreat.py` | 已重命名为 `inject_ai_focus_retreat.py` |
| `inject_tc_stomp_salvo.py` | 已拆分为 `inject_salvo.py` + `inject_hero_magic.py` |
| `inject_hero_skills.py` | 已重命名为 `inject_debug.py`（仅保留 -debug 命令） |

### 为什么废弃 kite（风筝）？

经过多轮实测，发现 WC3 引擎对 AI 玩家（Computer）控制的单位有指令限制：

- `IssuePointOrder("attack", point)` 对 AI 单位**静默失败**——AI 内部决策机制覆盖了 trigger 的 attack-move 指令
- `IssuePointOrder("smart", point)` 对 AI 单位生效，但单位只走不打（不做 attack-move）
- V19～V25 连续 7 个版本尝试 kite，均因上述原因效果不达预期

**结论**：trigger 实现的 kite 对 AI 单位不可靠，废弃。

### 为什么废弃残血撤退？

- 残血撤退（`inject_retreat_v31.py`）同样依赖 `IssuePointOrder("attack")`，受上述 AI 单位指令限制影响
- 撤退时单位停止输出，训练效果反而下降
- windyu 明确决定：不要单体走位，专注集火和围杀

## 技术注意事项

### JASS 1.27 兼容性雷区

| ❌ 重制版写法 | ✅ 1.27 兼容写法 |
|---|---|
| `BlzCreateUnitWithSkin(...)` | `CreateUnit(...)` |
| `1.0e18`（科学计数法） | `999999999.0` |
| `IsUnitInvulnerable(u)` | 1.27 无此 native，删除 |
| `BlzXxx*` 系列 | 1.27 全部没有 |

### WC3 AI 单位指令行为差异

| 指令 | 人类玩家单位 | AI（Computer）单位 |
|---|---|---|
| `IssuePointOrder("smart", p)` | move-only | ✅ 生效，路过敌人自动反击 |
| `IssuePointOrder("attack", p)` | attack-move | ❌ 静默失败 |
| `IssuePointOrder("move", p)` | 纯走 | ✅ 生效，绝不开火 |
| `IssueTargetOrder("attack", u)` | 攻击目标 | ✅ 生效 |

### 母调度干扰

原图 `Computer1/2Combat_AI_Actions` 每秒执行一次 `GroupPointOrderLocBJ(全军, "attack", 随机目标)`，会覆盖 trigger 下发的其他指令。各注入脚本均在 Round 1 / 围杀模式下对母调度加了 early return 保护。

## war3map.j 体积安全线

WC3 引擎对脚本大小有隐性上限，超出会在加载时 crash（内存报错）。

| 底座 | 注入后体积 | 状态 |
|---|---|---|
| 旧底座（origin） | ~1,444,911 bytes | ✅ 安全 |
| 新底座（2026-06 更新） | ~1,451,261 bytes（原始）→ ~1,445,097 bytes（注入后） | ✅ 安全（余量 ~6KB） |

**注意**：如果未来底座继续膨胀导致注入后超限，可对注入脚本做注释精简（参考 git commit `6d683c6`，已验证可节省 ~7KB，但会删掉 debug DisplayText 输出）。

## 出包文件名规范

- **不要带中文**，只用 ASCII（英文 + 数字 + - + _）
- **文件名要尽量短**：微信传文件时会在文件名后自动追加一串随机字符串（如 `---c7ba627d-f27d-4f95-9659`），导致 1.27 客户端在选图界面找不到地图
  - ✅ `UD-V39-Test.w3x`
  - ✅ `UD-decisive-V39-NewBase.w3x`
  - ❌ `UD-decisive-V39.13-NewBase-Test2-1.27.w3x`（叠加多个长后缀）
- 收到包后选图看不到，第一件事检查文件名是否被微信改长了，把随机串删掉即可

## 相关文档

- `DEGRADE.md`：reforged → 1.27 降级踩坑记录
