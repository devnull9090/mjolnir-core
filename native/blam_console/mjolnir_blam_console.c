// MJOLNIR Blam Console — the native half of mods/MJOLNIRBlamConsole.
//
// Halo Campaign Evolved's simulation DLL still carries the classic Blam
// console: the HS compiler, the function table, `help`, `script_doc`, the
// cheats. Nothing on the Unreal side feeds it text, and the Unreal console
// answers every Blam command with "Command not recognized". This DLL is the
// missing wire.
//
// How it works, and why it is this shape:
//
//   * The Blam engine's shell object owns a queue object at +0x140 whose
//     vtable slot 0 is the drain routine the simulation thread calls once per
//     tick (from the main-loop update). This DLL swaps that one pointer for its
//     own routine, which calls the original and then runs whatever command is
//     waiting. No code is patched, the swap is a single aligned pointer write,
//     and it runs on the thread the engine itself uses for console commands.
//     That matters: compile-and-evaluate reads game state through thread-local
//     storage, so it cannot be called from a foreign thread.
//
//   * The engine's `hs_compile_and_evaluate` survives in the release build with
//     its out-parameters intact (result value and type), a per-type formatter
//     table, the compile-error message and offset globals, and an optional
//     output-buffer global that compile errors are appended to. Together those
//     give a read-back path the stripped `console_printf` no longer provides.
//
//   * UE4SS's Lua loads this DLL with `package.loadlib` and calls the two
//     exports below. The Lua C API is not reachable from here (UE4SS links Lua
//     statically and exports none of it), so the exports take no arguments and
//     the two sides talk through small files next to this DLL, the same way
//     the bridge mod does. The Blam thread never touches a file: `pump`, run
//     from Lua, moves text between the files and an in-memory mailbox.
//
// Every RVA below is specific to one build of HaloSimulation_tag_release.dll.
// `open` refuses to install unless the DLL's PE timestamp matches, so a game
// update degrades to a clear status message rather than a crash. Re-derive
// them with the notes in docs/blam_console.md.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <intrin.h>

// ---- Build fingerprint and RVAs: HaloSimulation_tag_release.dll, CU4 ------
// IMAGE_FILE_HEADER.TimeDateStamp: Steam's copy and the Xbox app's. The two
// differ only in the header and Steam's signature, not in code or data
// (docs/game_pass.md), so the RVAs below serve both.
#define TIMESTAMP_STEAM      0x6a7a740au
#define TIMESTAMP_GAME_PASS  0x6a7a741du
#define RVA_EVALUATE         0x1f8b30      // hs_compile_and_evaluate (inner)
#define RVA_SHELL_PTR        0x2c40028     // the shell object, once created
#define RVA_QUEUE_VTABLE     0x7b0610      // vtable of the queue object at shell+0x140
#define RVA_QUEUE_DRAIN      0xe670        // its slot 0, the per-tick drain
#define RVA_OUT_BUF          0x2c2ef18     // char*: console output capture buffer
#define RVA_OUT_SIZE         0x2c2ef14     // int: its size
#define RVA_ERR_MSG          0x18327f0     // const char*: last compile error
#define RVA_ERR_OFFSET       0x18327f8     // int: its character offset
#define RVA_FORMATTERS       0x81f760      // void (*[])(short type, int value, char*, int)
#define RVA_TYPE_NAMES       0x9aa1c0      // const char*[] value-type names
#define RVA_IN_GAME          0x209a20      // bool game_in_progress(void)
#define RVA_ANCHOR_STRING    0x7f14c0      // "sleep_until"

