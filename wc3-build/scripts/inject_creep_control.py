#!/usr/bin/env python3
"""
inject_creep_control.py - Inject Last-Hit & Blood-Line Control into training map.

Takes a war3map.j (which already has TC stomp + salvo + kite) and adds:
  1. Last-Hit system: hero approaches creeps < 200HP, attacks creeps < 100HP
  2. Blood-Line Control: when enemy DK within 1200, hold creeps at 100-150 HP
     - Melee units approach but don't attack
     - Hero attacks enemy units only
     - When DK > 1500 from creep, all-in the creep

Runs on the same 0.5s SalvoTick timer.
"""

import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: inject_creep_control.py <war3map.j>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    nl = "\r\n" if "\r\n" in src else "\n"

    # --- 1) Add creep control globals ---
    CREEP_GLOBALS = """    // [CREEP] Last-Hit & Blood-Line Control globals
    boolean udg_aiml_CreepControlEnabled = true
    real    udg_aiml_CreepLastHitHP = 100.00
    real    udg_aiml_CreepApproachHP = 200.00
    real    udg_aiml_CreepBaitMinHP = 100.00
    real    udg_aiml_CreepBaitMaxHP = 150.00
    real    udg_aiml_CreepScanRadius = 700.00
    real    udg_aiml_CreepDKDetectRadius = 1200.00
    real    udg_aiml_CreepDKSafeRadius = 1500.00
    integer udg_aiml_CreepMode = 0
    unit    udg_aiml_CreepTarget = null
    unit    udg_aiml_CreepNearbyDK = null
    real    udg_aiml_CreepTargetHP = 0.00
    group   udg_aiml_CreepScanG = null
    integer udg_aiml_CreepDebugMode = 0"""

    # Insert after existing kite globals (or after DebugMode)
    marker = "boolean udg_aiml_DebugMode = false"
    idx = src.find(marker)
    if idx == -1:
        # Try alternate
        marker = "integer udg_aiml_DebugKiteDir = 0"
        idx = src.find(marker)
    if idx == -1:
        print("ERROR: cannot find globals insertion point")
        sys.exit(1)
    eol = src.index(nl, idx)
    src = src[:eol + len(nl)] + CREEP_GLOBALS + nl + src[eol + len(nl):]
    print("inserted creep control globals")

    # --- 2) Add creep control functions ---
    # Insert before Trig_AIML_IsThreatUnit (the first kite helper)
    CREEP_FUNCTIONS = """
// ================================================================
// [CREEP] Last-Hit & Blood-Line Control System
// ================================================================

// Filter: neutral aggressive units (creeps)
function Trig_AIML_IsCreepUnit takes nothing returns boolean
    local unit u = GetFilterUnit()
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return false
    endif
    if GetOwningPlayer(u) != Player(PLAYER_NEUTRAL_AGGRESSIVE) then
        set u = null
        return false
    endif
    set u = null
    return true
endfunction

// Filter: enemy DK (Udea) for blood-line detection
function Trig_AIML_IsDKFilter takes nothing returns boolean
    local unit u = GetFilterUnit()
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return false
    endif
    if GetUnitTypeId(u) != 'Udea' then
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

// Find lowest HP creep in range (for last-hit)
function Trig_AIML_FindLowHPCreep takes real cx, real cy, real radius, real maxHP returns unit
    local group g = CreateGroup()
    local unit u
    local unit best = null
    local real bestHP = 99999.0
    local real hp
    call GroupEnumUnitsInRange(g, cx, cy, radius, Filter(function Trig_AIML_IsCreepUnit))
    set u = FirstOfGroup(g)
    loop
        exitwhen u == null
        set hp = GetUnitState(u, UNIT_STATE_LIFE)
        if hp < maxHP and hp < bestHP and hp > 0 then
            set bestHP = hp
            set best = u
        endif
        call GroupRemoveUnit(g, u)
        set u = FirstOfGroup(g)
    endloop
    call DestroyGroup(g)
    set g = null
    return best
endfunction

// Find nearby enemy DK
function Trig_AIML_FindNearbyDK takes real cx, real cy, real radius returns unit
    local group g = CreateGroup()
    local unit u
    local unit dk = null
    call GroupEnumUnitsInRange(g, cx, cy, radius, Filter(function Trig_AIML_IsDKFilter))
    set dk = FirstOfGroup(g)
    call DestroyGroup(g)
    set g = null
    return dk
endfunction

// Get distance between unit and point
function Trig_AIML_DistUnitToPoint takes unit u, real px, real py returns real
    local real dx = GetUnitX(u) - px
    local real dy = GetUnitY(u) - py
    return SquareRoot(dx*dx + dy*dy)
endfunction

// [CREEP] Melee callback: approach creep but don't attack (bait mode)
function Trig_AIML_CreepBaitMeleeCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    if IsUnitType(u, UNIT_TYPE_HERO) then
        // Heroes don't get bait-move orders here
        set u = null
        return
    endif
    if IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set u = null
        return
    endif
    if udg_aiml_CreepTarget == null then
        set u = null
        return
    endif
    // Move near creep but don't attack
    call IssuePointOrder(u, "smart", GetUnitX(udg_aiml_CreepTarget), GetUnitY(udg_aiml_CreepTarget))
    set u = null
endfunction

// [CREEP] All-in callback: everyone attacks the creep
function Trig_AIML_CreepAllInCB takes nothing returns nothing
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
    if udg_aiml_CreepTarget == null then
        set u = null
        return
    endif
    call IssueTargetOrder(u, "smart", udg_aiml_CreepTarget)
    set u = null
endfunction

// ================================================================
// [CREEP] Main decision function - called every SalvoTick
// Returns true if creep control took over (skip normal salvo)
// ================================================================
function Trig_AIML_CreepControlTick takes nothing returns boolean
    local real cx
    local real cy
    local unit creep
    local unit dk
    local real creepHP
    local real dkDistToCreep
    local group armyG
    if not udg_aiml_CreepControlEnabled then
        return false
    endif
    // Use ranged centroid as reference point (or first hero position)
    if udg_aiml_SalvoRangedCount < 1 then
        return false
    endif
    set cx = udg_aiml_RangedCentroidX
    set cy = udg_aiml_RangedCentroidY
    // If centroid is 0,0 (not computed yet), skip
    if cx == 0.0 and cy == 0.0 then
        return false
    endif

    // --- Phase 1: Scan for low HP creeps ---
    set creep = Trig_AIML_FindLowHPCreep(cx, cy, udg_aiml_CreepScanRadius, udg_aiml_CreepApproachHP)
    if creep == null then
        // No low HP creeps nearby, normal behavior
        set udg_aiml_CreepMode = 0
        set udg_aiml_CreepTarget = null
        return false
    endif

    set creepHP = GetUnitState(creep, UNIT_STATE_LIFE)
    set udg_aiml_CreepTarget = creep
    set udg_aiml_CreepTargetHP = creepHP

    // --- Phase 2: Check for nearby enemy DK (blood-line control) ---
    set dk = Trig_AIML_FindNearbyDK(GetUnitX(creep), GetUnitY(creep), udg_aiml_CreepDKDetectRadius)
    set udg_aiml_CreepNearbyDK = dk

    if dk != null then
        // DK is near! Blood-line control mode
        set dkDistToCreep = Trig_AIML_DistUnitToPoint(dk, GetUnitX(creep), GetUnitY(creep))

        if dkDistToCreep > udg_aiml_CreepDKSafeRadius then
            // DK moved away (> 1500), all-in the creep!
            set udg_aiml_CreepMode = 3
            set armyG = GetUnitsOfPlayerAll(udg_aiml_SalvoOwnerPlayer)
            call ForGroup(armyG, function Trig_AIML_CreepAllInCB)
            call DestroyGroup(armyG)
            set armyG = null
            if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "[CREEP] ALL-IN! DK dist=" + R2S(dkDistToCreep) + " creepHP=" + R2S(creepHP))
            endif
            return true
        endif

        if creepHP >= udg_aiml_CreepBaitMinHP and creepHP <= udg_aiml_CreepBaitMaxHP then
            // Creep in bait zone (100-150 HP), hold!
            // Melee: approach but don't attack
            // Hero: attack enemy units (DK or skeletons)
            set udg_aiml_CreepMode = 2
            set armyG = GetUnitsOfPlayerAll(udg_aiml_SalvoOwnerPlayer)
            call ForGroup(armyG, function Trig_AIML_CreepBaitMeleeCB)
            call DestroyGroup(armyG)
            set armyG = null
            // Hero attacks DK
            call IssueTargetOrder(GroupPickRandomUnit(GetUnitsOfPlayerAndTypeId(udg_aiml_SalvoOwnerPlayer, 'Hamg')), "smart", dk)
            call IssueTargetOrder(GroupPickRandomUnit(GetUnitsOfPlayerAndTypeId(udg_aiml_SalvoOwnerPlayer, 'Ofar')), "smart", dk)
            if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "[CREEP] BAIT MODE creepHP=" + R2S(creepHP) + " DKdist=" + R2S(dkDistToCreep))
            endif
            return true
        endif

        if creepHP < udg_aiml_CreepBaitMinHP then
            // Creep too low (< 100), DON'T attack it (let DK waste DC)
            // Just hold position near creep
            set udg_aiml_CreepMode = 2
            set armyG = GetUnitsOfPlayerAll(udg_aiml_SalvoOwnerPlayer)
            call ForGroup(armyG, function Trig_AIML_CreepBaitMeleeCB)
            call DestroyGroup(armyG)
            set armyG = null
            if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "[CREEP] HOLD (creep too low) HP=" + R2S(creepHP) + " waiting DK waste DC")
            endif
            return true
        endif

        // Creep HP > 150 but DK nearby: continue attacking creep normally
        // (will naturally reduce HP to bait zone)
        set udg_aiml_CreepMode = 1
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[CREEP] FARMING (DK near) creepHP=" + R2S(creepHP))
        endif
        return false
    endif

    // --- Phase 3: No DK nearby, pure last-hit mode ---
    if creepHP < udg_aiml_CreepLastHitHP then
        // HP < 100: ALL-IN last hit!
        set udg_aiml_CreepMode = 3
        set armyG = GetUnitsOfPlayerAll(udg_aiml_SalvoOwnerPlayer)
        call ForGroup(armyG, function Trig_AIML_CreepAllInCB)
        call DestroyGroup(armyG)
        set armyG = null
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[CREEP] LAST HIT! creepHP=" + R2S(creepHP))
        endif
        return true
    elseif creepHP < udg_aiml_CreepApproachHP then
        // HP 100-200: Hero approaches (prepare for last hit)
        set udg_aiml_CreepMode = 1
        call IssuePointOrder(GroupPickRandomUnit(GetUnitsOfPlayerAndTypeId(udg_aiml_SalvoOwnerPlayer, 'Ofar')), "smart", GetUnitX(creep), GetUnitY(creep))
        call IssuePointOrder(GroupPickRandomUnit(GetUnitsOfPlayerAndTypeId(udg_aiml_SalvoOwnerPlayer, 'Hamg')), "smart", GetUnitX(creep), GetUnitY(creep))
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[CREEP] APPROACH creepHP=" + R2S(creepHP))
        endif
        return false
    endif

    set udg_aiml_CreepMode = 0
    return false
endfunction

"""

    # Insert before the first kite function
    kite_marker = "// [V32] Per-unit kite: each ranged unit dodges individually"
    idx2 = src.find(kite_marker)
    if idx2 == -1:
        # Try alternate marker
        kite_marker = "function Trig_AIML_IsThreatUnit takes nothing returns boolean"
        idx2 = src.find(kite_marker)
    if idx2 == -1:
        print("ERROR: cannot find insertion point for creep functions")
        sys.exit(1)
    src = src[:idx2] + CREEP_FUNCTIONS.replace("\n", nl) + src[idx2:]
    print("inserted creep control functions")

    # --- 3) Hook CreepControlTick into SalvoForPlayer ---
    # Insert call at the very beginning of the retreat logic block
    # (before DecideRetreatForTick, so creep control has highest priority)
    retreat_marker = "    // [V32] Per-unit kite state machine"
    idx3 = src.find(retreat_marker)
    if idx3 == -1:
        print("ERROR: cannot find state machine insertion point")
        sys.exit(1)

    creep_hook = """    // [CREEP] Creep control has highest priority
    if Trig_AIML_CreepControlTick() then
        return
    endif
"""
    src = src[:idx3] + creep_hook.replace("\n", nl) + src[idx3:]
    print("hooked CreepControlTick into SalvoForPlayer")

    # --- 4) Init creep scan group in SalvoInit ---
    init_marker = "set udg_aiml_LocalThreatG = CreateGroup()"
    idx4 = src.find(init_marker)
    if idx4 != -1:
        eol4 = src.index(nl, idx4)
        src = src[:eol4 + len(nl)] + "    set udg_aiml_CreepScanG = CreateGroup()" + nl + src[eol4 + len(nl):]
        print("added CreepScanG init to SalvoInit")

    # --- 5) Add -creep chat command to toggle creep control ---
    debug_toggle_marker = "function Trig_AIML_DebugToggle takes nothing returns nothing"
    idx5 = src.find(debug_toggle_marker)
    if idx5 != -1:
        creep_toggle = nl + "// [CREEP] Toggle creep control via -creep command" + nl
        creep_toggle += "function Trig_AIML_CreepToggle takes nothing returns nothing" + nl
        creep_toggle += "    if udg_aiml_CreepControlEnabled then" + nl
        creep_toggle += "        set udg_aiml_CreepControlEnabled = false" + nl
        creep_toggle += '        call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[AIML] Creep Control OFF|r")' + nl
        creep_toggle += "    else" + nl
        creep_toggle += "        set udg_aiml_CreepControlEnabled = true" + nl
        creep_toggle += '        call DisplayTextToForce(GetPlayersAll(), "|cffff0000[AIML] Creep Control ON|r")' + nl
        creep_toggle += "    endif" + nl
        creep_toggle += "endfunction" + nl
        src = src[:idx5] + creep_toggle.replace("\n", nl) + nl + src[idx5:]
        print("added -creep toggle function")

    # Register -creep command in DebugInit
    debug_init_body = '    call TriggerRegisterPlayerChatEvent(t, Player(0), "-debug", true)'
    idx6 = src.find(debug_init_body)
    if idx6 != -1:
        eol6 = src.index(nl, idx6)
        creep_reg = nl + "    // [CREEP] Register -creep toggle" + nl
        creep_reg += "    set t = CreateTrigger()" + nl
        creep_reg += '    call TriggerRegisterPlayerChatEvent(t, Player(0), "-creep", true)' + nl
        creep_reg += '    call TriggerRegisterPlayerChatEvent(t, Player(1), "-creep", true)' + nl
        creep_reg += "    call TriggerAddAction(t, function Trig_AIML_CreepToggle)" + nl
        # Find endfunction of DebugInit
        endfunc_marker = "endfunction"
        # Find the DebugInit's endfunction (after the -debug registrations)
        search_start = idx6 + len(debug_init_body)
        endfunc_idx = src.find(endfunc_marker, search_start)
        if endfunc_idx != -1:
            src = src[:endfunc_idx] + creep_reg.replace("\n", nl) + src[endfunc_idx:]
            print("registered -creep chat command")


    # --- 6) Remove original AI "attack neutral" triggers that conflict ---
    # These lines make heroes attack random neutral creeps every second,
    # overriding our precise creep control.
    lines = src.split(nl)
    disabled_count = 0
    new_lines = []
    for line in lines:
        if 'PLAYER_NEUTRAL_AGGRESSIVE' in line and '"attack"' in line and 'IssueTargetOrderBJ' in line:
            new_lines.append("    // [CREEP] Disabled: " + line.strip())
            disabled_count += 1
        else:
            new_lines.append(line)
    src = nl.join(new_lines)
    if disabled_count > 0:
        print(f"disabled {disabled_count} original neutral-attack triggers")

    # --- Write output ---
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"Creep control injected into {path}")


if __name__ == "__main__":
    main()
