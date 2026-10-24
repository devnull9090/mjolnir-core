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
//     index at +0x38, type at +0x3c. Types used here: 0 place from the
//     palette, 1 delete, 2 toggle the monitor, 3 grab, 4 release, 10
//     duplicate at the cursor.
//
//   * The palette is the scenario's own `map variant palettes` block, read
//     where the engine reads it. The DLL keeps which entry is selected and
//     lists every entry in forge_palette.txt for the Lua half.
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
#define RVA_CAN_CREATE       0x3049e0   // bool (tag index, out*): multiplayer data, quota and budget allow one more
#define RVA_SCENARIO         0x10c3558  // pointer to the loaded scenario's tag data
#define RVA_BLOCK_BASES      0x2c2ccc0  // tag data bases: a block handle h is at bases[h >> 28] + h*4

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

// The scenario's `map variant palettes` (docs/re/forge_engine.md, "Palettes").
#define SCENARIO_PALETTES    0x214      // count; +0x218 the block handle
#define PALETTE_DWORDS       5          // name, flags, entries (count, handle), thorage
#define PALETTE_ENTRIES      0x8
#define ENTRY_DWORDS         7          // name, variants (count, handle), ?, max allowed, price, thorage
#define ENTRY_VARIANTS       0x4
#define ENTRY_MAX_ALLOWED    0x10       // 0: no quota
#define VARIANT_DWORDS       6          // object reference (tag index at +0x10), variant name
#define VARIANT_TAG          0x10
#define MAX_PALETTES         16         // a request carries the palette in 4 bits
#define MAX_ENTRIES          256        // and the entry in 8
#define MAX_ROWS             512        // entries listed, all palettes together
#define RESCAN_TICKS         60         // re-read the palettes about every two seconds

enum {
    REQ_PLACE = 0,
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
    CMD_PLACE = 1 << 6,
    CMD_NEXT_ITEM = 1 << 7,
    CMD_PREV_ITEM = 1 << 8,
    CMD_NEXT_CATEGORY = 1 << 9,
    CMD_PREV_CATEGORY = 1 << 10,
};

#define DISTANCE_STEP 0.5f
#define DISTANCE_MIN  1.0f
#define DISTANCE_MAX  60.0f

typedef void (*tick_fn)(void *self, void *a, void *b, void *c);
typedef void (*send_fn)(uint8_t *request);
typedef uint8_t (*is_editing_fn)(uint32_t player);
typedef uint8_t (*place_check_fn)(uint32_t unused, uint32_t object, void *a, void *b, void *c);
typedef uint8_t (*can_create_fn)(uint64_t tag, void *out);

// ---- State --------------------------------------------------------------------
static uint8_t *g_base;
static tick_fn g_original_tick;
static send_fn g_send;
static is_editing_fn g_is_editing;
static place_check_fn g_place_check;
static can_create_fn g_can_create;
static unsigned g_tls_index = ~0u;
static int g_installed;

static volatile LONG g_commands;
// When the last command arrived (GetTickCount64). The simulation does not
// tick while the pause menu is up, so a key pressed there would otherwise
// act on resume; commands older than this are dropped.
static volatile LONG64 g_command_at;
#define COMMAND_MAX_AGE_MS 750

// The palettes, as the simulation thread last read them: one row per entry,
// naming its first variant's object (the converted maps give each entry one).
typedef struct {
    uint8_t palette, entry;
    uint8_t placeable;  // RVA_CAN_CREATE said yes when it was read
    char group[5];
    char tag[96];
} palette_row_t;

static palette_row_t g_rows[MAX_ROWS];
static int g_row_count;
static unsigned g_rows_version;      // bumped when the list changes
static unsigned g_rows_published = ~0u;
static int g_selected = -1;          // a row index, -1 none
static unsigned g_rescan;            // ticks until the next read
static int g_lifted;                 // times lift_bake_quotas lifted a palette's quotas

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
    int selected;    // the palette row selected, -1 none
    unsigned rows_version;
} snapshot_t;

