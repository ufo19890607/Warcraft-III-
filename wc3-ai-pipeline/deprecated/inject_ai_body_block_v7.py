#!/usr/bin/env python3
"""inject_ai_body_block.py V7-DEBUG
V7卡位逻辑不变 + 每tick直接Preload注册 + 每5tick flush + 递增文件名"""
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: <war3map.j>")
        sys.exit(1)
    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"

    if "function Trig_BLK_Tick" in src:
        print("[BLK] skip")
        return

    # globals
    g = nl.join([
        "    // --- body block globals ---",
        "    boolean udg_blk_Enabled    = false",
        "    unit    udg_blk_Target     = null",
        "    unit    udg_blk_Blocker    = null",
        "    integer udg_blk_SideToggle = 0",
        "    integer udg_blk_TickCount  = 0",
        "    boolean udg_blk_DebugMode  = false",
        "    // --- CSV log globals (DEBUG: no buffer, direct Preload) ---",
        "    integer udg_blk_LogLine    = 0",
        "    integer udg_blk_FlushCount = 0",
        "    boolean udg_blk_LogOpen    = false",
    ]) + nl
    src = src.replace("endglobals", g + "endglobals")
    print("[BLK] globals ok")

    D = 'call DisplayTimedTextToForce(GetPlayersAll(), 5.00, '

    funcs = nl + "// BODY BLOCK AI V7-DEBUG" + nl

    # FindBlocker
    funcs += "function Trig_BLK_FindBlocker takes nothing returns unit" + nl
    funcs += "    local group g = CreateGroup()" + nl
    funcs += "    local unit u" + nl
    funcs += "    local unit best = null" + nl
    funcs += "    call GroupEnumUnitsOfPlayer(g, udg_Race1Player, null)" + nl
    funcs += "    loop" + nl
    funcs += "        set u = FirstOfGroup(g)" + nl
    funcs += "        exitwhen u == null" + nl
    funcs += "        call GroupRemoveUnit(g, u)" + nl
    funcs += "        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitType(u, UNIT_TYPE_DEAD) then" + nl
    funcs += "            set best = u" + nl
    funcs += "        endif" + nl
    funcs += "    endloop" + nl
    funcs += "    call DestroyGroup(g)" + nl
    funcs += "    return best" + nl
    funcs += "endfunction" + nl + nl

    # FindTarget
    funcs += "function Trig_BLK_FindTarget takes nothing returns unit" + nl
    funcs += "    local group g = CreateGroup()" + nl
    funcs += "    local unit u" + nl
    funcs += "    local unit best = null" + nl
    funcs += "    call GroupEnumUnitsOfPlayer(g, udg_Race2Player, null)" + nl
    funcs += "    loop" + nl
    funcs += "        set u = FirstOfGroup(g)" + nl
    funcs += "        exitwhen u == null" + nl
    funcs += "        call GroupRemoveUnit(g, u)" + nl
    funcs += "        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitType(u, UNIT_TYPE_DEAD) then" + nl
    funcs += "            set best = u" + nl
    funcs += "        endif" + nl
    funcs += "    endloop" + nl
    funcs += "    call DestroyGroup(g)" + nl
    funcs += "    return best" + nl
    funcs += "endfunction" + nl + nl

    # FlushLog — 关闭当前 Preload session + 写文件，然后重新打开
    funcs += "function Trig_BLK_FlushLog takes nothing returns nothing" + nl
    funcs += "    local string fname" + nl
    funcs += '    set fname = "save\\\\blk_log\\\\data_" + I2S(udg_blk_FlushCount) + ".txt"' + nl
    funcs += "    set udg_blk_FlushCount = udg_blk_FlushCount + 1" + nl
    funcs += "    call PreloadGenEnd(fname)" + nl
    funcs += "    call PreloadGenClear()" + nl
    funcs += "    call PreloadGenStart()" + nl
    funcs += "    set udg_blk_LogLine = 0" + nl
    funcs += "endfunction" + nl + nl

    # EnableAction — 打开日志
    funcs += "function Trig_BLK_EnableAction takes nothing returns nothing" + nl
    funcs += "    set udg_blk_Enabled = true" + nl
    funcs += "    set udg_blk_FlushCount = 0" + nl
    funcs += "    set udg_blk_LogLine = 0" + nl
    funcs += "    call PreloadGenClear()" + nl
    funcs += "    call PreloadGenStart()" + nl
    funcs += "    set udg_blk_LogOpen = true" + nl
    funcs += "    " + D + '"[BLK] ON (V7-DEBUG)")' + nl
    funcs += "endfunction" + nl + nl

    # DisableAction — 最终flush
    funcs += "function Trig_BLK_DisableAction takes nothing returns nothing" + nl
    funcs += "    set udg_blk_Enabled = false" + nl
    funcs += "    call Trig_BLK_FlushLog()" + nl
    funcs += "    set udg_blk_LogOpen = false" + nl
    funcs += "    " + D + '"[BLK] OFF (files=" + I2S(udg_blk_FlushCount) + ")")' + nl
    funcs += "endfunction" + nl + nl

    # DebugAction
    funcs += "function Trig_BLK_DebugAction takes nothing returns nothing" + nl
    funcs += "    set udg_blk_DebugMode = not udg_blk_DebugMode" + nl
    funcs += "    " + D + '"[BLK] debug toggled")' + nl
    funcs += "endfunction" + nl + nl

    # Tick — V7 核心逻辑不变 + 每tick直接Preload
    funcs += "function Trig_BLK_Tick takes nothing returns nothing" + nl
    funcs += "    local unit blocker" + nl
    funcs += "    local unit target" + nl
    funcs += "    local real bx" + nl
    funcs += "    local real by" + nl
    funcs += "    local real tx" + nl
    funcs += "    local real ty" + nl
    funcs += "    local real facing" + nl
    funcs += "    local real dx" + nl
    funcs += "    local real dy" + nl
    funcs += "    local real dist" + nl
    funcs += "    local real blockDist" + nl
    funcs += "    local real blockX" + nl
    funcs += "    local real blockY" + nl
    funcs += "    local real sideAngle" + nl
    funcs += "    local real offsetSign" + nl
    funcs += "    local string csvLine" + nl
    funcs += "    if not udg_blk_Enabled then" + nl
    funcs += "        return" + nl
    funcs += "    endif" + nl
    funcs += "    set udg_blk_TickCount = udg_blk_TickCount + 1" + nl
    funcs += "    set blocker = Trig_BLK_FindBlocker()" + nl
    funcs += "    set target = Trig_BLK_FindTarget()" + nl
    funcs += "    if blocker == null or target == null then" + nl
    funcs += "        return" + nl
    funcs += "    endif" + nl
    funcs += "    set bx = GetUnitX(blocker)" + nl
    funcs += "    set by = GetUnitY(blocker)" + nl
    funcs += "    set tx = GetUnitX(target)" + nl
    funcs += "    set ty = GetUnitY(target)" + nl
    funcs += "    set facing = GetUnitFacing(target)" + nl
    funcs += "    set dx = bx - tx" + nl
    funcs += "    set dy = by - ty" + nl
    funcs += "    set dist = SquareRoot(dx * dx + dy * dy)" + nl
    # V7 原版卡位逻辑
    funcs += "    if dist > 800.0 then" + nl
    # FAR: 记录但不移动
    funcs += '        set csvLine = I2S(udg_blk_TickCount) + "," + R2SW(bx,1,1) + "," + R2SW(by,1,1) + "," + R2SW(tx,1,1) + "," + R2SW(ty,1,1) + "," + R2SW(facing,1,1) + "," + R2SW(dist,1,1) + ",0,0,0,FAR"' + nl
    funcs += '        call Preload(csvLine)' + nl
    funcs += "        set udg_blk_LogLine = udg_blk_LogLine + 1" + nl
    funcs += "        if udg_blk_LogLine >= 5 then" + nl
    funcs += "            call Trig_BLK_FlushLog()" + nl
    funcs += "        endif" + nl
    funcs += "        set blocker = null" + nl
    funcs += "        set target = null" + nl
    funcs += "        return" + nl
    funcs += "    endif" + nl
    # S形偏侧 (V7: 4 tick 周期)
    funcs += "    set udg_blk_SideToggle = udg_blk_SideToggle + 1" + nl
    funcs += "    if udg_blk_SideToggle >= 4 then" + nl
    funcs += "        set udg_blk_SideToggle = 0" + nl
    funcs += "    endif" + nl
    funcs += "    if udg_blk_SideToggle < 2 then" + nl
    funcs += "        set offsetSign = 1.0" + nl
    funcs += "    else" + nl
    funcs += "        set offsetSign = -1.0" + nl
    funcs += "    endif" + nl
    # V7 卡位点计算 (blockDist = dist + 50, side offset = 30)
    funcs += "    set blockDist = dist + 50.0" + nl
    funcs += "    set sideAngle = facing * bj_DEGTORAD + offsetSign * 1.5708" + nl
    funcs += "    set blockX = tx + Cos(facing * bj_DEGTORAD) * blockDist + Cos(sideAngle) * 30.0" + nl
    funcs += "    set blockY = ty + Sin(facing * bj_DEGTORAD) * blockDist + Sin(sideAngle) * 30.0" + nl
    funcs += '    call IssuePointOrder(blocker, "move", blockX, blockY)' + nl
    # CSV: 每 tick 直接 Preload，不拼 buffer
    funcs += '    set csvLine = I2S(udg_blk_TickCount) + "," + R2SW(bx,1,1) + "," + R2SW(by,1,1) + "," + R2SW(tx,1,1) + "," + R2SW(ty,1,1) + "," + R2SW(facing,1,1) + "," + R2SW(dist,1,1) + "," + R2SW(blockX,1,1) + "," + R2SW(blockY,1,1) + "," + R2SW(offsetSign,1,0) + ",MOVE"' + nl
    funcs += '    call Preload(csvLine)' + nl
    funcs += "    set udg_blk_LogLine = udg_blk_LogLine + 1" + nl
    funcs += "    if udg_blk_LogLine >= 5 then" + nl
    funcs += "        call Trig_BLK_FlushLog()" + nl
    funcs += "    endif" + nl
    # debug
    funcs += "    if udg_blk_DebugMode then" + nl
    funcs += "        " + D + '"[BLK] d=" + R2SW(dist, 1, 0))' + nl
    funcs += "    endif" + nl
    funcs += "    set blocker = null" + nl
    funcs += "    set target = null" + nl
    funcs += "endfunction" + nl + nl

    # Init
    funcs += "function InitTrig_BLK takes nothing returns nothing" + nl
    funcs += "    local trigger tTimer = CreateTrigger()" + nl
    funcs += "    local trigger tBlock = CreateTrigger()" + nl
    funcs += "    local trigger tNoBlock = CreateTrigger()" + nl
    funcs += "    local trigger tDebug = CreateTrigger()" + nl
    funcs += "    call TriggerRegisterTimerEvent(tTimer, 0.15, true)" + nl
    funcs += "    call TriggerAddAction(tTimer, function Trig_BLK_Tick)" + nl
    funcs += '    call TriggerRegisterPlayerChatEvent(tBlock, Player(0), "-block", true)' + nl
    funcs += '    call TriggerRegisterPlayerChatEvent(tBlock, Player(1), "-block", true)' + nl
    funcs += "    call TriggerAddAction(tBlock, function Trig_BLK_EnableAction)" + nl
    funcs += '    call TriggerRegisterPlayerChatEvent(tNoBlock, Player(0), "-noblock", true)' + nl
    funcs += '    call TriggerRegisterPlayerChatEvent(tNoBlock, Player(1), "-noblock", true)' + nl
    funcs += "    call TriggerAddAction(tNoBlock, function Trig_BLK_DisableAction)" + nl
    funcs += '    call TriggerRegisterPlayerChatEvent(tDebug, Player(0), "-blockdebug", true)' + nl
    funcs += '    call TriggerRegisterPlayerChatEvent(tDebug, Player(1), "-blockdebug", true)' + nl
    funcs += "    call TriggerAddAction(tDebug, function Trig_BLK_DebugAction)" + nl
    funcs += "    " + D + '"[BLK] V7-DEBUG init")' + nl
    funcs += "endfunction" + nl

    src = src.replace("function InitCustomTriggers", funcs + "function InitCustomTriggers")
    print("[BLK] functions ok")

    idx = src.find("call InitBlizzard(  )")
    if idx != -1:
        eol = src.find(nl, idx)
        src = src[:eol+len(nl)] + "    call InitTrig_BLK()" + nl + src[eol+len(nl):]
        print("[BLK] hooked")

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("[BLK] V7-DEBUG done")

if __name__ == "__main__":
    main()
