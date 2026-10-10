// MJOLNIR Map Registry — a short-name resolver for maps the shipped
// AssetRegistry does not know.
//
// Why this exists (docs/new_scenario_loading.md, "The world gate"):
//
//   The campaign flow starts a mission by travelling to the SHORT name of the
//   row's Unreal world ("B40?SeamlessTravel?ScenarioName=B40..."). In
//   UEngine::Browse, MakeSureMapNameIsValid turns a short name into a package
//   path by asking the AssetRegistry for the first package with that name —
//   IAssetRegistry::GetFirstPackageByName — and only a long path (one with a
//   '/') goes to FPackageName::DoesPackageExist and the IoStore. The registry
//   is loaded once at boot from Meteorite/AssetRegistry.bin, so a world that
//   ships in a mod container is never found, and the travel is refused before
//   any container is asked. Verified on CU4 with call-site probes: the flow's
//   own tag gate passes, travel is requested, and the registry answers "none".
//
// What it does:
//
//   Wraps GetFirstPackageByName (virtual slot 30 of the IAssetRegistry the
//   AssetRegistry module's Get() returns). When the registry misses, the name
//   is looked up among the .umap files listed by the directory indexes of the
//   .utoc containers in Meteorite/Content/Paks — the UE-style layout
//   `mjolnir level bake --standalone --world` writes — and the package path is
//   returned as an FName built the way the engine builds one. Shipped maps
//   never reach the fallback, so nothing else changes.
//
// It also switches the simulation's game engine for converted multiplayer
// maps (mjolnir_megalo_on / _off; docs/re/megalo_engine.md): six byte patches
// in HaloSimulation_tag_release.dll that make the next map load start Reach's
// Megalo engine instead of the campaign, drop the map-variant requirement the
// campaign flow cannot meet, keep the map variant across the start-up zone
// switch, and let the variant file loader read a file at all
// (mjolnir_megalo_variant installs the game mode it reads). A seventh, kept
// even when the switch goes off, lets the game quit from inside a
// multiplayer match. Each site is checked for the exact shipped or patched bytes first,
// so a different build is refused rather than corrupted.
//
// Everything here is CU4-specific (RVAs below, guarded by the PE timestamp or
// the bytes themselves).
// Loaded by mods/MJOLNIRLevelLoader/Scripts/main.lua with package.loadlib.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

#define EXE_TIMESTAMP 0x8a03f777u

// FModuleManager& FModuleManager::Get()
#define RVA_MODULE_MANAGER_GET 0x36D29F0u
// IModuleInterface* FModuleManager::GetModule(FName)
#define RVA_MODULE_MANAGER_GET_MODULE 0x36D3540u
// Hash of a name view, as the FName constructor wants it.
#define RVA_NAME_HASH 0x3709650u
// FName construction from a name view: (FName* out, view*, EFindName, hash)
#define RVA_NAME_MAKE 0x36FCC60u

// IModuleInterface: 8 virtuals; FAssetRegistryModule::Get() is the ninth.
#define MODULE_SLOT_GET 8
// IAssetRegistry::GetFirstPackageByName(FStringView) — FName returned
// through a hidden pointer.
#define REGISTRY_SLOT_FIRST_PACKAGE 30

#define MAX_MAPS 8192
#define MAX_PATH_CHARS 512

typedef struct {
    const wchar_t *data;
    int32_t len;
} string_view_t;

typedef struct {
    const wchar_t *ptr;
    int32_t len;
    uint8_t wide;
    uint8_t pad[3];
} name_view_t;

typedef void *(__fastcall *first_pkg_fn)(void *self, uint64_t *out, const string_view_t *name);
typedef void *(__fastcall *manager_get_fn)(void);
typedef void *(__fastcall *get_module_fn)(void *manager, uint64_t name);
typedef void *(__fastcall *module_get_fn)(void *module);
typedef uint64_t(__fastcall *name_hash_fn)(const wchar_t *str, void *tail);
typedef void(__fastcall *name_make_fn)(uint64_t *out, name_view_t *view, int find, uint64_t hash);

typedef struct {
    wchar_t leaf[128];
    wchar_t package[MAX_PATH_CHARS];
} map_entry_t;

static CRITICAL_SECTION g_cs;
static char g_log[MAX_PATH];
static char g_paks[MAX_PATH];
static uint8_t *g_base;
static void **g_vtable;
static first_pkg_fn g_orig;
static int g_hooked;
static map_entry_t g_maps[MAX_MAPS];
static int g_nmaps;
static long g_misses_logged;

static void Log(const char *fmt, ...) {
    va_list ap;
    EnterCriticalSection(&g_cs);
    FILE *f = NULL;
    if (fopen_s(&f, g_log, "a") == 0 && f) {
        va_start(ap, fmt);
        vfprintf(f, fmt, ap);
        va_end(ap);
        fputc('\n', f);
        fclose(f);
    }
    LeaveCriticalSection(&g_cs);
}

// ----------------------------------------------------------------- FName

static uint64_t make_fname(const wchar_t *s) {
    name_view_t v;
    v.ptr = s;
    v.len = (int32_t)wcslen(s);
    v.wide = 0;
    for (int32_t i = 0; i < v.len; i++)
        if (s[i] >= 0x80) v.wide = 1;
    memset(v.pad, 0, sizeof v.pad);
    uint64_t hash = ((name_hash_fn)(g_base + RVA_NAME_HASH))(s, &v.len);
    uint64_t out = 0;
    ((name_make_fn)(g_base + RVA_NAME_MAKE))(&out, &v, 1, hash);
    return out;
}

// ----------------------------------------------------------- the hook

static void *__fastcall hooked_first_package(void *self, uint64_t *out, const string_view_t *name) {
    void *r = g_orig(self, out, name);
    if (out[0] != 0 || !name || name->len <= 0 || name->len >= 127) return r;
    wchar_t leaf[128];
    memcpy(leaf, name->data, (size_t)name->len * sizeof(wchar_t));
    leaf[name->len] = 0;
    EnterCriticalSection(&g_cs);
    const wchar_t *package = NULL;
    for (int i = 0; i < g_nmaps; i++) {
        if (_wcsicmp(leaf, g_maps[i].leaf) == 0) {
            package = g_maps[i].package;
            break;
        }
    }
    LeaveCriticalSection(&g_cs);
    if (package) {
        out[0] = make_fname(package);
        Log("%ls -> %ls (container map)", leaf, package);
    } else if (g_misses_logged < 50) {
        InterlockedIncrement(&g_misses_logged);
        Log("%ls -> not a shipped package and not in any container", leaf);
    }
    return r;
}

// --------------------------------------------- .utoc directory indexes

typedef struct {
    const uint8_t *p;
    size_t len;
    size_t pos;
    int bad;
} reader_t;

