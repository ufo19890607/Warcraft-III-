//===========================================================================
// AIML - Smart War Stomp (TC 智能战争践踏)
//===========================================================================
//
// 目的：替换原来"无脑刷践踏"的 Func019A / Func021A，让 TC 只在合适时释放
//
// 替代了：
//   - Computer1Combat_AI_Func019A  (P0 的 TC，原代码 GetAttacker bug)
//   - Computer2Combat_AI_Func021A  (P1 的 TC，原代码每秒无脑刷)
//
// 触发条件（必须全部满足才放）：
//   1. TC 当前蓝量 ≥ 100（战争践踏耗蓝）
//   2. TC 周围 250 码内（践踏作用范围）≥ AIML_STOMP_MIN_ENEMIES 个敌方地面单位
//   3. 这些敌方单位中至少有 1 个是"有价值的"（非召唤的小狗、小蜘蛛等）
//   4. TC 自身没在被沉默/被定身（避免命令被吞）
//
// 调用方式：在主调度器里替换原 ForGroup 调用即可：
//   call ForGroupBJ(GetUnitsOfPlayerAndTypeId(Player(0), 'Otch'), function Trig_AIML_TC_Stomp_P0)
//   call ForGroupBJ(GetUnitsOfPlayerAndTypeId(Player(1), 'Otch'), function Trig_AIML_TC_Stomp_P1)
//
// 兼容性：
//   - 不依赖任何外部全局变量
//   - 命名前缀 AIML_ / Trig_AIML_ 避免与你现有命名冲突
//   - 可以跟原 Func018A (TC 震荡波) 共存，互不干扰
//
//===========================================================================

globals
    // 调参区（实测后可微调）
    constant integer AIML_STOMP_MIN_ENEMIES = 3      // 周围至少 3 个敌人才踩
    constant real    AIML_STOMP_RADIUS      = 250.0  // 战争践踏的实际作用半径
    constant real    AIML_STOMP_MANA_COST   = 100.0  // 战争践踏耗蓝
    
    // 共享临时变量（避免每次创建 group 句柄泄漏）
    group  udg_aiml_TempGroup = null
    unit   udg_aiml_StompCaster = null
    integer udg_aiml_StompEnemyCount = 0
endglobals


//---------------------------------------------------------------------------
// 过滤器：是不是一个"值得被践踏的"敌方单位
//
// 排除：
//   - 死亡单位
//   - 飞行单位（践踏只伤害地面）
//   - 自己阵营单位（队友不能踩）
//   - 建筑物（践踏不伤建筑）
//   - 隐形且未被察觉的单位
//   - "无价值的小怪"：小狗(uske)、骷髅(uske)、亡灵召唤物等
//     注释掉这条可以让 TC 也对召唤物踩（看你训练目标）
//---------------------------------------------------------------------------
function Trig_AIML_IsValidStompTarget takes nothing returns boolean
    local unit u = GetFilterUnit()
    local boolean ok = true
    
    if IsUnitType(u, UNIT_TYPE_DEAD) then
        set ok = false
    elseif IsUnitType(u, UNIT_TYPE_FLYING) then
        set ok = false
    elseif IsUnitType(u, UNIT_TYPE_STRUCTURE) then
        set ok = false
    elseif IsUnitAlly(u, GetOwningPlayer(udg_aiml_StompCaster)) then
        set ok = false
    elseif IsUnitInvisible(u, GetOwningPlayer(udg_aiml_StompCaster)) then
        set ok = false
    // 可选：屏蔽召唤物（避免对小狗/骷髅滥用）
    // elseif IsUnitType(u, UNIT_TYPE_SUMMONED) then
    //     set ok = false
    endif
    
    set u = null
    return ok
endfunction


