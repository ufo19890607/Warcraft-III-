#!/usr/bin/env python3
"""
inject_ai_body_block.py V1 — 卡位 AI（Body Blocking）

基于 Happy 选手 DK 卡 DH 的第一视角操作分析设计：
  - 卡位单位站在被卡单位前方偏侧位置
  - 沿被卡单位行进方向同向移动 + 小幅横移（S形）
  - 被挤过后立刻回到前方路径继续卡
  - 走走停停节奏（~0.15s tick）
  - 用 GetUnitFacing 实时感知被卡单位方向（零延迟）

简化场景：仅当卡位单位在被卡单位前方时才卡位，后方不卡。

算法：
  每 TICK (0.15s) 执行：
  1. 找卡位英雄（AI方）和被卡英雄（敌方）
  2. 用 GetUnitFacing(target) 获取朝向 = 行进方向
  3. 判断 blocker 是否在 target 前方扇形（±60°）内
  4. 前方 → 卡位：
     a. 卡位点 = target位置 + facing方向 × BLOCK_DIST + 偏侧(±SIDE_OFFSET，交替)
     b. blocker move 到卡位点
     c. 每N个tick切换偏侧方向（模拟S形横移）
  5. 后方/侧方 → 不卡位，blocker做正常行为

聊天命令：
  -block       开启卡位模式
  -noblock     关闭卡位模式
  -blockdebug  开启卡位调试信息

全局变量（新增）：
  udg_blk_Enabled       boolean  卡位开关
  udg_blk_Target        unit     被卡目标
  udg_blk_Blocker       unit     卡位英雄
  udg_blk_SideToggle    integer  偏侧方向切换计数器
  udg_blk_TickCount     integer  tick计数器
  udg_blk_DebugMode     boolean  卡位调试开关

Debug 信息（仅 blk_DebugMode=true 时输出）：
  [BLK] 卡位中 facing=xxx 先知在DK前方
  [BLK] 卡位点 (x, y) 偏侧=左/右
  [BLK] 先知在DK后方/侧方，不卡位
"""

import sys
import math

# ---- Configuration (matches ai_config.py) ----
TICK_INTERVAL      = 0.15    # tick 间隔（秒）
BLOCK_DIST         = 40.0    # 卡位点在target前方多远（码）
SIDE_OFFSET        = 25.0    # 偏侧距离（码）
FRONT_CONE_DEG     = 60.0    # 前方扇形角度（±60°）
SIDE_SWITCH_TICKS  = 3       # 每N个tick切换偏侧方向（0.15*3=0.45s）
FRONT_CONE_RAD     = math.radians(FRONT_CONE_DEG)


