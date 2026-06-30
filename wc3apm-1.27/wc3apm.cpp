// wc3apm.cpp: Transparent overlay window for WC3 1.27 APM display
//
// No D3D9/OpenGL hooks. Creates a layered topmost transparent window
// that sits on top of the game and displays APM info.
// Input hooks run in overlay thread (has message pump) so callbacks fire.
//
// Build (MinGW32):
//   g++ -shared -o wc3apm.dll wc3apm.cpp -lgdi32 -O2 -static-libgcc -static-libstdc++

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstring>

// ── Debug log (disabled by default, set g_debug=true to enable) ─────────────

static bool g_debug = false;

static void Log(const char* fmt, ...) {
    if (!g_debug) return;
    char buf[512];
    va_list ap; va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    OutputDebugStringA(buf);
    FILE* f = fopen("D:\\wc3apm_log.txt", "a");
    if (f) { fprintf(f, "%s", buf); fclose(f); }
}

// ── Config ─────────────────────────────────────────────────────────────────

static const int  APM_WIN  = 60;
static const int  OVL_W    = 900;
static const int  OVL_H    = 175;
static const int  FONT_H   = 62;

// ── Input Tracking ─────────────────────────────────────────────────────────

static volatile long g_keys = 0, g_clicks = 0, g_total = 0;
static volatile DWORD g_start = 0;
static volatile bool g_chat = false;
static volatile bool g_ingame = false;  // only count APM when in-game
static HWND g_gameWnd = NULL;

// Check if WC3 game window is in foreground (not menu/login)
static bool isGameActive() {
    if (!g_gameWnd) {
        g_gameWnd = FindWindowA("Warcraft III", NULL);
        if (!g_gameWnd) g_gameWnd = FindWindowA(NULL, "Warcraft III");
    }
    return g_gameWnd && GetForegroundWindow() == g_gameWnd;
}

struct Ev { DWORD t; };
static const int MAXEV = 8192;
static Ev g_ev[MAXEV];
static volatile long g_eh = 0, g_et = 0;
static CRITICAL_SECTION g_cs;

static void rec() {
    DWORD now = GetTickCount();
    if (!g_start) InterlockedCompareExchange((volatile LONG*)&g_start, now, 0);
    InterlockedIncrement(&g_total);
    EnterCriticalSection(&g_cs);
    long h = g_eh;
    g_ev[h % MAXEV].t = now;
    g_eh = (h + 1) % MAXEV;
    DWORD cut = now - APM_WIN * 1000;
    while (g_eh != g_et && g_ev[g_et].t < cut)
        g_et = (g_et + 1) % MAXEV;
    LeaveCriticalSection(&g_cs);
}

static HHOOK g_hkb = NULL, g_hms = NULL;

LRESULT CALLBACK KB(int n, WPARAM w, LPARAM l) {
    if (n == HC_ACTION && w == WM_KEYDOWN && isGameActive()) {
        DWORD vk = ((KBDLLHOOKSTRUCT*)l)->vkCode;
        if (vk == VK_RETURN) { g_chat = !g_chat; InterlockedIncrement(&g_keys); rec(); }
        else if (!g_chat) { InterlockedIncrement(&g_keys); rec(); }
    }
    return CallNextHookEx(g_hkb, n, w, l);
}

LRESULT CALLBACK MS(int n, WPARAM w, LPARAM l) {
    if (n == HC_ACTION && isGameActive() &&
        (w == WM_LBUTTONDOWN || w == WM_RBUTTONDOWN || w == WM_MBUTTONDOWN)) {
        InterlockedIncrement(&g_clicks); rec();
    }
    return CallNextHookEx(g_hms, n, w, l);
}

// ── APM ─────────────────────────────────────────────────────────────────────

