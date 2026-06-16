#!/usr/bin/env python3
"""
inject_ai_blademaster.py — Blademaster (剑圣) Escape AI

Injects BM escape logic into war3map.j:
- Detects HP drop >= 15% per tick -> triggers escape (mirror image > windwalk > smart retreat)
- WAIT state: maintains retreat order every tick (0.1s) to override mother scheduler (1s)
- Returns to NORMAL after 10 consecutive ticks (~1s) with no significant damage
- Re-engages nearest lowest-HP enemy within 1200 range

Hooks into HeroMagic 0.1s timer (SH_Tick endfunction).
"""

import re
import sys

# ─────────────────────────────────────────────────────────────────────
# JASS globals
# ─────────────────────────────────────────────────────────────────────
BM_GLOBALS = """
    // [BM-ESCAPE] Blademaster escape AI globals
    unit    udg_bm_Unit1       = null
    unit    udg_bm_Unit2       = null
    real    udg_bm_PrevHp1     = 0.0
    real    udg_bm_PrevHp2     = 0.0
    integer udg_bm_State1      = 0
    integer udg_bm_State2      = 0
    integer udg_bm_SafeTicks1  = 0
    integer udg_bm_SafeTicks2  = 0
    real    udg_bm_RetreatX1   = 0.0
    real    udg_bm_RetreatY1   = 0.0
    real    udg_bm_RetreatX2   = 0.0
    real    udg_bm_RetreatY2   = 0.0"""

