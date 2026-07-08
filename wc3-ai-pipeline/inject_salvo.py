#!/usr/bin/env python3
"""
inject_salvo.py - Ranged-force concentrated salvo (V18, custom whitelist)

Inject:
  - Salvo globals + functions
  - SalvoInit timer hook into main()
  - Independent trigger with configurable tick from ai_config.py

usage: inject_salvo.py <input.j> <output.j>
"""
import sys
import re
from ai_config import TICK_SALVO

# ---- Whitelist ----
RANGED_TROOPS = [
    # Human
    "'hrif'", "'hdhw'", "'hgry'", "'hgyr'",
    # Orc
    "'ohun'", "'otbk'", "'owyv'",
    # NE
    "'earc'", "'esen'", "'edry'", "'edot'",
    "'ehip'", "'ehpr'", "'efdr'",
    # UD
    "'ucry'", "'uabo'", "'uobs'", "'ufro'", "'ugar'", "'ugrm'",
]

RANGED_HEROES = [
    "'Hamg'", "'Hblm'",
    "'Ofar'", "'Oshd'",
    "'Ulic'",
    "'Emoo'", "'Ekee'",
    "'Nbrn'", "'Nfir'", "'Nngs'", "'Ntin'",
]

ALL_RANGED = RANGED_TROOPS + RANGED_HEROES


def build_is_ranged_troop():
    body = []
    body.append("function Trig_AIML_IsRangedTroop takes nothing returns boolean")
    body.append("    local unit u = GetFilterUnit()")
    body.append("    local integer t = GetUnitTypeId(u)")
    body.append("    local boolean ok = false")
    body.append("    if not IsUnitType(u, UNIT_TYPE_DEAD) then")
    first = True
    for tid in ALL_RANGED:
        kw = "if" if first else "elseif"
        body.append(f"        {kw} t == {tid} then")
        body.append(f"            set ok = true")
        first = False
    body.append("        endif")
    body.append("    endif")
    body.append("    if ok then")
    body.append("        if GetOwningPlayer(u) != udg_aiml_SalvoOwnerPlayer then")
    body.append("            set ok = false")
    body.append("        endif")
    body.append("    endif")
    body.append("    set u = null")
    body.append("    return ok")
    body.append("endfunction")
    return "\n".join(body)


SALVO_GLOBALS = """    // [AIML-SALVO] state (V18, custom whitelist)
    unit    udg_aiml_FocusTarget1 = null
    unit    udg_aiml_FocusTarget2 = null
    real    udg_aiml_SalvoMajorityRatio = 0.50
    integer udg_aiml_SalvoFrontRowCount = 4
    real    udg_aiml_SalvoMapRange = 99999.00
    group   udg_aiml_SalvoEnemyG = null
    group   udg_aiml_SalvoArmyG = null
    group   udg_aiml_SalvoRangedG = null
    integer udg_aiml_SalvoArmyCount = 0
    integer udg_aiml_SalvoRangedCount = 0
    player  udg_aiml_SalvoOwnerPlayer = null
    player  udg_aiml_SalvoEnemyPlayer = null
    real    udg_aiml_SalvoCurEx = 0.00
    real    udg_aiml_SalvoCurEy = 0.00
    real    udg_aiml_SalvoCurMinD = 0.00
    real    udg_aiml_SalvoPrevD = 0.00
    real    udg_aiml_SalvoCurBestD = 0.00
    unit    udg_aiml_SalvoCurRoundBest = null
    real    udg_aiml_SalvoFrontMaxD = 0.00
    real    udg_aiml_SalvoBestHp = 0.00
    real    udg_aiml_SalvoBestHeroHp = 0.00
    unit    udg_aiml_SalvoPicked = null
    unit    udg_aiml_SalvoPickedHero = null
    boolean udg_aiml_DebugMode = false
    unit    udg_aiml_LastFireTarget = null"""


