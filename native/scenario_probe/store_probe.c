/* store_probe.dll ??? observe FFilePackageStoreBackend in the running game.
 *
 * Loaded from the UE4SS Lua sandbox with package.loadlib(path, "probe_open").
 * Swaps two slots of the backend's vtable (in .rdata of HaloCampaignEvolved.exe,
 * CU4 build 0x8a03f777) under VirtualProtect, the same technique the Blam
 * console DLL uses:
 *   [2] BeginRead(this)  -> after the original, dump MountedContainers when
 *                           their count changes
 *   [4] GetPackageStoreEntry(this, FPackageId, FName, FPackageStoreEntry*)
 *                        -> log lookups of watched ids and the first misses
 * Everything goes to store_probe.log next to the DLL. probe_close restores.
 */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define EXE_TIMESTAMP 0x8a03f777u
#define RVA_VTABLE 0xB446618u
#define RVA_BEGINREAD 0x4677240u
#define RVA_GETENTRY 0x4677280u

/* FFilePackageStoreBackend layout (recon 2026-09-03) */
#define OFF_CONTAINERS 0x38 /* TArray<FMountedContainer>, elem 32 B */
#define OFF_NEEDS_UPDATE 0x118

typedef void(__fastcall *beginread_fn)(void *self);
typedef uint32_t(__fastcall *getentry_fn)(void *self, uint64_t pkg, uint64_t name, void *out);

static beginread_fn g_orig_beginread;
static getentry_fn g_orig_getentry;
static void **g_vtable;
static char g_log[MAX_PATH];
static CRITICAL_SECTION g_cs;
static int g_last_num = -1;
static int g_misses = 0;
static long g_lookups = 0;
static const uint64_t WATCH[] = {0x5e3449f5ba1a9001ull /* PG1-scenario */,
                                 0x52c15b2c9e45c38eull /* B40-scenario */,
                                 0xb3227eba64962a70ull /* A30-scenario */,
                                 0x18fdf1128c4040a5ull /* A15-scenario */};
static long g_logall = 0;

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

static void dump_containers(uint8_t *self) {
    uint8_t *data = *(uint8_t **)(self + OFF_CONTAINERS);
    int32_t num = *(int32_t *)(self + OFF_CONTAINERS + 8);
    int32_t max = *(int32_t *)(self + OFF_CONTAINERS + 12);
    plog("containers: num=%d max=%d needs_update=%u", num, max, (unsigned)self[OFF_NEEDS_UPDATE]);
    for (int32_t i = 0; i < num && i < 64; i++) {
        uint8_t *e = data + (size_t)i * 32;
        uint8_t *hdr = *(uint8_t **)e;
        uint32_t order = *(uint32_t *)(e + 8);
        uint32_t seq = *(uint32_t *)(e + 12);
        uint32_t w10 = *(uint32_t *)(e + 0x10);
        uint32_t w14 = *(uint32_t *)(e + 0x14);
        uint32_t w18 = *(uint32_t *)(e + 0x18);
        uint32_t w1c = *(uint32_t *)(e + 0x1c);
        uint64_t cid = 0;
        int32_t npkg = -1, nstore = -1;
        if (hdr && !IsBadReadPtr(hdr, 0xA0)) {
            cid = *(uint64_t *)hdr;
            npkg = *(int32_t *)(hdr + 0x10);
            nstore = *(int32_t *)(hdr + 0x20);
        }
        plog("  [%d] hdr=%p id=%016llx order=%u seq=%u w10=%u w14=%u w18=%u w1c=%u pkgids=%d storebytes=%d",
             i, hdr, (unsigned long long)cid, order, seq, w10, w14, w18, w1c, npkg, nstore);
    }
}

static void __fastcall hooked_beginread(void *self) {
    g_orig_beginread(self);
    int32_t num = *(int32_t *)((uint8_t *)self + OFF_CONTAINERS + 8);
    if (num != g_last_num) {
        g_last_num = num;
        dump_containers((uint8_t *)self);
    }
}

