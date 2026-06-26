#!/usr/bin/env python3
"""
inject_ai_escape.py -- 防围杀 AI v3 (Anti-Encirclement Escape)

逻辑：
  独立 0.5s 定时器。
  - 300码内 >= 2 个敌方单位 -> 触发逃跑，cooldown = 2 tick
  - 逃跑方向：避开障碍物(地形/野怪/边界)，朝开阔地跑 300码
  - 我方单位忽略
  - cooldown 期间持续发 move，卡住自动换方向
  - cooldown 结束后重判：仍被围继续逃，没被围则打怪或打敌

命令：-escape 开/关（默认开），-debug 调试打印
"""

import sys

ESCAPE_GLOBALS = """\
    // [ESCAPE v3] anti-encirclement globals
    boolean udg_aiml_EscapeMode   = true
    integer udg_esc_Cooldown0     = 0
    integer udg_esc_Cooldown1     = 0
    integer udg_esc_DbgTick       = 0
    real    udg_esc_LastX0        = 0.0
    real    udg_esc_LastY0        = 0.0
    real    udg_esc_LastX1        = 0.0
    real    udg_esc_LastY1        = 0.0
    real    udg_esc_TempDX        = 0.0
    real    udg_esc_TempDY        = 0.0
    real    udg_esc_LockDX0       = 0.0
    real    udg_esc_LockDY0       = 0.0
    real    udg_esc_LockDX1       = 0.0
    real    udg_esc_LockDY1       = 0.0
    boolean udg_esc_DirLocked0    = false
    boolean udg_esc_DirLocked1    = false
    integer udg_esc_StuckCount0   = 0
    integer udg_esc_StuckCount1   = 0
    unit udg_esc_BreakTarget     = null
    unit udg_esc_CreepTarget     = null
    real udg_esc_BreakTargetX    = 0.0
    real udg_esc_BreakTargetY    = 0.0
    boolean array udg_esc_ObsFlag
    integer array udg_esc_BaseScore
    real    udg_esc_PenalDX       = 0.0
    real    udg_esc_PenalDY       = 0.0
    integer array udg_esc_FinalScore
    // Obstacle memory: up to 60 points
    real array udg_esc_MemX
    real array udg_esc_MemY
    integer udg_esc_MemCount      = 0
    boolean array udg_esc_TreeGrid
"""

