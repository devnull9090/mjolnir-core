// MJOLNIR Forge — the native half of mods/MJOLNIRForge.
//
// Halo Campaign Evolved's simulation still carries Halo Reach's Forge: game
// engine 1 ("sandbox"), whose players turn into a flying monitor and grab,
// move, duplicate and delete the map's objects (docs/re/forge_engine.md).
// Every edit is a request the simulation queues and applies itself, the same
// path a Reach Forge session used, so a host's edits reach the session the
// engine's own way. Nothing on the Unreal side feeds it: the controls that
// would send those requests are never written. This DLL sends them.
//
// How it works, and why it is this shape:
//
//   * The sandbox engine's vtable slot 113 is a routine the engine calls once
//     a tick, and only while the sandbox engine runs. This DLL swaps that one
//     pointer for its own routine, which calls the original and then acts on
//     whatever the Lua half asked for. No code is patched, the swap is a
//     single aligned pointer write, and outside a Forge game nothing calls it.
//     Game state is thread-local in this engine, so the requests have to be
//     built on the simulation's own thread: that is where slot 113 runs.
//
//   * A request is the 0x40-byte record the engine's own input loop (sandbox
//     slot 30, 0x302260) builds and hands to 0x4074c0: payload at +0, player
//     index at +0x38, type at +0x3c. Types used here: 1 delete, 2 toggle the
//     monitor, 3 grab, 4 release, 10 duplicate at the cursor.
//
//   * UE4SS's Lua loads this DLL with `package.loadlib` and calls the exports
//     below, which take no arguments (the Lua C API is not exported to us).
//     Commands are bits in one word the simulation thread swaps out; the
//     editor's state goes the other way through a snapshot that `pump`,
//     called from Lua, writes to forge_state.txt next to this DLL.
//
// Every RVA below is specific to one build of HaloSimulation_tag_release.dll.
// `open` refuses to install unless the DLL's PE timestamp matches and the
// slots hold what CU4 has there, so a game update degrades to a status line
// rather than a crash.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <intrin.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

// ---- Build fingerprint and RVAs: HaloSimulation_tag_release.dll, CU4 ------
// Steam's copy and the Xbox app's differ only in the header (docs/game_pass.md).
#define TIMESTAMP_STEAM      0x6a7a740au
#define TIMESTAMP_GAME_PASS  0x6a7a741du
#define RVA_SANDBOX_VTABLE   0x85d740   // the sandbox engine's vtable (114 slots)
#define SLOT_INDEX           0x6970     // its slot 0: returns the engine index, 1
#define SLOT_TICK            113        // runs once a tick, sandbox only
#define RVA_SLOT_TICK        0x3036f0   // what CU4 has in slot 113
#define RVA_SEND_REQUEST     0x4074c0   // void (const request *): queue an editor request
#define RVA_IS_EDITING       0x2fe810   // bool (player index): the player is the monitor
#define RVA_PLACE_CHECK      0x306550   // bool (u8, object, 0, 0, 0): a palette entry can copy it
#define RVA_TAG_TABLE        0x182d1e8  // pointer to the tag instance table

// The thread-local block (TLS[_tls_index]) and the structures it points at.
#define TLS_OBJECTS          0x20       // object data array
#define TLS_PLAYERS          0x30       // player data array
#define TLS_ENGINE_GLOBALS   0x38       // game-engine globals, G
#define TLS_PLAYER_USERS     0x118      // player -> local user map
#define ARRAY_DATA           0x50       // a data array's element pointer
#define PLAYER_STRIDE        0x4b0
#define PLAYER_UNIT          0x28       // the player's unit, -1 none
#define PLAYER_USER          0x34       // +p*4 in the user map: local user index
#define OBJECT_ENTRY         0x18       // object array entry: +0x10 the object
#define G_EDITOR_STATE       0x17a4     // + p*300: the player's editor state
#define EDITOR_STRIDE        300
#define EDITOR_HELD          0x4        // the held object, -1 none
#define EDITOR_CURSOR        0x8        // the object under the cursor, -1 none
#define EDITOR_DISTANCE      0xc        // grab distance (the cursor reaches at least 5)
#define EDITOR_POINT         0x10       // the cursor point, 3 floats
#define TAG_ENTRY_STRIDE     0x30       // tag table entry: +0x10 path
#define MAX_PLAYERS          16

