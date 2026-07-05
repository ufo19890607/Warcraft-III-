#!/usr/bin/env python3
"""
inject_creep_control.py V46 - Dynamic Burst Last-Hit Creep Control.

V46 vs V39:
  - Dynamic burst threshold: scan enemy units within 150yd of creep,
    compute burst_max from unit composition (DK=33, dog=13, skel=15 for heavy armor)
  - 4-state FSM: FARMING(0) / APPROACH(1) / FAKE(2) / ALL_IN(3)
  - Approach: move hero close to creep, stop attacking
  - Fake attack: hero feint attack animation to bait player, then cancel
  - All-in: all units attack creep when HP <= burst_max * 1.15
  - State boundaries: FARM > 212, APPROACH [threshold+40, 212],
    FAKE (threshold, threshold+40], ALL_IN <= threshold
"""

import sys
from ai_config import TICK_CREEP_CONTROL


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
    CREEP_GLOBALS = """    // [CREEP V46] Dynamic Burst Last-Hit Control globals
    boolean udg_aiml_CreepControlEnabled = true
    real    udg_aiml_CreepScanRadius = 2000.00
    integer udg_aiml_CreepMode = 0
    unit    udg_aiml_CreepTarget = null
    real    udg_aiml_CreepTargetHP = 0.00
    real    udg_aiml_CreepMapTopY = 6000.00
    real    udg_aiml_CreepMapBotY = -6000.00
    real    udg_aiml_CreepLowHPThreshold = 100.00
    // [V46] Legacy compat: renamed to avoid breaking other injectors
    real    udg_aiml_CreepApproachHP = 212.00
    real    udg_aiml_CreepLastHitHP = 120.00
    // [V46] Dynamic burst damage constants (heavy armor, 1 def)
    real    udg_aiml_DK_Burst_Max = 33.00
    real    udg_aiml_Dog_Burst_Max = 13.00
    real    udg_aiml_Skel_Burst_Max = 15.00
    real    udg_aiml_BurstScanRadius = 150.00
    real    udg_aiml_ApproachUpper = 212.00
    real    udg_aiml_FakeWindow = 40.00
    real    udg_aiml_FakeChance = 0.30
    real    udg_aiml_CreepThreshold = 132.00
    // [V46] Feint state
    boolean udg_aiml_FeintActive = false
    real    udg_aiml_FeintX = 0.00
    real    udg_aiml_FeintY = 0.00"""

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
    print("[V46] inserted dynamic burst creep globals")

    # ------------------------------------------------------------------ #
    # 2) Functions
    # ------------------------------------------------------------------ #
    CREEP_FUNCTIONS = r"""
// ================================================================
// [CREEP V46] Dynamic Burst Last-Hit Control
// 4-state FSM: FARMING(0) / APPROACH(1) / FAKE(2) / ALL_IN(3)
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

// ================================================================
// [V46] Scan enemy melee units within radius of creep target.
// Counts dogs (ugho), DK (Udea), skeletons (uske).
// Returns total burst_max for heavy armor.
// ================================================================
function Trig_AIML_ScanBurstMax takes unit creep, player enemy returns real
    local group g = CreateGroup()
    local unit u
    local real cx = GetUnitX(creep)
    local real cy = GetUnitY(creep)
    local integer dogCount = 0
    local boolean dkPresent = false
    local integer skelCount = 0
    local real burst = 0.0
    local integer tid
    local real dist
    call GroupEnumUnitsOfPlayer(g, enemy, null)
    set u = FirstOfGroup(g)
    loop
        exitwhen u == null
        if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set dist = Trig_AIML_CreepDist(cx, cy, GetUnitX(u), GetUnitY(u))
            if dist <= udg_aiml_BurstScanRadius then
                set tid = GetUnitTypeId(u)
                if tid == 'ugho' then
                    set dogCount = dogCount + 1
                elseif tid == 'Udea' then
                    set dkPresent = true
                elseif tid == 'uske' then
                    set skelCount = skelCount + 1
                endif
            endif
        endif
        call GroupRemoveUnit(g, u)
        set u = FirstOfGroup(g)
    endloop
    call DestroyGroup(g)
    set g = null
    if dkPresent then
        set burst = burst + udg_aiml_DK_Burst_Max
    endif
    set burst = burst + I2R(dogCount) * udg_aiml_Dog_Burst_Max
    set burst = burst + I2R(skelCount) * udg_aiml_Skel_Burst_Max
    return burst
endfunction

// ================================================================
// [V46] ALL-IN callback: all non-locked non-retreating units attack creep
// ================================================================
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

// ================================================================
// [V46] APPROACH callback: hero moves close to creep, stops attacking.
// Other non-hero units also stop to avoid pushing creep HP too fast.
// ================================================================
function Trig_AIML_CreepApproachCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real tx
    local real ty
    local real ux
    local real uy
    local real dx
    local real dy
    local real dist
    local real ang
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) or IsUnitType(u, UNIT_TYPE_STRUCTURE) then
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
    set tx = GetUnitX(udg_aiml_CreepTarget)
    set ty = GetUnitY(udg_aiml_CreepTarget)
    set ux = GetUnitX(u)
    set uy = GetUnitY(u)
    set dx = ux - tx
    set dy = uy - ty
    set dist = SquareRoot(dx * dx + dy * dy)
    if dist < 10.0 then
        set dist = 10.0
    endif
    if IsUnitType(u, UNIT_TYPE_HERO) then
        // Hero: move to 80-120 yd range of creep (close enough for instant hit)
        if dist > 120.0 then
            call IssuePointOrder(u, "move", tx - (dx / dist) * 100.0, ty - (dy / dist) * 100.0)
        else
            // Already close enough; stop to avoid attacking
            call IssueImmediateOrder(u, "stop")
        endif
    else
        // Non-hero: stop attacking, stay near creep
        call IssueImmediateOrder(u, "stop")
    endif
    set u = null
endfunction

// ================================================================
// [V46] FAKE-ATTACK callback: hero feints attack on creep then cancels.
// Feint: attack -> 0.12s -> stop, to bait player into rushing.
// ================================================================
function Trig_AIML_CreepFakeAttack takes unit hero, unit creep returns nothing
    local real roll
    if hero == null or creep == null then
        return
    endif
    if IsUnitType(hero, UNIT_TYPE_DEAD) then
        return
    endif
    if udg_aiml_FeintActive then
        return
    endif
    set roll = GetRandomReal(0.0, 1.0)
    if roll <= udg_aiml_FakeChance then
        call IssueTargetOrder(hero, "attack", creep)
        set udg_aiml_FeintActive = true
        set udg_aiml_FeintX = GetUnitX(hero)
        set udg_aiml_FeintY = GetUnitY(hero)
    endif
endfunction

// ================================================================
// [V46] Creep feint cancel: called separately to cancel feint after
// a short delay (via a sub-tick timer or next tick check).
// ================================================================
function Trig_AIML_CreepFeintCancel takes unit hero returns nothing
    if hero == null then
        set udg_aiml_FeintActive = false
        return
    endif
    if not udg_aiml_FeintActive then
        return
    endif
    call IssueImmediateOrder(hero, "stop")
    set udg_aiml_FeintActive = false
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
// [CREEP V46] Main tick — 4-state dynamic burst FSM
//   Mode 0: FARMING  - normal combat (> approach_upper)
//   Mode 1: APPROACH - move hero close, stop attacking
//   Mode 2: FAKE     - feint attack to bait player
//   Mode 3: ALL_IN   - everyone attack creep, secure last hit
// ================================================================
function Trig_AIML_CreepControlForPlayer takes player owner, player enemy returns boolean
    local unit hero
    local real cx
    local real cy
    local unit creep
    local real creepHP
    local real burstMax
    local real threshold
    local real fakeUpper
    local group armyG
    local integer armyCount
    local unit dk
    local group harassG
    local unit u
    local integer assigned
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

    // --- Step 2: Cancel active feint from previous tick ---
    if udg_aiml_FeintActive then
        call Trig_AIML_CreepFeintCancel(hero)
    endif

    // --- Step 3: Scan for low HP creep ---
    set creep = Trig_AIML_CreepFindLowHP(cx, cy, udg_aiml_CreepScanRadius, udg_aiml_ApproachUpper)
    if creep == null then
        set udg_aiml_CreepMode = 0
        set udg_aiml_CreepTarget = null
        set hero = null
        return false
    endif

    set creepHP = GetUnitState(creep, UNIT_STATE_LIFE)
    set udg_aiml_CreepTarget = creep
    set udg_aiml_CreepTargetHP = creepHP

    // --- Step 4: Scan enemy melee units near creep, compute dynamic threshold ---
    set burstMax = Trig_AIML_ScanBurstMax(creep, enemy)
    set threshold = burstMax * 1.15
    set fakeUpper = threshold + udg_aiml_FakeWindow
    set udg_aiml_CreepThreshold = threshold

    // --- Step 5: 4-state FSM ---
    if creepHP <= threshold then
        // ----- MODE 3: ALL-IN -----
        set udg_aiml_CreepMode = 3
        set armyG = GetUnitsOfPlayerAll(owner)
        call ForGroup(armyG, function Trig_AIML_CreepAllInCB)
        call DestroyGroup(armyG)
        set armyG = null
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[CREEP] ALL-IN HP=" + I2S(R2I(creepHP)) + " threshold=" + I2S(R2I(threshold)) + " burst=" + I2S(R2I(burstMax)))
        endif
        set hero = null
        return true
    elseif creepHP <= fakeUpper then
        // ----- MODE 2: FAKE ATTACK -----
        set udg_aiml_CreepMode = 2
        // Trigger feint attack (stochastic, ~30% per tick)
        call Trig_AIML_CreepFakeAttack(hero, creep)
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[CREEP] FAKE HP=" + I2S(R2I(creepHP)) + " threshold=" + I2S(R2I(threshold)))
        endif
        set hero = null
        return true
    else
        // ----- MODE 1: APPROACH (creepHP <= approach_upper, but > fake_upper) -----
        set udg_aiml_CreepMode = 1
        set armyG = GetUnitsOfPlayerAll(owner)
        call ForGroup(armyG, function Trig_AIML_CreepApproachCB)
        call DestroyGroup(armyG)
        set armyG = null
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[CREEP] APPROACH HP=" + I2S(R2I(creepHP)) + " threshold=" + I2S(R2I(threshold)))
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
    print("[V46] inserted dynamic burst creep functions")

    # Insert CreepTick + CreepTimerInit (independent timer)
    CREEP_TIMER_FUNCS = (
        nl + "// [CREEP V46] Independent creep control timer" + nl
        + "function Trig_AIML_CreepTick takes nothing returns nothing" + nl
        + "    if udg_RoundNo == 1 and udg_aiml_Round1Mode >= 1 then" + nl
        + "        return" + nl
        + "    endif" + nl
        + "    call Trig_AIML_CreepControlForPlayer(Player(1), Player(0))" + nl
        + "endfunction" + nl
        + nl
        + "function Trig_AIML_CreepTimerInit takes nothing returns nothing" + nl
        + "    local trigger t = CreateTrigger()" + nl
        + f"    call TriggerRegisterTimerEvent(t, {TICK_CREEP_CONTROL:.2f}, true)" + nl
        + "    call TriggerAddAction(t, function Trig_AIML_CreepTick)" + nl
        + "    set t = null" + nl
        + "endfunction" + nl
    )
    stm = "function Trig_AIML_SalvoTick takes nothing returns nothing"
    idx_st = src.find(stm)
    if idx_st != -1:
        src = src[:idx_st] + CREEP_TIMER_FUNCS + src[idx_st:]
        print("[V46] inserted CreepTick + CreepTimerInit")

    # ------------------------------------------------------------------ #
    # 3) Rewrite SalvoTick
    # ------------------------------------------------------------------ #
    NEW_SALVO_TICK = """function Trig_AIML_SalvoTick takes nothing returns nothing
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
        call Trig_AIML_SalvoForPlayer(Player(1), Player(0), 2)
    endif