static uint32_t rd_u32(reader_t *r) {
    if (r->pos + 4 > r->len) {
        r->bad = 1;
        return 0;
    }
    uint32_t v;
    memcpy(&v, r->p + r->pos, 4);
    r->pos += 4;
    return v;
}

// FString: i32 length counting the terminator; negative = UTF-16.
static int rd_fstring(reader_t *r, wchar_t *out, size_t cap) {
    int32_t n = (int32_t)rd_u32(r);
    out[0] = 0;
    if (r->bad) return 0;
    if (n == 0) return 1;
    if (n < 0) {
        size_t chars = (size_t)(-n);
        if (r->pos + chars * 2 > r->len) {
            r->bad = 1;
            return 0;
        }
        size_t copy = chars < cap ? chars : cap - 1;
        memcpy(out, r->p + r->pos, copy * 2);
        out[copy] = 0;
        r->pos += chars * 2;
    } else {
        size_t chars = (size_t)n;
        if (r->pos + chars > r->len) {
            r->bad = 1;
            return 0;
        }
        size_t copy = chars < cap ? chars : cap - 1;
        for (size_t i = 0; i < copy; i++) out[i] = (wchar_t)r->p[r->pos + i];
        out[copy] = 0;
        r->pos += chars;
    }
    return 1;
}

static void add_map(const wchar_t *mount, const wchar_t *rel) {
    // Only worlds, only under a content root we can name. World Partition
    // cells (`<World>/_Generated_/<hash>.umap`, thousands per shipped
    // container) are never a travel target.
    size_t n = wcslen(rel);
    if (n < 6 || _wcsicmp(rel + n - 5, L".umap") != 0) return;
    if (wcsstr(rel, L"/_Generated_/") || _wcsnicmp(rel, L"_Generated_/", 12) == 0) return;
    wchar_t full[MAX_PATH_CHARS];
    if (swprintf(full, MAX_PATH_CHARS, L"%ls%ls", mount, rel) < 0) return;
    const wchar_t *root = NULL;
    const wchar_t *rest = NULL;
    static const struct {
        const wchar_t *prefix;
        const wchar_t *root;
    } ROOTS[] = {
        {L"../../../Meteorite/Content/", L"/Game/"},
        {L"../../../Engine/Content/", L"/Engine/"},
    };
    for (size_t i = 0; i < sizeof ROOTS / sizeof ROOTS[0]; i++) {
        size_t pl = wcslen(ROOTS[i].prefix);
        if (_wcsnicmp(full, ROOTS[i].prefix, pl) == 0) {
            root = ROOTS[i].root;
            rest = full + pl;
            break;
        }
    }
    if (!root) return;
    wchar_t package[MAX_PATH_CHARS];
    if (swprintf(package, MAX_PATH_CHARS, L"%ls%ls", root, rest) < 0) return;
    package[wcslen(package) - 5] = 0; // drop .umap
    const wchar_t *leaf = wcsrchr(package, L'/');
    leaf = leaf ? leaf + 1 : package;
    if (wcslen(leaf) >= 128) return;
    for (int i = 0; i < g_nmaps; i++)
        if (_wcsicmp(g_maps[i].package, package) == 0) return;
    if (g_nmaps >= MAX_MAPS) {
        static long warned;
        if (InterlockedIncrement(&warned) == 1) Log("map table full at %d; %ls and later worlds not indexed", MAX_MAPS, package);
        return;
    }
    wcscpy_s(g_maps[g_nmaps].leaf, 128, leaf);
    wcscpy_s(g_maps[g_nmaps].package, MAX_PATH_CHARS, package);
    g_nmaps++;
}

// FIoDirectoryIndexResource: mount point, directory entries {name, first
// child, next sibling, first file}, file entries {name, next file, user data},
// string table. Indexes are u32 with 0xffffffff for none.
static int walk_directory_index(const uint8_t *blob, size_t len, const char *toc_name) {
    reader_t r = {blob, len, 0, 0};
    wchar_t mount[MAX_PATH_CHARS];
    if (!rd_fstring(&r, mount, MAX_PATH_CHARS)) return 0;
    uint32_t ndirs = rd_u32(&r);
    if (r.bad || r.pos + (size_t)ndirs * 16 > len) return 0;
    const uint8_t *dirs = blob + r.pos;
    r.pos += (size_t)ndirs * 16;
    uint32_t nfiles = rd_u32(&r);
    if (r.bad || r.pos + (size_t)nfiles * 12 > len) return 0;
    const uint8_t *files = blob + r.pos;
    r.pos += (size_t)nfiles * 12;
    uint32_t nstrings = rd_u32(&r);
    if (r.bad || nstrings > 1000000) return 0;
    wchar_t **strings = (wchar_t **)calloc(nstrings, sizeof(wchar_t *));
    if (!strings) return 0;
    for (uint32_t i = 0; i < nstrings; i++) {
        wchar_t tmp[MAX_PATH_CHARS];
        if (!rd_fstring(&r, tmp, MAX_PATH_CHARS)) break;
        strings[i] = _wcsdup(tmp);
    }
    int added = 0;
    if (!r.bad && ndirs > 0) {
        // Iterative walk: (directory index, path prefix) pairs.
        typedef struct {
            uint32_t dir;
            wchar_t prefix[MAX_PATH_CHARS];
        } frame_t;
        frame_t *stack = (frame_t *)calloc(ndirs + 1, sizeof(frame_t));
        if (stack) {
            int sp = 0;
            stack[sp].dir = 0;
            stack[sp].prefix[0] = 0;
            sp++;
            int before = g_nmaps;
            while (sp > 0 && sp <= (int)ndirs) {
                frame_t f = stack[--sp];
                if (f.dir >= ndirs) continue;
                uint32_t d[4];
                memcpy(d, dirs + (size_t)f.dir * 16, 16);
                wchar_t path[MAX_PATH_CHARS];
                if (d[0] != 0xffffffffu && d[0] < nstrings && strings[d[0]])
                    swprintf(path, MAX_PATH_CHARS, L"%ls%ls/", f.prefix, strings[d[0]]);
                else
                    wcscpy_s(path, MAX_PATH_CHARS, f.prefix);
                uint32_t fi = d[3];
                uint32_t guard = 0;
                while (fi != 0xffffffffu && fi < nfiles && guard++ < nfiles) {
                    uint32_t e[3];
                    memcpy(e, files + (size_t)fi * 12, 12);
                    if (e[0] != 0xffffffffu && e[0] < nstrings && strings[e[0]]) {
                        wchar_t rel[MAX_PATH_CHARS];
                        if (swprintf(rel, MAX_PATH_CHARS, L"%ls%ls", path, strings[e[0]]) >= 0) add_map(mount, rel);
                    }
                    fi = e[1];
                }
                if (d[2] != 0xffffffffu && sp <= (int)ndirs) {
                    stack[sp].dir = d[2];
                    wcscpy_s(stack[sp].prefix, MAX_PATH_CHARS, f.prefix);
                    sp++;
                }
                if (d[1] != 0xffffffffu && sp <= (int)ndirs) {
                    stack[sp].dir = d[1];
                    wcscpy_s(stack[sp].prefix, MAX_PATH_CHARS, path);
                    sp++;
                }
            }
            added = g_nmaps - before;
            free(stack);
        }
    }
    for (uint32_t i = 0; i < nstrings; i++) free(strings[i]);
    free(strings);
    if (added) Log("%s: %d world(s) indexed", toc_name, added);
    return added;
}