enum {
    REQ_DELETE = 1,
    REQ_TOGGLE = 2,
    REQ_GRAB = 3,
    REQ_RELEASE = 4,
    REQ_DUPLICATE = 10,
};

enum {
    CMD_TOGGLE = 1 << 0,
    CMD_GRAB = 1 << 1,
    CMD_DELETE = 1 << 2,
    CMD_DUPLICATE = 1 << 3,
    CMD_NEARER = 1 << 4,
    CMD_FARTHER = 1 << 5,
};

#define DISTANCE_STEP 0.5f
#define DISTANCE_MIN  1.0f
#define DISTANCE_MAX  60.0f

typedef void (*tick_fn)(void *self, void *a, void *b, void *c);
typedef void (*send_fn)(uint8_t *request);
typedef uint8_t (*is_editing_fn)(uint32_t player);
typedef uint8_t (*place_check_fn)(uint32_t unused, uint32_t object, void *a, void *b, void *c);

// ---- State --------------------------------------------------------------------
static uint8_t *g_base;
static tick_fn g_original_tick;
static send_fn g_send;
static is_editing_fn g_is_editing;
static place_check_fn g_place_check;
static unsigned g_tls_index = ~0u;
static int g_installed;

static volatile LONG g_commands;
// When the last command arrived (GetTickCount64). The simulation does not
// tick while the pause menu is up, so a key pressed there would otherwise
// act on resume; commands older than this are dropped.
static volatile LONG64 g_command_at;
#define COMMAND_MAX_AGE_MS 750

// What the simulation thread last saw, for pump to publish.
typedef struct {
    unsigned tick;
    int player;      // -1: no local player with a unit
    int editing;
    uint32_t held, cursor;
    float distance;
    char held_tag[160], cursor_tag[160];
    char held_group[5], cursor_group[5];
    unsigned last_id; // counts commands acted on, so the same result twice still shows
    char last[160];  // what the last command did
} snapshot_t;

static CRITICAL_SECTION g_lock;
static snapshot_t g_snap;
static unsigned g_published_tick = ~0u;
static char g_last[160];
static unsigned g_last_id;

static char g_dir[MAX_PATH];
static char g_state_path[MAX_PATH];
static char g_status_path[MAX_PATH];

// ---- Small helpers --------------------------------------------------------------
static void write_file(const char *path, const char *text) {
    FILE *f = NULL;
    if (fopen_s(&f, path, "wb") == 0 && f) {
        fputs(text, f);
        fclose(f);
    }
}