endfunction"""

    start = src.find("function Trig_AIML_SalvoTick takes nothing returns nothing")
    if start == -1:
        print("ERROR: cannot find SalvoTick for rewrite")
        sys.exit(1)
    end_idx = src.find("endfunction", start + 10) + len("endfunction")
    src = src[:start] + NEW_SALVO_TICK.replace("\n", nl) + src[end_idx:]
    print("[V46] rewrote SalvoTick")

    # ------------------------------------------------------------------ #
    # 4) Guard Computer2Combat_AI_Actions in Round1
    # ------------------------------------------------------------------ #
    kodo_exclude1 = "function Trig_Computer1Combat_AI_Func001001002 takes nothing returns boolean"
    kodo_exclude2 = "function Trig_Computer2Combat_AI_Func002001002 takes nothing returns boolean"
    if kodo_exclude1 in src:
        old1 = "return GetBooleanAnd( Trig_Computer1Combat_AI_Func001001002001(), Trig_Computer1Combat_AI_Func001001002002() )"
        new1 = "return GetBooleanAnd( Trig_Computer1Combat_AI_Func001001002001(), GetBooleanAnd( Trig_Computer1Combat_AI_Func001001002002(), GetUnitTypeId(GetFilterUnit()) != 'okod' ) )"
        if old1 in src:
            src = src.replace(old1, new1, 1)
            print("[V42] excluded okod from Computer1Combat_AI army-attack filter")
    if kodo_exclude2 in src:
        old2 = "return GetBooleanAnd( Trig_Computer2Combat_AI_Func002001002001(), Trig_Computer2Combat_AI_Func002001002002() )"
        new2 = "return GetBooleanAnd( Trig_Computer2Combat_AI_Func002001002001(), GetBooleanAnd( Trig_Computer2Combat_AI_Func002001002002(), GetUnitTypeId(GetFilterUnit()) != 'okod' ) )"
        if old2 in src:
            src = src.replace(old2, new2, 1)
            print("[V42] excluded okod from Computer2Combat_AI army-attack filter")

    # Computer1Combat_AI_Actions:
    c1_marker = "function Trig_Computer1Combat_AI_Actions takes nothing returns nothing"
    c1_gpo1 = 'call GroupPointOrderLocBJ( GetUnitsOfPlayerMatching(Player(0), Condition(function Trig_Computer1Combat_AI_Func001001002)), "attack",'
    c1_gpo2 = 'call GroupPointOrderLocBJ( GetUnitsInRectOfPlayer(gg_rct_P1Start, Player(0)), "attack",'
    if c1_marker in src and c1_gpo1 in src and c1_gpo2 in src:
        c1_start = src.find(c1_marker)
        c1_body_start = src.find(nl, c1_start) + len(nl)
        c1_gpo2_idx = src.find(c1_gpo2, c1_start)
        c1_gpo2_end = src.find(")" + nl, c1_gpo2_idx) + len(")" + nl)
        original_lines = src[c1_body_start:c1_gpo2_end]
        guarded = ("    // [V40] Skip army-attack in surround/escape mode" + nl
                   + "    if not (udg_RoundNo == 1 and udg_aiml_Round1Mode >= 1) then" + nl
                   + original_lines
                   + "    endif" + nl)
        src = src[:c1_body_start] + guarded + src[c1_gpo2_end:]
        print("[V40] patched Computer1Combat_AI: selective guard on army-attack")

    # Computer2Combat_AI_Actions:
    c2_marker = "function Trig_Computer2Combat_AI_Actions takes nothing returns nothing"
    c2_gpo1 = 'call GroupPointOrderLocBJ( GetUnitsOfPlayerMatching(Player(1), Condition(function Trig_Computer2Combat_AI_Func002001002)), "attack",'
    c2_gpo2 = 'call GroupPointOrderLocBJ( GetUnitsInRectOfPlayer(gg_rct_P2Start, Player(1)), "attack",'
    if c2_marker in src and c2_gpo1 in src and c2_gpo2 in src:
        c2_start = src.find(c2_marker)
        c2_body_start = src.find(nl, c2_start) + len(nl)
        c2_gpo2_idx = src.find(c2_gpo2, c2_start)
        c2_gpo2_end = src.find(")" + nl, c2_gpo2_idx) + len(")" + nl)
        original_lines2 = src[c2_body_start:c2_gpo2_end]
        guarded2 = ("    // [V40] Skip army-attack in surround/escape mode" + nl
                    + "    if not (udg_RoundNo == 1 and udg_aiml_Round1Mode >= 1) then" + nl
                    + original_lines2
                    + "    endif" + nl)
        src = src[:c2_body_start] + guarded2 + src[c2_gpo2_end:]
        print("[V40] patched Computer2Combat_AI: selective guard on army-attack")

    # 4c) Inject round-start state reset into Variable Reset block
    RESET_MARKER = "// Variable Reset"
    RESET_INJECT = (
        "// Variable Reset" + nl
        + "    // [V40] Apply Round1Pref at countdown end" + nl
        + "    if udg_RoundNo == 1 then" + nl
        + "        set udg_aiml_Round1Mode = udg_aiml_Round1Pref" + nl
        + "    else" + nl
        + "        set udg_aiml_Round1Mode = 0" + nl
        + "    endif" + nl
        + "    set udg_aiml_CreepMode = 0" + nl
        + "    // [V40] Combat_AI always stays enabled - it handles unit production." + nl
        + "    // Mode ticks (surround/escape/creep) override Combat_AI orders" + nl
        + "    // at higher frequency (0.3-0.5s vs 1.0s), so they win the order race." + nl
        + "    set udg_aiml_SurroundStillTicks = 0" + nl
        + "    set udg_aiml_SurroundAttacking = false" + nl
        + "    set udg_aiml_SurroundTarget = null" + nl
        + "    set udg_aiml_SurroundFallbackPrinted = 0"
    )
    if RESET_MARKER in src:
        src = src.replace(RESET_MARKER, RESET_INJECT, 1)
        print("[V46] injected round-start state reset into Variable Reset")
    else:
        print("WARN: Variable Reset marker not found, skipping state reset injection")

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
        print(f"[V46] disabled {disabled} original neutral-attack triggers")

    # Hook CreepTimerInit into main()
    si_call = "call Trig_AIML_SalvoInit()"
    idx_si = src.find(si_call)
    if idx_si != -1 and "call Trig_AIML_CreepTimerInit()" not in src:
        eol_si = src.index(nl, idx_si)
        src = src[:eol_si + len(nl)] + "    call Trig_AIML_CreepTimerInit()" + nl + src[eol_si + len(nl):]
        print("[V46] hooked CreepTimerInit into main()")

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[V46] Dynamic burst creep control injected into {path}")


if __name__ == "__main__":
    main()