static uint32_t __fastcall hooked_getentry(void *self, uint64_t pkg, uint64_t name, void *out) {
    uint32_t r = g_orig_getentry(self, pkg, name, out);
    InterlockedIncrement(&g_lookups);
    int watched = 0;
    for (size_t i = 0; i < sizeof(WATCH) / sizeof(WATCH[0]); i++)
        if (WATCH[i] == pkg) watched = 1;
    if (watched) {
        plog("lookup WATCHED id=%016llx name=%016llx -> status %u", (unsigned long long)pkg,
             (unsigned long long)name, r);
    } else if (g_logall > 0) {
        InterlockedDecrement(&g_logall);
        plog("lookup id=%016llx name=%016llx -> status %u", (unsigned long long)pkg,
             (unsigned long long)name, r);
    } else if (r != 3 && g_misses < 40) {
        g_misses++;
        plog("lookup miss id=%016llx name=%016llx -> status %u", (unsigned long long)pkg,
             (unsigned long long)name, r);
    }
    return r;
}

static int swap_slot(void **slot, void *expect, void *replacement) {
    if (*slot != expect) return 0;
    DWORD old;
    if (!VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &old)) return 0;
    InterlockedExchangePointer(slot, replacement);
    VirtualProtect(slot, sizeof(void *), old, &old);
    return 1;
}

static void init_paths(void) {
    HMODULE me = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&init_paths, &me);
    GetModuleFileNameA(me, g_log, MAX_PATH);
    char *p = strrchr(g_log, '\\');
    if (p) *(p + 1) = 0;
    strcat_s(g_log, MAX_PATH, "store_probe.log");
}

__declspec(dllexport) int probe_open(void *L) {
    (void)L;
    static int inited = 0;
    if (!inited) {
        InitializeCriticalSection(&g_cs);
        init_paths();
        inited = 1;
    }
    uint8_t *base = (uint8_t *)GetModuleHandleA(NULL);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    if (nt->FileHeader.TimeDateStamp != EXE_TIMESTAMP) {
        plog("refused: exe timestamp %08x != %08x", nt->FileHeader.TimeDateStamp, EXE_TIMESTAMP);
        return 1;
    }
    g_vtable = (void **)(base + RVA_VTABLE);
    void *want_br = base + RVA_BEGINREAD;
    void *want_ge = base + RVA_GETENTRY;
    if (g_vtable[2] == (void *)hooked_beginread) {
        plog("already installed");
        return 0;
    }
    if (g_vtable[2] != want_br || g_vtable[4] != want_ge) {
        plog("refused: vtable[2]=%p (want %p) vtable[4]=%p (want %p)", g_vtable[2], want_br, g_vtable[4], want_ge);
        return 2;
    }
    g_orig_beginread = (beginread_fn)want_br;
    g_orig_getentry = (getentry_fn)want_ge;
    int a = swap_slot(&g_vtable[2], want_br, (void *)hooked_beginread);
    int b = swap_slot(&g_vtable[4], want_ge, (void *)hooked_getentry);
    plog("installed: base=%p vtable=%p beginread=%d getentry=%d", base, g_vtable, a, b);
    return (a && b) ? 0 : 3;
}

__declspec(dllexport) int probe_logall(void *L) {
    (void)L;
    g_logall = 300;
    plog("--- logging the next 300 lookups (lookups so far %ld) ---", g_lookups);
    return 0;
}

__declspec(dllexport) int probe_close(void *L) {
    (void)L;
    if (!g_vtable) return 1;
    swap_slot(&g_vtable[2], (void *)hooked_beginread, (void *)g_orig_beginread);
    swap_slot(&g_vtable[4], (void *)hooked_getentry, (void *)g_orig_getentry);
    plog("restored; lookups=%ld", g_lookups);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    (void)h; (void)reason; (void)r;
    return TRUE;
}

