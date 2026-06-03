#!/usr/bin/env python3
"""
inject_aiml_enhance.py - Enhance V18 base with:
  1. Far Seer chain lightning (smart targeting: hero<100HP > lowest HP unit)
  2. Skill build fixes (TC=War Stomp only, Far Seer=2CL+1Wolf, Shadow Hunter=Hex+HW)
  3. -debug chat command toggle
  4. Debug output: salvo target name display
  5. Hook SalvoInit into main()

Does NOT include kite/retreat logic.
"""

import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: inject_aiml_enhance.py <war3map.j>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    nl = "\r\n" if "\r\n" in src else "\n"

    # --- 1) Add debug global ---
    marker = "group   udg_aiml_SalvoEnemyG"
    idx = src.find(marker)
    if idx == -1:
        # Try another marker near AIML globals
        marker = "real    udg_aiml_SalvoMapRange"
        idx = src.find(marker)
    if idx == -1:
        print("ERROR: cannot find AIML globals")
        sys.exit(1)
    eol = src.index(nl, idx)
    debug_global = "    // [ENH] Debug mode" + nl + "    boolean udg_aiml_DebugMode = false"
    src = src[:eol + len(nl)] + debug_global + nl + src[eol + len(nl):]
    print("inserted debug global")

    # --- 2) Add debug output to IssueAttackCB (show target name) ---
    # Find the line where target is used
    old_issue = '    call IssueTargetOrder(u, "smart", target)'
    new_issue = ('    call IssueTargetOrder(u, "smart", target)' + nl +
                 '    // [ENH] Debug: show salvo target (only first unit in group)' + nl +
                 '    if udg_aiml_DebugMode and u == udg_aiml_DebugFirstUnit then' + nl +
                 '        call DisplayTextToForce(GetPlayersAll(), "[SALVO] -> " + GetUnitName(target) + " HP=" + R2S(GetUnitState(target, UNIT_STATE_LIFE)))' + nl +
                 '    endif')
    if old_issue in src:
        src = src.replace(old_issue, new_issue, 1)
        print("added debug output to IssueAttackCB")
    else:
        print("WARNING: could not find IssueTargetOrder in IssueAttackCB")

    # Add DebugFirstUnit global and set it before ForGroup
    # Find "call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_IssueAttackCB)"
    fg_line = "    call ForGroup(udg_aiml_SalvoRangedG, function Trig_AIML_IssueAttackCB)"
    fg_idx = src.find(fg_line)
    if fg_idx != -1:
        # Add DebugFirstUnit assignment before ForGroup
        debug_first = ("    // [ENH] Track first unit for debug display" + nl +
                       "    set udg_aiml_DebugFirstUnit = FirstOfGroup(udg_aiml_SalvoRangedG)" + nl)
        src = src[:fg_idx] + debug_first + src[fg_idx:]
        print("added DebugFirstUnit tracking")

    # Add the global variable declaration
    debug_global2 = "    unit    udg_aiml_DebugFirstUnit = null"
    # Insert after DebugMode global
    dm_idx = src.find("boolean udg_aiml_DebugMode = false")
    if dm_idx != -1:
        dm_eol = src.index(nl, dm_idx)
        src = src[:dm_eol + len(nl)] + debug_global2 + nl + src[dm_eol + len(nl):]
        print("added DebugFirstUnit global")

    # --- 3) Add Far Seer smart chain lightning function ---
    fs_func = """
// [ENH] Far Seer smart chain lightning
// Priority: enemy hero < 100 HP, else lowest HP enemy unit in 700 range
function Trig_AIML_FarSeerCL takes unit fs returns nothing
    local group eg
    local unit u
    local unit picked = null
    local real lowestHP = 99999.0
    local real hp
    if fs == null then
        return
    endif
    if IsUnitType(fs, UNIT_TYPE_DEAD) then
        return
    endif
    if GetUnitTypeId(fs) != 'Ofar' then
        return
    endif
    // Check mana (chain lightning costs 120)
    if GetUnitState(fs, UNIT_STATE_MANA) < 120.0 then
        return
    endif
    // Search enemies in 700 range
    set eg = CreateGroup()
    call GroupEnumUnitsInRange(eg, GetUnitX(fs), GetUnitY(fs), 700.0, null)
    set u = FirstOfGroup(eg)
    loop
        exitwhen u == null
        if not IsUnitType(u, UNIT_TYPE_DEAD) and not IsUnitAlly(u, GetOwningPlayer(fs)) and GetOwningPlayer(u) != Player(PLAYER_NEUTRAL_PASSIVE) then
            // Priority 1: enemy hero < 100 HP
            if IsUnitType(u, UNIT_TYPE_HERO) and GetUnitState(u, UNIT_STATE_LIFE) < 100.0 then
                set picked = u
                call DestroyGroup(eg)
                set eg = null
                call IssueTargetOrder(fs, "chainlightning", picked)
                if udg_aiml_DebugMode then
                    call DisplayTextToForce(GetPlayersAll(), "[ENH] FS CL -> " + GetUnitName(picked) + " HP=" + R2S(GetUnitState(picked, UNIT_STATE_LIFE)))
                endif
                set picked = null
                return
            endif
            // Track lowest HP for priority 2
            set hp = GetUnitState(u, UNIT_STATE_LIFE)
            if hp < lowestHP and hp > 0 then
                set lowestHP = hp
                set picked = u
            endif
        endif
        call GroupRemoveUnit(eg, u)
        set u = FirstOfGroup(eg)
    endloop
    call DestroyGroup(eg)
    set eg = null
    if picked != null then
        call IssueTargetOrder(fs, "chainlightning", picked)
        if udg_aiml_DebugMode then
            call DisplayTextToForce(GetPlayersAll(), "[ENH] FS CL -> " + GetUnitName(picked) + " HP=" + R2S(lowestHP))
        endif
    endif
    set picked = null
endfunction

"""
    # Insert before IssueAttackCB
    iac_marker = "function Trig_AIML_IssueAttackCB takes nothing returns nothing"
    iac_idx = src.find(iac_marker)
    if iac_idx != -1:
        src = src[:iac_idx] + fs_func.replace("\n", nl) + src[iac_idx:]
        print("added FarSeerCL function")

    # --- 4) Call FarSeerCL in SalvoForPlayer after picking target ---
    # Insert after "set udg_aiml_FocusTarget1 = picked" or "set udg_aiml_FocusTarget2 = picked"
    # Actually call it for all Far Seers every tick, right before ForGroup
    # Find the DebugFirstUnit line we just added and insert after it
    debug_first_line = "    set udg_aiml_DebugFirstUnit = FirstOfGroup(udg_aiml_SalvoRangedG)"
    df_idx = src.find(debug_first_line)
    if df_idx != -1:
        fs_call = ("    // [ENH] Far Seer smart chain lightning every tick" + nl +
                   "    call Trig_AIML_FarSeerCL(GroupPickRandomUnit(GetUnitsOfPlayerAndTypeId(udg_aiml_SalvoOwnerPlayer, 'Ofar')))" + nl)
        src = src[:df_idx] + fs_call + src[df_idx:]
        print("hooked FarSeerCL call into SalvoForPlayer")

    # --- 5) Hook SalvoInit into main() ---
    if "call Trig_AIML_SalvoInit()" not in src:
        main_marker = "call RunInitializationTriggers(  )"
        idx_main = src.find(main_marker)
        if idx_main != -1:
            eol_main = src.index(nl, idx_main)
            src = src[:eol_main + len(nl)] + "    call Trig_AIML_SalvoInit()" + nl + src[eol_main + len(nl):]
            print("hooked Trig_AIML_SalvoInit() into main()")

    # --- 6) Add -debug chat command ---
    debug_func = nl + "// [ENH] Debug toggle via -debug command" + nl
    debug_func += "function Trig_AIML_DebugToggle takes nothing returns nothing" + nl
    debug_func += "    if udg_aiml_DebugMode then" + nl
    debug_func += "        set udg_aiml_DebugMode = false" + nl
    debug_func += '        call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[AIML] Debug OFF|r")' + nl
    debug_func += "    else" + nl
    debug_func += "        set udg_aiml_DebugMode = true" + nl
    debug_func += '        call DisplayTextToForce(GetPlayersAll(), "|cffff0000[AIML] Debug ON|r")' + nl
    debug_func += "    endif" + nl
    debug_func += "endfunction" + nl + nl
    debug_func += "function Trig_AIML_DebugInit takes nothing returns nothing" + nl
    debug_func += "    local trigger t = CreateTrigger()" + nl
    debug_func += '    call TriggerRegisterPlayerChatEvent(t, Player(0), "-debug", true)' + nl
    debug_func += '    call TriggerRegisterPlayerChatEvent(t, Player(1), "-debug", true)' + nl
    debug_func += "    call TriggerAddAction(t, function Trig_AIML_DebugToggle)" + nl
    debug_func += "endfunction" + nl

    main_func_marker = "function main takes nothing returns nothing"
    idx_mf = src.find(main_func_marker)
    if idx_mf != -1 and "Trig_AIML_DebugToggle" not in src:
        src = src[:idx_mf] + debug_func.replace("\n", nl) + nl + src[idx_mf:]
        print("added -debug chat command")

    # Hook DebugInit into main
    if "call Trig_AIML_DebugInit()" not in src:
        si_call = "    call Trig_AIML_SalvoInit()"
        si_idx = src.find(si_call)
        if si_idx != -1:
            si_eol = src.index(nl, si_idx)
            src = src[:si_eol + len(nl)] + "    call Trig_AIML_DebugInit()" + nl + src[si_eol + len(nl):]
            print("hooked DebugInit into main()")

    # --- 7) Skill build fixes ---
    # TC: AOsw (Shockwave) -> AOws (War Stomp)
    count_aosw = src.count("'AOsw'")
    src = src.replace("'AOsw'", "'AOws'")
    if count_aosw > 0:
        print(f"TC: replaced {count_aosw} AOsw(Shockwave) with AOws(War Stomp)")

    # Far Seer skill build: 1Wolf, 2CL, 3CL (then Wolf, CL, EQ)
    # Original in ComputerSkill1: AOsf AOcl AOsf AOcl AOsf AOcl AOeq
    # Target:                     AOfs AOcl AOcl AOfs AOcl AOcl AOeq
    old_fs_skill = ("    call SelectHeroSkill( GetLastCreatedUnit(), 'AOsf' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOsf' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOsf' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOeq' )")
    new_fs_skill = ("    call SelectHeroSkill( GetLastCreatedUnit(), 'AOfs' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOfs' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOeq' )")
    count_fs = 0
    while old_fs_skill in src:
        src = src.replace(old_fs_skill, new_fs_skill, 1)
        count_fs += 1
    if count_fs > 0:
        print(f"Far Seer: fixed {count_fs} skill builds (1Wolf 2CL 3CL 4Wolf 5CL 6CL 7EQ)")
    else:
        print("WARNING: Far Seer skill sequence not found")

    # Shadow Hunter: fix ComputerSkill2 (add Hex)
    old_sh = ("    call SelectHeroSkill( GetLastCreatedUnit(), 'AOws' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOws' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOvd' )")
    new_sh = ("    call SelectHeroSkill( GetLastCreatedUnit(), 'AOws' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhx' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhx' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
              "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOvd' )")
    if old_sh in src:
        src = src.replace(old_sh, new_sh, 1)
        print("Shadow Hunter: fixed ComputerSkill2 (added Hex)")

    # --- 8) Enhance last-hit: approach creeps with HP 100-200 ---
    # Add a new condition function for HP <= 200 (approach range)
    # And modify Func004A/005A/006A to first try approaching HP 100-200 creeps
    approach_cond_p1 = nl + "function Trig_AIML_CreepApproach_Cond takes nothing returns boolean" + nl
    approach_cond_p1 += "    return ( GetUnitStateSwap(UNIT_STATE_LIFE, GetFilterUnit()) <= 200.00 )" + nl
    approach_cond_p1 += "endfunction" + nl

    # Insert before Func004A
    func004a_marker = "function Trig_Computer1Combat_AI_Func004A takes nothing returns nothing"
    idx_f4 = src.find(func004a_marker)
    if idx_f4 != -1 and "Trig_AIML_CreepApproach_Cond" not in src:
        src = src[:idx_f4] + approach_cond_p1.replace("\n", nl) + nl + src[idx_f4:]
        print("added CreepApproach_Cond function")

    # Now enhance Func004A (Archmage): approach HP 100-200, attack HP <= 125
    old_f4a = """function Trig_Computer1Combat_AI_Func004A takes nothing returns nothing
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer1Combat_AI_Func004Func001003001002))) )
endfunction"""
    new_f4a = """function Trig_Computer1Combat_AI_Func004A takes nothing returns nothing
    // [ENH] Approach creeps HP 100-200, attack creeps HP <= 125
    call IssueTargetOrderBJ( GetEnumUnit(), "smart", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_AIML_CreepApproach_Cond))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer1Combat_AI_Func004Func001003001002))) )
endfunction"""
    if old_f4a.replace("\n", nl) in src:
        src = src.replace(old_f4a.replace("\n", nl), new_f4a.replace("\n", nl), 1)
        print("enhanced P(0) Func004A (Archmage) with approach")

    # Func006A (Keeper): same enhancement
    old_f6a = """function Trig_Computer1Combat_AI_Func006A takes nothing returns nothing
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer1Combat_AI_Func006Func001003001002))) )
endfunction"""
    new_f6a = """function Trig_Computer1Combat_AI_Func006A takes nothing returns nothing
    // [ENH] Approach creeps HP 100-200, attack creeps HP <= 125
    call IssueTargetOrderBJ( GetEnumUnit(), "smart", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_AIML_CreepApproach_Cond))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer1Combat_AI_Func006Func001003001002))) )
endfunction"""
    if old_f6a.replace("\n", nl) in src:
        src = src.replace(old_f6a.replace("\n", nl), new_f6a.replace("\n", nl), 1)
        print("enhanced P(0) Func006A (Keeper) with approach")

    # Player 2 versions
    old_f4a_p2 = """function Trig_Computer2Combat_AI_Func004A takes nothing returns nothing
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer2Combat_AI_Func004Func001003001002))) )
endfunction"""
    new_f4a_p2 = """function Trig_Computer2Combat_AI_Func004A takes nothing returns nothing
    // [ENH] Approach creeps HP 100-200, attack creeps HP <= 125
    call IssueTargetOrderBJ( GetEnumUnit(), "smart", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_AIML_CreepApproach_Cond))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer2Combat_AI_Func004Func001003001002))) )
endfunction"""
    if old_f4a_p2.replace("\n", nl) in src:
        src = src.replace(old_f4a_p2.replace("\n", nl), new_f4a_p2.replace("\n", nl), 1)
        print("enhanced P(1) Func004A (Archmage) with approach")

    old_f6a_p2 = """function Trig_Computer2Combat_AI_Func006A takes nothing returns nothing
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer2Combat_AI_Func006Func001003001002))) )
endfunction"""
    new_f6a_p2 = """function Trig_Computer2Combat_AI_Func006A takes nothing returns nothing
    // [ENH] Approach creeps HP 100-200, attack creeps HP <= 125
    call IssueTargetOrderBJ( GetEnumUnit(), "smart", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_AIML_CreepApproach_Cond))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer2Combat_AI_Func006Func001003001002))) )
endfunction"""
    if old_f6a_p2.replace("\n", nl) in src:
        src = src.replace(old_f6a_p2.replace("\n", nl), new_f6a_p2.replace("\n", nl), 1)
        print("enhanced P(1) Func006A (Keeper) with approach")

    # --- 9) Add chainlightning to Far Seer Func005A (original combat AI) ---
    old_p1 = """function Trig_Computer1Combat_AI_Func005A takes nothing returns nothing
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer1Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(1), Condition(function Trig_Computer1Combat_AI_Func005Func002003001002))) )
endfunction"""
    new_p1 = """function Trig_Computer1Combat_AI_Func005A takes nothing returns nothing
    // [ENH] Far Seer: chain lightning priority, then attack
    call IssueTargetOrderBJ( GetEnumUnit(), "chainlightning", GroupPickRandomUnit(GetUnitsOfPlayerAll(Player(1))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer1Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(1), Condition(function Trig_Computer1Combat_AI_Func005Func002003001002))) )
endfunction"""
    if old_p1.replace("\n", nl) in src:
        src = src.replace(old_p1.replace("\n", nl), new_p1.replace("\n", nl), 1)
        print("added chainlightning to P(0) Far Seer Func005A")

    old_p2 = """function Trig_Computer2Combat_AI_Func005A takes nothing returns nothing
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer2Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(0), Condition(function Trig_Computer2Combat_AI_Func005Func002003001002))) )
endfunction"""
    new_p2 = """function Trig_Computer2Combat_AI_Func005A takes nothing returns nothing
    // [ENH] Far Seer: chain lightning priority, then attack
    call IssueTargetOrderBJ( GetEnumUnit(), "chainlightning", GroupPickRandomUnit(GetUnitsOfPlayerAll(Player(0))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer2Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(0), Condition(function Trig_Computer2Combat_AI_Func005Func002003001002))) )
endfunction"""
    if old_p2.replace("\n", nl) in src:
        src = src.replace(old_p2.replace("\n", nl), new_p2.replace("\n", nl), 1)
        print("added chainlightning to P(1) Far Seer Func005A")

    # --- Write output ---
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"Enhancement injected into {path}")


if __name__ == "__main__":
    main()
