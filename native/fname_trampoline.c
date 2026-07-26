// MJOLNIR FName Injector v3
// Injects a real FName::FName(const wchar_t*) constructor into the game's .text section.
//
// The real FName construction path in this build (RVA 0x36FFEF0, 412 callers) takes:
//   RCX = FNameView source descriptor { uint64 packedData; int32 number; int8 flags; ... }
//   RDX = FName* destination
// It has a complex path that includes wcslen computation, hash, and FNamePool lookup.
//
// We create a wrapper with UE4SS's expected signature:
//   RCX = FName* this (destination)
//   RDX = const wchar_t* name
// That builds the source descriptor and calls the real function.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

// Real FName construction function RVA
#define FNAME_MAKE_RVA 0x36FFEF0ULL

static FILE* g_log = NULL;
static void Log(const char* fmt, ...) {
    if (!g_log) {
        char path[MAX_PATH];
        GetModuleFileNameA(NULL, path, MAX_PATH);
        char* dot = strrchr(path, '\\');
        if (dot) strcpy(dot + 1, "MJOLNIRTrampoline.log");
        g_log = fopen(path, "w");
    }
    if (g_log) {
        va_list a; va_start(a, fmt);
        vfprintf(g_log, fmt, a); fprintf(g_log, "\n"); fflush(g_log);
        va_end(a);
    }
}

// Global: address of our injected function (used by verification trigger thread)
static uint8_t* g_injectedFn = NULL;

// Typedef for calling our injected FName constructor
typedef void* (__fastcall *FNameCtorFn)(void* thisPtr, const wchar_t* name, int findType);

static uint8_t* FindCCPadding(uintptr_t textStart, size_t textSize, size_t needed) {
    uint8_t* p = (uint8_t*)textStart;
    size_t run = 0;
    for (size_t i = textSize - 1; i >= needed; i--) {
        if (p[i] == 0xCC) {
            run++;
            if (run >= needed) return &p[i];
        } else {
            run = 0;
        }
    }
    return NULL;
}

