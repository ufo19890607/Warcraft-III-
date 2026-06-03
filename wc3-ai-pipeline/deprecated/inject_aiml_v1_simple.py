#!/usr/bin/env python3
"""
inject_aiml_v1_simple.py

把"TC 智能战争践踏"逻辑注入到指定的 war3map.j 中。

适配规则：
- 自动识别 TC stomp 调度入口的函数名（搜函数体里有 IssueImmediateOrderBJ(... "stomp")）
- 适配换行符 (\\n vs \\r\\n)
- 仅替换入口函数体，保留其他逻辑

usage: inject_aiml_v1_simple.py <input.j> <output.j>
"""
import sys
import re
import os


AIML_GLOBALS_LINES = [
    "    // [AIML] TC Smart War Stomp shared globals",
    "    group   udg_aiml_TempGroup = null",
    "    unit    udg_aiml_StompCaster = null",
    "    integer udg_aiml_StompMinEnemies = 2",
    "    real    udg_aiml_StompRadius = 250.00",
    "    real    udg_aiml_StompManaCost = 100.00",
    "    real    udg_aiml_StompHeroBypassRadius = 250.00",
]


AIML_FUNCTIONS_BODY = """
//===========================================================================
// [AIML] TC Smart War Stomp - replaces dumb stomp calls
// Conditions: enough mana AND (hero in melee range OR >=2 valid ground enemies in radius)
//===========================================================================
function Trig_AIML_IsValidStompTarget takes nothing returns boolean
    local unit u = GetFilterUnit()
    local boolean ok = true
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set ok = false
    elseif IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set ok = false
    elseif IsUnitType(u, UNIT_TYPE_FLYING) then
        set ok = false
    endif
    if ok then
        if IsUnitAlly(u, GetOwningPlayer(udg_aiml_StompCaster)) then
            set ok = false
        endif
    endif
    set u = null
    return ok
endfunction

function Trig_AIML_IsHostileHeroInRange takes nothing returns boolean
    local unit u = GetFilterUnit()
    local boolean ok = false
    if IsUnitType(u, UNIT_TYPE_HERO) then
        if not IsUnitType(u, UNIT_TYPE_DEAD) then
            if not IsUnitAlly(u, GetOwningPlayer(udg_aiml_StompCaster)) then
                set ok = true
            endif
        endif
    endif
    set u = null
    return ok
endfunction

function Trig_AIML_TC_Stomp_Logic takes unit tc returns nothing
    local real cx
    local real cy
    local group g = CreateGroup()
    local integer count = 0
    local boolean heroNear = false
    if tc == null then
        call DestroyGroup(g)
        return
    endif
    if IsUnitType(tc, UNIT_TYPE_DEAD) then
        call DestroyGroup(g)
        return
    endif
    if GetUnitState(tc, UNIT_STATE_MANA) < udg_aiml_StompManaCost then
        call DestroyGroup(g)
        return
    endif
    set cx = GetUnitX(tc)
    set cy = GetUnitY(tc)
    set udg_aiml_StompCaster = tc
    // hero check first (always stomp if hostile hero is in radius)
    call GroupEnumUnitsInRange(g, cx, cy, udg_aiml_StompHeroBypassRadius, Filter(function Trig_AIML_IsHostileHeroInRange))
    if CountUnitsInGroup(g) > 0 then
        set heroNear = true
    endif
    call GroupClear(g)
    if heroNear then
        call IssueImmediateOrder(tc, "stomp")
        call DestroyGroup(g)
        return
    endif
    // crowd check
    call GroupEnumUnitsInRange(g, cx, cy, udg_aiml_StompRadius, Filter(function Trig_AIML_IsValidStompTarget))
    set count = CountUnitsInGroup(g)
    if count >= udg_aiml_StompMinEnemies then
        call IssueImmediateOrder(tc, "stomp")
    endif
    call DestroyGroup(g)
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

    # 1) 找所有 "TC stomp 调度入口" — 函数体仅一行 IssueImmediateOrderBJ(... "stomp")
    #    匹配格式: function NAME takes nothing returns nothing\n    call IssueImmediateOrderBJ( ..., "stomp" )\nendfunction
    pattern = re.compile(
        r'function (Trig_Computer\d+Combat_AI_Func\d+A) takes nothing returns nothing'
        + re.escape(nl)
        + r'(\s*call IssueImmediateOrderBJ\(\s*GetEnumUnit\(\),\s*"stomp"\s*\))'
        + re.escape(nl)
        + r'endfunction'
    )

    matches = list(pattern.finditer(src))
    if not matches:
        # 兼容上次那张图的"无空格"格式: IssueImmediateOrder(GetEnumUnit(), "stomp")
        pattern2 = re.compile(
            r'function (Trig_Computer\d+Combat_AI_Func\d+A) takes nothing returns nothing'
            + re.escape(nl)
            + r'(\s*call IssueImmediateOrder(?:BJ)?\([^)]*"stomp"[^)]*\))'
            + re.escape(nl)
            + r'endfunction'
        )
        matches = list(pattern2.finditer(src))

    if not matches:
        print(f"WARN: 没找到 TC stomp 调度入口（无任何 IssueImmediateOrderBJ(..., \"stomp\")）", file=sys.stderr)

    # 2) 替换每个入口的函数体为 call Trig_AIML_TC_Stomp_Logic(GetEnumUnit())
    for m in reversed(matches):
        fname = m.group(1)
        new_body = (
            f"function {fname} takes nothing returns nothing"
            + nl
            + "    // [AIML] replaced dumb stomp with smart logic"
            + nl
            + "    call Trig_AIML_TC_Stomp_Logic(GetEnumUnit())"
            + nl
            + "endfunction"
        )
        src = src[: m.start()] + new_body + src[m.end():]
        print(f"hooked: {fname}")

    # 3) 找 endglobals 之后插 AIML globals
    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: no 'endglobals' line found")
    # 把 globals 行加到 endglobals 之前
    extra_g = nl.join(AIML_GLOBALS_LINES) + nl
    idx = src.find(eg)
    src = src[:idx] + extra_g + src[idx:]

    # 4) 在 endglobals 之后立即插函数体
    idx_after = src.find(eg) + len(eg)
    funcs = AIML_FUNCTIONS_BODY.replace("\n", nl)
    src = src[:idx_after] + funcs + src[idx_after:]

    # 5) 写出
    with open(out_path, "wb") as f:
        f.write(src.encode("latin-1"))

    print(f"OK -> {out_path} ({len(src)} bytes; hooked {len(matches)} entries)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(64)
    inject(sys.argv[1], sys.argv[2])
