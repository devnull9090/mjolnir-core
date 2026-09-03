/* tagrefs_probe.dll - dump BlamCookedTagReferencesEngineSubsystem.
 * Lua writes the object's address (hex) to tagrefs_addr.txt next to the DLL;
 * tagrefs_dump reads it and writes tagrefs.log:
 *   +0x30 TArray<FString> paths (Num, first/last, entries matching a needle)
 *   +0x40 TArray of 13 container records {u32 id; TArray; i32; i32}
 *   +0x50 hash mask, and the words that follow (bucket table?)
 */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

static char g_dir[MAX_PATH];

static void init_dir(void) {
    HMODULE me = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&init_dir, &me);
    GetModuleFileNameA(me, g_dir, MAX_PATH);
    char *p = strrchr(g_dir, '\\');
    if (p) *(p + 1) = 0;
}

static int readable(const void *p, size_t n) { return p && !IsBadReadPtr(p, n); }

__declspec(dllexport) int tagrefs_dump(void *L) {
    (void)L;
    init_dir();
    char path[MAX_PATH];
    snprintf(path, MAX_PATH, "%stagrefs_addr.txt", g_dir);
    FILE *fa = fopen(path, "r");
    if (!fa) return 1;
    unsigned long long addr = 0;
    fscanf(fa, "%llx", &addr);
    fclose(fa);
    snprintf(path, MAX_PATH, "%stagrefs.log", g_dir);
    FILE *f = fopen(path, "a");
    if (!f) return 2;
    uint8_t *obj = (uint8_t *)addr;
    fprintf(f, "subsystem @ %p\n", obj);
    if (!readable(obj, 0x200)) { fprintf(f, "unreadable\n"); fclose(f); return 3; }
    /* raw words 0x28..0x120 */
    for (int o = 0x28; o < 0x120; o += 8)
        fprintf(f, "  +%03x %016llx\n", o, (unsigned long long)*(uint64_t *)(obj + o));
    /* +0x30 TArray<FString> */
    uint8_t *data = *(uint8_t **)(obj + 0x30);
    int32_t num = *(int32_t *)(obj + 0x38), max = *(int32_t *)(obj + 0x3c);
    fprintf(f, "paths: data=%p num=%d max=%d\n", data, num, max);
    if (readable(data, (size_t)num * 16)) {
        for (int32_t i = 0; i < num; i++) {
            wchar_t *s = *(wchar_t **)(data + (size_t)i * 16);
            int32_t sn = *(int32_t *)(data + (size_t)i * 16 + 8);
            if (i < 3 || i >= num - 3 || (readable(s, 2) && (wcsstr(s, L"scenario") && (wcsstr(s, L"B40") || wcsstr(s, L"b40") || wcsstr(s, L"PG1") || wcsstr(s, L"pg1")))))
                fprintf(f, "  [%d] len %d %ls\n", i, sn, readable(s, 2) ? s : L"?");
        }
    }
    /* +0x40 containers */
    uint8_t *cdata = *(uint8_t **)(obj + 0x40);
    int32_t cnum = *(int32_t *)(obj + 0x48), cmax = *(int32_t *)(obj + 0x4c);
    fprintf(f, "containers: data=%p num=%d max=%d\n", cdata, cnum, cmax);
    for (int32_t i = 0; i < cnum && readable(cdata, (size_t)(i + 1) * 32); i++) {
        uint8_t *e = cdata + (size_t)i * 32;
        fprintf(f, "  [%d] %08x %08x ptr=%p num=%d max=%d %08x %08x\n", i, *(uint32_t *)e, *(uint32_t *)(e + 4),
                *(void **)(e + 8), *(int32_t *)(e + 16), *(int32_t *)(e + 20), *(uint32_t *)(e + 24), *(uint32_t *)(e + 28));
    }
    fclose(f);
    return 0;
}


/* Dump a UFunction's trailing fields so the native thunk pointer can be found:
 * Lua writes the UFunction address to ufunc_addr.txt. */