// FIoStoreTocHeader (version 3): the directory index follows the chunk ids,
// offsets, compression blocks, method names and optional signatures.
static void index_toc(const char *path, const char *name) {
    FILE *f = NULL;
    if (fopen_s(&f, path, "rb") != 0 || !f) return;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size < 144) {
        fclose(f);
        return;
    }
    uint8_t *blob = (uint8_t *)malloc((size_t)size);
    if (!blob) {
        fclose(f);
        return;
    }
    size_t got = fread(blob, 1, (size_t)size, f);
    fclose(f);
    if (got != (size_t)size || memcmp(blob, "-==--==--==--==-", 16) != 0) {
        free(blob);
        return;
    }
    uint32_t u32[25];
    memcpy(u32, blob, sizeof u32);
    size_t header_size = u32[5];
    size_t entry_count = u32[6];
    size_t block_count = u32[7];
    size_t block_entry_size = u32[8];
    size_t method_count = u32[9];
    size_t method_length = u32[10];
    size_t dir_index_size = u32[12];
    uint8_t version = blob[16];
    uint8_t flags = blob[80];
    size_t perfect_hash_seeds = u32[21];
    size_t chunks_without_perfect_hash = u32[24];
    // chunk ids (12 each), offsets (10 each), then from toc version 4 the
    // perfect-hash seeds and from 5 the overflow list, then the blocks and
    // the compression method names.
    size_t pos = header_size + entry_count * 12 + entry_count * 10;
    if (version >= 4) pos += perfect_hash_seeds * 4;
    if (version >= 5) pos += chunks_without_perfect_hash * 4;
    pos += block_count * block_entry_size + method_count * method_length;
    if (flags & 0x04) { // signed
        if (pos + 4 <= (size_t)size) {
            uint32_t hash_size;
            memcpy(&hash_size, blob + pos, 4);
            pos += 4 + (size_t)hash_size * 2 + (size_t)hash_size * block_count;
        }
    }
    if ((flags & 0x08) && !(flags & 0x02) && dir_index_size > 0 && pos + dir_index_size <= (size_t)size)
        walk_directory_index(blob + pos, dir_index_size, name);
    free(blob);
}

static void index_paks(void) {
    char pattern[MAX_PATH];
    if (snprintf(pattern, MAX_PATH, "%s*.utoc", g_paks) < 0) return;
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE) {
        Log("no containers under %s", g_paks);
        return;
    }
    int tocs = 0;
    do {
        char path[MAX_PATH];
        if (snprintf(path, MAX_PATH, "%s%s", g_paks, fd.cFileName) > 0) {
            index_toc(path, fd.cFileName);
            tocs++;
        }
    } while (FindNextFileA(h, &fd));
    FindClose(h);
    Log("%d container(s) scanned, %d world(s) known", tocs, g_nmaps);
}

// --------------------------------------------------------------- setup

static void init_paths(void) {
    HMODULE me = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&init_paths, &me);
    GetModuleFileNameA(me, g_log, MAX_PATH);
    char *p = strrchr(g_log, '\\');
    if (p) *(p + 1) = 0;
    strcat_s(g_log, MAX_PATH, "map_registry.log");

    // <game>/Meteorite/Binaries/Win64/<exe> -> <game>/Meteorite/Content/Paks/
    GetModuleFileNameA(NULL, g_paks, MAX_PATH);
    for (int i = 0; i < 3; i++) {
        p = strrchr(g_paks, '\\');
        if (p) *p = 0;
    }
    strcat_s(g_paks, MAX_PATH, "\\Content\\Paks\\");
}

static int swap_slot(void **slot, void *expect, void *replacement) {
    if (*slot != expect) return 0;
    DWORD old;
    if (!VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &old)) return 0;
    InterlockedExchangePointer(slot, replacement);
    VirtualProtect(slot, sizeof(void *), old, &old);
    return 1;
}

static void ensure_init(void) {
    static int inited = 0;
    if (!inited) {
        InitializeCriticalSection(&g_cs);
        init_paths();
        inited = 1;
    }
}

// Lua C function: returns 0 results. Idempotent.
__declspec(dllexport) int mjolnir_map_registry_open(void *L) {
    (void)L;
    ensure_init();
    if (g_hooked) {
        Log("already open");
        return 0;
    }
    g_base = (uint8_t *)GetModuleHandleA(NULL);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)g_base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(g_base + dos->e_lfanew);
    if (nt->FileHeader.TimeDateStamp != EXE_TIMESTAMP) {
        Log("refused: exe timestamp %08x is not CU4 (%08x); the RVAs would be wrong", nt->FileHeader.TimeDateStamp,
            EXE_TIMESTAMP);
        return 0;
    }
    uint64_t module_name = make_fname(L"AssetRegistry");
    void *manager = ((manager_get_fn)(g_base + RVA_MODULE_MANAGER_GET))();
    void *module = manager ? ((get_module_fn)(g_base + RVA_MODULE_MANAGER_GET_MODULE))(manager, module_name) : NULL;
    if (!module) {
        Log("AssetRegistry module not found (manager %p)", manager);
        return 0;
    }
    void **module_vt = *(void ***)module;
    void *registry = ((module_get_fn)module_vt[MODULE_SLOT_GET])(module);
    if (!registry) {
        Log("AssetRegistry module has no registry");
        return 0;
    }
    g_vtable = *(void ***)registry;
    g_orig = (first_pkg_fn)g_vtable[REGISTRY_SLOT_FIRST_PACKAGE];
    index_paks();
    g_hooked = swap_slot(&g_vtable[REGISTRY_SLOT_FIRST_PACKAGE], (void *)g_orig, (void *)hooked_first_package);
    Log("registry %p vtable rva %llx: GetFirstPackageByName %s", registry,
        (unsigned long long)((uint8_t *)g_vtable - g_base), g_hooked ? "wrapped" : "NOT wrapped (slot changed?)");
    return 0;
}

