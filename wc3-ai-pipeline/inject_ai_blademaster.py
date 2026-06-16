#!/usr/bin/env python3
"""
inject_ai_blademaster.py — Blademaster (剑圣) Escape AI

Injects BM escape logic into war3map.j:
- Detects HP drop >= 15% per tick -> triggers windwalk -> smart retreat 600 yards
- WAIT state: maintains retreat order every tick (0.1s) to override mother scheduler (1s)
- Returns to NORMAL after 3-tick min-run guard + 5 consecutive safe ticks (drop <= 100)
- On re-engage: attack order breaks windwalk -> gains windwalk crit bonus on first hit
- Retreat order is NOT issued on the same tick as re-engage (avoids order collision)
- If windwalk on CD / no mana, attacks directly without entering WAIT
- NORMAL state has 1s cooldown before next EVADE (safeTicks=-10)

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
    real    udg_bm_RetreatY2   = 0.0
    integer udg_bm_WaitTick1   = 0
    integer udg_bm_WaitTick2   = 0"""

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

function Trig_AIML_BM_TryCast takes unit bm returns boolean
    local boolean ww
    set ww = IssueImmediateOrder(bm, "windwalk")
    if ww then
        call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[BM] windwalk OK|r")
    else
        call DisplayTextToForce(GetPlayersAll(), "|cffff0000[BM] windwalk CD/no mana!|r")
    endif
    return ww
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
    set rx = bx + vx / len * 600.0
    set ry = by + vy / len * 600.0
    if idx == 0 then
        set udg_bm_RetreatX1 = rx
        set udg_bm_RetreatY1 = ry
    else
        set udg_bm_RetreatX2 = rx
        set udg_bm_RetreatY2 = ry
    endif
    call DisplayTextToForce(GetPlayersAll(), "|cff88ccff[BM] retreat to (" + I2S(R2I(rx)) + "," + I2S(R2I(ry)) + ") dist=600|r")
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
    // Force-break windwalk: UnitRemoveBuffs removes all positive buffs (windwalk is positive)
    // This works regardless of the exact buff rawcode, and is safe even when not invisible
    if IsUnitInvisible(bm, enemyP) then
        call UnitRemoveBuffs(bm, true, false)
        call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] forced invis break via UnitRemoveBuffs|r")
    endif
    if nearBest != null then
        call IssueTargetOrder(bm, "attack", nearBest)
        call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[BM] STRIKE target=" + GetUnitName(nearBest) + " hp=" + I2S(R2I(GetUnitState(nearBest, UNIT_STATE_LIFE))) + "/" + I2S(R2I(GetUnitState(nearBest, UNIT_STATE_MAX_LIFE))) + " (near600)|r")
    elseif best != null then
        call IssueTargetOrder(bm, "attack", best)
        call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[BM] STRIKE target=" + GetUnitName(best) + " hp=" + I2S(R2I(GetUnitState(best, UNIT_STATE_LIFE))) + "/" + I2S(R2I(GetUnitState(best, UNIT_STATE_MAX_LIFE))) + " (best1200)|r")
    else
        call DisplayTextToForce(GetPlayersAll(), "|cffff0000[BM] STRIKE no target in 1200!|r")
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
    local integer waitTick
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
        set waitTick = udg_bm_WaitTick1
    else
        set prevHp = udg_bm_PrevHp2
        set state = udg_bm_State2
        set safeTicks = udg_bm_SafeTicks2
        set waitTick = udg_bm_WaitTick2
    endif
    if prevHp <= 0.0 then
        set prevHp = curHp
    endif
    set drop = prevHp - curHp
    if drop < 0.0 then
        set drop = 0.0
    endif
    if idx == 0 then
        set udg_bm_PrevHp1 = curHp
    else
        set udg_bm_PrevHp2 = curHp
    endif
    // ── EVADE trigger (only when cooldown expired) ──
    if state == 0 and safeTicks >= 0 and drop >= maxHp * 0.15 then
        call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] EVADE! hp=" + I2S(R2I(curHp)) + "/" + I2S(R2I(maxHp)) + " (drop " + I2S(R2I(drop)) + ")|r")
        if Trig_AIML_BM_TryCast(bm) then
            // Windwalk success -> enter WAIT, reset waitTick for min-run guard
            set enemyHero = Trig_AIML_BM_FindEnemyHero(enemyP)
            call Trig_AIML_BM_UpdateRetreat(bm, enemyHero, idx)
            if idx == 0 then
                set udg_bm_State1 = 1
                set udg_bm_SafeTicks1 = 0
                set udg_bm_WaitTick1 = 0
            else
                set udg_bm_State2 = 1
                set udg_bm_SafeTicks2 = 0
                set udg_bm_WaitTick2 = 0
            endif
            set enemyHero = null
        else
            // Windwalk CD/no mana -> attack directly, no WAIT
            call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] windwalk CD/no mana, attack directly!|r")
            call Trig_AIML_BM_AttackNearest(bm, enemyP)
            if idx == 0 then
                set udg_bm_SafeTicks1 = -10
            else
                set udg_bm_SafeTicks2 = -10
            endif
        endif
        set bm = null
        return
    endif
    // ── WAIT state ──
    if state == 1 then
        set waitTick = waitTick + 1
        if idx == 0 then
            set udg_bm_WaitTick1 = waitTick
        else
            set udg_bm_WaitTick2 = waitTick
        endif
        call DisplayTextToForce(GetPlayersAll(), "|cff88ccff[BM] WAIT wt=" + I2S(waitTick) + " safe=" + I2S(safeTicks) + " hp=" + I2S(R2I(curHp)) + " drop=" + I2S(R2I(drop)) + "|r")
        // Min-run guard: first 3 ticks (0.3s) always retreat, do not count safeTicks
        // This ensures BM runs some distance before striking back
        if waitTick <= 3 then
            if idx == 0 then
                call IssuePointOrder(bm, "smart", udg_bm_RetreatX1, udg_bm_RetreatY1)
            else
                call IssuePointOrder(bm, "smart", udg_bm_RetreatX2, udg_bm_RetreatY2)
            endif
            set bm = null
            return
        endif
        // After min-run: maintain retreat order every tick to override mother scheduler
        // Count safe ticks: HP drop <= 100 per tick (under windwalk, drop ~0, counts quickly)
        if drop <= 100.0 then
            set safeTicks = safeTicks + 1
        else
            set safeTicks = 0
        endif
        if idx == 0 then
            set udg_bm_SafeTicks1 = safeTicks
        else
            set udg_bm_SafeTicks2 = safeTicks
        endif
        if safeTicks >= 5 then
            // Re-engage: IssueTargetOrder(attack) breaks windwalk invisibility immediately
            // and gains windwalk critical strike bonus on first hit
            call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] WAIT->STRIKE! break windwalk safe=" + I2S(safeTicks) + " wt=" + I2S(waitTick) + "|r")
            if idx == 0 then
                set udg_bm_State1 = 0
                set udg_bm_SafeTicks1 = -10
            else
                set udg_bm_State2 = 0
                set udg_bm_SafeTicks2 = -10
            endif
            // Do NOT issue retreat order this tick — let attack be the only order
            call Trig_AIML_BM_AttackNearest(bm, enemyP)
        else
            // Still waiting: maintain retreat order
            if idx == 0 then
                call IssuePointOrder(bm, "smart", udg_bm_RetreatX1, udg_bm_RetreatY1)
            else
                call IssuePointOrder(bm, "smart", udg_bm_RetreatX2, udg_bm_RetreatY2)
            endif
        endif
        set bm = null
        return
    endif
    // ── NORMAL: count cooldown + maintain attack ──
    if safeTicks < 0 then
        set safeTicks = safeTicks + 1
        if idx == 0 then
            set udg_bm_SafeTicks1 = safeTicks
        else
            set udg_bm_SafeTicks2 = safeTicks
        endif
        // Re-issue attack every 3 ticks (0.3s) during cooldown to fill the gap
        // between our STRIKE order and the mother scheduler's next 1s cycle
        if ModuloInteger(safeTicks, 3) == 0 then
            call Trig_AIML_BM_AttackNearest(bm, enemyP)
        endif
    endif
    set bm = null
