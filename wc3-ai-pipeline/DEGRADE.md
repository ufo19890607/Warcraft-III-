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

## 坑 7：guard 条件包含 Round1Mode 导致 HVU 第一关 AI 冻结

**现象**：HVU 第一关冷却时间到了但 AI 不出兵、不攻击。

**根因**：guard 条件是 `CreepMode >= 1 or Round1Mode == 1`，而 `Round1Mode` 是 Surround 模式开关——跨局不重置时 Round1Mode 仍然是 1，导致 HVU 第一关母调度被永久封死，CreepControl 也没有野怪可打，AI 彻底瘫痪。

**修复**：
1. guard 条件改为只看 `CreepMode >= 1`（去掉 Round1Mode）
2. 在 `// Variable Reset` 块里注入5行重置，每关开始时清零所有 AI 状态：
```jass
set udg_aiml_Round1Mode = 0
set udg_aiml_CreepMode = 0
set udg_aiml_SurroundStillTicks = 0
set udg_aiml_SurroundAttacking = false
set udg_aiml_SurroundTarget = null
```

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
8. inject AIML
9. repack tmpdir/ hm3w_header.bin output.w3x
```

## 快速诊断清单

| 现象 | 先查这里 |
|---|---|
| 进大厅看不到玩家 | pjass 检查 .j，看 `CreateUnit` 参数数量 |
| CustomObjectField 崩溃 | w3a/w3h/w3q/w3u 有没有降级 |
| hooked stomp 没输出 | stomp 函数用的是 GetEnumUnit 还是 GetAttackedUnitBJ |
| 某关 AI 冻结不动 | guard 条件是否包含了 Round1Mode；Variable Reset 是否重置了所有状态 |
| debug 打印异常多/少 | DebugMode 默认值是否为 false |
| 功能 skip 日志但实际没注入 | guard 检测是否用了 `function` 前缀 |
