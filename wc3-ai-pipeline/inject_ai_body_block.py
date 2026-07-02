#!/usr/bin/env python3
"""inject_ai_body_block.py V9 — V7 baseline + param tuning
Changes vs V7:
  - blockDist = min(dist+50, 250)  (cap at 250)
  - SideToggle period: 3 tick (was 4)
  - Player detection: GetPlayerController (V7-FIX)
  - side offset: 30 (unchanged)
"""
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

    g = nl.join([
        "    // --- body block globals (V9: V7 + blockDist cap 250, toggle 3t) ---",
        "    boolean udg_blk_Enabled     = false",
        "    unit    udg_blk_Target      = null",
        "    unit    udg_blk_Blocker     = null",
        "    integer udg_blk_SideToggle  = 0",
        "    integer udg_blk_TickCount   = 0",
        "    boolean udg_blk_DebugMode   = false",
        "    integer udg_blk_LogLine     = 0",
        "    integer udg_blk_FlushCount  = 0",
        "    boolean udg_blk_LogOpen     = false",
        "    player  udg_blk_AIPlayer    = null",
        "    player  udg_blk_UserPlayer  = null",
        "    // --- shared globals (declare here if not in base map) ---",
        "    integer udg_aiml_Round1Mode    = 0",
        "    integer udg_aiml_Round1Pref    = 0",
    ]) + nl
    src = src.replace("endglobals", g + "endglobals")
    print("[BLK] globals ok")

    D = 'call DisplayTimedTextToForce(GetPlayersAll(), 5.00, '

    funcs = nl + "// BODY BLOCK AI V9 (V7 logic + cap250 + toggle3t + correct player)" + nl

    funcs += "function Trig_BLK_InitPlayers takes nothing returns nothing" + nl
    funcs += "    local integer i = 0" + nl
    funcs += "    local player p" + nl
    funcs += "    loop" + nl
    funcs += "        exitwhen i >= 12" + nl
    funcs += "        set p = Player(i)" + nl
    funcs += "        if GetPlayerController(p) == MAP_CONTROL_COMPUTER and GetPlayerSlotState(p) == PLAYER_SLOT_STATE_PLAYING then" + nl
    funcs += "            set udg_blk_AIPlayer = p" + nl
    funcs += "        endif" + nl
    funcs += "        if GetPlayerController(p) == MAP_CONTROL_USER and GetPlayerSlotState(p) == PLAYER_SLOT_STATE_PLAYING then" + nl
    funcs += "            set udg_blk_UserPlayer = p" + nl
    funcs += "        endif" + nl
    funcs += "        set i = i + 1" + nl
    funcs += "    endloop" + nl
    funcs += "endfunction" + nl + nl

    funcs += "function Trig_BLK_FindBlocker takes nothing returns unit" + nl
    funcs += "    local group g = CreateGroup()" + nl
    funcs += "    local unit u" + nl
    funcs += "    local unit best = null" + nl
    funcs += "    if udg_blk_AIPlayer == null then" + nl
    funcs += "        return null" + nl
    funcs += "    endif" + nl
    funcs += "    call GroupEnumUnitsOfPlayer(g, udg_blk_AIPlayer, null)" + nl
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

    funcs += "function Trig_BLK_FindTarget takes nothing returns unit" + nl
    funcs += "    local group g = CreateGroup()" + nl
    funcs += "    local unit u" + nl
    funcs += "    local unit best = null" + nl
    funcs += "    if udg_blk_UserPlayer == null then" + nl
    funcs += "        return null" + nl
    funcs += "    endif" + nl
    funcs += "    call GroupEnumUnitsOfPlayer(g, udg_blk_UserPlayer, null)" + nl
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

    funcs += "function Trig_BLK_FlushLog takes nothing returns nothing" + nl
    funcs += "    local string fname" + nl
    funcs += '    set fname = "save\\\\blk_log\\\\data_" + I2S(udg_blk_FlushCount) + ".txt"' + nl
    funcs += "    set udg_blk_FlushCount = udg_blk_FlushCount + 1" + nl
    funcs += "    call PreloadGenEnd(fname)" + nl
    funcs += "    call PreloadGenClear()" + nl
    funcs += "    call PreloadGenStart()" + nl
    funcs += "    set udg_blk_LogLine = 0" + nl
    funcs += "endfunction" + nl + nl

    funcs += "function Trig_BLK_EnableAction takes nothing returns nothing" + nl
    funcs += "    set udg_blk_Enabled = true" + nl
    funcs += "    set udg_blk_FlushCount = 0" + nl
    funcs += "    set udg_blk_LogLine = 0" + nl
    funcs += "    set udg_blk_LogOpen = true" + nl
    funcs += "    call PreloadGenClear()" + nl
    funcs += "    call PreloadGenStart()" + nl
    funcs += "    " + D + '"[BLK] ON (V9)")' + nl
    funcs += "endfunction" + nl + nl

    funcs += "function Trig_BLK_DisableAction takes nothing returns nothing" + nl
    funcs += "    set udg_blk_Enabled = false" + nl
    funcs += "    set udg_blk_LogOpen = false" + nl
    funcs += "    call Trig_BLK_FlushLog()" + nl
    funcs += "    " + D + '"[BLK] OFF (files=" + I2S(udg_blk_FlushCount) + ")")' + nl
    funcs += "endfunction" + nl + nl

    funcs += "function Trig_BLK_DebugAction takes nothing returns nothing" + nl
    funcs += "    set udg_blk_DebugMode = not udg_blk_DebugMode" + nl
    funcs += "    " + D + '"[BLK] debug toggled")' + nl
    funcs += "endfunction" + nl + nl

    # === TICK: V7 logic + blockDist cap 250 + toggle 3t ===
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
    funcs += "    if udg_blk_TickCount == 1 then" + nl
    funcs += "        call Trig_BLK_InitPlayers()" + nl
    funcs += "    endif" + nl
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
    # === FAR (>800 no-op) ===
    funcs += "    if dist > 800.0 then" + nl
    funcs += '        set csvLine = I2S(udg_blk_TickCount) + "," + R2SW(bx,1,1) + "," + R2SW(by,1,1) + "," + R2SW(tx,1,1) + "," + R2SW(ty,1,1) + "," + R2SW(facing,1,1) + "," + R2SW(dist,1,1) + ",0,0,0,FAR"' + nl
    funcs += "        call Preload(csvLine)" + nl
    funcs += "        set udg_blk_LogLine = udg_blk_LogLine + 1" + nl
    funcs += "        if udg_blk_LogLine >= 5 then" + nl
    funcs += "            call Trig_BLK_FlushLog()" + nl
    funcs += "        endif" + nl
    funcs += "        set blocker = null" + nl
    funcs += "        set target = null" + nl
    funcs += "        return" + nl
    funcs += "    endif" + nl
    # === S-shaped side (3 tick period) ===
    funcs += "    set udg_blk_SideToggle = udg_blk_SideToggle + 1" + nl
    funcs += "    if udg_blk_SideToggle >= 3 then" + nl
    funcs += "        set udg_blk_SideToggle = 0" + nl
    funcs += "    endif" + nl
    funcs += "    if udg_blk_SideToggle < 2 then" + nl
    funcs += "        set offsetSign = 1.0" + nl
    funcs += "    else" + nl
    funcs += "        set offsetSign = -1.0" + nl
    funcs += "    endif" + nl
    # === blockDist: V7 dist+50 but capped at 250 ===
    funcs += "    set blockDist = dist + 50.0" + nl
    funcs += "    if blockDist > 250.0 then" + nl
    funcs += "        set blockDist = 250.0" + nl
    funcs += "    endif" + nl
    # === side offset 30 (unchanged) ===
    funcs += "    set sideAngle = facing * bj_DEGTORAD + offsetSign * 1.5708" + nl
    funcs += "    set blockX = tx + Cos(facing * bj_DEGTORAD) * blockDist + Cos(sideAngle) * 30.0" + nl
    funcs += "    set blockY = ty + Sin(facing * bj_DEGTORAD) * blockDist + Sin(sideAngle) * 30.0" + nl
    funcs += '    call IssuePointOrder(blocker, "move", blockX, blockY)' + nl
    funcs += '    set csvLine = I2S(udg_blk_TickCount) + "," + R2SW(bx,1,1) + "," + R2SW(by,1,1) + "," + R2SW(tx,1,1) + "," + R2SW(ty,1,1) + "," + R2SW(facing,1,1) + "," + R2SW(dist,1,1) + "," + R2SW(blockX,1,1) + "," + R2SW(blockY,1,1) + "," + R2SW(offsetSign,1,0) + ",MOVE"' + nl
    funcs += "    call Preload(csvLine)" + nl
    funcs += "    set udg_blk_LogLine = udg_blk_LogLine + 1" + nl
    funcs += "    if udg_blk_LogLine >= 5 then" + nl
    funcs += "        call Trig_BLK_FlushLog()" + nl
    funcs += "    endif" + nl
    funcs += "    if udg_blk_DebugMode then" + nl
    funcs += "        " + D + '"[BLK] d=" + R2SW(dist, 1, 0) + " bd=" + R2SW(blockDist, 1, 0))' + nl
    funcs += "    endif" + nl
    funcs += "    set blocker = null" + nl
    funcs += "    set target = null" + nl
    funcs += "endfunction" + nl + nl

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
    funcs += "    " + D + '"[BLK] V9 init")' + nl
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
    print("[BLK] V9 done")

if __name__ == "__main__":
    main()
