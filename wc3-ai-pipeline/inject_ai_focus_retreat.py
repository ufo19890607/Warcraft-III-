#!/usr/bin/env python3
"""
inject_focus_retreat.py V35 - Inject focus-fire retreat protection.

When any AI unit (including heroes) loses >20% max HP in a single 0.5s tick,
issue a "smart" order 300 distance away from the enemy centroid.
One-shot: after issuing the retreat order, the unit is left to AI normal behavior.

Priority: LOWER than creep control (补刀优先).
Runs inside SalvoTick after creep control, before SalvoForPlayer.

Implementation:
  - Uses a hashtable to store last-tick HP for each unit.
  - Each tick: scan all units of owner, compare current HP vs stored HP.
  - If delta > 20% of max HP → retreat order.
  - Update stored HP for all units.
"""

import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: inject_focus_retreat.py <war3map.j>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    nl = "\r\n" if "\r\n" in src else "\n"

    # --- 1) Add focus retreat globals ---
    FOCUS_GLOBALS = """    // [FOCUS V35] Focus-fire retreat protection globals
    boolean udg_aiml_FocusRetreatEnabled = true
    real    udg_aiml_FocusRetreatThreshold = 0.20
    real    udg_aiml_FocusRetreatDist = 300.00
    hashtable udg_aiml_FocusHPTable = null"""

    # Insert after CreepControlEnabled or DebugMode
    marker = "boolean udg_aiml_CreepControlEnabled = true"
    idx = src.find(marker)
    if idx == -1:
        marker = "boolean udg_aiml_DebugMode = false"
        idx = src.find(marker)
    if idx == -1:
        print("ERROR: cannot find globals insertion point for focus retreat")
        sys.exit(1)
    eol = src.index(nl, idx)
    src = src[:eol + len(nl)] + FOCUS_GLOBALS + nl + src[eol + len(nl):]
    print("[FOCUS V35] inserted focus retreat globals")

    # --- 2) Add focus retreat functions (before SalvoTick) ---
    FOCUS_FUNCTIONS = r"""
// ================================================================
// [FOCUS V35] Focus-fire Retreat Protection
// If a unit loses >20% max HP in one tick, retreat 300 away from enemy.
// One-shot: issue order once, then let AI resume.
// ================================================================

// Compute enemy centroid for a player
function Trig_AIML_FocusEnemyCentroid takes player enemy, real array cx, real array cy returns nothing
    local group g = CreateGroup()
    local unit u
    local real sx = 0.0
    local real sy = 0.0
    local integer count = 0
    call GroupEnumUnitsOfPlayer(g, enemy, null)
    set u = FirstOfGroup(g)
    loop
        exitwhen u == null
        if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set sx = sx + GetUnitX(u)
            set sy = sy + GetUnitY(u)
            set count = count + 1
        endif
        call GroupRemoveUnit(g, u)
        set u = FirstOfGroup(g)
    endloop
    call DestroyGroup(g)
    set g = null
    if count > 0 then
        set cx[0] = sx / I2R(count)
        set cy[0] = sy / I2R(count)
    else
        set cx[0] = 0.0
        set cy[0] = 0.0
    endif
endfunction

// [FOCUS V35] Main scan for one player. Check all units for HP drop.
function Trig_AIML_FocusRetreatForPlayer takes player owner, player enemy returns nothing
    local group g
    local unit u
    local integer uid
    local real curHP
    local real maxHP
    local real lastHP
    local real drop
    local real ecx
    local real ecy
    local real ux
    local real uy
    local real dx
    local real dy
    local real dist
    local real retreatX
    local real retreatY
    local boolean needCentroid = true
    local integer retreated = 0

    if not udg_aiml_FocusRetreatEnabled then
        return
    endif

    set ecx = 0.0
    set ecy = 0.0

    set g = CreateGroup()
    call GroupEnumUnitsOfPlayer(g, owner, null)
    set u = FirstOfGroup(g)
    loop
        exitwhen u == null
        if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set uid = GetHandleId(u)
            set curHP = GetUnitState(u, UNIT_STATE_LIFE)
            set maxHP = GetUnitState(u, UNIT_STATE_MAX_LIFE)
            set lastHP = LoadReal(udg_aiml_FocusHPTable, uid, 0)

            // Check if HP dropped significantly
            if lastHP > 0.0 and maxHP > 0.0 then
                set drop = lastHP - curHP
                if drop > maxHP * udg_aiml_FocusRetreatThreshold then
                    // Unit is being focused! Retreat away from enemy centroid.
                    if needCentroid then
                        // Compute enemy centroid (only once per tick per player)
                        set needCentroid = false
                        // Inline centroid calculation
                        call GroupClear(g)
                        call GroupEnumUnitsOfPlayer(g, enemy, null)
                        loop
                            set u = FirstOfGroup(g)
                            exitwhen u == null
                            if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
                                set ecx = ecx + GetUnitX(u)
                                set ecy = ecy + GetUnitY(u)
                                set retreated = retreated + 1
                            endif
                            call GroupRemoveUnit(g, u)
                        endloop
                        if retreated > 0 then
                            set ecx = ecx / I2R(retreated)
                            set ecy = ecy / I2R(retreated)
                        endif
                        set retreated = 0
                        // Re-enum owner units (we consumed g)
                        call GroupEnumUnitsOfPlayer(g, owner, null)
                        set u = FirstOfGroup(g)
                        // We need to restart the loop but can't easily.
                        // Simpler: break and do a second pass.
                        call DestroyGroup(g)
                        set g = null
                        // Do second pass with centroid known
                        call Trig_AIML_FocusRetreatPass2(owner, ecx, ecy)
                        return
                    endif
                endif
            endif

            // Store current HP for next tick
            call SaveReal(udg_aiml_FocusHPTable, uid, 0, curHP)
        endif
        call GroupRemoveUnit(g, u)
        set u = FirstOfGroup(g)
    endloop
    call DestroyGroup(g)
    set g = null
endfunction

// [FOCUS V35] Second pass: already know enemy centroid, check all units and retreat the focused ones
function Trig_AIML_FocusRetreatPass2 takes player owner, real ecx, real ecy returns nothing
    local group g = CreateGroup()
    local unit u
    local integer uid
    local real curHP
    local real maxHP
    local real lastHP
    local real drop
    local real ux
    local real uy
    local real dx
    local real dy
    local real dist
    local real retreatX
    local real retreatY

    call GroupEnumUnitsOfPlayer(g, owner, null)
    set u = FirstOfGroup(g)
    loop
        exitwhen u == null
        if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set uid = GetHandleId(u)
            set curHP = GetUnitState(u, UNIT_STATE_LIFE)
            set maxHP = GetUnitState(u, UNIT_STATE_MAX_LIFE)
            set lastHP = LoadReal(udg_aiml_FocusHPTable, uid, 0)

            if lastHP > 0.0 and maxHP > 0.0 then
                set drop = lastHP - curHP
                if drop > maxHP * udg_aiml_FocusRetreatThreshold then
                    // Retreat this unit!
                    set ux = GetUnitX(u)
                    set uy = GetUnitY(u)
                    set dx = ux - ecx
                    set dy = uy - ecy
                    set dist = SquareRoot(dx*dx + dy*dy)
                    if dist < 1.0 then
                        set dist = 1.0
                    endif
                    // Normalize and scale to retreat distance
                    set retreatX = ux + (dx / dist) * udg_aiml_FocusRetreatDist
                    set retreatY = uy + (dy / dist) * udg_aiml_FocusRetreatDist
                    call IssuePointOrder(u, "smart", retreatX, retreatY)
                    if udg_aiml_DebugMode then
                        call DisplayTextToForce(GetPlayersAll(), "[FOCUS] " + GetUnitName(u) + " HP-" + R2S(drop) + " retreat!")
                    endif
                endif
            endif

            // Update stored HP
            call SaveReal(udg_aiml_FocusHPTable, uid, 0, curHP)
        endif
        call GroupRemoveUnit(g, u)
        set u = FirstOfGroup(g)
    endloop
    call DestroyGroup(g)
    set g = null
endfunction

"""

    # Wait — the above has a control flow issue (ForGroup consumed during centroid calc).
    # Simpler approach: split into two phases cleanly.
    # Rewrite to a cleaner version:

    FOCUS_FUNCTIONS = r"""
// ================================================================
// [FOCUS V35] Focus-fire Retreat Protection
// If a unit loses >20% max HP in one 0.5s tick, retreat 300 away from enemy.
// One-shot: issue order once, then let AI resume next tick.
// ================================================================

// [FOCUS V35] Compute enemy centroid (simple inline)
function Trig_AIML_FocusGetEnemyCentroid takes player enemy returns nothing
    local group g = CreateGroup()
    local unit u
    local real sx = 0.0
    local real sy = 0.0
    local integer n = 0
    call GroupEnumUnitsOfPlayer(g, enemy, null)
    set u = FirstOfGroup(g)
    loop
        exitwhen u == null
        if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set sx = sx + GetUnitX(u)
            set sy = sy + GetUnitY(u)
            set n = n + 1
        endif
        call GroupRemoveUnit(g, u)
        set u = FirstOfGroup(g)
    endloop
    call DestroyGroup(g)
    set g = null
    if n > 0 then
        set udg_aiml_FocusEnemyCX = sx / I2R(n)
        set udg_aiml_FocusEnemyCY = sy / I2R(n)
    else
        set udg_aiml_FocusEnemyCX = 0.0
        set udg_aiml_FocusEnemyCY = 0.0
    endif
endfunction

// [FOCUS V35] Main: scan all units of owner, detect focus, retreat
function Trig_AIML_FocusRetreatForPlayer takes player owner, player enemy returns nothing
    local group g
    local unit u
    local integer uid
    local real curHP
    local real maxHP
    local real lastHP
    local real drop
    local real ux
    local real uy
    local real dx
    local real dy
    local real dist
    local real retreatX
    local real retreatY
    local boolean centroidDone = false

    if not udg_aiml_FocusRetreatEnabled then
        return
    endif

    // Phase 1: update HP table and detect focused units
    set g = CreateGroup()
    call GroupEnumUnitsOfPlayer(g, owner, null)
    set u = FirstOfGroup(g)
    loop
        exitwhen u == null
        if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set uid = GetHandleId(u)
            set curHP = GetUnitState(u, UNIT_STATE_LIFE)
            set maxHP = GetUnitState(u, UNIT_STATE_MAX_LIFE)
            set lastHP = LoadReal(udg_aiml_FocusHPTable, uid, 0)

            if lastHP > 0.0 and maxHP > 0.0 then
                set drop = lastHP - curHP
                if drop > maxHP * udg_aiml_FocusRetreatThreshold then
                    // This unit is being focused!
                    if not centroidDone then
                        call Trig_AIML_FocusGetEnemyCentroid(enemy)
                        set centroidDone = true
                    endif
                    // Retreat away from enemy centroid
                    set ux = GetUnitX(u)
                    set uy = GetUnitY(u)
                    set dx = ux - udg_aiml_FocusEnemyCX
                    set dy = uy - udg_aiml_FocusEnemyCY
                    set dist = SquareRoot(dx*dx + dy*dy)
                    if dist < 1.0 then
                        set dist = 1.0
                    endif
                    set retreatX = ux + (dx / dist) * udg_aiml_FocusRetreatDist
                    set retreatY = uy + (dy / dist) * udg_aiml_FocusRetreatDist
                    call IssuePointOrder(u, "smart", retreatX, retreatY)
                    if udg_aiml_DebugMode then
                        call DisplayTextToForce(GetPlayersAll(), "[FOCUS] " + GetUnitName(u) + " -" + I2S(R2I(drop)) + "HP retreat!")
                    endif
                endif
            endif

            // Store current HP for next tick comparison
            call SaveReal(udg_aiml_FocusHPTable, uid, 0, curHP)
        endif
        call GroupRemoveUnit(g, u)
        set u = FirstOfGroup(g)
    endloop
    call DestroyGroup(g)
    set g = null
endfunction

"""

    # Find insertion point: before SalvoTick (after creep functions if present)
    salvo_tick_marker = "function Trig_AIML_SalvoTick takes nothing returns nothing"
    idx2 = src.find(salvo_tick_marker)
    if idx2 == -1:
        print("ERROR: cannot find Trig_AIML_SalvoTick")
        sys.exit(1)
    src = src[:idx2] + FOCUS_FUNCTIONS.replace("\n", nl) + src[idx2:]
    print("[FOCUS V35] inserted focus retreat functions before SalvoTick")

    # --- 3) Add FocusEnemyCX/CY globals ---
    FOCUS_GLOBALS2 = """    real    udg_aiml_FocusEnemyCX = 0.0
    real    udg_aiml_FocusEnemyCY = 0.0"""

    # Insert right after the first FOCUS globals block
    after_marker = "hashtable udg_aiml_FocusHPTable = null"
    idx3 = src.find(after_marker)
    if idx3 != -1:
        eol3 = src.index(nl, idx3)
        src = src[:eol3 + len(nl)] + FOCUS_GLOBALS2 + nl + src[eol3 + len(nl):]
        print("[FOCUS V35] inserted FocusEnemyCX/CY globals")

    # --- 4) Hook into SalvoTick: after creep control, before SalvoForPlayer ---
    # Current SalvoTick (after V35 creep injection) looks like:
    #   set creep0 = Trig_AIML_CreepControlForPlayer(P0, P1)
    #   set creep1 = Trig_AIML_CreepControlForPlayer(P1, P0)
    #   if not creep0 then call SalvoForPlayer(...)
    #   if not creep1 then call SalvoForPlayer(...)
    # We insert focus retreat AFTER creep lines but BEFORE the if-not-creep salvo calls.
    # Focus retreat doesn't block salvo — it runs independently (one-shot retreat for focused units).

    # SalvoTick hook is managed by inject_ai_creep_control.py which calls FocusRetreatForPlayer directly
    # No hook needed here
    print("[FOCUS V35] functions injected; SalvoTick managed by creep_control")

    # --- 5) Initialize hashtable in SalvoInit ---
    init_marker = "set udg_aiml_SalvoEnemyG = CreateGroup()"
    idx5 = src.find(init_marker)
    if idx5 != -1:
        eol5 = src.index(nl, idx5)
        src = src[:eol5 + len(nl)] + "    set udg_aiml_FocusHPTable = InitHashtable()" + nl + src[eol5 + len(nl):]
        print("[FOCUS V35] added FocusHPTable init to SalvoInit")
    else:
        print("WARNING: could not find SalvoInit insertion point for hashtable init")

    # --- Write output ---
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[FOCUS V35] Focus retreat injected into {path}")


if __name__ == "__main__":
    main()
