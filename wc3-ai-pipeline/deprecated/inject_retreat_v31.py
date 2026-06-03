#!/usr/bin/env python3
"""
inject_retreat_v31.py - Inject V30b retreat logic into V18 base map.

Takes the V18 base war3map.j (which already has TC stomp + salvo) and adds:
  1. New globals for retreat state machine
  2. DecideRetreatForTick function (threat scanning + retreat point calculation)
  3. Modified IssueAttackCB with retreat action handling
  4. State machine in SalvoForPlayer (before ForGroup)
  5. Full-army ForGroup on move/stop ticks

Direction: fixed toward map RIGHT (+X).
Step: 200. Cycle: shoot(0.5s) -> move(0.5s) -> stop(0.5s) = 1.5s.
Trigger: ranged >= 50% of army (existing majority check).
"""

import re
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: inject_retreat_v31.py <war3map.j>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    nl = "\r\n" if "\r\n" in src else "\n"

    # --- 1) Add retreat globals after existing AIML globals ---
    RETREAT_GLOBALS = """    // [V32] Per-unit kite globals
    boolean udg_aiml_GroupRetreating = false
    boolean udg_aiml_DebugMode = false
    integer udg_aiml_GlobalThreatCount = 0
    real    udg_aiml_GlobalThreatSumX = 0.00
    real    udg_aiml_GlobalThreatSumY = 0.00
    real    udg_aiml_GroupRetreatStep = 200.00
    real    udg_aiml_LocalThreatRadius = 350.00
    real    udg_aiml_KiteMinMapBound = 600.00
    real    udg_aiml_KiteMapMinX = -99999.00
    real    udg_aiml_KiteMapMaxX = 99999.00
    real    udg_aiml_KiteMapMinY = -99999.00
    real    udg_aiml_KiteMapMaxY = 99999.00
    group   udg_aiml_LocalThreatG = null
    real    udg_aiml_LocalSumX = 0.00
    real    udg_aiml_LocalSumY = 0.00
    real    udg_aiml_RangedCentroidX = 0.00
    real    udg_aiml_RangedCentroidY = 0.00
    integer udg_aiml_RetreatPhase = 0
    integer udg_aiml_RetreatAction = 0
    integer udg_aiml_DebugKiteCount = 0
    integer udg_aiml_DebugKiteDir = 0"""

    # Find the last AIML global line (before first function)
    # Insert after "real    udg_aiml_SalvoMapRange" or similar
    marker = "real    udg_aiml_SalvoMapRange"
    idx = src.find(marker)
    if idx == -1:
        # Try another marker
        marker = "group   udg_aiml_SalvoEnemyG"
        idx = src.find(marker)
    if idx == -1:
        print("ERROR: cannot find AIML globals insertion point")
        sys.exit(1)
    # Find end of that line
    eol = src.index(nl, idx)
    src = src[:eol + len(nl)] + RETREAT_GLOBALS + nl + src[eol + len(nl):]
    print("inserted retreat globals")

    # --- 2) Add helper functions before IssueAttackCB ---
    RETREAT_FUNCTIONS = """
// [V32] Per-unit kite: each ranged unit dodges individually
// Direction: above centroid -> flee up(+Y), below -> flee down(-Y), near center -> random
function Trig_AIML_IsThreatUnit takes nothing returns boolean
    local unit u = GetFilterUnit()
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return false
    endif
    if IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set u = null
        return false
    endif
    if IsUnitAlly(u, udg_aiml_SalvoOwnerPlayer) then
        set u = null
        return false
    endif
    set u = null
    return true
endfunction

function Trig_AIML_LocalThreatTallyCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    set udg_aiml_GlobalThreatCount = udg_aiml_GlobalThreatCount + 1
    set udg_aiml_GlobalThreatSumX = udg_aiml_GlobalThreatSumX + GetUnitX(u)
    set udg_aiml_GlobalThreatSumY = udg_aiml_GlobalThreatSumY + GetUnitY(u)
    set u = null
endfunction

function Trig_AIML_RetreatScanRangedCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real ux = GetUnitX(u)
    local real uy = GetUnitY(u)
    // Accumulate ranged positions for centroid
    set udg_aiml_LocalSumX = udg_aiml_LocalSumX + ux
    set udg_aiml_LocalSumY = udg_aiml_LocalSumY + uy
    // Check local threats within radius
    call GroupClear(udg_aiml_LocalThreatG)
    call GroupEnumUnitsInRange(udg_aiml_LocalThreatG, ux, uy, udg_aiml_LocalThreatRadius, Filter(function Trig_AIML_IsThreatUnit))
    call ForGroup(udg_aiml_LocalThreatG, function Trig_AIML_LocalThreatTallyCB)
    set u = null
endfunction

function Trig_AIML_DecideRetreatForTick takes nothing returns nothing
    local real ax
    local real ay
    // Reset
    set udg_aiml_GlobalThreatCount = 0
    set udg_aiml_GlobalThreatSumX = 0.0
    set udg_aiml_GlobalThreatSumY = 0.0
    set udg_aiml_LocalSumX = 0.0
    set udg_aiml_LocalSumY = 0.0
    set udg_aiml_GroupRetreating = false
    if udg_aiml_SalvoRangedCount < 1 then
        return
    endif
    // Scan ranged units for threats + compute centroid
    call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_RetreatScanRangedCB)
    if udg_aiml_GlobalThreatCount == 0 then
        return
    endif
    // Ranged centroid
    set ax = udg_aiml_LocalSumX / I2R(udg_aiml_SalvoRangedCount)
    set ay = udg_aiml_LocalSumY / I2R(udg_aiml_SalvoRangedCount)
    set udg_aiml_RangedCentroidX = ax
    set udg_aiml_RangedCentroidY = ay
    // [V32] Exit condition: threats*3 <= army => stand and fight
    if udg_aiml_GlobalThreatCount * 3 <= udg_aiml_SalvoArmyCount then
        set udg_aiml_GroupRetreating = false
        return
    endif
    set udg_aiml_GroupRetreating = true
endfunction

// [V32] Per-unit kite callback: each unit decides its own flee direction
function Trig_AIML_PerUnitKiteCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real ux
    local real uy
    local real dy
    local real targetY
    local integer localThreats
    local group tg
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    if IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set u = null
        return
    endif
    // [V32] Skip heroes - only troops kite
    if IsUnitType(u, UNIT_TYPE_HERO) then
        set u = null
        return
    endif
    set ux = GetUnitX(u)
    set uy = GetUnitY(u)
    // Check if this unit has threats nearby
    set tg = CreateGroup()
    call GroupEnumUnitsInRange(tg, ux, uy, udg_aiml_LocalThreatRadius, Filter(function Trig_AIML_IsThreatUnit))
    set localThreats = CountUnitsInGroup(tg)
    call DestroyGroup(tg)
    set tg = null
    if localThreats == 0 then
        // No threats nearby, don't kite
        set u = null
        return
    endif
    // Decide direction based on position relative to centroid
    set dy = uy - udg_aiml_RangedCentroidY
    if dy > 50.0 then
        // Above centroid -> flee UP (+Y)
        set targetY = uy + udg_aiml_GroupRetreatStep
        set udg_aiml_DebugKiteDir = 1
    elseif dy < -50.0 then
        // Below centroid -> flee DOWN (-Y)
        set targetY = uy - udg_aiml_GroupRetreatStep
        set udg_aiml_DebugKiteDir = 2
    else
        // Near center -> random up or down
        if GetRandomInt(0, 1) == 0 then
            set targetY = uy + udg_aiml_GroupRetreatStep
            set udg_aiml_DebugKiteDir = 3
        else
            set targetY = uy - udg_aiml_GroupRetreatStep
            set udg_aiml_DebugKiteDir = 4
        endif
    endif
    // Clamp Y
    if targetY > udg_aiml_KiteMapMaxY - udg_aiml_KiteMinMapBound then
        set targetY = udg_aiml_KiteMapMaxY - udg_aiml_KiteMinMapBound
    endif
    if targetY < udg_aiml_KiteMapMinY + udg_aiml_KiteMinMapBound then
        set targetY = udg_aiml_KiteMapMinY + udg_aiml_KiteMinMapBound
    endif
    call IssuePointOrder(u, "smart", ux, targetY)
    set udg_aiml_DebugKiteCount = udg_aiml_DebugKiteCount + 1
    set u = null
endfunction

// [V32] Stop callback to break movement
function Trig_AIML_StopCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    if IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set u = null
        return
    endif
    call IssueImmediateOrder(u, "stop")
    set u = null
endfunction

"""

    # Insert before IssueAttackCB
    marker2 = "function Trig_AIML_IssueAttackCB takes nothing returns nothing"
    idx2 = src.find(marker2)
    if idx2 == -1:
        print("ERROR: cannot find IssueAttackCB")
        sys.exit(1)
    src = src[:idx2] + RETREAT_FUNCTIONS.replace("\n", nl) + src[idx2:]
    print("inserted retreat helper functions")

    # --- 3) Replace IssueAttackCB to add retreat handling ---
    old_cb = """function Trig_AIML_IssueAttackCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local unit target = udg_aiml_FocusTarget1
    if target == null then
        set u = null
        return
    endif
    if IsUnitType(target, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    call IssueTargetOrder(u, "smart", target)
    set u = null
endfunction"""

    new_cb = """function Trig_AIML_IssueAttackCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local unit target = udg_aiml_FocusTarget1
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    // Normal mode: focus-fire on target
    if target == null then
        set u = null
        return
    endif
    if IsUnitType(target, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    call IssueTargetOrder(u, "smart", target)
    set u = null
endfunction"""

    # Normalize line endings for matching
    old_cb_norm = old_cb.replace("\n", nl)
    new_cb_norm = new_cb.replace("\n", nl)
    if old_cb_norm in src:
        src = src.replace(old_cb_norm, new_cb_norm, 1)
        print("replaced IssueAttackCB with retreat-aware version")
    else:
        print("WARNING: could not find exact IssueAttackCB to replace")

    # --- 4) Add per-unit kite state machine in SalvoForPlayer ---
    # Insert BEFORE RebuildGroupEnemy (after majority check passes).
    old_enemy_rebuild = "    call Trig_AIML_RebuildGroupEnemy()"
    
    state_machine_block = """    // [V32] Per-unit kite state machine
    call Trig_AIML_DecideRetreatForTick()
    set udg_aiml_DebugKiteCount = 0
    if udg_aiml_GroupRetreating then
        if udg_aiml_RetreatPhase == 0 then
            // Shoot tick: fall through to normal salvo
            set udg_aiml_RetreatAction = 0
            set udg_aiml_RetreatPhase = 2
        elseif udg_aiml_RetreatPhase == 2 then
            // Move tick: per-unit kite
            set udg_aiml_RetreatAction = 2
            set udg_aiml_RetreatPhase = 1
            call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_PerUnitKiteCB)
            if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "[V32] KITE act=2 kited=" + I2S(udg_aiml_DebugKiteCount) + " dir=" + I2S(udg_aiml_DebugKiteDir) + " threats=" + I2S(udg_aiml_GlobalThreatCount) + " centroidY=" + R2S(udg_aiml_RangedCentroidY))
            endif
            return
        elseif udg_aiml_RetreatPhase == 1 then
            // Stop tick: break movement
            set udg_aiml_RetreatAction = 1
            set udg_aiml_RetreatPhase = 0
            call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_StopCB)
            if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "[V32] STOP act=1 threats=" + I2S(udg_aiml_GlobalThreatCount))
            endif
            return
        endif
    else
        set udg_aiml_RetreatAction = 0
        set udg_aiml_RetreatPhase = 0
    endif
    // Shoot tick or not retreating: fall through to normal salvo
"""

    old_er_norm = old_enemy_rebuild.replace("\n", nl)
    new_block_norm = state_machine_block.replace("\n", nl) + old_er_norm
    if old_er_norm in src:
        src = src.replace(old_er_norm, new_block_norm, 1)
        print("inserted per-unit kite state machine BEFORE RebuildGroupEnemy")
    else:
        print("WARNING: could not find RebuildGroupEnemy insertion point")

    # --- 5) Init map bounds in SalvoInit ---
    # Find SalvoInit and add LocalThreatG creation + map bounds cache
    init_marker = "function Trig_AIML_SalvoInit takes nothing returns nothing"
    idx3 = src.find(init_marker)
    if idx3 != -1:
        # Find the endfunction of SalvoInit
        end_init = src.find("endfunction", idx3)
        init_code = nl + "    // [V31] Init retreat resources" + nl
        init_code += "    set udg_aiml_LocalThreatG = CreateGroup()" + nl
        init_code += "    set r = GetPlayableMapRect()" + nl
        init_code += "    if r != null then" + nl
        init_code += "        set udg_aiml_KiteMapMinX = GetRectMinX(r)" + nl
        init_code += "        set udg_aiml_KiteMapMaxX = GetRectMaxX(r)" + nl
        init_code += "        set udg_aiml_KiteMapMinY = GetRectMinY(r)" + nl
        init_code += "        set udg_aiml_KiteMapMaxY = GetRectMaxY(r)" + nl
        init_code += "    endif" + nl
        # Insert before endfunction
        src = src[:end_init] + init_code + src[end_init:]
        print("added retreat init to SalvoInit")
    
    # Check if 'local rect r' exists in SalvoInit
    salvo_init_body = src[idx3:src.find("endfunction", idx3)]
    if "local rect r" not in salvo_init_body:
        # Add local declaration
        after_takes = src.find(nl, idx3) + len(nl)
        src = src[:after_takes] + "    local rect r" + nl + src[after_takes:]
        print("added 'local rect r' to SalvoInit")

    # --- 6) Hook SalvoInit into main() if not already there ---
    if "call Trig_AIML_SalvoInit()" not in src:
        main_marker = "call RunInitializationTriggers(  )"
        idx_main = src.find(main_marker)
        if idx_main != -1:
            eol_main = src.index(nl, idx_main)
            src = src[:eol_main + len(nl)] + "    call Trig_AIML_SalvoInit()" + nl + src[eol_main + len(nl):]
            print("hooked Trig_AIML_SalvoInit() into main()")
        else:
            print("WARNING: could not find RunInitializationTriggers in main()")
    else:
        print("SalvoInit already hooked in main()")

    # --- 6b) Add -debug chat command trigger ---
    debug_func = nl + "// [V32] Debug toggle via chat command -debug" + nl
    debug_func += "function Trig_AIML_DebugToggle takes nothing returns nothing" + nl
    debug_func += "    if udg_aiml_DebugMode then" + nl
    debug_func += "        set udg_aiml_DebugMode = false" + nl
    debug_func += '        call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[AIML] Debug OFF|r")' + nl
    debug_func += "    else" + nl
    debug_func += "        set udg_aiml_DebugMode = true" + nl
    debug_func += '        call DisplayTextToForce(GetPlayersAll(), "|cffff0000[AIML] Debug ON|r")' + nl
    debug_func += "    endif" + nl
    debug_func += "endfunction" + nl + nl
    debug_func += "function Trig_AIML_DebugInit takes nothing returns nothing" + nl
    debug_func += "    local trigger t = CreateTrigger()" + nl
    debug_func += "    call TriggerRegisterPlayerChatEvent(t, Player(0), \"-debug\", true)" + nl
    debug_func += "    call TriggerRegisterPlayerChatEvent(t, Player(1), \"-debug\", true)" + nl
    debug_func += "    call TriggerAddAction(t, function Trig_AIML_DebugToggle)" + nl
    debug_func += "endfunction" + nl
    # Insert before main()
    main_func_marker = "function main takes nothing returns nothing"
    idx_mf = src.find(main_func_marker)
    if idx_mf != -1:
        src = src[:idx_mf] + debug_func + nl + src[idx_mf:]
        print("added -debug chat command trigger")
    # Hook DebugInit into main
    if "call Trig_AIML_DebugInit()" not in src:
        salvo_init_call = "    call Trig_AIML_SalvoInit()"
        idx_si = src.find(salvo_init_call)
        if idx_si != -1:
            eol_si = src.index(nl, idx_si)
            src = src[:eol_si + len(nl)] + "    call Trig_AIML_DebugInit()" + nl + src[eol_si + len(nl):]
            print("hooked Trig_AIML_DebugInit() into main()")

    # --- 7) Add chain lightning to Far Seer (Ofar) Func005A for both players ---
    # Player(0) Far Seer: add chainlightning on Player(1) units before attack lines
    old_p1_farseer = """function Trig_Computer1Combat_AI_Func005A takes nothing returns nothing
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer1Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(1), Condition(function Trig_Computer1Combat_AI_Func005Func002003001002))) )
endfunction"""
    new_p1_farseer = """function Trig_Computer1Combat_AI_Func005A takes nothing returns nothing
    // [V31] Far Seer chain lightning on enemy hero or random enemy
    call IssueTargetOrderBJ( GetEnumUnit(), "chainlightning", GroupPickRandomUnit(GetUnitsOfPlayerAll(Player(1))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer1Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(1), Condition(function Trig_Computer1Combat_AI_Func005Func002003001002))) )
endfunction"""
    old_p1_norm = old_p1_farseer.replace("\n", nl)
    new_p1_norm = new_p1_farseer.replace("\n", nl)
    if old_p1_norm in src:
        src = src.replace(old_p1_norm, new_p1_norm, 1)
        print("added chainlightning to Player(0) Far Seer")

    # Player(1) Far Seer
    old_p2_farseer = """function Trig_Computer2Combat_AI_Func005A takes nothing returns nothing
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer2Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(0), Condition(function Trig_Computer2Combat_AI_Func005Func002003001002))) )
endfunction"""
    new_p2_farseer = """function Trig_Computer2Combat_AI_Func005A takes nothing returns nothing
    // [V31] Far Seer chain lightning on enemy hero or random enemy
    call IssueTargetOrderBJ( GetEnumUnit(), "chainlightning", GroupPickRandomUnit(GetUnitsOfPlayerAll(Player(0))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer2Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(0), Condition(function Trig_Computer2Combat_AI_Func005Func002003001002))) )
endfunction"""
    old_p2_norm = old_p2_farseer.replace("\n", nl)
    new_p2_norm = new_p2_farseer.replace("\n", nl)
    if old_p2_norm in src:
        src = src.replace(old_p2_norm, new_p2_norm, 1)
        print("added chainlightning to Player(1) Far Seer")

    # --- 8) Force TC to only learn War Stomp (replace AOsw with AOws in skill tables) ---
    # AOsw = Shockwave, AOws = War Stomp. Replace all AOsw with AOws.
    count_aosw = src.count("'AOsw'")
    src = src.replace("'AOsw'", "'AOws'")
    if count_aosw > 0:
        print(f"replaced {count_aosw} occurrences of AOsw(Shockwave) with AOws(War Stomp)")

    # --- 9) Fix Far Seer skill build: 2x Chain Lightning + 1x Feral Spirit ---
    # Original: AOsf(Far Sight) x3 + AOcl x3 + AOeq
    # Want: AOcl x2 + AOfs x1 (for lv3 Far Seer) then remaining AOcl + AOfs + AOfs + AOeq
    # Replace the entire Far Seer skill sequence in both ComputerSkill tables.
    # Strategy: replace 'AOsf' (Far Sight, useless) with 'AOfs' (Feral Spirit)
    # and reorder: first AOcl, then AOcl, then AOfs, then AOcl, AOfs, AOfs, AOeq
    # Simplest: just swap all 'AOsf' -> 'AOfs' so Far Seer learns wolves instead of far sight
    count_aosf = src.count("'AOsf'")
    src = src.replace("'AOsf'", "'AOfs'")
    if count_aosf > 0:
        print(f"replaced {count_aosf} occurrences of AOsf(Far Sight) with AOfs(Feral Spirit)")

    # --- 10) Fix Shadow Hunter skill build in ComputerSkill2 ---
    # ComputerSkill2 has: AOws, AOhw, AOhw, AOws, AOhw, AOvd for Shadow Hunter (no Hex!)
    # Want: AOhx, AOhw, AOhw, AOhx, AOhw, AOvd (same as ComputerSkill1)
    # After step 8 already ran (AOsw->AOws), the pattern in source is with AOws
    old_sh_skill2 = ("    call SelectHeroSkill( GetLastCreatedUnit(), 'AOws' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOws' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOvd' )")
    new_sh_skill2 = ("    call SelectHeroSkill( GetLastCreatedUnit(), 'AOws' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhx' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhx' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOvd' )")
    if old_sh_skill2 in src:
        src = src.replace(old_sh_skill2, new_sh_skill2, 1)
        print("fixed Shadow Hunter skill build in ComputerSkill2 (added Hex)")
    else:
        print("NOTE: ComputerSkill2 Shadow Hunter pattern not found (may already be correct)")

    # --- 11) Add Far Seer smart chain lightning in PerUnitKiteCB stop phase ---
    # On stop tick, Far Seer casts chain lightning on: hero<100HP (priority) or lowest HP enemy
    # We add a new function and call it from StopCB for Far Seer units
    # Actually better: add a dedicated trigger for Far Seer in the state machine stop phase
    # Insert a new function before StopCB
    farseer_cast_func = """
// [V32] Far Seer smart chain lightning on stop tick
// Priority: enemy hero < 100 HP, else lowest HP enemy unit
function Trig_AIML_FarSeerChainLightning takes nothing returns nothing
    local unit fs = GetEnumUnit()
    local group eg
    local unit picked = null
    local unit u
    local real lowestHP = 99999.0
    local real hp
    if fs == null then
        return
    endif
    if IsUnitType(fs, UNIT_TYPE_DEAD) then
        set fs = null
        return
    endif
    if GetUnitTypeId(fs) != 'Ofar' then
        set fs = null
        return
    endif
    // Check mana (chain lightning costs 120)
    if GetUnitState(fs, UNIT_STATE_MANA) < 120.0 then
        set fs = null
        return
    endif
    // Search enemies in 700 range
    set eg = CreateGroup()
    call GroupEnumUnitsInRange(eg, GetUnitX(fs), GetUnitY(fs), 700.0, Filter(function Trig_AIML_IsThreatUnit))
    // Priority 1: enemy hero < 100 HP
    set u = FirstOfGroup(eg)
    loop
        exitwhen u == null
        if IsUnitType(u, UNIT_TYPE_HERO) and GetUnitState(u, UNIT_STATE_LIFE) < 100.0 then
            set picked = u
            set u = null
        else
            call GroupRemoveUnit(eg, u)
            set u = FirstOfGroup(eg)
        endif
    endloop
    if picked != null then
        call IssueTargetOrder(fs, "chainlightning", picked)
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[V32] FS CL -> hero(" + R2S(GetUnitState(picked, UNIT_STATE_LIFE)) + "HP)")
        endif
        call DestroyGroup(eg)
        set eg = null
        set picked = null
        set fs = null
        return
    endif
    // Priority 2: lowest HP enemy (prefer < 200 HP)
    call DestroyGroup(eg)
    set eg = CreateGroup()
    call GroupEnumUnitsInRange(eg, GetUnitX(fs), GetUnitY(fs), 700.0, Filter(function Trig_AIML_IsThreatUnit))
    set u = FirstOfGroup(eg)
    loop
        exitwhen u == null
        set hp = GetUnitState(u, UNIT_STATE_LIFE)
        if hp < lowestHP then
            set lowestHP = hp
            set picked = u
        endif
        call GroupRemoveUnit(eg, u)
        set u = FirstOfGroup(eg)
    endloop
    call DestroyGroup(eg)
    set eg = null
    if picked != null then
        call IssueTargetOrder(fs, "chainlightning", picked)
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[V32] FS CL -> unit(" + R2S(lowestHP) + "HP)")
        endif
    endif
    set picked = null
    set fs = null
endfunction

"""
    # Insert before StopCB
    stop_marker = "// [V32] Stop callback to break movement"
    idx_stop = src.find(stop_marker)
    if idx_stop != -1:
        src = src[:idx_stop] + farseer_cast_func.replace("\n", nl) + src[idx_stop:]
        print("added FarSeerChainLightning function")

    # Now modify the stop phase in state machine to also call FarSeerChainLightning
    # In the stop tick, after ForGroup StopCB, also do ForGroup FarSeerChainLightning on ranged
    old_stop_call = 'call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_StopCB)'
    new_stop_call = '''call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_StopCB)
            call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_FarSeerChainLightning)'''
    old_stop_norm = old_stop_call.replace("\n", nl)
    new_stop_norm = new_stop_call.replace("\n", nl)
    if old_stop_norm in src:
        src = src.replace(old_stop_norm, new_stop_norm, 1)
        print("added FarSeerChainLightning call in stop phase")

    # --- Write output ---
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"V31 retreat logic injected into {path}")


if __name__ == "__main__":
    main()
