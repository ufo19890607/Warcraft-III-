#!/usr/bin/env python3
"""
inject_ai_shaman.py - Shadow Hunter AI (independent tick)

Finds the AI player's Shadow Hunter ('Oshd') and controls hex + healingwave
via its own timer tick.  Does NOT depend on Combat_AI hooks.

Injects:
  1. SH globals (hero HP tracking)
  2. SH functions (ScanHeroes, FindHealTarget, ActForUnit, Tick)
  3. SH_Init call in main()
  4. Clears original Func007A hex+healingwave body

usage: inject_ai_shaman.py <input.j> <output.j>
"""

import sys
import re
from ai_config import TICK_HERO_MAGIC

SH_GLOBALS = """    // [SHAMAN] Shadow Hunter AI globals
    real    udg_sh_HeroPrevHp1 = 0.0
    real    udg_sh_HeroPrevHp2 = 0.0
    real    udg_sh_HeroPrevHp3 = 0.0
    real    udg_sh_HeroPrevHp4 = 0.0
    unit    udg_sh_HeroUnit1   = null
    unit    udg_sh_HeroUnit2   = null
    unit    udg_sh_HeroUnit3   = null
    unit    udg_sh_HeroUnit4   = null
    boolean udg_sh_HexAttempted = false"""

SH_FUNCTIONS = """
//===========================================================================
// [SHAMAN] Shadow Hunter AI - hex on DK, healingwave on HP-drop hero
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
    // hex: check if previous hex attempt succeeded (buff appeared on DK)
    if udg_sh_HexAttempted then
        set udg_sh_HexAttempted = false
        set g = CreateGroup()
        call GroupEnumUnitsOfPlayer(g, enemyP, Condition(function Trig_AIML_SH_IsDK))
        set dk = FirstOfGroup(g)
        call DestroyGroup(g)
        set g = null
        if dk != null and not IsUnitType(dk, UNIT_TYPE_DEAD) then
            // hex buff: Bpsd (hex/burrow cocoon variant), check if present
            if GetUnitAbilityLevel(dk, 'Bpsd') > 0 then
                call DisplayTimedTextToForce(GetPlayersAll(), 2.00, "|cffff00ff[SHAMAN] HEX landed on DK|r")
            endif
        endif
        set dk = null
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
            set udg_sh_HexAttempted = true
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
    local unit sh
    local group g
    local integer i = 0
    loop
        exitwhen i >= 2
        if GetPlayerController(Player(i)) == MAP_CONTROL_COMPUTER and GetPlayerSlotState(Player(i)) == PLAYER_SLOT_STATE_PLAYING then
            set g = CreateGroup()
            call GroupEnumUnitsOfPlayer(g, Player(i), Condition(function Trig_AIML_SH_IsOshd))
            set sh = FirstOfGroup(g)
            call DestroyGroup(g)
            set g = null
            call Trig_AIML_SH_ScanHeroes(Player(i))
            call Trig_AIML_SH_ActForUnit(sh, Player(i), Player(1 - i))
            set sh = null
        endif
        set i = i + 1
    endloop
endfunction

function Trig_AIML_SH_Init takes nothing returns nothing
    local trigger t = CreateTrigger()
    call TriggerRegisterTimerEvent(t, __TICK_SHAMAN__, true)
    call TriggerAddAction(t, function Trig_AIML_SH_Tick)
    call DisplayTimedTextToForce(GetPlayersAll(), 5.00, "|cff00ff00[SHAMAN] init (tick=" + R2SW(__TICK_SHAMAN__,2,2) + "s)|r")
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

    # 1) Inject globals
    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' found")
    extra_g = SH_GLOBALS.replace("\n", nl) + nl
    idx = src.find(eg)
    src = src[:idx] + extra_g + src[idx:]
    print("[SHAMAN] inserted globals")

    # 2) Inject functions after endglobals
    idx_after = src.find(eg) + len(eg)
    funcs = SH_FUNCTIONS.replace("__TICK_SHAMAN__", f"{TICK_HERO_MAGIC:.2f}")
    funcs = funcs.replace("\n", nl)
    src = src[:idx_after] + funcs + src[idx_after:]
    print("[SHAMAN] inserted functions")

    # 3) Hook SH_Init into main() after TC_Stomp_Init or other AI init
    hook_point = None
    for anchor in [
        "call Trig_AIML_TC_Stomp_Init()",
        "call Trig_AIML_SurroundInit()",
        "call Trig_AIML_SalvoInit()",
    ]:
        if anchor in src:
            idx_anchor = src.find(anchor)
            idx_eol = src.find(nl, idx_anchor)
            hook_point = idx_eol + len(nl)
            break
    if hook_point is None:
        runit = "call RunInitializationTriggers(  )" + nl
        if runit in src:
            idx_runit = src.find(runit)
            hook_point = idx_runit + len(runit)

    if hook_point and "call Trig_AIML_SH_Init()" not in src:
        call_site = (
            "    // [SHAMAN] Shadow Hunter AI tick" + nl
            + "    call Trig_AIML_SH_Init()" + nl
        )
        src = src[:hook_point] + call_site + src[hook_point:]
        print("[SHAMAN] hooked SH_Init into main()")

    # 4) Clear original Func007A hex+healingwave body (both players)
    for pidx in ["1", "2"]:
        fname = f"Trig_Computer{pidx}Combat_AI_Func007A"
        marker = f"function {fname} takes nothing returns nothing"
        idx7 = src.find(marker)
        if idx7 == -1:
            print(f"  WARN: {fname} not found")
            continue
        end7 = src.find("endfunction", idx7)
        if end7 == -1:
            continue
        new_func = (
            f"function {fname} takes nothing returns nothing{nl}"
            f"    // [SHAMAN] handled by Trig_AIML_SH_Tick{nl}"
            f"endfunction"
        )
        src = src[:idx7] + new_func + src[end7 + len("endfunction"):]
        print(f"[SHAMAN] cleared {fname}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[SHAMAN] OK -> {out_path} ({len(src.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: inject_ai_shaman.py <input.j> <output.j>")
        sys.exit(1)
    inject(sys.argv[1], sys.argv[2])