static void set_status(const char *fmt, ...) {
    char line[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    write_file(g_status_path, line);
}

static void derive_paths(HMODULE self) {
    GetModuleFileNameA(self, g_dir, MAX_PATH);
    char *slash = strrchr(g_dir, '\\');
    if (slash) slash[1] = '\0';
    snprintf(g_state_path, MAX_PATH, "%sforge_state.txt", g_dir);
    snprintf(g_status_path, MAX_PATH, "%sstatus.txt", g_dir);
}

// The simulation thread's thread-local block. Only meaningful on that thread.
static uint8_t *tls_block(void) {
    void **tls_array = (void **)__readgsqword(0x58);
    return tls_array ? (uint8_t *)tls_array[g_tls_index] : NULL;
}

static void note(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(g_last, sizeof g_last, fmt, ap);
    g_last_id++;
    va_end(ap);
}

// The last component of an object's tag path ("shotgun"), or "", and its
// tag group as four characters ("weap"), or "".
static void object_tag_name(uint8_t *tls, uint32_t handle, char *out, size_t size, char group[5]) {
    out[0] = '\0';
    group[0] = '\0';
    if (handle == 0xffffffffu) return;
    uint8_t *objects = *(uint8_t **)(tls + TLS_OBJECTS);
    uint8_t *data = objects ? *(uint8_t **)(objects + ARRAY_DATA) : NULL;
    uint8_t *object = data ? *(uint8_t **)(data + 0x10 + (size_t)(handle & 0xffff) * OBJECT_ENTRY) : NULL;
    if (!object) return;
    uint32_t tag = *(uint32_t *)object;
    uint8_t *table = *(uint8_t **)(g_base + RVA_TAG_TABLE);
    uint8_t *entries = table ? *(uint8_t **)(table + ARRAY_DATA) : NULL;
    uint8_t *entry = entries ? entries + (size_t)(tag & 0xffff) * TAG_ENTRY_STRIDE : NULL;
    const char *path = entry ? *(const char **)(entry + 0x10) : NULL;
    if (!path) return;
    // +0x04: the group four-CC as a little-endian u32 ('weap' reads "paew").
    for (int i = 0; i < 4; i++) {
        char c = (char)entry[4 + 3 - i];
        group[i] = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '!' ? c : '?';
    }
    group[4] = '\0';
    const char *leaf = strrchr(path, '\\');
    strncpy_s(out, size, leaf ? leaf + 1 : path, _TRUNCATE);
}

// The player local user 0 controls, with a unit; -1 if none.
static int local_player(uint8_t *tls) {
    uint8_t *players = *(uint8_t **)(tls + TLS_PLAYERS);
    uint8_t *data = players ? *(uint8_t **)(players + ARRAY_DATA) : NULL;
    uint8_t *users = *(uint8_t **)(tls + TLS_PLAYER_USERS);
    if (!data || !users) return -1;
    for (int p = 0; p < MAX_PLAYERS; p++) {
        uint8_t *entry = data + (size_t)p * PLAYER_STRIDE;
        if (*(int16_t *)entry == 0) continue;                       // free slot
        if (*(int32_t *)(users + PLAYER_USER + p * 4) != 0) continue; // not local user 0
        if (*(int32_t *)(entry + PLAYER_UNIT) == -1) continue;
        return p;
    }
    return -1;
}

static void send(int player, uint16_t type, const void *payload, size_t size) {
    uint8_t request[0x40];
    memset(request, 0, sizeof request);
    memcpy(request, payload, size);
    *(uint32_t *)(request + 0x38) = (uint32_t)player;
    *(uint16_t *)(request + 0x3c) = type;
    g_send(request);
}

// ---- The simulation-thread side ---------------------------------------------------

static void act(uint8_t *tls, int player, LONG commands) {
    uint8_t *g = *(uint8_t **)(tls + TLS_ENGINE_GLOBALS);
    uint8_t *state = g + G_EDITOR_STATE + (size_t)player * EDITOR_STRIDE;
    uint32_t held = *(uint32_t *)(state + EDITOR_HELD);
    uint32_t cursor = *(uint32_t *)(state + EDITOR_CURSOR);
    uint32_t target = held != 0xffffffffu ? held : cursor;
    int editing = g_is_editing((uint32_t)player) != 0;

    if (commands & CMD_TOGGLE) {
        uint8_t want = editing ? 0 : 1;
        send(player, REQ_TOGGLE, &want, 1);
        note(want ? "monitor" : "biped");
        return; // the rest needs the monitor, which the toggle changes
    }
    if (!editing) {
        if (commands & ~(CMD_TOGGLE)) note("not in the monitor");
        return;
    }
    if (commands & CMD_GRAB) {
        if (held != 0xffffffffu) {
            uint8_t payload[5] = {0};
            memcpy(payload, &held, 4);
            send(player, REQ_RELEASE, payload, sizeof payload);
            note("released");
        } else if (cursor != 0xffffffffu) {
            send(player, REQ_GRAB, &cursor, 4);
            note("grabbed");
        } else {
            note("nothing under the cursor");
        }
    }
    if (commands & CMD_DELETE) {
        if (target != 0xffffffffu) {
            send(player, REQ_DELETE, &target, 4);
            note("deleted");
        } else {
            note("nothing to delete");
        }
    }
    if (commands & CMD_DUPLICATE) {
        if (target == 0xffffffffu) {
            note("nothing to duplicate");
        } else if (!g_place_check(0, target, NULL, NULL, NULL)) {
            note("this map's palette has no entry for that object");
        } else {
            uint8_t payload[16];
            memcpy(payload, &target, 4);
            memcpy(payload + 4, state + EDITOR_POINT, 12);
            send(player, REQ_DUPLICATE, payload, sizeof payload);
            note("duplicated");
        }
    }
    if (commands & (CMD_NEARER | CMD_FARTHER)) {
        float *distance = (float *)(state + EDITOR_DISTANCE);
        float d = *distance < DISTANCE_MIN ? DISTANCE_MIN : *distance;
        if (commands & CMD_NEARER) d -= DISTANCE_STEP;
        if (commands & CMD_FARTHER) d += DISTANCE_STEP;
        *distance = d < DISTANCE_MIN ? DISTANCE_MIN : d > DISTANCE_MAX ? DISTANCE_MAX : d;
    }
}

static void snapshot(uint8_t *tls, int player) {
    snapshot_t s;
    memset(&s, 0, sizeof s);
    s.player = player;
    s.held = s.cursor = 0xffffffffu;
    if (player >= 0) {
        uint8_t *g = *(uint8_t **)(tls + TLS_ENGINE_GLOBALS);
        uint8_t *state = g + G_EDITOR_STATE + (size_t)player * EDITOR_STRIDE;
        s.editing = g_is_editing((uint32_t)player) != 0;
        s.held = *(uint32_t *)(state + EDITOR_HELD);
        s.cursor = *(uint32_t *)(state + EDITOR_CURSOR);
        s.distance = *(float *)(state + EDITOR_DISTANCE);
        object_tag_name(tls, s.held, s.held_tag, sizeof s.held_tag, s.held_group);
        object_tag_name(tls, s.cursor, s.cursor_tag, sizeof s.cursor_tag, s.cursor_group);
    }
    EnterCriticalSection(&g_lock);
    s.tick = g_snap.tick + 1;
    memcpy(s.last, g_last, sizeof s.last);
    s.last_id = g_last_id;
    g_snap = s;
    LeaveCriticalSection(&g_lock);
}

static void hooked_tick(void *self, void *a, void *b, void *c) {
    g_original_tick(self, a, b, c);
    uint8_t *tls = tls_block();
    if (!tls) return;
    int player = local_player(tls);
    LONG commands = InterlockedExchange(&g_commands, 0);
    if (commands && GetTickCount64() - (ULONGLONG)g_command_at > COMMAND_MAX_AGE_MS) commands = 0;
    if (commands && player >= 0) act(tls, player, commands);
    snapshot(tls, player);
}

// ---- Installation ---------------------------------------------------------------

static int install(void) {
    if (g_installed) return 1;
    HMODULE sim = GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!sim) {
        set_status("waiting: the simulation DLL loads with the first game");
        return 0;
    }
    uint8_t *base = (uint8_t *)sim;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    uint32_t stamp = nt->FileHeader.TimeDateStamp;
    if (stamp != TIMESTAMP_STEAM && stamp != TIMESTAMP_GAME_PASS) {
        set_status("error: simulation DLL timestamp 0x%08x, expected 0x%08x or 0x%08x: the game updated and the "
                   "offsets need re-deriving (docs/re/forge_engine.md)",
                   stamp, TIMESTAMP_STEAM, TIMESTAMP_GAME_PASS);
        return 0;
    }
    void **vtable = (void **)(base + RVA_SANDBOX_VTABLE);
    if (vtable[0] != (void *)(base + SLOT_INDEX)) {
        set_status("error: the sandbox engine's vtable is not at +0x%x", RVA_SANDBOX_VTABLE);
        return 0;
    }
    void **slot = &vtable[SLOT_TICK];
    if (*slot != (void *)(base + RVA_SLOT_TICK) && *slot != (void *)hooked_tick) {
        set_status("error: sandbox slot %d is %p, expected +0x%x", SLOT_TICK, *slot, RVA_SLOT_TICK);
        return 0;
    }
    IMAGE_DATA_DIRECTORY dir_tls = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_TLS];
    if (!dir_tls.VirtualAddress) {
        set_status("error: the simulation DLL has no TLS directory");
        return 0;
    }
    g_tls_index = *(unsigned *)(uintptr_t)((IMAGE_TLS_DIRECTORY64 *)(base + dir_tls.VirtualAddress))->AddressOfIndex;
    g_base = base;
    g_send = (send_fn)(base + RVA_SEND_REQUEST);
    g_is_editing = (is_editing_fn)(base + RVA_IS_EDITING);
    g_place_check = (place_check_fn)(base + RVA_PLACE_CHECK);
    g_original_tick = (tick_fn)(base + RVA_SLOT_TICK);
    if (*slot != (void *)hooked_tick) {
        DWORD old;
        if (!VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &old)) {
            set_status("error: VirtualProtect failed (%lu)", GetLastError());
            return 0;
        }
        InterlockedExchangePointer(slot, (void *)hooked_tick);
        VirtualProtect(slot, sizeof(void *), old, &old);
    }
    g_installed = 1;
    set_status("ok base=%p", (void *)base);
    return 1;
}

