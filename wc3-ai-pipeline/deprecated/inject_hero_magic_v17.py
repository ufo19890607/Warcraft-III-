#!/usr/bin/env python3
"""
inject_hero_magic.py - TC stomp + Shadow Hunter AI

Inject:
  1. TC smart war stomp (replaces dumb stomp Funcs)
  2. Shadow Hunter AI (configurable tick):
     - hex: cast on enemy Death Knight only
     - healingwave: cast when any ally hero HP drops >= 15% in one tick
  3. Clear original Func007A hex+healingwave body

usage: inject_hero_magic.py <input.j> <output.j>
"""
import sys
import re
from ai_config import TICK_HERO_MAGIC

# ---- Globals ----
MAGIC_GLOBALS = """    // [HERO-MAGIC] shared globals
    unit    udg_aiml_StompCaster = null
    integer udg_aiml_StompMinEnemies = 2
    real    udg_aiml_StompRadius = 250.00
    real    udg_aiml_StompManaCost = 100.00
    real    udg_aiml_StompHeroBypassRadius = 250.00
    // [HERO-MAGIC] Shadow Hunter AI globals
    real    udg_sh_HeroPrevHp1 = 0.0
    real    udg_sh_HeroPrevHp2 = 0.0
    real    udg_sh_HeroPrevHp3 = 0.0
    real    udg_sh_HeroPrevHp4 = 0.0
    unit    udg_sh_HeroUnit1   = null
    unit    udg_sh_HeroUnit2   = null
    unit    udg_sh_HeroUnit3   = null
    unit    udg_sh_HeroUnit4   = null"""


MAGIC_FUNCTIONS = """
//===========================================================================
// [HERO-MAGIC] TC Smart War Stomp
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
    call TriggerRegisterTimerEvent(t, __TICK_HERO_MAGIC__, true)
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
            + "    // [HERO-MAGIC] replaced dumb stomp with smart logic"
            + nl
            + "    call Trig_AIML_TC_Stomp_Logic(GetEnumUnit())"
            + nl
            + "endfunction"
        )
        src = src[: m.start()] + new_body + src[m.end():]
        print(f"[HERO-MAGIC] hooked stomp: {fname}")

    # 2) Inject globals into endglobals
    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' found")
    extra_g = MAGIC_GLOBALS.replace("\n", nl) + nl
    idx = src.find(eg)
    src = src[:idx] + extra_g + src[idx:]
    print("[HERO-MAGIC] inserted globals")

    # 3) Inject functions after endglobals
    idx_after = src.find(eg) + len(eg)
    funcs = MAGIC_FUNCTIONS.replace("__TICK_HERO_MAGIC__", f"{TICK_HERO_MAGIC:.2f}")
    funcs = funcs.replace("\n", nl)
    src = src[:idx_after] + funcs + src[idx_after:]
    print("[HERO-MAGIC] inserted functions")

    # 4) Hook SH_Init into main()
    main_pat = re.compile(
        r'function main takes nothing returns nothing' + re.escape(nl)
        + r'(.*?)' + re.escape(nl) + r'endfunction',
        re.DOTALL,
    )
    m_main = main_pat.search(src)
    if m_main and "call Trig_AIML_SH_Init()" not in src:
        body = m_main.group(1)
        new_main = (
            f"function main takes nothing returns nothing{nl}"
            f"{body}{nl}"
            f"    call Trig_AIML_SH_Init(){nl}"
            f"endfunction"
        )
        src = src[: m_main.start()] + new_main + src[m_main.end():]
        print("[HERO-MAGIC] hooked SH_Init into main()")

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
        print(f"[HERO-MAGIC] cleared {func_name}")

    # 6) Write out
    with open(out_path, "wb") as f:
        f.write(src.encode("latin-1"))
    print(f"[HERO-MAGIC] OK -> {out_path} ({len(src)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(64)
    inject(sys.argv[1], sys.argv[2])