// Restored cheats (docs/re/restored_cheats.md). The release build points these
// functions' evaluators at one stub; we point them back at our own.
#define RVA_FUNCTION_TABLE   0x81ba20      // const hs_function_definition*[1695]
#define RVA_STUB_EVALUATE    0x1b2430      // the shared stub: hs_return(thread, 0)
#define RVA_HS_RETURN        0x1fe100      // void (int32 thread, int32 value)
#define RVA_HS_ARGUMENTS     0x1feca0      // int32* (thread, count, u16* types, bool init); NULL = not yet
#define RVA_TLS_INDEX        0xd72730      // u32: the game-state TLS slot
#define RVA_PLACEMENT_NEW    0x5ee570      // void (placement*, tag, owner object, u64 0)
#define RVA_OBJECT_NEW       0x5a0fc0      // u32 object (placement*), -1 on failure
#define RVA_OBJECT_ORIGIN    0x5a6780      // void (u32 object, float out[3])
#define RVA_TAG_TABLE        0x182d1e8     // pointer to the `tag instance` data array
#define FN_CHEAT_ALL_WEAPONS  333
#define FN_CHEAT_ALL_VEHICLES 334
#define FN_DROP_SAFE          339

typedef unsigned char (*evaluate_fn)(uint64_t unused, const char *source, const char *text,
                                     char interactive, uint32_t unused5, int32_t *value_out,
                                     int32_t *type_out);
typedef void (*format_fn)(int16_t type, int32_t value, char *buf, int32_t size);
typedef unsigned char (*in_game_fn)(void);
typedef void (*drain_fn)(void *self);

// ---- State --------------------------------------------------------------------
static uint8_t *g_base;
static evaluate_fn g_evaluate;
static in_game_fn g_in_game;
static drain_fn g_original_drain;
static void **g_vtable_slot;
static char **g_out_buf;
static int32_t *g_out_size;
static const char **g_err_msg;
static int32_t *g_err_offset;
static format_fn *g_formatters;
static const char **g_type_names;

static CRITICAL_SECTION g_lock;
static int g_installed;

// Mailbox. One command in flight at a time is all a console needs.
static char g_pending_text[4096];
static int g_pending_id;
static int g_pending_force;
static int g_has_pending;
static char g_result_text[8192];
static int g_result_id;
static int g_has_result;

// Files, next to this DLL.
static char g_dir[MAX_PATH];
static char g_request_path[MAX_PATH];
static char g_response_path[MAX_PATH];
static char g_status_path[MAX_PATH];
static int g_last_request_id = -1;

// ---- Small helpers --------------------------------------------------------------
static void write_file(const char *path, const char *text) {
    FILE *f = NULL;
    if (fopen_s(&f, path, "wb") == 0 && f) {
        fputs(text, f);
        fclose(f);
    }
}

static void set_status(const char *fmt, ...) {
    char line[1024];
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
    snprintf(g_request_path, MAX_PATH, "%srequest.txt", g_dir);
    snprintf(g_response_path, MAX_PATH, "%sresponse.txt", g_dir);
    snprintf(g_status_path, MAX_PATH, "%sstatus.txt", g_dir);
}

// ---- The Blam-thread side ------------------------------------------------------

// Run one console line the way the engine's own console would, and describe
// what happened. Runs on the simulation thread, inside the per-tick drain.
static void run_command(const char *text, int force, char *out, size_t out_size) {
    if (!force && !g_in_game()) {
        snprintf(out, out_size, "refused: no game in progress (prefix with ! to force)");
        return;
    }

    // Everything the engine would have printed lands here instead of nowhere.
    char capture[4096];
    capture[0] = '\0';
    char *old_buf = *g_out_buf;
    int32_t old_size = *g_out_size;
    *g_out_buf = capture;
    *g_out_size = (int32_t)sizeof capture;
    *g_err_msg = NULL;
    *g_err_offset = -1;

    int32_t value = -1;
    int32_t type = 0;
    g_evaluate(0, "console_command", text, 1, 0, &value, &type);

    *g_out_buf = old_buf;
    *g_out_size = old_size;

    const char *err = *g_err_msg;
    size_t n = 0;
    if (err && *err) {
        n += (size_t)snprintf(out + n, out_size - n, "error: %s", err);
        if (*g_err_offset >= 0)
            n += (size_t)snprintf(out + n, out_size - n, " (at character %d)", *g_err_offset);
    } else if (type > 4 && g_formatters[type]) {
        char formatted[1024];
        formatted[0] = '\0';
        g_formatters[type]((int16_t)type, value, formatted, (int32_t)sizeof formatted);
        const char *type_name = g_type_names[type] ? g_type_names[type] : "?";
        n += (size_t)snprintf(out + n, out_size - n, "= %s  (%s)", formatted, type_name);
    } else if (type == 4) {
        n += (size_t)snprintf(out + n, out_size - n, "ok");
    } else {
        n += (size_t)snprintf(out + n, out_size - n, "ok (type %d, value %d)", type, value);
    }
    if (capture[0] && n < out_size) {
        // Strip the trailing newline the engine's format adds.
        size_t len = strlen(capture);
        while (len && (capture[len - 1] == '\n' || capture[len - 1] == '\r')) capture[--len] = '\0';
        snprintf(out + n, out_size - n, "\n%s", capture);
    }
}