// ---- Exports, called from Lua through package.loadlib ------------------------------
//
// Each takes Lua's `lua_State*` and ignores it, returning 0 results. A
// command is acted on at the next simulation tick of a Forge game.

static int command(LONG bit) {
    if (!g_installed && !install()) return 0;
    InterlockedExchange64(&g_command_at, (LONG64)GetTickCount64());
    InterlockedOr(&g_commands, bit);
    return 0;
}

__declspec(dllexport) int mjolnir_forge_open(void *L) {
    (void)L;
    install();
    return 0;
}

__declspec(dllexport) int mjolnir_forge_toggle(void *L) { (void)L; return command(CMD_TOGGLE); }
__declspec(dllexport) int mjolnir_forge_grab(void *L) { (void)L; return command(CMD_GRAB); }
__declspec(dllexport) int mjolnir_forge_delete(void *L) { (void)L; return command(CMD_DELETE); }
__declspec(dllexport) int mjolnir_forge_duplicate(void *L) { (void)L; return command(CMD_DUPLICATE); }
__declspec(dllexport) int mjolnir_forge_nearer(void *L) { (void)L; return command(CMD_NEARER); }
__declspec(dllexport) int mjolnir_forge_farther(void *L) { (void)L; return command(CMD_FARTHER); }

// Write forge_state.txt when the simulation thread has seen a new tick since
// the last call: `key=value` lines. `forge=0` once ticks stop (no Forge game).
// Runs on whichever thread Lua calls it from; never on the simulation thread.
__declspec(dllexport) int mjolnir_forge_pump(void *L) {
    (void)L;
    if (!g_installed && !install()) return 0;
    EnterCriticalSection(&g_lock);
    snapshot_t s = g_snap;
    LeaveCriticalSection(&g_lock);
    int live = s.tick != g_published_tick;
    g_published_tick = s.tick;
    char text[1024];
    snprintf(text, sizeof text,
             "forge=%d\nplayer=%d\nediting=%d\nheld=%08x\nheld_tag=%s\nheld_group=%s\ncursor=%08x\ncursor_tag=%s\n"
             "cursor_group=%s\ndistance=%.1f\nlast=%s\nlast_id=%u\n",
             live, s.player, s.editing, s.held, s.held_tag, s.held_group, s.cursor, s.cursor_tag, s.cursor_group,
             s.distance, s.last, s.last_id);
    write_file(g_state_path, text);
    return 0;
}

/* Pinned for the life of the process: the engine keeps calling the slot this
   DLL installs, and a UE4SS mod reload (Ctrl+R) would otherwise unload the
   code under it (the same rule as mjolnir_blam_console.c). */
BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        HMODULE pinned;
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN, (LPCWSTR)module, &pinned);
        DisableThreadLibraryCalls(module);
        InitializeCriticalSection(&g_lock);
        // Nothing seen yet: no player, nothing held or aimed at, and no tick
        // (pump reports forge=0 until the first sandbox tick).
        g_snap.player = -1;
        g_snap.held = g_snap.cursor = 0xffffffffu;
        g_published_tick = 0;
        derive_paths(module);
        set_status("loaded, not installed");
    }
    return TRUE;
}