// Re-read the containers (a map installed while the game runs).
__declspec(dllexport) int mjolnir_map_registry_rescan(void *L) {
    (void)L;
    if (!g_hooked) return 0;
    EnterCriticalSection(&g_cs);
    g_nmaps = 0;
    LeaveCriticalSection(&g_cs);
    index_paks();
    return 0;
}

// ------------------------------------------------- mounting a map live
//
// A map downloaded while the game runs (docs/live_map_install.md): its
// containers are mounted the way the engine mounts a chunk it downloads, by
// FCoreDelegates::MountPak, which FPakPlatformFile binds at startup to
// HandleMountPakDelegate(const FString&, int32 order). That mounts the .pak,
// then its .utoc/.ucas sibling with the IoDispatcher and the package store
// (whose container list it flags for an update), then fires
// OnPakFileMounted, so it is the whole of what boot does for one file.
//
// The delegate's storage is a pointer to its bound instance: vtable, handle
// at +0x10, the FPakPlatformFile at +0x18, the method at +0x20 (CU4
// FUN_144690200 binds it; the method is checked before it is called).

// FCoreDelegates::MountPak (TDelegate inline storage: instance pointer)
#define RVA_MOUNT_PAK_DELEGATE 0xD349040u
// FPakPlatformFile::HandleMountPakDelegate
#define RVA_MOUNT_PAK_HANDLER 0x4694C00u

typedef struct {
    wchar_t *data;
    int32_t num;
    int32_t max;
} fstring_t;

typedef void *(__fastcall *mount_pak_fn)(void *pak_file, const fstring_t *path, int32_t order);

static void native_path(const char *file, char *out, size_t cap) {
    strcpy_s(out, cap, g_log);
    char *slash = strrchr(out, '\\');
    if (slash) *(slash + 1) = 0;
    strcat_s(out, cap, file);
}

static void write_reply(const char *file, const char *text) {
    char path[MAX_PATH];
    native_path(file, path, sizeof path);
    FILE *f = NULL;
    if (fopen_s(&f, path, "wb") == 0 && f) {
        fputs(text, f);
        fclose(f);
    }
}

// Mount one .pak (and its IoStore sibling); 1 on success.
static int mount_one(const wchar_t *pak, char *why, size_t why_cap) {
    void **storage = (void **)(g_base + RVA_MOUNT_PAK_DELEGATE);
    uint8_t *instance = (uint8_t *)*storage;
    if (!instance) {
        snprintf(why, why_cap, "MountPak is not bound");
        return 0;
    }
    void *pak_file = *(void **)(instance + 0x18);
    void *method = *(void **)(instance + 0x20);
    if (method != (void *)(g_base + RVA_MOUNT_PAK_HANDLER) || !pak_file) {
        snprintf(why, why_cap, "MountPak is bound to %p (expected %p)", method,
                 (void *)(g_base + RVA_MOUNT_PAK_HANDLER));
        return 0;
    }
    // The engine copies what it keeps; the string only has to outlive the call.
    wchar_t buffer[MAX_PATH_CHARS];
    wcscpy_s(buffer, MAX_PATH_CHARS, pak);
    fstring_t path = {buffer, (int32_t)wcslen(buffer) + 1, MAX_PATH_CHARS};
    void *mounted = ((mount_pak_fn)(g_base + RVA_MOUNT_PAK_HANDLER))(pak_file, &path, -1);
    if (!mounted) {
        snprintf(why, why_cap, "the engine refused %ls", pak);
        return 0;
    }
    return 1;
}

// Lua C function, 0 results. `mount_request.txt` beside this DLL lists one
// .pak per line, as the engine names them (`../../../Meteorite/Content/
// Paks/<file>.pak`, relative to the exe's folder); each is mounted in turn,
// the world index is re-read, and `mount_reply.txt` gets `ok <n>` or
// `error <why>`.
__declspec(dllexport) int mjolnir_mount_paks(void *L) {
    (void)L;
    ensure_init();
    if (!g_base) g_base = (uint8_t *)GetModuleHandleA(NULL);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)g_base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(g_base + dos->e_lfanew);
    if (nt->FileHeader.TimeDateStamp != EXE_TIMESTAMP) {
        write_reply("mount_reply.txt", "error this game build is not CU4; maps cannot be mounted live");
        return 0;
    }
    char request[MAX_PATH];
    native_path("mount_request.txt", request, sizeof request);
    FILE *f = NULL;
    if (fopen_s(&f, request, "rb") != 0 || !f) {
        write_reply("mount_reply.txt", "error no mount_request.txt");
        return 0;
    }
    char line[MAX_PATH_CHARS];
    int mounted = 0;
    char why[MAX_PATH_CHARS + 64] = "";
    while (fgets(line, sizeof line, f)) {
        size_t n = strlen(line);
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r' || line[n - 1] == ' ')) line[--n] = 0;
        if (!n) continue;
        wchar_t wide[MAX_PATH_CHARS];
        if (!MultiByteToWideChar(CP_UTF8, 0, line, -1, wide, MAX_PATH_CHARS)) continue;
        if (!mount_one(wide, why, sizeof why)) break;
        Log("mounted %s", line);
        mounted++;
    }
    fclose(f);
    if (g_hooked) mjolnir_map_registry_rescan(NULL);
    char reply[sizeof why + 32];
    if (why[0]) {
        Log("mount: %s (%d mounted first)", why, mounted);
        snprintf(reply, sizeof reply, "error %s", why);
    } else {
        snprintf(reply, sizeof reply, "ok %d", mounted);
    }
    write_reply("mount_reply.txt", reply);
    return 0;
}

// ------------------------------------------ registering a map live
//
// A map the cooked registration container (pakchunk996) did not list at boot
// gets its DT_Scenarios row and its campaign ScenarioList handle here, in
// memory, the same records `blam_pack::scenario::register` cooks: a clone of
// a template row with the codename's world, ScenarioName and MapGuid.
// StartScenario and SetAndBeginCampaign read both when a map starts, so a row
// added before the start is as good as a cooked one
// (docs/live_map_install.md).
//
// Everything is allocated through the engine's GMalloc, so the engine can
// free it at shutdown like its own (HeapAlloc'd probe buffers crashed the
// exit; docs/new_scenario_loading.md).

// FMalloc* GMalloc; Malloc(count, alignment) at vtable +0x28, Free at +0x48.
#define RVA_GMALLOC 0xD4B7428u
#define GMALLOC_MALLOC 0x28
#define GMALLOC_FREE 0x48

// BlamScenarioDataTableRow (176 bytes): +8 UnrealLevel (FSoftObjectPtr: weak
// ptr, package FName, asset FName, sub-path FString), +48 ScenarioName,
// +64 MapGuid, +80 / +96 title / description (FText).
#define ROW_SIZE 176
#define ROW_WORLD_WEAK 8
#define ROW_WORLD_PACKAGE 16
#define ROW_WORLD_ASSET 24
#define ROW_WORLD_SUBPATH 32
#define ROW_SCENARIO_NAME 48
#define ROW_MAP_GUID 64
#define ROW_TITLE 80
#define ROW_DESCRIPTION 96