# ─────────────────────────────────────────────────────────────────────
# JASS functions
# ─────────────────────────────────────────────────────────────────────
BM_FUNCTIONS = """
// ================================================================
// [BM-ESCAPE] Blademaster Escape AI
// ================================================================

function Trig_AIML_BM_IsObla takes nothing returns boolean
    return GetUnitTypeId(GetFilterUnit()) == 'Obla' and not IsUnitDeadBJ(GetFilterUnit())
endfunction

function Trig_AIML_BM_FindUnit takes player p returns unit
    local group g = CreateGroup()
    local unit u
    call GroupEnumUnitsOfPlayer(g, p, Condition(function Trig_AIML_BM_IsObla))
    set u = FirstOfGroup(g)
    call DestroyGroup(g)
    set g = null
    return u
endfunction

function Trig_AIML_BM_FindEnemyHero takes player enemyP returns unit
    local group g = CreateGroup()
    local unit u
    call GroupEnumUnitsOfPlayer(g, enemyP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitDeadBJ(u) then
            call DestroyGroup(g)
            set g = null
            return u
        endif
        call GroupRemoveUnit(g, u)
    endloop
    call DestroyGroup(g)
    set g = null
    return null
endfunction

function Trig_AIML_BM_TryCast takes unit bm returns nothing
    if IssueImmediateOrder(bm, "mirrorimage") == false then
        call IssueImmediateOrder(bm, "windwalk")
    endif
endfunction

function Trig_AIML_BM_UpdateRetreat takes unit bm, unit enemyHero, integer idx returns nothing
    local real bx = GetUnitX(bm)
    local real by = GetUnitY(bm)
    local real vx
    local real vy
    local real len
    local real rx
    local real ry
    if enemyHero != null then
        set vx = bx - GetUnitX(enemyHero)
        set vy = by - GetUnitY(enemyHero)
    else
        set vx = 0.0
        set vy = 1.0
    endif
    set len = SquareRoot(vx * vx + vy * vy)
    if len < 1.0 then
        set len = 1.0
    endif
    set rx = bx + vx / len * 1000.0
    set ry = by + vy / len * 1000.0
    if idx == 0 then
        set udg_bm_RetreatX1 = rx
        set udg_bm_RetreatY1 = ry
    else
        set udg_bm_RetreatX2 = rx
        set udg_bm_RetreatY2 = ry
    endif
    call IssuePointOrder(bm, "smart", rx, ry)
endfunction

function Trig_AIML_BM_AttackNearest takes unit bm, player enemyP returns nothing
    local group g = CreateGroup()
    local unit u
    local unit best = null
    local unit nearBest = null
    local real bestHp = 999999.0
    local real nearHp = 999999.0
    local real bx = GetUnitX(bm)
    local real by = GetUnitY(bm)
    local real dx
    local real dy
    local real d
    local real hp
    call GroupEnumUnitsOfPlayer(g, enemyP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        if not IsUnitDeadBJ(u) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set dx = GetUnitX(u) - bx
            set dy = GetUnitY(u) - by
            set d = dx * dx + dy * dy
            set hp = GetUnitState(u, UNIT_STATE_LIFE)
            if d <= 1440000.0 then
                if d <= 360000.0 and hp < nearHp then
                    set nearHp = hp
                    set nearBest = u
                endif
                if hp < bestHp then
                    set bestHp = hp
                    set best = u
                endif
            endif
        endif
        call GroupRemoveUnit(g, u)
    endloop
    call DestroyGroup(g)
    set g = null
    if nearBest != null then
        call IssueTargetOrder(bm, "attack", nearBest)
    elseif best != null then
        call IssueTargetOrder(bm, "attack", best)
    endif
    set best = null
    set nearBest = null
endfunction

function Trig_AIML_BM_TickForPlayer takes player myP, player enemyP, integer idx returns nothing
    local unit bm
    local unit enemyHero
    local real curHp
    local real maxHp
    local real prevHp
    local real drop
    local integer state
    local integer safeTicks
    set bm = Trig_AIML_BM_FindUnit(myP)
    if bm == null then
        return
    endif
    if IsUnitDeadBJ(bm) then
        set bm = null
        return
    endif
    set curHp = GetUnitState(bm, UNIT_STATE_LIFE)
    set maxHp = GetUnitState(bm, UNIT_STATE_MAX_LIFE)
    if idx == 0 then
        set prevHp = udg_bm_PrevHp1
        set state = udg_bm_State1
        set safeTicks = udg_bm_SafeTicks1
    else
        set prevHp = udg_bm_PrevHp2
        set state = udg_bm_State2
        set safeTicks = udg_bm_SafeTicks2
    endif
    if prevHp <= 0.0 then
        set prevHp = curHp
    endif
    set drop = prevHp - curHp
    if idx == 0 then
        set udg_bm_PrevHp1 = curHp
    else
        set udg_bm_PrevHp2 = curHp
    endif
    // ── EVADE trigger ──
    if drop >= maxHp * 0.15 then
        call Trig_AIML_BM_TryCast(bm)
        set enemyHero = Trig_AIML_BM_FindEnemyHero(enemyP)
        call Trig_AIML_BM_UpdateRetreat(bm, enemyHero, idx)
        if idx == 0 then
            set udg_bm_State1 = 1
            set udg_bm_SafeTicks1 = 0
        else
            set udg_bm_State2 = 1
            set udg_bm_SafeTicks2 = 0
        endif
        set enemyHero = null
        set bm = null
        return
    endif
    // ── WAIT state ──
    if state == 1 then
        if drop < maxHp * 0.02 then
            set safeTicks = safeTicks + 1
        else
            set safeTicks = 0
            call Trig_AIML_BM_TryCast(bm)
            set enemyHero = Trig_AIML_BM_FindEnemyHero(enemyP)
            call Trig_AIML_BM_UpdateRetreat(bm, enemyHero, idx)
            set enemyHero = null
        endif
        // Maintain retreat order every tick to override mother scheduler
        if safeTicks < 10 then
            if idx == 0 then
                call IssuePointOrder(bm, "smart", udg_bm_RetreatX1, udg_bm_RetreatY1)
            else
                call IssuePointOrder(bm, "smart", udg_bm_RetreatX2, udg_bm_RetreatY2)
            endif
        endif
        if idx == 0 then
            set udg_bm_SafeTicks1 = safeTicks
        else
            set udg_bm_SafeTicks2 = safeTicks
        endif
        if safeTicks >= 10 then
            if idx == 0 then
                set udg_bm_State1 = 0
            else
                set udg_bm_State2 = 0
            endif
            call Trig_AIML_BM_AttackNearest(bm, enemyP)
        endif
        set bm = null
        return
    endif
    // ── NORMAL: do nothing ──
    set bm = null
endfunction

function Trig_AIML_BM_Tick takes nothing returns nothing
    call Trig_AIML_BM_TickForPlayer(Player(0), Player(1), 0)
    call Trig_AIML_BM_TickForPlayer(Player(1), Player(0), 1)
endfunction
"""


