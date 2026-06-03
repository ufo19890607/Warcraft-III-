#!/usr/bin/env python3
"""
inject_aiml_v3.py - V19 (TC stomp + SALVO + KITE / hit-and-run)

Inject:
  1. TC smart war stomp (replaces dumb stomp Funcs)        [V18]
  2. Ranged-force concentrated salvo with custom whitelist [V18]
  3. Hit-and-run kite when enemy is mostly melee/flying    [V19 NEW]

[V19] Kite design (hit-and-run):
  - When enemy army is >= 60% melee+flying, ranged army goes into kite mode
  - Per-unit decision: only units within KiteThreshold (350) of focus retreat
    (units already at safe range keep firing -- avoids 'shooting blanks')
  - Retreat direction = away from enemy centroid (not from focus)
    -> stable, doesn't get cut by single-target weirdness
  - Retreat step = 100 game units per tick (~0.78 tile, ~1/6 of 600 range)
  - Heroes participate in kite; melee units do not (whitelist excluded melee)

Custom whitelist (per windyu UD-vs-all training preferences):
  Human:   hrif (riflemen), hgry (gryphon), hgyr (flying machine - actually not ranged?)
           Actually hgyr=Flying Machine (no attack), hdhw=Dragonhawk
           Actual ranged Humans: hrif, hdhw, hgry (gryphon)
  Orc:     ohun (headhunter), otbk (berserker), owyv (windrider/wyvern)
  NE:      earc (archer), esen (huntress), edry (dryad), edot (storm crow),
           ehip (hippogryph), ehpr (hippogryph rider), efdr (faerie dragon)
  UD:      ucry (crypt fiend), uabo (abomination -- but you said destroyer; we keep uobs+uabo just in case),
           uobs (obsidian statue), ufro (frost wyrm), ugar (gargoyle air), ugrm (gargoyle stone)
  Ranged Heroes:
           Hamg, Hblm,
           Ofar, Oshd,
           Ulic,
           Emoo, Ekee,
           Nbrn, Nfir, Nngs, Ntin

usage: inject_aiml_v2.py <input.j> <output.j>

NOTE: The "Kiting" feature has been deprecated due to its poor performance.
"""
import sys
import re

# ---- Whitelist ----
RANGED_TROOPS = [
    # Human
    "'hrif'", "'hdhw'", "'hgry'", "'hgyr'",
    # Orc
    "'ohun'", "'otbk'", "'owyv'",
    # NE
    "'earc'", "'esen'", "'edry'", "'edot'",
    "'ehip'", "'ehpr'", "'efdr'",
    # UD
    "'ucry'", "'uabo'", "'uobs'", "'ufro'", "'ugar'", "'ugrm'",
]

RANGED_HEROES = [
    "'Hamg'", "'Hblm'",
    "'Ofar'", "'Oshd'",
    "'Ulic'",
    "'Emoo'", "'Ekee'",
    "'Nbrn'", "'Nfir'", "'Nngs'", "'Ntin'",
]

ALL_RANGED = RANGED_TROOPS + RANGED_HEROES

# ---- Build the IsRangedTroop function dynamically ----
def build_is_ranged_troop():
    body = []
    body.append("function Trig_AIML_IsRangedTroop takes nothing returns boolean")
    body.append("    local unit u = GetFilterUnit()")
    body.append("    local integer t = GetUnitTypeId(u)")
    body.append("    local boolean ok = false")
    body.append("    if not IsUnitType(u, UNIT_TYPE_DEAD) then")
    first = True
    for tid in ALL_RANGED:
        kw = "if" if first else "elseif"
        body.append(f"        {kw} t == {tid} then")
        body.append(f"            set ok = true")
        first = False
    body.append("        endif")
    body.append("    endif")
    body.append("    if ok then")
    body.append("        if GetOwningPlayer(u) != udg_aiml_SalvoOwnerPlayer then")
    body.append("            set ok = false")
    body.append("        endif")
    body.append("    endif")
    body.append("    set u = null")
    body.append("    return ok")
    body.append("endfunction")
    return "\n".join(body)


