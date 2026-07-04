#!/usr/bin/env python3
"""inject_ai_kodo.py — Kodo Beast devour + retreat AI

Strategy:
  - Excluded from Combat_AI army-attack (filter patch in inject_ai_creep_control.py)
  - Each tick: find best devour target by priority (abom > spider > banshee > ghoul)
  - Track target unit, wait for IsUnitHidden to confirm devour landed
  - On devour: retreat to rear of friendly army (+300 away from enemy)
  - On digestion complete (target no longer hidden): return to idle

Priority: 憎恶(uabo) > 穴居恶魔(ucry) > 女妖(uban) > 食尸鬼(ugho)
Skip: 骷髅(uske/uskm), heroes, structures, flying, mechanical
"""

import sys

KODO_GLOBALS = """
    // [KODO] devour-retreat state
    group udg_KodoRetreating1 = null
    group udg_KodoRetreating2 = null
    unit array udg_KodoTarget1
    unit array udg_KodoTarget2"""

KODO_FUNCTIONS = """
// ================================================================
//  Kodo Devour + Retreat AI
// ================================================================

function Trig_AIML_KodoPri takes integer utype returns integer
    if utype == 'Uabo' or utype == 'uabo' then
        return 1
    elseif utype == 'Uspi' or utype == 'uspi' or utype == 'ubsp' or utype == 'ucry' then
        return 2
    elseif utype == 'Uban' or utype == 'uban' then
        return 3
    elseif utype == 'Ugho' or utype == 'ugho' then
        return 4
    else
        return 99
    endif
endfunction

function Trig_AIML_KodoTypeName takes integer utype returns string
    if utype == 'Uabo' or utype == 'uabo' then
        return "憎恶"
    elseif utype == 'Uspi' or utype == 'uspi' or utype == 'ubsp' or utype == 'ucry' then
        return "穴居恶魔"
    elseif utype == 'Uban' or utype == 'uban' then
        return "女妖"
    elseif utype == 'Ugho' or utype == 'ugho' then
        return "食尸鬼"
    else
        return "未知"
    endif
endfunction

// Find best devour target for a kodo: nearest unit by priority
function Trig_AIML_KodoFindTarget takes unit kodo, player enemyP returns unit
    local group enemyGround
    local unit u
    local unit best
    local integer bestPri
    local real bestDist
    local real d
    local integer utype
    local integer pri
    local real kx
    local real ky
    local real ux
    local real uy

    set best = null
    set bestPri = 99
    set bestDist = 99999.0
    set kx = GetUnitX(kodo)
    set ky = GetUnitY(kodo)

    set enemyGround = GetUnitsOfPlayerAll(enemyP)

    loop
        set u = FirstOfGroup(enemyGround)
        exitwhen u == null
        call GroupRemoveUnit(enemyGround, u)

        if IsUnitAliveBJ(u) and not IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitType(u, UNIT_TYPE_STRUCTURE) and not IsUnitType(u, UNIT_TYPE_FLYING) and not IsUnitType(u, UNIT_TYPE_MECHANICAL) then
            set utype = GetUnitTypeId(u)
            set pri = Trig_AIML_KodoPri(utype)

            if pri < 99 then
                set ux = GetUnitX(u)
                set uy = GetUnitY(u)
                set d = SquareRoot((kx-ux)*(kx-ux) + (ky-uy)*(ky-uy))

                if pri < bestPri or (pri == bestPri and d < bestDist) then
                    set best = u
                    set bestPri = pri
                    set bestDist = d
                endif
            endif
        endif
    endloop

    call DestroyGroup(enemyGround)
    set enemyGround = null
    return best
endfunction

function Trig_AIML_KodoRetreatForPlayer takes player myP, player enemyP, group retGroup, integer playerIdx returns nothing
    local group gg = GetUnitsOfPlayerAndTypeId(myP, 'okod')
    local unit kodo
    local unit target
    local unit u
    local group allyArmy
    local real kx
    local real ky
    local real cx
    local real cy
    local real ex
    local real ey
    local real dx
    local real dy
    local real dist
    local real retreatX
    local real retreatY
    local integer allyCount
    local integer kodoIdx
    local integer curOrder

    set kodoIdx = 0

    loop
        set kodo = FirstOfGroup(gg)
        exitwhen kodo == null
        call GroupRemoveUnit(gg, kodo)

        if IsUnitAliveBJ(kodo) then

            if IsUnitInGroup(kodo, retGroup) then
                // RETREATING — check if still has unit inside
                if playerIdx == 0 then
                    set target = udg_KodoTarget1[kodoIdx]
                else
                    set target = udg_KodoTarget2[kodoIdx]
                endif

                if target != null and IsUnitAliveBJ(target) and not IsUnitHidden(target) then
                    // Target visible and alive — devour was lost, stop retreating
                    call GroupRemoveUnit(retGroup, kodo)
                    if playerIdx == 0 then
                        set udg_KodoTarget1[kodoIdx] = null
                    else
                        set udg_KodoTarget2[kodoIdx] = null
                    endif
                    set target = null
                else
                    set target = null
                endif

                // Move to rear
                set kx = GetUnitX(kodo)
                set ky = GetUnitY(kodo)

                set allyArmy = GetUnitsOfPlayerAll(myP)
                set cx = 0.0
                set cy = 0.0
                set allyCount = 0
                loop
                    set u = FirstOfGroup(allyArmy)
                    exitwhen u == null
                    call GroupRemoveUnit(allyArmy, u)
                    if IsUnitAliveBJ(u) and GetUnitTypeId(u) != 'okod' and GetUnitTypeId(u) != 'Okod' and not IsUnitType(u, UNIT_TYPE_STRUCTURE) then
                        set cx = cx + GetUnitX(u)
                        set cy = cy + GetUnitY(u)
                        set allyCount = allyCount + 1
                    endif
                endloop
                call DestroyGroup(allyArmy)
                set allyArmy = null

                if allyCount > 0 then
                    set cx = cx / I2R(allyCount)
                    set cy = cy / I2R(allyCount)
                else
                    set cx = GetLocationX(GetPlayerStartLocationLoc(myP))
                    set cy = GetLocationY(GetPlayerStartLocationLoc(myP))
                endif

                set u = GroupPickRandomUnit(GetUnitsOfPlayerAndTypeId(enemyP, 'Obla'))
                if u == null then
                    set u = GroupPickRandomUnit(GetUnitsOfPlayerAndTypeId(enemyP, 'Oshd'))
                endif
                if u == null then
                    set u = GroupPickRandomUnit(GetUnitsOfPlayerAndTypeId(enemyP, 'Udea'))
                endif
                if u == null then
                    set u = GroupPickRandomUnit(GetUnitsOfPlayerAndTypeId(enemyP, 'Ulic'))
                endif
                if u != null and IsUnitAliveBJ(u) then
                    set ex = GetUnitX(u)
                    set ey = GetUnitY(u)
                else
                    set ex = GetLocationX(GetPlayerStartLocationLoc(enemyP))
                    set ey = GetLocationY(GetPlayerStartLocationLoc(enemyP))
                endif

                set dx = cx - ex
                set dy = cy - ey
                set dist = SquareRoot(dx*dx + dy*dy)
                if dist < 1.0 then
                    set dist = 1.0
                endif
                set retreatX = cx + dx / dist * 300.0
                set retreatY = cy + dy / dist * 300.0

                if retreatX < -7000.0 then
                    set retreatX = -7000.0
                elseif retreatX > 7000.0 then
                    set retreatX = 7000.0
                endif
                if retreatY < -7000.0 then
                    set retreatY = -7000.0
                elseif retreatY > 7000.0 then
                    set retreatY = 7000.0
                endif

                set dx = kx - retreatX
                set dy = ky - retreatY
                set dist = SquareRoot(dx*dx + dy*dy)

                if dist > 200.0 then
                    call IssuePointOrder(kodo, "smart", retreatX, retreatY)
                endif

            else
                // NOT RETREATING
                if playerIdx == 0 then
                    set target = udg_KodoTarget1[kodoIdx]
                else
                    set target = udg_KodoTarget2[kodoIdx]
                endif

                if target != null then
                    // We issued devour previously — check if target got eaten
                    if not IsUnitAliveBJ(target) then
                        // Target died before being devoured — reset
                        if playerIdx == 0 then
                            set udg_KodoTarget1[kodoIdx] = null
                        else
                            set udg_KodoTarget2[kodoIdx] = null
                        endif
                        set target = null
                    elseif IsUnitHidden(target) then
                        // TARGET IS HIDDEN — devour landed! Start retreating
                        call GroupAddUnit(retGroup, kodo)
                        if udg_aiml_DebugMode then
                        call DisplayTextToForce(GetPlayersAll(), "|cff00ffcc[KODO] 吞噬成功 -> " + Trig_AIML_KodoTypeName(GetUnitTypeId(target)) + "，后撤中|r")
                        endif
                        set target = null
                    else
                        // Target still visible — re-issue devour if kodo is not walking to target
                        set curOrder = GetUnitCurrentOrder(kodo)
                        if curOrder != 851971 and curOrder != 851983 and curOrder != 851990 then
                            call IssueTargetOrder(kodo, "devour", target)
                        endif
                        set target = null
                    endif
                else
                    // No tracked target — try to find one and issue devour
                    set target = Trig_AIML_KodoFindTarget(kodo, enemyP)
                    if target != null then
                        if IssueTargetOrder(kodo, "devour", target) then
                            // Track this target
                            if playerIdx == 0 then
                                set udg_KodoTarget1[kodoIdx] = target
                            else
                                set udg_KodoTarget2[kodoIdx] = target
                            endif
                            if udg_aiml_DebugMode then
                            call DisplayTextToForce(GetPlayersAll(), "|cff00ffcc[KODO] 吞噬 -> " + Trig_AIML_KodoTypeName(GetUnitTypeId(target)) + "|r")
                            endif
                        endif
                    endif
                endif
            endif

        else
            // Dead — cleanup
            if IsUnitInGroup(kodo, retGroup) then
                call GroupRemoveUnit(retGroup, kodo)
            endif
            if playerIdx == 0 then
                set udg_KodoTarget1[kodoIdx] = null
            else
                set udg_KodoTarget2[kodoIdx] = null
            endif
        endif

        set kodoIdx = kodoIdx + 1
    endloop

    call DestroyGroup(gg)
    set gg = null
    set kodo = null
    set target = null
    set u = null
endfunction
"""