__declspec(dllexport) int ufunc_dump(void *L) {
    (void)L;
    init_dir();
    char path[MAX_PATH];
    snprintf(path, MAX_PATH, "%sufunc_addr.txt", g_dir);
    FILE *fa = fopen(path, "r");
    if (!fa) return 1;
    unsigned long long addr = 0;
    fscanf(fa, "%llx", &addr);
    fclose(fa);
    snprintf(path, MAX_PATH, "%stagrefs.log", g_dir);
    FILE *f = fopen(path, "a");
    if (!f) return 2;
    uint8_t *base = (uint8_t *)GetModuleHandleA(NULL);
    uint8_t *obj = (uint8_t *)addr;
    fprintf(f, "ufunction @ %p exe base %p\n", obj, base);
    if (readable(obj, 0x100)) {
        for (int o = 0x90; o < 0x100; o += 8) {
            uint64_t w = *(uint64_t *)(obj + o);
            if (w > (uint64_t)base && w < (uint64_t)base + 0x0E200000)
                fprintf(f, "  +%03x %016llx  (exe RVA %08llx)\n", o, (unsigned long long)w, (unsigned long long)(w - (uint64_t)base));
            else
                fprintf(f, "  +%03x %016llx\n", o, (unsigned long long)w);
        }
    }
    fclose(f);
    return 0;
}


/* Append one path (UTF-8 in tagrefs_append.txt) to the +0x30 TArray<FString>
 * if there is spare capacity; the string buffer comes from the process heap
 * and is never freed (a probe, not a mod). */
__declspec(dllexport) int tagrefs_append(void *L) {
    (void)L;
    init_dir();
    char path[MAX_PATH];
    snprintf(path, MAX_PATH, "%stagrefs_addr.txt", g_dir);
    FILE *fa = fopen(path, "r");
    if (!fa) return 1;
    unsigned long long addr = 0;
    fscanf(fa, "%llx", &addr);
    fclose(fa);
    snprintf(path, MAX_PATH, "%stagrefs_append.txt", g_dir);
    FILE *fp = fopen(path, "r");
    if (!fp) return 2;
    char utf8[512] = {0};
    if (!fgets(utf8, sizeof utf8, fp)) { fclose(fp); return 3; }
    fclose(fp);
    size_t n = strlen(utf8);
    while (n && (utf8[n - 1] == '\n' || utf8[n - 1] == '\r')) utf8[--n] = 0;
    snprintf(path, MAX_PATH, "%stagrefs.log", g_dir);
    FILE *f = fopen(path, "a");
    if (!f) return 4;
    uint8_t *obj = (uint8_t *)addr;
    uint8_t *data = *(uint8_t **)(obj + 0x30);
    int32_t *num = (int32_t *)(obj + 0x38);
    int32_t max = *(int32_t *)(obj + 0x3c);
    if (*num >= max) { fprintf(f, "append: no capacity (%d/%d)\n", *num, max); fclose(f); return 5; }
    int wlen = MultiByteToWideChar(CP_UTF8, 0, utf8, -1, NULL, 0);
    wchar_t *w = (wchar_t *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (size_t)wlen * 2);
    MultiByteToWideChar(CP_UTF8, 0, utf8, -1, w, wlen);
    uint8_t *e = data + (size_t)(*num) * 16;
    *(wchar_t **)e = w;
    *(int32_t *)(e + 8) = wlen;      /* FString Num includes the terminator */
    *(int32_t *)(e + 12) = wlen;
    int idx = (*num)++;
    fprintf(f, "append: [%d] %ls (num now %d)\n", idx, w, *num);
    fclose(f);
    return 0;
}


/* Hexdump: dump_req.txt holds "<hex addr> <len>"; output to tagrefs.log. */
__declspec(dllexport) int dump_bytes(void *L) {
    (void)L;
    init_dir();
    char path[MAX_PATH];
    snprintf(path, MAX_PATH, "%sdump_req.txt", g_dir);
    FILE *fa = fopen(path, "r");
    if (!fa) return 1;
    unsigned long long addr = 0; unsigned long len = 0;
    fscanf(fa, "%llx %lu", &addr, &len);
    fclose(fa);
    snprintf(path, MAX_PATH, "%stagrefs.log", g_dir);
    FILE *f = fopen(path, "a");
    if (!f) return 2;
    uint8_t *p = (uint8_t *)addr;
    fprintf(f, "dump %p len %lu\n", p, len);
    if (!readable(p, len)) { fprintf(f, "  unreadable\n"); fclose(f); return 3; }
    for (unsigned long o = 0; o < len; o += 16) {
        fprintf(f, "  %04lx ", o);
        for (unsigned long j = 0; j < 16 && o + j < len; j++) fprintf(f, "%02x ", p[o + j]);
        fprintf(f, "\n");
    }
    fclose(f);
    return 0;
}