def main():
    if len(sys.argv) < 2:
        print("Usage: inject_ai_body_block.py <war3map.j>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    nl = "\r\n" if "\r\n" in src else "\n"

    # ---- Guard ----
    if "function Trig_BLK_Tick" in src:
        print("[BLK] Already injected, skipping.")
        return

    # ============================================================
    # 1) Globals — before endglobals
    # ============================================================
    BLK_GLOBALS = (
        "    // --- body block globals ---" + nl +
        "    boolean udg_blk_Enabled    = false" + nl +
        "    unit    udg_blk_Target     = null" + nl +
        "    unit    udg_blk_Blocker    = null" + nl +
        "    integer udg_blk_SideToggle = 0" + nl +
        "    integer udg_blk_TickCount  = 0" + nl +
        "    boolean udg_blk_DebugMode  = false" + nl
    )

    end_globals = src.find("endglobals")
    if end_globals == -1:
        print("ERROR: endglobals not found")
        sys.exit(1)
    src = src[:end_globals] + BLK_GLOBALS + src[end_globals:]
    print("[BLK] Inserted globals.")

    # ============================================================
    # 2) JASS functions — insert before "function InitCustomTriggers"
    # ============================================================
    BLK_FUNCTIONS = (
        nl +
        "//============================================================" + nl +
        "// BODY BLOCK AI  (inject_ai_body_block.py V1)" + nl +
        "//============================================================" + nl +
        nl +

        "// Find blocker hero: AI side (Race1Player)" + nl +
        "function Trig_BLK_FindBlocker takes nothing returns unit" + nl +
        "    local group g = CreateGroup()" + nl +
        "    local unit u" + nl +
        "    local unit best = null" + nl +
        "    call GroupEnumUnitsOfPlayer(g, udg_Race1Player, null)" + nl +
        "    loop" + nl +
        "        set u = FirstOfGroup(g)" + nl +
        "        exitwhen u == null" + nl +
        "        call GroupRemoveUnit(g, u)" + nl +
        "        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitType(u, UNIT_TYPE_DEAD) then" + nl +
        "            set best = u" + nl +
        "        endif" + nl +
        "    endloop" + nl +
        "    call DestroyGroup(g)" + nl +
        "    return best" + nl +
        "endfunction" + nl +
        nl +

        "// Find target hero: enemy side (Race2Player)" + nl +
        "function Trig_BLK_FindTarget takes nothing returns unit" + nl +
        "    local group g = CreateGroup()" + nl +
        "    local unit u" + nl +
        "    local unit best = null" + nl +
        "    call GroupEnumUnitsOfPlayer(g, udg_Race2Player, null)" + nl +
        "    loop" + nl +
        "        set u = FirstOfGroup(g)" + nl +
        "        exitwhen u == null" + nl +
        "        call GroupRemoveUnit(g, u)" + nl +
        "        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitType(u, UNIT_TYPE_DEAD) then" + nl +
        "            set best = u" + nl +
        "        endif" + nl +
        "    endloop" + nl +
        "    call DestroyGroup(g)" + nl +
        "    return best" + nl +
        "endfunction" + nl +
        nl +

        "// Main tick function" + nl +
        "function Trig_BLK_Tick takes nothing returns nothing" + nl +
        "    local unit blocker" + nl +
        "    local unit target" + nl +
        "    local real bx" + nl +
        "    local real by" + nl +
        "    local real tx" + nl +
        "    local real ty" + nl +
        "    local real facing" + nl +
        "    local real dx" + nl +
        "    local real dy" + nl +
        "    local real dist" + nl +
        "    local real angleToBlocker" + nl +
        "    local real angleDiff" + nl +
        "    local real blockX" + nl +
        "    local real blockY" + nl +
        "    local real sideAngle" + nl +
        "    local real offsetSign" + nl +
        "    local boolean inFront" + nl +
        nl +
        "    if not udg_blk_Enabled then" + nl +
        "        return" + nl +
        "    endif" + nl +
        nl +
        "    set blocker = Trig_BLK_FindBlocker()" + nl +
        "    set target  = Trig_BLK_FindTarget()" + nl +
        nl +
        "    if blocker == null or target == null then" + nl +
        "        if udg_blk_DebugMode then" + nl +
        "            call BJDebugMsg(\"[BLK] no blocker/target\")" + nl +
        "        endif" + nl +
        "        return" + nl +
        "    endif" + nl +
        nl +
        "    set udg_blk_Blocker = blocker" + nl +
        "    set udg_blk_Target  = target" + nl +
        nl +
        "    set bx = GetUnitX(blocker)" + nl +
        "    set by = GetUnitY(blocker)" + nl +
        "    set tx = GetUnitX(target)" + nl +
        "    set ty = GetUnitY(target)" + nl +
        nl +
        "    // target facing = movement direction" + nl +
        "    set facing = GetUnitFacing(target) * bj_DEGTORAD" + nl +
        nl +
        "    // Is blocker in target's front cone?" + nl +
        "    set dx = bx - tx" + nl +
        "    set dy = by - ty" + nl +
        "    set dist = SquareRoot(dx * dx + dy * dy)" + nl +
        nl +
        "    if dist < 1.0 then" + nl +
        "        set inFront = true" + nl +
        "        set angleDiff = 0.0" + nl +
        "    else" + nl +
        "        set angleToBlocker = Atan2(dy, dx)" + nl +
        "        set angleDiff = angleToBlocker - facing" + nl +
        "        loop" + nl +
        f"            exitwhen angleDiff >= -{math.pi:.6f}" + nl +
        f"            set angleDiff = angleDiff + 2.0 * {math.pi:.6f}" + nl +
        "        endloop" + nl +
        "        loop" + nl +
        f"            exitwhen angleDiff <= {math.pi:.6f}" + nl +
        f"            set angleDiff = angleDiff - 2.0 * {math.pi:.6f}" + nl +
        "        endloop" + nl +
        f"        set inFront = (angleDiff >= -{FRONT_CONE_RAD:.6f} and angleDiff <= {FRONT_CONE_RAD:.6f})" + nl +
        "    endif" + nl +
        nl +
        "    set udg_blk_TickCount = udg_blk_TickCount + 1" + nl +
        nl +
        "    if inFront then" + nl +
        "        // ===== FRONT → block =====" + nl +
        f"        if udg_blk_TickCount % {SIDE_SWITCH_TICKS} * 2 < {SIDE_SWITCH_TICKS} then" + nl +
        "            set offsetSign = 1.0" + nl +
        "        else" + nl +
        "            set offsetSign = -1.0" + nl +
        "        endif" + nl +
        nl +
        "        set sideAngle = facing + offsetSign * 1.5708" + nl +
        f"        set blockX = tx + Cos(facing) * {BLOCK_DIST:.1f} + Cos(sideAngle) * {SIDE_OFFSET:.1f}" + nl +
        f"        set blockY = ty + Sin(facing) * {BLOCK_DIST:.1f} + Sin(sideAngle) * {SIDE_OFFSET:.1f}" + nl +
        nl +
        "        call IssuePointOrder(blocker, \"move\", blockX, blockY)" + nl +
        nl +
        "        if udg_blk_DebugMode then" + nl +
        "            call BJDebugMsg(\"[BLK] front f=\" + R2SW(GetUnitFacing(target),1,0) + \" side=\" + I2S(R2I(offsetSign)) + \" pos=\" + R2SW(blockX,1,0) + \",\" + R2SW(blockY,1,0) + \" d=\" + R2SW(dist,1,0))" + nl +
        "        endif" + nl +
        "    else" + nl +
        "        // ===== BEHIND/SIDE → no block =====" + nl +
        "        if udg_blk_DebugMode then" + nl +
        "            call BJDebugMsg(\"[BLK] behind/side ad=\" + R2SW(angleDiff * bj_RADTODEG,1,0))" + nl +
        "        endif" + nl +
        "    endif" + nl +
        nl +
        "    set blocker = null" + nl +
        "    set target  = null" + nl +
        "endfunction" + nl +
        nl +

        "// Periodic tick via Timer (non-blocking, same as other AI modules)" + nl +
        "function Trig_BLK_TickHandler takes nothing returns nothing" + nl +
        "    call Trig_BLK_Tick()" + nl +
        "endfunction" + nl +
        nl +

        "// Chat command: -block enable" + nl +
        "function Trig_BLK_EnableAction takes nothing returns nothing" + nl +
        "    set udg_blk_Enabled = true" + nl +
        "    call BJDebugMsg(\"[BLK] body block ON\")" + nl +
        "endfunction" + nl +
        nl +

        "// Chat command: -noblock disable" + nl +
        "function Trig_BLK_DisableAction takes nothing returns nothing" + nl +
        "    set udg_blk_Enabled = false" + nl +
        "    call BJDebugMsg(\"[BLK] body block OFF\")" + nl +
        "endfunction" + nl +
        nl +

        "// Chat command: -blockdebug toggle debug" + nl +
        "function Trig_BLK_DebugAction takes nothing returns nothing" + nl +
        "    set udg_blk_DebugMode = not udg_blk_DebugMode" + nl +
        "    if udg_blk_DebugMode then" + nl +
        "        call BJDebugMsg(\"[BLK] debug ON\")" + nl +
        "    else" + nl +
        "        call BJDebugMsg(\"[BLK] debug OFF\")" + nl +
        "    endif" + nl +
        "endfunction" + nl +
        nl +

        "// Initialization" + nl +
        "function InitTrig_BLK takes nothing returns nothing" + nl +
        "    local trigger tBlock" + nl +
        "    local trigger tNoBlock" + nl +
        "    local trigger tDebug" + nl +
        nl +
        "    // Register -block chat command (both players)" + nl +
        "    set tBlock = CreateTrigger()" + nl +
        "    call TriggerRegisterPlayerChatEvent(tBlock, Player(0), \"-block\", true)" + nl +
        "    call TriggerRegisterPlayerChatEvent(tBlock, Player(1), \"-block\", true)" + nl +
        "    call TriggerAddAction(tBlock, function Trig_BLK_EnableAction)" + nl +
        nl +
        "    // Register -noblock chat command" + nl +
        "    set tNoBlock = CreateTrigger()" + nl +
        "    call TriggerRegisterPlayerChatEvent(tNoBlock, Player(0), \"-noblock\", true)" + nl +
        "    call TriggerRegisterPlayerChatEvent(tNoBlock, Player(1), \"-noblock\", true)" + nl +
        "    call TriggerAddAction(tNoBlock, function Trig_BLK_DisableAction)" + nl +
        nl +
        "    // Register -blockdebug chat command" + nl +
        "    set tDebug = CreateTrigger()" + nl +
        "    call TriggerRegisterPlayerChatEvent(tDebug, Player(0), \"-blockdebug\", true)" + nl +
        "    call TriggerRegisterPlayerChatEvent(tDebug, Player(1), \"-blockdebug\", true)" + nl +
        "    call TriggerAddAction(tDebug, function Trig_BLK_DebugAction)" + nl +
        nl +
        "    // Start block tick timer (non-blocking)" + nl +
        "    set tBlock = CreateTrigger()" + nl +
        f"    call TriggerRegisterTimerEvent(tBlock, {TICK_INTERVAL}, true)" + nl +
        "    call TriggerAddAction(tBlock, function Trig_BLK_TickHandler)" + nl +
        nl +
        f"    call BJDebugMsg(\"[BLK] init tick={TICK_INTERVAL} dist={BLOCK_DIST} side={SIDE_OFFSET}\")" + nl +
        "endfunction" + nl +
        nl
    )

    # Insert functions before "function InitCustomTriggers" (this is always in war3map.j)
    insert_marker = "function InitCustomTriggers"
    idx = src.find(insert_marker)
    if idx == -1:
        print("ERROR: 'function InitCustomTriggers' not found, cannot insert functions")
        sys.exit(1)
    src = src[:idx] + BLK_FUNCTIONS + src[idx:]
    print("[BLK] Inserted body block functions.")

    # ============================================================
    # 3) Hook InitTrig_BLK call — after SurroundInit
    # ============================================================
    surround_init_call = "call Trig_AIML_SurroundInit()"
    idx2 = src.find(surround_init_call)
    if idx2 != -1:
        eol = src.find(nl, idx2)
        call_line = "    call InitTrig_BLK()" + nl
        src = src[:eol + len(nl)] + call_line + src[eol + len(nl):]
        print("[BLK] Hooked InitTrig_BLK after SurroundInit.")
    else:
        # Fallback: after SalvoInit
        salvo_init_call = "call Trig_AIML_SalvoInit()"
        idx3 = src.find(salvo_init_call)
        if idx3 != -1:
            eol = src.find(nl, idx3)
            call_line = "    call InitTrig_BLK()" + nl
            src = src[:eol + len(nl)] + call_line + src[eol + len(nl):]
            print("[BLK] Hooked InitTrig_BLK after SalvoInit.")
        else:
            # Fallback 3: after call InitBlizzard() in main()
            init_bliz_call = "call InitBlizzard(  )"
            idx4 = src.find(init_bliz_call)
            if idx4 != -1:
                eol = src.find(nl, idx4)
                call_line = "    call InitTrig_BLK()" + nl
                src = src[:eol + len(nl)] + call_line + src[eol + len(nl):]
                print("[BLK] Hooked InitTrig_BLK after InitBlizzard in main().")
            else:
                print("WARN: Could not find init hook — call InitTrig_BLK() manually in main()")

    # ============================================================
    # 4) Write back
    # ============================================================
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[BLK] Done. Written to {path}")


if __name__ == "__main__":
    main()
