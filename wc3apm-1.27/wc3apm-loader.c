// wc3apm-loader.c — WC3 APM Overlay Loader
// Build: windres wc3apm-loader.rc -o wc3apm-loader.res --output-format=coff
//        gcc -o wc3apm.exe wc3apm-loader.c wc3apm-loader.res -m32 -O2
//   (or without icon: gcc -o wc3apm.exe wc3apm-loader.c -m32 -O2)
// Usage: double-click or ./wc3apm.exe [path\to\wc3apm.dll]

#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static void pause_exit(int code) {
    printf("\n");
    system("pause");
    exit(code);
}

static DWORD findPid(const char* name) {
    HANDLE s = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (s == INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32 pe = { .dwSize = sizeof(pe) };
    DWORD pid = 0;
    if (Process32First(s, &pe)) do {
        if (_stricmp(pe.szExeFile, name) == 0) { pid = pe.th32ProcessID; break; }
    } while (Process32Next(s, &pe));
    CloseHandle(s);
    return pid;
}

static BOOL inject(DWORD pid, const char* dll) {
    HANDLE h = OpenProcess(PROCESS_ALL_ACCESS, 0, pid);
    if (!h) {
        printf("OpenProcess failed (error %lu). Run as Administrator!\n", GetLastError());
        return 0;
    }
    SIZE_T n = strlen(dll)+1;
    void* rp = VirtualAllocEx(h, NULL, n, MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE);
    if (!rp) { printf("VirtualAllocEx failed\n"); CloseHandle(h); return 0; }
    WriteProcessMemory(h, rp, dll, n, NULL);
    FARPROC ll = GetProcAddress(GetModuleHandleA("kernel32.dll"), "LoadLibraryA");
    HANDLE t = CreateRemoteThread(h, NULL, 0, (LPTHREAD_START_ROUTINE)ll, rp, 0, NULL);
    if (!t) {
        printf("CreateRemoteThread failed (error %lu)\n", GetLastError());
        VirtualFreeEx(h,rp,0,MEM_RELEASE); CloseHandle(h); return 0;
    }
    WaitForSingleObject(t, 10000);
    DWORD exitCode = 0;
    GetExitCodeThread(t, &exitCode);
    CloseHandle(t); VirtualFreeEx(h,rp,0,MEM_RELEASE); CloseHandle(h);
    if (!exitCode) { printf("LoadLibrary failed in remote process. Check DLL path.\n"); return 0; }
    return 1;
}

int main(int argc, char* argv[]) {
    // Ensure console window stays visible
    SetConsoleTitleA("WC3 APM Loader");
    printf("=== WC3 APM Loader ===\n\n");

    char dll[MAX_PATH] = {};
    if (argc > 1) {
        GetFullPathNameA(argv[1], MAX_PATH, dll, NULL);
    } else {
        GetModuleFileNameA(NULL, dll, MAX_PATH);
        char* p = strrchr(dll, '\\');
        if (p) strcpy(p+1, "wc3apm.dll");
        else strcpy(dll, "wc3apm.dll");
    }

    printf("DLL: %s\n", dll);
    if (GetFileAttributesA(dll) == INVALID_FILE_ATTRIBUTES) {
        printf("ERROR: DLL not found!\n");
        printf("Put wc3apm.dll in the same folder as wc3apm.exe\n");
        pause_exit(1);
    }

    DWORD pid = findPid("war3.exe");
    if (!pid) {
        printf("war3.exe not running.\n");
        printf("Waiting for game to start (launch WC3 now)...\n");
        int dots = 0;
        while (!pid) {
            Sleep(1000);
            pid = findPid("war3.exe");
            printf(".");
            if (++dots % 30 == 0) printf("\n");
        }
        printf("\nwar3.exe detected! Waiting 3s for initialization...\n");
        Sleep(3000);
    }

    printf("Target PID: %lu\n", pid);
    printf("Injecting...\n");

    if (inject(pid, dll)) {
        printf("\n>>> SUCCESS! APM overlay is now active. <<<\n");
    } else {
        printf("\n>>> INJECTION FAILED <<<\n");
        printf("Try: right-click wc3apm.exe -> Run as Administrator\n");
    }

    pause_exit(0);
    return 0;
}
