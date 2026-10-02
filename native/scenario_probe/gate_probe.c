/* gate_probe.dll — watch the campaign flow's pre-travel gate.
 *
 * StartScenario (CU4 exe FUN_147b44cb0) only travels when
 * FUN_147b21ff0(BlamEngineModule*, FString* scenarioName) returns true: it
 * composes "/Game/Tags/" + name + ".scenario" as an FName and asks the object
 * at module+0x120, virtual slot 3, whether it exists. Every caller reaches the
 * gate through `call rel32`, so the probe redirects those call sites to
 * logging wrappers (no prologue relocation) and, once it has seen the +0x120
 * object, swaps its vtable slot 3 too.
 *
 * Loaded from the UE4SS Lua sandbox with package.loadlib(path, "probe_open").
 */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define EXE_TIMESTAMP 0x8a03f777u
#define RVA_GATE 0x7B21FF0u
#define RVA_TRAVEL 0x680FFF0u
#define RVA_START 0x7B44CB0u

static const uint32_t GATE_SITES[] = {0x7B222D9u, 0x7B45C64u, 0x7B463F9u, 0x7B4791Du, 0x7B49DB1u};
static const uint32_t TRAVEL_SITES[] = {0x7B45C7Cu};
static const uint32_t START_SITES[] = {0x7B449EEu, 0x7B44A67u, 0x7B46621u};

typedef char(__fastcall *gate_fn)(uint8_t *module, void *name);
typedef char(__fastcall *travel_fn)(void *ctx, uint8_t *url, char flag);
typedef uint64_t(__fastcall *start_fn)(void *self, void *arg);
typedef char(__fastcall *slot3_fn)(void *self, uint64_t fname, int flag);

static CRITICAL_SECTION g_cs;
static char g_log[MAX_PATH];
static uint8_t *g_base;
static uint8_t *g_stubs;
static size_t g_stub_used;
static void **g_slot3_addr;
static slot3_fn g_slot3_orig;
static int g_slot3_hooked;

static void plog(const char *fmt, ...) {
    va_list ap;
    EnterCriticalSection(&g_cs);
    FILE *f = fopen(g_log, "a");
    if (f) {
        va_start(ap, fmt);
        vfprintf(f, fmt, ap);
        va_end(ap);
        fputc('\n', f);
        fclose(f);
    }
    LeaveCriticalSection(&g_cs);
}

static void log_fstring(const char *label, const uint8_t *fs) {
    const wchar_t *p = *(const wchar_t *const *)fs;
    int n = *(const int *)(fs + 8);
    if (!p || n <= 0) {
        plog("  %s = <empty> (len %d)", label, n);
        return;
    }
    plog("  %s = \"%ls\" (len %d)", label, p, n);
}

static char __fastcall hook_slot3(void *self, uint64_t fname, int flag) {
    char r = g_slot3_orig(self, fname, flag);
    plog("  slot3(self=%p, fname idx=%u num=%u, %d) -> %d", self, (unsigned)(fname & 0xffffffffu),
         (unsigned)(fname >> 32), flag, r);
    return r;
}

static char __fastcall hook_gate(uint8_t *module, void *name) {
    plog("gate: module=%p name=%p", module, name);
    if (name) log_fstring("scenario", (const uint8_t *)name);
    uint8_t *obj = module ? *(uint8_t **)(module + 0x120) : NULL;
    if (obj) {
        void **vt = *(void ***)obj;
        plog("  +0x120 obj=%p vtable rva %llx slot3 rva %llx", obj,
             (unsigned long long)((uint8_t *)vt - g_base), (unsigned long long)((uint8_t *)vt[3] - g_base));
        if (!g_slot3_hooked) {
            DWORD old;
            if (VirtualProtect(&vt[3], sizeof(void *), PAGE_READWRITE, &old)) {
                g_slot3_addr = &vt[3];
                g_slot3_orig = (slot3_fn)vt[3];
                vt[3] = (void *)hook_slot3;
                VirtualProtect(&vt[3], sizeof(void *), old, &old);
                g_slot3_hooked = 1;
                plog("  slot3 hooked");
            }
        }
    } else {
        plog("  +0x120 obj is NULL");
    }
    char r = ((gate_fn)(g_base + RVA_GATE))(module, name);
    plog("gate -> %d", r);
    return r;
}