static void __fastcall hooked_drain(void *self) {
    g_original_drain(self);

    char text[4096];
    int id = 0, force = 0;
    EnterCriticalSection(&g_lock);
    int has = g_has_pending;
    if (has) {
        memcpy(text, g_pending_text, sizeof text);
        id = g_pending_id;
        force = g_pending_force;
        g_has_pending = 0;
    }
    LeaveCriticalSection(&g_lock);
    if (!has) return;

    char result[8192];
    result[0] = '\0';
    run_command(text, force, result, sizeof result);

    EnterCriticalSection(&g_lock);
    memcpy(g_result_text, result, sizeof g_result_text);
    g_result_id = id;
    g_has_result = 1;
    LeaveCriticalSection(&g_lock);
}

// ---- Restored cheats ------------------------------------------------------------
//
// `cheat_all_weapons`, `cheat_all_vehicles` and `drop_safe` are still in the
// function table with their names and parameter lists, but the release build
// points every one at the shared stub. Halo 1 (MCC) still has the bodies:
// gather the loaded tags of one group, then drop each near the player. The
// pieces that does here all survive in this DLL and are what the Forge
// editor's become-monitor uses (`0x3054f0`): placement data, the unit's
// origin, object_new. The evaluators run inside HS evaluation on the
// simulation thread, so scripts can call them as well as the console.

typedef void (*hs_return_fn)(int32_t thread, int32_t value);
typedef int32_t *(*hs_arguments_fn)(int32_t thread, uint16_t count, const uint16_t *types, uint8_t init);
typedef void (*placement_new_fn)(void *placement, uint32_t tag, uint32_t owner, uint64_t zero);
typedef uint32_t (*object_new_fn)(void *placement);
typedef void (*object_origin_fn)(uint32_t object, float out[3]);
typedef void (*hs_evaluate_fn)(int16_t function, int32_t thread, uint8_t init);

#define PLACEMENT_SIZE     0x330           // placement_new clears this many bytes
#define PLACEMENT_POSITION 0x1c            // real_point3d
#define TLS_OBJECTS        0x20
#define TLS_PLAYERS        0x30
#define ARRAY_DATA         0x50
#define OBJECT_ENTRY       0x18            // object array entry: +0x10 the object's data
#define PLAYER_STRIDE      0x4b0
#define PLAYER_UNIT        0x28
#define UNIT_FORWARD       0x204           // the unit's facing, 3 floats
#define TAG_HIGH_WATER     0x44
#define TAG_ENTRIES        0x50
#define TAG_BITSET         0x58
#define TAG_ENTRY_STRIDE   0x30            // +0 generation, +4 group, +0x10 path
#define DROP_MAX           20              // Halo 1 drops at most 16 weapons

static uint8_t *game_state(void) {
    uint32_t slot = *(uint32_t *)(g_base + RVA_TLS_INDEX);
    uint8_t **tls = (uint8_t **)__readgsqword(0x58);
    return tls[slot];
}

