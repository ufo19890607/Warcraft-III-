#!/usr/bin/env python3
"""
inject_ai_blademaster.py — Blademaster (剑圣) Escape + Hunt AI

State machine:
  state=0  NORMAL
  state=1  WAIT   (EVADE撤退中)
  state=2  HUNT   (疾风步穿身突进残血英雄)

EVADE (被集火逃跑):
- Detects HP drop >= 15% per tick -> TryCast windwalk
  - success -> smart retreat 600 yards, enter WAIT
  - fail    -> AttackNearest, safeTicks=-10
- WAIT: 3-tick min-run guard, then 5 safe ticks (drop<=100) -> NORMAL
- On NORMAL re-engage: UnitRemoveBuffs + AttackNearest

HUNT (主动猎杀残血英雄):
- NORMAL (safeTicks>=0 or <0): scan enemy hero dist<2000 and HP<300
- TryCast windwalk success -> enter HUNT(state=2), smart move toward target
- TryCast fail (CD/no mana) -> do nothing, wait for CD
- HUNT state: every tick issue smart toward huntTarget
  - Boro buff gone -> UnitRemoveBuffs + attack(huntTarget) -> NORMAL safeTicks=-10
  - target dead / dist>2000 -> NORMAL safeTicks=0
  - BM focused (drop>=15%) -> EVADE takes priority

AttackNearest 目标优先级:
- UnitRemoveBuffs first (break invis regardless)
- 1. 600码内最低HP (nearBest)
- 2. 1200码内最低HP (best, 兜底)
- 3. 无目标 -> 不发指令 (母调度接管)

Skill learning: wk>cr>ww>cr>ww>cr>ww (no mirror image)

Hooks into HeroMagic 0.1s timer (SH_Tick endfunction).
"""

import sys

# ─────────────────────────────────────────────────────────────────────
# JASS globals
# ─────────────────────────────────────────────────────────────────────
BM_GLOBALS = """
    // [BM] Blademaster escape + hunt AI globals
    unit    udg_bm_Unit1        = null
    unit    udg_bm_Unit2        = null
    real    udg_bm_PrevHp1      = 0.0
    real    udg_bm_PrevHp2      = 0.0
    integer udg_bm_State1       = 0
    integer udg_bm_State2       = 0
    integer udg_bm_SafeTicks1   = 0
    integer udg_bm_SafeTicks2   = 0
    real    udg_bm_RetreatX1    = 0.0
    real    udg_bm_RetreatY1    = 0.0
    real    udg_bm_RetreatX2    = 0.0
    real    udg_bm_RetreatY2    = 0.0
    integer udg_bm_WaitTick1    = 0
    integer udg_bm_WaitTick2    = 0
    unit    udg_bm_HuntTarget1  = null
    unit    udg_bm_HuntTarget2  = null"""

