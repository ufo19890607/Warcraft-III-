#!/usr/bin/env python3
"""
inject_ai_blademaster.py — Blademaster (剑圣) EVADE + HUNT + DASH

状态: 0=NORMAL  1=WAIT(撤退)  2=DASH(突进攻击)  3=STRIKE(持续输出)

V41 fixes: EVADE 0.5s window + 5s cooldown, STRIKE exits at HP<25%.
核心: 所有攻击都先靠近目标(<100码)再取消buff攻击，解决隐身attack失效问题。
攻击目标 = 敌方血量最少的英雄(FindLowestHpHero)。

NORMAL (state=0, safeTicks>=0):
  ① EVADE: drop>=maxHp*15%
     TryCast成功 -> 撤退600码 -> WAIT
     TryCast失败 -> attack 血最少英雄 + safeTicks=-10
  ② HUNT: 残血英雄(<2000码, HP<300)存在
     TryCast成功 -> DASH -> move靠近
     TryCast失败 -> safeTicks=-10 (母调度接管)

NORMAL冷却 (safeTicks<0): safeTicks++, 母调度接管

WAIT (state=1): 撤退
  前3tick强制撤退; 5 safe ticks(drop<=100) -> 撤退结束:
     Boro在 -> DASH; Boro无 -> attack血最少英雄(平A) + safeTicks=-10

DASH (state=2): 专心突进(不检测EVADE)
  target死/无 -> NORMAL safeTicks=0
  距target<100 -> UnitRemoveBuffs -> attack -> NORMAL safeTicks=-10
  距target>=100 -> move靠近

挂在 HeroMagic 0.1s timer (SH_Tick endfunction)。
"""

import sys

BM_GLOBALS = """
    // [BM] Blademaster EVADE+HUNT+DASH globals
    real    udg_bm_PrevHp1    = 0.0
    real array udg_bm_HpHistory1  // 5-tick HP ring buffer for 0.5s EVADE window
    integer udg_bm_HpIdx1     = 0  // ring buffer index
    integer udg_bm_State1     = 0
    integer udg_bm_SafeTicks1 = 0
    integer udg_bm_WaitTick1  = 0
    real    udg_bm_RetreatX1  = 0.0
    real    udg_bm_RetreatY1  = 0.0
    unit    udg_bm_Target1    = null
    integer udg_bm_HuntCooldown1 = 0    // HUNT冷却计时(tick数,0=可触发)
    integer udg_bm_EvadeCooldown1 = 0   // EVADE冷却(tick数,0=可触发)
    integer udg_bm_ExecuteTimer1 = 0   // [V48] EXECUTE打印节流(tick)
    unit    udg_bm_ExecuteTarget1 = null
    integer udg_bm_AttackPrintCd1 = 0  // [V51] forced attack print cooldown
   // [V50] EXECUTE lock target (persists until target dies)
"""

