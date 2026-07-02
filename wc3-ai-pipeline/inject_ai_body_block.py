#!/usr/bin/env python3
"""inject_ai_body_block.py V12

Changes from V9:
  - -block: toggle (Round1Mode=3) with colored prompt, -noblock removed
  - -blockdebug removed; debug via udg_aiml_DebugMode (inject_debug.py)
  - Debug display: once/sec, only when dist<=300
  - Format: [BLK] dir=X | dist=NNN | BLOCK/CHASE
  - BLOCK = FS ahead of DK (facing projection > 0)
  - CHASE = FS behind DK (facing projection <= 0)
"""
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: <war3map.j>")
        sys.exit(1)
    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if "function Trig_BLK_Tick" in src:
        print("[BLK] skip (already injected)")
        return
    nl = "\r\n" if "\r\n" in src else "\n"
    D = "call DisplayTimedTextToForce(GetPlayersAll(), 5.00, "

    # ── globals ──
    g_body = [
        "    // --- body block globals (V12: toggle+Round1Mode=3, debug via aiml_DebugMode) ---",
        "    boolean udg_blk_Enabled     = false",
        "    boolean udg_blk_Recording   = false",
        "    unit    udg_blk_Target      = null",
        "    unit    udg_blk_Blocker     = null",
        "    integer udg_blk_SideToggle  = 0",
        "    integer udg_blk_TickCount   = 0",
        "    integer udg_blk_LogLine     = 0",
        "    integer udg_blk_FlushCount  = 0",
        "    boolean udg_blk_LogOpen     = false",
        "    player  udg_blk_AIPlayer    = null",
        "    player  udg_blk_UserPlayer  = null",
        "    integer udg_blk_DebugTick   = 0   // throttle debug to once/sec",
    ]
    g = nl.join(g_body) + nl
    if "udg_aiml_Round1Mode" not in src:
        g += nl.join([
            "    // --- shared globals (not in base map) ---",
            "    integer udg_aiml_Round1Mode    = 0",
            "    integer udg_aiml_Round1Pref    = 0",
        ]) + nl
    src = src.replace("endglobals", g + "endglobals")
    print("[BLK] globals ok")

    # ── functions ──
    body = nl + "// BODY BLOCK AI V12 (toggle + Round1Mode=3 + aiml_DebugMode + once/sec debug)" + nl

    # InitPlayers
    body += """function Trig_BLK_InitPlayers takes nothing returns nothing
    local integer i = 0
    local player p
    loop
        exitwhen i >= 12
        set p = Player(i)
        if GetPlayerController(p) == MAP_CONTROL_COMPUTER and GetPlayerSlotState(p) == PLAYER_SLOT_STATE_PLAYING then
            set udg_blk_AIPlayer = p
        endif
        if GetPlayerController(p) == MAP_CONTROL_USER and GetPlayerSlotState(p) == PLAYER_SLOT_STATE_PLAYING then
            set udg_blk_UserPlayer = p
        endif
        set i = i + 1
    endloop
endfunction

""" + nl

    # FindBlocker
    body += """function Trig_BLK_FindBlocker takes nothing returns unit
    local group g = CreateGroup()
    local unit u
    local unit best = null
    if udg_blk_AIPlayer == null then
        return null
    endif
    call GroupEnumUnitsOfPlayer(g, udg_blk_AIPlayer, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitType(u, UNIT_TYPE_DEAD) then
            set best = u
        endif
    endloop
    call DestroyGroup(g)
    return best
endfunction

""" + nl

    # FindTarget
    body += """function Trig_BLK_FindTarget takes nothing returns unit
    local group g = CreateGroup()
    local unit u
    local unit best = null
    if udg_blk_UserPlayer == null then
        return null
    endif
    call GroupEnumUnitsOfPlayer(g, udg_blk_UserPlayer, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitType(u, UNIT_TYPE_DEAD) then
            set best = u
        endif
    endloop
    call DestroyGroup(g)
    return best
endfunction

""" + nl

    # FlushLog
    body += """function Trig_BLK_FlushLog takes nothing returns nothing
    local string fname
    set fname = "save\\\\blk_log\\\\data_" + I2S(udg_blk_FlushCount) + ".txt"
    set udg_blk_FlushCount = udg_blk_FlushCount + 1
    call PreloadGenEnd(fname)
    call PreloadGenClear()
    call PreloadGenStart()
    set udg_blk_LogLine = 0
endfunction

""" + nl

    # DirName helper: facing angle -> 8-way direction string
    body += """function Trig_BLK_DirName takes real facing returns string
    local integer i = R2I((facing + 22.5) / 45.0)
    set i = ModuloInteger(i, 8)
    if i == 0 then
        return "N"
    elseif i == 1 then
        return "NE"
    elseif i == 2 then
        return "E"
    elseif i == 3 then
        return "SE"
    elseif i == 4 then
        return "S"
    elseif i == 5 then
        return "SW"
    elseif i == 6 then
        return "W"
    endif
    return "NW"
endfunction

""" + nl

    # -block toggle: Round1Mode=3 with color prompt, -noblock removed
    body += """function Trig_BLK_ToggleAction takes nothing returns nothing
    if udg_blk_Enabled then
        set udg_blk_Enabled = false
        set udg_aiml_Round1Pref = 0
        set udg_blk_LogOpen = false
        call Trig_BLK_FlushLog()
        """ + D + '"[AIML] |cff00ff00Body-Block OFF|r (files=" + I2S(udg_blk_FlushCount) + ")")' + nl + """    else
        set udg_blk_Enabled = true
        set udg_aiml_Round1Pref = 3
        set udg_aiml_Round1Pref = 3
        set udg_blk_TickCount = 0
        set udg_blk_SideToggle = 0
        set udg_blk_FlushCount = 0
        set udg_blk_LogLine = 0
        set udg_blk_LogOpen = true
        call PreloadGenClear()
        call PreloadGenStart()
        """ + D + '"|cffff0000[AIML] Body-Block ON (Round1Pref=3, activated on countdown)|r")' + nl + """    endif
endfunction

""" + nl

    # -record toggle: independent CSV logging (works without block)
    body += """function Trig_BLK_RecordToggle takes nothing returns nothing
    if udg_blk_Recording then
        set udg_blk_Recording = false
        set udg_blk_LogOpen = false
        call Trig_BLK_FlushLog()
        """ + D + '"[BLK] |cff00ff00Recording OFF|r (files=" + I2S(udg_blk_FlushCount) + ")")' + nl + """    else
        set udg_blk_Recording = true
        set udg_blk_FlushCount = 0
        set udg_blk_LogLine = 0
        set udg_blk_LogOpen = true
        call PreloadGenClear()
        call PreloadGenStart()
        """ + D + '"|cffff0000[BLK] Recording ON|r")' + nl + """    endif
endfunction

""" + nl

    # === TICK: V9 logic + V12 debug (aiml_DebugMode, once/sec, dist<=300) ===
    body += """function Trig_BLK_Tick takes nothing returns nothing
    local unit blocker
    local unit target
    local real bx
    local real by
    local real tx
    local real ty
    local real facing
    local real dx
    local real dy
    local real dist
    local real blockDist
    local real blockX
    local real blockY
    local real sideAngle
    local real offsetSign
    local real proj   // facing projection for BLOCK/CHASE
    local string csvLine
    if not udg_blk_Enabled then
        return
    endif
    set udg_blk_TickCount = udg_blk_TickCount + 1
    if udg_blk_TickCount == 1 then
        call Trig_BLK_InitPlayers()
    endif
    set blocker = Trig_BLK_FindBlocker()
    set target = Trig_BLK_FindTarget()
    if blocker == null or target == null then
        return
    endif
    set bx = GetUnitX(blocker)
    set by = GetUnitY(blocker)
    set tx = GetUnitX(target)
    set ty = GetUnitY(target)
    set facing = GetUnitFacing(target)
    set dx = bx - tx
    set dy = by - ty
    set dist = SquareRoot(dx * dx + dy * dy)
    // FAR (>800): no block action, just log
    if dist > 800.0 then
        if udg_blk_Recording and udg_blk_LogOpen then
            set csvLine = I2S(udg_blk_TickCount) + "," + R2SW(bx,1,1) + "," + R2SW(by,1,1) + "," + R2SW(tx,1,1) + "," + R2SW(ty,1,1) + "," + R2SW(facing,1,1) + "," + R2SW(dist,1,1) + ",0,0,0,FAR"
            call Preload(csvLine)
            set udg_blk_LogLine = udg_blk_LogLine + 1
            if udg_blk_LogLine >= 5 then
                call Trig_BLK_FlushLog()
            endif
        endif
        set blocker = null
        set target = null
        return
    endif
    // V9 block logic
    set udg_blk_SideToggle = udg_blk_SideToggle + 1
    if udg_blk_SideToggle >= 3 then
        set udg_blk_SideToggle = 0
    endif
    if udg_blk_SideToggle < 2 then
        set offsetSign = 1.0
    else
        set offsetSign = -1.0
    endif
    set blockDist = dist + 50.0
    if blockDist > 250.0 then
        set blockDist = 250.0
    endif
    set sideAngle = facing * bj_DEGTORAD + offsetSign * 1.5708
    set blockX = tx + Cos(facing * bj_DEGTORAD) * blockDist + Cos(sideAngle) * 30.0
    set blockY = ty + Sin(facing * bj_DEGTORAD) * blockDist + Sin(sideAngle) * 30.0
    call IssuePointOrder(blocker, "move", blockX, blockY)
    // CSV log (conditional on Recording)
    if udg_blk_Recording and udg_blk_LogOpen then
        set csvLine = I2S(udg_blk_TickCount) + "," + R2SW(bx,1,1) + "," + R2SW(by,1,1) + "," + R2SW(tx,1,1) + "," + R2SW(ty,1,1) + "," + R2SW(facing,1,1) + "," + R2SW(dist,1,1) + "," + R2SW(blockX,1,1) + "," + R2SW(blockY,1,1) + "," + R2SW(offsetSign,1,0) + ",MOVE"
        call Preload(csvLine)
        set udg_blk_LogLine = udg_blk_LogLine + 1
        if udg_blk_LogLine >= 5 then
            call Trig_BLK_FlushLog()
        endif
    endif
    // V12 debug: aiml_DebugMode, once/sec (~every 7th tick), dist<=300 only
    if udg_aiml_DebugMode and dist <= 300.0 then
        set udg_blk_DebugTick = udg_blk_DebugTick + 1
        if udg_blk_DebugTick >= 7 then
            set udg_blk_DebugTick = 0
            // projection of (bx,by) onto DK facing
            set proj = dx * Cos(facing * bj_DEGTORAD) + dy * Sin(facing * bj_DEGTORAD)
            if proj > 0.0 then
                """ + D + '"[BLK] dir=" + Trig_BLK_DirName(facing) + " | dist=" + R2SW(dist,1,0) + " | BLOCK")' + nl + """            else
                """ + D + '"[BLK] dir=" + Trig_BLK_DirName(facing) + " | dist=" + R2SW(dist,1,0) + " | CHASE")' + nl + """            endif
        endif
    endif
    set blocker = null
    set target = null
endfunction

""" + nl

    # InitTrig
    body += """function InitTrig_BLK takes nothing returns nothing
    local trigger tTimer = CreateTrigger()
    local trigger tBlock = CreateTrigger()
    local trigger tRecord = CreateTrigger()
    call TriggerRegisterTimerEvent(tTimer, 0.15, true)
    call TriggerAddAction(tTimer, function Trig_BLK_Tick)
    call TriggerRegisterPlayerChatEvent(tBlock, Player(0), "-block", true)
    call TriggerRegisterPlayerChatEvent(tBlock, Player(1), "-block", true)
    call TriggerAddAction(tBlock, function Trig_BLK_ToggleAction)
    call TriggerRegisterPlayerChatEvent(tRecord, Player(0), "-record", true)
    call TriggerRegisterPlayerChatEvent(tRecord, Player(1), "-record", true)
    call TriggerAddAction(tRecord, function Trig_BLK_RecordToggle)
    """ + D + '"[BLK] V12 init (Round1Mode=3 toggle + -record + aiml debug)")' + nl + """endfunction

"""

    src = src.replace("function InitCustomTriggers", body + "function InitCustomTriggers")
    print("[BLK] functions ok")

    # hook: place after RunInitializationTriggers (same as other AI modules)
    idx = src.find("call RunInitializationTriggers(  )")
    if idx != -1:
        eol = src.find(nl, idx)
        src = src[:eol + len(nl)] + "    call InitTrig_BLK()" + nl + src[eol + len(nl):]
        print("[BLK] hooked")

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("[BLK] V12 done")


if __name__ == "__main__":
    main()