// UDataTable::RowMap, a TMap<FName, uint8*>: the sparse array's elements
// {ptr, num, max} at +0x30, its allocation bits (4 inline dwords) at +0x40,
// NumBits/MaxBits at +0x58/+0x5c, free list at +0x60/+0x64; the hash's
// buckets at +0x70 and their count at +0x78. Element: FName, row pointer,
// next in bucket, bucket index (24 bytes).
#define DT_ELEMENTS 0x30
#define DT_BITS 0x40
#define DT_BITS_HEAP 0x50
#define DT_NUM_BITS 0x58
#define DT_MAX_BITS 0x5c
#define DT_NUM_FREE 0x64
#define DT_BUCKETS 0x70
#define DT_HASH_SIZE 0x78
#define DT_ELEMENT 24

// UBlamCampaignDataAsset::ScenarioList, TArray<FDataTableRowHandle {table, FName}>.
#define CAMPAIGN_SCENARIO_LIST 0x40

typedef struct {
    uint32_t index;
    uint32_t number;
} fname_t;

// The row alone is not enough: at boot
// UBlamFrontendLevelsEngineGlueSubsystem::BuildRuntimeCachesFromBuiltInMapInfoDataAsset
// (CU4 0x7B7D180) passes every DT_Scenarios row to a cache insert (0x7BAC140:
// world path, MapGuid and per-map entries the simulation's level lookups go
// through), then stamps each campaign map's entry with its campaign's id. A
// row added later has no entry, and the simulation never starts the map
// ("not in a game"; verified 2026-10-09). So the insert is called for the
// new row too, and the campaign id copied from the template's entry.
//
// The subsystem: 0x7B7DFC0 returns it. Its per-map entries: a sparse array
// at +0x138 {ptr, num}, 0x14c bytes each, keyed by MapGuid at +0, campaign id at
// +0x120 (16 bytes).
#define RVA_LEVELS_GLUE_GET 0x7B7DFC0u
#define RVA_LEVELS_GLUE_ADD_ROW 0x7BAC140u
#define GLUE_MAPS 0x138
#define GLUE_MAP_SIZE 0x14c
#define GLUE_MAP_GUID 0
#define GLUE_MAP_CAMPAIGN 0x120

typedef void *(__fastcall *glue_get_fn)(void);
typedef void(__fastcall *glue_add_row_fn)(void **subsystem, void *row_element, void *row);

static uint8_t *glue_entry(uint8_t *glue, const uint8_t guid[16]) {
    uint8_t *maps = *(uint8_t **)(glue + GLUE_MAPS);
    int32_t n = *(int32_t *)(glue + GLUE_MAPS + 8);
    for (int32_t i = 0; i < n; i++) {
        uint8_t *e = maps + (size_t)i * GLUE_MAP_SIZE;
        if (memcmp(e + GLUE_MAP_GUID, guid, 16) == 0) return e;
    }
    return NULL;
}

// Give the frontend levels glue the new row, as boot gives it every cooked one.
static int glue_add(fname_t name, uint8_t *row, const uint8_t *tmpl, char *why, size_t cap) {
    uint8_t *glue = (uint8_t *)((glue_get_fn)(g_base + RVA_LEVELS_GLUE_GET))();
    if (!glue) {
        snprintf(why, cap, "the frontend levels subsystem is not up");
        return 0;
    }
    if (glue_entry(glue, row + ROW_MAP_GUID)) return 1;
    uint8_t element[DT_ELEMENT] = {0};
    memcpy(element, &name, 8);
    *(uint8_t **)(element + 8) = row;
    void *self = glue;
    ((glue_add_row_fn)(g_base + RVA_LEVELS_GLUE_ADD_ROW))(&self, element, row);
    uint8_t *mine = glue_entry(glue, row + ROW_MAP_GUID);
    if (!mine) {
        snprintf(why, cap, "the frontend levels subsystem did not take the row");
        return 0;
    }
    uint8_t *theirs = glue_entry(glue, tmpl + ROW_MAP_GUID);
    if (theirs) memcpy(mine + GLUE_MAP_CAMPAIGN, theirs + GLUE_MAP_CAMPAIGN, 16);
    return 1;
}

typedef void *(__fastcall *malloc_fn)(void *self, size_t count, uint32_t alignment);
typedef void(__fastcall *free_fn)(void *self, void *p);

static void *engine_malloc(size_t n) {
    void *gmalloc = *(void **)(g_base + RVA_GMALLOC);
    if (!gmalloc) return NULL;
    void **vt = *(void ***)gmalloc;
    void *p = ((malloc_fn)vt[GMALLOC_MALLOC / 8])(gmalloc, n, 16);
    if (p) memset(p, 0, n);
    return p;
}

static void engine_free(void *p) {
    void *gmalloc = *(void **)(g_base + RVA_GMALLOC);
    if (!gmalloc || !p) return;
    void **vt = *(void ***)gmalloc;
    ((free_fn)vt[GMALLOC_FREE / 8])(gmalloc, p);
}

// TSet<FName> bucket hash: GetTypeHash of the comparison index (checked
// against every shipped row by the 2026-09 probe).
static uint32_t fname_bucket_hash(uint32_t id) {
    uint32_t b = id >> 16, o = id & 0xffff;
    return (b << 19) + b + (o << 16) + o + (o >> 4);
}

static int bit_set(uint8_t *dt, int32_t i) {
    int32_t max_bits = *(int32_t *)(dt + DT_MAX_BITS);
    uint32_t *words = max_bits > 128 ? *(uint32_t **)(dt + DT_BITS_HEAP) : (uint32_t *)(dt + DT_BITS);
    return (words[i / 32] >> (i % 32)) & 1;
}

static uint8_t *find_row(uint8_t *dt, fname_t name) {
    uint8_t *elements = *(uint8_t **)(dt + DT_ELEMENTS);
    int32_t n = *(int32_t *)(dt + DT_ELEMENTS + 8);
    for (int32_t i = 0; i < n; i++) {
        if (!bit_set(dt, i)) continue;
        uint8_t *e = elements + (size_t)i * DT_ELEMENT;
        if (*(uint32_t *)e == name.index && *(uint32_t *)(e + 4) == name.number) return *(uint8_t **)(e + 8);
    }
    return NULL;
}

// An FText copied by value has to hold its own reference: TRefCountPtr<ITextData>
// at +0, whose shared reference count lives in the text data at +8.
static void text_addref(uint8_t *text) {
    uint8_t *data = *(uint8_t **)text;
    if (data) InterlockedIncrement((volatile LONG *)(data + 8));
}