BM_FUNCTIONS = """
// ================================================================
// [BM] Blademaster AI  state=0:NORMAL 1:WAIT 2:DASH
// ================================================================

function Trig_AIML_BM_IsObla takes nothing returns boolean
    return GetUnitTypeId(GetFilterUnit()) == 'Obla' and not IsUnitDeadBJ(GetFilterUnit())
endfunction

function Trig_AIML_BM_FindBM takes player p returns unit
    local group g = CreateGroup()
    local unit u
    call GroupEnumUnitsOfPlayer(g, p, Condition(function Trig_AIML_BM_IsObla))
    set u = FirstOfGroup(g)
    call DestroyGroup(g)
    set g = null
    return u
endfunction

// 找敌方血量最少的英雄
function Trig_AIML_BM_FindLowestHpHero takes player enemyP returns unit
    local group g = CreateGroup()
    local unit u
    local unit best = null
    local real bestHp = 999999.0
    local real hp
    call GroupEnumUnitsOfPlayer(g, enemyP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitDeadBJ(u) and GetUnitAbilityLevel(u, 'Bvul') == 0 then
            set hp = GetUnitState(u, UNIT_STATE_LIFE)
            if hp < bestHp then
                set bestHp = hp
                set best = u
            endif
        endif
        call GroupRemoveUnit(g, u)
    endloop
    call DestroyGroup(g)
    set g = null
    return best
endfunction

// 找最近的敌方单位（非建筑），用于DASH目标失效时兜底
function Trig_AIML_BM_FindNearestEnemy takes unit bm, player enemyP returns unit
    local group g = CreateGroup()
    local unit u
    local unit best = null
    local real bestD = 999999999.0
    local real bx = GetUnitX(bm)
    local real by = GetUnitY(bm)
    local real dx
    local real dy
    local real d
    call GroupEnumUnitsOfPlayer(g, enemyP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        if not IsUnitDeadBJ(u) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
            set dx = GetUnitX(u) - bx
            set dy = GetUnitY(u) - by
            set d = dx * dx + dy * dy
            if d < bestD then
                set bestD = d
                set best = u
            endif
        endif
        call GroupRemoveUnit(g, u)
    endloop
    call DestroyGroup(g)
    set g = null
    return best
endfunction


// [V51c] Find nearest enemy within given range (for NORMAL fallback: no target selection, just hit whats next to BM)
function Trig_AIML_BM_FindNearestEnemyInRange takes unit bm, player enemyP, real range returns unit
    local group g = CreateGroup()
    local unit u
    local unit best = null
    local real bestD = range * range
    local real bx = GetUnitX(bm)
    local real by = GetUnitY(bm)
    local real dx
    local real dy
    local real d
    call GroupEnumUnitsInRange(g, bx, by, range, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        if not IsUnitDeadBJ(u) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) and GetUnitAbilityLevel(u, 'Abur') == 0 and GetOwningPlayer(u) == enemyP then
            set dx = GetUnitX(u) - bx
            set dy = GetUnitY(u) - by
            set d = dx * dx + dy * dy
            if d < bestD then
                set bestD = d
                set best = u
            endif
        endif
        call GroupRemoveUnit(g, u)
    endloop
    call DestroyGroup(g)
    set g = null
    return best
endfunction

// HUNT目标选择（按优先级）:
//   ① 残血英雄(HP<300, 2000码内)
//   ② 毁灭者'ubsp'  ③ 黑曜石雕像'uobs'  ④ 女妖'uban'
//   ⑤ 蜘蛛'ucry'   ⑥ 食尸鬼'ugho'      (②~⑥: 800码内)
// 返回目标unit，无目标返回null
function Trig_AIML_BM_FindHuntTarget takes unit bm, player enemyP returns unit
    local group g = CreateGroup()
    local unit u
    local real bx = GetUnitX(bm)
    local real by = GetUnitY(bm)
    local real dx
    local real dy
    local real d2
    local unit heroTarget = null
    local real heroHp = 999999.0
    local unit priTarget_2 = null  // 毁灭者 (Destroyer)
    local unit priTarget_3 = null  // 黑曜石雕像 (Obsidian Statue)
    local unit priTarget_4 = null  // 女妖 (Banshee)
    local unit priTarget_5 = null  // 穴居恶魔/蜘蛛 (Crypt Fiend)
    local unit priTarget_6 = null  // 食尸鬼 (Ghoul)
    local integer uid
    local real hp
    call GroupEnumUnitsOfPlayer(g, enemyP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        if not IsUnitDeadBJ(u) and GetUnitAbilityLevel(u, 'Bvul') == 0 then
            set dx = GetUnitX(u) - bx
            set dy = GetUnitY(u) - by
            set d2 = dx * dx + dy * dy
            // ① 残血英雄: 2000码内 HP<300
            if IsUnitType(u, UNIT_TYPE_HERO) and d2 < 4000000.0 then
                set hp = GetUnitState(u, UNIT_STATE_LIFE)
                if hp < 300.0 and hp < heroHp then
                    set heroHp = hp
                    set heroTarget = u
                endif
            endif
            //   ②~6 普通单位: 毁灭者(ubsp)  黑曜石雕像(uobs)  女妖(uban)  穴居恶魔/蜘蛛(ucry)  食尸鬼(ugho)    (②~6: 800码内)
            if d2 < 640000.0 then
                set uid = GetUnitTypeId(u)
                if uid == 'ubsp' and priTarget_2 == null then
                    set priTarget_2 = u
                elseif uid == 'uobs' and priTarget_3 == null then
                    set priTarget_3 = u
                elseif uid == 'uban' and priTarget_4 == null then
                    set priTarget_4 = u
                elseif uid == 'ucry' and priTarget_5 == null then
                    set priTarget_5 = u
                elseif uid == 'ugho' and priTarget_6 == null then
                    set priTarget_6 = u
                endif
            endif
        endif
        call GroupRemoveUnit(g, u)
    endloop
    call DestroyGroup(g)
    set g = null
    // 按优先级返回 (from aiml_target_priority.py)
    if heroTarget != null then
        return heroTarget
    endif
    if priTarget_2 != null then
        return priTarget_2
    endif
    if priTarget_3 != null then
        return priTarget_3
    endif
    if priTarget_4 != null then
        return priTarget_4
    endif
    if priTarget_5 != null then
        return priTarget_5
    endif
    if priTarget_6 != null then
        return priTarget_6
    endif
    return null
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

// [V52] Find friendly Shadow Hunter (Oshd) for retreat target
function Trig_AIML_BM_FindShadowHunter takes player myP returns unit
    local group g = CreateGroup()
    local unit u
    local unit best = null
    local real bestD = 999999.0
    local real bx = GetUnitX(GetEnumUnit())
    local real by = GetUnitY(GetEnumUnit())
    call GroupEnumUnitsOfPlayer(g, myP, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitDeadBJ(u) and GetUnitTypeId(u) == 'Oshd' then
            set best = u
            call GroupClear(g)
            exitwhen true
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    set u = null
    return best
endfunction

function Trig_AIML_BM_UpdateRetreat takes unit bm, unit enemyHero returns nothing
    local real bx = GetUnitX(bm)
    local real by = GetUnitY(bm)
    local real vx
    local real vy
    local real len
    local real rx
    local real ry
    local unit sh = Trig_AIML_BM_FindShadowHunter(GetOwningPlayer(bm))
    if sh != null then
        // [V52] retreat towards Shadow Hunter for healing
        set vx = GetUnitX(sh) - bx
        set vy = GetUnitY(sh) - by
        set len = SquareRoot(vx * vx + vy * vy)
        if len < 1.0 then
            set len = 1.0
        endif
        // move towards SH (not all the way, stop 200yd before to avoid clumping)
        if len > 200.0 then
            set rx = bx + vx / len * (len - 200.0)
            set ry = by + vy / len * (len - 200.0)
        else
            // already close to SH, stay
            set rx = bx
            set ry = by
        endif
        set udg_bm_RetreatX1 = rx
        set udg_bm_RetreatY1 = ry
        call IssuePointOrder(bm, "smart", rx, ry)
    elseif enemyHero != null then
        // no SH found, fallback: retreat away from enemy
        set vx = bx - GetUnitX(enemyHero)
        set vy = by - GetUnitY(enemyHero)
        set len = SquareRoot(vx * vx + vy * vy)
        if len < 1.0 then
            set len = 1.0
        endif
        set rx = bx + vx / len * 600.0
        set ry = by + vy / len * 600.0
        set udg_bm_RetreatX1 = rx
        set udg_bm_RetreatY1 = ry
        call IssuePointOrder(bm, "smart", rx, ry)
    else
        set udg_bm_RetreatX1 = bx
        set udg_bm_RetreatY1 = by
    endif
    set sh = null
endfunction

// [V52] Combat_AI filter: exclude BM from parent dispatch
// Patched into Trig_Computer1Combat_AI_Func001001002 and Func002001002
function Trig_AIML_BM_IsNotBlademaster takes nothing returns boolean
    return GetUnitTypeId(GetFilterUnit()) != 'Obla'
endfunction

function Trig_AIML_BM_TickForPlayer takes player myP, player enemyP returns nothing
    local unit bm
    local unit enemyHero
    local unit target
    local real curHp
    local real maxHp
    local real prevHp
    local real drop
    local real dx
    local real dy
    local real dist
    local integer state
    local integer safeTicks
    local integer waitTick
    local real hp
    local boolean ww
    set bm = Trig_AIML_BM_FindBM(myP)
    if bm == null or IsUnitDeadBJ(bm) then
        set bm = null
        return
    endif
    set curHp = GetUnitState(bm, UNIT_STATE_LIFE)
    set maxHp = GetUnitState(bm, UNIT_STATE_MAX_LIFE)

    set state = udg_bm_State1
    set safeTicks = udg_bm_SafeTicks1
    set waitTick = udg_bm_WaitTick1
    // [V41] 0.5s EVADE window: use 5-tick HP ring buffer
    set udg_bm_HpHistory1[udg_bm_HpIdx1] = curHp
    set prevHp = udg_bm_HpHistory1[ModuloInteger(udg_bm_HpIdx1 + 1, 5)]
    set udg_bm_HpIdx1 = ModuloInteger(udg_bm_HpIdx1 + 1, 5)
    if prevHp <= 0.0 then
        set prevHp = curHp
    endif
    set drop = prevHp - curHp
    if drop < 0.0 then
        set drop = 0.0
    endif
    set udg_bm_PrevHp1 = curHp

    // ── DASH state (专心突进，不检测EVADE) ──
    if state == 2 then
        set target = udg_bm_Target1
        // 目标失效（死亡）-> 攻击最近敌方单位，避免原地乱转
        if target == null or IsUnitDeadBJ(target) then
            set target = Trig_AIML_BM_FindNearestEnemy(bm, enemyP)
            if target == null then
                if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] DASH target lost, no enemy -> NORMAL|r")
                endif
                set udg_bm_State1 = 0
                set udg_bm_SafeTicks1 = 0
                set udg_bm_Target1 = null
                set bm = null
                return
            endif
            // 靠近最近敌方单位 -> 破隐 -> 攻击
            set dx = GetUnitX(target) - GetUnitX(bm)
            set dy = GetUnitY(target) - GetUnitY(bm)
            set dist = SquareRoot(dx * dx + dy * dy)
            if dist < 100.0 then
                call UnitRemoveBuffs(bm, true, false)
                call IssueTargetOrder(bm, "attack", target)
                if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] DASH target lost -> STRIKE nearest " + GetUnitName(target) + " (d=" + I2S(R2I(dist)) + ")|r")
                endif
                set udg_bm_State1 = 0
                set udg_bm_SafeTicks1 = -10
                set udg_bm_Target1 = null
            else
                call IssuePointOrder(bm, "move", GetUnitX(target), GetUnitY(target))
            endif
            set bm = null
            return
        endif
        set dx = GetUnitX(target) - GetUnitX(bm)
        set dy = GetUnitY(target) - GetUnitY(bm)
        set dist = SquareRoot(dx * dx + dy * dy)
        if dist < 100.0 then
            call UnitRemoveBuffs(bm, true, false)
            call IssueTargetOrder(bm, "attack", target)
            if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] DASH reached (d=" + I2S(R2I(dist)) + ") -> STRIKE " + GetUnitName(target) + " hp=" + I2S(R2I(GetUnitState(target, UNIT_STATE_LIFE))) + "|r")
            endif
            // 进入持续输出状态，咬住目标打
            set udg_bm_State1 = 3
            set udg_bm_SafeTicks1 = 0
            // udg_bm_Target1 保留
        else
            call IssuePointOrder(bm, "move", GetUnitX(target), GetUnitY(target))
        endif
        set bm = null
        return
    endif

    // ── STRIKE state (持续输出) ──
    if state == 3 then
        set target = udg_bm_Target1
        // [V41] 退出条件1：目标死亡
        if target == null or IsUnitDeadBJ(target) then
            if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] STRIKE done (target dead) -> NORMAL|r")
            endif
            set udg_bm_State1 = 0
            set udg_bm_SafeTicks1 = -10
            set udg_bm_Target1 = null
            set udg_bm_ExecuteTarget1 = null
    set udg_bm_AttackPrintCd1 = 0
            set bm = null
            return
        endif
        // [V52] exit 1.6: target burrowed (Abur) -> release to NORMAL, find new target
        if GetUnitAbilityLevel(target, 'Abur') > 0 then
            if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] STRIKE done (target submerged) -> NORMAL|r")
            endif
            set udg_bm_State1 = 0
            set udg_bm_SafeTicks1 = -10
            set udg_bm_Target1 = null
            set udg_bm_ExecuteTarget1 = null
            set bm = null
            return
        endif
        // [V50] exit 1.5: target invulnerable -> release lock, back to NORMAL
        if GetUnitAbilityLevel(target, 'Bvul') > 0 then
            if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] STRIKE release (target invul) -> NORMAL|r")
            endif
            set udg_bm_State1 = 0
            set udg_bm_SafeTicks1 = -10
            set udg_bm_Target1 = null
            set udg_bm_ExecuteTarget1 = null
            set bm = null
            return
        endif
        // [V41] 退出条件2：HP < 25% -> 撤退保命
        // [V50] EXECUTE lock exception: do not retreat, keep attacking until target dies
        if curHp < maxHp * 0.25 then
            if udg_bm_ExecuteTarget1 == target then
                if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] STRIKE hold (EXECUTE lock, hp=" + I2S(R2I(curHp)) + " < 25%) -> continue|r")
                endif
            else
                if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "|cffff4444[BM] STRIKE abort (hp=" + I2S(R2I(curHp)) + " < 25%) -> WAIT|r")
                endif
                set enemyHero = Trig_AIML_BM_FindEnemyHero(enemyP)
                call Trig_AIML_BM_UpdateRetreat(bm, enemyHero)
                set udg_bm_State1 = 1
                set udg_bm_SafeTicks1 = 0
                set udg_bm_WaitTick1 = 0
                set udg_bm_Target1 = null
                set enemyHero = null
                set bm = null
                return
            endif
        endif
        // [V52] only re-issue attack if target changed (avoid resetting attack animation)
        if udg_bm_Target1 != target then
            call IssueTargetOrder(bm, "attack", target)
            set udg_bm_Target1 = target
        endif
        // [V51] forced print: STRIKE target (throttled 1s)
        set udg_bm_AttackPrintCd1 = udg_bm_AttackPrintCd1 + 1
        if udg_bm_AttackPrintCd1 >= 10 then
            call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] STRIKE " + GetUnitName(target) + " hp=" + I2S(R2I(GetUnitState(target, UNIT_STATE_LIFE))) + "|r")
            set udg_bm_AttackPrintCd1 = 0
        endif
        set bm = null
        return
    endif

    // ── WAIT state (撤退) ──
    if state == 1 then
        set waitTick = waitTick + 1
        set udg_bm_WaitTick1 = waitTick
        if waitTick == 1 then
            if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "|cff88ccff[BM] WAIT start hp=" + I2S(R2I(curHp)) + "/" + I2S(R2I(maxHp)) + "|r")
            endif
        endif
        if waitTick <= 10 then
            call IssuePointOrder(bm, "smart", udg_bm_RetreatX1, udg_bm_RetreatY1)
            set bm = null
            return
        endif
        if drop <= 100.0 then
            set safeTicks = safeTicks + 1
        else
            set safeTicks = 0
        endif
        set udg_bm_SafeTicks1 = safeTicks
        // [V52] EXECUTE bypass: if BM has windwalk and enemy hero HP<150 (not invul/burrowed), break retreat
        if GetUnitAbilityLevel(bm, 'Boro') > 0 then
            set target = Trig_AIML_BM_FindLowestHpHero(enemyP)
            if target != null then
                set hp = GetUnitState(target, UNIT_STATE_LIFE)
                if hp < 150.0 and GetUnitAbilityLevel(target, 'Bvul') == 0 and GetUnitAbilityLevel(target, 'Abur') == 0 then
                    if udg_aiml_DebugMode then
                    call DisplayTextToForce(GetPlayersAll(), "|cffff0000[BM] WAIT->EXECUTE bypass! " + GetUnitName(target) + " hp=" + I2S(R2I(hp)) + "|r")
                    endif
                    set udg_bm_State1 = 2
                    set udg_bm_SafeTicks1 = 0
                    set udg_bm_Target1 = target
                    set udg_bm_ExecuteTarget1 = target
                    call IssuePointOrder(bm, "move", GetUnitX(target), GetUnitY(target))
                    set target = null
                    set bm = null
                    return
                endif
                set target = null
            endif
        endif
        // [V52] if HP still < 300, keep retreating towards SH (don't return yet)
        if safeTicks >= 10 and curHp <= 300.0 then
            // keep moving towards SH position (RetreatX/Y already set towards SH)
            call IssuePointOrder(bm, "smart", udg_bm_RetreatX1, udg_bm_RetreatY1)
        elseif safeTicks >= 10 and curHp > 300.0 then
            set target = Trig_AIML_BM_FindHuntTarget(bm, enemyP)
            if GetUnitAbilityLevel(bm, 'Boro') > 0 and target != null then
                if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] WAIT->DASH (Boro on) target=" + GetUnitName(target) + "|r")
                endif
                set udg_bm_State1 = 2
                set udg_bm_SafeTicks1 = 0
                set udg_bm_Target1 = target
                call IssuePointOrder(bm, "move", GetUnitX(target), GetUnitY(target))
            else
                if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] WAIT->ATTACK (no Boro)|r")
                endif
                if target != null then
                    call IssueTargetOrder(bm, "attack", target)
                endif
                set udg_bm_State1 = 0
                set udg_bm_SafeTicks1 = -10
            endif
        else
            call IssuePointOrder(bm, "smart", udg_bm_RetreatX1, udg_bm_RetreatY1)
        endif
        set bm = null
        return
    endif

    // ── NORMAL冷却 (safeTicks<0) ──
    // [V52] also attack nearest enemy during cooldown (don't let parent dispatch take over)
    if safeTicks < 0 then
        set safeTicks = safeTicks + 1
        set udg_bm_SafeTicks1 = safeTicks
        set target = Trig_AIML_BM_FindNearestEnemyInRange(bm, enemyP, 150.0)
        if target != null and GetUnitAbilityLevel(target, 'Abur') == 0 then
            if udg_bm_Target1 != target then
                set udg_bm_Target1 = target
                call IssueTargetOrder(bm, "attack", target)
            endif
        endif
        set bm = null
        return
    endif

    // ── NORMAL (safeTicks>=0) ──

    // [V52] if BM is silenced (BNsi), skip EXECUTE/HUNT (cannot cast windwalk)
    if GetUnitAbilityLevel(bm, 'BNsi') > 0 then
        // silenced: NORMAL fallback only (150yd nearest enemy)
        set target = Trig_AIML_BM_FindNearestEnemyInRange(bm, enemyP, 150.0)
        if target != null then
            set udg_bm_Target1 = target
            call IssueTargetOrder(bm, "attack", target)
        endif
        set bm = null
        return
    endif

    // [V48/V50] ⓪ EXECUTE: enemy hero HP<150 -> burst kill (ignore cooldown/threat, lock target)
    // [V50] lock persists while target HP < 350 (heal < 200); release if HP >= 350 -> fall back to HUNT
    // [V50] release if target invulnerable (Avul buff)
    if udg_bm_ExecuteTarget1 != null and not IsUnitDeadBJ(udg_bm_ExecuteTarget1) then
        set target = udg_bm_ExecuteTarget1
        // [V50] release lock if target became invulnerable
        if GetUnitAbilityLevel(target, 'Bvul') > 0 then
            if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] EXECUTE release (target invul) -> HUNT|r")
            endif
            set udg_bm_ExecuteTarget1 = null
            set udg_bm_Target1 = null
            set target = null  // fall through to EVADE/HUNT below
        endif
    else
        set target = Trig_AIML_BM_FindLowestHpHero(enemyP)
        if target != null then
            set udg_bm_ExecuteTarget1 = null  // found target but hp may be >=150, checked below
        endif
    endif
    if target != null then
        set hp = GetUnitState(target, UNIT_STATE_LIFE)
        // [V50] skip EXECUTE if target invulnerable (no point attacking)
        // fall through to EVADE/HUNT (engine drops invisible targets)
        if GetUnitAbilityLevel(target, 'Bvul') > 0 then
            set target = null  // fall through to EVADE/HUNT below
        endif
        if (udg_bm_ExecuteTarget1 == target and hp < 350.0) or hp < 150.0 then
            // [V50] release lock if target healed above 350 (heal > 200)
            if udg_bm_ExecuteTarget1 == target and hp >= 350.0 then
                if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] EXECUTE release (hp=" + I2S(R2I(hp)) + " >= 350) -> HUNT|r")
                endif
                set udg_bm_ExecuteTarget1 = null
                set udg_bm_Target1 = null
                set target = null  // fall through to EVADE/HUNT below
            endif
            set udg_bm_ExecuteTimer1 = udg_bm_ExecuteTimer1 + 1
            if udg_aiml_DebugMode and udg_bm_ExecuteTimer1 >= 10 then
                call DisplayTextToForce(GetPlayersAll(), "|cffff0000[BM] EXECUTE! " + GetUnitName(target) + " hp=" + I2S(R2I(hp)) + "|r")
                set udg_bm_ExecuteTimer1 = 0
            endif
            set dx = GetUnitX(target) - GetUnitX(bm)
            set dy = GetUnitY(target) - GetUnitY(bm)
            set dist = SquareRoot(dx * dx + dy * dy)
            if dist < 100.0 then
                call IssueTargetOrder(bm, "attack", target)
                set udg_bm_State1 = 3
                set udg_bm_SafeTicks1 = 0
                set udg_bm_Target1 = target
                set udg_bm_ExecuteTarget1 = target  // [V50] lock target
            else
                // 斩杀无视冷却，强制释放疾风步
                set ww = IssueImmediateOrder(bm, "windwalk")
                if ww then
                    if udg_aiml_DebugMode then
                    call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[BM] EXECUTE windwalk -> DASH|r")
                    endif
                    set udg_bm_State1 = 2
                    set udg_bm_SafeTicks1 = 0
                    set udg_bm_Target1 = target
                    set udg_bm_ExecuteTarget1 = target  // [V50] lock target
                else
                    // windwalk CD -> move towards target, go NORMAL cooldown (don't enter DASH, let EVADE/HUNT run next tick)
                    call IssuePointOrder(bm, "move", GetUnitX(target), GetUnitY(target))
                    set udg_bm_EvadeCooldown1 = 0
                    set udg_bm_ExecuteTarget1 = target  // [V50] lock target
                    set udg_bm_SafeTicks1 = -1
                endif
            endif
            set bm = null
            return
        endif
    endif

    // ① EVADE: 被集火 (V41: 0.5s window + cooldown)
    if udg_bm_EvadeCooldown1 > 0 then
        set udg_bm_EvadeCooldown1 = udg_bm_EvadeCooldown1 - 1
    elseif drop >= maxHp * 0.15 then
        if udg_aiml_DebugMode then
        call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] EVADE! hp=" + I2S(R2I(curHp)) + "/" + I2S(R2I(maxHp)) + " drop=" + I2S(R2I(drop)) + "|r")
        endif
        set ww = IssueImmediateOrder(bm, "windwalk")
        if ww then
            set udg_bm_EvadeCooldown1 = 50  // [V41] 5s EVADE cooldown after using windwalk
            set udg_bm_Target1 = null  // [V49] clear target on retreat so Salvo stops following
            set enemyHero = Trig_AIML_BM_FindEnemyHero(enemyP)
            call Trig_AIML_BM_UpdateRetreat(bm, enemyHero)
            set udg_bm_State1 = 1
            set udg_bm_SafeTicks1 = 0
            set udg_bm_WaitTick1 = 0
            set enemyHero = null
        else
            // 没疾风步 -> 平A血最少英雄
            set target = Trig_AIML_BM_FindLowestHpHero(enemyP)
            if target != null then
                call IssueTargetOrder(bm, "attack", target)
            endif
            set udg_bm_SafeTicks1 = -10
        endif
        set bm = null
        return
    endif

    // ② HUNT: 按优先级找目标（冷却30s=300tick，冷却中跳过枚举）
    if udg_bm_HuntCooldown1 > 0 then
        set udg_bm_HuntCooldown1 = udg_bm_HuntCooldown1 - 1
    else
        set target = Trig_AIML_BM_FindHuntTarget(bm, enemyP)
        if target != null then
            if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] HUNT! target=" + GetUnitName(target) + " hp=" + I2S(R2I(GetUnitState(target, UNIT_STATE_LIFE))) + "|r")
            endif
            set udg_bm_HuntCooldown1 = 100  // 10s cooldown
            // 先判距离：已在100码内则直接进STRIKE平A，节省疾风步CD
            set dx = GetUnitX(target) - GetUnitX(bm)
            set dy = GetUnitY(target) - GetUnitY(bm)
            set dist = SquareRoot(dx * dx + dy * dy)
            if dist < 100.0 then
                if udg_aiml_DebugMode then
                call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] HUNT close (d=" + I2S(R2I(dist)) + ") -> STRIKE directly|r")
                endif
                call IssueTargetOrder(bm, "attack", target)
                set udg_bm_State1 = 3
                set udg_bm_SafeTicks1 = 0
                set udg_bm_Target1 = target
            else
                // 距离>=100 -> 释放疾风步突进
                set ww = IssueImmediateOrder(bm, "windwalk")
                if ww then
                    if udg_aiml_DebugMode then
                    call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[BM] windwalk OK -> DASH|r")
                    endif
                    set udg_bm_EvadeCooldown1 = 50  // [V41] 5s EVADE cooldown after HUNT windwalk
                    set udg_bm_State1 = 2
                    set udg_bm_SafeTicks1 = 0
                    set udg_bm_Target1 = target
                    call IssuePointOrder(bm, "move", GetUnitX(target), GetUnitY(target))
                else
                    // 疾风步CD -> 母调度接管1s
                    set udg_bm_SafeTicks1 = -10
                endif
            endif
            set bm = null
            return
        endif
    endif

    // [V51c] NORMAL fallback: attack nearest enemy within 150yd (no target selection)
    //         Only HUNT/EXECUTE pick specific targets. BM just hits whatever is next to it.
    set target = Trig_AIML_BM_FindNearestEnemyInRange(bm, enemyP, 150.0)
    if target != null and GetUnitAbilityLevel(target, 'Abur') == 0 then
        if udg_bm_Target1 != target then
            set udg_bm_Target1 = target
            call IssueTargetOrder(bm, "attack", target)
        endif
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
    call Trig_AIML_BM_TickForPlayer(aiP, enemyP)
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

    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' found")
    idx = src.find(eg)
    src = src[:idx] + BM_GLOBALS.replace("\n", nl) + nl + src[idx:]
    print("[BM] inserted globals")

    marker = "function Trig_AIML_SH_Tick takes nothing returns nothing"
    idx_marker = src.find(marker)
    if idx_marker == -1:
        raise SystemExit("ERROR: cannot find Trig_AIML_SH_Tick — inject_hero_magic.py must run first")
    src = src[:idx_marker] + BM_FUNCTIONS.replace("\n", nl) + nl + src[idx_marker:]
    print("[BM] inserted functions")

    sh_start = src.find("function Trig_AIML_SH_Tick takes nothing returns nothing")
    sh_end = src.find("endfunction", sh_start + 10)
    if sh_end == -1:
        raise SystemExit("ERROR: cannot find SH_Tick endfunction")
    src = src[:sh_end] + f"    call Trig_AIML_BM_Tick(){nl}" + src[sh_end:]
    print("[BM] hooked BM_Tick into SH_Tick")

    reset_marker = "// Variable Reset"
    idx_reset = src.find(reset_marker)
    if idx_reset != -1:
        eol = src.index(nl, idx_reset)
        reset_code = (
            f"    set udg_bm_State1 = 0{nl}"
            f"    set udg_bm_SafeTicks1 = 0{nl}"
            f"    set udg_bm_WaitTick1 = 0{nl}"
            f"    set udg_bm_PrevHp1 = 0.0{nl}"
            f"    set udg_bm_Target1 = null{nl}"
            f"    set udg_bm_ExecuteTimer1 = 0{nl}"
            f"    set udg_bm_ExecuteTarget1 = null{nl}"
            f"    set udg_bm_HuntCooldown1 = 0{nl}"
        )
        src = src[:eol + len(nl)] + reset_code + src[eol + len(nl):]
        print("[BM] added state reset to Variable Reset block")
    else:
        print("[BM] WARN: Variable Reset block not found, skipping reset injection")

    # [V52] Patch Combat_AI filter functions to exclude BM (Obla)
    for filter_func in [
        "Trig_Computer1Combat_AI_Func001001002",
        "Trig_Computer2Combat_AI_Func002001002",
    ]:
        # Replace the return statement to also check for BM
        old_ret = f"function {filter_func} takes nothing returns boolean"
        idx = src.find(old_ret)
        if idx != -1:
            # Find the endfunction after this function
            end_idx = src.find("endfunction", idx + 10)
            if end_idx != -1:
                old_body = src[idx:end_idx + len("endfunction")]
                new_body = (
                    f"function {filter_func} takes nothing returns boolean{nl}"
                    f"    return GetBooleanAnd(GetBooleanAnd((RectContainsUnit(gg_rct_P1BaseArea, GetFilterUnit()) == false), (RectContainsUnit(gg_rct_P2BaseArea, GetFilterUnit()) == false)), GetUnitTypeId(GetFilterUnit()) != 'Obla'){nl}"
                    f"endfunction"
                )
                src = src[:idx] + new_body + src[end_idx + len("endfunction"):]
                print(f"[BM] patched {filter_func} to exclude Blademaster")

    # Disable AntiCheat triggers (clear Actions body)
    for ac_func in [
        "Trig_AntiCheat_Computer1_BM_Actions",
        "Trig_AntiCheat_Computer2_BM_Actions",
    ]:
        marker = f"function {ac_func} takes nothing returns nothing"
        idx = src.find(marker)
        if idx == -1:
            print(f"[BM] WARN: {ac_func} not found, skip")
            continue
        end = src.find("endfunction", idx)
        if end == -1:
            continue
        new_func = marker + f"{nl}    // [BM] disabled - BM AI manages windwalk usage{nl}endfunction"
        src = src[:idx] + new_func + src[end + len("endfunction"):]
        print(f"[BM] disabled {ac_func}")

    src = patch_bm_skill_learn(src)

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[BM] Blademaster AI (EVADE+HUNT+DASH) injected into {path}")


if __name__ == "__main__":
    main()