# ─────────────────────────────────────────────────────────────────────
# JASS functions
# ─────────────────────────────────────────────────────────────────────
BM_FUNCTIONS = """
// ================================================================
// [BM] Blademaster AI  state=0:NORMAL  1:WAIT  2:HUNT
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

// 找距离<2000且HP<300的敌方英雄
function Trig_AIML_BM_FindHuntTarget takes unit bm, player enemyP returns unit
    local group g = CreateGroup()
    local unit u
    local real bx = GetUnitX(bm)
    local real by = GetUnitY(bm)
    local real dx
    local real dy
    call GroupEnumUnitsOfPlayer(g, enemyP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitDeadBJ(u) then
            if GetUnitState(u, UNIT_STATE_LIFE) < 300.0 then
                set dx = GetUnitX(u) - bx
                set dy = GetUnitY(u) - by
                if dx * dx + dy * dy < 4000000.0 then  // 2000码
                    call DestroyGroup(g)
                    set g = null
                    return u
                endif
            endif
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

function Trig_AIML_BM_AttackDK takes unit bm, player enemyP returns nothing
    local group g = CreateGroup()
    local unit u
    local unit dk = null
    // 先解除隐身
    if IsUnitInvisible(bm, enemyP) then
        call UnitRemoveBuffs(bm, true, false)
        call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] invis break|r")
    endif
    call GroupEnumUnitsOfPlayer(g, enemyP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        if GetUnitTypeId(u) == 'Udea' and not IsUnitDeadBJ(u) then
            set dk = u
        endif
        call GroupRemoveUnit(g, u)
    endloop
    call DestroyGroup(g)
    set g = null
    if dk != null then
        call IssueTargetOrder(bm, "attack", dk)
        call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] POST-WW ATTACK DK hp=" + I2S(R2I(GetUnitState(dk, UNIT_STATE_LIFE))) + "|r")
    else
        call DisplayTextToForce(GetPlayersAll(), "|cffff0000[BM] POST-WW DK not found!|r")
    endif
    set dk = null
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
    // 先解除隐身（无论有无目标）
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
    local unit huntTarget
    local real curHp
    local real maxHp
    local real prevHp
    local real drop
    local real dx
    local real dy
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
        set prevHp     = udg_bm_PrevHp1
        set state      = udg_bm_State1
        set safeTicks  = udg_bm_SafeTicks1
        set waitTick   = udg_bm_WaitTick1
        set huntTarget = udg_bm_HuntTarget1
    else
        set prevHp     = udg_bm_PrevHp2
        set state      = udg_bm_State2
        set safeTicks  = udg_bm_SafeTicks2
        set waitTick   = udg_bm_WaitTick2
        set huntTarget = udg_bm_HuntTarget2
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

    // ── WAIT state ──────────────────────────────────────────────────
    if state == 1 then
        set waitTick = waitTick + 1
        if idx == 0 then
            set udg_bm_WaitTick1 = waitTick
        else
            set udg_bm_WaitTick2 = waitTick
        endif
        if waitTick == 1 then
            call DisplayTextToForce(GetPlayersAll(), "|cff88ccff[BM] WAIT start hp=" + I2S(R2I(curHp)) + "/" + I2S(R2I(maxHp)) + "|r")
        endif
        // min-run guard: 前3tick强制撤退
        if waitTick <= 3 then
            if idx == 0 then
                call IssuePointOrder(bm, "smart", udg_bm_RetreatX1, udg_bm_RetreatY1)
            else
                call IssuePointOrder(bm, "smart", udg_bm_RetreatX2, udg_bm_RetreatY2)
            endif
            set bm = null
            return
        endif
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
            call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] WAIT->STRIKE! safe=" + I2S(safeTicks) + " wt=" + I2S(waitTick) + "|r")
            if idx == 0 then
                set udg_bm_State1 = 0
                set udg_bm_SafeTicks1 = -10
            else
                set udg_bm_State2 = 0
                set udg_bm_SafeTicks2 = -10
            endif
            call Trig_AIML_BM_AttackDK(bm, enemyP)
        else
            if idx == 0 then
                call IssuePointOrder(bm, "smart", udg_bm_RetreatX1, udg_bm_RetreatY1)
            else
                call IssuePointOrder(bm, "smart", udg_bm_RetreatX2, udg_bm_RetreatY2)
            endif
        endif
        set bm = null
        return
    endif

    // ── HUNT state ──────────────────────────────────────────────────
    if state == 2 then
        // EVADE优先：被集火则中断HUNT
        if drop >= maxHp * 0.15 then
            call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] HUNT interrupted by EVADE! drop=" + I2S(R2I(drop)) + "|r")
            if Trig_AIML_BM_TryCast(bm) then
                set enemyHero = Trig_AIML_BM_FindEnemyHero(enemyP)
                call Trig_AIML_BM_UpdateRetreat(bm, enemyHero, idx)
                if idx == 0 then
                    set udg_bm_State1 = 1
                    set udg_bm_SafeTicks1 = 0
                    set udg_bm_WaitTick1 = 0
                    set udg_bm_HuntTarget1 = null
                else
                    set udg_bm_State2 = 1
                    set udg_bm_SafeTicks2 = 0
                    set udg_bm_WaitTick2 = 0
                    set udg_bm_HuntTarget2 = null
                endif
                set enemyHero = null
            else
                if idx == 0 then
                    set udg_bm_State1 = 0
                    set udg_bm_SafeTicks1 = -10
                    set udg_bm_HuntTarget1 = null
                else
                    set udg_bm_State2 = 0
                    set udg_bm_SafeTicks2 = -10
                    set udg_bm_HuntTarget2 = null
                endif
                call Trig_AIML_BM_AttackDK(bm, enemyP)
            endif
            set bm = null
            return
        endif
        // 目标失效检测：死亡或超出2000码
        if huntTarget == null or IsUnitDeadBJ(huntTarget) then
            call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] HUNT target dead -> NORMAL|r")
            if idx == 0 then
                set udg_bm_State1 = 0
                set udg_bm_SafeTicks1 = 0
                set udg_bm_HuntTarget1 = null
            else
                set udg_bm_State2 = 0
                set udg_bm_SafeTicks2 = 0
                set udg_bm_HuntTarget2 = null
            endif
            set bm = null
            return
        endif
        set dx = GetUnitX(huntTarget) - GetUnitX(bm)
        set dy = GetUnitY(huntTarget) - GetUnitY(bm)
        if dx * dx + dy * dy > 4000000.0 then
            call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] HUNT target out of range -> NORMAL|r")
            if idx == 0 then
                set udg_bm_State1 = 0
                set udg_bm_SafeTicks1 = 0
                set udg_bm_HuntTarget1 = null
            else
                set udg_bm_State2 = 0
                set udg_bm_SafeTicks2 = 0
                set udg_bm_HuntTarget2 = null
            endif
            set bm = null
            return
        endif
        // 疾风步buff消失 -> 解隐身，发起攻击
        if GetUnitAbilityLevel(bm, 'Boro') == 0 then
            call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] HUNT windwalk expired -> ATTACK DK|r")
            call Trig_AIML_BM_AttackDK(bm, enemyP)
            if idx == 0 then
                set udg_bm_State1 = 0
                set udg_bm_SafeTicks1 = -10
                set udg_bm_HuntTarget1 = null
            else
                set udg_bm_State2 = 0
                set udg_bm_SafeTicks2 = -10
                set udg_bm_HuntTarget2 = null
            endif
            set bm = null
            return
        endif
        // 疾风步仍在，持续靠近目标
        call IssuePointOrder(bm, "smart", GetUnitX(huntTarget), GetUnitY(huntTarget))
        set bm = null
        return
    endif

    // ── NORMAL冷却期（safeTicks < 0）──────────────────────────────
    if safeTicks < 0 then
        set safeTicks = safeTicks + 1
        if idx == 0 then
            set udg_bm_SafeTicks1 = safeTicks
        else
            set udg_bm_SafeTicks2 = safeTicks
        endif
        // 冷却期内HUNT检测仍有效
        set huntTarget = Trig_AIML_BM_FindHuntTarget(bm, enemyP)
        if huntTarget != null then
            call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] HUNT(cd)! target=" + GetUnitName(huntTarget) + " hp=" + I2S(R2I(GetUnitState(huntTarget, UNIT_STATE_LIFE))) + "|r")
            if Trig_AIML_BM_TryCast(bm) then
                // windwalk成功 -> 进HUNT状态，靠近目标
                call IssuePointOrder(bm, "smart", GetUnitX(huntTarget), GetUnitY(huntTarget))
                if idx == 0 then
                    set udg_bm_State1 = 2
                    set udg_bm_SafeTicks1 = 0
                    set udg_bm_HuntTarget1 = huntTarget
                else
                    set udg_bm_State2 = 2
                    set udg_bm_SafeTicks2 = 0
                    set udg_bm_HuntTarget2 = huntTarget
                endif
            else
                // windwalk CD/没蓝 -> 不进HUNT，等CD
                call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] HUNT(cd) WW not ready, wait CD|r")
            endif
            set huntTarget = null
        endif
        // 母调度接管，不发AttackNearest
        set bm = null
        return
    endif

    // ── NORMAL 主判定（safeTicks >= 0）──────────────────────────────

    // ① EVADE: 被集火（优先级最高）
    if drop >= maxHp * 0.15 then
        call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] EVADE! hp=" + I2S(R2I(curHp)) + "/" + I2S(R2I(maxHp)) + " drop=" + I2S(R2I(drop)) + "|r")
        if Trig_AIML_BM_TryCast(bm) then
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
            call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] EVADE WW fail -> ATTACK DK|r")
            call Trig_AIML_BM_AttackDK(bm, enemyP)
            if idx == 0 then
                set udg_bm_SafeTicks1 = -10
            else
                set udg_bm_SafeTicks2 = -10
            endif
        endif
        set bm = null
        return
    endif

    // ② HUNT: 主动猎杀残血英雄
    set huntTarget = Trig_AIML_BM_FindHuntTarget(bm, enemyP)
    if huntTarget != null then
        call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] HUNT! target=" + GetUnitName(huntTarget) + " hp=" + I2S(R2I(GetUnitState(huntTarget, UNIT_STATE_LIFE))) + "|r")
        if Trig_AIML_BM_TryCast(bm) then
            // windwalk成功 -> 进HUNT状态，靠近目标
            call IssuePointOrder(bm, "smart", GetUnitX(huntTarget), GetUnitY(huntTarget))
            if idx == 0 then
                set udg_bm_State1 = 2
                set udg_bm_SafeTicks1 = 0
                set udg_bm_HuntTarget1 = huntTarget
            else
                set udg_bm_State2 = 2
                set udg_bm_SafeTicks2 = 0
                set udg_bm_HuntTarget2 = huntTarget
            endif
        else
            // windwalk CD/没蓝 -> 不进HUNT，等CD
            call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] HUNT WW not ready, wait CD|r")
        endif
        set huntTarget = null
    endif

    set bm = null
endfunction

function Trig_AIML_BM_Tick takes nothing returns nothing
    local player aiP
    local player enemyP
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
        print("[BM] WARNING: BM skill learning pattern not found, skip")
        return j_text
    j_text = j_text.replace(old_bm, new_bm)
    print("[BM] patched BM skill learning: wk>cr>ww>cr>ww>cr>ww (no mirror image)")
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

    if "function Trig_AIML_BM_Tick" in src:
        print("[BM] already injected, skipping")
        return

    # 1) globals
    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' found")
    idx = src.find(eg)
    src = src[:idx] + BM_GLOBALS.replace("\n", nl) + nl + src[idx:]
    print("[BM] inserted globals")

    # 2) functions before SH_Tick
    marker = "function Trig_AIML_SH_Tick takes nothing returns nothing"
    idx_marker = src.find(marker)
    if idx_marker == -1:
        raise SystemExit("ERROR: cannot find Trig_AIML_SH_Tick — inject_hero_magic.py must run first")
    src = src[:idx_marker] + BM_FUNCTIONS.replace("\n", nl) + nl + src[idx_marker:]
    print("[BM] inserted functions")

    # 3) hook into SH_Tick
    sh_start = src.find("function Trig_AIML_SH_Tick takes nothing returns nothing")
    sh_end = src.find("endfunction", sh_start + 10)
    if sh_end == -1:
        raise SystemExit("ERROR: cannot find SH_Tick endfunction")
    src = src[:sh_end] + f"    call Trig_AIML_BM_Tick(){nl}" + src[sh_end:]
    print("[BM] hooked BM_Tick into SH_Tick")

    # 4) variable reset
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
            f"    set udg_bm_HuntTarget1 = null{nl}"
            f"    set udg_bm_HuntTarget2 = null{nl}"
        )
        src = src[:eol + len(nl)] + reset_code + src[eol + len(nl):]
        print("[BM] added state reset to Variable Reset block")
    else:
        print("[BM] WARN: Variable Reset block not found, skipping reset injection")

    # 5) skill learn
    src = patch_bm_skill_learn(src)

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[BM] Blademaster AI (EVADE+HUNT state=2) injected into {path}")


if __name__ == "__main__":
    main()
