#!/usr/bin/env python3
"""
inject_ai_spirit_walker.py - Spirit Walker spell AI (V51d)

Hooks into SalvoTick (0.5s). Two phases per tick:
  1. Dispel: find friendly unit with Curse ('Bcrs') or Slow ('Bslo') buff
     (hero priority), cast Dispel Magic at its position
  2. Spirit Link: find friendly unit without Spirit Link ('Bslf') buff
     (hero priority), cast Spirit Link on it

Spirit Walker is NOT in Salvo ranged whitelist (would interrupt casts).
Movement handled by Combat_AI GroupPointOrderLocBJ "attack" (every 1s).

usage: inject_ai_spirit_walker.py <input.j> <output.j>
"""

import sys

SW_FUNCTIONS = r"""
//===========================================================================
// [SPIRIT WALKER] Spell AI - Dispel + Spirit Link (V51d)
//===========================================================================


// Find friendly unit with Curse or Slow buff (hero priority)
// Returns null if no unit needs dispel
// Spirit Link buff rawcode is Bspl (not Bslf), Curse debuff is Bcrs (not Bcur)
function Trig_AIML_SW_FindDispelTarget takes player myP returns unit
    local group g = CreateGroup()
    local unit u
    local unit bestHero = null
    local unit bestUnit = null
    local boolean diagDone = false
    call GroupEnumUnitsOfPlayer(g, myP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitDeadBJ(u) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            if not diagDone then
                set diagDone = true
            endif
            if GetUnitAbilityLevel(u, 'Bcrs') > 0 or GetUnitAbilityLevel(u, 'Bslo') > 0 then
                if IsUnitType(u, UNIT_TYPE_HERO) then
                    set bestHero = u
                else
                    set bestUnit = u
                endif
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    set u = null
    if bestHero != null then
        return bestHero
    endif
    return bestUnit
endfunction

// Find friendly unit without Spirit Link buff (hero priority)
// Returns null if all units already have Spirit Link
// Spirit Link buff rawcode confirmed as Bspl via diagnostic scan
function Trig_AIML_SW_FindSpiritLinkTarget takes player myP returns unit
    local group g = CreateGroup()
    local unit u
    local unit bestHero = null
    local unit bestUnit = null
    call GroupEnumUnitsOfPlayer(g, myP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitDeadBJ(u) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            if GetUnitAbilityLevel(u, 'Bspl') == 0 then
                if IsUnitType(u, UNIT_TYPE_HERO) then
                    set bestHero = u
                else
                    set bestUnit = u
                endif
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    set u = null
    if bestHero != null then
        return bestHero
    endif
    return bestUnit
endfunction

// Find a Spirit Walker with enough mana to cast (>= 75)
function Trig_AIML_SW_FindCaster takes player myP returns unit
    local group g = CreateGroup()
    local unit u
    local unit sw = null
    call GroupEnumUnitsOfPlayer(g, myP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitDeadBJ(u) and GetUnitTypeId(u) == 'ospw' then
            if GetUnitState(u, UNIT_STATE_MANA) >= 75.0 then
                set sw = u
                call GroupClear(g)
                exitwhen true
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    set u = null
    return sw
endfunction

// Main tick: called from SalvoTick for each computer player
function Trig_AIML_SW_TickForPlayer takes player myP, player enemyP returns nothing
    local unit sw
    local unit target

    // Phase 1: Dispel (priority)
    set target = Trig_AIML_SW_FindDispelTarget(myP)
    if target != null then
        set sw = Trig_AIML_SW_FindCaster(myP)
        if sw != null then
            call IssuePointOrder(sw, "dispel", GetUnitX(target), GetUnitY(target))
        endif
        set sw = null
        set target = null
        return
    endif

    // Phase 2: Spirit Link
    set target = Trig_AIML_SW_FindSpiritLinkTarget(myP)
    if target != null then
        set sw = Trig_AIML_SW_FindCaster(myP)
        if sw != null then
            call IssueTargetOrder(sw, "spiritlink", target)
        endif
        set sw = null
        set target = null
        return
    endif

    set sw = null
    set target = null
endfunction
"""

# SW_Tick calls to insert before SalvoTick endfunction
SW_HOOK_CODE = """    // [SW] Spirit Walker spell AI (V51d)
    if GetPlayerController(Player(0)) == MAP_CONTROL_COMPUTER then
        call Trig_AIML_SW_TickForPlayer(Player(0), Player(1))
    endif
    if GetPlayerController(Player(1)) == MAP_CONTROL_COMPUTER then
        call Trig_AIML_SW_TickForPlayer(Player(1), Player(0))
    endif
"""


def detect_newline(src_bytes):
    if b"\r\n" in src_bytes[:4096]:
        return "\r\n"
    return "\n"


def inject(src, nl):
    changes = 0

    # 1. Insert SW functions before SalvoTick
    marker = "function Trig_AIML_SalvoTick takes nothing returns nothing"
    idx = src.find(marker)
    if idx == -1:
        print("[SW] ERROR: cannot find SalvoTick marker")
        sys.exit(1)

    # Insert functions before the SalvoTick function
    insert_text = SW_FUNCTIONS.replace("\n", nl)
    src = src[:idx] + insert_text + nl + src[idx:]
    changes += 1
    print("[SW] inserted Spirit Walker functions before SalvoTick")

    # 2. Hook SW_Tick calls into SalvoTick (find endfunction, insert before it)
    marker = "function Trig_AIML_SalvoTick takes nothing returns nothing"
    idx = src.find(marker)
    if idx == -1:
        print("[SW] ERROR: cannot find SalvoTick for hook")
        sys.exit(1)

    endfunc_idx = src.find("endfunction", idx + 10)
    if endfunc_idx == -1:
        print("[SW] ERROR: cannot find SalvoTick endfunction")
        sys.exit(1)

    hook_text = SW_HOOK_CODE.replace("\n", nl)
    src = src[:endfunc_idx] + hook_text + src[endfunc_idx:]
    changes += 1
    print("[SW] hooked SW_Tick into SalvoTick")

    print(f"[SW] Spirit Walker spell AI injected ({changes} changes)")
    return src


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: inject_ai_spirit_walker.py <input.j> [output.j]")
        sys.exit(1)

    inpath = sys.argv[1]
    outpath = sys.argv[2] if len(sys.argv) > 2 else inpath

    with open(inpath, "rb") as f:
        src_bytes = f.read()

    nl = detect_newline(src_bytes)
    src = src_bytes.decode("utf-8")
    src = inject(src, nl)

    with open(outpath, "wb") as f:
        f.write(src.encode("utf-8"))

    print(f"[SW] wrote {outpath}")
