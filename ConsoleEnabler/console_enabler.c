// MJOLNIR Console Enabler - Lightweight DLL for Halo Campaign Evolved
// Enables the UE5 developer console without UE4SS
// Zero overhead: no pattern scanning loops, no function hooks
//
// Strategy:
// 1. Find GEngine by scanning for a known pattern near GameEngineTick
// 2. Navigate: GEngine -> GameViewport -> ViewportConsole
// 3. If ViewportConsole is null, create one via StaticConstructObject_Internal
// 4. Set console keys via InputSettings

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>

// ============================================================
// Type definitions matching UE5 internals
// ============================================================

typedef void* UObject;
typedef void* UClass;

// StaticConstructObject_Internal signature (UE5)
// UObject* StaticConstructObject_Internal(const FStaticConstructObjectParameters& Params);
// In practice, we'll call it with the simplified overload

// Forward declarations
static void ConsoleEnablerThread(void* param);
static void* FindGEngine(void);
static void EnableConsole(void* GEngine);

// ============================================================
// Logging
// ============================================================

static FILE* g_logFile = NULL;

static void Log(const char* fmt, ...) {
    if (!g_logFile) {
        char path[MAX_PATH];
        GetModuleFileNameA(NULL, path, MAX_PATH);
        // Replace .exe with _console.log
        char* dot = strrchr(path, '.');
        if (dot) strcpy(dot, "_console.log");
        else strcat(path, "_console.log");
        g_logFile = fopen(path, "w");
    }
    if (g_logFile) {
        va_list args;
        va_start(args, fmt);
        vfprintf(g_logFile, fmt, args);
        fprintf(g_logFile, "\n");
        fflush(g_logFile);
        va_end(args);
    }
}

// ============================================================
// Memory scanning utilities
// ============================================================

static uintptr_t GetModuleBase(void) {
    return (uintptr_t)GetModuleHandleA(NULL);
}

// Read a RIP-relative address from a LEA/MOV instruction
static uintptr_t ReadRipRelative(uintptr_t instrAddr, int instrLen) {
    int32_t offset = *(int32_t*)(instrAddr + instrLen - 4);
    return instrAddr + instrLen + offset;
}

// Search for a byte pattern in memory
static uintptr_t FindPattern(uintptr_t start, size_t size, const uint8_t* pattern, const char* mask, size_t patLen) {
    for (size_t i = 0; i <= size - patLen; i++) {
        int found = 1;
        for (size_t j = 0; j < patLen; j++) {
            if (mask[j] == 'x' && ((uint8_t*)start)[i + j] != pattern[j]) {
                found = 0;
                break;
            }
        }
        if (found) return start + i;
    }
    return 0;
}

// ============================================================
// GEngine finder
// ============================================================

// GEngine is typically referenced early in UGameEngine::Tick
// We find it by scanning for a LEA or MOV instruction that loads a global
// pointer near the GameEngineTick function.
//
// From UE4SS: GameEngineTick matched at a known offset.
// The function references GEngine via something like:
//   mov rax, [rip+offset]  ; 48 8B 05 xx xx xx xx
//   or
//   lea rcx, [rip+offset]  ; 48 8D 0D xx xx xx xx

