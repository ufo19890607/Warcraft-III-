# wc3-ai-pipeline 使用说明

## 快速开始

```bash
bash build_train_devcloud.sh <input-reforged.w3x> <output-prefix>
```

**示例：**
```bash
bash build_train_devcloud.sh \
    /data/ufo/Warcraft-III/origin-reforged/UD-decisive-optimized.w3x \
    UD-decisive-V39.17
```

## 输出目录

产物自动落到脚本上级目录（`Warcraft-III/`）下：

| 版本 | 目录 | 文件名 |
|---|---|---|
| 重制版 | `converted-reforged/` | `<prefix>-Reforged.w3x` |
| 1.27 版 | `converted-1.27/` | `<prefix>-1.27.w3x` |

两个目录不存在时自动创建（`mkdir -p`）。

## 流水线步骤（8 步）

| 步骤 | 脚本 | 功能 | 游戏内命令 |
|---|---|---|---|
| 1 | — | 解包 war3map.j | — |
| 2 | `inject_salvo.py` | 远程齐射 | — |
| 3 | `inject_hero_magic.py` | TC 战争践踏 + 暗影猎手（Hex/治疗波） | — |
| 4 | `inject_ai_focus_retreat.py` | 集火后撤保护 | — |
| 5 | `inject_ai_creep_control.py` | 补刀 / 防补刀（Round 1） | `-creep` |
| 6 | `inject_ai_surround.py` | 围杀（Round 1） | `-surround` |
| 7 | `inject_debug.py` | Debug 开关 | `-debug` |
| 8 | — | pjass 语法检查 + 打包 | — |

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

## 英雄魔法

### TC 战争践踏（inject_hero_magic.py）
- 自动检测范围内敌人，智能施放践踏

### 暗影猎手 AI（inject_hero_magic.py）
- **Hex**：仅对敌方 DK 施放
- **治疗波**：己方英雄单 tick HP 下降 ≥15% 时触发

### 齐射（inject_salvo.py）
- 远程单位集火目标英雄
- `'Oshd'`（暗影猎手）已从远程英雄白名单移除

## 关键配置文件

| 文件 | 用途 |
|---|---|
| `ai_config.py` | 全局 tick 间隔 + 围杀参数 |
| `build_train_devcloud.sh` | 8 步注入流水线入口 |

## war3map.j 体积安全线

WC3 引擎对脚本大小有隐性上限，超出会在加载时 crash（内存报错）。

| 底座 | 注入后体积 | 状态 |
|---|---|---|
| 旧底座（origin） | ~1,444,911 bytes | ✅ 安全 |
| 新底座（2026-06 更新） | ~1,451,261 bytes（原始）→ ~1,445,097 bytes（注入后） | ✅ 安全（余量 ~6KB） |

**注意**：如果未来底座继续膨胀导致注入后超限，可对注入脚本做注释精简（参考 git commit `6d683c6`，已验证可节省 ~7KB，但会删掉 debug DisplayText 输出）。

## 相关文档

- `DEGRADE.md`：reforged → 1.27 降级踩坑记录