static uint8_t *object_data(uint32_t object) {
    uint8_t *objects = *(uint8_t **)(game_state() + TLS_OBJECTS);
    uint8_t *data = objects ? *(uint8_t **)(objects + ARRAY_DATA) : NULL;
    return data ? *(uint8_t **)(data + 0x10 + (size_t)(object & 0xffff) * OBJECT_ENTRY) : NULL;
}

// The first player with a unit, as player0 would be; -1 for none.
static uint32_t player_unit(void) {
    uint8_t *players = *(uint8_t **)(game_state() + TLS_PLAYERS);
    uint8_t *data = players ? *(uint8_t **)(players + ARRAY_DATA) : NULL;
    if (!data) return 0xffffffffu;
    for (int p = 0; p < 16; p++) {
        uint8_t *player = data + (size_t)p * PLAYER_STRIDE;
        uint32_t unit = *(uint32_t *)(player + PLAYER_UNIT);
        if (*(uint16_t *)player && unit != 0xffffffffu && object_data(unit)) return unit;
    }
    return 0xffffffffu;
}

static uint8_t *tag_entry(uint32_t index) {
    uint8_t *table = *(uint8_t **)(g_base + RVA_TAG_TABLE);
    if (!table || index >= *(uint32_t *)(table + TAG_HIGH_WATER)) return NULL;
    uint8_t *bits = *(uint8_t **)(table + TAG_BITSET);
    if (!(bits[index / 8] & (1 << (index % 8)))) return NULL;
    return *(uint8_t **)(table + TAG_ENTRIES) + (size_t)index * TAG_ENTRY_STRIDE;
}

static uint32_t tag_handle(uint32_t index, uint8_t *entry) {
    return (uint32_t)*(uint16_t *)entry << 16 | index;
}

#pragma warning(disable : 4295 4305 4309)  // four-character group constants
static int is_object_group(uint32_t group) {
    static const uint32_t groups[] = { 'weap', 'vehi', 'eqip', 'bipd', 'scen', 'bloc',
                                       'crat', 'mach', 'ctrl', 'ssce', 'term' };
    for (size_t i = 0; i < sizeof groups / sizeof groups[0]; i++)
        if (groups[i] == group) return 1;
    return 0;
}

// The object tag a resolved `any_tag` names. A path such as
// objects\weapons\rifle\assault_rifle\assault_rifle is shared by the weapon,
// its model, its render model and more, and the compiler may hand back any of
// them; prefer the object tag of the same path.
static uint32_t object_tag_for(uint32_t handle) {
    uint8_t *entry = tag_entry(handle & 0xffff);
    if (!entry) return 0xffffffffu;
    if (is_object_group(*(uint32_t *)(entry + 4))) return handle;
    const char *path = *(const char **)(entry + 0x10);
    uint8_t *table = *(uint8_t **)(g_base + RVA_TAG_TABLE);
    uint32_t high = *(uint32_t *)(table + TAG_HIGH_WATER);
    for (uint32_t i = 0; path && i < high; i++) {
        uint8_t *e = tag_entry(i);
        const char *p = e ? *(const char **)(e + 0x10) : NULL;
        if (p && is_object_group(*(uint32_t *)(e + 4)) && strcmp(p, path) == 0) return tag_handle(i, e);
    }
    return 0xffffffffu;
}