static wchar_t *engine_wstring(const wchar_t *s, int32_t *num) {
    *num = (int32_t)wcslen(s) + 1;
    wchar_t *w = (wchar_t *)engine_malloc((size_t)*num * sizeof(wchar_t));
    if (w) memcpy(w, s, (size_t)*num * sizeof(wchar_t));
    return w;
}

// `blam_pack::scenario::map_guid`: two FNV-1a 64 hashes over "MJOLNIR map <CODE>".
static void map_guid(const char *code, uint8_t out[16]) {
    char text[64];
    snprintf(text, sizeof text, "MJOLNIR map %s", code);
    uint64_t seeds[2] = {0xcbf29ce484222325ull, 0x84222325cbf29ce4ull};
    for (int k = 0; k < 2; k++) {
        uint64_t h = seeds[k];
        for (const char *p = text; *p; p++) {
            h ^= (uint8_t)(*p >= 'a' && *p <= 'z' ? *p - 32 : *p);
            h *= 0x100000001b3ull;
        }
        memcpy(out + k * 8, &h, 8);
    }
}

static int add_row(uint8_t *dt, fname_t name, uint8_t *row, char *why, size_t cap) {
    int32_t n = *(int32_t *)(dt + DT_ELEMENTS + 8);
    int32_t max = *(int32_t *)(dt + DT_ELEMENTS + 12);
    if (*(int32_t *)(dt + DT_NUM_FREE) != 0) {
        snprintf(why, cap, "the row map has free slots (%d); not handled", *(int32_t *)(dt + DT_NUM_FREE));
        return 0;
    }
    if (n + 1 > *(int32_t *)(dt + DT_MAX_BITS)) {
        snprintf(why, cap, "the row map's allocation bits are full (%d)", n);
        return 0;
    }
    uint8_t **elements = (uint8_t **)(dt + DT_ELEMENTS);
    if (n >= max) {
        int32_t grown = max + 16;
        uint8_t *fresh = (uint8_t *)engine_malloc((size_t)grown * DT_ELEMENT);
        if (!fresh) {
            snprintf(why, cap, "out of memory");
            return 0;
        }
        memcpy(fresh, *elements, (size_t)n * DT_ELEMENT);
        uint8_t *old = *elements;
        *elements = fresh;
        *(int32_t *)(dt + DT_ELEMENTS + 12) = grown;
        engine_free(old);
    }
    uint8_t *e = *elements + (size_t)n * DT_ELEMENT;
    memcpy(e, &name, 8);
    *(uint8_t **)(e + 8) = row;
    int32_t hash_size = *(int32_t *)(dt + DT_HASH_SIZE);
    int32_t *buckets = hash_size > 1 ? *(int32_t **)(dt + DT_BUCKETS) : (int32_t *)(dt + DT_BUCKETS);
    uint32_t bucket = fname_bucket_hash(name.index) & (uint32_t)(hash_size - 1);
    *(int32_t *)(e + 16) = buckets[bucket];
    *(int32_t *)(e + 20) = (int32_t)bucket;
    buckets[bucket] = n;
    int32_t max_bits = *(int32_t *)(dt + DT_MAX_BITS);
    uint32_t *words = max_bits > 128 ? *(uint32_t **)(dt + DT_BITS_HEAP) : (uint32_t *)(dt + DT_BITS);
    words[n / 32] |= 1u << (n % 32);
    *(int32_t *)(dt + DT_NUM_BITS) = n + 1;
    *(int32_t *)(dt + DT_ELEMENTS + 8) = n + 1;
    return 1;
}

static int add_handle(uint8_t *campaign, uint8_t *dt, fname_t name, char *why, size_t cap) {
    uint8_t **data = (uint8_t **)(campaign + CAMPAIGN_SCENARIO_LIST);
    int32_t *num = (int32_t *)(campaign + CAMPAIGN_SCENARIO_LIST + 8);
    int32_t *max = (int32_t *)(campaign + CAMPAIGN_SCENARIO_LIST + 12);
    for (int32_t i = 0; i < *num; i++) {
        uint8_t *h = *data + (size_t)i * 16;
        if (*(uint32_t *)(h + 8) == name.index && *(uint32_t *)(h + 12) == name.number) return 1;
    }
    if (*num >= *max) {
        int32_t grown = *max + 16;
        uint8_t *fresh = (uint8_t *)engine_malloc((size_t)grown * 16);
        if (!fresh) {
            snprintf(why, cap, "out of memory");
            return 0;
        }
        memcpy(fresh, *data, (size_t)*num * 16);
        uint8_t *old = *data;
        *data = fresh;
        *max = grown;
        engine_free(old);
    }
    uint8_t *h = *data + (size_t)*num * 16;
    *(uint8_t **)h = dt;
    memcpy(h + 8, &name, 8);
    (*num)++;
    return 1;
}

static fname_t fname_of(const wchar_t *s) {
    uint64_t v = make_fname(s);
    fname_t f;
    memcpy(&f, &v, 8);
    return f;
}