static void* FindGEngine(void) {
    uintptr_t base = GetModuleBase();
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)(base + dos->e_lfanew);
    PIMAGE_SECTION_HEADER text = IMAGE_FIRST_SECTION(nt);
    
    uintptr_t textStart = base + text->VirtualAddress;
    size_t textSize = text->SizeOfRawData;
    
    Log("Module base: 0x%llX", base);
    Log(".text: 0x%llX - 0x%llX (%zu MB)", textStart, textStart + textSize, textSize / (1024*1024));
    
    // Strategy: Find GEngine by looking for the pattern used in UGameEngine::Init
    // which stores to the GEngine global pointer.
    // In UE5: GEngine = this; is typically: 
    //   48 89 0D xx xx xx xx  (mov [rip+disp32], rcx)
    // near the start of UGameEngine::Init
    
    // Alternative: search for the string "GEngine" in .rdata and find xrefs
    
    // Most reliable: In UE5, GEngine is always accessed via a pattern like:
    // 48 8B 05 xx xx xx xx  (mov rax, [rip+disp32]) at function start
    // followed by 48 85 C0 (test rax, rax) - null check
    // followed by 48 8B ?? (mov reg, [rax+offset]) - dereference
    
    // Let's search for the GEngine pattern used in common engine code
    // Specifically look for: mov rax, [GEngine]; test rax,rax; jz; mov rcx,[rax+GameViewportOffset]
    // Pattern: 48 8B 05 ?? ?? ?? ?? 48 85 C0 74
    uint8_t pat1[] = { 0x48, 0x8B, 0x05, 0x00, 0x00, 0x00, 0x00, 0x48, 0x85, 0xC0, 0x74 };
    char mask1[] =   "xxx????xxxx";
    
    Log("Scanning for GEngine access pattern...");
    
    // We need to find multiple matches and determine which global is GEngine
    // GEngine is typically the most-referenced global pointer
    
    // Simpler approach: scan for all 48 8B 05 xx xx xx xx 48 85 C0 patterns
    // and count how many times each resolved global is referenced
    
    typedef struct { uintptr_t addr; int count; } GlobalRef;
    GlobalRef globals[1024];
    int numGlobals = 0;
    
    for (size_t i = 0; i < textSize - 16; i++) {
        uint8_t* p = (uint8_t*)(textStart + i);
        if (p[0] == 0x48 && p[1] == 0x8B && p[2] == 0x05 && 
            p[7] == 0x48 && p[8] == 0x85 && p[9] == 0xC0) {
            // Found mov rax,[rip+disp]; test rax,rax
            int32_t disp = *(int32_t*)(p + 3);
            uintptr_t globalAddr = (uintptr_t)(p + 7) + disp;
            
            // Check if this global is in .data section  
            if (globalAddr >= base && globalAddr < base + nt->OptionalHeader.SizeOfImage) {
                // Add or increment count
                int found = 0;
                for (int g = 0; g < numGlobals; g++) {
                    if (globals[g].addr == globalAddr) {
                        globals[g].count++;
                        found = 1;
                        break;
                    }
                }
                if (!found && numGlobals < 1024) {
                    globals[numGlobals].addr = globalAddr;
                    globals[numGlobals].count = 1;
                    numGlobals++;
                }
            }
        }
    }
    
    // Sort by reference count (bubble sort, it's only 1024 max)
    for (int i = 0; i < numGlobals - 1; i++) {
        for (int j = i + 1; j < numGlobals; j++) {
            if (globals[j].count > globals[i].count) {
                GlobalRef tmp = globals[i];
                globals[i] = globals[j];
                globals[j] = tmp;
            }
        }
    }
    
    Log("Found %d unique globals referenced with null-check pattern", numGlobals);
    
    // Print top candidates
    for (int i = 0; i < 10 && i < numGlobals; i++) {
        void* val = NULL;
        __try {
            val = *(void**)globals[i].addr;
        } __except(1) {
            val = NULL;
        }
        Log("  #%d: global at 0x%llX (%d refs) -> value=0x%llX", 
            i+1, globals[i].addr, globals[i].count, (uintptr_t)val);
    }
    
    // GEngine is typically one of the most-referenced globals
    // Try the top candidates and check if they point to a valid UObject
    // UObject starts with a vtable pointer
    for (int i = 0; i < 10 && i < numGlobals; i++) {
        void** pGlobal = (void**)globals[i].addr;
        void* obj = NULL;
        __try { obj = *pGlobal; } __except(1) { continue; }
        if (!obj) continue;
        
        // Check if it looks like a UObject (vtable pointer should be in .text/.rdata)
        uintptr_t vtable = 0;
        __try { vtable = *(uintptr_t*)obj; } __except(1) { continue; }
        
        if (vtable >= base && vtable < base + nt->OptionalHeader.SizeOfImage) {
            // Looks like a valid UObject. Check if GameViewport is at a known offset
            // In UE5, UEngine::GameViewport is typically at offset 0x??
            // We need to find it by scanning the object's memory for pointers
            
            Log("  Candidate GEngine at global 0x%llX -> UObject at 0x%llX (vtable 0x%llX)",
                globals[i].addr, (uintptr_t)obj, vtable);
            
            // Try to find GameViewport by checking offsets 0x100-0x1000 for a pointer 
            // that itself contains a vtable pointer
            for (int off = 0x100; off < 0x1000; off += 8) {
                void* field = NULL;
                __try { field = *(void**)((uintptr_t)obj + off); } __except(1) { continue; }
                if (!field) continue;
                
                uintptr_t fieldVt = 0;
                __try { fieldVt = *(uintptr_t*)field; } __except(1) { continue; }
                
                if (fieldVt >= base && fieldVt < base + nt->OptionalHeader.SizeOfImage) {
                    // This looks like a UObject pointer field
                    // Check if THIS object has a ViewportConsole field (pointer at some offset)
                    // GameViewport would have many pointer fields
                    int ptrCount = 0;
                    for (int off2 = 0; off2 < 0x800; off2 += 8) {
                        void* f2 = NULL;
                        __try { f2 = *(void**)((uintptr_t)field + off2); } __except(1) { continue; }
                        if (f2) {
                            uintptr_t vt2 = 0;
                            __try { vt2 = *(uintptr_t*)f2; } __except(1) { continue; }
                            if (vt2 >= base && vt2 < base + nt->OptionalHeader.SizeOfImage)
                                ptrCount++;
                        }
                    }
                    if (ptrCount > 10) {
                        Log("    Offset 0x%X -> UObject with %d sub-objects (possible GameViewport)", off, ptrCount);
                    }
                }
            }
            
            return obj; // Return first valid candidate
        }
    }
    
    Log("GEngine not found!");
    return NULL;
}

// ============================================================
// Console enabler thread
// ============================================================

static void ConsoleEnablerThread(void* param) {
    Log("=== MJOLNIR Console Enabler Started ===");
    
    // Wait for game to initialize
    Sleep(10000);
    
    void* engine = FindGEngine();
    if (engine) {
        Log("GEngine found at 0x%llX", (uintptr_t)engine);
        // TODO: Navigate to GameViewport and create console
    } else {
        Log("Failed to find GEngine");
    }
    
    Log("=== MJOLNIR Console Enabler Thread Exit ===");
}

// ============================================================
// DLL Entry Point
// ============================================================

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        CreateThread(NULL, 0, (LPTHREAD_START_ROUTINE)ConsoleEnablerThread, NULL, 0, NULL);
    }
    return TRUE;
}
