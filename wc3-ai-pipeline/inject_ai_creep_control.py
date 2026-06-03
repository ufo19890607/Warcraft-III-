#!/usr/bin/env python3
"""
inject_creep_control.py V39 - Inject Last-Hit & Anti-Steal Creep Control.

V39 vs V35:
  - CreepScanRadius: 700 -> 2000
  - Step4 (HP 120-200): DK dist > 1600 -> AllIn; DK dist <= 1600 -> SurroundCB (encircle);
    No DK -> AllIn
  - New CreepSurroundCB: non-hero non-elemental units encircle creep
  - AllInCB/ApproachCB: skip locked/retreating units (UserData==1 or 2), skip ewsp
  - CreepFindEnemyDK: visibility check included
  - DK harass (hmil/hfoo lock) only when armyCount > 8
  - Round1 only for Player(1) (computer)
  - SalvoTick: Player(1) creep only; Round1Mode surround guard preserved
  - Computer2Combat_AI guard: CreepMode>=1 blocks default combat dispatch in Round1
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

    # ------------------------------------------------------------------ #
    # 1) Globals
    # ------------------------------------------------------------------ #
    CREEP_GLOBALS = """    // [CREEP V39] Last-Hit & Anti-Steal Control globals
    boolean udg_aiml_CreepControlEnabled = true
    real    udg_aiml_CreepLastHitHP = 120.00
    real    udg_aiml_CreepApproachHP = 200.00
    real    udg_aiml_CreepScanRadius = 2000.00
    real    udg_aiml_CreepHeroAtkRange = 600.00
    integer udg_aiml_CreepMode = 0
    unit    udg_aiml_CreepTarget = null
    real    udg_aiml_CreepTargetHP = 0.00
    real    udg_aiml_CreepMapTopY = 6000.00
    real    udg_aiml_CreepMapBotY = -6000.00
    real    udg_aiml_CreepLowHPThreshold = 100.00"""

    marker = "boolean udg_aiml_DebugMode"
    idx = src.find(marker)
    if idx == -1:
        marker = "integer udg_aiml_DebugKiteDir = 0"
        idx = src.find(marker)
    if idx == -1:
        marker = "real    udg_aiml_SalvoMajorityRatio"
        idx = src.find(marker)
    if idx == -1:
        print("ERROR: cannot find globals insertion point")
        sys.exit(1)
    eol = src.index(nl, idx)
    src = src[:eol + len(nl)] + CREEP_GLOBALS + nl + src[eol + len(nl):]
    print("[V39] inserted creep globals")

    # ------------------------------------------------------------------ #
    # 2) Functions (inserted before SalvoTick)
    # ------------------------------------------------------------------ #
    CREEP_FUNCTIONS = r"""
// ================================================================
// [CREEP V39] Last-Hit & Anti-Steal Control
// Only for Player(1) (computer), only in Round 1.
// ================================================================

// Filter: neutral aggressive creep units
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

// Distance between two points
function Trig_AIML_CreepDist takes real x1, real y1, real x2, real y2 returns real
    local real dx = x2 - x1
    local real dy = y2 - y1
    return SquareRoot(dx * dx + dy * dy)
endfunction

// Find lowest HP creep within radius of (cx,cy) below maxHP
function Trig_AIML_CreepFindLowHP takes real cx, real cy, real radius, real maxHP returns unit
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
        if hp < maxHP and hp < bestHP and hp > 0.5 then
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

// Find enemy DK ('Udea') - visibility check
function Trig_AIML_CreepFindEnemyDK takes player enemy returns unit
    local group g = GetUnitsOfPlayerAndTypeId(enemy, 'Udea')
    local unit dk = FirstOfGroup(g)
    call DestroyGroup(g)
    set g = null
    if dk != null and IsUnitType(dk, UNIT_TYPE_DEAD) then
        return null
    endif
    return dk
endfunction

// Find first living hero of player
function Trig_AIML_CreepFindHero takes player p returns unit
    local group g = CreateGroup()
    local unit u
    local unit hero = null
    call GroupEnumUnitsOfPlayer(g, p, null)
    set u = FirstOfGroup(g)
    loop
        exitwhen u == null
        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitType(u, UNIT_TYPE_DEAD) then
            set hero = u
            call DestroyGroup(g)
            set g = null
            return hero
        endif
        call GroupRemoveUnit(g, u)
        set u = FirstOfGroup(g)
    endloop
    call DestroyGroup(g)
    set g = null
    return null
endfunction