SALVO_FUNCTIONS_TEMPLATE = """
//===========================================================================
// [AIML-SALVO] Ranged-force concentrated salvo (V18, custom whitelist)
//===========================================================================
__IS_RANGED_TROOP_PLACEHOLDER__

function Trig_AIML_IsArmyUnit takes nothing returns boolean
    local unit u = GetFilterUnit()
    local boolean ok = true
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set ok = false
    elseif IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set ok = false
    endif
    if ok then
        if GetOwningPlayer(u) != udg_aiml_SalvoOwnerPlayer then
            set ok = false
        endif
    endif
    set u = null
    return ok
endfunction

function Trig_AIML_IsValidSalvoTarget takes nothing returns boolean
    local unit u = GetFilterUnit()
    local boolean ok = true
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set ok = false
    elseif IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set ok = false
    endif
    if ok then
        if GetOwningPlayer(u) != udg_aiml_SalvoEnemyPlayer then
            set ok = false
        endif
    endif
    set u = null
    return ok
endfunction

function Trig_AIML_UpdateMinDistCB takes nothing returns nothing
    local unit a = GetEnumUnit()
    local real ax = GetUnitX(a)
    local real ay = GetUnitY(a)
    local real dx = ax - udg_aiml_SalvoCurEx
    local real dy = ay - udg_aiml_SalvoCurEy
    local real d = dx*dx + dy*dy
    if d < udg_aiml_SalvoCurMinD then
        set udg_aiml_SalvoCurMinD = d
    endif
    set a = null
endfunction

function Trig_AIML_MinDistSqToArmy takes real ex, real ey returns real
    set udg_aiml_SalvoCurEx = ex
    set udg_aiml_SalvoCurEy = ey
    set udg_aiml_SalvoCurMinD = 999999999.0
    call ForGroup(udg_aiml_SalvoArmyG, function Trig_AIML_UpdateMinDistCB)
    return udg_aiml_SalvoCurMinD
endfunction

function Trig_AIML_SelectRoundCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real ex
    local real ey
    local real d
    if u == null then
        return
    endif
    set ex = GetUnitX(u)
    set ey = GetUnitY(u)
    set d = Trig_AIML_MinDistSqToArmy(ex, ey)
    if d > udg_aiml_SalvoPrevD then
        if d < udg_aiml_SalvoCurBestD then
            set udg_aiml_SalvoCurBestD = d
            set udg_aiml_SalvoCurRoundBest = u
        endif
    endif
    set u = null
endfunction

function Trig_AIML_PickPhase2CB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local real ex
    local real ey
    local real d
    local real hp
    if u == null then
        return
    endif
    set ex = GetUnitX(u)
    set ey = GetUnitY(u)
    set d = Trig_AIML_MinDistSqToArmy(ex, ey)
    if d <= udg_aiml_SalvoFrontMaxD then
        set hp = GetWidgetLife(u)
        if IsUnitType(u, UNIT_TYPE_HERO) then
            if hp < udg_aiml_SalvoBestHeroHp then
                set udg_aiml_SalvoBestHeroHp = hp
                set udg_aiml_SalvoPickedHero = u
            endif
        else
            if hp < udg_aiml_SalvoBestHp then
                set udg_aiml_SalvoBestHp = hp
                set udg_aiml_SalvoPicked = u
            endif
        endif
    endif
    set u = null
endfunction

function Trig_AIML_PickSalvoTarget takes nothing returns unit
    local integer round
    local integer rowN = udg_aiml_SalvoFrontRowCount
    if udg_aiml_SalvoArmyCount == 0 then
        return null
    endif
    set udg_aiml_SalvoPrevD = -1.0
    set round = 0
    loop
        exitwhen round >= rowN
        set udg_aiml_SalvoCurBestD = 999999999.0
        set udg_aiml_SalvoCurRoundBest = null
        call ForGroup(udg_aiml_SalvoEnemyG, function Trig_AIML_SelectRoundCB)
        if udg_aiml_SalvoCurRoundBest == null then
            exitwhen true
        endif
        set udg_aiml_SalvoPrevD = udg_aiml_SalvoCurBestD
        set round = round + 1
    endloop
    set udg_aiml_SalvoFrontMaxD = udg_aiml_SalvoPrevD
    set udg_aiml_SalvoBestHp = 999999.0
    set udg_aiml_SalvoBestHeroHp = 999999.0
    set udg_aiml_SalvoPicked = null
    set udg_aiml_SalvoPickedHero = null
    call ForGroup(udg_aiml_SalvoEnemyG, function Trig_AIML_PickPhase2CB)
    if udg_aiml_SalvoPickedHero != null then
        return udg_aiml_SalvoPickedHero
    endif
    return udg_aiml_SalvoPicked
endfunction

function Trig_AIML_IssueAttackCB takes nothing returns nothing
    local unit u = GetEnumUnit()
    local unit target = udg_aiml_FocusTarget1
    if target == null then
        set u = null
        return
    endif
    if IsUnitType(target, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    if u == null then
        return
    endif
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set u = null
        return
    endif
    call IssueTargetOrder(u, "smart", target)
    set u = null
endfunction

function Trig_AIML_RebuildGroupArmy takes nothing returns nothing
    call GroupClear(udg_aiml_SalvoArmyG)
    call GroupEnumUnitsOfPlayer(udg_aiml_SalvoArmyG, udg_aiml_SalvoOwnerPlayer, Filter(function Trig_AIML_IsArmyUnit))
    set udg_aiml_SalvoArmyCount = CountUnitsInGroup(udg_aiml_SalvoArmyG)
endfunction

function Trig_AIML_RebuildGroupRanged takes nothing returns nothing
    call GroupClear(udg_aiml_SalvoRangedG)
    call GroupEnumUnitsOfPlayer(udg_aiml_SalvoRangedG, udg_aiml_SalvoOwnerPlayer, Filter(function Trig_AIML_IsRangedTroop))
    set udg_aiml_SalvoRangedCount = CountUnitsInGroup(udg_aiml_SalvoRangedG)
endfunction

function Trig_AIML_RebuildGroupEnemy takes nothing returns nothing
    call GroupClear(udg_aiml_SalvoEnemyG)
    call GroupEnumUnitsOfPlayer(udg_aiml_SalvoEnemyG, udg_aiml_SalvoEnemyPlayer, Filter(function Trig_AIML_IsValidSalvoTarget))
endfunction

function Trig_AIML_SalvoForPlayer takes player p, player ep, integer focusSlot returns nothing
    local unit picked
    set udg_aiml_SalvoOwnerPlayer = p
    set udg_aiml_SalvoEnemyPlayer = ep
    call Trig_AIML_RebuildGroupArmy()
    if udg_aiml_SalvoArmyCount == 0 then
        return
    endif
    call Trig_AIML_RebuildGroupRanged()
    if I2R(udg_aiml_SalvoRangedCount) < I2R(udg_aiml_SalvoArmyCount) * udg_aiml_SalvoMajorityRatio then
        if focusSlot == 1 then
            set udg_aiml_FocusTarget1 = null
        else
            set udg_aiml_FocusTarget2 = null
        endif
        return
    endif
    call Trig_AIML_RebuildGroupEnemy()
    if CountUnitsInGroup(udg_aiml_SalvoEnemyG) == 0 then
        return
    endif
    // [V49] if Blademaster is in DASH/STRIKE, follow its target; else use normal target selection
    if udg_bm_Target1 != null and not IsUnitDeadBJ(udg_bm_Target1) and GetOwningPlayer(udg_bm_Target1) == ep then
        set picked = udg_bm_Target1
    else
        set picked = Trig_AIML_PickSalvoTarget()
    endif
    if picked == null then
        return
    endif
    if udg_aiml_DebugMode and picked != udg_aiml_LastFireTarget and udg_RoundNo != 1 then
        call DisplayTextToForce(GetPlayersAll(), "[AIML] FIRE >> " + GetUnitName(picked) + " (HP:" + I2S(R2I(GetUnitStateSwap(UNIT_STATE_LIFE, picked))) + ")")
        set udg_aiml_LastFireTarget = picked
    endif
    if focusSlot == 1 then
        set udg_aiml_FocusTarget1 = picked
    else
        set udg_aiml_FocusTarget2 = picked
    endif
    call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_IssueAttackCB)
endfunction

function Trig_AIML_SalvoTick takes nothing returns nothing
    call Trig_AIML_SalvoForPlayer(Player(0), Player(1), 1)
    call Trig_AIML_SalvoForPlayer(Player(1), Player(0), 2)
endfunction

function Trig_AIML_SalvoInit takes nothing returns nothing
    local trigger t
    set udg_aiml_SalvoEnemyG = CreateGroup()
    set udg_aiml_SalvoArmyG = CreateGroup()
    set udg_aiml_SalvoRangedG = CreateGroup()
    set t = CreateTrigger()
    call TriggerRegisterTimerEvent(t, __TICK_SALVO__, true)
    call TriggerAddAction(t, function Trig_AIML_SalvoTick)
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

    # 1) Inject Salvo globals into endglobals
    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' found")
    extra_g = SALVO_GLOBALS.replace("\n", nl) + nl
    idx = src.find(eg)
    src = src[:idx] + extra_g + src[idx:]
    print("[SALVO] inserted globals")

    # 2) Inject Salvo functions after endglobals
    idx_after = src.find(eg) + len(eg)
    funcs = SALVO_FUNCTIONS_TEMPLATE.replace(
        "__IS_RANGED_TROOP_PLACEHOLDER__", build_is_ranged_troop()
    )
    funcs = funcs.replace("__TICK_SALVO__", f"{TICK_SALVO:.2f}")
    funcs = funcs.replace("\n", nl)
    src = src[:idx_after] + funcs + src[idx_after:]
    print("[SALVO] inserted functions")

    # 3) Hook SalvoInit into main()
    main_pat = re.compile(
        r'function main takes nothing returns nothing' + re.escape(nl)
        + r'(.*?)' + re.escape(nl) + r'endfunction',
        re.DOTALL,
    )
    m_main = main_pat.search(src)
    if m_main and "call Trig_AIML_SalvoInit()" not in src:
        body = m_main.group(1)
        new_main = (
            f"function main takes nothing returns nothing{nl}"
            f"{body}{nl}"
            f"    call Trig_AIML_SalvoInit(){nl}"
            f"endfunction"
        )
        src = src[: m_main.start()] + new_main + src[m_main.end():]
        print("[SALVO] hooked SalvoInit into main()")

    # 4) Write out
    with open(out_path, "wb") as f:
        f.write(src.encode("latin-1"))
    print(f"[SALVO] OK -> {out_path} ({len(src)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(64)
    inject(sys.argv[1], sys.argv[2])
