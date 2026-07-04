#!/usr/bin/env python3
"""
inject_ai_tc_stomp.py - TC smart war stomp (TC-ONLY, no SH)

Inject:
  1. TC smart war stomp (replaces dumb stomp Funcs with Trig_AIML_TC_Stomp_Logic)

usage: inject_ai_tc_stomp.py <input.j> <output.j>
"""
import sys
import re

# ---- Globals ----
MAGIC_GLOBALS = """    // [HERO-MAGIC] shared globals
    unit    udg_aiml_StompCaster = null
    integer udg_aiml_StompMinEnemies = 2
    real    udg_aiml_StompRadius = 250.00
    real    udg_aiml_StompManaCost = 100.00
    real    udg_aiml_StompHeroBypassRadius = 250.00
    // [HERO-MAGIC] Shadow Hunter AI handled by inject_ai_shaman.py"""


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

    # 4) Inject functions after endglobals (re-read position since globals shifted it)
    idx_after = src.find(eg) + len(eg)
    funcs = MAGIC_FUNCTIONS.replace("\n", nl)
    src = src[:idx_after] + funcs + src[idx_after:]
    print("[HERO-MAGIC] inserted functions")

    # 5) Write out
    with open(out_path, "wb") as f:
        f.write(src.encode("latin-1"))
    print(f"[HERO-MAGIC] OK -> {out_path} ({len(src)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(64)
    inject(sys.argv[1], sys.argv[2])
