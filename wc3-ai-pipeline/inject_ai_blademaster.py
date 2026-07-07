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
        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitDeadBJ(u) then
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
        if not IsUnitDeadBJ(u) then
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

function Trig_AIML_BM_UpdateRetreat takes unit bm, unit enemyHero returns nothing
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
    set udg_bm_RetreatX1 = rx
    set udg_bm_RetreatY1 = ry
    call IssuePointOrder(bm, "smart", rx, ry)
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
                call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] DASH target lost, no enemy -> NORMAL|r")
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
                call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] DASH target lost -> STRIKE nearest " + GetUnitName(target) + " (d=" + I2S(R2I(dist)) + ")|r")
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
            call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] DASH reached (d=" + I2S(R2I(dist)) + ") -> STRIKE " + GetUnitName(target) + " hp=" + I2S(R2I(GetUnitState(target, UNIT_STATE_LIFE))) + "|r")
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
            call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] STRIKE done (target dead) -> NORMAL|r")
            set udg_bm_State1 = 0
            set udg_bm_SafeTicks1 = -10
            set udg_bm_Target1 = null
            set bm = null
            return
        endif
        // [V41] 退出条件2：HP < 25% -> 撤退保命
        if curHp < maxHp * 0.25 then
            call DisplayTextToForce(GetPlayersAll(), "|cffff4444[BM] STRIKE abort (hp=" + I2S(R2I(curHp)) + " < 25%) -> WAIT|r")
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
        // 每tick重新下attack指令，咬住目标，覆盖母调度
        call IssueTargetOrder(bm, "attack", target)
        set bm = null
        return
    endif

    // ── WAIT state (撤退) ──
    if state == 1 then
        set waitTick = waitTick + 1
        set udg_bm_WaitTick1 = waitTick
        if waitTick == 1 then
            call DisplayTextToForce(GetPlayersAll(), "|cff88ccff[BM] WAIT start hp=" + I2S(R2I(curHp)) + "/" + I2S(R2I(maxHp)) + "|r")
        endif
        if waitTick <= 3 then
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
        if safeTicks >= 5 then
            // 撤退结束 -> 检测疾风步状态
            set target = Trig_AIML_BM_FindHuntTarget(bm, enemyP)
            if GetUnitAbilityLevel(bm, 'Boro') > 0 and target != null then
                // 疾风步还在 -> DASH突进
                call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] WAIT->DASH (Boro on) target=" + GetUnitName(target) + "|r")
                set udg_bm_State1 = 2
                set udg_bm_SafeTicks1 = 0
                set udg_bm_Target1 = target
                call IssuePointOrder(bm, "move", GetUnitX(target), GetUnitY(target))
            else
                // 疾风步没了 -> 平A
                call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] WAIT->ATTACK (no Boro)|r")
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
    if safeTicks < 0 then
        set safeTicks = safeTicks + 1
        set udg_bm_SafeTicks1 = safeTicks
        set bm = null
        return
    endif

    // ── NORMAL (safeTicks>=0) ──

    // ① EVADE: 被集火 (V41: 0.5s window + cooldown)
    if udg_bm_EvadeCooldown1 > 0 then
        set udg_bm_EvadeCooldown1 = udg_bm_EvadeCooldown1 - 1
    elseif drop >= maxHp * 0.15 then
        call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM] EVADE! hp=" + I2S(R2I(curHp)) + "/" + I2S(R2I(maxHp)) + " drop=" + I2S(R2I(drop)) + "|r")
        set ww = IssueImmediateOrder(bm, "windwalk")
        if ww then
            set udg_bm_EvadeCooldown1 = 50  // [V41] 5s EVADE cooldown after using windwalk
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
            call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM] HUNT! target=" + GetUnitName(target) + " hp=" + I2S(R2I(GetUnitState(target, UNIT_STATE_LIFE))) + "|r")
            set udg_bm_HuntCooldown1 = 300  // 重置30s冷却
            // 先判距离：已在100码内则直接进STRIKE平A，节省疾风步CD
            set dx = GetUnitX(target) - GetUnitX(bm)
            set dy = GetUnitY(target) - GetUnitY(bm)
            set dist = SquareRoot(dx * dx + dy * dy)
            if dist < 100.0 then
                call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM] HUNT close (d=" + I2S(R2I(dist)) + ") -> STRIKE directly|r")
                call IssueTargetOrder(bm, "attack", target)
                set udg_bm_State1 = 3
                set udg_bm_SafeTicks1 = 0
                set udg_bm_Target1 = target
            else
                // 距离>=100 -> 释放疾风步突进
                set ww = IssueImmediateOrder(bm, "windwalk")
                if ww then
                    call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[BM] windwalk OK -> DASH|r")
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
            f"    set udg_bm_HuntCooldown1 = 0{nl}"
        )
        src = src[:eol + len(nl)] + reset_code + src[eol + len(nl):]
        print("[BM] added state reset to Variable Reset block")
    else:
        print("[BM] WARN: Variable Reset block not found, skipping reset injection")

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
