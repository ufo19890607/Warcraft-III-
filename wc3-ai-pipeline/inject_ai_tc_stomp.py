#!/usr/bin/env python3
"""
inject_ai_tc_stomp.py - TC Smart War Stomp (independent tick)

Finds the AI player's Tauren Chieftain ('Ofar') and controls stomp via its own
timer tick.  Does NOT depend on Combat_AI hooks or dumb stomp in the base map.

Injects:
  1. TC stomp globals
  2. Smart stomp logic (Trig_AIML_TC_Stomp_Logic + helpers)
  3. TC stomp tick + init via SH_Tick (reuses hero_magic tick interval)
  4. Patches Ofar Combat_AI funcs to call smart stomp instead of raw attack

Replaces the TC stomp portion of inject_hero_magic.py.
"""

import sys
import re
from ai_config import TICK_HERO_MAGIC

# ---- Globals ----
TC_STOMP_GLOBALS = """    // [TC-STOMP] globals
    unit    udg_aiml_StompCaster = null
    integer udg_aiml_StompMinEnemies = 2
    real    udg_aiml_StompRadius = 250.00
    real    udg_aiml_StompManaCost = 100.00
    real    udg_aiml_StompHeroBypassRadius = 250.00"""

# ---- Functions ----
TC_STOMP_FUNCTIONS = """
//===========================================================================
// [TC-STOMP] TC Smart War Stomp
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
        call DisplayTimedTextToForce(GetPlayersAll(), 2.00, "|cffff8800[TC-STOMP] STOMP (hero nearby!)|r")
        call DestroyGroup(g)
        return
    endif
    call GroupEnumUnitsInRange(g, cx, cy, udg_aiml_StompRadius, Filter(function Trig_AIML_IsValidStompTarget))
    set count = CountUnitsInGroup(g)
    if count >= udg_aiml_StompMinEnemies then
        call IssueImmediateOrder(tc, "stomp")
        call DisplayTimedTextToForce(GetPlayersAll(), 2.00, "|cff00ff00[TC-STOMP] STOMP (" + I2S(count) + " enemies)|r")
    endif
    call DestroyGroup(g)
endfunction

//===========================================================================
// [TC-STOMP] TC Stomp Tick — controls AI TC hero directly
//===========================================================================
function Trig_AIML_TC_Stomp_IsOfar takes nothing returns boolean
    return GetUnitTypeId(GetFilterUnit()) == 'Ofar' and not IsUnitDeadBJ(GetFilterUnit())
endfunction

function Trig_AIML_TC_Stomp_Tick takes nothing returns nothing
    local group g = CreateGroup()
    local unit tc
    local integer i = 0
    loop
        exitwhen i >= 2
        if GetPlayerController(Player(i)) == MAP_CONTROL_COMPUTER and GetPlayerSlotState(Player(i)) == PLAYER_SLOT_STATE_PLAYING then
            call GroupEnumUnitsOfPlayer(g, Player(i), Condition(function Trig_AIML_TC_Stomp_IsOfar))
            set tc = FirstOfGroup(g)
            call GroupClear(g)
            call Trig_AIML_TC_Stomp_Logic(tc)
            set tc = null
        endif
        set i = i + 1
    endloop
    call DestroyGroup(g)
endfunction

function Trig_AIML_TC_Stomp_Init takes nothing returns nothing
    local trigger t = CreateTrigger()
    call TriggerRegisterTimerEvent(t, __TICK_TC_STOMP__, true)
    call TriggerAddAction(t, function Trig_AIML_TC_Stomp_Tick)
    call DisplayTimedTextToForce(GetPlayersAll(), 5.00, "|cff00ff00[TC-STOMP] init (tick=" + R2SW(__TICK_TC_STOMP__,2,2) + "s)|r")
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
    extra_g = TC_STOMP_GLOBALS.replace("\n", nl) + nl
    idx = src.find(eg)
    src = src[:idx] + extra_g + src[idx:]
    print("[TC-STOMP] inserted globals")

    # 2) Inject functions after endglobals
    idx_after = src.find(eg) + len(eg)
    funcs = TC_STOMP_FUNCTIONS.replace("__TICK_TC_STOMP__", f"{TICK_HERO_MAGIC:.2f}")
    funcs = funcs.replace("\n", nl)
    src = src[:idx_after] + funcs + src[idx_after:]
    print("[TC-STOMP] inserted functions")

    # 3) Hook TC_Stomp_Init into main() after existing SH_Init / SalvoInit etc
    #    Find the last inject_ai init call in main() and append after it
    #    If Trig_AIML_SurroundInit exists, hook after it; otherwise after RunInitializationTriggers
    hook_point = None
    for anchor in ["call Trig_AIML_SurroundInit()", "call Trig_AIML_SH_Init()", "call Trig_AIML_SalvoInit()"]:
        if anchor in src:
            idx_anchor = src.find(anchor)
            # Find end of this line
            idx_eol = src.find(nl, idx_anchor)
            hook_point = idx_eol + len(nl)
            break
    if hook_point is None:
        # Fallback: after RunInitializationTriggers
        runit = "call RunInitializationTriggers(  )" + nl
        if runit in src:
            idx_runit = src.find(runit)
            hook_point = idx_runit + len(runit)

    if hook_point:
        call_site = (
            "    // [TC-STOMP] independent TC stomp tick" + nl
            + "    call Trig_AIML_TC_Stomp_Init()" + nl
        )
        src = src[:hook_point] + call_site + src[hook_point:]
        print("[TC-STOMP] hooked TC_Stomp_Init into main()")

    # 4) Patch Ofar Combat_AI functions to use smart stomp instead of raw attack
    ofar_funcs = []
    for line_s in src.split(nl):
        if "ForGroupBJ" in line_s and "Ofar" in line_s and "function Trig_Computer" in line_s:
            fn_start = line_s.find("function ") + len("function ")
            fn_end = line_s.find(" )", fn_start)
            if fn_end == -1:
                fn_end = line_s.find(")", fn_start)
            fn_name = line_s[fn_start:fn_end].strip()
            ofar_funcs.append(fn_name)

    seen = set()
    for fn_name in ofar_funcs:
        if fn_name in seen:
            continue
        seen.add(fn_name)
        old_header = "function " + fn_name + " takes nothing returns nothing" + nl
        idx_func = src.find(old_header)
        if idx_func == -1:
            continue
        idx_end = src.find(nl + "endfunction", idx_func)
        if idx_end == -1:
            continue
        idx_end += len(nl + "endfunction")
        new_body = (
            "function " + fn_name + " takes nothing returns nothing"
            + nl
            + "    // [TC-STOMP] smart stomp"
            + nl
            + "    call Trig_AIML_TC_Stomp_Logic(GetEnumUnit())"
            + nl
            + "endfunction"
        )
        src = src[:idx_func] + new_body + src[idx_end:]
        print(f"[TC-STOMP] patched Ofar Combat_AI: {fn_name}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[TC-STOMP] OK -> {out_path} ({len(src.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: inject_ai_tc_stomp.py <input.j> <output.j>")
        sys.exit(1)
    inject(sys.argv[1], sys.argv[2])
