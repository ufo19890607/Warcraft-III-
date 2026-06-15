#!/usr/bin/env python3
"""
inject_hero_magic.py - TC stomp + ranged SALVO + Shadow Hunter AI

Inject:
  1. TC smart war stomp (replaces dumb stomp Funcs)
  2. Ranged-force concentrated salvo with custom unit whitelist
  3. Shadow Hunter AI (0.1s tick):
     - hex: cast on enemy Death Knight only
     - healingwave: cast when any ally hero HP drops >= 15% in one tick

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
AIML_GLOBALS = """    // [AIML] shared globals
    boolean udg_aiml_DebugMode = false
    unit    udg_aiml_LastFireTarget = null
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
    // [HERO-MAGIC] Shadow Hunter AI globals
    real    udg_sh_HeroPrevHp1 = 0.0
    real    udg_sh_HeroPrevHp2 = 0.0
    real    udg_sh_HeroPrevHp3 = 0.0
    real    udg_sh_HeroPrevHp4 = 0.0
    unit    udg_sh_HeroUnit1   = null
    unit    udg_sh_HeroUnit2   = null
    unit    udg_sh_HeroUnit3   = null
    unit    udg_sh_HeroUnit4   = null"""


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

function Trig_AIML_IssueAttackCB takes nothing returns nothing
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

function Trig_AIML_SalvoForPlayer takes player p, player ep, integer focusSlot returns nothing
    local unit picked
    set udg_aiml_SalvoOwnerPlayer = p
    set udg_aiml_SalvoEnemyPlayer = ep
    call Trig_AIML_RebuildGroupArmy()
    if udg_aiml_SalvoArmyCount == 0 then
        return
    endif
    call Trig_AIML_RebuildGroupRanged()
    if I2R(udg_aiml_SalvoRangedCount) < I2R(udg_aiml_SalvoArmyCount) * udg_aiml_SalvoMajorityRatio then
        if focusSlot == 1 then
            set udg_aiml_FocusTarget1 = null
        else
            set udg_aiml_FocusTarget2 = null
        endif
        return
    endif
    call Trig_AIML_RebuildGroupEnemy()
    if CountUnitsInGroup(udg_aiml_SalvoEnemyG) == 0 then
        return
    endif
    set picked = Trig_AIML_PickSalvoTarget()
    if picked == null then
        return
    endif
    if udg_aiml_DebugMode and picked != udg_aiml_LastFireTarget and udg_RoundNo != 1 then
        call DisplayTextToForce(GetPlayersAll(), "[AIML] FIRE >> " + GetUnitName(picked) + " (HP:" + I2S(R2I(GetUnitStateSwap(UNIT_STATE_LIFE, picked))) + ")")
        set udg_aiml_LastFireTarget = picked
    endif
    if focusSlot == 1 then
        set udg_aiml_FocusTarget1 = picked
    else
        set udg_aiml_FocusTarget2 = picked
    endif
    call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_IssueAttackCB)
endfunction

function Trig_AIML_SalvoTick takes nothing returns nothing
    call Trig_AIML_SalvoForPlayer(Player(0), Player(1), 1)
    call Trig_AIML_SalvoForPlayer(Player(1), Player(0), 2)
endfunction

function Trig_AIML_SalvoInit takes nothing returns nothing
    local trigger t
    set udg_aiml_SalvoEnemyG = CreateGroup()
    set udg_aiml_SalvoArmyG = CreateGroup()
    set udg_aiml_SalvoRangedG = CreateGroup()
    set t = CreateTrigger()
    call TriggerRegisterTimerEvent(t, 0.10, true)
    call TriggerAddAction(t, function Trig_AIML_SalvoTick)
endfunction

//===========================================================================
// [HERO-MAGIC] Shadow Hunter AI - hex on DK, healingwave on HP-drop hero
//===========================================================================
// Scan allied heroes, record HP, detect drop this tick
function Trig_AIML_SH_ScanHeroes takes player p returns nothing
    local group g = CreateGroup()
    local unit u
    local integer i = 0
    call GroupEnumUnitsOfPlayer(g, p, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitType(u, UNIT_TYPE_DEAD) then
            set i = i + 1
            if i == 1 then
                set udg_sh_HeroUnit1 = u
            elseif i == 2 then
                set udg_sh_HeroUnit2 = u
            elseif i == 3 then
                set udg_sh_HeroUnit3 = u
            elseif i == 4 then
                set udg_sh_HeroUnit4 = u
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
endfunction

// Find ally hero with largest HP drop (>=15%)
function Trig_AIML_SH_FindHealTarget takes nothing returns unit
    local unit best = null
    local real bestDrop = 0.0
    local real maxHp
    local real curHp
    local real drop
    // hero1
    if udg_sh_HeroUnit1 != null and not IsUnitType(udg_sh_HeroUnit1, UNIT_TYPE_DEAD) then
        set maxHp = GetUnitState(udg_sh_HeroUnit1, UNIT_STATE_MAX_LIFE)
        set curHp = GetUnitState(udg_sh_HeroUnit1, UNIT_STATE_LIFE)
        if maxHp > 0.0 then
            set drop = udg_sh_HeroPrevHp1 - curHp
            if drop >= maxHp * 0.15 and drop > bestDrop then
                set bestDrop = drop
                set best = udg_sh_HeroUnit1
            endif
        endif
        set udg_sh_HeroPrevHp1 = curHp
    endif
    // hero2
    if udg_sh_HeroUnit2 != null and not IsUnitType(udg_sh_HeroUnit2, UNIT_TYPE_DEAD) then
        set maxHp = GetUnitState(udg_sh_HeroUnit2, UNIT_STATE_MAX_LIFE)
        set curHp = GetUnitState(udg_sh_HeroUnit2, UNIT_STATE_LIFE)
        if maxHp > 0.0 then
            set drop = udg_sh_HeroPrevHp2 - curHp
            if drop >= maxHp * 0.15 and drop > bestDrop then
                set bestDrop = drop
                set best = udg_sh_HeroUnit2
            endif
        endif
        set udg_sh_HeroPrevHp2 = curHp
    endif
    // hero3
    if udg_sh_HeroUnit3 != null and not IsUnitType(udg_sh_HeroUnit3, UNIT_TYPE_DEAD) then
        set maxHp = GetUnitState(udg_sh_HeroUnit3, UNIT_STATE_MAX_LIFE)
        set curHp = GetUnitState(udg_sh_HeroUnit3, UNIT_STATE_LIFE)
        if maxHp > 0.0 then
            set drop = udg_sh_HeroPrevHp3 - curHp
            if drop >= maxHp * 0.15 and drop > bestDrop then
                set bestDrop = drop
                set best = udg_sh_HeroUnit3
            endif
        endif
        set udg_sh_HeroPrevHp3 = curHp
    endif
    // hero4
    if udg_sh_HeroUnit4 != null and not IsUnitType(udg_sh_HeroUnit4, UNIT_TYPE_DEAD) then
        set maxHp = GetUnitState(udg_sh_HeroUnit4, UNIT_STATE_MAX_LIFE)
        set curHp = GetUnitState(udg_sh_HeroUnit4, UNIT_STATE_LIFE)
        if maxHp > 0.0 then
            set drop = udg_sh_HeroPrevHp4 - curHp
            if drop >= maxHp * 0.15 and drop > bestDrop then
                set bestDrop = drop
                set best = udg_sh_HeroUnit4
            endif
        endif
        set udg_sh_HeroPrevHp4 = curHp
    endif
    return best
endfunction

function Trig_AIML_SH_IsDK takes nothing returns boolean
    return GetUnitTypeId(GetFilterUnit()) == 'Udea' and not IsUnitType(GetFilterUnit(), UNIT_TYPE_DEAD)
endfunction

function Trig_AIML_SH_IsOshd takes nothing returns boolean
    return GetUnitTypeId(GetFilterUnit()) == 'Oshd' and not IsUnitType(GetFilterUnit(), UNIT_TYPE_DEAD)
endfunction

// Execute Shadow Hunter AI for one unit
function Trig_AIML_SH_ActForUnit takes unit sh, player ownP, player enemyP returns nothing
    local unit dk
    local unit healTgt
    local group g
    if sh == null or IsUnitType(sh, UNIT_TYPE_DEAD) then
        return
    endif
    // hex: target enemy Death Knight 'Udea', cast if enough mana
    if GetUnitState(sh, UNIT_STATE_MANA) >= 75.0 then
        set g = CreateGroup()
        call GroupEnumUnitsOfPlayer(g, enemyP, Condition(function Trig_AIML_SH_IsDK))
        set dk = FirstOfGroup(g)
        call DestroyGroup(g)
        set g = null
        if dk != null and not IsUnitType(dk, UNIT_TYPE_DEAD) then
            call IssueTargetOrder(sh, "hex", dk)
            set dk = null
            return
        endif
        set dk = null
    endif
    // healingwave: check ally hero HP drop >= 15%
    set healTgt = Trig_AIML_SH_FindHealTarget()
    if healTgt != null then
        if GetUnitState(sh, UNIT_STATE_MANA) >= 65.0 then
            call IssueTargetOrder(sh, "healingwave", healTgt)
        endif
    endif
    set healTgt = null
endfunction

function Trig_AIML_SH_Tick takes nothing returns nothing
    local unit sh1
    local unit sh2
    local group g
    // Shadow Hunter for Player(0)
    set g = CreateGroup()
    call GroupEnumUnitsOfPlayer(g, Player(0), Condition(function Trig_AIML_SH_IsOshd))
    set sh1 = FirstOfGroup(g)
    call DestroyGroup(g)
    set g = null
    call Trig_AIML_SH_ScanHeroes(Player(0))
    call Trig_AIML_SH_ActForUnit(sh1, Player(0), Player(1))
    set sh1 = null
    // Shadow Hunter for Player(1)
    set g = CreateGroup()
    call GroupEnumUnitsOfPlayer(g, Player(1), Condition(function Trig_AIML_SH_IsOshd))
    set sh2 = FirstOfGroup(g)
    call DestroyGroup(g)
    set g = null
    call Trig_AIML_SH_ScanHeroes(Player(1))
    call Trig_AIML_SH_ActForUnit(sh2, Player(1), Player(0))
    set sh2 = null
endfunction

function Trig_AIML_SH_Init takes nothing returns nothing
    local trigger t = CreateTrigger()
    call TriggerRegisterTimerEvent(t, 0.10, true)
    call TriggerAddAction(t, function Trig_AIML_SH_Tick)
    set t = null
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
    if not matches:
        # pattern3: GetAttackedUnitBJ() form
        pattern3 = re.compile(
            r'function (Trig_Computer\d+Combat_AI_Func\d+A) takes nothing returns nothing'
            + re.escape(nl)
            + r'(\s*call IssueImmediateOrderBJ\(\s*GetAttackedUnitBJ\(\),\s*"stomp"\s*\))'
            + re.escape(nl)
            + r'endfunction'
        )
        matches = list(pattern3.finditer(src))

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

    # 4) Hook main() with SalvoInit + SH_Init
    main_pat = re.compile(
        r'function main takes nothing returns nothing' + re.escape(nl)
        + r'(.*?)' + re.escape(nl) + r'endfunction',
        re.DOTALL,
    )
    m_main = main_pat.search(src)
    if m_main:
        body = m_main.group(1)
        hooks = ""
        if "call Trig_AIML_SalvoInit()" not in src:
            hooks += f"    call Trig_AIML_SalvoInit(){nl}"
        if "call Trig_AIML_SH_Init()" not in src:
            hooks += f"    call Trig_AIML_SH_Init(){nl}"
        if hooks:
            new_main = (
                f"function main takes nothing returns nothing{nl}"
                f"{body}{nl}"
                f"{hooks}"
                f"endfunction"
            )
            src = src[: m_main.start()] + new_main + src[m_main.end():]
            print("hooked main: SalvoInit + SH_Init")

    # 5) Clear original Func007A hex+healingwave body (both players)
    for player_idx in ["1", "2"]:
        func_name = f"Trig_Computer{player_idx}Combat_AI_Func007A"
        marker = f"function {func_name} takes nothing returns nothing"
        idx7 = src.find(marker)
        if idx7 == -1:
            print(f"WARN: {func_name} not found, skipping")
            continue
        end7 = src.find("endfunction", idx7)
        if end7 == -1:
            continue
        new_func = (
            f"function {func_name} takes nothing returns nothing{nl}"
            f"    // [HERO-MAGIC] Shadow Hunter AI handled by Trig_AIML_SH_Tick{nl}"
            f"endfunction"
        )
        src = src[:idx7] + new_func + src[end7 + len("endfunction"):]
        print(f"cleared {func_name}")

    # 6) Write out
    with open(out_path, "wb") as f:
        f.write(src.encode("latin-1"))
    print(f"OK -> {out_path} ({len(src)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(64)
    inject(sys.argv[1], sys.argv[2])
