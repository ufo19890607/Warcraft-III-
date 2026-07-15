# WC3 AI Pipeline — TODO (2026-07-15)

## 任务：OVU 第3关 — 倒计时选兵模式

### 需求

- UD 方 (Player 2) 开局得到一个"不死族军营"（`u00A`）
- **只给 UD 方选兵**，30 秒倒计时
- 倒计时结束：
  - UD 人口上限锁定为 **70**
  - 删除不死族军营 (`u00A`)
- 现有触发器刷兵逻辑**完全保留不动**（兵营是额外给的，用来让玩家自由调配兵力）
- 这只是个**试验**——先看"兵营自选 + 人口锁定 + 倒计时"这种模式玩起来怎么样

### 技术细节

**底座图**: `/data/ufo/Warcraft-III/base-reforged/UD-decisive-multiplayer.w3x`

**不死族军营 `u00A`**:
- 训练列表: `ushd, uabo, umtw, uban, unec, uobs, ufro, ubsp, ugho, ucry, ugar`（11 种 UD 兵种全覆盖）
- WTS STRING 321: Name, STRING 322: Ubertip

**C3Round3 触发器位置**:
- 当前在 `war3map.j` 第 6952-7180 行
- 开局 `CreateNUnitsAtLoc(1, 'u00A', udg_Race2Player, ...)` 创建军营
- 后面紧跟触发刷兵和英雄

**需要新增的逻辑**:
1. 新增全局变量（如果 `globals` 段没有足够空间，需注入到 `//JASSHelper struct globals:` 段）
   - `timer udg_C3DraftTimer`
   - `timerdialog udg_C3DraftTimerDialog`
   - `boolean udg_C3DraftEnded`（初始 false）

2. 在 `Trig_C3Round3_Actions` 末尾插入：
   - 创建倒计时 Timer + TimerDialog
   - 30 秒后回调 `Trig_C3Round3_DraftEnd`

3. 回调函数 `Trig_C3Round3_DraftEnd`:
   - `SetPlayerState(udg_Race2Player, PLAYER_STATE_RESOURCE_FOOD_CAP, 70)` — 锁人口上限
   - 找到并删除地图上所有属于 UD 方的 `u00A` 单位
   - 销毁 TimerDialog
   - 设置 `udg_C3DraftEnded = true`

### 实现路径

1. 解包 `UD-decisive-multiplayer.w3x` → 获取 `war3map.j`
2. 在 `globals` 段末尾添加 3 个新变量
3. 在 `Trig_C3Round3_Actions` 末尾插入倒计时创建代码
4. 在文件中插入 `Trig_C3Round3_DraftEnd` 函数
5. `pjass` 检查 → 无语法错误
6. `stormpatch` 替换 war3map.j → repack → 出包
7. 产出 Reforged 版 + 1.27 版

### 待确认

- [ ] Orc 方（Player 1）是否也需要类似的选兵机制？目前需求说的是"只给 UD 方"
- [ ] 人口 70 是硬上限还是当前已用人口的上限？（需求说"人口上限为 70"，理解为 UD 方人口上限 = 70）
- [ ] 30 秒倒计时是否需要屏幕显示计时器窗口（TimerDialog）？按惯例应该有
- [ ] windyu 确认后开始动手

---

## 关键文件路径

| 文件 | 路径 |
|------|------|
| 新底座图 | `/data/ufo/Warcraft-III/base-reforged/UD-decisive-multiplayer.w3x` |
| 解包 war3map.j | `/data/ufo/Warcraft-III/wc3-ai-pipeline/decompile-multiplayer/out/war3map.j` |
| pjass | `/data/ufo/Warcraft-III/wc3-ai-pipeline/tools/pjass` |
| common.j | `/data/ufo/Warcraft-III/wc3-ai-pipeline/refs/common-127-clean.j` |
| Blizzard.j | `/data/ufo/Warcraft-III/wc3-ai-pipeline/refs/Blizzard.j` |
| stormpatch | `/data/ufo/Warcraft-III/wc3-ai-pipeline/tools/stormpatch` |
| C3Round3 触发器 | `war3map.j` 第 6952-7180 行 |