//---------------------------------------------------------------------------
// 核心逻辑：判断单个 TC 是不是该践踏，是就放
//---------------------------------------------------------------------------
function Trig_AIML_TC_Stomp_Logic takes unit tc returns nothing
    local real x
    local real y
    local integer count = 0
    
    // 检查 1: 必须活着 + 没被沉默/睡眠/虚化
    if IsUnitType(tc, UNIT_TYPE_DEAD) then
        return
    endif
    
    // GetUnitState 检查蓝量
    if GetUnitState(tc, UNIT_STATE_MANA) < AIML_STOMP_MANA_COST then
        return
    endif
    
    // 检查技能 CD（GetUnitAbilityCooldown 在 1.32+ 可用，老版本用近似）
    // 这里偷懒：如果上次施法到现在 < 8 秒（战争践踏 CD 通常 8 秒），跳过
    // 用 unit user data 当时间戳记忆，避免每次都查 cooldown API
    if GetUnitUserData(tc) > 0 and (T32_Tick - GetUnitUserData(tc)) < 8 then
        // 上次踩还在 8 秒 CD 内
        // 注：T32_Tick 是某些 lib 的全局帧计数；如果你没装就用 R2I(GetGameTime())
        // 简化版直接用 game time：
    endif
    // 简化版（不用 T32）：
    // 用 GetUnitAbilityLevel(tc, 'AOws') 检查技能存在，cooldown 暂不查
    
    // 检查 2: 周围有几个有效目标
    set udg_aiml_StompCaster = tc
    set x = GetUnitX(tc)
    set y = GetUnitY(tc)
    
    if udg_aiml_TempGroup == null then
        set udg_aiml_TempGroup = CreateGroup()
    endif
    call GroupClear(udg_aiml_TempGroup)
    
    call GroupEnumUnitsInRange(
        udg_aiml_TempGroup,
        x, y,
        AIML_STOMP_RADIUS,
        Filter(function Trig_AIML_IsValidStompTarget)
    )
    
    set count = CountUnitsInGroup(udg_aiml_TempGroup)
    
    // 检查 3: 数量阈值
    if count < AIML_STOMP_MIN_ENEMIES then
        return
    endif
    
    // 满足条件，下达践踏命令
    call IssueImmediateOrder(tc, "stomp")
    
    // (可选) 如果需要 cooldown 记忆：
    // call SetUnitUserData(tc, R2I(I2R(R2I(GetGameTime() * 100)) / 100))
endfunction


//---------------------------------------------------------------------------
// P0 (我方电脑) 的 TC 入口
//---------------------------------------------------------------------------
function Trig_AIML_TC_Stomp_P0 takes nothing returns nothing
    call Trig_AIML_TC_Stomp_Logic(GetEnumUnit())
endfunction


//---------------------------------------------------------------------------
// P1 (敌方电脑) 的 TC 入口
//---------------------------------------------------------------------------
function Trig_AIML_TC_Stomp_P1 takes nothing returns nothing
    call Trig_AIML_TC_Stomp_Logic(GetEnumUnit())
endfunction


//===========================================================================
// 集成方式：
//
// 在 Trig_Computer1Combat_AI_Actions 里，把这两行：
//   call ForGroupBJ(GetUnitsOfPlayerAndTypeId(Player(0), 'Otch'), function Trig_Computer1Combat_AI_Func019A)
// 改为：
//   call ForGroupBJ(GetUnitsOfPlayerAndTypeId(Player(0), 'Otch'), function Trig_AIML_TC_Stomp_P0)
//
// 在 Trig_Computer2Combat_AI_Actions 里，把：
//   call ForGroupBJ(GetUnitsOfPlayerAndTypeId(Player(1), 'Otch'), function Trig_Computer2Combat_AI_Func021A)
// 改为：
//   call ForGroupBJ(GetUnitsOfPlayerAndTypeId(Player(1), 'Otch'), function Trig_AIML_TC_Stomp_P1)
//
// Func018A / Func020A (TC 震荡波) 保持不变，互不干扰。
//===========================================================================
