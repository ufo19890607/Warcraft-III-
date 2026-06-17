#!/usr/bin/env python3
"""
inject_ai_blademaster.py — Blademaster (剑圣) 最小化测试版

逻辑（无状态机）：
  每0.1s tick:
    1. 找到BM（type='Obla'，AI玩家方）
    2. 若疾风步可用 -> 释放windwalk -> UnitRemoveBuffs解除隐身 -> attack DK
    3. 用冷却变量避免每tick重复释放（释放后等待N tick）

挂在 HeroMagic 0.1s timer (SH_Tick endfunction)。

完全抛弃旧的 EVADE / HUNT / 状态机逻辑。
"""

import sys

BM_GLOBALS = """
    // [BM-MIN] Blademaster minimal test globals
    integer udg_bm_Cooldown1 = 0"""

BM_FUNCTIONS = """
// ================================================================
// [BM-MIN] Blademaster minimal: windwalk -> remove buff -> attack DK
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

function Trig_AIML_BM_FindDK takes player enemyP returns unit
    local group g = CreateGroup()
    local unit u
    local unit dk = null
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
    return dk
endfunction

function Trig_AIML_BM_TickForPlayer takes player myP, player enemyP returns nothing
    local unit bm
    local unit dk
    local boolean ww
    set bm = Trig_AIML_BM_FindBM(myP)
    if bm == null or IsUnitDeadBJ(bm) then
        set bm = null
        return
    endif
    set dk = Trig_AIML_BM_FindDK(enemyP)
    if dk == null then
        call DisplayTextToForce(GetPlayersAll(), "|cffff0000[BM-MIN] no DK found|r")
        set bm = null
        return
    endif
    // 冷却中：等待，期间持续攻击DK
    if udg_bm_Cooldown1 > 0 then
        set udg_bm_Cooldown1 = udg_bm_Cooldown1 - 1
        // 解除隐身 + 攻击DK
        if IsUnitInvisible(bm, enemyP) then
            call UnitRemoveBuffs(bm, true, false)
            call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BM-MIN] invis break|r")
        endif
        call IssueTargetOrder(bm, "attack", dk)
        call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM-MIN] attack DK hp=" + I2S(R2I(GetUnitState(dk, UNIT_STATE_LIFE))) + " cd=" + I2S(udg_bm_Cooldown1) + "|r")
        set bm = null
        set dk = null
        return
    endif
    // 冷却好了：尝试释放疾风步
    set ww = IssueImmediateOrder(bm, "windwalk")
    if ww then
        call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[BM-MIN] windwalk OK -> set cd=30|r")
        set udg_bm_Cooldown1 = 30
    else
        // 没蓝/CD：直接攻击DK
        call DisplayTextToForce(GetPlayersAll(), "|cffffff00[BM-MIN] windwalk fail -> attack DK directly|r")
        call IssueTargetOrder(bm, "attack", dk)
    endif
    set bm = null
    set dk = null
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
        print("[BM-MIN] WARNING: BM skill learning pattern not found, skip")
        return j_text
    j_text = j_text.replace(old_bm, new_bm)
    print("[BM-MIN] patched BM skill learning: wk>cr>ww>cr>ww>cr>ww (no mirror image)")
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
        print("[BM-MIN] already injected, skipping")
        return

    # 1) globals
    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' found")
    idx = src.find(eg)
    src = src[:idx] + BM_GLOBALS.replace("\n", nl) + nl + src[idx:]
    print("[BM-MIN] inserted globals")

    # 2) functions before SH_Tick
    marker = "function Trig_AIML_SH_Tick takes nothing returns nothing"
    idx_marker = src.find(marker)
    if idx_marker == -1:
        raise SystemExit("ERROR: cannot find Trig_AIML_SH_Tick — inject_hero_magic.py must run first")
    src = src[:idx_marker] + BM_FUNCTIONS.replace("\n", nl) + nl + src[idx_marker:]
    print("[BM-MIN] inserted functions")

    # 3) hook into SH_Tick
    sh_start = src.find("function Trig_AIML_SH_Tick takes nothing returns nothing")
    sh_end = src.find("endfunction", sh_start + 10)
    if sh_end == -1:
        raise SystemExit("ERROR: cannot find SH_Tick endfunction")
    src = src[:sh_end] + f"    call Trig_AIML_BM_Tick(){nl}" + src[sh_end:]
    print("[BM-MIN] hooked BM_Tick into SH_Tick")

    # 4) variable reset
    reset_marker = "// Variable Reset"
    idx_reset = src.find(reset_marker)
    if idx_reset != -1:
        eol = src.index(nl, idx_reset)
        reset_code = f"    set udg_bm_Cooldown1 = 0{nl}"
        src = src[:eol + len(nl)] + reset_code + src[eol + len(nl):]
        print("[BM-MIN] added state reset to Variable Reset block")
    else:
        print("[BM-MIN] WARN: Variable Reset block not found, skipping reset injection")

    # 5) skill learn
    src = patch_bm_skill_learn(src)

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[BM-MIN] Blademaster minimal AI injected into {path}")


if __name__ == "__main__":
    main()