# ---- Globals ----
AIML_GLOBALS = """    // [AIML] TC Smart War Stomp shared globals
    group   udg_aiml_TempGroup = null
    unit    udg_aiml_StompCaster = null
    integer udg_aiml_StompMinEnemies = 2
    real    udg_aiml_StompRadius = 250.00
    real    udg_aiml_StompManaCost = 100.00
    real    udg_aiml_StompHeroBypassRadius = 250.00
    // [AIML-SALVO] state (V18, custom whitelist)
    unit    udg_aiml_FocusTarget1 = null
    unit    udg_aiml_FocusTarget2 = null
    real    udg_aiml_SalvoMajorityRatio = 0.50
    integer udg_aiml_SalvoFrontRowCount = 4
    real    udg_aiml_SalvoMapRange = 99999.00
    group   udg_aiml_SalvoEnemyG = null
    group   udg_aiml_SalvoArmyG = null
    group   udg_aiml_SalvoRangedG = null
    integer udg_aiml_SalvoArmyCount = 0
    integer udg_aiml_SalvoRangedCount = 0
    player  udg_aiml_SalvoOwnerPlayer = null
    player  udg_aiml_SalvoEnemyPlayer = null
    real    udg_aiml_SalvoCurEx = 0.00
    real    udg_aiml_SalvoCurEy = 0.00
    real    udg_aiml_SalvoCurMinD = 0.00
    real    udg_aiml_SalvoPrevD = 0.00
    real    udg_aiml_SalvoCurBestD = 0.00
    unit    udg_aiml_SalvoCurRoundBest = null
    real    udg_aiml_SalvoFrontMaxD = 0.00
    real    udg_aiml_SalvoBestHp = 0.00
    real    udg_aiml_SalvoBestHeroHp = 0.00
    unit    udg_aiml_SalvoPicked = null
    unit    udg_aiml_SalvoPickedHero = null
    // [AIML-KITE] V19 hit-and-run state
    boolean udg_aiml_KiteEnabled = true
    real    udg_aiml_KiteMeleeAirRatio = 0.60
    real    udg_aiml_KiteThreshold = 350.00
    real    udg_aiml_KiteStep = 100.00
    real    udg_aiml_KiteMinMapBound = 600.00
    boolean udg_aiml_KiteActiveThisTick = false
    real    udg_aiml_KiteEnemyCx = 0.00
    real    udg_aiml_KiteEnemyCy = 0.00
    integer udg_aiml_KiteEnemyCount = 0
    real    udg_aiml_KiteEnemyMeleeAirCount = 0.00
    // [V20] Per-unit local-threat state (still used by V21 group-retreat scan)
    real    udg_aiml_LocalThreatRadius = 350.00
    real    udg_aiml_LocalRetreatStep  = 150.00
    real    udg_aiml_LocalSumX = 0.00
    real    udg_aiml_LocalSumY = 0.00
    real    udg_aiml_LocalThreatSumX = 0.00
    real    udg_aiml_LocalThreatSumY = 0.00
    integer udg_aiml_LocalThreatCount = 0
    group   udg_aiml_LocalThreatG = null
    // [V21] D3-mode group retreat: ANY ranged unit threatened -> whole ranged team retreats together
    boolean udg_aiml_GroupRetreating = false
    real    udg_aiml_GroupRetreatX = 0.00
    real    udg_aiml_GroupRetreatY = 0.00
    real    udg_aiml_GroupRetreatStep = 200.00
    location udg_aiml_TmpStartLoc = null
    unit    udg_aiml_DebugFirstUnit = null
    boolean udg_aiml_RetreatDidMove = false
    integer udg_aiml_RetreatPhase = 0
    integer udg_aiml_RetreatShootTicks = 0
    integer udg_aiml_RetreatAction = 0
    real    udg_aiml_RangedCentroidX = 0.00
    real    udg_aiml_RangedCentroidY = 0.00
    group   udg_aiml_TempRetreatG = null
    integer udg_aiml_GlobalThreatCount = 0
    real    udg_aiml_GlobalThreatSumX = 0.00
    real    udg_aiml_GlobalThreatSumY = 0.00
    integer udg_aiml_SalvoDebugCounter = 0
    real    udg_aiml_KiteSumX = 0.00
    real    udg_aiml_KiteSumY = 0.00
    real    udg_aiml_KiteMapMinX = -99999.00
    real    udg_aiml_KiteMapMaxX = 99999.00
    real    udg_aiml_KiteMapMinY = -99999.00
    real    udg_aiml_KiteMapMaxY = 99999.00"""