// Create `tag` `distance` units from the player along `angle` radians off
// their facing, half a unit up. Returns the object, or -1.
static uint32_t drop_near_player(uint32_t tag, float distance, float angle) {
    uint32_t unit = player_unit();
    if (unit == 0xffffffffu) return 0xffffffffu;
    float origin[3];
    ((object_origin_fn)(g_base + RVA_OBJECT_ORIGIN))(unit, origin);
    const float *forward = (const float *)(object_data(unit) + UNIT_FORWARD);
    float fx = forward[0], fy = forward[1];
    float len = sqrtf(fx * fx + fy * fy);
    if (len < 1e-3f) { fx = 1.0f; fy = 0.0f; } else { fx /= len; fy /= len; }
    float c = cosf(angle), s = sinf(angle);
    float dx = fx * c - fy * s, dy = fx * s + fy * c;

    __declspec(align(16)) uint8_t placement[PLACEMENT_SIZE];
    ((placement_new_fn)(g_base + RVA_PLACEMENT_NEW))(placement, tag, 0xffffffffu, 0);
    float *position = (float *)(placement + PLACEMENT_POSITION);
    position[0] = origin[0] + dx * distance;
    position[1] = origin[1] + dy * distance;
    position[2] = origin[2] + 0.5f;
    return ((object_new_fn)(g_base + RVA_OBJECT_NEW))(placement);
}

// What a player can carry or drive. Halo 1 took every loaded weapon; here the
// vehicles' guns and turrets are tags of the same groups (the Pelican's chin
// gun is both a `weap` and a `vehi`, the Warthog's chaingun a `vehi`), and a
// Jackal's shield and a Skirmisher's bracers are `weap`s, the tuning fork's
// turret a `vehi`. Picking up a vehicle's gun gives an unnamed weapon.
static int droppable(uint32_t group, const char *path) {
    if (group == 'weap')
        return strncmp(path, "objects\\weapons\\", 16) == 0 && !strstr(path, "jackal_shield") &&
               !strstr(path, "skirmisher_bracers");
    return strncmp(path, "objects\\vehicles\\", 17) == 0 && !strstr(path, "\\weapons\\") &&
           !strstr(path, "\\attachments\\") && !strstr(path, "\\turrets\\");
}

// Every droppable loaded tag of `group`, up to DROP_MAX, in an arc in front
// of the player.
static void drop_all(uint32_t group, float distance, const char *what) {
    uint32_t tags[DROP_MAX];
    int n = 0, found = 0, created = 0;
    uint8_t *table = *(uint8_t **)(g_base + RVA_TAG_TABLE);
    uint32_t high = table ? *(uint32_t *)(table + TAG_HIGH_WATER) : 0;
    for (uint32_t i = 0; i < high; i++) {
        uint8_t *e = tag_entry(i);
        const char *path = e ? *(const char **)(e + 0x10) : NULL;
        if (!path || *(uint32_t *)(e + 4) != group || !droppable(group, path)) continue;
        found++;
        if (n < DROP_MAX) tags[n++] = tag_handle(i, e);
    }
    for (int i = 0; i < n; i++) {
        // Spread over 160 degrees, nearest the facing first.
        float t = n > 1 ? (float)i / (float)(n - 1) - 0.5f : 0.0f;
        if (drop_near_player(tags[i], distance, t * 2.79f) != 0xffffffffu) created++;
    }
    // The console's capture buffer is set only while run_command evaluates a
    // line, so a script's call stays silent.
    char *out = *g_out_buf;
    if (out) {
        size_t len = strlen(out);
        if (len < (size_t)*g_out_size)
            snprintf(out + len, (size_t)*g_out_size - len, "dropped %d of %d loaded %s%s\n", created,
                     found, what, found > DROP_MAX ? " (the first by tag slot)" : "");
    }
}

static void evaluate_cheat_all_weapons(int16_t function, int32_t thread, uint8_t init) {
    (void)function; (void)init;
    drop_all('weap', 2.0f, "weapons");
    ((hs_return_fn)(g_base + RVA_HS_RETURN))(thread, 0);
}

static void evaluate_cheat_all_vehicles(int16_t function, int32_t thread, uint8_t init) {
    (void)function; (void)init;
    drop_all('vehi', 8.0f, "vehicles");
    ((hs_return_fn)(g_base + RVA_HS_RETURN))(thread, 0);
}

