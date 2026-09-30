/* chunk_probe.dll — watch FIoDispatcher's backends answer DoesChunkExist.
 *
 * FPackageName::DoesPackageExistEx (CU4 exe FUN_1437a8ae0) resolves a
 * package's existence in IoStore by FIoDispatcher::DoesChunkExist over the
 * ExportBundleData chunk of its FPackageId, unless the DoesPackageExist
 * override delegate is bound (nothing binds it in this build). This probe
 * swaps vtable slot 7 (DoesChunkExist) of every mounted IoStore backend, and
 * logs every query for watched package ids, plus a window of all queries.
 *
 * FIoDispatcher global: CU4 .data RVA 0xD348BF8 holds FIoDispatcher*, whose
 * first qword is the impl; impl+0x28 = TArray<{?, IIoDispatcherBackend*}>
 * data (24-byte elements, backend at +8), impl+0x30 = count, impl+0x20 = the
 * SRWLOCK guarding them (FUN_1436165a0).
 *
 * Loaded from the UE4SS Lua sandbox with package.loadlib(path, "probe_open").
 */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define EXE_TIMESTAMP 0x8a03f777u
#define RVA_DISPATCHER 0xD348BF8u
#define OFF_BACKENDS 0x28
#define OFF_COUNT 0x30
#define SLOT_DOES_CHUNK_EXIST 7
#define MAX_BACKENDS 8

typedef struct {
    uint64_t id;
    uint16_t index;
    uint8_t pad;
    uint8_t type;
} chunk_id_t;

typedef char(__fastcall *dce_fn)(void *self, const chunk_id_t *id);

static const uint64_t WATCH[] = {0x84f618c3f58689a4ull /* BGL world */,
                                 0xbfbd9b75d06224b8ull /* BGL-scenario */,
                                 0x0367597972819631ull /* B40 world */,
                                 0x11484f1c60e05d0bull /* SeamlessTravelTEst */};

static CRITICAL_SECTION g_cs;
static char g_log[MAX_PATH];
static void **g_vtables[MAX_BACKENDS];
static dce_fn g_orig[MAX_BACKENDS];
static void *g_backend[MAX_BACKENDS];
static int g_n;
static long g_logall;
static long g_calls;

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

static char __fastcall hooked(void *self, const chunk_id_t *id) {
    int slot = -1;
    for (int i = 0; i < g_n; i++)
        if (g_backend[i] == self) slot = i;
    char r = slot >= 0 ? g_orig[slot](self, id) : 0;
    InterlockedIncrement(&g_calls);
    int watched = 0;
    for (size_t i = 0; i < sizeof(WATCH) / sizeof(WATCH[0]); i++)
        if (WATCH[i] == id->id) watched = 1;
    if (watched) {
        plog("WATCHED backend %d id=%016llx index=%u type=%u -> %d", slot, (unsigned long long)id->id,
             id->index, id->type, r);
    } else if (g_logall > 0) {
        InterlockedDecrement(&g_logall);
        plog("backend %d id=%016llx index=%u type=%u -> %d", slot, (unsigned long long)id->id, id->index,
             id->type, r);
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
    strcat_s(g_log, MAX_PATH, "chunk_probe.log");
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
        plog("refused: exe timestamp %08x", nt->FileHeader.TimeDateStamp);
        return 0;
    }
    uint8_t *dispatcher = *(uint8_t **)(base + RVA_DISPATCHER);
    if (!dispatcher) {
        plog("no dispatcher");
        return 0;
    }
    uint8_t *impl = *(uint8_t **)dispatcher;
    uint8_t *data = *(uint8_t **)(impl + OFF_BACKENDS);
    int count = *(int *)(impl + OFF_COUNT);
    plog("dispatcher=%p impl=%p backends=%d", dispatcher, impl, count);
    for (int i = 0; i < count && g_n < MAX_BACKENDS; i++) {
        void *backend = *(void **)(data + (size_t)i * 0x18 + 8);
        if (!backend || IsBadReadPtr(backend, 8)) continue;
        void **vt = *(void ***)backend;
        int dup = 0;
        for (int k = 0; k < g_n; k++)
            if (g_vtables[k] == vt) dup = 1;
        if (dup) {
            g_backend[g_n] = backend;
            g_vtables[g_n] = vt;
            g_orig[g_n] = g_orig[g_n - 1];
            g_n++;
            continue;
        }
        g_backend[g_n] = backend;
        g_vtables[g_n] = vt;
        g_orig[g_n] = (dce_fn)vt[SLOT_DOES_CHUNK_EXIST];
        int ok = swap_slot(&vt[SLOT_DOES_CHUNK_EXIST], (void *)g_orig[g_n], (void *)hooked);
        plog("  backend[%d]=%p vtable=%p DoesChunkExist=%p hooked=%d", i, backend, vt, g_orig[g_n], ok);
        g_n++;
    }
    return 0;
}

__declspec(dllexport) int probe_logall(void *L) {
    (void)L;
    g_logall = 400;
    plog("--- logging the next 400 queries (so far %ld) ---", g_calls);
    return 0;
}

__declspec(dllexport) int probe_close(void *L) {
    (void)L;
    for (int i = 0; i < g_n; i++) {
        if (i > 0 && g_vtables[i] == g_vtables[i - 1]) continue;
        swap_slot(&g_vtables[i][SLOT_DOES_CHUNK_EXIST], (void *)hooked, (void *)g_orig[i]);
    }
    plog("restored; calls=%ld", g_calls);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    (void)h; (void)reason; (void)r;
    return TRUE;
}