static void InjectFNameConstructor(void) {
    uintptr_t base = (uintptr_t)GetModuleHandleA(NULL);
    uintptr_t fnameMake = base + FNAME_MAKE_RVA;
    
    Log("Module base: 0x%llX", base);
    Log("FName construction func: 0x%llX", fnameMake);
    
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)base;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)(base + dos->e_lfanew);
    PIMAGE_SECTION_HEADER text = IMAGE_FIRST_SECTION(nt);
    uintptr_t textStart = base + text->VirtualAddress;
    size_t textSize = text->SizeOfRawData;
    
    // The FName construction function at RVA 0x36FFEF0 takes:
    //   RCX = pointer to source descriptor:
    //     +0: uint64 packedData (pointer to wchar_t string, with high bit as flag)
    //     +8: int32 number
    //     +C: int8 flags (0 = normal)
    //   RDX = FName* destination
    //
    // We create a function with UE4SS signature:
    //   RCX = FName* this (= destination)
    //   RDX = const wchar_t* name
    //
    // Our function builds the source descriptor on the stack and calls the real one.
    
    uint8_t code[160];
    int pos = 0;
    
    // === UNIQUE MARKER FIRST at offset 0x00 (16 bytes) ===
    // NOPs with 'MJOL' and 'NIR!' displacement so UE4SS Lua scanner matches Attempt 1.
    // Execution falls through seamlessly to prologue at offset 0x10.
    code[pos++] = 0x0F; code[pos++] = 0x1F; code[pos++] = 0x84; code[pos++] = 0x00;
    code[pos++] = 0x4D; code[pos++] = 0x4A; code[pos++] = 0x4F; code[pos++] = 0x4C;
    code[pos++] = 0x0F; code[pos++] = 0x1F; code[pos++] = 0x84; code[pos++] = 0x00;
    code[pos++] = 0x4E; code[pos++] = 0x49; code[pos++] = 0x52; code[pos++] = 0x21;
    
    // === FUNCTION PROLOGUE AT OFFSET 0x10 ===
    // RCX = FName* this (destination)
    // RDX = const wchar_t* name (source string)
    // R8  = EFindName findType (0 = FNAME_Find, 1 = FNAME_Add)
    
    // +10: push rbp
    code[pos++] = 0x55;
    // +11: mov rbp, rsp
    code[pos++] = 0x48; code[pos++] = 0x8B; code[pos++] = 0xEC;
    // +14: push rbx
    code[pos++] = 0x53;
    // +15: push rdi
    code[pos++] = 0x57;
    // +16: sub rsp, 0x40
    code[pos++] = 0x48; code[pos++] = 0x83; code[pos++] = 0xEC; code[pos++] = 0x40;
    // +1A: mov rbx, rcx  (save FName* this)
    code[pos++] = 0x48; code[pos++] = 0x8B; code[pos++] = 0xD9;
    // +1D: mov rdi, rdx  (save wchar_t* name)
    code[pos++] = 0x48; code[pos++] = 0x8B; code[pos++] = 0xFA;
    
    // Build source descriptor on stack at [rsp+0x20]:
    // +0x20: uint64 = pointer to wchar_t string WITH BIT 63 SET
    // +0x28: int32 = 0 (number = NAME_NO_NUMBER_INTERNAL)  
    // +0x2C: int8 = r8b (FindType: 0 = FNAME_Find, 1 = FNAME_Add)
    
    // Zero the entire descriptor area first (16 bytes)
    // xor eax, eax
    code[pos++] = 0x33; code[pos++] = 0xC0;
    // mov [rsp+0x20], rax   ; zero qword at +0x20
    code[pos++] = 0x48; code[pos++] = 0x89; code[pos++] = 0x44; code[pos++] = 0x24; code[pos++] = 0x20;
    // mov [rsp+0x28], rax   ; zero qword at +0x28 (covers Number and Flags)
    code[pos++] = 0x48; code[pos++] = 0x89; code[pos++] = 0x44; code[pos++] = 0x24; code[pos++] = 0x28;
    // mov [rsp+0x2C], r8b   ; store FindType (FNAME_Find = 0, FNAME_Add = 1) from 3rd argument (r8)
    code[pos++] = 0x44; code[pos++] = 0x88; code[pos++] = 0x44; code[pos++] = 0x24; code[pos++] = 0x2C;
    
    // Set bit 63 on the string pointer: rdi = name ptr, need rdi | 0x8000000000000000
    // mov rax, 0x8000000000000000
    code[pos++] = 0x48; code[pos++] = 0xB8;
    *(uint64_t*)&code[pos] = 0x8000000000000000ULL;
    pos += 8;
    // or rax, rdi            ; rax = name_ptr | bit63
    code[pos++] = 0x48; code[pos++] = 0x0B; code[pos++] = 0xC7;
    // mov [rsp+0x20], rax   ; descriptor.Data = name_ptr | bit63
    code[pos++] = 0x48; code[pos++] = 0x89; code[pos++] = 0x44; code[pos++] = 0x24; code[pos++] = 0x20;
    
    // Call the real FName construction function:
    //   RCX = &descriptor (source)
    //   RDX = FName* (destination)
    
    // lea rcx, [rsp+0x20]  ; arg1 = &source descriptor
    code[pos++] = 0x48; code[pos++] = 0x8D; code[pos++] = 0x4C; code[pos++] = 0x24; code[pos++] = 0x20;
    // mov rdx, rbx          ; arg2 = FName* this (destination)
    code[pos++] = 0x48; code[pos++] = 0x8B; code[pos++] = 0xD3;
    
    // mov rax, <fnameMake absolute address>
    code[pos++] = 0x48; code[pos++] = 0xB8;
    *(uint64_t*)&code[pos] = fnameMake;
    pos += 8;
    
    // call rax
    code[pos++] = 0xFF; code[pos++] = 0xD0;
    
    // Return FName* this in rax
    // mov rax, rbx
    code[pos++] = 0x48; code[pos++] = 0x8B; code[pos++] = 0xC3;
    
    // Epilogue
    // add rsp, 0x40
    code[pos++] = 0x48; code[pos++] = 0x83; code[pos++] = 0xC4; code[pos++] = 0x40;
    // pop rdi
    code[pos++] = 0x5F;
    // pop rbx
    code[pos++] = 0x5B;
    // pop rbp
    code[pos++] = 0x5D;
    // ret
    code[pos++] = 0xC3;
    
    int codeSize = pos;
    Log("Generated %d bytes of FName constructor code", codeSize);
    
    uint8_t* target = FindCCPadding(textStart, textSize, codeSize + 32);
    if (!target) {
        Log("ERROR: No CC padding found!");
        return;
    }
    
    Log("Found CC padding at 0x%llX (RVA 0x%llX)", (uintptr_t)target, (uintptr_t)target - base);
    
    DWORD oldProtect;
    if (!VirtualProtect(target, codeSize, PAGE_EXECUTE_READWRITE, &oldProtect)) {
        Log("ERROR: VirtualProtect failed: %lu", GetLastError());
        return;
    }
    
    memcpy(target, code, codeSize);
    VirtualProtect(target, codeSize, oldProtect, &oldProtect);
    FlushInstructionCache(GetCurrentProcess(), target, codeSize);
    
    Log("FName constructor injected at 0x%llX", (uintptr_t)target);
    
    // Log AOB
    char aob[256] = {0};
    for (int i = 0; i < 32 && i < codeSize; i++) {
        char hex[4];
        sprintf(hex, "%02X ", target[i]);
        strcat(aob, hex);
    }
    Log("AOB: %s", aob);
    
    // Store the address for the verification trigger thread
    g_injectedFn = target;
    
    // Write the injected function address to a file for the Lua script
    // Register runtime function entry in Windows PE Exception Table
    // so RtlLookupFunctionEntry (used by UE4SS and Windows exception handler)
    // recognizes our injected trampoline as a valid function.
    static RUNTIME_FUNCTION rf;
    rf.BeginAddress = (DWORD)(target - (uint8_t*)base);
    rf.EndAddress = (DWORD)(target + codeSize - (uint8_t*)base);
    rf.UnwindData = 0;
    
    if (RtlAddFunctionTable(&rf, 1, base)) {
        Log("Registered RUNTIME_FUNCTION in PE Exception Table for 0x%p", target);
    } else {
        Log("WARNING: RtlAddFunctionTable failed");
    }
    
    char addrPath[MAX_PATH];
    GetModuleFileNameA(NULL, addrPath, MAX_PATH);
    char* lastSlash = strrchr(addrPath, '\\');
    if (lastSlash) strcpy(lastSlash + 1, "mjolnir_fname_addr.txt");
    FILE* af = fopen(addrPath, "w");
    if (af) {
        fprintf(af, "%llu\n", (unsigned long long)(uintptr_t)target);
        fclose(af);
        Log("Wrote function address to: %s", addrPath);
    }
    
    Log("=== Injection Complete ===");
}