/* Grow a TArray of 16-byte {ptr, FName} scenario entries by one:
 * scenlist_req.txt = "<hex TArray addr> <hex fname index> <fname number>".
 * A new heap buffer replaces the old one (which leaks: a probe). */
__declspec(dllexport) int scenlist_append(void *L) {
    (void)L;
    init_dir();
    char path[MAX_PATH];
    snprintf(path, MAX_PATH, "%sscenlist_req.txt", g_dir);
    FILE *fa = fopen(path, "r");
    if (!fa) return 1;
    unsigned long long arr = 0; unsigned long idx = 0, number = 0;
    fscanf(fa, "%llx %lx %lu", &arr, &idx, &number);
    fclose(fa);
    snprintf(path, MAX_PATH, "%stagrefs.log", g_dir);
    FILE *f = fopen(path, "a");
    if (!f) return 2;
    uint8_t *ta = (uint8_t *)arr;
    uint8_t *data = *(uint8_t **)ta;
    int32_t num = *(int32_t *)(ta + 8), max = *(int32_t *)(ta + 12);
    if (!readable(data, (size_t)num * 16)) { fprintf(f, "scenlist: unreadable\n"); fclose(f); return 3; }
    uint8_t *nb = (uint8_t *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (size_t)(num + 1) * 16);
    memcpy(nb, data, (size_t)num * 16);
    memcpy(nb + (size_t)num * 16, data, 8); /* shared pointer from element 0 */
    *(uint32_t *)(nb + (size_t)num * 16 + 8) = (uint32_t)idx;
    *(uint32_t *)(nb + (size_t)num * 16 + 12) = (uint32_t)number;
    *(uint8_t **)ta = nb;
    *(int32_t *)(ta + 8) = num + 1;
    *(int32_t *)(ta + 12) = num + 1;
    fprintf(f, "scenlist: %d -> %d entries, new [%d] fname %08lx:%lu (old max %d)\n", num, num + 1, num, idx, number, max);
    fclose(f);
    return 0;
}


/* Add a row to a UDataTable's RowMap (TMap<FName, uint8*>) by cloning a
 * template row. dt_req.txt = "<hex table> <hex template row> <hex fname idx> <row size> <scenario name>".
 * The clone's FString at +48 (ScenarioName) is replaced by <scenario name>.
 * Layout (UE 5.5 TSet): +0x30 elements {ptr,num,max}, +0x40 inline alloc bits,
 * +0x58 NumBits, +0x70 hash buckets, +0x78 HashSize. Element = {FName, ptr, HashNext, HashIndex}. */
static uint32_t fname_hash(uint32_t id) {
    uint32_t b = id >> 16, o = id & 0xffff;
    return (b << 19) + b + (o << 16) + o + (o >> 4);
}
__declspec(dllexport) int dt_addrow(void *L) {
    (void)L;
    init_dir();
    char path[MAX_PATH];
    snprintf(path, MAX_PATH, "%sdt_req.txt", g_dir);
    FILE *fa = fopen(path, "r");
    if (!fa) return 1;
    unsigned long long table = 0, tmpl = 0; unsigned long idx = 0, rowsize = 0; char name[64] = {0};
    fscanf(fa, "%llx %llx %lx %lu %63s", &table, &tmpl, &idx, &rowsize, name);
    fclose(fa);
    snprintf(path, MAX_PATH, "%stagrefs.log", g_dir);
    FILE *f = fopen(path, "a");
    if (!f) return 2;
    uint8_t *dt = (uint8_t *)table;
    uint8_t *row = (uint8_t *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, rowsize);
    memcpy(row, (void *)tmpl, rowsize);
    int wlen = MultiByteToWideChar(CP_UTF8, 0, name, -1, NULL, 0);
    wchar_t *w = (wchar_t *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (size_t)wlen * 2);
    MultiByteToWideChar(CP_UTF8, 0, name, -1, w, wlen);
    *(wchar_t **)(row + 48) = w;   /* FString: ptr @48, Num @56, Max @60 */
    *(int32_t *)(row + 56) = wlen;
    *(int32_t *)(row + 60) = wlen;
    /* elements */
    uint8_t **eptr = (uint8_t **)(dt + 0x30);
    int32_t *enum_ = (int32_t *)(dt + 0x38), *emax = (int32_t *)(dt + 0x3c);
    int32_t n = *enum_;
    uint8_t *ne = (uint8_t *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (size_t)(n + 1) * 24);
    memcpy(ne, *eptr, (size_t)n * 24);
    uint8_t *e = ne + (size_t)n * 24;
    *(uint32_t *)e = (uint32_t)idx; *(uint32_t *)(e + 4) = 0;
    *(uint8_t **)(e + 8) = row;
    int32_t hashsize = *(int32_t *)(dt + 0x78);
    int32_t *buckets = *(int32_t **)(dt + 0x70);
    uint32_t hb = fname_hash((uint32_t)idx) & (uint32_t)(hashsize - 1);
    *(int32_t *)(e + 16) = buckets[hb];
    *(int32_t *)(e + 20) = (int32_t)hb;
    buckets[hb] = n;
    /* allocation flags: inline 128 bits at +0x40 */
    int32_t *numbits = (int32_t *)(dt + 0x58);
    if (n < 128) { ((uint32_t *)(dt + 0x40))[n / 32] |= 1u << (n % 32); }
    *numbits = n + 1;
    *eptr = ne; *enum_ = n + 1; *emax = n + 1;
    fprintf(f, "dt_addrow: table %p row %p name %ls fname %08lx bucket %u (chain -> %d) elements %d\n",
            dt, row, w, idx, hb, *(int32_t *)(e + 16), n + 1);
    fclose(f);
    return 0;
}