# ---- Functions block (TC stomp + Salvo) ----
AIML_FUNCTIONS_TEMPLATE = """
//===========================================================================
// [AIML] TC Smart War Stomp - replaces dumb stomp calls
//===========================================================================
function Trig_AIML_IsValidStompTarget takes nothing returns boolean
    local unit u = GetFilterUnit()
    local boolean ok = true
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set ok = false
    elseif IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set ok = false
    elseif IsUnitType(u, UNIT_TYPE_FLYING) then
        set ok = false
    endif
    if ok then
        if IsUnitAlly(u, GetOwningPlayer(udg_aiml_StompCaster)) then
            set ok = false
        endif
    endif
    set u = null
    return ok
endfunction

function Trig_AIML_IsHostileHeroInRange takes nothing returns boolean
    local unit u = GetFilterUnit()
    local boolean ok = false
    if IsUnitType(u, UNIT_TYPE_HERO) then
        if not IsUnitType(u, UNIT_TYPE_DEAD) then
            if not IsUnitAlly(u, GetOwningPlayer(udg_aiml_StompCaster)) then
                set ok = true
            endif
        endif
    endif
    set u = null
    return ok
endfunction

function Trig_AIML_TC_Stomp_Logic takes unit tc returns nothing
    local real cx
    local real cy
    local group g = CreateGroup()
    local integer count = 0
    local boolean heroNear = false
    if tc == null then
        call DestroyGroup(g)
        return
    endif
    if IsUnitType(tc, UNIT_TYPE_DEAD) then
        call DestroyGroup(g)
        return
    endif
    if GetUnitState(tc, UNIT_STATE_MANA) < udg_aiml_StompManaCost then
        call DestroyGroup(g)
        return
    endif
    set cx = GetUnitX(tc)
    set cy = GetUnitY(tc)
    set udg_aiml_StompCaster = tc
    call GroupEnumUnitsInRange(g, cx, cy, udg_aiml_StompHeroBypassRadius, Filter(function Trig_AIML_IsHostileHeroInRange))
    if CountUnitsInGroup(g) > 0 then
        set heroNear = true
    endif
    call GroupClear(g)
    if heroNear then
        call IssueImmediateOrder(tc, "stomp")
        call DestroyGroup(g)
        return
    endif
    call GroupEnumUnitsInRange(g, cx, cy, udg_aiml_StompRadius, Filter(function Trig_AIML_IsValidStompTarget))
    set count = CountUnitsInGroup(g)
    if count >= udg_aiml_StompMinEnemies then
        call IssueImmediateOrder(tc, "stomp")
    endif
    call DestroyGroup(g)
endfunction

//===========================================================================
// [AIML-SALVO] Ranged-force concentrated salvo (V18, custom whitelist)
//===========================================================================
__IS_RANGED_TROOP_PLACEHOLDER__

function Trig_AIML_IsArmyUnit takes nothing returns boolean
    local unit u = GetFilterUnit()
    local boolean ok = true
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set ok = false
    elseif IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set ok = false
    endif
    if ok then
        if GetOwningPlayer(u) != udg_aiml_SalvoOwnerPlayer then
            set ok = false
        endif
    endif
    set u = null
    return ok
endfunction

function Trig_AIML_IsValidSalvoTarget takes nothing returns boolean
    local unit u = GetFilterUnit()
    local boolean ok = true
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set ok = false
    elseif IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set ok = false
    endif
    if ok then
        if GetOwningPlayer(u) != udg_aiml_SalvoEnemyPlayer then
            set ok = false
        endif
    endif
    set u = null
    return ok
endfunction

function Trig_AIML_UpdateMinDistCB takes nothing returns nothing
    local unit a = GetEnumUnit()
    local real ax = GetUnitX(a)
    local real ay = GetUnitY(a)
    local real dx = ax - udg_aiml_SalvoCurEx
    local real dy = ay - udg_aiml_SalvoCurEy
    local real d = dx*dx + dy*dy
    if d < udg_aiml_SalvoCurMinD then
        set udg_aiml_SalvoCurMinD = d
    endif
    set a = null
endfunction

function Trig_AIML_MinDistSqToArmy takes real ex, real ey returns real
    set udg_aiml_SalvoCurEx = ex
    set udg_aiml_SalvoCurEy = ey
    set udg_aiml_SalvoCurMinD = 999999999.0
    call ForGroup(udg_aiml_SalvoArmyG, function Trig_AIML_UpdateMinDistCB)
    return udg_aiml_SalvoCurMinD
endfunction

function Trig_AIML_SelectRoundCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real ex
    local real ey
    local real d
    if u == null then
        return
    endif
    set ex = GetUnitX(u)
    set ey = GetUnitY(u)
    set d = Trig_AIML_MinDistSqToArmy(ex, ey)
    if d > udg_aiml_SalvoPrevD then
        if d < udg_aiml_SalvoCurBestD then
            set udg_aiml_SalvoCurBestD = d
            set udg_aiml_SalvoCurRoundBest = u
        endif
    endif
    set u = null
endfunction

function Trig_AIML_PickPhase2CB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real ex
    local real ey
    local real d
    local real hp
    if u == null then
        return
    endif
    set ex = GetUnitX(u)
    set ey = GetUnitY(u)
    set d = Trig_AIML_MinDistSqToArmy(ex, ey)
    if d <= udg_aiml_SalvoFrontMaxD then
        set hp = GetWidgetLife(u)
        if IsUnitType(u, UNIT_TYPE_HERO) then
            if hp < udg_aiml_SalvoBestHeroHp then
                set udg_aiml_SalvoBestHeroHp = hp
                set udg_aiml_SalvoPickedHero = u
            endif
        else
            if hp < udg_aiml_SalvoBestHp then
                set udg_aiml_SalvoBestHp = hp
                set udg_aiml_SalvoPicked = u
            endif
        endif
    endif
    set u = null
endfunction

function Trig_AIML_PickSalvoTarget takes nothing returns unit
    local integer round
    local integer rowN = udg_aiml_SalvoFrontRowCount
    if udg_aiml_SalvoArmyCount == 0 then
        return null
    endif
    set udg_aiml_SalvoPrevD = -1.0
    set round = 0
    loop
        exitwhen round >= rowN
        set udg_aiml_SalvoCurBestD = 999999999.0
        set udg_aiml_SalvoCurRoundBest = null
        call ForGroup(udg_aiml_SalvoEnemyG, function Trig_AIML_SelectRoundCB)
        if udg_aiml_SalvoCurRoundBest == null then
            exitwhen true
        endif
        set udg_aiml_SalvoPrevD = udg_aiml_SalvoCurBestD
        set round = round + 1
    endloop
    set udg_aiml_SalvoFrontMaxD = udg_aiml_SalvoPrevD
    set udg_aiml_SalvoBestHp = 999999.0
    set udg_aiml_SalvoBestHeroHp = 999999.0
    set udg_aiml_SalvoPicked = null
    set udg_aiml_SalvoPickedHero = null
    call ForGroup(udg_aiml_SalvoEnemyG, function Trig_AIML_PickPhase2CB)
    if udg_aiml_SalvoPickedHero != null then
        return udg_aiml_SalvoPickedHero
    endif
    return udg_aiml_SalvoPicked
endfunction

// [V20] Per-unit local-threat detection helpers (must be defined before IssueAttackCB)
function Trig_AIML_IsThreatUnit takes unit u returns boolean
    local integer t
    if u == null then
        return false
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        return false
    endif
    if IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        return false
    endif
    if IsUnitAlly(u, udg_aiml_SalvoOwnerPlayer) then
        return false
    endif
    if IsUnitType(u, UNIT_TYPE_FLYING) then
        return true
    endif
    set t = GetUnitTypeId(u)
    if t == 'hfoo' or t == 'hkni' or t == 'hmil' then
        return true
    endif
    if t == 'ogru' or t == 'otau' or t == 'ofor' then
        return true
    endif
    if t == 'ugho' or t == 'uabo' then
        return true
    endif
    if t == 'edoc' or t == 'emtg' then
        return true
    endif
    if t == 'Hmkg' or t == 'Hpal' or t == 'Hart' then
        return true
    endif
    if t == 'Obla' or t == 'Otch' or t == 'Obea' then
        return true
    endif
    if t == 'Udea' or t == 'Ucrl' or t == 'Udre' then
        return true
    endif
    if t == 'Edmm' or t == 'Ewar' then
        return true
    endif
    if t == 'nfel' or t == 'ngol' or t == 'nogr' or t == 'nogm' or t == 'nogl' then
        return true
    endif
    return false
endfunction

function Trig_AIML_LocalThreatFilter takes nothing returns boolean
    return Trig_AIML_IsThreatUnit(GetFilterUnit())
endfunction

function Trig_AIML_LocalThreatTallyCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    if u == null then
        return
    endif
    set udg_aiml_LocalThreatSumX = udg_aiml_LocalThreatSumX + GetUnitX(u)
    set udg_aiml_LocalThreatSumY = udg_aiml_LocalThreatSumY + GetUnitY(u)
    set udg_aiml_LocalThreatCount = udg_aiml_LocalThreatCount + 1
    set u = null
endfunction

// [V21 D3] Group-retreat scan callbacks
// Per-ranged-unit scan: detect if THIS unit has a threat in LocalThreatRadius;
// if so, set the global flag. Also accumulate ALL threats around ALL ranged
// units into a global centroid (used for retreat direction).
function Trig_AIML_RetreatScanRangedCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real ux
    local real uy
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    set ux = GetUnitX(u)
    set uy = GetUnitY(u)
    // Accumulate ranged-team centroid every call (used as retreat anchor)
    set udg_aiml_LocalSumX = udg_aiml_LocalSumX + ux
    set udg_aiml_LocalSumY = udg_aiml_LocalSumY + uy
    // Reset per-unit local tally; reuse LocalThreatTallyCB to count + sum centroid
    set udg_aiml_LocalThreatSumX = 0.0
    set udg_aiml_LocalThreatSumY = 0.0
    set udg_aiml_LocalThreatCount = 0
    call GroupClear(udg_aiml_LocalThreatG)
    call GroupEnumUnitsInRange(udg_aiml_LocalThreatG, ux, uy, udg_aiml_LocalThreatRadius, Filter(function Trig_AIML_LocalThreatFilter))
    call ForGroup(udg_aiml_LocalThreatG, function Trig_AIML_LocalThreatTallyCB)
    if udg_aiml_LocalThreatCount > 0 then
        // Trip the group-retreat flag and add this unit's nearby threats to the global centroid.
        set udg_aiml_GroupRetreating = true
        set udg_aiml_GlobalThreatSumX = udg_aiml_GlobalThreatSumX + udg_aiml_LocalThreatSumX
        set udg_aiml_GlobalThreatSumY = udg_aiml_GlobalThreatSumY + udg_aiml_LocalThreatSumY
        set udg_aiml_GlobalThreatCount = udg_aiml_GlobalThreatCount + udg_aiml_LocalThreatCount
    endif
    set u = null
endfunction

// Decide retreat for the whole ranged team and pre-compute one shared retreat point.
// Retreat point = ranged-team centroid pushed GroupRetreatStep units away from threat centroid.
function Trig_AIML_DecideRetreatForTick takes nothing returns nothing
    local real ax
    local real ay
    local real cx
    local real cy
    local real dirx
    local real diry
    local real dirLen
    set udg_aiml_GroupRetreating = false
    set udg_aiml_LocalSumX = 0.0
    set udg_aiml_LocalSumY = 0.0
    set udg_aiml_GlobalThreatSumX = 0.0
    set udg_aiml_GlobalThreatSumY = 0.0
    set udg_aiml_GlobalThreatCount = 0
    if udg_aiml_SalvoRangedCount == 0 then
        return
    endif
    call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_RetreatScanRangedCB)
    if not udg_aiml_GroupRetreating then
        return
    endif
    if udg_aiml_GlobalThreatCount == 0 then
        // Defensive: flag tripped but somehow no threats accumulated -- bail.
        set udg_aiml_GroupRetreating = false
        return
    endif
    // Anchor = ranged-team centroid; threat centroid = weighted avg of threat positions
    set ax = udg_aiml_LocalSumX / I2R(udg_aiml_SalvoRangedCount)
    set ay = udg_aiml_LocalSumY / I2R(udg_aiml_SalvoRangedCount)
    set udg_aiml_RangedCentroidX = ax
    set udg_aiml_RangedCentroidY = ay
    set cx = udg_aiml_GlobalThreatSumX / I2R(udg_aiml_GlobalThreatCount)
    set cy = udg_aiml_GlobalThreatSumY / I2R(udg_aiml_GlobalThreatCount)
    // [V29] Fixed retreat direction = map RIGHT (positive X axis).
    // All units retreat to the same point: centroid + (step, 0).
    // This guarantees visible unified group movement toward map right edge.
    set dirx = 1.0
    set diry = 0.0
    set udg_aiml_GroupRetreatX = ax + dirx * udg_aiml_GroupRetreatStep
    set udg_aiml_GroupRetreatY = ay + diry * udg_aiml_GroupRetreatStep
    // Clamp to playable map bounds
    if udg_aiml_GroupRetreatX < udg_aiml_KiteMapMinX + udg_aiml_KiteMinMapBound then
        set udg_aiml_GroupRetreatX = udg_aiml_KiteMapMinX + udg_aiml_KiteMinMapBound
    endif
    if udg_aiml_GroupRetreatX > udg_aiml_KiteMapMaxX - udg_aiml_KiteMinMapBound then
        set udg_aiml_GroupRetreatX = udg_aiml_KiteMapMaxX - udg_aiml_KiteMinMapBound
    endif
    if udg_aiml_GroupRetreatY < udg_aiml_KiteMapMinY + udg_aiml_KiteMinMapBound then
        set udg_aiml_GroupRetreatY = udg_aiml_KiteMapMinY + udg_aiml_KiteMinMapBound
    endif
    if udg_aiml_GroupRetreatY > udg_aiml_KiteMapMaxY - udg_aiml_KiteMinMapBound then
        set udg_aiml_GroupRetreatY = udg_aiml_KiteMapMaxY - udg_aiml_KiteMinMapBound
    endif
    // [V27] If clamped retreat point is too close to current centroid (< 50), we're at the
    // map edge and can't retreat further. Cancel retreat to avoid standing in a corner doing nothing.
    if (udg_aiml_GroupRetreatX - ax) * (udg_aiml_GroupRetreatX - ax) + (udg_aiml_GroupRetreatY - ay) * (udg_aiml_GroupRetreatY - ay) < 2500.00 then
        set udg_aiml_GroupRetreating = false
    endif
endfunction

function Trig_AIML_IssueAttackCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local unit target = udg_aiml_FocusTarget1
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    // [V21 D3 -> V22] Group-retreat mode: whole ranged team attack-moves to RetreatX/RetreatY.
    // CRITICAL: use "attack" (attack-move), NOT "smart" or "move".
    //   - "smart" treats the point as a destination; unit walks all the way without firing on enemies it passes.
    //   - "move" pure pathing, ignores enemies entirely.
    //   - "attack" = attack-move: shoot anything in range while pathing toward the point.
    // This way the team retreats AND fires simultaneously ("kite" behavior).
    // Heroes in attack-move will still auto-cast in-range spells (D3 spirit preserved).
    // [V30b] Retreat action. Move ALL army units (incl melee+heroes) on move tick.
    if udg_aiml_GroupRetreating then
        if udg_aiml_RetreatAction == 2 then
            // MOVE: skip structures
            if IsUnitType(u, UNIT_TYPE_STRUCTURE) then
                set u = null
                return
            endif
            call IssuePointOrder(u, "smart", udg_aiml_GroupRetreatX, udg_aiml_GroupRetreatY)
        elseif udg_aiml_RetreatAction == 1 then
            // STOP: break move, let native AI shoot
            if IsUnitType(u, UNIT_TYPE_STRUCTURE) then
                set u = null
                return
            endif
            call IssueImmediateOrder(u, "stop")
        endif
        // Action 0 = do nothing (native AI shoots on its own)
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
endfunction

function Trig_AIML_RebuildGroupArmy takes nothing returns nothing
    call GroupClear(udg_aiml_SalvoArmyG)
    call GroupEnumUnitsOfPlayer(udg_aiml_SalvoArmyG, udg_aiml_SalvoOwnerPlayer, Filter(function Trig_AIML_IsArmyUnit))
    set udg_aiml_SalvoArmyCount = CountUnitsInGroup(udg_aiml_SalvoArmyG)
endfunction

function Trig_AIML_RebuildGroupRanged takes nothing returns nothing
    call GroupClear(udg_aiml_SalvoRangedG)
    call GroupEnumUnitsOfPlayer(udg_aiml_SalvoRangedG, udg_aiml_SalvoOwnerPlayer, Filter(function Trig_AIML_IsRangedTroop))
    set udg_aiml_SalvoRangedCount = CountUnitsInGroup(udg_aiml_SalvoRangedG)
endfunction

function Trig_AIML_RebuildGroupEnemy takes nothing returns nothing
    call GroupClear(udg_aiml_SalvoEnemyG)
    call GroupEnumUnitsOfPlayer(udg_aiml_SalvoEnemyG, udg_aiml_SalvoEnemyPlayer, Filter(function Trig_AIML_IsValidSalvoTarget))
endfunction

//===========================================================================
// [AIML-KITE] V19 hit-and-run helpers
//===========================================================================
// [V20] Per-unit local-threat helpers moved above IssueAttackCB

function Trig_AIML_KiteEnemyTallyCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local integer t
    local boolean isMeleeOrAir = false
    if u == null then
        return
    endif
    set udg_aiml_KiteSumX = udg_aiml_KiteSumX + GetUnitX(u)
    set udg_aiml_KiteSumY = udg_aiml_KiteSumY + GetUnitY(u)
    set udg_aiml_KiteEnemyCount = udg_aiml_KiteEnemyCount + 1
    // [V19] Classify enemy unit as melee/flying:
    //   1. Flying = UNIT_TYPE_FLYING (works for both ground-attacker flyers and air units)
    //   2. Melee ground = explicit unit-id whitelist of common melee units across all races
    //      (we cannot rely on GetUnitAcquireRange -- not present in 1.27)
    if IsUnitType(u, UNIT_TYPE_FLYING) then
        set isMeleeOrAir = true
    else
        set t = GetUnitTypeId(u)
        // Human melee: footman (hfoo), knight (hkni), militia (hmil)
        if t == 'hfoo' or t == 'hkni' or t == 'hmil' then
            set isMeleeOrAir = true
        // Orc melee: grunt (ogru), tauren (otau), raider (orai is mounted ranged-ish, exclude),
        //            spirit walker melee form, troll berserker (otbk is ranged though)
        elseif t == 'ogru' or t == 'otau' or t == 'ofor' then
            set isMeleeOrAir = true
        // UD melee: ghoul (ugho), abomination (uabo), crypt fiend (ucry is ranged though, exclude),
        //           gargoyle ground (ugar = flying, handled above)
        elseif t == 'ugho' or t == 'uabo' then
            set isMeleeOrAir = true
        // NE melee: dryad is ranged (exclude); huntress (esen is ranged 'ish'), 
        //           bear/druid bear form (edoc), mountain giant (emtg)
        elseif t == 'edoc' or t == 'emtg' then
            set isMeleeOrAir = true
        // Heroes (melee): MK (Hmkg), Pala (Hpal), BM (Obla), TC (Otch), Beastmaster (Obea),
        //                 DK (Udea), Crypt Lord (Ucrl is melee-ish), DH (Edmm), POTM=ranged exclude
        elseif t == 'Hmkg' or t == 'Hpal' or t == 'Hart' then
            set isMeleeOrAir = true
        elseif t == 'Obla' or t == 'Otch' or t == 'Obea' then
            set isMeleeOrAir = true
        elseif t == 'Udea' or t == 'Ucrl' or t == 'Udre' then
            set isMeleeOrAir = true
        elseif t == 'Edmm' or t == 'Ewar' then
            set isMeleeOrAir = true
        // Common neutrals/creeps melee: ghoul-type, golems, demons
        elseif t == 'nfel' or t == 'ngol' or t == 'nogr' or t == 'nogm' or t == 'nogl' then
            set isMeleeOrAir = true
        endif
    endif
    if isMeleeOrAir then
        set udg_aiml_KiteEnemyMeleeAirCount = udg_aiml_KiteEnemyMeleeAirCount + 1.0
    endif
    set u = null
endfunction

function Trig_AIML_DecideKiteForTick takes nothing returns nothing
    local real ratio
    set udg_aiml_KiteActiveThisTick = false
    if not udg_aiml_KiteEnabled then
        return
    endif
    set udg_aiml_KiteSumX = 0.0
    set udg_aiml_KiteSumY = 0.0
    set udg_aiml_KiteEnemyCount = 0
    set udg_aiml_KiteEnemyMeleeAirCount = 0.0
    call ForGroup(udg_aiml_SalvoEnemyG, function Trig_AIML_KiteEnemyTallyCB)
    if udg_aiml_KiteEnemyCount == 0 then
        return
    endif
    set udg_aiml_KiteEnemyCx = udg_aiml_KiteSumX / I2R(udg_aiml_KiteEnemyCount)
    set udg_aiml_KiteEnemyCy = udg_aiml_KiteSumY / I2R(udg_aiml_KiteEnemyCount)
    set ratio = udg_aiml_KiteEnemyMeleeAirCount / I2R(udg_aiml_KiteEnemyCount)
    if ratio >= udg_aiml_KiteMeleeAirRatio then
        set udg_aiml_KiteActiveThisTick = true
    endif
endfunction

function Trig_AIML_SalvoForPlayer takes player p, player ep, integer focusSlot returns nothing
    local unit picked
    local boolean dbg = false  // [AIML] V19 debug verified clean, default off; for debugging change to (udg_aiml_SalvoDebugCounter == 0) and (focusSlot == 2)
    set udg_aiml_SalvoOwnerPlayer = p
    set udg_aiml_SalvoEnemyPlayer = ep
    call Trig_AIML_RebuildGroupArmy()
    if dbg then
        call DisplayTextToForce(GetPlayersAll(), "[AIML] tick fs=" + I2S(focusSlot) + " army=" + I2S(udg_aiml_SalvoArmyCount))
    endif
    if udg_aiml_SalvoArmyCount == 0 then
        return
    endif
    call Trig_AIML_RebuildGroupRanged()
    if dbg then
        call DisplayTextToForce(GetPlayersAll(), "[AIML] ranged=" + I2S(udg_aiml_SalvoRangedCount) + " need>=" + R2S(I2R(udg_aiml_SalvoArmyCount) * udg_aiml_SalvoMajorityRatio) + " majRatio=" + R2S(udg_aiml_SalvoMajorityRatio))
    endif
    if I2R(udg_aiml_SalvoRangedCount) < I2R(udg_aiml_SalvoArmyCount) * udg_aiml_SalvoMajorityRatio then
        if focusSlot == 1 then
            set udg_aiml_FocusTarget1 = null
        else
            set udg_aiml_FocusTarget2 = null
        endif
        return
    endif
    call Trig_AIML_RebuildGroupEnemy()
    if dbg then
        call DisplayTextToForce(GetPlayersAll(), "[AIML] enemy=" + I2S(CountUnitsInGroup(udg_aiml_SalvoEnemyG)))
    endif
    if CountUnitsInGroup(udg_aiml_SalvoEnemyG) == 0 then
        return
    endif
    set picked = Trig_AIML_PickSalvoTarget()
    if dbg then
        if picked != null then
            call DisplayTextToForce(GetPlayersAll(), "[AIML] picked=" + GetUnitName(picked))
        else
            call DisplayTextToForce(GetPlayersAll(), "[AIML] picked=NULL")
        endif
    endif
    if picked == null then
        return
    endif
    if focusSlot == 1 then
        set udg_aiml_FocusTarget1 = picked
    else
        set udg_aiml_FocusTarget2 = picked
    endif
    // [V21 D3] Decide group-retreat for this tick before issuing attack/move orders.
    // Replaces V19/V20 kite logic. If ANY ranged unit has a threat in 350 radius,
    // the whole ranged team retreats together by GroupRetreatStep (default 100).
    call Trig_AIML_DecideRetreatForTick()
    set udg_aiml_DebugFirstUnit = null
    // [V22 DEBUG] FORCED on -- only fires on Player(1) (AI) tick to halve spam.
    if focusSlot == 2 then
        if udg_aiml_GroupRetreating then
            call DisplayTextToForce(GetPlayersAll(), "[V29] retreat=YES act=" + I2S(udg_aiml_RetreatAction) + " threats=" + I2S(udg_aiml_GlobalThreatCount) + " rangedN=" + I2S(udg_aiml_SalvoRangedCount) + " centroid=(" + R2S(udg_aiml_RangedCentroidX) + "," + R2S(udg_aiml_RangedCentroidY) + ") pt=(" + R2S(udg_aiml_GroupRetreatX) + "," + R2S(udg_aiml_GroupRetreatY) + ") step=" + R2S(udg_aiml_GroupRetreatStep))
        else
            call DisplayTextToForce(GetPlayersAll(), "[V22] retreat=no rangedN=" + I2S(udg_aiml_SalvoRangedCount) + " enemyN=" + I2S(CountUnitsInGroup(udg_aiml_SalvoEnemyG)))
        endif
    endif
    if dbg then
        if udg_aiml_GroupRetreating then
            call DisplayTextToForce(GetPlayersAll(), "[AIML] retreat=YES threats=" + I2S(udg_aiml_GlobalThreatCount) + " point=(" + R2S(udg_aiml_GroupRetreatX) + "," + R2S(udg_aiml_GroupRetreatY) + ")")
        else
            call DisplayTextToForce(GetPlayersAll(), "[AIML] retreat=no")
        endif
    endif
    // [V28] State machine for retreat phase (decided BEFORE ForGroup so all units act uniformly):
    //   Phase 0 = shooting (do nothing in callback). Transition: after 2 ticks of shooting -> phase 2.
    //   Phase 1 = just moved, must stop next. Transition: -> phase 0 (stop issued, now shoot).
    //   Phase 2 = ready to move. Transition: -> phase 1 (move issued).
    // [V28] Retreat state machine - decide action for this tick BEFORE ForGroup
    // udg_aiml_RetreatAction: 0=do-nothing(shoot), 1=stop, 2=move
    if udg_aiml_GroupRetreating then
        if udg_aiml_RetreatPhase == 0 then
            // Shooting: do nothing this tick
            set udg_aiml_RetreatAction = 0
            // [V30b] 1 tick shoot, then move
            set udg_aiml_RetreatPhase = 2
        elseif udg_aiml_RetreatPhase == 2 then
            // Move this tick
            set udg_aiml_RetreatAction = 2
            // Next tick must stop
            set udg_aiml_RetreatPhase = 1
        elseif udg_aiml_RetreatPhase == 1 then
            // Stop this tick
            set udg_aiml_RetreatAction = 1
            // Back to shoot
            set udg_aiml_RetreatPhase = 0
        endif
    else
        set udg_aiml_RetreatAction = 0
        set udg_aiml_RetreatPhase = 0
        set udg_aiml_RetreatShootTicks = 0
    endif
    // [V30] When retreating, move ALL units (including melee+heroes), not just ranged.
    // When retreating (move or stop tick), apply to entire army.
    // When not retreating or shoot tick, only ranged do salvo focus-fire.
    if udg_aiml_GroupRetreating and (udg_aiml_RetreatAction == 2 or udg_aiml_RetreatAction == 1) then
        // MOVE or STOP tick: entire army
        set udg_aiml_TempRetreatG = GetUnitsOfPlayerAll(udg_aiml_SalvoOwnerPlayer)
        call ForGroup(udg_aiml_TempRetreatG, function Trig_AIML_IssueAttackCB)
        call DestroyGroup(udg_aiml_TempRetreatG)
        set udg_aiml_TempRetreatG = null
    else
        call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_IssueAttackCB)
    endif
    // No post-ForGroup phase transition needed -- already done above.
endfunction

function Trig_AIML_SalvoTick takes nothing returns nothing
    set udg_aiml_SalvoDebugCounter = udg_aiml_SalvoDebugCounter + 1
    if udg_aiml_SalvoDebugCounter >= 10 then
        set udg_aiml_SalvoDebugCounter = 0
    endif
    call Trig_AIML_SalvoForPlayer(Player(0), Player(1), 1)
    call Trig_AIML_SalvoForPlayer(Player(1), Player(0), 2)
endfunction

function Trig_AIML_SalvoInit takes nothing returns nothing
    local trigger t
    local rect r
    // [V19] Explicit init -- 1.27 globals block default values are NOT reliable at runtime.
    // udg_* vars not assigned here will read as type default (boolean=false, real=0).
    set udg_aiml_StompMinEnemies = 2
    set udg_aiml_StompRadius = 250.00
    set udg_aiml_StompManaCost = 100.00
    set udg_aiml_StompHeroBypassRadius = 250.00
    set udg_aiml_FocusTarget1 = null
    set udg_aiml_FocusTarget2 = null
    set udg_aiml_SalvoMajorityRatio = 0.50
    set udg_aiml_SalvoFrontRowCount = 4
    set udg_aiml_SalvoMapRange = 99999.00
    set udg_aiml_KiteEnabled = true
    set udg_aiml_KiteMeleeAirRatio = 0.60
    set udg_aiml_KiteThreshold = 350.00
    set udg_aiml_KiteStep = 100.00
    set udg_aiml_KiteMinMapBound = 600.00
    set udg_aiml_KiteActiveThisTick = false
    // [V20] Per-unit local-threat tunables (still used as group-retreat trigger radius)
    set udg_aiml_LocalThreatRadius = 350.00
    set udg_aiml_LocalRetreatStep  = 150.00
    set udg_aiml_LocalThreatG = CreateGroup()
    // [V21 D3] Group-retreat tunables
    set udg_aiml_GroupRetreatStep = 200.00
    set udg_aiml_GroupRetreating = false
    set udg_aiml_GroupRetreatX = 0.0
    set udg_aiml_GroupRetreatY = 0.0
    set udg_aiml_TmpStartLoc = null
    set udg_aiml_SalvoDebugCounter = 0
    set udg_aiml_SalvoEnemyG = CreateGroup()
    set udg_aiml_SalvoArmyG = CreateGroup()
    set udg_aiml_SalvoRangedG = CreateGroup()
    // [V19 DEBUG] Confirm SalvoInit is actually invoked at map load
    // [AIML] V19 SalvoInit OK verified, suppressed by default; uncomment below to debug
    // if udg_aiml_KiteEnabled then
    //     call DisplayTimedTextToForce(GetPlayersAll(), 30.0, "[AIML] SalvoInit OK -- KiteEnabled=YES majRatio=" + R2S(udg_aiml_SalvoMajorityRatio))
    // else
    //     call DisplayTimedTextToForce(GetPlayersAll(), 30.0, "[AIML] SalvoInit OK -- KiteEnabled=no  majRatio=" + R2S(udg_aiml_SalvoMajorityRatio))
    // endif
    // [V19] Cache playable map bounds for kite clamping
    set r = GetPlayableMapRect()
    if r != null then
        set udg_aiml_KiteMapMinX = GetRectMinX(r)
        set udg_aiml_KiteMapMaxX = GetRectMaxX(r)
        set udg_aiml_KiteMapMinY = GetRectMinY(r)
        set udg_aiml_KiteMapMaxY = GetRectMaxY(r)
    endif
    set t = CreateTrigger()
    call TriggerRegisterTimerEvent(t, 0.50, true)
    call TriggerAddAction(t, function Trig_AIML_SalvoTick)
endfunction

"""