ESCAPE_FUNCTIONS = """\
// ================================================================
// [ESCAPE v3] Anti-Encirclement: count units, flee to open ground
// ================================================================

function Trig_AIML_DirName takes real dx, real dy returns string
    if dx == 0.0 and dy > 0.0 then
        return "N"
    elseif dx > 0.0 and dy > 0.0 then
        return "NE"
    elseif dx > 0.0 and dy == 0.0 then
        return "E"
    elseif dx > 0.0 and dy < 0.0 then
        return "SE"
    elseif dx == 0.0 and dy < 0.0 then
        return "S"
    elseif dx < 0.0 and dy < 0.0 then
        return "SW"
    elseif dx < 0.0 and dy == 0.0 then
        return "W"
    elseif dx < 0.0 and dy > 0.0 then
        return "NW"
    else
        return "?"
    endif
endfunction

// Check if a point is within map bounds (200y margin)
function Trig_AIML_InBounds takes real x, real y returns boolean
    if x < -5400.0 or x > 5400.0 then
        return false
    endif
    if y < -2800.0 or y > 2300.0 then
        return false
    endif
    return true
endfunction

// Check if a point is walkable (terrain not blocked)
function Trig_AIML_IsWalkable takes real x, real y returns boolean
    return not IsTerrainPathable(x, y, PATHING_TYPE_WALKABILITY)
endfunction

// Check if there are neutral hostile (creep) units within 300y of (x, y)
function Trig_AIML_HasCreepNear takes real x, real y returns boolean
    local group g = CreateGroup()
    local unit u
    local real dx
    local real dy
    local boolean found = false
    call GroupEnumUnitsOfPlayer(g, Player(PLAYER_NEUTRAL_AGGRESSIVE), null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitType(u, UNIT_TYPE_DEAD) then
            set dx = GetUnitX(u) - x
            set dy = GetUnitY(u) - y
            if dx * dx + dy * dy <= 90000.0 then
                set found = true
                exitwhen true
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    return found
endfunction

// ================================================================
// Obstacle Memory System
// ================================================================

// Try to add a point to memory. Skip if within 100y of existing point.
function Trig_AIML_MemAdd takes real x, real y returns nothing
    local integer i
    local real dx
    local real dy
    if udg_esc_MemCount >= 100 then
        return
    endif
    set i = 0
    loop
        exitwhen i >= udg_esc_MemCount
        set dx = udg_esc_MemX[i] - x
        set dy = udg_esc_MemY[i] - y
        if dx * dx + dy * dy <= 10000.0 then
            return
        endif
        set i = i + 1
    endloop
    set udg_esc_MemX[udg_esc_MemCount] = x
    set udg_esc_MemY[udg_esc_MemCount] = y
    set udg_esc_MemCount = udg_esc_MemCount + 1
endfunction

// Check if any memory point is within 100y of (x, y)
function Trig_AIML_MemHasNear takes real x, real y returns boolean
    local integer i
    local real dx
    local real dy
    set i = 0
    loop
        exitwhen i >= udg_esc_MemCount
        set dx = udg_esc_MemX[i] - x
        set dy = udg_esc_MemY[i] - y
        if dx * dx + dy * dy <= 10000.0 then
            return true
        endif
        set i = i + 1
    endloop
    return false
endfunction


// 8-direction escape angle table (cos, sin) * 45 degrees apart
// 0=N, 1=NE, 2=E, 3=SE, 4=S, 5=SW, 6=W, 7=NW
function Trig_AIML_DirDX takes integer i returns real
    if i == 0 then
        return 0.0    // N
    elseif i == 1 then
        return 0.707  // NE
    elseif i == 2 then
        return 1.0    // E
    elseif i == 3 then
        return 0.707  // SE
    elseif i == 4 then
        return 0.0    // S
    elseif i == 5 then
        return -0.707 // SW
    elseif i == 6 then
        return -1.0   // W
    else
        return -0.707 // NW
    endif
endfunction

function Trig_AIML_DirDY takes integer i returns real
    if i == 0 then
        return 1.0    // N
    elseif i == 1 then
        return 0.707  // NE
    elseif i == 2 then
        return 0.0    // E
    elseif i == 3 then
        return -0.707 // SE
    elseif i == 4 then
        return -1.0   // S
    elseif i == 5 then
        return -0.707 // SW
    elseif i == 6 then
        return 0.0    // W
    else
        return 0.707  // NW
    endif
endfunction

// [TREE GRID] O(1) grid query: is (x,y) in a tree cell?
function Trig_AIML_HasTreeAt takes real x, real y, real rad returns boolean
    local integer col = R2I((x - (-5600.0)) / 128.0)
    local integer row = R2I((y - (-3000.0)) / 128.0)
    if col < 0 or col >= 88 or row < 0 or row >= 43 then
        return false
    endif
    return udg_esc_TreeGrid[col * 43 + row]
endfunction

// Pick escape direction using scoring with 16 directions:
// score = enemyCountInDir + (hasObstacle ? 100 : 0)
// Result in udg_esc_TempDX / udg_esc_TempDY.
function Trig_AIML_PickEscapeDir takes real hx, real hy, integer enemyNE, integer enemyNW, integer enemySE, integer enemySW, boolean stuck returns nothing
    local integer i
    local real dx
    local real dy
    local real tx
    local real ty
    local integer score
    local integer bestScore = 999
    local integer bestPick = -1
    local integer randStart
    local integer enemyQuad

    // Priority 2: score all 8 directions in two passes
    // Pass 1: compute base score + obstacle flag for each direction
    set i = 0
    loop
        exitwhen i >= 8
        set dx = Trig_AIML_DirDX(i)
        set dy = Trig_AIML_DirDY(i)
        if dx >= 0.0 and dy >= 0.0 then
            set enemyQuad = enemyNE
        elseif dx < 0.0 and dy >= 0.0 then
            set enemyQuad = enemyNW
        elseif dx >= 0.0 and dy < 0.0 then
            set enemyQuad = enemySE
        else
            set enemyQuad = enemySW
        endif
        set score = enemyQuad * 5
        set udg_esc_ObsFlag[i] = false
        // Forward scan: every 100y from 100 to 500, check memory + terrain + tree grid
        if not Trig_AIML_InBounds(hx + dx * 212.1, hy + dy * 212.1) then
            set score = score + 100
            set udg_esc_ObsFlag[i] = true
        elseif Trig_AIML_HasCreepNear(hx + dx * 212.1, hy + dy * 212.1) then
            set score = score + 100
            set udg_esc_ObsFlag[i] = true
        else
            set tx = hx + dx * 100.0
            set ty = hy + dy * 100.0
            loop
                // Check memory first (fast), then IsTerrainPathable (and record)
                if Trig_AIML_MemHasNear(tx, ty) then
                    set score = score + 100
                    set udg_esc_ObsFlag[i] = true
                    exitwhen true
                endif
                if not Trig_AIML_InBounds(tx, ty) then
                    set score = score + 100
                    set udg_esc_ObsFlag[i] = true
                    exitwhen true
                endif
                if not Trig_AIML_IsWalkable(tx, ty) then
                    set score = score + 100
                    set udg_esc_ObsFlag[i] = true
                    call Trig_AIML_MemAdd(tx, ty)
                    exitwhen true
                endif
                if Trig_AIML_HasTreeAt(tx, ty, 0.0) then
                    set score = score + 100
                    set udg_esc_ObsFlag[i] = true
                    exitwhen true
                endif
                if (tx - hx) * (tx - hx) + (ty - hy) * (ty - hy) >= 250000.0 then
                    exitwhen true
                endif
                set tx = tx + dx * 100.0
                set ty = ty + dy * 100.0
            endloop
        endif
        set udg_esc_BaseScore[i] = score
        set i = i + 1
    endloop
    // Pass 2: apply neighbor penalty + stuck penalty + pick lowest
    set randStart = ModuloInteger(GetRandomInt(0, 99), 8)
    set i = 0
    loop
        exitwhen i >= 8
        set score = udg_esc_BaseScore[ModuloInteger(randStart + i, 8)]
        if not udg_esc_ObsFlag[ModuloInteger(randStart + i, 8)] then
            if udg_esc_ObsFlag[ModuloInteger(randStart + i + 7, 8)] and udg_esc_ObsFlag[ModuloInteger(randStart + i + 1, 8)] then
                set score = score + 50
            elseif udg_esc_ObsFlag[ModuloInteger(randStart + i + 7, 8)] or udg_esc_ObsFlag[ModuloInteger(randStart + i + 1, 8)] then
                set score = score + 10
            endif
        endif
        // Stuck penalty: if this direction matches penalized dir, +100
        set dx = Trig_AIML_DirDX(ModuloInteger(randStart + i, 8))
        set dy = Trig_AIML_DirDY(ModuloInteger(randStart + i, 8))
        if dx == udg_esc_PenalDX and dy == udg_esc_PenalDY then
            set score = score + 100
        endif
        set udg_esc_FinalScore[ModuloInteger(randStart + i, 8)] = score
        if score < bestScore then
            set bestScore = score
            set bestPick = ModuloInteger(randStart + i, 8)
        endif
        set i = i + 1
    endloop
    // Apply best direction
    if bestPick >= 0 then
        set udg_esc_TempDX = Trig_AIML_DirDX(bestPick)
        set udg_esc_TempDY = Trig_AIML_DirDY(bestPick)
    else
        // Last resort: head to map center
        set dx = 0.0 - hx
        set dy = 0.0 - hy
        if dx > 0.0 then
            set dx = 1.0
        elseif dx < 0.0 then
            set dx = -1.0
        endif
        if dy > 0.0 then
            set dy = 1.0
        elseif dy < 0.0 then
            set dy = -1.0
        endif
        set udg_esc_TempDX = dx
        set udg_esc_TempDY = dy
    endif
    // Print all 8 direction scores in one line (debug only)
    if udg_aiml_DebugMode then
        call DisplayTextToForce(GetPlayersAll(), "|cff888888[ESC-SCORE] mem=" + I2S(udg_esc_MemCount) + " N=" + I2S(udg_esc_FinalScore[0]) + " NE=" + I2S(udg_esc_FinalScore[1]) + " E=" + I2S(udg_esc_FinalScore[2]) + " SE=" + I2S(udg_esc_FinalScore[3]) + " S=" + I2S(udg_esc_FinalScore[4]) + " SW=" + I2S(udg_esc_FinalScore[5]) + " W=" + I2S(udg_esc_FinalScore[6]) + " NW=" + I2S(udg_esc_FinalScore[7]) + "|r")
    endif
endfunction

// ================================================================
// [BREAKOUT] All AI units attack lowest-HP enemy within 200y of hero
// Called when hero is stuck for 3+ consecutive ticks (surrounded by bodies)
// ================================================================
function Trig_AIML_Breakout takes unit hero, player owner, player enemyPlayer returns nothing
    local real hx = GetUnitX(hero)
    local real hy = GetUnitY(hero)
    local group g = CreateGroup()
    local unit u
    local unit target = null
    local real lowestHP = 99999.0
    local real hp
    local real dx
    local real dy
    local group army
    // Find lowest-HP enemy within 200y
    call GroupEnumUnitsOfPlayer(g, enemyPlayer, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitType(u, UNIT_TYPE_DEAD) then
            set dx = GetUnitX(u) - hx
            set dy = GetUnitY(u) - hy
            if dx * dx + dy * dy <= 40000.0 then
                set hp = GetWidgetLife(u)
                if hp < lowestHP then
                    set lowestHP = hp
                    set target = u
                endif
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    if target == null then
        return
    endif
    // Lock target and issue attack to all AI units
    set udg_esc_BreakTarget = target
    set udg_esc_BreakTargetX = GetUnitX(target)
    set udg_esc_BreakTargetY = GetUnitY(target)
    set army = CreateGroup()
    call GroupEnumUnitsOfPlayer(army, owner, null)
    loop
        set u = FirstOfGroup(army)
        exitwhen u == null
        call GroupRemoveUnit(army, u)
        if not IsUnitType(u, UNIT_TYPE_DEAD) then
            call IssueTargetOrder(u, "attack", target)
        endif
    endloop
    call DestroyGroup(army)
    set army = null
    call DisplayTextToForce(GetPlayersAll(), "|cffff8800[BREAKOUT] " + GetUnitName(hero) + " -> focus " + GetUnitName(target) + " (HP=" + I2S(R2I(lowestHP)) + ")|r")
    set target = null
endfunction


// slot=0/1 for last-pos tracking. Returns new cooldown.
function Trig_AIML_Escape_Hero takes unit hero, player ep, integer cooldown, integer slot returns integer
    local real hx = GetUnitX(hero)
    local real hy = GetUnitY(hero)
    local group g
    local unit u
    local real ux
    local real uy
    local real distSq
    local real nearestDistSq = 99999999.0
    local unit nearestEnemy = null
    local integer enemyCount300 = 0
    // enemy quadrant flags (for direction avoidance)
    local integer enemyNE = 0
    local integer enemyNW = 0
    local integer enemySE = 0
    local integer enemySW = 0
    local real dirX = 1.0
    local real dirY = 1.0
    local real lastX
    local real lastY
    local real movedSq
    local boolean stuck = false
    local group g2
    local real checkX
    local real checkY
    local integer di
    // [BREAKOUT LOCK] If we have a locked breakout target, keep attacking it
    if udg_esc_BreakTarget != null then
        if IsUnitType(udg_esc_BreakTarget, UNIT_TYPE_DEAD) or GetWidgetLife(udg_esc_BreakTarget) <= 0.0 then
            // Target dead -> clear lock, resume escape
            set udg_esc_BreakTarget = null
        else
            set checkX = GetUnitX(udg_esc_BreakTarget) - udg_esc_BreakTargetX
            set checkY = GetUnitY(udg_esc_BreakTarget) - udg_esc_BreakTargetY
            if checkX * checkX + checkY * checkY > 10000.0 then
                // Target moved > 100y from lock position -> clear lock, resume escape
                set udg_esc_BreakTarget = null
            else
                // Target alive and in place -> re-issue attack to ALL units every tick
                set g = CreateGroup()
                call GroupEnumUnitsOfPlayer(g, GetOwningPlayer(hero), null)
                loop
                    set u = FirstOfGroup(g)
                    exitwhen u == null
                    call GroupRemoveUnit(g, u)
                    if not IsUnitType(u, UNIT_TYPE_DEAD) then
                        call IssueTargetOrder(u, "attack", udg_esc_BreakTarget)
                    endif
                endloop
                call DestroyGroup(g)
                set g = null
                return cooldown
            endif
        endif
    endif
    // [CREEP LOCK] If we have a locked creep target, keep attacking it
    if udg_esc_CreepTarget != null then
        // First check: are we now surrounded? If so, abort creep and let escape handle it
        set g = CreateGroup()
        call GroupEnumUnitsOfPlayer(g, ep, null)
        set enemyCount300 = 0
        loop
            set u = FirstOfGroup(g)
            exitwhen u == null
            call GroupRemoveUnit(g, u)
            if not IsUnitType(u, UNIT_TYPE_DEAD) then
                set ux = GetUnitX(u) - hx
                set uy = GetUnitY(u) - hy
                if ux * ux + uy * uy <= 90000.0 then
                    set enemyCount300 = enemyCount300 + 1
                endif
            endif
        endloop
        call DestroyGroup(g)
        set g = null
        if enemyCount300 >= 2 then
            // Surrounded! Abort creep, let escape trigger below
            set udg_esc_CreepTarget = null
        elseif IsUnitType(udg_esc_CreepTarget, UNIT_TYPE_DEAD) or GetWidgetLife(udg_esc_CreepTarget) <= 0.0 then
            // Target dead -> clear lock
            set udg_esc_CreepTarget = null
        else
            // Target alive, not surrounded -> all units keep attacking
            set g = CreateGroup()
            call GroupEnumUnitsOfPlayer(g, GetOwningPlayer(hero), null)
            loop
                set u = FirstOfGroup(g)
                exitwhen u == null
                call GroupRemoveUnit(g, u)
                if not IsUnitType(u, UNIT_TYPE_DEAD) then
                    call IssueTargetOrder(u, "attack", udg_esc_CreepTarget)
                endif
            endloop
            call DestroyGroup(g)
            set g = null
            return cooldown
        endif
    endif
    // Load last position for stuck detection
    if slot == 0 then
        set lastX = udg_esc_LastX0
        set lastY = udg_esc_LastY0
        set udg_esc_LastX0 = hx
        set udg_esc_LastY0 = hy
    else
        set lastX = udg_esc_LastX1
        set lastY = udg_esc_LastY1
        set udg_esc_LastX1 = hx
        set udg_esc_LastY1 = hy
    endif
    set movedSq = (hx - lastX) * (hx - lastX) + (hy - lastY) * (hy - lastY)
    if movedSq < 3600.0 then
        set stuck = true
        // Record stuck position as obstacle ONLY if front is blocked by terrain
        if slot == 0 then
            if not Trig_AIML_IsWalkable(hx + udg_esc_LockDX0 * 100.0, hy + udg_esc_LockDY0 * 100.0) then
                call Trig_AIML_MemAdd(hx + udg_esc_LockDX0 * 100.0, hy + udg_esc_LockDY0 * 100.0)
            endif
        else
            if not Trig_AIML_IsWalkable(hx + udg_esc_LockDX1 * 100.0, hy + udg_esc_LockDY1 * 100.0) then
                call Trig_AIML_MemAdd(hx + udg_esc_LockDX1 * 100.0, hy + udg_esc_LockDY1 * 100.0)
            endif
        endif
    endif
    // [BREAKOUT] stuck 3+ ticks -> all AI focus lowest-HP enemy in 200y
    if stuck then
        if slot == 0 then
            set udg_esc_StuckCount0 = udg_esc_StuckCount0 + 1
        else
            set udg_esc_StuckCount1 = udg_esc_StuckCount1 + 1
        endif
    else
        if slot == 0 then
            set udg_esc_StuckCount0 = 0
        else
            set udg_esc_StuckCount1 = 0
        endif
    endif
    if slot == 0 and udg_esc_StuckCount0 >= 3 then
        call Trig_AIML_Breakout(hero, GetOwningPlayer(hero), ep)
        set udg_esc_StuckCount0 = 0
        return cooldown
    endif
    if slot == 1 and udg_esc_StuckCount1 >= 3 then
        call Trig_AIML_Breakout(hero, GetOwningPlayer(hero), ep)
        set udg_esc_StuckCount1 = 0
        return cooldown
    endif
    // --- Escaping (cooldown > 0): keep moving, count down ---
    if cooldown > 0 then
        // Quick scan: enemy quads within 300y for direction avoidance
        set g = CreateGroup()
        call GroupEnumUnitsOfPlayer(g, ep, null)
        loop
            set u = FirstOfGroup(g)
            exitwhen u == null
            call GroupRemoveUnit(g, u)
            if not IsUnitType(u, UNIT_TYPE_DEAD) then
                set ux = GetUnitX(u) - hx
                set uy = GetUnitY(u) - hy
                set distSq = ux * ux + uy * uy
                if distSq <= 90000.0 then
                    if ux >= 0.0 and uy >= 0.0 then
                        set enemyNE = enemyNE + 1
                    elseif ux < 0.0 and uy >= 0.0 then
                        set enemyNW = enemyNW + 1
                    elseif ux >= 0.0 and uy < 0.0 then
                        set enemySE = enemySE + 1
                    else
                        set enemySW = enemySW + 1
                    endif
                endif
            endif
        endloop
        call DestroyGroup(g)
        set g = null
        // Direction lock: keep same direction unless stuck or front blocked
        if slot == 0 then
            // Front check: if locked dir blocked at 350y (memory or terrain), unlock
            if udg_esc_DirLocked0 and not stuck then
                set checkX = hx + udg_esc_LockDX0 * 350.0
                set checkY = hy + udg_esc_LockDY0 * 350.0
                if Trig_AIML_MemHasNear(checkX, checkY) or not Trig_AIML_IsWalkable(checkX, checkY) then
                    set udg_esc_DirLocked0 = false
                endif
            endif
            if stuck or not udg_esc_DirLocked0 then
                if stuck then
                    set udg_esc_PenalDX = udg_esc_LockDX0
                    set udg_esc_PenalDY = udg_esc_LockDY0
                else
                    set udg_esc_PenalDX = 0.0
                    set udg_esc_PenalDY = 0.0
                endif
                call Trig_AIML_PickEscapeDir(hx, hy, enemyNE, enemyNW, enemySE, enemySW, stuck)
                set udg_esc_LockDX0 = udg_esc_TempDX
                set udg_esc_LockDY0 = udg_esc_TempDY
                set udg_esc_DirLocked0 = true
            endif
            set dirX = udg_esc_LockDX0
            set dirY = udg_esc_LockDY0
        else
            if udg_esc_DirLocked1 and not stuck then
                set checkX = hx + udg_esc_LockDX1 * 350.0
                set checkY = hy + udg_esc_LockDY1 * 350.0
                if Trig_AIML_MemHasNear(checkX, checkY) or not Trig_AIML_IsWalkable(checkX, checkY) then
                    set udg_esc_DirLocked1 = false
                endif
            endif
            if stuck or not udg_esc_DirLocked1 then
                if stuck then
                    set udg_esc_PenalDX = udg_esc_LockDX1
                    set udg_esc_PenalDY = udg_esc_LockDY1
                else
                    set udg_esc_PenalDX = 0.0
                    set udg_esc_PenalDY = 0.0
                endif
                call Trig_AIML_PickEscapeDir(hx, hy, enemyNE, enemyNW, enemySE, enemySW, stuck)
                set udg_esc_LockDX1 = udg_esc_TempDX
                set udg_esc_LockDY1 = udg_esc_TempDY
                set udg_esc_DirLocked1 = true
            endif
            set dirX = udg_esc_LockDX1
            set dirY = udg_esc_LockDY1
        endif
        call IssuePointOrder(hero, "move", hx + dirX * 212.1, hy + dirY * 212.1)
        if udg_aiml_DebugMode then
            if stuck then
                call DisplayTextToForce(GetPlayersAll(), "|cffff4444[ESC] " + GetUnitName(hero) + " flee " + Trig_AIML_DirName(dirX, dirY) + " STUCK cd=" + I2S(cooldown) + "|r")
            else
                call DisplayTextToForce(GetPlayersAll(), "|cffff4444[ESC] " + GetUnitName(hero) + " flee " + Trig_AIML_DirName(dirX, dirY) + " cd=" + I2S(cooldown) + "|r")
            endif
        endif
        return cooldown - 1
    endif
    // --- Cooldown == 0: scan and decide ---
    set g = CreateGroup()
    call GroupEnumUnitsOfPlayer(g, ep, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitType(u, UNIT_TYPE_DEAD) then
            set ux = GetUnitX(u) - hx
            set uy = GetUnitY(u) - hy
            set distSq = ux * ux + uy * uy
            if distSq < nearestDistSq then
                set nearestDistSq = distSq
                set nearestEnemy = u
            endif
            // Count enemies within 300y
            if distSq <= 90000.0 then
                set enemyCount300 = enemyCount300 + 1
                if ux >= 0.0 and uy >= 0.0 then
                    set enemyNE = enemyNE + 1
                elseif ux < 0.0 and uy >= 0.0 then
                    set enemyNW = enemyNW + 1
                elseif ux >= 0.0 and uy < 0.0 then
                    set enemySE = enemySE + 1
                else
                    set enemySW = enemySW + 1
                endif
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    // Trigger: >= 2 enemies within 300y

    if enemyCount300 >= 2 then
        call Trig_AIML_PickEscapeDir(hx, hy, enemyNE, enemyNW, enemySE, enemySW, false)
        set dirX = udg_esc_TempDX
        set dirY = udg_esc_TempDY
        // Lock direction for this escape burst
        if slot == 0 then
            set udg_esc_LockDX0 = dirX
            set udg_esc_LockDY0 = dirY
            set udg_esc_DirLocked0 = true
        else
            set udg_esc_LockDX1 = dirX
            set udg_esc_LockDY1 = dirY
            set udg_esc_DirLocked1 = true
        endif
        call IssuePointOrder(hero, "move", hx + dirX * 212.1, hy + dirY * 212.1)
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "|cffff4444[ESCAPE] " + GetUnitName(hero) + " SURROUNDED (" + I2S(enemyCount300) + " enemies) -> flee " + Trig_AIML_DirName(dirX, dirY) + "|r")
        endif
        set nearestEnemy = null
        return 4
    endif
    // Not surrounded: unlock direction and engage
    if slot == 0 then
        set udg_esc_DirLocked0 = false
    else
        set udg_esc_DirLocked1 = false
    endif
    if udg_aiml_DebugMode and udg_esc_DbgTick <= 0 then
        call DisplayTextToForce(GetPlayersAll(), "|cff88ffff[ESC] " + GetUnitName(hero) + " safe enemies300=" + I2S(enemyCount300) + " enemyDist=" + I2S(R2I(SquareRoot(nearestDistSq))) + "|r")
    endif
    // [CREEP] Check for low-HP neutral creep within 500y for last-hit
    set g = CreateGroup()
    call GroupEnumUnitsOfPlayer(g, Player(PLAYER_NEUTRAL_AGGRESSIVE), null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if not IsUnitType(u, UNIT_TYPE_DEAD) and GetWidgetLife(u) < 120.0 and GetWidgetLife(u) > 0.0 then
            set ux = GetUnitX(u) - hx
            set uy = GetUnitY(u) - hy
            if ux * ux + uy * uy <= 250000.0 then
                // Found low-HP creep within 500y -> lock and all-attack
                set udg_esc_CreepTarget = u
                set g2 = CreateGroup()
                call GroupEnumUnitsOfPlayer(g2, GetOwningPlayer(hero), null)
                loop
                    set u = FirstOfGroup(g2)
                    exitwhen u == null
                    call GroupRemoveUnit(g2, u)
                    if not IsUnitType(u, UNIT_TYPE_DEAD) then
                        call IssueTargetOrder(u, "attack", udg_esc_CreepTarget)
                    endif
                endloop
                call DestroyGroup(g2)
                set g2 = null
                call DestroyGroup(g)
                set g = null
                if udg_aiml_DebugMode then
                    call DisplayTextToForce(GetPlayersAll(), "|cff88ff88[CREEP] " + GetUnitName(hero) + " -> last-hit " + GetUnitName(udg_esc_CreepTarget) + " (HP=" + I2S(R2I(GetWidgetLife(udg_esc_CreepTarget))) + ")|r")
                endif
                set nearestEnemy = null
                return 0
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    if nearestDistSq > 640000.0 then
        // Enemy > 800y: attack creeps
        set g = CreateGroup()
        call GroupEnumUnitsOfPlayer(g, Player(PLAYER_NEUTRAL_AGGRESSIVE), null)
        loop
            set u = FirstOfGroup(g)
            exitwhen u == null
            call GroupRemoveUnit(g, u)
            if not IsUnitType(u, UNIT_TYPE_DEAD) then
                set ux = GetUnitX(u) - hx
                set uy = GetUnitY(u) - hy
                set distSq = ux * ux + uy * uy
                if distSq < nearestDistSq then
                    set nearestDistSq = distSq
                    set nearestEnemy = u
                endif
            endif
        endloop
        call DestroyGroup(g)
        set g = null
        if nearestEnemy != null then
            call IssueTargetOrder(hero, "attack", nearestEnemy)
            if udg_aiml_DebugMode and udg_esc_DbgTick <= 0 then
                call DisplayTextToForce(GetPlayersAll(), "|cff88ff88[ESC] " + GetUnitName(hero) + " -> creep|r")
            endif
            set nearestEnemy = null
        endif
    else
        // Enemy <= 800y: attack nearest enemy
        if nearestEnemy != null then
            call IssueTargetOrder(hero, "attack", nearestEnemy)
            if udg_aiml_DebugMode and udg_esc_DbgTick <= 0 then
                call DisplayTextToForce(GetPlayersAll(), "|cff88ff88[ESC] " + GetUnitName(hero) + " -> enemy " + GetUnitName(nearestEnemy) + "|r")
            endif
            set nearestEnemy = null
        endif
    endif
    return 0
endfunction

__GRID_INIT_PLACEHOLDER__

// Called every 0.5s (independent timer)
function Trig_AIML_EscapeTick takes nothing returns nothing
    local integer pid = 0
    local player p
    local player ep
    local group g
    local unit u
    local unit hero0
    local unit hero1
    local integer heroCount
    if not udg_aiml_EscapeMode or udg_aiml_Round1Mode != 2 then
        return
    endif
    loop
        exitwhen pid > 11
        set p = Player(pid)
        if GetPlayerController(p) == MAP_CONTROL_COMPUTER and GetPlayerSlotState(p) == PLAYER_SLOT_STATE_PLAYING then
            set heroCount = 0
            set hero0 = null
            set hero1 = null
            if pid == 0 then
                set ep = Player(1)
            else
                set ep = Player(0)
            endif
            set g = CreateGroup()
            call GroupEnumUnitsOfPlayer(g, p, null)
            loop
                set u = FirstOfGroup(g)
                exitwhen u == null
                call GroupRemoveUnit(g, u)
                if not IsUnitType(u, UNIT_TYPE_DEAD) and IsUnitType(u, UNIT_TYPE_HERO) then
                    set heroCount = heroCount + 1
                    if hero0 == null then
                        set hero0 = u
                    elseif hero1 == null then
                        set hero1 = u
                    endif
                endif
            endloop
            call DestroyGroup(g)
            set g = null
            if hero0 != null then
                set udg_esc_Cooldown0 = Trig_AIML_Escape_Hero(hero0, ep, udg_esc_Cooldown0, 0)
            endif
            if hero1 != null then
                set udg_esc_Cooldown1 = Trig_AIML_Escape_Hero(hero1, ep, udg_esc_Cooldown1, 1)
            endif
            set hero0 = null
            set hero1 = null
        endif
        set pid = pid + 1
    endloop
    set udg_esc_DbgTick = udg_esc_DbgTick - 1
    if udg_esc_DbgTick <= 0 then
        set udg_esc_DbgTick = 4
    endif
endfunction

function Trig_AIML_EscapeToggle takes nothing returns nothing
    set udg_aiml_Round1Mode = 2
    set udg_aiml_Round1Pref = 2
    set udg_aiml_EscapeMode = true
    call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[AIML] Round 1 mode: ESCAPE|r")
endfunction


function Trig_AIML_EscapeInit takes nothing returns nothing
    local trigger t
    call Trig_AIML_TreeGridInit()
    set t = CreateTrigger()
    call TriggerRegisterPlayerChatEvent(t, Player(0), "-escape", true)
    call TriggerRegisterPlayerChatEvent(t, Player(1), "-escape", true)
    call TriggerAddAction(t, function Trig_AIML_EscapeToggle)

    set t = null
    set t = CreateTrigger()
    call TriggerRegisterTimerEvent(t, 0.50, true)
    call TriggerAddAction(t, function Trig_AIML_EscapeTick)
    set t = null
endfunction
"""