static int apmRolling() {
    DWORD now = GetTickCount();
    DWORD elapsed = g_start ? (now - g_start) / 1000 : 0;
    if (elapsed < 1) return 0;
    int win = (int)elapsed < APM_WIN ? (int)elapsed : APM_WIN;
    DWORD cut = now - win * 1000;
    int c = 0;
    EnterCriticalSection(&g_cs);
    for (long i = g_et; i != g_eh; i = (i+1) % MAXEV)
        if (g_ev[i].t >= cut) c++;
    LeaveCriticalSection(&g_cs);
    return c * 60 / win;
}

static int apmOverall() {
    DWORD s = g_start;
    if (!s) return 0;
    DWORD el = GetTickCount() - s;
    return el < 1000 ? 0 : (int)((double)g_total / (el / 60000.0));
}

// ── Overlay Window ─────────────────────────────────────────────────────────

static const wchar_t* WND_CLASS = L"WC3APMOverlay";
static HWND g_hwnd = NULL;
static HFONT g_font = NULL;
static bool g_running = true;

static HFONT mkFont() {
    if (g_font) DeleteObject(g_font);
    g_font = CreateFontA(-FONT_H, 0, 0, 0, FW_BOLD, 0, 0, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        CLEARTYPE_QUALITY, DEFAULT_PITCH|FF_DONTCARE, "Consolas");
    return g_font;
}

static void PaintOverlay(HDC hdc) {
    RECT rc = {0, 0, OVL_W, OVL_H};

    // Semi-transparent dark background
    HBRUSH bg = CreateSolidBrush(RGB(13, 17, 23));
    FillRect(hdc, &rc, bg);
    DeleteObject(bg);

    if (!g_font) mkFont();
    HFONT of = (HFONT)SelectObject(hdc, g_font);
    SetBkMode(hdc, TRANSPARENT);

    int a = apmRolling(), ao = apmOverall();
    DWORD el = g_start ? (GetTickCount()-g_start)/1000 : 0;

    COLORREF c;
    if      (a >= 200) c = RGB(255,107,107);
    else if (a >= 120) c = RGB(255,169,77);
    else if (a >= 60)  c = RGB(88,166,255);
    else               c = RGB(105,219,124);

    SetTextColor(hdc, c);
    char s1[64]; sprintf(s1, "%s APM: %d",
        a>=200?">>>":a>=120?" >>":a>=60?" >":" .", a);
    TextOutA(hdc, 8, 4, s1, (int)strlen(s1));

    SetTextColor(hdc, RGB(139,148,158));
    char s2[80]; sprintf(s2, "avg:%d K:%ld M:%ld %lus",
        ao, g_keys, g_clicks, el);
    TextOutA(hdc, 8, 4+FONT_H+4, s2, (int)strlen(s2));

    SelectObject(hdc, of);
}

static LRESULT CALLBACK WndProc(HWND hw, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_PAINT) {
        PAINTSTRUCT ps;
        HDC hdc = BeginPaint(hw, &ps);
        PaintOverlay(hdc);
        EndPaint(hw, &ps);
        return 0;
    }
    if (msg == WM_TIMER) {
        InvalidateRect(hw, NULL, FALSE);
        return 0;
    }
    if (msg == WM_DESTROY) {
        g_running = false;
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hw, msg, wp, lp);
}

