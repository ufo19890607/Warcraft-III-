# wc3-ai-pipeline 使用说明

## 快速开始

```bash
bash build_train_devcloud.sh <input-reforged.w3x> <output-prefix>
```

**示例：**
```bash
bash build_train_devcloud.sh \
    /data/ufo/Warcraft-III/origin-reforged/UD-decisive-reforged.w3x \
    UD-decisive-V39.11
```

## 输出目录

产物自动落到脚本上级目录（`Warcraft-III/`）下：

| 版本 | 目录 | 文件名 |
|---|---|---|
| 重制版 | `converted-reforged/` | `<prefix>-Reforged.w3x` |
| 1.27 版 | `converted-1.27/` | `<prefix>-1.27.w3x` |

两个目录不存在时自动创建（`mkdir -p`）。

## 注入功能

流水线依次注入以下 AI 行为（可通过游戏内命令控制）：

| 步骤 | 功能 | 命令 |
|---|---|---|
| 2 | TC 战争践踏（智能） + 远程齐射 | — |
| 3 | 集火后撤保护 | — |
| 4 | 补刀 / 防补刀（Round 1）| `-creep` |
| 5 | 围杀（Round 1）| `-surround` |
| 6 | 英雄技能修复（Far Seer wolves）| — |

调试开关：`-debug`（游戏内聊天输入）

## war3map.j 体积安全线

WC3 引擎对脚本大小有隐性上限，超出会在加载时 crash（内存报错）。

| 底座 | 注入后体积 | 状态 |
|---|---|---|
| 旧底座（origin）| ~1,444,911 bytes | ✅ 安全 |
| 新底座（2026-06 更新）| ~1,451,261 bytes（原始）→ ~1,445,097 bytes（注入后）| ✅ 安全（余量 ~6KB）|

**注意**：如果未来底座继续膨胀导致注入后超限，可对注入脚本做注释精简（
参考 git commit `6d683c6`，已验证可节省 ~7KB，但会删掉 debug DisplayText 输出）。

## 相关文档

- `DEGRADE.md`：reforged → 1.27 降级踩坑记录