endfunction

function Trig_AIML_BM_Tick takes nothing returns nothing
    local player aiP
    local player enemyP
    // Find which player is computer-controlled (has the BM)
    if GetPlayerController(Player(0)) == MAP_CONTROL_COMPUTER then
        set aiP    = Player(0)
        set enemyP = Player(1)
    else
        set aiP    = Player(1)
        set enemyP = Player(0)
    endif
    call Trig_AIML_BM_TickForPlayer(aiP, enemyP, 0)
    set aiP    = null
    set enemyP = null
endfunction
"""


def detect_newline(src_bytes):
    if b"\r\n" in src_bytes[:4096]:
        return "\r\n"
    return "\n"



# -- BM Skill Learning: wk>cr>ww>cr>ww>cr>ww (windwalk + crit only, no mirror image) --
def patch_bm_skill_learn(j_text):
    nl = chr(10)
    q = chr(39)
    old_bm = (
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOwk" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOcr" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOcr" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOmi" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOcr" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOww" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOwk" + q + " )"
    )
    new_bm = (
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOwk" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOcr" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOww" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOcr" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOww" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOcr" + q + " )" + nl +
        "    call SelectHeroSkill( GetLastCreatedUnit(), " + q + "AOww" + q + " )"
    )
    if old_bm not in j_text:
        print("[BM-ESCAPE] WARNING: BM skill learning pattern not found, skip")
        return j_text
    j_text = j_text.replace(old_bm, new_bm)
    print("[BM-ESCAPE] patched BM skill learning: wk>cr>ww>cr>ww>cr>ww (no mirror image)")
    return j_text

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
            f"    set udg_bm_WaitTick1 = 0{nl}"
            f"    set udg_bm_WaitTick2 = 0{nl}"
            f"    set udg_bm_PrevHp1 = 0.0{nl}"
            f"    set udg_bm_PrevHp2 = 0.0{nl}"
            f"    set udg_bm_Unit1 = null{nl}"
            f"    set udg_bm_Unit2 = null{nl}"
        )
        src = src[:eol + len(nl)] + reset_code + src[eol + len(nl):]
        print("[BM-ESCAPE] added state reset to Variable Reset block")
    else:
        print("[BM-ESCAPE] WARN: Variable Reset block not found, skipping reset injection")

    # 5) Patch BM skill learning order
    src = patch_bm_skill_learn(src)

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[BM-ESCAPE] Blademaster escape AI injected into {path}")


if __name__ == "__main__":
    main()