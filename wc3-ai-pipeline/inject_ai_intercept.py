#!/usr/bin/env python3
"""
inject_ai_intercept.py - 卡位拦截 AI 原型（独立测试版，不加入出包流水线）

算法概述：
  每 0.3s tick 执行一次：
  1. 用坐标差计算目标单位的移动速度向量 V = (dx, dy)
  2. 当 |V| < 速度阈值（目标近乎静止）→ 全部单位走围杀逻辑（收缩贴近目标）
  3. 当 |V| >= 阈值 → 对每个 AI 单位：
       计算该单位相对目标的位置向量 P
       点积 dot = V·P
       dot > 0 → 单位在"前方扇形"→ 发移动指令到预判点
       dot <= 0 → 单位在"后方/侧方" → 走围杀逻辑（向目标收缩）
  4. 预判点 = 目标当前位置 + V方向 * (|V| + INTERCEPT_LEAD)
       INTERCEPT_LEAD = 50（额外前置距离，单位：码）

全局变量（新增）：
  udg_icpt_PrevX / PrevY       — 上一 tick 目标坐标
  udg_icpt_Target              — 当前追踪目标
  udg_icpt_VX / VY             — 速度向量（dx/dt）
  udg_icpt_Speed               — 速度标量
  udg_icpt_MinSpeed            — 速度阈值（低于此值认为静止，切围杀）

注意：
  - 本脚本为纯原型，不引用 CreepControl / Salvo / Surround 任何逻辑
  - 围杀部分用最简单的"向目标移动"代替，不做 Phase1/2 判断
  - 仅针对 udg_Race1Player（AI 玩家），可按需扩展
"""

import sys
import re


TICK_INTERVAL    = 0.30   # tick 间隔（秒）
INTERCEPT_LEAD   = 50.0   # 额外预判前置距离（码）
MIN_SPEED        = 20.0   # 速度阈值：低于此值认为目标静止
SURROUND_RADIUS  = 800.0  # 取围杀单位的最大范围