// Lua C function, 0 results. `scenario_request.txt` beside this DLL:
// `<DT_Scenarios address> <campaign data asset address> <CODE> <template CODE>`
// (hex addresses, as UE4SS's GetAddress gives them). The row clones the
// template's (an installed map of ours: its preview, insertion points and
// unlock tag) with the world /Game/Levels/Halo1/Solo/<CODE>/<CODE>.<CODE>,
// ScenarioName <CODE> and the codename's MapGuid. `scenario_reply.txt`:
// `ok added`, `ok present` or `error <why>`.
__declspec(dllexport) int mjolnir_scenario_add(void *L) {
    (void)L;
    ensure_init();
    if (!g_base) g_base = (uint8_t *)GetModuleHandleA(NULL);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)g_base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(g_base + dos->e_lfanew);
    if (nt->FileHeader.TimeDateStamp != EXE_TIMESTAMP) {
        write_reply("scenario_reply.txt", "error this game build is not CU4");
        return 0;
    }
    char request[MAX_PATH];
    native_path("scenario_request.txt", request, sizeof request);
    FILE *f = NULL;
    unsigned long long table = 0, campaign = 0;
    char code[8] = "", from[8] = "";
    if (fopen_s(&f, request, "rb") != 0 || !f) {
        write_reply("scenario_reply.txt", "error no scenario_request.txt");
        return 0;
    }
    int got = fscanf_s(f, "%llx %llx %7s %7s", &table, &campaign, code, (unsigned)sizeof code, from,
                       (unsigned)sizeof from);
    fclose(f);
    if (got != 4 || !table || !campaign) {
        write_reply("scenario_reply.txt", "error a malformed scenario_request.txt");
        return 0;
    }
    for (char *p = code; *p; p++) {
        if (!((*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9'))) {
            write_reply("scenario_reply.txt", "error not a map code");
            return 0;
        }
    }
    uint8_t *dt = (uint8_t *)table;
    wchar_t wcode[8], wfrom[8], package[128], asset[16];
    MultiByteToWideChar(CP_UTF8, 0, code, -1, wcode, 8);
    MultiByteToWideChar(CP_UTF8, 0, from, -1, wfrom, 8);
    fname_t name = fname_of(wcode);
    char why[256] = "";
    if (find_row(dt, name)) {
        if (!add_handle((uint8_t *)campaign, dt, name, why, sizeof why)) {
            write_reply("scenario_reply.txt", why);
            return 0;
        }
        write_reply("scenario_reply.txt", "ok present");
        return 0;
    }
    uint8_t *tmpl = find_row(dt, fname_of(wfrom));
    if (!tmpl) {
        snprintf(why, sizeof why, "error no %s row to clone", from);
        write_reply("scenario_reply.txt", why);
        return 0;
    }
    uint8_t *row = (uint8_t *)engine_malloc(ROW_SIZE);
    if (!row) {
        write_reply("scenario_reply.txt", "error out of memory");
        return 0;
    }
    memcpy(row, tmpl, ROW_SIZE);
    // The world: a fresh soft pointer (no resolved weak pointer, no sub-path).
    memset(row + ROW_WORLD_WEAK, 0, 8);
    swprintf(package, 128, L"/Game/Levels/Halo1/Solo/%ls/%ls", wcode, wcode);
    swprintf(asset, 16, L"%ls", wcode);
    fname_t pkg = fname_of(package), ast = fname_of(asset);
    memcpy(row + ROW_WORLD_PACKAGE, &pkg, 8);
    memcpy(row + ROW_WORLD_ASSET, &ast, 8);
    memset(row + ROW_WORLD_SUBPATH, 0, 16);
    int32_t num = 0;
    wchar_t *scenario = engine_wstring(wcode, &num);
    *(wchar_t **)(row + ROW_SCENARIO_NAME) = scenario;
    *(int32_t *)(row + ROW_SCENARIO_NAME + 8) = num;
    *(int32_t *)(row + ROW_SCENARIO_NAME + 12) = num;
    map_guid(code, row + ROW_MAP_GUID);
    text_addref(row + ROW_TITLE);
    text_addref(row + ROW_DESCRIPTION);
    // The preview image's soft path may carry a sub-path string; the clone
    // must not share its buffer.
    memset(row + 112 + 24, 0, 16);
    if (!add_row(dt, name, row, why, sizeof why) || !add_handle((uint8_t *)campaign, dt, name, why, sizeof why) ||
        !glue_add(name, row, tmpl, why, sizeof why)) {
        Log("scenario %s: %s", code, why);
        char reply[300];
        snprintf(reply, sizeof reply, "error %s", why);
        write_reply("scenario_reply.txt", reply);
        return 0;
    }
    Log("scenario %s: row added (cloned from %s), world %ls", code, from, package);
    write_reply("scenario_reply.txt", "ok added");
    return 0;
}

// ------------------------------------------------------- the Megalo switch

typedef struct {
    uint32_t rva;
    uint32_t len;
    uint8_t shipped[16];
    uint8_t patched[16];
    const char *what;
} code_patch_t;

// HaloSimulation_tag_release.dll, CU4. Mirrors `mjolnir live engine
// --launch-engine 2 --map-variant-gate skip --map-variant-reset skip`.
static const code_patch_t MEGALO[] = {
    // Load-map handler 0xf650: `mov r8d, 3` feeds 0x21c4f0(&variant, 3); the
    // campaign fields are copied in only for engine 3, and the launch mode
    // is derived from the engine, so this constant is the whole switch.
    {0xf6db, 6, {0x41, 0xb8, 0x03, 0x00, 0x00, 0x00}, {0x41, 0xb8, 0x02, 0x00, 0x00, 0x00},
     "map load asks for the Megalo engine"},
    // Session readiness 0x55a2a0: required-parameter mask for multiplayer
    // session modes, `movabs rax, 0x8001813e0`; bit 20 is the map variant.
    {0x55af56, 10, {0x48, 0xb8, 0xe0, 0x13, 0x18, 0x00, 0x08, 0x00, 0x00, 0x00},
     {0x48, 0xb8, 0xe0, 0x13, 0x08, 0x00, 0x08, 0x00, 0x00, 0x00}, "session readiness: map variant not required"},
    // Options from session 0x55e1c0: a missing map variant no longer fails.
    {0x55e8c7, 2, {0x74, 0x31}, {0x74, 0x34}, "options builder: no map variant is not a failure"},
    // In-game parameter check 0x45b160, its own copy of the mask.
    {0x45b1a3, 10, {0x48, 0xb8, 0xe0, 0x13, 0x18, 0x00, 0x08, 0x00, 0x00, 0x00},
     {0x48, 0xb8, 0xe0, 0x13, 0x08, 0x00, 0x08, 0x00, 0x00, 0x00}, "in-game parameter check: map variant not required"},
    // Game-engine zone-set handler 0x2ad2d0: always take its early exit, so
    // the start-up zone switch does not delete and reset the map variant.
    {0x2ad2e2, 2, {0x74, 0x36}, {0xeb, 0x36}, "zone-set switch: map variant kept"},
    // Variant file reader 0x3f8a00: after closing the file it asks its size
    // again (0x74f410), by handle when the Unreal host supplies the file
    // system, and close has already set the handle to -1, so every `.mglo`
    // is dropped undecoded. Report the 0x5000-byte buffer instead: the
    // decoder stops where the variant's grammar ends and only checks it
    // read no more bits than that.
    {0x3f8a8d, 15,
     {0x48, 0x8d, 0x95, 0x08, 0x50, 0x00, 0x00, 0x48, 0x8b, 0xcb, 0xe8, 0x74, 0x69, 0x35, 0x00},
     {0xc7, 0x85, 0x08, 0x50, 0x00, 0x00, 0x00, 0x50, 0x00, 0x00, 0xb0, 0x01, 0x0f, 0x1f, 0x00},
     "variant file reader: size from the buffer, not the closed handle"},
    // Shell event drain 0xe670, event 0/7 (the exit the Unreal host posts from
    // its shutdown, exe 0x7b24160, then waits on): with a game in progress it
    // sets the main loop's exit flag (0x1357023) only when the game options'
    // mode is campaign, so under a Megalo game the event was dropped, the
    // simulation kept playing and the host's shutdown slept forever (the
    // window closed, the process never exited; docs/re/megalo_engine.md,
    // "Quitting from a match"). Drop the `jne`: a multiplayer game exits the
    // loop the way a campaign mission already does. The host posts this event
    // from nowhere else, so this changes nothing but the quit, and
    // mjolnir_megalo_off leaves it in place.
    {0xef18, 6, {0x0f, 0x85, 0x0d, 0x05, 0x00, 0x00}, {0x66, 0x0f, 0x1f, 0x44, 0x00, 0x00},
     "exit event: honoured in a multiplayer game"},
};

// Sites from this index on stay patched when the switch goes off.
#define MEGALO_KEEP 6

static int set_megalo(int on) {
    ensure_init();
    uint8_t *sim = (uint8_t *)GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!sim) {
        Log("megalo: the simulation DLL is not loaded");
        return 0;
    }
    const size_t n = sizeof(MEGALO) / sizeof(MEGALO[0]);
    for (size_t i = 0; i < n; i++) {
        const code_patch_t *p = &MEGALO[i];
        uint8_t *at = sim + p->rva;
        if (memcmp(at, p->shipped, p->len) != 0 && memcmp(at, p->patched, p->len) != 0) {
            Log("megalo: refused, +%x holds neither the CU4 bytes nor the patch (%s)", p->rva, p->what);
            return 0;
        }
    }
    for (size_t i = 0; i < n; i++) {
        const code_patch_t *p = &MEGALO[i];
        uint8_t *at = sim + p->rva;
        const uint8_t *want = (on || i >= MEGALO_KEEP) ? p->patched : p->shipped;
        if (memcmp(at, want, p->len) == 0) continue;
        DWORD old;
        if (!VirtualProtect(at, p->len, PAGE_EXECUTE_READWRITE, &old)) {
            Log("megalo: VirtualProtect failed at +%x", p->rva);
            return 0;
        }
        memcpy(at, want, p->len);
        VirtualProtect(at, p->len, old, &old);
        FlushInstructionCache(GetCurrentProcess(), at, p->len);
    }
    Log("megalo: %s (%zu sites)", on ? "ON: the next map load starts the Megalo engine" : "off: shipped bytes", n);
    return 1;
}