static DWORD WINAPI OverlayThread(LPVOID) {
    // Install input hooks IN THIS THREAD so callbacks fire via our message pump
    g_hkb = SetWindowsHookExW(WH_KEYBOARD_LL, KB, GetModuleHandleW(NULL), 0);
    g_hms = SetWindowsHookExW(WH_MOUSE_LL, MS, GetModuleHandleW(NULL), 0);
    Log("[APM] Input hooks (overlay thread): kb=%p ms=%p\n", g_hkb, g_hms);

    // Wait for WC3 window to appear and be visible
    HWND hGame = NULL;
    for (int i = 0; i < 60; i++) {
        hGame = FindWindowA("Warcraft III", NULL);
        if (!hGame) hGame = FindWindowA(NULL, "Warcraft III");
        if (hGame && IsWindowVisible(hGame)) {
            RECT grc;
            if (GetWindowRect(hGame, &grc) && grc.left > -10000) break;
        }
        hGame = NULL;
        // Must pump messages so hook callbacks can fire even while waiting
        MSG tmp;
        while (PeekMessageW(&tmp, NULL, 0, 0, PM_REMOVE)) {
            TranslateMessage(&tmp);
            DispatchMessageW(&tmp);
        }
        Sleep(200);
    }
    Log("[APM] Game window: %p\n", (void*)hGame);

    // Register window class
    HINSTANCE hInst = GetModuleHandleW(NULL);
    WNDCLASSW wc = {};
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInst;
    wc.lpszClassName = WND_CLASS;
    RegisterClassW(&wc);

    // Get game window position (default fallback)
    RECT grc = {0, 0, 800, 600};
    if (hGame) GetWindowRect(hGame, &grc);

    // Create layered + transparent + topmost window (top center)
    int scrW = GetSystemMetrics(SM_CXSCREEN);
    int cx = scrW / 2 - OVL_W / 2;
    int cy = 10;
    g_hwnd = CreateWindowExW(
        WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
        WND_CLASS, L"WC3APM",
        WS_POPUP,
        cx, cy, OVL_W, OVL_H,
        NULL, NULL, hInst, NULL);

    if (!g_hwnd) {
        Log("[APM] CreateWindow failed: %d\n", GetLastError());
        return 0;
    }

    SetLayeredWindowAttributes(g_hwnd, 0, 220, LWA_ALPHA);
    ShowWindow(g_hwnd, SW_SHOWNA);

    // Timer to repaint every 200ms
    SetTimer(g_hwnd, 1, 200, NULL);

    Log("[APM] Overlay window created at (%d,%d) %dx%d\n",
        grc.left+10, grc.top+10, OVL_W, OVL_H);

    // Message loop - this is also where hook callbacks are dispatched
    MSG msg;
    while (g_running) {
        // Keep overlay topmost (necessary for fullscreen games)
        SetWindowPos(g_hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);

        // Process all messages (including hook callbacks)
        while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        Sleep(10); // fast enough for hook callbacks + reposition
    }

    KillTimer(g_hwnd, 1);
    if (g_hkb) UnhookWindowsHookEx(g_hkb);
    if (g_hms) UnhookWindowsHookEx(g_hms);
    DestroyWindow(g_hwnd);
    UnregisterClassW(WND_CLASS, hInst);
    return 0;
}

// ── DLL Entry ──────────────────────────────────────────────────────────────

static DWORD WINAPI go(LPVOID) {
    if (g_debug) DeleteFileA("D:\\wc3apm_log.txt");
    Log("[APM] DLL loaded (transparent overlay window version)\n");

    // Declare DPI awareness so font/window sizes are not scaled down
    typedef BOOL (WINAPI *SPDA)(void);
    HMODULE hUser = GetModuleHandleA("user32.dll");
    if (hUser) {
        SPDA fn = (SPDA)GetProcAddress(hUser, "SetProcessDPIAware");
        if (fn) fn();
    }

    Sleep(500);

    InitializeCriticalSectionAndSpinCount(&g_cs, 4000);
    mkFont();

    // Start overlay thread - it also runs input hooks (needs message pump)
    CreateThread(0, 0, OverlayThread, 0, 0, 0);

    Log("[APM] Init complete\n");
    return 0;
}

BOOL APIENTRY DllMain(HMODULE h, DWORD r, LPVOID) {
    if (r == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        CreateThread(0,0,go,0,0,0);
    } else if (r == DLL_PROCESS_DETACH) {
        g_running = false;
        if (g_hwnd) PostMessageW(g_hwnd, WM_CLOSE, 0, 0);
        if (g_font) { DeleteObject(g_font); g_font = NULL; }
        DeleteCriticalSection(&g_cs);
    }
    return TRUE;
}