def detect_newline(raw):
    if b"\r\n" in raw[:4096]:
        return "\r\n"
    return "\n"


def inject(path, out_path=None):
    if out_path is None:
        out_path = path

    with open(path, "rb") as f:
        raw = f.read()
    nl = detect_newline(raw)
    src = raw.decode("utf-8")

    if "function Trig_AIML_KodoRetreatForPlayer" in src:
        print("[KODO] already injected, skipping")
        return

    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' found")
    idx = src.find(eg)
    src = src[:idx] + KODO_GLOBALS.replace("\n", nl) + nl + src[idx:]
    print("[KODO] inserted globals")

    salvo_marker = "function Trig_AIML_SalvoTick takes nothing returns nothing"
    idx_salvo = src.find(salvo_marker)
    if idx_salvo == -1:
        raise SystemExit("ERROR: cannot find Trig_AIML_SalvoTick")
    src = src[:idx_salvo] + KODO_FUNCTIONS.replace("\n", nl) + nl + src[idx_salvo:]
    print("[KODO] inserted functions")

    salvo_start = src.find(salvo_marker)
    salvo_endfunc = src.find("endfunction", salvo_start + 10)
    if salvo_endfunc == -1:
        raise SystemExit("ERROR: cannot find SalvoTick endfunction")

    kodo_call = (
        f"    // [KODO] kodo devour-retreat{nl}"
        f"    if udg_KodoRetreating1 == null then{nl}"
        f"        set udg_KodoRetreating1 = CreateGroup(){nl}"
        f"        set udg_KodoRetreating2 = CreateGroup(){nl}"
        f"    endif{nl}"
        f"    if GetPlayerController(Player(0)) == MAP_CONTROL_COMPUTER then{nl}"
        f"        call Trig_AIML_KodoRetreatForPlayer(Player(0), Player(1), udg_KodoRetreating1, 0){nl}"
        f"    endif{nl}"
        f"    if GetPlayerController(Player(1)) == MAP_CONTROL_COMPUTER then{nl}"
        f"        call Trig_AIML_KodoRetreatForPlayer(Player(1), Player(0), udg_KodoRetreating2, 1){nl}"
        f"    endif{nl}"
    )
    src = src[:salvo_endfunc] + kodo_call + src[salvo_endfunc:]
    print("[KODO] hooked into SalvoTick")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[KODO] Kodo devour-retreat AI injected into {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(64)
    inject(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