def main():
    if len(sys.argv) < 2:
        print("Usage: inject_ai_intercept.py <war3map.j>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    nl = "\r\n" if "\r\n" in src else "\n"

    # ------------------------------------------------------------------ #
    # Guard: skip if already injected
    # ------------------------------------------------------------------ #
    if "function Trig_ICPT_Tick" in src:
        print("[ICPT] Already injected, skipping.")
        return

    # ------------------------------------------------------------------ #
    # 1) Globals
    # ------------------------------------------------------------------ #
    ICPT_GLOBALS = f"""\
    // --- intercept globals ---
    unit    udg_icpt_Target  = null
    real    udg_icpt_PrevX   = 0.0
    real    udg_icpt_PrevY   = 0.0
    real    udg_icpt_VX      = 0.0
    real    udg_icpt_VY      = 0.0
    real    udg_icpt_Speed   = 0.0
    real    udg_icpt_MinSpeed = {MIN_SPEED}"""

    # 插到 endglobals 之前
    end_globals = src.find("endglobals")
    if end_globals == -1:
        print("ERROR: endglobals not found")
        sys.exit(1)
    src = src[:end_globals] + ICPT_GLOBALS + nl + src[end_globals:]
    print("[ICPT] Inserted globals.")

    # ------------------------------------------------------------------ #
    # 2) Functions
    # ------------------------------------------------------------------ #
    ICPT_FUNCTIONS = f"""
//============================================================
// INTERCEPT AI  (inject_ai_intercept.py prototype)
//============================================================

// 找目标：优先敌方英雄，否则取最近存活单位
function Trig_ICPT_FindTarget takes nothing returns unit
    local unit  best  = null
    local real  bestD = 99999.0
    local group g
    local unit  u
    local real  cx
    local real  cy
    local real  dx
    local real  dy
    local real  d

    // 以 AI 基地为参考中心（用 Race1Player 起始位置）
    set cx = GetStartLocationX(GetPlayerStartLocation(udg_Race1Player))
    set cy = GetStartLocationY(GetPlayerStartLocation(udg_Race1Player))

    // 先找敌方英雄
    set g = GetUnitsOfPlayerMatching(udg_Race2Player, Condition(function Trig_ICPT_FilterHero))
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitType(u, UNIT_TYPE_DEAD) then
            set dx = GetUnitX(u) - cx
            set dy = GetUnitY(u) - cy
            set d  = dx*dx + dy*dy
            if d < bestD then
                set bestD = d
                set best  = u
            endif
        endif
    endloop
    call DestroyGroup(g)

    // 没有英雄则找任意存活单位
    if best == null then
        set g = GetUnitsOfPlayerMatching(udg_Race2Player, Condition(function Trig_ICPT_FilterUnit))
        loop
            set u = FirstOfGroup(g)
            exitwhen u == null
            call GroupRemoveUnit(g, u)
            if not IsUnitType(u, UNIT_TYPE_DEAD) then
                set dx = GetUnitX(u) - cx
                set dy = GetUnitY(u) - cy
                set d  = dx*dx + dy*dy
                if d < bestD then
                    set bestD = d
                    set best  = u
                endif
            endif
        endloop
        call DestroyGroup(g)
    endif

    return best
endfunction

// Filter: 英雄且存活
function Trig_ICPT_FilterHero takes nothing returns boolean
    return IsUnitType(GetFilterUnit(), UNIT_TYPE_HERO) and not IsUnitType(GetFilterUnit(), UNIT_TYPE_DEAD)
endfunction

// Filter: 存活单位（非建筑）
function Trig_ICPT_FilterUnit takes nothing returns boolean
    return not IsUnitType(GetFilterUnit(), UNIT_TYPE_DEAD) and not IsUnitType(GetFilterUnit(), UNIT_TYPE_STRUCTURE)
endfunction

// 对单个 AI 单位执行卡位或围杀指令（ForGroup 回调）
// 用全局变量传参（JASS 无法直接给 ForGroup 传参）
real    udg_icpt_TgtX   = 0.0   // 目标当前 X
real    udg_icpt_TgtY   = 0.0   // 目标当前 Y
real    udg_icpt_LeadX  = 0.0   // 预判点 X
real    udg_icpt_LeadY  = 0.0   // 预判点 Y

function Trig_ICPT_MoveUnitCB takes nothing returns nothing
    local unit u  = GetEnumUnit()
    local real px                // 单位相对目标的位置向量 X
    local real py                // 单位相对目标的位置向量 Y
    local real dot               // 点积 V·P

    if u == null or IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif

    set px  = GetUnitX(u) - udg_icpt_TgtX
    set py  = GetUnitY(u) - udg_icpt_TgtY
    set dot = udg_icpt_VX * px + udg_icpt_VY * py

    if dot > 0.0 then
        // 前方扇形 → 奔向预判点卡位
        call BJDebugMsg("[ICPT] unit " + GetUnitName(u) + " INTERCEPT -> (" + R2SW(udg_icpt_LeadX,1,1) + "," + R2SW(udg_icpt_LeadY,1,1) + ")")
        call IssuePointOrder(u, "move", udg_icpt_LeadX, udg_icpt_LeadY)
    else
        // 后方/侧方 → 围杀：直接向目标收缩
        call BJDebugMsg("[ICPT] unit " + GetUnitName(u) + " SURROUND -> target")
        call IssuePointOrder(u, "move", udg_icpt_TgtX, udg_icpt_TgtY)
    endif

    set u = null
endfunction

// 主 tick 函数
function Trig_ICPT_Tick takes nothing returns nothing
    local unit  tgt
    local real  cx
    local real  cy
    local real  nx
    local real  ny
    local real  dx
    local real  dy
    local real  spd
    local real  invSpd
    local real  leadX
    local real  leadY
    local group g

    // --- 找目标 ---
    set tgt = Trig_ICPT_FindTarget()
    if tgt == null then
        call BJDebugMsg("[ICPT] no target found")
        return
    endif
    set udg_icpt_Target = tgt

    // --- 计算速度向量（坐标差） ---
    set nx  = GetUnitX(tgt)
    set ny  = GetUnitY(tgt)
    set dx  = nx - udg_icpt_PrevX
    set dy  = ny - udg_icpt_PrevY
    set spd = SquareRoot(dx*dx + dy*dy)   // 单位：码/tick（0.3s）

    // 更新速度全局（供 CB 使用）
    set udg_icpt_Speed = spd

    if spd >= udg_icpt_MinSpeed then
        // 目标在移动 → 归一化速度向量
        set invSpd        = 1.0 / spd
        set udg_icpt_VX   = dx * invSpd
        set udg_icpt_VY   = dy * invSpd

        // 预判点 = 目标当前位置 + 方向 * (速度 + LEAD)
        set leadX = nx + udg_icpt_VX * (spd + {INTERCEPT_LEAD})
        set leadY = ny + udg_icpt_VY * (spd + {INTERCEPT_LEAD})
    else
        // 目标静止 → 全部向目标收缩，预判点设为目标本身
        set udg_icpt_VX = 0.0
        set udg_icpt_VY = 0.0
        set leadX = nx
        set leadY = ny
        call BJDebugMsg("[ICPT] target still, fallback surround")
    endif

    // 写入 CB 全局
    set udg_icpt_TgtX  = nx
    set udg_icpt_TgtY  = ny
    set udg_icpt_LeadX = leadX
    set udg_icpt_LeadY = leadY

    // 记录本 tick 坐标供下次使用
    set udg_icpt_PrevX = nx
    set udg_icpt_PrevY = ny

    // --- 对 AI 单位逐一发指令 ---
    set g = GetUnitsOfPlayerWithinRangeOfXYMatching(
        {SURROUND_RADIUS}, nx, ny, udg_Race1Player,
        Condition(function Trig_ICPT_FilterUnit))
    call ForGroupBJ(g, function Trig_ICPT_MoveUnitCB)
    call DestroyGroup(g)

    set tgt = null
    set g   = null
endfunction

// 周期性触发器入口
function Trig_ICPT_Loop takes nothing returns nothing
    loop
        call TriggerSleepAction({TICK_INTERVAL})
        call Trig_ICPT_Tick()
    endloop
endfunction

// 初始化
function InitTrig_ICPT takes nothing returns nothing
    local trigger t = CreateTrigger()
    call TriggerAddAction(t, function Trig_ICPT_Loop)
    call TriggerExecute(t)
    set t = null
    call BJDebugMsg("[ICPT] Intercept AI initialized (tick={TICK_INTERVAL}s, lead={INTERCEPT_LEAD}, minSpd={MIN_SPEED})")
endfunction

"""

    # ------------------------------------------------------------------ #
    # 3) 插入函数：在 InitBlizzard 之前
    # ------------------------------------------------------------------ #
    INSERT_MARKER = "function InitBlizzard"
    idx = src.find(INSERT_MARKER)
    if idx == -1:
        print("ERROR: 'function InitBlizzard' not found, cannot insert functions")
        sys.exit(1)
    src = src[:idx] + ICPT_FUNCTIONS + src[idx:]
    print("[ICPT] Inserted intercept functions.")

    # ------------------------------------------------------------------ #
    # 4) 在 InitBlizzard 末尾调用 InitTrig_ICPT
    # ------------------------------------------------------------------ #
    # 找 InitBlizzard 函数体结尾（第一个 endfunction 之后）
    init_bliz_idx = src.find("function InitBlizzard")
    if init_bliz_idx == -1:
        print("ERROR: InitBlizzard not found after insert")
        sys.exit(1)
    endfunc_idx = src.find("endfunction", init_bliz_idx)
    if endfunc_idx == -1:
        print("ERROR: endfunction of InitBlizzard not found")
        sys.exit(1)
    call_line = f"    call InitTrig_ICPT(){nl}"
    src = src[:endfunc_idx] + call_line + src[endfunc_idx:]
    print("[ICPT] Hooked InitTrig_ICPT into InitBlizzard.")

    # ------------------------------------------------------------------ #
    # 5) 写回文件
    # ------------------------------------------------------------------ #
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[ICPT] Done. Written to {path}")


if __name__ == "__main__":
    main()