// Count alive non-structure units for player
function Trig_AIML_CreepCountArmy takes player p returns integer
    local group g = CreateGroup()
    local unit u
    local integer n = 0
    call GroupEnumUnitsOfPlayer(g, p, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set n = n + 1
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    return n
endfunction

// ALL-IN callback: all non-locked non-retreating units attack creep
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
    if GetUnitUserData(u) == 1 or GetUnitUserData(u) == 2 then
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

// SURROUND-CREEP callback: non-hero non-elemental units encircle creep
// Used when DK is close (<=1600). Heroes and water elementals attack freely.
function Trig_AIML_CreepSurroundCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real ux
    local real uy
    local real tx
    local real ty
    local real dx
    local real dy
    local real dist
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) or IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set u = null
        return
    endif
    // Heroes attack freely
    if IsUnitType(u, UNIT_TYPE_HERO) then
        set u = null
        return
    endif
    // Water elemental attacks freely
    if GetUnitTypeId(u) == 'ewsp' then
        set u = null
        return
    endif
    // Locked to DK or retreating: skip
    if GetUnitUserData(u) == 1 or GetUnitUserData(u) == 2 then
        set u = null
        return
    endif
    if udg_aiml_CreepTarget == null then
        set u = null
        return
    endif
    set ux = GetUnitX(u)
    set uy = GetUnitY(u)
    set tx = GetUnitX(udg_aiml_CreepTarget)
    set ty = GetUnitY(udg_aiml_CreepTarget)
    set dx = ux - tx
    set dy = uy - ty
    set dist = SquareRoot(dx * dx + dy * dy)
    if dist < 10.0 then
        set dist = 10.0
    endif
    call IssuePointOrder(u, "move", tx - (dx / dist) * 200.0, ty - (dy / dist) * 200.0)
    set u = null
endfunction

// LOW-HP RETREAT callback
function Trig_AIML_LowHPRetreatCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real hp
    local real uy
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    if IsUnitType(u, UNIT_TYPE_HERO) then
        set u = null
        return
    endif
    if IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set u = null
        return
    endif
    if GetUnitUserData(u) == 2 then
        set uy = GetUnitY(u)
        if uy >= 0.0 then
            call IssuePointOrder(u, "move", GetUnitX(u), udg_aiml_CreepMapTopY)
        else
            call IssuePointOrder(u, "move", GetUnitX(u), udg_aiml_CreepMapBotY)
        endif
        set u = null
        return
    endif
    set hp = GetUnitState(u, UNIT_STATE_LIFE)
    if hp < udg_aiml_CreepLowHPThreshold and hp > 0.5 then
        set uy = GetUnitY(u)
        call SetUnitUserData(u, 2)
        if uy >= 0.0 then
            call IssuePointOrder(u, "move", GetUnitX(u), udg_aiml_CreepMapTopY)
        else
            call IssuePointOrder(u, "move", GetUnitX(u), udg_aiml_CreepMapBotY)
        endif
    endif
    set u = null
endfunction