def detect_newline(src_bytes):
    if b"\r\n" in src_bytes[:4096]:
        return "\r\n"
    return "\n"


def inject(in_path, out_path):
    with open(in_path, "rb") as f:
        raw = f.read()
    nl = detect_newline(raw)
    src = raw.decode("latin-1")

    # 1) Hook TC stomp entries
    pattern = re.compile(
        r'function (Trig_Computer\d+Combat_AI_Func\d+A) takes nothing returns nothing'
        + re.escape(nl)
        + r'(\s*call IssueImmediateOrderBJ\(\s*GetEnumUnit\(\),\s*"stomp"\s*\))'
        + re.escape(nl)
        + r'endfunction'
    )
    matches = list(pattern.finditer(src))
    if not matches:
        pattern2 = re.compile(
            r'function (Trig_Computer\d+Combat_AI_Func\d+A) takes nothing returns nothing'
            + re.escape(nl)
            + r'(\s*call IssueImmediateOrder(?:BJ)?\([^)]*"stomp"[^)]*\))'
            + re.escape(nl)
            + r'endfunction'
        )
        matches = list(pattern2.finditer(src))

    for m in reversed(matches):
        fname = m.group(1)
        new_body = (
            f"function {fname} takes nothing returns nothing"
            + nl
            + "    // [AIML] replaced dumb stomp with smart logic"
            + nl
            + "    call Trig_AIML_TC_Stomp_Logic(GetEnumUnit())"
            + nl
            + "endfunction"
        )
        src = src[: m.start()] + new_body + src[m.end():]
        print(f"hooked stomp: {fname}")

    # 2) Inject AIML globals into endglobals
    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' found")
    extra_g = AIML_GLOBALS.replace("\n", nl) + nl
    idx = src.find(eg)
    src = src[:idx] + extra_g + src[idx:]

    # 3) Inject AIML functions after endglobals
    idx_after = src.find(eg) + len(eg)
    funcs = AIML_FUNCTIONS_TEMPLATE.replace(
        "__IS_RANGED_TROOP_PLACEHOLDER__", build_is_ranged_troop()
    )
    funcs = funcs.replace("\n", nl)
    src = src[:idx_after] + funcs + src[idx_after:]

    # 3.5) Neutralize old per-second AI "attack" dispatchers that conflict with our 0.5s salvo timer
    # OVU stage-2 AI = Player(1) goes Computer2 path; we also clean Computer1 for symmetry / future stages.
    # These functions originally force units to attack random neutral/player target every second,
    # which steals orders from our 0.5s salvo timer.
    DISPATCHERS_TO_NEUTRALIZE = [
        # (Computer2, OVU stage-2 actually triggered):
        "Trig_Computer2Combat_AI_Func016A",  # Ofar (ancient TC) attack
        "Trig_Computer2Combat_AI_Func017A",  # ohun (Headhunter) attack <- most critical
        "Trig_Computer2Combat_AI_Func018A",  # osw1 (Witch Doctor) attack
        "Trig_Computer2Combat_AI_Func025A",  # Orc misc grunt attack (excludes Ofar/ohun)
        # (Computer1, symmetric cleanup):
        "Trig_Computer1Combat_AI_Func016A",
        "Trig_Computer1Combat_AI_Func017A",
        "Trig_Computer1Combat_AI_Func018A",
        "Trig_Computer1Combat_AI_Func025A",
    ]
    neutralized = 0
    for fname in DISPATCHERS_TO_NEUTRALIZE:
        # 匹配整个函数体（从 function ... 到对应 endfunction）
        fpat = re.compile(
            r"function " + re.escape(fname) + r" takes nothing returns nothing"
            + re.escape(nl) + r".*?" + re.escape(nl) + r"endfunction",
            re.DOTALL,
        )
        new_body = (
            f"function {fname} takes nothing returns nothing" + nl
            + "    // [AIML] neutralized: replaced by 0.5s salvo timer to avoid order-conflict" + nl
            + "endfunction"
        )
        new_src, n = fpat.subn(new_body, src, count=1)
        if n == 1:
            src = new_src
            neutralized += 1
            print(f"neutralized: {fname}")
    print(f"total neutralized dispatchers: {neutralized}/{len(DISPATCHERS_TO_NEUTRALIZE)}")

    # 3.6) [V23] Neutralize Computer{1,2}Combat_AI_Actions's 2 leading GroupPointOrderLocBJ calls.
    # These run every 1s and force ALL Player(1) units (incl. headhunters) to attack-move to a
    # random Player(0) unit, completely overriding our 0.5s retreat IssuePointOrder.
    # Diagnosed by V22 debug screen output: retreat=YES kept firing but pt only drifted ~80
    # units in 10s -- because every 1s, the dispatcher pulled the entire ranged team back to
    # attack a player target. Fix: comment out the two lines (preserve as inline comments so
    # the file still parses and any side-effects of skipping them are documented).
    actions_to_clean = [
        "Trig_Computer2Combat_AI_Actions",
        "Trig_Computer1Combat_AI_Actions",
    ]
    for action_fn in actions_to_clean:
        # Find the function body and replace just the leading two GroupPointOrderLocBJ lines.
        action_pat = re.compile(
            r"(function " + re.escape(action_fn) + r" takes nothing returns nothing" + re.escape(nl) + r")"
            + r"((?:[ \t]*call GroupPointOrderLocBJ\([^\n\r]*\)" + re.escape(nl) + r"){1,2})",
            re.DOTALL,
        )
        m = action_pat.search(src)
        if not m:
            print(f"warning: {action_fn} leading GroupPointOrderLocBJ block not found")
            continue
        head = m.group(1)
        block = m.group(2)
        # Comment each call line
        commented = nl.join(
            ("    // [V23] neutralized: " + line.lstrip()) if line.strip().startswith("call GroupPointOrderLocBJ") else line
            for line in block.split(nl)
        )
        src = src[:m.start()] + head + commented + src[m.end():]
        print(f"neutralized actions-block: {action_fn} (commented {block.count('call GroupPointOrderLocBJ')} GroupPointOrderLocBJ lines)")

    # 4) Hook main() with SalvoInit
    main_pat = re.compile(
        r'function main takes nothing returns nothing' + re.escape(nl)
        + r'(.*?)' + re.escape(nl) + r'endfunction',
        re.DOTALL,
    )
    m_main = main_pat.search(src)
    if m_main and "call Trig_AIML_SalvoInit()" not in src:
        body = m_main.group(1)
        new_main = (
            f"function main takes nothing returns nothing{nl}"
            f"{body}{nl}"
            f"    call Trig_AIML_SalvoInit(){nl}"
            f"endfunction"
        )
        src = src[: m_main.start()] + new_main + src[m_main.end():]
        print("hooked main: SalvoInit")

    # 5) Write out
    with open(out_path, "wb") as f:
        f.write(src.encode("latin-1"))
    print(f"OK -> {out_path} ({len(src)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(64)
    inject(sys.argv[1], sys.argv[2])
