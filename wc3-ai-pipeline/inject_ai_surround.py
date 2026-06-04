#!/usr/bin/env python3
"""
inject_surround.py V39 - Inject Surround/Encircle AI into training map.

Features (V39.06):
  - SurroundQuadrantCheck: checks all four quadrants within 800-radius to detect Phase 2
  - SurroundMoveCB:
      * Attack mode (SurroundAttacking=true): all units smart-attack target directly
      * Phase 2 (surrounded): move to target center (squeeze)
      * Phase 1 (encircling): pass-through move, 200 units past target
  - SurroundFindTarget: enemy hero first, then first alive unit
  - SurroundTick:
      * Only for computer-controlled players
      * Auto-downgrade: unit count < 8 -> fallback to CreepControlForPlayer + reset CreepMode=0
      * Still-tick detection: target moves < 50 units -> increment counter;
        >= 6 ticks still -> SurroundAttacking=true; moves >= 50 -> reset to encircle
      * Phase 2 check -> SurroundMoveCB
  - SurroundToggle: -surround command -> Round1Mode=1, Round1Pref=1
  - CreepModeToggle: -creep command -> Round1Mode=0, Round1Pref=0
  - SurroundInit: registers -surround and -creep chat commands
  - Globals: Round1Mode, Round1Pref, SurroundTarget/X/Y, SurroundPrevX/Y, SurroundPhase2,
             SurroundStillTicks, SurroundAttacking

Prerequisites: inject_creep_control.py must have already been run
               (SurroundTick calls CreepControlForPlayer, SalvoTick uses Round1Mode).
"""

