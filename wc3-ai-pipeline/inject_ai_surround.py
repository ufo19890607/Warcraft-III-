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
from ai_config import SURROUND_STILL_THRESHOLD, SURROUND_STILL_TICKS, TICK_SURROUND


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
    SURROUND_GLOBALS = """    integer udg_aiml_Round1Mode = 0
    integer udg_aiml_Round1Pref = 1
    integer udg_aiml_SurroundFallbackPrinted = 0
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
// Returns distance from enemyHero to the given creep unit.
function Trig_AIML_SurroundEnemyCreepDist takes unit enemyHero, unit creep returns real
    local real dx = GetUnitX(creep) - GetUnitX(enemyHero)
    local real dy = GetUnitY(creep) - GetUnitY(enemyHero)
    return SquareRoot(dx * dx + dy * dy)
endfunction

// AllIn callback for surround fallback (集火野怪)
function Trig_AIML_SurroundCreepAllInCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) or IsUnitType(u, UNIT_TYPE_STRUCTURE) then
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
        call IssuePointOrder(u, "move", tx, ty)
    else
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

function Trig_AIML_SurroundTick takes player p, player ep returns nothing
    local group g
    local real tx
    local real ty
    local real ddx
    local real ddy
    local integer unitCount
    local unit u
    local real creepDist
    local unit aiHero
    local unit approachCreep
    if GetPlayerController(p) != MAP_CONTROL_COMPUTER then
        return
    endif
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
        if udg_aiml_DebugMode and udg_aiml_SurroundFallbackPrinted == 0 then
            set udg_aiml_SurroundFallbackPrinted = 1
        endif
        call Trig_AIML_CreepControlForPlayer(p, ep)
        set udg_aiml_CreepMode = 0
        return
    endif
    // [SURROUND] Creep HP gating (checked before finding encircle target):
    // HP > 200 -> CreepControlForPlayer (normal last-hit/approach logic, preserves debug prints)
    // HP 120-200 -> approach window: encircle or all-in depending on enemy hero distance
    // HP < 120  -> all-in on creep directly
    // No creep   -> proceed to encircle enemy
    set aiHero = Trig_AIML_CreepFindHero(p)
    if aiHero != null then
        set approachCreep = Trig_AIML_CreepFindLowHP(GetUnitX(aiHero), GetUnitY(aiHero), udg_aiml_CreepScanRadius, udg_aiml_CreepApproachHP)
        if approachCreep != null then
            set creepDist = GetUnitState(approachCreep, UNIT_STATE_LIFE)
            if creepDist >= udg_aiml_CreepApproachHP then
                // HP >= 200: safety fallback
                set approachCreep = null
                set aiHero = null
                if udg_aiml_DebugMode then
                    call DisplayTextToForce(GetPlayersAll(), "[SURROUND] HP>200, creep mode")
                endif
                call Trig_AIML_CreepControlForPlayer(p, ep)
                return
            elseif creepDist < udg_aiml_CreepLastHitHP then
                // HP < 120: all-in directly
                if udg_aiml_DebugMode then
                    call DisplayTextToForce(GetPlayersAll(), "[SURROUND] HP<120, attack creep")
                endif
                set udg_aiml_CreepTarget = approachCreep
                set approachCreep = null
                set aiHero = null
                set g = CreateGroup()
                call GroupEnumUnitsOfPlayer(g, p, null)
                call ForGroup(g, function Trig_AIML_SurroundCreepAllInCB)
                call DestroyGroup(g)
                set g = null
                return
            else
                // HP 120-200: check enemy hero distance to creep
                set aiHero = null
                set udg_aiml_SurroundTarget = Trig_AIML_SurroundFindTarget(ep)
                if udg_aiml_SurroundTarget != null and IsUnitType(udg_aiml_SurroundTarget, UNIT_TYPE_HERO) then
                    set creepDist = Trig_AIML_SurroundEnemyCreepDist(udg_aiml_SurroundTarget, approachCreep)
                else
                    set creepDist = 0.0
                endif
                if creepDist > 1000.0 then
                    // Enemy hero far: all-in on creep
                    if udg_aiml_DebugMode then
                        call DisplayTextToForce(GetPlayersAll(), "[SURROUND] HP120-200 hero_dist=" + I2S(R2I(creepDist)) + " >1000, attack creep")
                    endif
                    set udg_aiml_CreepTarget = approachCreep
                    set approachCreep = null
                    set g = CreateGroup()
                    call GroupEnumUnitsOfPlayer(g, p, null)
                    call ForGroup(g, function Trig_AIML_SurroundCreepAllInCB)
                    call DestroyGroup(g)
                    set g = null
                    return
                endif
                // Enemy hero close (<= 1000): fall through to encircle logic below
                if udg_aiml_DebugMode then
                    call DisplayTextToForce(GetPlayersAll(), "[SURROUND] HP120-200 hero_dist=" + I2S(R2I(creepDist)) + " <=1000, encircle")
                endif
                set approachCreep = null
            endif
        else
            // No creep in 120-200 window: check for any creep (HP > 200 or none)
            set udg_aiml_CreepTarget = Trig_AIML_CreepFindLowHP(GetUnitX(aiHero), GetUnitY(aiHero), udg_aiml_CreepScanRadius, 99999.0)
            set aiHero = null
            if udg_aiml_CreepTarget != null then
                // Creep exists with HP > 200: hand off to CreepControlForPlayer
                if udg_aiml_DebugMode then
                    call DisplayTextToForce(GetPlayersAll(), "[SURROUND] HP>200, creep mode")
                endif
                call Trig_AIML_CreepControlForPlayer(p, ep)
                return
            endif
            // No creep at all: proceed to encircle
        endif
    endif
    set aiHero = null
    set approachCreep = null
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
    set ddx = tx - udg_aiml_SurroundPrevX
    set ddy = ty - udg_aiml_SurroundPrevY
    if ddx * ddx + ddy * ddy < __SURROUND_STILL_THRESHOLD__ then
        set udg_aiml_SurroundStillTicks = udg_aiml_SurroundStillTicks + 1
        if udg_aiml_SurroundStillTicks >= __SURROUND_STILL_TICKS__ then
            set udg_aiml_SurroundAttacking = true
        endif
    else
        set udg_aiml_SurroundStillTicks = 0
        set udg_aiml_SurroundAttacking = false
    endif
    set udg_aiml_SurroundPhase2 = Trig_AIML_SurroundQuadrantCheck(p, tx, ty, 800.0)
    set g = CreateGroup()
    call GroupEnumUnitsOfPlayer(g, p, null)
    call ForGroup(g, function Trig_AIML_SurroundMoveCB)
    call DestroyGroup(g)
    set g = null
    set udg_aiml_SurroundPrevX = tx
    set udg_aiml_SurroundPrevY = ty
endfunction

function Trig_AIML_SurroundToggle takes nothing returns nothing
    set udg_aiml_Round1Mode = 1
    set udg_aiml_Round1Pref = 1
    call DisplayTextToForce(GetPlayersAll(), "|cffff8800[AIML] Round 1 mode: SURROUND|r")
endfunction

function Trig_AIML_CreepModeToggle takes nothing returns nothing
    set udg_aiml_Round1Mode = 0
    set udg_aiml_Round1Pref = 0
    call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[AIML] Round 1 mode: CREEP|r")
endfunction

function Trig_AIML_SurroundTimerTick takes nothing returns nothing
    if udg_RoundNo != 1 then
        return
    endif
    if udg_aiml_Round1Mode != 1 then
        return
    endif
    call Trig_AIML_SurroundTick(Player(0), Player(1))
    call Trig_AIML_SurroundTick(Player(1), Player(0))
endfunction

function Trig_AIML_SurroundInit takes nothing returns nothing
    local trigger t1 = CreateTrigger()
    local trigger t2 = CreateTrigger()
    local trigger t3 = CreateTrigger()
    call TriggerRegisterPlayerChatEvent(t1, Player(0), "-surround", true)
    call TriggerRegisterPlayerChatEvent(t1, Player(1), "-surround", true)
    call TriggerAddAction(t1, function Trig_AIML_SurroundToggle)
    call TriggerRegisterPlayerChatEvent(t2, Player(0), "-creep", true)
    call TriggerRegisterPlayerChatEvent(t2, Player(1), "-creep", true)
    call TriggerAddAction(t2, function Trig_AIML_CreepModeToggle)
    call TriggerRegisterTimerEvent(t3, __TICK_SURROUND__, true)
    call TriggerAddAction(t3, function Trig_AIML_SurroundTimerTick)
endfunction

"""

    salvo_tick_marker = "function Trig_AIML_SalvoTick takes nothing returns nothing"
    idx2 = src.find(salvo_tick_marker)
    if idx2 == -1:
        print("ERROR: cannot find Trig_AIML_SalvoTick")
        sys.exit(1)
    funcs_text = SURROUND_FUNCTIONS
    funcs_text = funcs_text.replace("__SURROUND_STILL_THRESHOLD__", f"{SURROUND_STILL_THRESHOLD:.1f}")
    funcs_text = funcs_text.replace("__SURROUND_STILL_TICKS__", str(SURROUND_STILL_TICKS))
    funcs_text = funcs_text.replace("__TICK_SURROUND__", f"{TICK_SURROUND:.2f}")
    src = src[:idx2] + funcs_text.replace("\n", nl) + src[idx2:]
    print("[V39] inserted surround functions")

    # ------------------------------------------------------------------ #
    # 3) Surround now uses independent timer — no need to patch SalvoTick
    print("[V39] surround uses independent timer, SalvoTick patch skipped")

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