static void evaluate_drop_safe(int16_t function, int32_t thread, uint8_t init) {
    uint8_t *def = ((uint8_t **)(g_base + RVA_FUNCTION_TABLE))[function];
    int32_t *args = ((hs_arguments_fn)(g_base + RVA_HS_ARGUMENTS))(
        thread, *(uint16_t *)(def + 0x38), (const uint16_t *)(def + 0x3a), init);
    if (!args) return;  // arguments still evaluating; called again
    uint32_t tag = object_tag_for((uint32_t)args[0]);
    if (tag != 0xffffffffu) drop_near_player(tag, 2.0f, 0.0f);
    ((hs_return_fn)(g_base + RVA_HS_RETURN))(thread, 0);
}

// Point one stubbed function back at a working evaluator. Refuses unless the
// slot holds the expected name and still points at the stub (or at us).
static int restore_function(int index, const char *name, hs_evaluate_fn evaluate) {
    uint8_t *def = ((uint8_t **)(g_base + RVA_FUNCTION_TABLE))[index];
    void **slot = (void **)(def + 0x20);
    if (strcmp(*(const char **)(def + 8), name) != 0) return 0;
    if (*slot == (void *)evaluate) return 1;
    if (*slot != (void *)(g_base + RVA_STUB_EVALUATE)) return 0;
    DWORD old;
    if (!VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &old)) return 0;
    InterlockedExchangePointer(slot, (void *)evaluate);
    VirtualProtect(slot, sizeof(void *), old, &old);
    return 1;
}

static int restore_cheats(void) {
    return restore_function(FN_CHEAT_ALL_WEAPONS, "cheat_all_weapons", evaluate_cheat_all_weapons)
         + restore_function(FN_CHEAT_ALL_VEHICLES, "cheat_all_vehicles", evaluate_cheat_all_vehicles)
         + restore_function(FN_DROP_SAFE, "drop_safe", evaluate_drop_safe);
}

// ---- Installation ---------------------------------------------------------------

static int fingerprint_ok(HMODULE sim, char *why, size_t why_size) {
    uint8_t *base = (uint8_t *)sim;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    uint32_t stamp = nt->FileHeader.TimeDateStamp;
    if (stamp != TIMESTAMP_STEAM && stamp != TIMESTAMP_GAME_PASS) {
        snprintf(why, why_size, "simulation DLL timestamp 0x%08x, expected 0x%08x or 0x%08x: the game updated and the offsets need re-deriving",
                 stamp, TIMESTAMP_STEAM, TIMESTAMP_GAME_PASS);
        return 0;
    }
    if (strcmp((const char *)(base + RVA_ANCHOR_STRING), "sleep_until") != 0) {
        snprintf(why, why_size, "anchor string not where expected");
        return 0;
    }
    void *slot0 = *(void **)(base + RVA_QUEUE_VTABLE);
    if (slot0 != (void *)(base + RVA_QUEUE_DRAIN) && slot0 != (void *)hooked_drain) {
        snprintf(why, why_size, "queue vtable slot 0 is %p, expected %p", slot0, (void *)(base + RVA_QUEUE_DRAIN));
        return 0;
    }
    return 1;
}

