#!/usr/bin/env python3
"""
inject_debug.py - Inject -debug chat command for toggling AI debug prints.

Injects:
  - udg_aiml_DebugMode global
  - Trig_AIML_DebugToggle function
  - Trig_AIML_DebugInit function (registers -debug chat event for both players)
  - Hook DebugInit into main()
"""

import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: inject_debug.py <war3map.j>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    nl = "\r\n" if "\r\n" in src else "\n"

    # --- Need DebugMode global ---
    if "boolean udg_aiml_DebugMode" not in src:
        marker = "real    udg_aiml_SalvoMajorityRatio"
        idx = src.find(marker)
        if idx == -1:
            marker = "integer udg_aiml_SalvoFocusSlot2"
            idx = src.find(marker)
        if idx != -1:
            eol = src.index(nl, idx)
            src = src[:eol + len(nl)] + "    boolean udg_aiml_DebugMode = false" + nl + src[eol + len(nl):]
            print("added DebugMode global")

    # --- Add -debug command if not present ---
    if "Trig_AIML_DebugToggle" not in src:
        debug_func = nl + "// [DEBUG] Debug toggle" + nl
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

        # Insert before main()
        main_marker = "function main takes nothing returns nothing"
        idx_main = src.find(main_marker)
        if idx_main != -1:
            src = src[:idx_main] + debug_func.replace("\n", nl) + src[idx_main:]
            print("added DebugToggle + DebugInit functions")

        # Hook DebugInit into main()
        call_main_marker = "    call SetPlayerSlotAvailable"
        idx_hook = src.find(call_main_marker)
        if idx_hook == -1:
            call_main_marker = "    call InitBlizzard"
            idx_hook = src.find(call_main_marker)
        if idx_hook != -1:
            hook_code = "    call Trig_AIML_DebugInit()" + nl
            src = src[:idx_hook] + hook_code.replace("\n", nl) + src[idx_hook:]
            print("hooked DebugInit into main()")

    # --- Write output ---
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[DEBUG] Debug command injected into {path}")


if __name__ == "__main__":
    main()
