#!/usr/bin/env python3
"""
inject_hero_skills.py - Inject hero skill fixes ONLY (no kite/retreat).

Extracted from inject_aiml_kite.py, keeping only:
  7) Far Seer chain lightning in combat dispatch
  8) TC: War Stomp only (replace Shockwave)
  9) Far Seer skill build: wolves instead of Far Sight
  10) Shadow Hunter: add Hex to skill build
  11) Far Seer smart chain lightning function + hook into -debug
  + -debug command registration (if not already present)
  + Trig_AIML_SalvoInit hook into main() (needed for debug timer)
"""

import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: inject_hero_skills.py <war3map.j>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    nl = "\r\n" if "\r\n" in src else "\n"

    # --- Need DebugMode global ---
    if "boolean udg_aiml_DebugMode" not in src:
        # Add it after the last AIML global
        marker = "real    udg_aiml_SalvoMajorityRatio"
        idx = src.find(marker)
        if idx == -1:
            marker = "integer udg_aiml_SalvoFocusSlot2"
            idx = src.find(marker)
        if idx != -1:
            eol = src.index(nl, idx)
            src = src[:eol + len(nl)] + "    boolean udg_aiml_DebugMode = false" + nl + src[eol + len(nl):]
            print("added DebugMode global")

    # --- 7) Add chain lightning to Far Seer combat dispatch for both players ---
    old_p1_farseer = """function Trig_Computer1Combat_AI_Func005A takes nothing returns nothing
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer1Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(1), Condition(function Trig_Computer1Combat_AI_Func005Func002003001002))) )
endfunction"""
    new_p1_farseer = """function Trig_Computer1Combat_AI_Func005A takes nothing returns nothing
    // [HERO] Far Seer chain lightning on enemy
    call IssueTargetOrderBJ( GetEnumUnit(), "chainlightning", GroupPickRandomUnit(GetUnitsOfPlayerAll(Player(1))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer1Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(1), Condition(function Trig_Computer1Combat_AI_Func005Func002003001002))) )
endfunction"""
    if old_p1_farseer.replace("\n", nl) in src:
        src = src.replace(old_p1_farseer.replace("\n", nl), new_p1_farseer.replace("\n", nl), 1)
        print("added chainlightning to Player(0) Far Seer")

    old_p2_farseer = """function Trig_Computer2Combat_AI_Func005A takes nothing returns nothing
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer2Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(0), Condition(function Trig_Computer2Combat_AI_Func005Func002003001002))) )
endfunction"""
    new_p2_farseer = """function Trig_Computer2Combat_AI_Func005A takes nothing returns nothing
    // [HERO] Far Seer chain lightning on enemy
    call IssueTargetOrderBJ( GetEnumUnit(), "chainlightning", GroupPickRandomUnit(GetUnitsOfPlayerAll(Player(0))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(PLAYER_NEUTRAL_AGGRESSIVE), Condition(function Trig_Computer2Combat_AI_Func005Func001003001002))) )
    call IssueTargetOrderBJ( GetEnumUnit(), "attack", GroupPickRandomUnit(GetUnitsOfPlayerMatching(Player(0), Condition(function Trig_Computer2Combat_AI_Func005Func002003001002))) )
endfunction"""
    if old_p2_farseer.replace("\n", nl) in src:
        src = src.replace(old_p2_farseer.replace("\n", nl), new_p2_farseer.replace("\n", nl), 1)
        print("added chainlightning to Player(1) Far Seer")

    # --- 8) TC: replace Shockwave with War Stomp ---
    count_aosw = src.count("'AOsw'")
    src = src.replace("'AOsw'", "'AOws'")
    if count_aosw > 0:
        print(f"replaced {count_aosw} occurrences of AOsw(Shockwave) with AOws(War Stomp)")

    # --- 9) Far Seer: replace Far Sight with Feral Spirit ---
    count_aosf = src.count("'AOsf'")
    src = src.replace("'AOsf'", "'AOfs'")
    if count_aosf > 0:
        print(f"replaced {count_aosf} occurrences of AOsf(Far Sight) with AOfs(Feral Spirit)")

    # --- 9b) Far Seer skill build: 1=wolves, 2=chain, 3=chain ---
    # After step 9, AOsf became AOfs. Original pattern: AOfs,AOcl,AOfs,AOcl,AOfs,AOcl,AOeq
    # Desired: AOfs,AOcl,AOcl,AOfs,AOcl,AOfs,AOeq (1=wolf, 2=chain, 3=chain, 4=wolf, 5=chain, 6=wolf, 7=quake)
    old_fs_skill = ("    call SelectHeroSkill( GetLastCreatedUnit(), 'AOfs' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOfs' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOfs' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOeq' )")
    new_fs_skill = ("    call SelectHeroSkill( GetLastCreatedUnit(), 'AOfs' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOfs' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOcl' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOfs' )" + nl +
                    "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOeq' )")
    fs_count = src.count(old_fs_skill)
    if fs_count > 0:
        src = src.replace(old_fs_skill, new_fs_skill)
        print(f"fixed Far Seer skill build: 1=wolves,2=chain,3=chain ({fs_count} occurrences)")

    # --- 10) Shadow Hunter skill build: 1=hex, 2=heal, 3=heal ---
    # ComputerSkill1 original: AOhx,AOhw,AOhw,AOhx,AOhw,AOvd,AOhx
    # Already correct! 1=hex, 2=heal, 3=heal, 4=hex, 5=heal, 6=voodoo, 7=hex
    # No change needed for ComputerSkill1.

    # ComputerSkill2 shadow hunter: after step 8, AOsw became AOws
    # Original (post-step8): AOws,AOhw,AOhw,AOws,AOhw,AOvd,AOws
    # Desired: AOhx,AOhw,AOhw,AOhx,AOhw,AOvd,AOhx (1=hex, 2=heal, 3=heal)
    old_sh_skill2 = ("    call SelectHeroSkill( GetLastCreatedUnit(), 'AOws' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOws' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOvd' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOws' )")
    new_sh_skill2 = ("    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhx' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhx' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhw' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOvd' )" + nl +
                     "    call SelectHeroSkill( GetLastCreatedUnit(), 'AOhx' )")
    if old_sh_skill2 in src:
        src = src.replace(old_sh_skill2, new_sh_skill2, 1)
        print("fixed Shadow Hunter skill build in ComputerSkill2: 1=hex,2=heal,3=heal")

    # --- 11) Add -debug command if not present ---
    if "Trig_AIML_DebugToggle" not in src:
        # Add debug toggle function + init before endfunction of main or InitBlizzard
        debug_func = nl + "// [HERO] Debug toggle" + nl
        debug_func += "function Trig_AIML_DebugToggle takes nothing returns nothing" + nl
        debug_func += "    if udg_aiml_DebugMode then" + nl
        debug_func += "        set udg_aiml_DebugMode = false" + nl
        debug_func += '        call DisplayTextToForce(GetPlayersAll(), "|cff00ff00[AIML] Debug OFF|r")' + nl
        debug_func += "    else" + nl
        debug_func += "        set udg_aiml_DebugMode = true" + nl
        debug_func += '        call DisplayTextToForce(GetPlayersAll(), "|cffff0000[AIML] Debug ON|r")' + nl
        debug_func += "    endif" + nl
        debug_func += "endfunction" + nl
        debug_func += nl
        debug_func += "function Trig_AIML_DebugInit takes nothing returns nothing" + nl
        debug_func += "    local trigger t = CreateTrigger()" + nl
        debug_func += '    call TriggerRegisterPlayerChatEvent(t, Player(0), "-debug", true)' + nl
        debug_func += '    call TriggerRegisterPlayerChatEvent(t, Player(1), "-debug", true)' + nl
        debug_func += "    call TriggerAddAction(t, function Trig_AIML_DebugToggle)" + nl
        debug_func += "endfunction" + nl

        # Insert before main() function
        main_marker = "function main takes nothing returns nothing"
        idx_main = src.find(main_marker)
        if idx_main != -1:
            src = src[:idx_main] + debug_func.replace("\n", nl) + src[idx_main:]
            print("added DebugToggle + DebugInit functions")

        # Hook DebugInit into main()
        call_main_marker = "    call SetPlayerSlotAvailable"
        idx_hook = src.find(call_main_marker)
        if idx_hook == -1:
            # Try InitBlizzard call
            call_main_marker = "    call InitBlizzard"
            idx_hook = src.find(call_main_marker)
        if idx_hook != -1:
            hook_code = "    call Trig_AIML_DebugInit()" + nl
            src = src[:idx_hook] + hook_code.replace("\n", nl) + src[idx_hook:]
            print("hooked DebugInit into main()")

    # --- 12) Ensure SalvoInit is hooked into main() ---
    if "call Trig_AIML_SalvoInit()" not in src and "Trig_AIML_SalvoInit" in src:
        # Find insertion point in main()
        call_main_marker = "    call SetPlayerSlotAvailable"
        idx_hook = src.find(call_main_marker)
        if idx_hook == -1:
            call_main_marker = "    call InitBlizzard"
            idx_hook = src.find(call_main_marker)
        if idx_hook != -1:
            hook_code = "    call Trig_AIML_SalvoInit()" + nl
            src = src[:idx_hook] + hook_code.replace("\n", nl) + src[idx_hook:]
            print("hooked SalvoInit into main()")

    # --- Write output ---
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[HERO] Hero skills injected into {path}")


if __name__ == "__main__":
    main()
