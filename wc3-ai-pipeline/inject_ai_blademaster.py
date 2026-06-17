#!/usr/bin/env python3
"""
inject_ai_blademaster.py — Blademaster (剑圣) 最小化测试版 v2

逻辑（疾风步穿身突进）：
  每0.1s tick:
    1. 找BM(Obla) + DK(Udea)
    2. 突进中(Dashing=1):
       - 距DK < 100码 -> UnitRemoveBuffs -> attack DK -> Dashing=0
       - 距DK >= 100码 -> move靠近DK (隐身穿身)
    3. 非突进:
       - 疾风步可用 -> 释放windwalk -> Dashing=1 -> move靠近DK
       - 疾风步fail -> attack DK directly

挂在 HeroMagic 0.1s timer (SH_Tick endfunction)。
"""

import sys

BM_GLOBALS = """
    // [BM-MIN] Blademaster minimal test globals
    integer udg_bm_Dashing1 = 0"""

BM_FUNCTIONS = """
// ================================================================
// [BM-MIN] Blademaster: windwalk -> dash to DK -> remove buff -> attack
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
    local real dx
    local real dy
    local real dist
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
    set dx = GetUnitX(dk) - GetUnitX(bm)
    set dy = GetUnitY(dk) - GetUnitY(bm)
    set dist = SquareRoot(dx * dx + dy * dy)
    // ── 突进中 ──
    if udg_bm_Dashing1 == 1 then
        if dist < 100.0 then
            // 到达DK身边 -> 解隐身 -> 攻击
            call UnitRemoveBuffs(bm, true, false)
            call IssueTargetOrder(bm, "attack", dk)
            call DisplayTextToForce(GetPlayersAll(), "|cff00ffff[BM-MIN] reached DK (dist=" + I2S(R2I(dist)) + ") -> STRIKE hp=" + I2S(R2I(GetUnitState(dk, UNIT_STATE_LIFE))) + "|r")
            set udg_bm_Dashing1 = 0
        else
            // 继续隐身穿身靠近
            call IssuePointOrder(bm, "move", GetUnitX(dk), GetUnitY(dk))
            call DisplayTextToForce(GetPlayersAll(), "|cffff00ff[BM-MIN] dashing dist=" + I2S(R2I(dist)) + " Boro=" + I2S(GetUnitAbilityLevel(bm, 'Boro')) + "|r")
        endif
        set bm = null
        set dk = null
        return
    endif
    // ── 非突进：尝试疾风步 ──
    set ww = IssueImmediateOrder(bm, "windwalk")
    if ww then
        call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[BM-MIN] windwalk OK -> dash to DK (dist=" + I2S(R2I(dist)) + ")|r")
        set udg_bm_Dashing1 = 1
        call IssuePointOrder(bm, "move", GetUnitX(dk), GetUnitY(dk))
    else
        // 没蓝/CD -> 直接攻击DK
        call DisplayTextToForce(GetPlayersAll(), "|cffffff00[BM-MIN] windwalk fail -> attack DK directly (dist=" + I2S(R2I(dist)) + ")|r")
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

    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' found")
    idx = src.find(eg)
    src = src[:idx] + BM_GLOBALS.replace("\n", nl) + nl + src[idx:]
    print("[BM-MIN] inserted globals")

    marker = "function Trig_AIML_SH_Tick takes nothing returns nothing"
    idx_marker = src.find(marker)
    if idx_marker == -1:
        raise SystemExit("ERROR: cannot find Trig_AIML_SH_Tick — inject_hero_magic.py must run first")
    src = src[:idx_marker] + BM_FUNCTIONS.replace("\n", nl) + nl + src[idx_marker:]
    print("[BM-MIN] inserted functions")

    sh_start = src.find("function Trig_AIML_SH_Tick takes nothing returns nothing")
    sh_end = src.find("endfunction", sh_start + 10)
    if sh_end == -1:
        raise SystemExit("ERROR: cannot find SH_Tick endfunction")
    src = src[:sh_end] + f"    call Trig_AIML_BM_Tick(){nl}" + src[sh_end:]
    print("[BM-MIN] hooked BM_Tick into SH_Tick")

    reset_marker = "// Variable Reset"
    idx_reset = src.find(reset_marker)
    if idx_reset != -1:
        eol = src.index(nl, idx_reset)
        reset_code = f"    set udg_bm_Dashing1 = 0{nl}"
        src = src[:eol + len(nl)] + reset_code + src[eol + len(nl):]
        print("[BM-MIN] added state reset to Variable Reset block")
    else:
        print("[BM-MIN] WARN: Variable Reset block not found, skipping reset injection")

    src = patch_bm_skill_learn(src)

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[BM-MIN] Blademaster minimal AI (dash) injected into {path}")


if __name__ == "__main__":
    main()
