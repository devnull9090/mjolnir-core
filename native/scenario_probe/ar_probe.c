/* ar_probe.dll — the AssetRegistry's short-name resolver.
 *
 * UEngine::MakeSureMapNameIsValid (CU4 exe FUN_1467789d0) resolves a map
 * name without a '/' by calling IAssetRegistry virtual slot 30 (+0xf0),
 * GetFirstPackageByName(FStringView), on the registry the AssetRegistry
 * module's Get() returns. Only a hit continues to travel; a long path goes
 * to FPackageName::DoesPackageExist instead.
 *
 * probe_open reads the UAssetRegistryImpl address from ar_addr.txt (written
 * by the UE4SS Lua side), takes the IAssetRegistry sub-object at +0x28, logs
 * the vtable and, when ARMED, wraps slot 30 to log every query and answer.
 *
 * Loaded from the UE4SS Lua sandbox with package.loadlib(path, "probe_open").
 */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define EXE_TIMESTAMP 0x8a03f777u
#define IFACE_OFFSET 0x28
#define SLOT_FIRST_PACKAGE 30

typedef struct {
    const wchar_t *data;
    int32_t len;
} string_view_t;

/* FName GetFirstPackageByName(FStringView): a struct return arrives through a
 * hidden pointer in RDX, the view pointer in R8. */
typedef void *(__fastcall *first_pkg_fn)(void *self, uint64_t *out, const string_view_t *name);

static CRITICAL_SECTION g_cs;
static char g_dir[MAX_PATH];
static char g_log[MAX_PATH];
static uint8_t *g_base;
static void **g_vt;
static first_pkg_fn g_orig;
static int g_hooked;

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

static void *__fastcall hook_first_pkg(void *self, uint64_t *out, const string_view_t *name) {
    void *r = g_orig(self, out, name);
    wchar_t buf[256];
    int n = name && name->len > 0 && name->len < 255 ? name->len : 0;
    if (n) memcpy(buf, name->data, (size_t)n * sizeof(wchar_t));
    buf[n] = 0;
    plog("GetFirstPackageByName(\"%ls\" len %d) -> out[0]=%016llx out[1]=%016llx ret=%p", buf, name ? name->len : -1,
         (unsigned long long)out[0], (unsigned long long)out[1], r);
    return r;
}

static void init_paths(void) {
    HMODULE me = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&init_paths, &me);
    GetModuleFileNameA(me, g_dir, MAX_PATH);
    char *p = strrchr(g_dir, '\\');
    if (p) *(p + 1) = 0;
    strcpy_s(g_log, MAX_PATH, g_dir);
    strcat_s(g_log, MAX_PATH, "ar_probe.log");
}

static int swap_slot(void **slot, void *expect, void *replacement) {
    if (*slot != expect) return 0;
    DWORD old;
    if (!VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &old)) return 0;
    InterlockedExchangePointer(slot, replacement);
    VirtualProtect(slot, sizeof(void *), old, &old);
    return 1;
}

__declspec(dllexport) int probe_open(void *L) {
    (void)L;
    static int inited = 0;
    if (!inited) {
        InitializeCriticalSection(&g_cs);
        init_paths();
        inited = 1;
    }
    g_base = (uint8_t *)GetModuleHandleA(NULL);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)g_base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(g_base + dos->e_lfanew);
    if (nt->FileHeader.TimeDateStamp != EXE_TIMESTAMP) {
        plog("refused: exe timestamp %08x", nt->FileHeader.TimeDateStamp);
        return 0;
    }
    char path[MAX_PATH];
    strcpy_s(path, MAX_PATH, g_dir);
    strcat_s(path, MAX_PATH, "ar_addr.txt");
    FILE *f = fopen(path, "r");
    if (!f) {
        plog("no ar_addr.txt");
        return 0;
    }
    unsigned long long addr = 0;
    fscanf(f, "%llu", &addr);
    fclose(f);
    uint8_t *obj = (uint8_t *)(uintptr_t)addr;
    uint8_t *iface = obj + IFACE_OFFSET;
    void **vt = *(void ***)iface;
    plog("registry object %p iface %p vtable rva %llx", obj, iface, (unsigned long long)((uint8_t *)vt - g_base));
    for (int i = 0; i < 40; i++)
        plog("  slot %2d rva %llx", i, (unsigned long long)((uint8_t *)vt[i] - g_base));
    g_vt = vt;
    return 0;
}

__declspec(dllexport) int probe_arm(void *L) {
    (void)L;
    if (!g_vt || g_hooked) {
        plog("arm: nothing to do");
        return 0;
    }
    g_orig = (first_pkg_fn)g_vt[SLOT_FIRST_PACKAGE];
    int ok = swap_slot(&g_vt[SLOT_FIRST_PACKAGE], (void *)g_orig, (void *)hook_first_pkg);
    g_hooked = ok;
    plog("arm: slot %d hooked=%d", SLOT_FIRST_PACKAGE, ok);
    return 0;
}

__declspec(dllexport) int probe_close(void *L) {
    (void)L;
    if (g_hooked) {
        swap_slot(&g_vt[SLOT_FIRST_PACKAGE], (void *)hook_first_pkg, (void *)g_orig);
        g_hooked = 0;
        plog("restored");
    }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    (void)h;
    (void)reason;
    (void)r;
    return TRUE;
}
