# UD 决战操作图 — AI 注入流水线

## 一键流水线（主入口）

```bash
cd /data/ufo/Warcraft-III-/wc3-ai-pipeline/
./build_train_devcloud.sh <input.w3x> <output-prefix>
```

产出两个版本：
- `<prefix>-Reforged.w3x` — 重制版（可在重制版客户端打开）
- `<prefix>-1.27.w3x` — 1.27 兼容版（可在 1.27 整合包打开）

## 5 项注入功能 & 对应脚本

| 顺序 | 功能 | 脚本 |
|---|---|---|
| 1 | 智能 TC 战争践踏 + 远程齐射 | `inject_tc_stomp_salvo.py` |
| 2 | 集火后撤 | `inject_ai_focus_retreat.py` |
| 3 | 补刀 / 防补刀 | `inject_ai_creep_control.py` |
| 4 | 围杀 | `inject_ai_surround.py` |
| 5 | 英雄技能修复（可选） | `inject_hero_skills.py` |

## 游戏内命令

| 命令 | 效果 |
|---|---|
| `-debug` | 开启 debug 文字输出 |
| `-creep` | 第一关切换为补刀/防补刀模式（默认） |
| `-surround` | 第一关切换为围杀模式 |

## 废弃脚本说明

以下脚本**已废弃，不再使用**，保留仅供参考：

| 脚本 | 废弃原因 |
|---|---|
| `inject_aiml_v1_simple.py` | 早期原型，功能不完整 |
| `inject_aiml_v2.py` | 已重命名为 `inject_tc_stomp_salvo.py` |
| `inject_aiml_v3.py` | 包含 kite（风筝）功能，已废弃（见下）|
| `inject_aiml_kite.py` | kite 功能废弃（见下）|
| `inject_aiml_enhance.py` | 实验性增强，已被新脚本覆盖 |
| `inject_retreat_v31.py` | 残血撤退功能，已废弃（见下）|
| `inject_creep_control.py` | 已重命名为 `inject_ai_creep_control.py` |
| `inject_focus_retreat.py` | 已重命名为 `inject_ai_focus_retreat.py` |

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

## 文件结构

```
wc3-ai-pipeline/
  build_train_devcloud.sh     ← 主入口（一键出图）
  inject_tc_stomp_salvo.py    ← TC践踏 + 齐射
  inject_ai_focus_retreat.py  ← 集火后撤
  inject_ai_creep_control.py  ← 补刀 / 防补刀
  inject_ai_surround.py       ← 围杀
  inject_hero_skills.py       ← 英雄技能修复（可选）
  tools/
    stormtool                 ← MPQ 解包
    stormpatch                ← 单文件替换打包
    pjass                     ← JASS 语法检查（可选）
  refs/
    common-127-clean.j        ← pjass 用
    Blizzard.j                ← pjass 用
```