static char __fastcall hook_travel(void *ctx, uint8_t *url, char flag) {
    plog("travel: ctx=%p url=%p flag=%d", ctx, url, flag);
    if (url) {
        log_fstring("protocol", url);
        log_fstring("host", url + 0x10);
        log_fstring("map", url + 0x28);
        const uint8_t *ops = *(const uint8_t *const *)(url + 0x48);
        int nops = *(const int *)(url + 0x50);
        plog("  %d options", nops);
        for (int i = 0; i < nops && i < 32; i++) log_fstring("op", ops + (size_t)i * 16);
    }
    char r = ((travel_fn)(g_base + RVA_TRAVEL))(ctx, url, flag);
    plog("travel -> %d", r);
    return r;
}

static uint64_t __fastcall hook_start(void *self, void *arg) {
    plog("StartScenario: self=%p arg=%p", self, arg);
    uint64_t r = ((start_fn)(g_base + RVA_START))(self, arg);
    plog("StartScenario -> %llx", (unsigned long long)r);
    return r;
}

static uint8_t *alloc_near(uint8_t *base) {
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    for (uint64_t step = si.dwAllocationGranularity * 4; step < 0x7ff00000ull; step += si.dwAllocationGranularity) {
        uint8_t *cand = base - step;
        void *p = VirtualAlloc(cand, 0x1000, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (p) return (uint8_t *)p;
    }
    return NULL;
}

static uint8_t *make_stub(void *target) {
    uint8_t *s = g_stubs + g_stub_used;
    s[0] = 0x48;
    s[1] = 0xB8;
    memcpy(s + 2, &target, 8);
    s[10] = 0xFF;
    s[11] = 0xE0;
    g_stub_used += 16;
    return s;
}

static int patch_sites(const char *what, const uint32_t *sites, size_t n, void *hook, uint32_t expect_rva) {
    uint8_t *stub = make_stub(hook);
    int done = 0;
    for (size_t i = 0; i < n; i++) {
        uint8_t *site = g_base + sites[i];
        if (site[0] != 0xE8) {
            plog("%s site %x: not a call (%02x)", what, sites[i], site[0]);
            continue;
        }
        int32_t rel = *(int32_t *)(site + 1);
        uint8_t *dest = site + 5 + rel;
        if (dest != g_base + expect_rva) {
            plog("%s site %x: calls rva %llx, expected %x", what, sites[i], (unsigned long long)(dest - g_base),
                 expect_rva);
            continue;
        }
        int64_t delta = (int64_t)(stub - (site + 5));
        if (delta > INT32_MAX || delta < INT32_MIN) {
            plog("%s site %x: stub too far", what, sites[i]);
            continue;
        }
        DWORD old;
        if (!VirtualProtect(site, 5, PAGE_EXECUTE_READWRITE, &old)) {
            plog("%s site %x: protect failed", what, sites[i]);
            continue;
        }
        int32_t rel32 = (int32_t)delta;
        memcpy(site + 1, &rel32, 4);
        VirtualProtect(site, 5, old, &old);
        FlushInstructionCache(GetCurrentProcess(), site, 5);
        done++;
    }
    plog("%s: %d/%zu call sites redirected", what, done, n);
    return done;
}

static void init_paths(void) {
    HMODULE me = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&init_paths, &me);
    GetModuleFileNameA(me, g_log, MAX_PATH);
    char *p = strrchr(g_log, '\\');
    if (p) *(p + 1) = 0;
    strcat_s(g_log, MAX_PATH, "gate_probe.log");
}

__declspec(dllexport) int probe_open(void *L) {
    (void)L;
    static int inited = 0;
    if (inited) {
        plog("already open");
        return 0;
    }
    InitializeCriticalSection(&g_cs);
    init_paths();
    g_base = (uint8_t *)GetModuleHandleA(NULL);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)g_base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(g_base + dos->e_lfanew);
    if (nt->FileHeader.TimeDateStamp != EXE_TIMESTAMP) {
        plog("refused: exe timestamp %08x", nt->FileHeader.TimeDateStamp);
        return 0;
    }
    g_stubs = alloc_near(g_base);
    if (!g_stubs) {
        plog("no near page");
        return 0;
    }
    plog("base=%p stubs=%p", g_base, g_stubs);
    patch_sites("gate", GATE_SITES, sizeof GATE_SITES / sizeof GATE_SITES[0], (void *)hook_gate, RVA_GATE);
    patch_sites("travel", TRAVEL_SITES, sizeof TRAVEL_SITES / sizeof TRAVEL_SITES[0], (void *)hook_travel,
                RVA_TRAVEL);
    patch_sites("start", START_SITES, sizeof START_SITES / sizeof START_SITES[0], (void *)hook_start, RVA_START);
    inited = 1;
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    (void)h;
    (void)reason;
    (void)r;
    return TRUE;
}
