# Reforged → 1.27 降级踩坑记录

本文件记录 `build_train_devcloud.sh` 在将 Reforged 地图降级为 1.27 兼容版时遇到的坑。

---

## war3map.w3e：v12 → v11 降级缺失

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

在流水线降级步骤（Step 3）末尾补上 `w3e_downgrade.py`：

```bash
[ -f "$DG_DIR/war3map.w3e" ] \
    && python3 "$W3E_DG" "$DG_DIR/war3map.w3e" "$DG_DIR/war3map.w3e.tmp" \
    && mv "$DG_DIR/war3map.w3e.tmp" "$DG_DIR/war3map.w3e"
```

`w3e_downgrade.py` 已有 v11 检测，若输入已是 v11 则直接 copy，不会重复处理。

**对应 commit**：`48a3702`

---

## war3map.j 体积超限（脚本内存 crash）

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

## 历史降级步骤覆盖范围

| 文件 | 工具 | 备注 |
|---|---|---|
| `war3map.doo` | `doo_downgrade.py` | 装饰物格式 |
| `war3mapUnits.doo` | `units_doo_downgrade.py` | 单位放置 |
| `war3map.w3i` | `w3i_downgrade.py` | 地图信息 |
| `war3map.w3a/h/q/u` | `w3_objdata_downgrade.py` | 对象数据 |
| `war3map.w3e` | `w3e_downgrade.py` | 地形（2026-06 补加）|
| `war3map.j` | `sed` BlzCreateUnitWithSkin 替换 | JASS 兼容 |
| `conversation.json` | 直接删除 | Reforged-only |
| `war3mapSkin.*` | 直接删除 | Reforged-only |