// The variant file loader (docs/re/megalo_engine.md, "A variant from a file"):
// at each round reset, with the Megalo engine running, the simulation reads
// `<name>.mglo` from `<root>\<sub>\` and decodes it into the live variant, when
// this buffer holds a name. The root and sub-directory live in a path struct
// the Unreal host fills on first use (`%LOCALAPPDATA%\Meteorite\Saved\BlamData\`
// and `HotReload` on CU4); before that they read empty, so those are the
// fallbacks.
#define RVA_MGLO_NAME 0x152a7c0u
#define RVA_MGLO_PATHS 0xc79d40u
#define MGLO_NAME "mjolnir"

// A printable ASCII string of at most `cap` bytes at `at`, or "" if it is not one.
static void ascii_at(const uint8_t *at, size_t cap, char *out, size_t out_cap) {
    size_t n = 0;
    for (; n < cap && n + 1 < out_cap && at[n] >= 0x20 && at[n] < 0x7f; n++) out[n] = (char)at[n];
    out[(n < cap && at[n] == 0) ? n : 0] = 0;
}

// `<root>\<sub>\`, created if missing; 0 if there is no root to be had.
static int mglo_dir(uint8_t *sim, char *dir, size_t cap) {
    char root[0x101], sub[0x101];
    ascii_at(sim + RVA_MGLO_PATHS + 8, 0x100, root, sizeof root);
    ascii_at(sim + RVA_MGLO_PATHS + 0x10c, 0x100, sub, sizeof sub);
    if (!root[0]) {
        char local[MAX_PATH];
        DWORD n = GetEnvironmentVariableA("LOCALAPPDATA", local, MAX_PATH);
        if (!n || n >= MAX_PATH) return 0;
        snprintf(root, sizeof root, "%s\\Meteorite\\Saved\\BlamData\\", local);
    }
    if (!sub[0]) strcpy_s(sub, sizeof sub, "HotReload");
    snprintf(dir, cap, "%s%s%s\\", root, root[strlen(root) - 1] == '\\' ? "" : "\\", sub);
    // Every level of the path, so a fresh install without BlamData works too.
    for (char *p = dir + 3; *p; p++) {
        if (*p != '\\') continue;
        *p = 0;
        CreateDirectoryA(dir, NULL);
        *p = '\\';
    }
    return 1;
}

// Lua C functions: 0 results. Call before the mission starts (the load-map
// event reads the first patch).
__declspec(dllexport) int mjolnir_megalo_on(void *L) {
    (void)L;
    set_megalo(1);
    return 0;
}

// Install `native\variant.mglo` (staged next to this DLL by MJOLNIRLevelLoader
// from its `variants\` folder) as `mjolnir.mglo` in the loader's directory, and
// ask the simulation to read it at the next round reset.
__declspec(dllexport) int mjolnir_megalo_variant(void *L) {
    (void)L;
    ensure_init();
    uint8_t *sim = (uint8_t *)GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!sim) return 0;
    char staged[MAX_PATH], dir[MAX_PATH], target[MAX_PATH];
    strcpy_s(staged, sizeof staged, g_log);
    char *slash = strrchr(staged, '\\');
    if (slash) *(slash + 1) = 0;
    strcat_s(staged, sizeof staged, "variant.mglo");
    if (!mglo_dir(sim, dir, sizeof dir)) {
        Log("megalo: no variant directory (LOCALAPPDATA unset); the default variant runs");
        return 0;
    }
    snprintf(target, sizeof target, "%s%s.mglo", dir, MGLO_NAME);
    if (!CopyFileA(staged, target, FALSE)) {
        Log("megalo: could not copy %s to %s (error %lu); the default variant runs", staged, target,
            GetLastError());
        return 0;
    }
    static const char name[] = MGLO_NAME;
    char *buffer = (char *)(sim + RVA_MGLO_NAME);
    DWORD old;
    if (!VirtualProtect(buffer, sizeof(name), PAGE_READWRITE, &old)) return 0;
    memcpy(buffer, name, sizeof(name));
    VirtualProtect(buffer, sizeof(name), old, &old);
    Log("megalo: %s installed; the next round reset loads it", target);
    return 0;
}

__declspec(dllexport) int mjolnir_megalo_off(void *L) {
    (void)L;
    set_megalo(0);
    return 0;
}

/* Pinned for the life of the process. The game keeps calling the hooks this
   DLL installs, and a UE4SS mod reload (Ctrl+R) closes the Lua state that
   loaded it, which unloaded the code under them: the host crashed executing
   freed memory (two PCs, 2026-10-03). Pinned, a reload's package.loadlib
   finds the same module, statics and all, and the install guards skip a
   second install. */
BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        HMODULE pinned;
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN, (LPCWSTR)h, &pinned);
    }
    return TRUE;
}