typedef void* (__fastcall *FNameCtorFn)(void* thisPtr, const wchar_t* name, int findType);
typedef void (__fastcall *EngineTickFn)(void* engine, float deltaSeconds, int unused);

// Background thread: waits for UE4SS to hook our function, then calls it
// to trigger the verification post-hook and EngineTick unhooker
static DWORD WINAPI VerificationTriggerThread(LPVOID param) {
    // Wait 500ms for UE4SS DLL injection
    Sleep(500);
    
    Log("Verification trigger: started fast polling for both WChar and Ansi + EngineTick...");
    
    if (!g_injectedFn) {
        Log("ERROR: No injected function address!");
        return 1;
    }
    
    FNameCtorFn fn = (FNameCtorFn)g_injectedFn;
    
    const wchar_t* testWStrings[] = { L"None", L"Verify", L"Test", L"Object", L"Class" };
    const char* testAStrings[] = { "None", "Verify", "Test", "Object", "Class" };
    
    // Call injected function every 100ms for 60 seconds (600 rounds)
    for (int round = 0; round < 600; round++) {
        for (int i = 0; i < 5; i++) {
            __try {
                // Test wchar_t* string (satisfies WChar hook)
                uint8_t fnameW[16] = {0};
                fn(fnameW, testWStrings[i], 1);
                
                // Test char* string (satisfies Ansi hook)
                uint8_t fnameA[16] = {0};
                fn(fnameA, (const wchar_t*)testAStrings[i], 1);
            } __except(EXCEPTION_EXECUTE_HANDLER) {}
        }
        Sleep(100);
    }
    
    Log("Verification trigger complete.");
    return 0;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        InjectFNameConstructor();
        // Verification is handled natively by UE4SS; no trigger thread needed
    }
    return TRUE;
}