/* BlamCookedTagReferencesEngineSubsystem +0x40: TMap<uint32 tag index, TArray refs>
 * (element 32 B: key u32, pad u32, TArray{ptr,num,max}, HashNext i32, HashIndex i32;
 * TSet header: elements @0x40/0x48/0x4c, inline bits @0x50, NumBits @0x68,
 * buckets ptr @0x80, HashSize @0x88). refs_req.txt = "<hex subsystem> <new key> <template key>".
 * Requires spare capacity (max > num). */
__declspec(dllexport) int refs_addentry(void *L) {
    (void)L;
    init_dir();
    char path[MAX_PATH];
    snprintf(path, MAX_PATH, "%srefs_req.txt", g_dir);
    FILE *fa = fopen(path, "r");
    if (!fa) return 1;
    unsigned long long sub = 0; unsigned long key = 0, tkey = 0;
    fscanf(fa, "%llx %lu %lu", &sub, &key, &tkey);
    fclose(fa);
    snprintf(path, MAX_PATH, "%stagrefs.log", g_dir);
    FILE *f = fopen(path, "a");
    if (!f) return 2;
    uint8_t *o = (uint8_t *)sub;
    uint8_t *data = *(uint8_t **)(o + 0x40);
    int32_t *num = (int32_t *)(o + 0x48), *max = (int32_t *)(o + 0x4c);
    if (*num >= *max) { fprintf(f, "refs_addentry: no capacity %d/%d\n", *num, *max); fclose(f); return 3; }
    uint8_t *tmpl = NULL;
    for (int32_t i = 0; i < *num; i++) if (*(uint32_t *)(data + (size_t)i * 32) == tkey) tmpl = data + (size_t)i * 32;
    if (!tmpl) { fprintf(f, "refs_addentry: template key %lu not found\n", tkey); fclose(f); return 4; }
    int32_t n = *num;
    uint8_t *e = data + (size_t)n * 32;
    memcpy(e, tmpl, 32);
    *(uint32_t *)e = (uint32_t)key;
    int32_t hashsize = *(int32_t *)(o + 0x88);
    int32_t *buckets = *(int32_t **)(o + 0x80);
    uint32_t hb = (uint32_t)key & (uint32_t)(hashsize - 1);
    *(int32_t *)(e + 24) = buckets[hb];
    *(int32_t *)(e + 28) = (int32_t)hb;
    buckets[hb] = n;
    if (n < 128) ((uint32_t *)(o + 0x50))[n / 32] |= 1u << (n % 32);
    *(int32_t *)(o + 0x68) = n + 1;
    *num = n + 1;
    fprintf(f, "refs_addentry: key %lu (template %lu) -> element %d bucket %u chain %d refs num %d\n", key, tkey, n, hb, *(int32_t *)(e + 24), *(int32_t *)(e + 16));
    fclose(f);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) { (void)h; (void)reason; (void)r; return TRUE; }