def main():
    if len(sys.argv) < 3:
        print("Usage: inject_ai_escape.py <war3map.j> <war3map.doo>")
        sys.exit(1)

    path = sys.argv[1]
    doo_path = sys.argv[2]
    with open(path, "rb") as f:
        raw = f.read()
    nl = "\r\n" if b"\r\n" in raw[:4096] else "\n"
    src = raw.decode("utf-8")

    if "function Trig_AIML_EscapeTick" in src:
        print("[ESCAPE] already injected, skipping")
        return

    # --- Generate tree grid from doo ---
    from _escape_grid import read_trees_from_doo, build_grid, gen_grid_init_jass
    trees = read_trees_from_doo(doo_path)
    grid_cells = build_grid(trees)
    grid_init_jass_code = gen_grid_init_jass(grid_cells)
    print(f"[ESCAPE] {len(trees)} trees, {len(grid_cells)} grid cells")

    # 1) globals
    eg = "endglobals" + nl
    if eg not in src:
        raise SystemExit("ERROR: 'endglobals' not found")
    idx = src.find(eg)
    src = src[:idx] + ESCAPE_GLOBALS.replace("\n", nl) + src[idx:]
    print("[ESCAPE] inserted globals")

    # 2) functions before SurroundTick
    marker = "function Trig_AIML_SurroundTick"
    if marker not in src:
        marker = "function Trig_AIML_SalvoTick takes nothing returns nothing"
    if marker not in src:
        raise SystemExit("ERROR: SurroundTick/SalvoTick not found")
    idx = src.find(marker)
    esc_fn = ESCAPE_FUNCTIONS.replace("__GRID_INIT_PLACEHOLDER__", grid_init_jass_code)
    src = src[:idx] + esc_fn.replace("\n", nl) + nl + src[idx:]
    print("[ESCAPE] inserted functions")

    # 3) EscapeInit call in SurroundInit
    init_marker = "call TriggerAddAction(t3, function Trig_AIML_SurroundTimerTick)"
    if init_marker not in src:
        # Fallback: SalvoInit
        init_marker2 = "function Trig_AIML_SalvoInit takes nothing returns nothing"
        if init_marker2 in src:
            init_start = src.find(init_marker2)
            init_end = src.find("endfunction", init_start + 10)
            src = src[:init_end] + f"    call Trig_AIML_EscapeInit(){nl}" + src[init_end:]
        else:
            print("WARN: no init anchor found")
    else:
        idx_init = src.find(init_marker)
        init_end = src.find("endfunction", idx_init)
        src = src[:init_end] + f"    call Trig_AIML_EscapeInit(){nl}" + src[init_end:]
    print("[ESCAPE] registered EscapeInit")

    # 4) Patch Combat_AI guard to include escape mode (Round1Mode>=1)
    old_guard = "udg_aiml_CreepMode >= 1 or udg_aiml_Round1Mode == 1"
    new_guard = "udg_aiml_CreepMode >= 1 or udg_aiml_Round1Mode >= 1"
    if old_guard in src:
        src = src.replace(old_guard, new_guard)
        print("[ESCAPE] patched Combat_AI guard for escape mode")

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[ESCAPE] injected into {path}")


if __name__ == "__main__":
    main()