// ================================================================
// [CREEP V39] Main tick — Player(1) only, Round 1 only.
// ================================================================
function Trig_AIML_CreepControlForPlayer takes player owner, player enemy returns boolean
    local unit hero
    local real cx
    local real cy
    local unit creep
    local real creepHP
    local group armyG
    local integer armyCount
    local unit dk
    local group harassG
    local unit u
    local integer assigned
    local real dkDist
    local boolean dkVisible

    // Only for computer player
    if GetPlayerController(owner) != MAP_CONTROL_COMPUTER then
        return false
    endif

    // Only active in Round 1
    if udg_RoundNo != 1 then
        set udg_aiml_CreepMode = 0
        return false
    endif

    // Find hero
    set hero = Trig_AIML_CreepFindHero(owner)
    if hero == null then
        set udg_aiml_CreepMode = 0
        return false
    endif
    set cx = GetUnitX(hero)
    set cy = GetUnitY(hero)

    // Count army
    set armyCount = Trig_AIML_CreepCountArmy(owner)

    // --- Step 1: DK harass (army > 8 = HvU) ---
    if armyCount > 8 then
        set dk = Trig_AIML_CreepFindEnemyDK(enemy)
        if dk != null then
            set dkVisible = IsUnitVisible(dk, owner)
            if dkVisible then
                set harassG = GetUnitsOfPlayerAndTypeId(owner, 'hmil')
                set assigned = 0
                set u = FirstOfGroup(harassG)
                loop
                    exitwhen u == null
                    exitwhen assigned >= 2
                    if not IsUnitType(u, UNIT_TYPE_DEAD) and GetUnitUserData(u) != 2 then
                        call IssueTargetOrder(u, "smart", dk)
                        call SetUnitUserData(u, 1)
                        set assigned = assigned + 1
                    endif
                    call GroupRemoveUnit(harassG, u)
                    set u = FirstOfGroup(harassG)
                endloop
                call DestroyGroup(harassG)
                set harassG = null
                set harassG = GetUnitsOfPlayerAndTypeId(owner, 'hfoo')
                set u = FirstOfGroup(harassG)
                if u != null and not IsUnitType(u, UNIT_TYPE_DEAD) and GetUnitUserData(u) != 2 then
                    call IssueTargetOrder(u, "smart", dk)
                    call SetUnitUserData(u, 1)
                endif
                call DestroyGroup(harassG)
                set harassG = null
            endif
            if not dkVisible then
                set dk = null
            endif
        endif
    else
        set dk = Trig_AIML_CreepFindEnemyDK(enemy)
        if dk != null then
            if not IsUnitVisible(dk, owner) then
                set dk = null
            endif
        endif
    endif

    // --- Step 2: Scan for low HP creep ---
    set creep = Trig_AIML_CreepFindLowHP(cx, cy, udg_aiml_CreepScanRadius, udg_aiml_CreepApproachHP)
    if creep == null then
        set udg_aiml_CreepMode = 0
        set udg_aiml_CreepTarget = null
        set hero = null
        return false
    endif

    set creepHP = GetUnitState(creep, UNIT_STATE_LIFE)
    set udg_aiml_CreepTarget = creep
    set udg_aiml_CreepTargetHP = creepHP

    // --- Step 3: HP < 120 = ALL-IN ---
    if creepHP < udg_aiml_CreepLastHitHP then
        set udg_aiml_CreepMode = 3
        set armyG = GetUnitsOfPlayerAll(owner)
        call ForGroup(armyG, function Trig_AIML_CreepAllInCB)
        call DestroyGroup(armyG)
        set armyG = null
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[CREEP] ALL-IN HP=" + I2S(R2I(creepHP)))
        endif
        set hero = null
        return true
    endif

    // --- Step 4: HP 120-200 = DK distance check ---
    set udg_aiml_CreepMode = 1

    if dk != null then
        set dkDist = Trig_AIML_CreepDist(GetUnitX(creep), GetUnitY(creep), GetUnitX(dk), GetUnitY(dk))
        if dkDist > 1600.0 then
            // DK far: all units attack creep freely
            set armyG = GetUnitsOfPlayerAll(owner)
            call ForGroup(armyG, function Trig_AIML_CreepAllInCB)
            call DestroyGroup(armyG)
            set armyG = null
            if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "[CREEP] DK_FAR ALLIN HP=" + I2S(R2I(creepHP)))
            endif
            set hero = null
            return true
        else
            // DK close: non-hero non-elemental encircle; heroes+elemental attack freely
            set armyG = GetUnitsOfPlayerAll(owner)
            call ForGroup(armyG, function Trig_AIML_CreepSurroundCB)
            call DestroyGroup(armyG)
            set armyG = null
            if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "[CREEP] DK_CLOSE SURROUND HP=" + I2S(R2I(creepHP)))
            endif
            set hero = null
            return true
        endif
    else
        // No DK: all units attack creep freely
        set armyG = GetUnitsOfPlayerAll(owner)
        call ForGroup(armyG, function Trig_AIML_CreepAllInCB)
        call DestroyGroup(armyG)
        set armyG = null
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[CREEP] NO_DK_ATK HP=" + I2S(R2I(creepHP)))
        endif
        set hero = null
        return true
    endif
endfunction

"""

    salvo_tick_marker = "function Trig_AIML_SalvoTick takes nothing returns nothing"
    idx2 = src.find(salvo_tick_marker)
    if idx2 == -1:
        print("ERROR: cannot find Trig_AIML_SalvoTick")
        sys.exit(1)
    src = src[:idx2] + CREEP_FUNCTIONS.replace("\n", nl) + src[idx2:]
    print("[V39] inserted creep functions")

    # ------------------------------------------------------------------ #
    # 3) Rewrite SalvoTick to include Round1 creep+surround guard
    # ------------------------------------------------------------------ #
    NEW_SALVO_TICK = """function Trig_AIML_SalvoTick takes nothing returns nothing
    local boolean creep1 = false
    // [SURROUND] Round 1 mode switch
    if udg_RoundNo == 1 and udg_aiml_Round1Mode == 1 then
        call Trig_AIML_SurroundTick(Player(0), Player(1))
        call Trig_AIML_SurroundTick(Player(1), Player(0))
        return
    endif
    // [CREEP V39] Creep control only for AI (Player 1), only in Round 1
    set creep1 = Trig_AIML_CreepControlForPlayer(Player(1), Player(0))
    // [FOCUS] Focus retreat only for computer-controlled players, Round 2+
    if udg_RoundNo >= 2 then
        if GetPlayerController(Player(1)) == MAP_CONTROL_COMPUTER then
            call Trig_AIML_FocusRetreatForPlayer(Player(1), Player(0))
        endif
        if GetPlayerController(Player(0)) == MAP_CONTROL_COMPUTER then
            call Trig_AIML_FocusRetreatForPlayer(Player(0), Player(1))
        endif
    endif
    if GetPlayerController(Player(0)) == MAP_CONTROL_COMPUTER then
        call Trig_AIML_SalvoForPlayer(Player(0), Player(1), 1)
    endif
    if GetPlayerController(Player(1)) == MAP_CONTROL_COMPUTER then
        if not creep1 then
            call Trig_AIML_SalvoForPlayer(Player(1), Player(0), 2)
        endif
    endif