static CRITICAL_SECTION g_lock;
static snapshot_t g_snap;
static unsigned g_published_tick = ~0u;
static char g_last[160];
static unsigned g_last_id;

static char g_dir[MAX_PATH];
static char g_state_path[MAX_PATH];
static char g_palette_path[MAX_PATH];
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
    snprintf(g_palette_path, MAX_PATH, "%sforge_palette.txt", g_dir);
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

// The last component of a tag's path ("shotgun"), or "", and its group as
// four characters ("weap"), or "".
static void tag_name(uint32_t tag, char *out, size_t size, char group[5]) {
    out[0] = '\0';
    group[0] = '\0';
    if (tag == 0xffffffffu) return;
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

// The same for an object: its tag's name and group.
static void object_tag_name(uint8_t *tls, uint32_t handle, char *out, size_t size, char group[5]) {
    out[0] = '\0';
    group[0] = '\0';
    if (handle == 0xffffffffu) return;
    uint8_t *objects = *(uint8_t **)(tls + TLS_OBJECTS);
    uint8_t *data = objects ? *(uint8_t **)(objects + ARRAY_DATA) : NULL;
    uint8_t *object = data ? *(uint8_t **)(data + 0x10 + (size_t)(handle & 0xffff) * OBJECT_ENTRY) : NULL;
    if (!object) return;
    tag_name(*(uint32_t *)object, out, size, group);
}

// ---- The palettes -----------------------------------------------------------------

// Element `index` of a tag block whose handle is `handle`, `dwords` wide.
static uint8_t *block_element(uint32_t handle, int index, int dwords) {
    uint8_t **bases = (uint8_t **)(g_base + RVA_BLOCK_BASES);
    uint8_t *base = bases[handle >> 28];
    if (!base) return NULL;
    return base + ((uint64_t)handle + (uint64_t)index * (uint64_t)dwords) * 4;
}

static uint8_t *palette_entry(uint8_t *scenario, int palette, int entry) {
    uint8_t *p = block_element(*(uint32_t *)(scenario + SCENARIO_PALETTES + 4), palette, PALETTE_DWORDS);
    return p ? block_element(*(uint32_t *)(p + PALETTE_ENTRIES + 4), entry, ENTRY_DWORDS) : NULL;
}

// The first variant's object of a palette entry: a tag index, -1 none.
static uint32_t entry_tag(uint8_t *entry) {
    if (!entry || *(int32_t *)(entry + ENTRY_VARIANTS) < 1) return 0xffffffffu;
    uint8_t *variant = block_element(*(uint32_t *)(entry + ENTRY_VARIANTS + 4), 0, VARIANT_DWORDS);
    return variant ? *(uint32_t *)(variant + VARIANT_TAG) : 0xffffffffu;
}

// The palette MJOLNIR's level bake wrote before Forge could place: one
// palette whose every entry's quota is what the map places, so nothing could
// ever be duplicated. Lift those quotas (0 is none), in memory, for this load
// of the scenario. A palette made any other way keeps its quotas.
static void lift_bake_quotas(uint8_t *scenario) {
    if (*(int32_t *)(scenario + SCENARIO_PALETTES) != 1) return;
    uint8_t *p = block_element(*(uint32_t *)(scenario + SCENARIO_PALETTES + 4), 0, PALETTE_DWORDS);
    int entries = p ? *(int32_t *)(p + PALETTE_ENTRIES) : 0;
    if (entries <= 0 || entries > MAX_ENTRIES) return;
    for (int e = 0; e < entries; e++) {
        uint8_t *entry = palette_entry(scenario, 0, e);
        if (!entry || *(int32_t *)(entry + ENTRY_MAX_ALLOWED) <= 0) return;
    }
    for (int e = 0; e < entries; e++) *(int32_t *)(palette_entry(scenario, 0, e) + ENTRY_MAX_ALLOWED) = 0;
    g_lifted++;
}

// Re-read the palettes; bump the version when the list differs. Simulation
// thread only.
static void read_palettes(void) {
    static palette_row_t rows[MAX_ROWS];
    uint8_t *scenario = *(uint8_t **)(g_base + RVA_SCENARIO);
    int count = 0;
    if (scenario) {
        lift_bake_quotas(scenario);
        int palettes = *(int32_t *)(scenario + SCENARIO_PALETTES);
        if (palettes > MAX_PALETTES) palettes = MAX_PALETTES;
        for (int p = 0; p < palettes; p++) {
            uint8_t *palette = block_element(*(uint32_t *)(scenario + SCENARIO_PALETTES + 4), p, PALETTE_DWORDS);
            int entries = palette ? *(int32_t *)(palette + PALETTE_ENTRIES) : 0;
            if (entries > MAX_ENTRIES) entries = MAX_ENTRIES;
            for (int e = 0; e < entries && count < MAX_ROWS; e++) {
                uint32_t tag = entry_tag(palette_entry(scenario, p, e));
                if (tag == 0xffffffffu) continue;
                palette_row_t *row = &rows[count++];
                memset(row, 0, sizeof *row);
                row->palette = (uint8_t)p;
                row->entry = (uint8_t)e;
                tag_name(tag, row->tag, sizeof row->tag, row->group);
                row->placeable = g_can_create(tag, NULL) != 0;
            }
        }
    }
    if (count != g_row_count || memcmp(rows, g_rows, sizeof(palette_row_t) * (size_t)count) != 0) {
        EnterCriticalSection(&g_lock);
        memcpy(g_rows, rows, sizeof(palette_row_t) * (size_t)count);
        g_row_count = count;
        g_rows_version++;
        LeaveCriticalSection(&g_lock);
    }
    if (g_selected >= g_row_count) g_selected = g_row_count - 1;
    if (g_selected < 0 && g_row_count > 0) g_selected = 0;
}

// A category is a run of rows in one palette with one tag group: the level
// bake writes a palette per group, and its older single palette, sorted by
// group, still browses as weapons, vehicles and so on.
static int same_category(int a, int b) {
    return g_rows[a].palette == g_rows[b].palette && strcmp(g_rows[a].group, g_rows[b].group) == 0;
}

static int category_first(int at) {
    while (at > 0 && same_category(at - 1, at)) at--;
    return at;
}

// Move the selection: `item_step` entries within its category, or
// `category_step` categories, to that category's first entry. Both wrap.
static void select_move(int item_step, int category_step) {
    if (g_row_count <= 0) return;
    int at = g_selected < 0 ? 0 : g_selected;
    if (item_step) {
        int first = category_first(at), last = at;
        while (last + 1 < g_row_count && same_category(last + 1, at)) last++;
        int span = last - first + 1;
        at = first + ((at - first + item_step) % span + span) % span;
    } else if (category_step > 0) {
        int from = at;
        while (at < g_row_count && same_category(at, from)) at++;
        if (at == g_row_count) at = 0;
    } else if (category_step < 0) {
        int first = category_first(at);
        at = category_first(first > 0 ? first - 1 : g_row_count - 1);
    }
    g_selected = at;
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
    if (commands & (CMD_NEXT_ITEM | CMD_PREV_ITEM)) {
        select_move(commands & CMD_NEXT_ITEM ? 1 : -1, 0);
    }
    if (commands & (CMD_NEXT_CATEGORY | CMD_PREV_CATEGORY)) {
        select_move(0, commands & CMD_NEXT_CATEGORY ? 1 : -1);
    }
    if (commands & CMD_PLACE) {
        uint8_t *scenario = *(uint8_t **)(g_base + RVA_SCENARIO);
        if (g_selected < 0 || g_selected >= g_row_count || !scenario) {
            note("this map has no Forge palette");
        } else {
            palette_row_t *row = &g_rows[g_selected];
            uint32_t tag = entry_tag(palette_entry(scenario, row->palette, row->entry));
            if (tag == 0xffffffffu || !g_can_create(tag, NULL)) {
                note("cannot place %s", row->tag);
            } else {
                // The engine places nothing while the player holds an object
                // (0x306260 returns), so drop it first: requests apply in the
                // order sent.
                if (held != 0xffffffffu) {
                    uint8_t release[5] = {0};
                    memcpy(release, &held, 4);
                    send(player, REQ_RELEASE, release, sizeof release);
                }
                // Palette, entry and variant (4, 8 and 5 bits on the wire),
                // then the point: the engine creates the object there and
                // grabs it.
                uint32_t fields[3] = {row->palette, row->entry, 0};
                uint8_t payload[24];
                memcpy(payload, fields, sizeof fields);
                memcpy(payload + 12, state + EDITOR_POINT, 12);
                send(player, REQ_PLACE, payload, sizeof payload);
                note("placed %s", row->tag);
            }
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
    s.selected = g_selected;
    s.rows_version = g_rows_version;
    g_snap = s;
    LeaveCriticalSection(&g_lock);
}

static void hooked_tick(void *self, void *a, void *b, void *c) {
    g_original_tick(self, a, b, c);
    uint8_t *tls = tls_block();
    if (!tls) return;
    int player = local_player(tls);
    if (g_rescan == 0) {
        read_palettes();
        g_rescan = RESCAN_TICKS;
    }
    g_rescan--;
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
    g_can_create = (can_create_fn)(base + RVA_CAN_CREATE);
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
__declspec(dllexport) int mjolnir_forge_place(void *L) { (void)L; return command(CMD_PLACE); }
__declspec(dllexport) int mjolnir_forge_next_item(void *L) { (void)L; return command(CMD_NEXT_ITEM); }
__declspec(dllexport) int mjolnir_forge_prev_item(void *L) { (void)L; return command(CMD_PREV_ITEM); }
__declspec(dllexport) int mjolnir_forge_next_category(void *L) { (void)L; return command(CMD_NEXT_CATEGORY); }
__declspec(dllexport) int mjolnir_forge_prev_category(void *L) { (void)L; return command(CMD_PREV_CATEGORY); }

// Write forge_state.txt when the simulation thread has seen a new tick since
// the last call: `key=value` lines. `forge=0` once ticks stop (no Forge game).
// When the palettes changed, forge_palette.txt first: one line per entry,
// `palette<TAB>entry<TAB>group<TAB>tag<TAB>placeable`; the state's
// `selected` is a line index into it (from 0) and `palette_version` says
// which list.
// Runs on whichever thread Lua calls it from; never on the simulation thread.
__declspec(dllexport) int mjolnir_forge_pump(void *L) {
    (void)L;
    if (!g_installed && !install()) return 0;
    EnterCriticalSection(&g_lock);
    snapshot_t s = g_snap;
    LeaveCriticalSection(&g_lock);
    int live = s.tick != g_published_tick;
    g_published_tick = s.tick;
    if (s.rows_version != g_rows_published) {
        static char list[MAX_ROWS * 128];
        size_t used = 0;
        EnterCriticalSection(&g_lock);
        for (int i = 0; i < g_row_count && used + 128 < sizeof list; i++) {
            palette_row_t *r = &g_rows[i];
            used += (size_t)snprintf(list + used, sizeof list - used, "%u\t%u\t%s\t%s\t%u\n", r->palette, r->entry,
                                     r->group, r->tag, r->placeable);
        }
        LeaveCriticalSection(&g_lock);
        list[used] = '\0';
        write_file(g_palette_path, list);
        g_rows_published = s.rows_version;
    }
    char text[1024];
    snprintf(text, sizeof text,
             "forge=%d\nplayer=%d\nediting=%d\nheld=%08x\nheld_tag=%s\nheld_group=%s\ncursor=%08x\ncursor_tag=%s\n"
             "cursor_group=%s\ndistance=%.1f\nlast=%s\nlast_id=%u\nselected=%d\npalette_version=%u\nlifted=%d\n",
             live, s.player, s.editing, s.held, s.held_tag, s.held_group, s.cursor, s.cursor_tag, s.cursor_group,
             s.distance, s.last, s.last_id, s.selected, s.rows_version, g_lifted);
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
        g_snap.selected = -1;
        g_published_tick = 0;
        derive_paths(module);
        set_status("loaded, not installed");
    }
    return TRUE;
}