import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: inject_surround.py <war3map.j>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    nl = "\r\n" if "\r\n" in src else "\n"

    # ------------------------------------------------------------------ #
    # Guard: skip if already injected
    # ------------------------------------------------------------------ #
    if "function Trig_AIML_SurroundTick" in src:
        print("[V39] Surround already injected, skipping")
        return

    # ------------------------------------------------------------------ #
    # 1) Globals
    # ------------------------------------------------------------------ #
    SURROUND_GLOBALS = """    // [SURROUND V39] Encircle/Surround system globals
    integer udg_aiml_Round1Mode = 0
    integer udg_aiml_Round1Pref = 1  // default ON: auto-enable creep mode in Round 1
    unit    udg_aiml_SurroundTarget = null
    real    udg_aiml_SurroundTargetX = 0.0
    real    udg_aiml_SurroundTargetY = 0.0
    real    udg_aiml_SurroundPrevX = 0.0
    real    udg_aiml_SurroundPrevY = 0.0
    boolean udg_aiml_SurroundPhase2 = false
    integer udg_aiml_SurroundStillTicks = 0
    boolean udg_aiml_SurroundAttacking = false"""

    # Insert after CreepMode global (injected by inject_creep_control.py)
    marker = "integer udg_aiml_CreepMode = 0"
    idx = src.find(marker)
    if idx == -1:
        # Fallback: after DebugMode
        marker = "boolean udg_aiml_DebugMode"
        idx = src.find(marker)
    if idx == -1:
        print("ERROR: cannot find globals insertion point")
        sys.exit(1)
    eol = src.index(nl, idx)
    src = src[:eol + len(nl)] + SURROUND_GLOBALS + nl + src[eol + len(nl):]
    print("[V39] inserted surround globals")

    # ------------------------------------------------------------------ #
    # 2) Functions (insert before SalvoTick)
    # ------------------------------------------------------------------ #
    SURROUND_FUNCTIONS = r"""
// ================================================================
// [SURROUND V39] Encircle + Squeeze AI System
// Active in Round 1 when Round1Mode == 1 (-surround command).
// ================================================================

// Check if player's army covers all four quadrants around (tx,ty) within radius
function Trig_AIML_SurroundQuadrantCheck takes player p, real tx, real ty, real radius returns boolean
    local group g = CreateGroup()
    local unit u
    local boolean hasNE = false
    local boolean hasNW = false
    local boolean hasSE = false
    local boolean hasSW = false
    local real ux
    local real uy
    call GroupEnumUnitsOfPlayer(g, p, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set ux = GetUnitX(u) - tx
            set uy = GetUnitY(u) - ty
            if ux * ux + uy * uy <= radius * radius then
                if ux >= 0 and uy >= 0 then
                    set hasNE = true
                elseif ux < 0 and uy >= 0 then
                    set hasNW = true
                elseif ux >= 0 and uy < 0 then
                    set hasSE = true
                else
                    set hasSW = true
                endif
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    return hasNE and hasNW and hasSE and hasSW
endfunction

// Move callback: encircle or squeeze or attack the surround target
function Trig_AIML_SurroundMoveCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real ux
    local real uy
    local real tx = udg_aiml_SurroundTargetX
    local real ty = udg_aiml_SurroundTargetY
    local real dx
    local real dy
    local real dist
    local real moveX
    local real moveY
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) or IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set u = null
        return
    endif
    // Attack mode: target trapped (still >=6 ticks) -> all units attack directly
    if udg_aiml_SurroundAttacking then
        if udg_aiml_SurroundTarget != null then
            call IssueTargetOrder(u, "smart", udg_aiml_SurroundTarget)
        endif
        set u = null
        return
    endif
    set ux = GetUnitX(u)
    set uy = GetUnitY(u)
    if udg_aiml_SurroundPhase2 then
        // Phase 2: all quadrants covered -> squeeze to center
        call IssuePointOrder(u, "move", tx, ty)
    else
        // Phase 1: pass through -> move 200 units past target on opposite side
        set dx = ux - tx
        set dy = uy - ty
        set dist = SquareRoot(dx * dx + dy * dy)
        if dist < 10.0 then
            set dist = 10.0
        endif
        set moveX = tx - (dx / dist) * 200.0
        set moveY = ty - (dy / dist) * 200.0
        call IssuePointOrder(u, "move", moveX, moveY)
    endif
    set u = null
endfunction

// Find surround target: enemy hero first, then first alive unit
function Trig_AIML_SurroundFindTarget takes player enemyPlayer returns unit
    local group g = CreateGroup()
    local unit u
    local unit best = null
    call GroupEnumUnitsOfPlayer(g, enemyPlayer, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitType(u, UNIT_TYPE_DEAD) then
            if IsUnitType(u, UNIT_TYPE_HERO) then
                call DestroyGroup(g)
                set g = null
                return u
            endif
            if best == null then
                set best = u
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    return best
endfunction

// [SURROUND V39] Main surround tick - called in Round 1 when Round1Mode==1
function Trig_AIML_SurroundTick takes player p, player ep returns nothing
    local group g
    local real tx
    local real ty
    local real ddx
    local real ddy
    local integer unitCount
    local unit u
    // Only for computer-controlled players
    if GetPlayerController(p) != MAP_CONTROL_COMPUTER then
        return
    endif
    // Auto-downgrade: fewer than 8 alive units -> fall back to creep control
    set g = CreateGroup()
    set unitCount = 0
    call GroupEnumUnitsOfPlayer(g, p, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set unitCount = unitCount + 1
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    if unitCount < 8 then
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[SURROUND] unit count=" + I2S(unitCount) + " <8, fallback to creep")
        endif
        call Trig_AIML_CreepControlForPlayer(p, ep)
        set udg_aiml_CreepMode = 0
        return
    endif
    // Find target
    set udg_aiml_SurroundTarget = Trig_AIML_SurroundFindTarget(ep)
    if udg_aiml_SurroundTarget == null then
        return
    endif
    if IsUnitType(udg_aiml_SurroundTarget, UNIT_TYPE_DEAD) then
        set udg_aiml_SurroundTarget = null
        return
    endif
    set tx = GetUnitX(udg_aiml_SurroundTarget)
    set ty = GetUnitY(udg_aiml_SurroundTarget)
    set udg_aiml_SurroundTargetX = tx
    set udg_aiml_SurroundTargetY = ty
    // Check if target has moved since last tick (threshold 50 units = 2500 sq)
    set ddx = tx - udg_aiml_SurroundPrevX
    set ddy = ty - udg_aiml_SurroundPrevY
    if ddx * ddx + ddy * ddy < 2500.0 then
        // Target still: increment still counter
        set udg_aiml_SurroundStillTicks = udg_aiml_SurroundStillTicks + 1
        if udg_aiml_SurroundStillTicks >= 6 then
            set udg_aiml_SurroundAttacking = true
        endif
    else
        // Target moved: escaped -> reset to encircle
        set udg_aiml_SurroundStillTicks = 0
        set udg_aiml_SurroundAttacking = false
    endif
    // Phase 2 check
    set udg_aiml_SurroundPhase2 = Trig_AIML_SurroundQuadrantCheck(p, tx, ty, 800.0)
    if udg_aiml_DebugMode then
        if udg_aiml_SurroundPhase2 then
            call DisplayTextToForce(GetPlayersAll(), "[SURROUND] Phase 2 SQUEEZE on " + GetUnitName(udg_aiml_SurroundTarget))
        else
            call DisplayTextToForce(GetPlayersAll(), "[SURROUND] Phase 1 ENCIRCLE on " + GetUnitName(udg_aiml_SurroundTarget))
        endif
    endif
    // Issue move orders
    set g = CreateGroup()
    call GroupEnumUnitsOfPlayer(g, p, null)
    call ForGroup(g, function Trig_AIML_SurroundMoveCB)
    call DestroyGroup(g)
    set g = null
    // Save position for next tick
    set udg_aiml_SurroundPrevX = tx
    set udg_aiml_SurroundPrevY = ty
endfunction

// -surround: activate surround mode in Round 1
function Trig_AIML_SurroundToggle takes nothing returns nothing
    set udg_aiml_Round1Mode = 1
    set udg_aiml_Round1Pref = 1
    call DisplayTextToForce(GetPlayersAll(), "|cffff8800[AIML] Round 1 mode: SURROUND|r")
endfunction

// -creep: activate creep/last-hit mode in Round 1
function Trig_AIML_CreepModeToggle takes nothing returns nothing
    set udg_aiml_Round1Mode = 0
    set udg_aiml_Round1Pref = 0
    call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[AIML] Round 1 mode: CREEP|r")
endfunction

// Register -surround and -creep chat commands at init
function Trig_AIML_SurroundInit takes nothing returns nothing
    local trigger t1 = CreateTrigger()
    local trigger t2 = CreateTrigger()
    call TriggerRegisterPlayerChatEvent(t1, Player(0), "-surround", true)
    call TriggerRegisterPlayerChatEvent(t1, Player(1), "-surround", true)
    call TriggerAddAction(t1, function Trig_AIML_SurroundToggle)
    call TriggerRegisterPlayerChatEvent(t2, Player(0), "-creep", true)
    call TriggerRegisterPlayerChatEvent(t2, Player(1), "-creep", true)
    call TriggerAddAction(t2, function Trig_AIML_CreepModeToggle)
endfunction

"""

    salvo_tick_marker = "function Trig_AIML_SalvoTick takes nothing returns nothing"
    idx2 = src.find(salvo_tick_marker)
    if idx2 == -1:
        print("ERROR: cannot find Trig_AIML_SalvoTick")
        sys.exit(1)
    src = src[:idx2] + SURROUND_FUNCTIONS.replace("\n", nl) + src[idx2:]
    print("[V39] inserted surround functions")

    # ------------------------------------------------------------------ #
    # 3) Patch SalvoTick: add Round1Mode surround guard at top
    #    inject_creep_control.py already rewrote SalvoTick with a basic
    #    Round1Mode check. If present, we leave it; otherwise we patch it.
    # ------------------------------------------------------------------ #
    if "udg_aiml_Round1Mode == 1" in src:
        print("[V39] SalvoTick Round1Mode guard already present, skipping patch")
    else:
        # Find the SalvoTick function body and prepend the guard AFTER all local declarations
        # (JASS requires all locals to come before any statements)
        start = src.find("function Trig_AIML_SalvoTick takes nothing returns nothing")
        if start != -1:
            pos = src.index(nl, start) + len(nl)
            # Skip all leading local/set/call lines until we find a non-local line
            while True:
                line_end = src.find(nl, pos)
                if line_end == -1:
                    break
                line = src[pos:line_end].strip()
                if line.startswith("local "):
                    pos = line_end + len(nl)
                else:
                    break
            guard = (
                "    // [SURROUND V39] Round 1 surround mode" + nl
                + "    if udg_RoundNo == 1 and udg_aiml_Round1Mode == 1 then" + nl
                + "        call Trig_AIML_SurroundTick(Player(0), Player(1))" + nl
                + "        call Trig_AIML_SurroundTick(Player(1), Player(0))" + nl
                + "        return" + nl
                + "    endif" + nl
            )
            src = src[:pos] + guard + src[pos:]
            print("[V39] patched SalvoTick with Round1Mode surround guard (after locals)")

    # ------------------------------------------------------------------ #
    # 4) Call SurroundInit from map init function (Trig_AIML_DebugInit or
    #    equivalent AIML init function)
    # ------------------------------------------------------------------ #
    # Try to find existing AIML init call site (DebugInit endfunction)
    debug_init_end = src.find("function Trig_AIML_DebugInit takes nothing returns nothing")
    if debug_init_end != -1:
        end_idx = src.find("endfunction", debug_init_end + 10)
        if end_idx != -1:
            surround_init_call = "    call Trig_AIML_SurroundInit()" + nl
            src = src[:end_idx] + surround_init_call + src[end_idx:]
            print("[V39] registered SurroundInit call inside DebugInit")
    else:
        # Fallback: find SalvoInit
        salvo_init = src.find("call Trig_AIML_SalvoInit()")
        if salvo_init != -1:
            eol2 = src.index(nl, salvo_init)
            src = src[:eol2 + len(nl)] + "    call Trig_AIML_SurroundInit()" + nl + src[eol2 + len(nl):]
            print("[V39] registered SurroundInit call after SalvoInit")
        else:
            print("WARN: could not find init hook for SurroundInit — please call it manually")

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[V39] Surround AI injected into {path}")


if __name__ == "__main__":
    main()