endfunction"""

    start = src.find("function Trig_AIML_SalvoTick takes nothing returns nothing")
    if start == -1:
        print("ERROR: cannot find SalvoTick for rewrite")
        sys.exit(1)
    end_idx = src.find("endfunction", start + 10) + len("endfunction")
    src = src[:start] + NEW_SALVO_TICK.replace("\n", nl) + src[end_idx:]
    print("[V39] rewrote SalvoTick")

    # ------------------------------------------------------------------ #
    # 4) Guard Computer2Combat_AI_Actions in Round1
    # ------------------------------------------------------------------ #
    GUARD_OLD = "function Trig_Computer2Combat_AI_Actions takes nothing returns nothing"
    GUARD_NEW = (
        "function Trig_Computer2Combat_AI_Actions takes nothing returns nothing" + nl
        + "    // [CREEP V39] Skip combat AI dispatch when creep control is active in Round 1" + nl
        + "    if udg_RoundNo == 1 and (udg_aiml_CreepMode >= 1 or udg_aiml_Round1Mode == 1) then" + nl
        + "        return" + nl
        + "    endif"
    )
    if GUARD_OLD in src:
        src = src.replace(GUARD_OLD, GUARD_NEW, 1)
        print("[V39] patched Computer2Combat_AI_Actions guard")
    else:
        print("WARN: Computer2Combat_AI_Actions not found, skipping guard patch")

    # 4c) Inject round-start state reset into Variable Reset block
    RESET_MARKER = "// Variable Reset"
    RESET_INJECT = (
        "// Variable Reset" + nl
        + "    // [AIML V39] Reset AI mode state on each round start" + nl
        + "    set udg_aiml_Round1Mode = 0" + nl
        + "    set udg_aiml_CreepMode = 0" + nl
        + "    set udg_aiml_SurroundStillTicks = 0" + nl
        + "    set udg_aiml_SurroundAttacking = false" + nl
        + "    set udg_aiml_SurroundTarget = null"
    )
    if RESET_MARKER in src:
        src = src.replace(RESET_MARKER, RESET_INJECT, 1)
        print("[V39] injected round-start state reset into Variable Reset")
    else:
        print("WARN: Variable Reset marker not found, skipping state reset injection")

    # 4b) Guard Computer1Combat_AI_Actions in Round1
    GUARD1_OLD = "function Trig_Computer1Combat_AI_Actions takes nothing returns nothing"
    if GUARD1_OLD in src:
        src = src.replace(
            GUARD1_OLD,
            "function Trig_Computer1Combat_AI_Actions takes nothing returns nothing" + nl
            + "    if udg_RoundNo == 1 and (udg_aiml_CreepMode >= 1 or udg_aiml_Round1Mode == 1) then" + nl
            + "        return" + nl
            + "    endif",
        )
        print("[V39] patched Computer1Combat_AI_Actions guard")
    else:
        print("WARN: Computer1Combat_AI_Actions not found, skipping guard patch")

    # ------------------------------------------------------------------ #
    # 5) Disable original neutral-attack triggers
    # ------------------------------------------------------------------ #
    lines = src.split(nl)
    disabled = 0
    new_lines = []
    for line in lines:
        if 'PLAYER_NEUTRAL_AGGRESSIVE' in line and '"attack"' in line and 'IssueTargetOrderBJ' in line:
            new_lines.append("    // [CREEP] Disabled: " + line.strip())
            disabled += 1
        else:
            new_lines.append(line)
    src = nl.join(new_lines)
    if disabled:
        print(f"[V39] disabled {disabled} original neutral-attack triggers")

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[V39] Creep control injected into {path}")


if __name__ == "__main__":
    main()