def detect_newline(src_bytes):
    if b"\r\n" in src_bytes[:4096]:
        return "\r\n"
    return "\n"


def main():
    if len(sys.argv) < 2:
        print("Usage: inject_ai_blademaster.py <war3map.j>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "rb") as f:
        raw = f.read()
    nl = detect_newline(raw)
    src = raw.decode("utf-8")

    # Guard: already injected?
    if "function Trig_AIML_BM_Tick" in src:
        print("[BM-ESCAPE] already injected, skipping")
        return

    # 1) Inject globals before endglobals
    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' found")
    idx = src.find(eg)
    globals_text = BM_GLOBALS.replace("\n", nl) + nl
    src = src[:idx] + globals_text + src[idx:]
    print("[BM-ESCAPE] inserted globals")

    # 2) Inject functions before SH_Tick (so BM functions are defined before being called)
    marker = "function Trig_AIML_SH_Tick takes nothing returns nothing"
    idx_marker = src.find(marker)
    if idx_marker == -1:
        raise SystemExit("ERROR: cannot find Trig_AIML_SH_Tick — inject_hero_magic.py must run first")
    funcs_text = BM_FUNCTIONS.replace("\n", nl)
    src = src[:idx_marker] + funcs_text + nl + src[idx_marker:]
    print("[BM-ESCAPE] inserted functions")

    # 3) Hook BM_Tick call into SH_Tick (before its endfunction)
    sh_tick_start = src.find("function Trig_AIML_SH_Tick takes nothing returns nothing")
    sh_tick_end = src.find("endfunction", sh_tick_start + 10)
    if sh_tick_end == -1:
        raise SystemExit("ERROR: cannot find SH_Tick endfunction")
    hook_line = f"    call Trig_AIML_BM_Tick(){nl}"
    src = src[:sh_tick_end] + hook_line + src[sh_tick_end:]
    print("[BM-ESCAPE] hooked BM_Tick into SH_Tick")

    # 4) Add BM state reset in Variable Reset block
    reset_marker = "// Variable Reset"
    idx_reset = src.find(reset_marker)
    if idx_reset != -1:
        eol = src.index(nl, idx_reset)
        reset_code = (
            f"    set udg_bm_State1 = 0{nl}"
            f"    set udg_bm_State2 = 0{nl}"
            f"    set udg_bm_SafeTicks1 = 0{nl}"
            f"    set udg_bm_SafeTicks2 = 0{nl}"
            f"    set udg_bm_PrevHp1 = 0.0{nl}"
            f"    set udg_bm_PrevHp2 = 0.0{nl}"
            f"    set udg_bm_Unit1 = null{nl}"
            f"    set udg_bm_Unit2 = null{nl}"
        )
        src = src[:eol + len(nl)] + reset_code + src[eol + len(nl):]
        print("[BM-ESCAPE] added state reset to Variable Reset block")
    else:
        print("[BM-ESCAPE] WARN: Variable Reset block not found, skipping reset injection")

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[BM-ESCAPE] Blademaster escape AI injected into {path}")


if __name__ == "__main__":
    main()