static int install(void) {
    if (g_installed) return 1;
    HMODULE sim = GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!sim) {
        set_status("error: HaloSimulation_tag_release.dll is not loaded yet");
        return 0;
    }
    char why[512];
    if (!fingerprint_ok(sim, why, sizeof why)) {
        set_status("error: %s", why);
        return 0;
    }
    g_base = (uint8_t *)sim;
    g_evaluate = (evaluate_fn)(g_base + RVA_EVALUATE);
    g_in_game = (in_game_fn)(g_base + RVA_IN_GAME);
    g_vtable_slot = (void **)(g_base + RVA_QUEUE_VTABLE);
    g_out_buf = (char **)(g_base + RVA_OUT_BUF);
    g_out_size = (int32_t *)(g_base + RVA_OUT_SIZE);
    g_err_msg = (const char **)(g_base + RVA_ERR_MSG);
    g_err_offset = (int32_t *)(g_base + RVA_ERR_OFFSET);
    g_formatters = (format_fn *)(g_base + RVA_FORMATTERS);
    g_type_names = (const char **)(g_base + RVA_TYPE_NAMES);

    if (*g_vtable_slot != (void *)hooked_drain) {
        g_original_drain = (drain_fn)(g_base + RVA_QUEUE_DRAIN);
        DWORD old;
        if (!VirtualProtect(g_vtable_slot, sizeof(void *), PAGE_READWRITE, &old)) {
            set_status("error: VirtualProtect failed (%lu)", GetLastError());
            return 0;
        }
        InterlockedExchangePointer(g_vtable_slot, (void *)hooked_drain);
        VirtualProtect(g_vtable_slot, sizeof(void *), old, &old);
    }
    g_installed = 1;
    int restored = restore_cheats();
    void *shell = *(void **)(g_base + RVA_SHELL_PTR);
    set_status("ok base=%p shell=%p cheats=%d/3", (void *)g_base, shell, restored);
    return 1;
}

// ---- Exports, called from Lua through package.loadlib ------------------------------
//
// Both take Lua's `lua_State*` and ignore it, returning 0 results. Lua sees
// them as ordinary functions of no arguments.

__declspec(dllexport) int mjolnir_blam_open(void *L) {
    (void)L;
    install();
    return 0;
}

// Move a new request from request.txt into the mailbox, and a finished result
// from the mailbox into response.txt. Runs on whichever thread Lua calls it
// from; never on the simulation thread.
//
// request.txt:  "<id> <flags>\n<command>"      flags: 1 = run even at the frontend
// response.txt: "<id>\n<text>"
__declspec(dllexport) int mjolnir_blam_pump(void *L) {
    (void)L;
    if (!g_installed && !install()) return 0;

    FILE *f = NULL;
    if (fopen_s(&f, g_request_path, "rb") == 0 && f) {
        char buf[4600];
        size_t n = fread(buf, 1, sizeof buf - 1, f);
        fclose(f);
        buf[n] = '\0';
        int id = -1, flags = 0;
        char *nl = strchr(buf, '\n');
        if (nl && sscanf_s(buf, "%d %d", &id, &flags) >= 1 && id != g_last_request_id) {
            g_last_request_id = id;
            const char *cmd = nl + 1;
            EnterCriticalSection(&g_lock);
            strncpy_s(g_pending_text, sizeof g_pending_text, cmd, _TRUNCATE);
            // The engine's own preprocessor stops at the first newline anyway.
            char *end = strpbrk(g_pending_text, "\r\n");
            if (end) *end = '\0';
            g_pending_id = id;
            g_pending_force = flags & 1;
            g_has_pending = 1;
            LeaveCriticalSection(&g_lock);
        }
    }

    EnterCriticalSection(&g_lock);
    int has = g_has_result;
    int id = g_result_id;
    char text[8192];
    if (has) {
        memcpy(text, g_result_text, sizeof text);
        g_has_result = 0;
    }
    LeaveCriticalSection(&g_lock);
    if (has) {
        char out[8300];
        snprintf(out, sizeof out, "%d\n%s", id, text);
        write_file(g_response_path, out);
    }
    return 0;
}

/* Pinned for the life of the process. The game keeps calling the hooks this
   DLL installs, and a UE4SS mod reload (Ctrl+R) closes the Lua state that
   loaded it, which unloaded the code under them: the host crashed executing
   freed memory (two PCs, 2026-10-03). Pinned, a reload's package.loadlib
   finds the same module, statics and all, and the install guards skip a
   second install. */
BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        HMODULE pinned;
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN, (LPCWSTR)module, &pinned);
        DisableThreadLibraryCalls(module);
        InitializeCriticalSection(&g_lock);
        derive_paths(module);
        set_status("loaded, not installed");
    }
    return TRUE;
}
