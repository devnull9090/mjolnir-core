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
//     duplicate at the cursor. Object properties (request 5) go straight to
//     the request's applier instead, and objects the editor cannot drag
//     (CE's markers) are placed and carried by the DLL; see those sections.
//
//   * The palette is the scenario's own `map variant palettes` block, read
//     where the engine reads it. The DLL keeps which entry is selected and
//     lists every entry in forge_palette.txt for the Lua half.
//
//   * Layouts: the map variant (what Forge edits) is saved with the
//     simulation's own encoder into a Reach-style `.mvar` file,
//     layouts\<MAP>.mvar beside native\, and read back with its decoder
//     (docs/re/map_variant_format.md). A saved layout replaces the map's own
//     in every game on that map, Forge or not: new-map's one call that builds
//     the variant from the scenario (0x2ace53 -> 0x32cc00) is pointed at a
//     wrapper that copies the layout in instead, the way the engine copies a
//     session-supplied variant (0x32bdb0). In a Forge game the Monitor can
//     also save, reload and revert to the map's own layout on the spot.
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
#include <math.h>
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

// Map variants (docs/re/map_variant_format.md, "Layouts" in docs/re/forge_engine.md).
#define RVA_MV_LIVE          0x32b600   // map variant *(void): the live one, NULL outside multiplayer
#define RVA_MV_ENCODE        0x32cfb0   // void (mv*, bitstream*)
#define RVA_MV_DECODE        0x32d810   // bool (mv*, bitstream*)
#define RVA_MV_COPY          0x32bdb0   // void (dst*, src*, bool): make src current, as new-map does with a session's
#define RVA_MV_FROM_SCENARIO 0x32cc00   // void (mv*): build from the scenario's placements
#define RVA_MV_DELETE_ALL    0x32f710   // void (void): delete every object the variant made
#define RVA_MV_CREATE_ALL    0x32f6a0   // void (mv*): create every entry's object (round reset, host migration)
#define RVA_MV_BUDGET        0x32e300   // void (mv*): recount the budget spent
#define RVA_APPLY_PROPERTIES 0x3071e0   // void (player, object, const properties *): request 5's applier
#define RVA_MV_ENTRY_DIRTY   0x4d1b70   // void (entry, 4): send an entry to the session again (host migration does)
#define RVA_NEW_MAP_BUILD    0x2ace53   // new-map's `call RVA_MV_FROM_SCENARIO`
#define MV_SIZE              0xd9c0
#define MV_ENTRIES           651
#define MV_MAP_ID            0x2b4
#define MV_ENCODING_VERSION  0x2b0      // i16: 32 in CE, 31 in MCC's files
#define MV_GUID              0x2b8      // 16 bytes, written from version 32 on
#define MV_BOUNDS            0x2c8      // x min, x max, y min, y max, z min, z max
#define MV_ENTRY_TABLE       0x14fc     // 651 entries of 0x4c
#define MV_ENTRY_STRIDE      0x4c
#define MV_BITS_BYTES        0x7000     // the buffer the engine's own normaliser (0x5323a0) uses

// The thread-local block (TLS[_tls_index]) and the structures it points at.
#define TLS_OBJECTS          0x20       // object data array
#define TLS_PLAYERS          0x30       // player data array
#define TLS_ENGINE_GLOBALS   0x38       // game-engine globals, G
#define TLS_PLAYER_USERS     0x118      // player -> local user map
#define ARRAY_DATA           0x50       // a data array's element pointer
#define ARRAY_COUNT          0x44       // a data array's slots in use (the high-water mark)
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
#define EDITOR_HOLD_AXES     0x40       // the held object's forward, left, up (3 floats each)
#define EDITOR_HOLD_BASIS    0x70       // the same, as the snap's reference
#define EDITOR_SNAP          0xc8       // rotation snap index: 0 free, 90, 45, 30, 15, 5 degrees
#define TAG_ENTRY_STRIDE     0x30       // tag table entry: +0x10 path
#define MAX_PLAYERS          16

// The scenario's `map variant palettes` (docs/re/forge_engine.md, "Palettes").
#define SCENARIO_MAP_ID      0x10
#define SCENARIO_PALETTES    0x214      // count; +0x218 the block handle
#define PALETTE_DWORDS       5          // name, flags, entries (count, handle), thorage
#define PALETTE_ENTRIES      0x8
#define ENTRY_DWORDS         7          // name, variants (count, handle), ?, max allowed, price, thorage
#define ENTRY_VARIANTS       0x4
#define ENTRY_MAX_ALLOWED    0x10       // 0: no quota
#define ENTRY_PRICE          0x14
#define MV_QUOTAS            0xd640     // per flat palette entry: minimum, maximum, placed (u8 each)
#define MV_BUDGET            0x2e0      // the budget (the scenario's sandbox budget), then spent at +0x2e4
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
    CMD_SAVE = 1 << 11,
    CMD_LOAD = 1 << 12,
    CMD_REVERT = 1 << 13,
    CMD_TEAM = 1 << 14,
    CMD_LABEL = 1 << 15,
    CMD_RESPAWN = 1 << 16,
    CMD_ORDER = 1 << 17,
    CMD_ROTATE_LEFT = 1 << 18,
    CMD_ROTATE_RIGHT = 1 << 19,
};

#define DISTANCE_STEP 0.5f
#define DISTANCE_MIN  1.0f
#define DISTANCE_MAX  60.0f

typedef void (*tick_fn)(void *self, void *a, void *b, void *c);
typedef void (*send_fn)(uint8_t *request);
typedef uint8_t (*is_editing_fn)(uint32_t player);
typedef uint8_t (*place_check_fn)(uint32_t unused, uint32_t object, void *a, void *b, void *c);
typedef uint8_t (*can_create_fn)(uint64_t tag, void *out);
typedef void *(*mv_live_fn)(void);
typedef void (*mv_encode_fn)(void *mv, void *bits);
typedef uint8_t (*mv_decode_fn)(void *mv, void *bits);
typedef void (*mv_copy_fn)(void *dst, const void *src, uint8_t flag);
typedef void (*mv_build_fn)(void *mv);
typedef void (*mv_void_fn)(void);
typedef void (*mv_entry_fn)(uint32_t entry, uint32_t how);
typedef int (*mv_flat_fn)(void *unused, uint32_t palette, uint32_t entry);
typedef void (*apply_properties_fn)(uint32_t player_handle, uint32_t object, const void *properties);

// ---- State --------------------------------------------------------------------
static uint8_t *g_base;
static tick_fn g_original_tick;
static send_fn g_send;
static is_editing_fn g_is_editing;
static place_check_fn g_place_check;
static can_create_fn g_can_create;
static mv_live_fn g_mv_live;
static mv_encode_fn g_mv_encode;
static mv_decode_fn g_mv_decode;
static mv_copy_fn g_mv_copy;
static mv_build_fn g_mv_from_scenario, g_mv_create_all, g_mv_budget;
static mv_void_fn g_mv_delete_all;
static mv_entry_fn g_mv_entry_dirty;
static mv_flat_fn g_mv_flat;
static apply_properties_fn g_apply_properties;
static unsigned g_tls_index = ~0u;
static int g_installed;
static int g_start_hook;               // new-map's call goes through layout_new_map

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
    int32_t maximum, price; // the entry's quota (0: none) and price
    int32_t placed;         // how many the map variant has (its quota record)
} palette_row_t;

static palette_row_t g_rows[MAX_ROWS];
static int g_row_count;
static unsigned g_rows_version;      // bumped when the list changes
static unsigned g_rows_published = ~0u;
static int g_selected = -1;          // a row index, -1 none
static unsigned g_rescan;            // ticks until the next read
static int g_lifted;                 // times lift_bake_quotas lifted a palette's quotas

#define PROPS_SIZE_SNAP 0x1c      // PROPS_SIZE, defined with the properties below

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
    // The target's Forge properties (the held object, else the one under the
    // cursor), when it belongs to the map variant.
    int budget, spent; // the map variant's budget (0: none) and what is spent
    int props;       // 0: no target, or not a map-variant object
    int team, order, respawn, mp_type, label;
    char label_name[64];
    uint8_t raw[PROPS_SIZE_SNAP];
} snapshot_t;

static CRITICAL_SECTION g_lock;
static snapshot_t g_snap;
static unsigned g_published_tick = ~0u;
static char g_last[160];
static unsigned g_last_id;

static char g_dir[MAX_PATH];
static char g_state_path[MAX_PATH];
static char g_palette_path[MAX_PATH];
static char g_slots_path[MAX_PATH];   // slots.txt: palette entries pointed at other tags
static char g_status_path[MAX_PATH];
static char g_layouts_dir[MAX_PATH];  // the mod's layouts folder, beside native
static char g_running_path[MAX_PATH]; // MJOLNIRLevelLoader's running.txt
static char g_layout[160];            // what the layout code last did, for pump (any engine)

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
    snprintf(g_slots_path, MAX_PATH, "%s..\\slots.txt", g_dir);
    snprintf(g_layouts_dir, MAX_PATH, "%s..\\layouts\\", g_dir);
    snprintf(g_running_path, MAX_PATH, "%s..\\..\\MJOLNIRLevelLoader\\running.txt", g_dir);
}

// The simulation thread's thread-local block. Only meaningful on that thread.
static uint8_t *tls_block(void) {
    void **tls_array = (void **)__readgsqword(0x58);
    return tls_array ? (uint8_t *)tls_array[g_tls_index] : NULL;
}

// A fireteam client's simulation (game options +0x11 == 4) sends its edits
// to the host as the engine's requests, and the host applies them. What the
// DLL does by hand (layouts, properties, markers, turning) is the host's.
#define TLS_GAME_OPTIONS     0x60
#define OPTIONS_ROLE         0x11       // 4: a client of someone else's game
static int is_client(uint8_t *tls) {
    uint8_t *options = tls ? *(uint8_t **)(tls + TLS_GAME_OPTIONS) : NULL;
    return options && options[OPTIONS_ROLE] == 4;
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

// Scenery from the palette was refused at the cursor: placing asks the
// engine for room there (0x3049e0 -> 0x2cf130, a search sized by the tag's
// bounding radius), and scenery resting on the ground never has it. Reach
// marks its Forge scenery "phased physics in forge" (multiplayer object
// flags, bit 1), which skips that search; CE's tags lack it. Set it, in
// memory, on every palette object that is not a weapon, vehicle or
// equipment, the first time it is seen. 1 when it was set now.
#define TAG_ROOT             0x1c       // tag table entry: the root's block handle
#define OBJECT_MP_BLOCK      0x124      // object definition: multiplayer object (count, handle)
#define MP_FLAGS             0x1a       // its flags word
#define MP_PHASED_IN_FORGE   0x2
static int g_phased;                 // objects given the flag

static int phase_in_forge(uint32_t tag, const char group[5]) {
    if (!strcmp(group, "weap") || !strcmp(group, "vehi") || !strcmp(group, "eqip")) return 0;
    uint8_t *table = *(uint8_t **)(g_base + RVA_TAG_TABLE);
    uint8_t *entries = table ? *(uint8_t **)(table + ARRAY_DATA) : NULL;
    if (!entries) return 0;
    uint8_t *root = block_element(*(uint32_t *)(entries + (size_t)(tag & 0xffff) * TAG_ENTRY_STRIDE + TAG_ROOT), 0, 0);
    if (!root || *(int32_t *)(root + OBJECT_MP_BLOCK) < 1) return 0;
    uint8_t *mp = block_element(*(uint32_t *)(root + OBJECT_MP_BLOCK + 4), 0, 0);
    if (!mp || (*(uint16_t *)(mp + MP_FLAGS) & MP_PHASED_IN_FORGE)) return 0;
    *(uint16_t *)(mp + MP_FLAGS) |= MP_PHASED_IN_FORGE;
    return 1;
}

// ---- Palette slots ----------------------------------------------------------
//
// A palette entry's object is the tag index in its first variant (+0x10),
// read every time the engine places from it (0x32f450 -> 0x5ee570). So an
// entry can be pointed at another loaded object tag at run time, and then
// places that instead. slots.txt beside native lists `palette:entry = tag
// path` lines, applied when the palettes are read; this is the hook Forge
// block packs use to reach maps baked before them (docs/forge_blocks.md).
// The tag must be loaded (the map references it) and be an object.
#define TAG_TABLE_COUNT      0x44

static int g_slots;                  // entries pointed elsewhere

// A loaded object tag by its full path, -1 if none.
static uint32_t object_tag_by_path(const char *path) {
    uint8_t *table = *(uint8_t **)(g_base + RVA_TAG_TABLE);
    uint8_t *entries = table ? *(uint8_t **)(table + ARRAY_DATA) : NULL;
    int count = table ? *(int32_t *)(table + TAG_TABLE_COUNT) : 0;
    for (int i = 0; entries && i < count; i++) {
        uint8_t *entry = entries + (size_t)i * TAG_ENTRY_STRIDE;
        const char *name = *(const char **)(entry + 0x10);
        uint16_t salt = *(uint16_t *)entry;
        if (!salt || !name || _stricmp(name, path)) continue;
        char group[5], leaf[8];
        tag_name((uint32_t)salt << 16 | (uint32_t)i, leaf, sizeof leaf, group);
        static const char *objects[] = {"scen", "bloc", "mach", "ctrl", "weap", "vehi", "eqip"};
        for (int k = 0; k < 7; k++)
            if (!strcmp(group, objects[k])) return (uint32_t)salt << 16 | (uint32_t)i;
    }
    return 0xffffffffu;
}

static void apply_slots(uint8_t *scenario) {
    FILE *f = NULL;
    if (fopen_s(&f, g_slots_path, "rb") != 0 || !f) return;
    char line[512];
    int applied = 0;
    while (fgets(line, sizeof line, f)) {
        int p, e;
        char path[400];
        if (line[0] == '#' || sscanf_s(line, " %d : %d = %399[^\r\n]", &p, &e, path, (unsigned)sizeof path) != 3)
            continue;
        char *end = path + strlen(path);
        while (end > path && (end[-1] == ' ' || end[-1] == '\t')) *--end = '\0';
        int palettes = *(int32_t *)(scenario + SCENARIO_PALETTES);
        if (p < 0 || p >= palettes || p >= MAX_PALETTES) continue;
        uint8_t *pal = block_element(*(uint32_t *)(scenario + SCENARIO_PALETTES + 4), p, PALETTE_DWORDS);
        if (!pal || e < 0 || e >= *(int32_t *)(pal + PALETTE_ENTRIES)) continue;
        uint8_t *entry = palette_entry(scenario, p, e);
        if (!entry || *(int32_t *)(entry + ENTRY_VARIANTS) < 1) continue;
        uint8_t *variant = block_element(*(uint32_t *)(entry + ENTRY_VARIANTS + 4), 0, VARIANT_DWORDS);
        uint32_t tag = object_tag_by_path(path);
        if (!variant || tag == 0xffffffffu) continue;
        *(uint32_t *)(variant + VARIANT_TAG) = tag;
        applied++;
    }
    fclose(f);
    g_slots = applied;
}

// Re-read the palettes; bump the version when the list differs. Simulation
// thread only.
static void read_palettes(void) {
    static palette_row_t rows[MAX_ROWS];
    uint8_t *scenario = *(uint8_t **)(g_base + RVA_SCENARIO);
    int count = 0;
    if (scenario) {
        lift_bake_quotas(scenario);
        apply_slots(scenario);
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
                g_phased += phase_in_forge(tag, row->group);
                row->placeable = g_can_create(tag, NULL) != 0;
                uint8_t *pe = palette_entry(scenario, p, e);
                row->maximum = *(int32_t *)(pe + ENTRY_MAX_ALLOWED);
                row->price = *(int32_t *)(pe + ENTRY_PRICE);
                uint8_t *mv = (uint8_t *)g_mv_live();
                int flat = g_mv_flat(NULL, (uint32_t)p, (uint32_t)e);
                row->placed = mv && flat >= 0 && flat < 256 ? mv[MV_QUOTAS + flat * 3 + 2] : 0;
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

// A category is the rows of one palette with one tag group, as the HUD shows
// them: the level bake writes a palette per group, its older single palette
// still browses as weapons, vehicles and so on, and an entry slots.txt points
// at a crate joins the crates even with scenery around it.
static int same_category(int a, int b) {
    return g_rows[a].palette == g_rows[b].palette && strcmp(g_rows[a].group, g_rows[b].group) == 0;
}

// The first row of `at`'s category.
static int category_first(int at) {
    for (int i = 0; i < at; i++)
        if (same_category(i, at)) return i;
    return at;
}

// Move the selection: `item_step` entries within its category, or
// `category_step` categories (in the order they first appear), to that
// category's first entry. Both wrap.
static void select_move(int item_step, int category_step) {
    if (g_row_count <= 0) return;
    int at = g_selected < 0 ? 0 : g_selected;
    if (item_step) {
        int members[MAX_ROWS], n = 0, here = 0;
        for (int i = 0; i < g_row_count; i++) {
            if (!same_category(i, at)) continue;
            if (i == at) here = n;
            members[n++] = i;
        }
        at = members[((here + item_step) % n + n) % n];
    } else if (category_step) {
        int firsts[MAX_ROWS], n = 0, here = 0;
        for (int i = 0; i < g_row_count; i++) {
            if (category_first(i) != i) continue;
            if (i == category_first(at)) here = n;
            firsts[n++] = i;
        }
        at = firsts[((here + category_step) % n + n) % n];
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
    __declspec(align(16)) uint8_t request[0x40]; // the encoder finds request 5's block at (+9) & ~1
    memset(request, 0, sizeof request);
    memcpy(request, payload, size);
    *(uint32_t *)(request + 0x38) = (uint32_t)player;
    *(uint16_t *)(request + 0x3c) = type;
    g_send(request);
}

// ---- Layouts ------------------------------------------------------------------------
//
// The engine's bitstream, as its own normaliser (0x5323a0) lays one out on its
// stack: the buffer's bounds and size, the mode (1 write, 3 read), and a
// 64-bit accumulator filled from the high bit.
#define BITS_BEGIN     0x00
#define BITS_END       0x08
#define BITS_SIZE      0x10
#define BITS_ALIGN     0x14
#define BITS_MODE      0x18
#define BITS_COUNT     0x20  // write: bits already in the buffer; read: bits in the accumulator
#define BITS_ACC       0x28
#define BITS_ACC_BITS  0x30  // write: bits in the accumulator
#define BITS_CURSOR    0x38
#define BITS_STRUCT    0x80  // the engine's is 0x48; zeroed spare room
#define BITS_WRITE     1
#define BITS_READ      3

static __declspec(align(16)) uint8_t g_mv_scratch[MV_SIZE];
static uint8_t g_bits[MV_BITS_BYTES];
static uint8_t g_file[MV_BITS_BYTES + 0x100];
static LONG g_deferred;              // commands to run again next tick (a load waits for a drop)

static void layout_note(const char *fmt, ...) {
    char text[sizeof g_layout];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(text, sizeof text, fmt, ap);
    va_end(ap);
    EnterCriticalSection(&g_lock);
    memcpy(g_layout, text, sizeof g_layout);
    LeaveCriticalSection(&g_lock);
}

// The running map's code, from running.txt ("CODE<TAB>game type<TAB>title");
// 0 when no multiplayer map runs or the code is not a plain name.
static int running_code(char *out, size_t size) {
    FILE *f = NULL;
    char line[256];
    if (fopen_s(&f, g_running_path, "rb") != 0 || !f) return 0;
    size_t n = fread(line, 1, sizeof line - 1, f);
    fclose(f);
    line[n] = '\0';
    size_t i = 0;
    for (; i < n && line[i] != '\t' && line[i] != '\r' && line[i] != '\n'; i++) {
        char c = line[i];
        int plain = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-';
        if (!plain || i + 1 >= size) return 0;
        out[i] = c;
    }
    out[i] = '\0';
    return i > 0;
}

static void layout_path(char *out, const char *code) {
    snprintf(out, MAX_PATH, "%s%s.mvar", g_layouts_dir, code);
}

// Move a map's layout file aside into layouts\history (kept, never deleted).
static void layout_retire(const char *code) {
    char from[MAX_PATH], dir[MAX_PATH], to[MAX_PATH];
    layout_path(from, code);
    if (GetFileAttributesA(from) == INVALID_FILE_ATTRIBUTES) return;
    snprintf(dir, MAX_PATH, "%shistory", g_layouts_dir);
    CreateDirectoryA(dir, NULL);
    SYSTEMTIME t;
    GetLocalTime(&t);
    snprintf(to, MAX_PATH, "%s\\%s-%04u%02u%02u-%02u%02u%02u.mvar", dir, code, t.wYear, t.wMonth, t.wDay, t.wHour,
             t.wMinute, t.wSecond);
    MoveFileExA(from, to, MOVEFILE_REPLACE_EXISTING);
}

// Encode a map variant with the engine's encoder; the payload's size in
// bytes, 0 when it does not fit.
static int mv_encode(void *mv, uint8_t *out, int cap) {
    uint8_t w[BITS_STRUCT];
    memset(w, 0, sizeof w);
    *(uint8_t **)(w + BITS_BEGIN) = out;
    *(uint8_t **)(w + BITS_END) = out + cap;
    *(int32_t *)(w + BITS_SIZE) = cap;
    *(int32_t *)(w + BITS_ALIGN) = 1;
    *(int32_t *)(w + BITS_MODE) = BITS_WRITE;
    *(uint8_t **)(w + BITS_CURSOR) = out;
    g_mv_encode(mv, w);
    // The bits still in the accumulator, high first (0x532434 onwards).
    int held = *(int32_t *)(w + BITS_ACC_BITS);
    uint64_t acc = *(uint64_t *)(w + BITS_ACC);
    if (held <= 0) acc = 0;
    else if (held < 64) acc <<= 64 - held;
    uint8_t *cursor = *(uint8_t **)(w + BITS_CURSOR);
    for (int k = 0; k < 8 && cursor >= out && cursor < out + cap; k++, cursor++) {
        *cursor = (uint8_t)(acc >> 56);
        acc <<= 8;
    }
    int64_t bits = (int64_t) * (int32_t *)(w + BITS_COUNT) + held;
    int64_t bytes = (bits + 7) / 8;
    return bytes > 0 && bytes <= cap ? (int)bytes : 0;
}

// Decode a payload into `mv` (MV_SIZE bytes) with the engine's decoder.
static int mv_decode(void *mv, const uint8_t *in, int len) {
    uint8_t r[BITS_STRUCT];
    memset(r, 0, sizeof r);
    *(const uint8_t **)(r + BITS_BEGIN) = in;
    *(const uint8_t **)(r + BITS_END) = in + len;
    *(int32_t *)(r + BITS_SIZE) = len;
    *(int32_t *)(r + BITS_ALIGN) = 1;
    *(int32_t *)(r + BITS_MODE) = BITS_READ;
    // The accumulator starts with the first eight bytes, big-endian.
    uint64_t acc = 0;
    int k = 0;
    for (; k < 8 && k < len; k++) acc = (acc << 8) | in[k];
    if (k > 0 && k < 8) acc <<= 64 - 8 * k;
    *(int32_t *)(r + BITS_COUNT) = 8 * k;
    *(uint64_t *)(r + BITS_ACC) = acc;
    *(const uint8_t **)(r + BITS_CURSOR) = in + k;
    memset(mv, 0, MV_SIZE);
    return g_mv_decode(mv, r) != 0;
}

static int mv_objects(const uint8_t *mv) {
    int n = 0;
    for (int i = 0; i < MV_ENTRIES; i++) n += mv[MV_ENTRY_TABLE + i * MV_ENTRY_STRIDE] & 1;
    return n;
}

static void put_be32(uint8_t *at, uint32_t v) {
    at[0] = (uint8_t)(v >> 24);
    at[1] = (uint8_t)(v >> 16);
    at[2] = (uint8_t)(v >> 8);
    at[3] = (uint8_t)v;
}

static uint32_t get_be32(const uint8_t *at) {
    return (uint32_t)at[0] << 24 | (uint32_t)at[1] << 16 | (uint32_t)at[2] << 8 | at[3];
}

static uint8_t *blf_chunk(uint8_t *at, const char sig[4], uint32_t size, uint16_t major, uint16_t minor) {
    memcpy(at, sig, 4);
    put_be32(at + 4, size);
    at[8] = (uint8_t)(major >> 8);
    at[9] = (uint8_t)major;
    at[10] = (uint8_t)(minor >> 8);
    at[11] = (uint8_t)minor;
    return at + 12;
}

// A Reach-style .mvar, as MCC ships them minus the content-header chunk (the
// payload carries its own): `_blf` 1.2, `mvar` 31.1 (20-byte hash, here zero,
// a big-endian length, the payload), `_eof` 1.1.
static int write_mvar(const char *path, const uint8_t *payload, int len) {
    uint8_t *at = g_file;
    uint8_t *body = blf_chunk(at, "_blf", 0x30, 1, 2);
    memset(body, 0, 0x30 - 12);
    body[0] = 0xff;
    body[1] = 0xfe;
    at += 0x30;
    uint32_t mvar_size = 12 + 20 + 4 + (uint32_t)len;
    body = blf_chunk(at, "mvar", mvar_size, 31, 1);
    memset(body, 0, 20);
    put_be32(body + 20, (uint32_t)len);
    memcpy(body + 24, payload, (size_t)len);
    at += mvar_size;
    uint32_t before = (uint32_t)(at - g_file);
    body = blf_chunk(at, "_eof", 17, 1, 1);
    put_be32(body, before);
    body[4] = 0;
    at += 17;
    char tmp[MAX_PATH];
    snprintf(tmp, MAX_PATH, "%s.tmp", path);
    FILE *f = NULL;
    if (fopen_s(&f, tmp, "wb") != 0 || !f) return 0;
    size_t want = (size_t)(at - g_file);
    size_t wrote = fwrite(g_file, 1, want, f);
    fclose(f);
    if (wrote != want) return 0;
    return MoveFileExA(tmp, path, MOVEFILE_REPLACE_EXISTING) != 0;
}

// The `mvar` payload of a file, copied to `out`; its length, or -1.
static int read_mvar(const char *path, uint8_t *out, int cap) {
    FILE *f = NULL;
    if (fopen_s(&f, path, "rb") != 0 || !f) return -1;
    size_t n = fread(g_file, 1, sizeof g_file, f);
    fclose(f);
    size_t at = 0;
    while (at + 12 <= n) {
        uint32_t size = get_be32(g_file + at + 4);
        if (size < 12 || at + size > n) return -1;
        if (memcmp(g_file + at, "mvar", 4) == 0) {
            if (size < 12 + 24) return -1;
            uint32_t len = get_be32(g_file + at + 12 + 20);
            if (len > (uint32_t)cap || 12 + 24 + len > size) return -1;
            memcpy(out, g_file + at + 12 + 24, len);
            return (int)len;
        }
        if (memcmp(g_file + at, "_eof", 4) == 0) break;
        at += size;
    }
    return -1;
}

// The scenario's map id (scnr +0x10), which the scenario build (0x32cc00)
// writes into a variant; -1 without a scenario. Converted maps carry -1 or 0.
static int32_t scenario_map_id(void) {
    uint8_t *scenario = *(uint8_t **)(g_base + RVA_SCENARIO);
    return scenario ? *(int32_t *)(scenario + SCENARIO_MAP_ID) : -1;
}

// Read and decode `code`'s layout into the scratch variant. A file whose map
// id names another real map is refused (the file name already ties it to the
// map; converted maps all have ids of 0 or -1). 1 done, 0 none saved, -1
// unusable (`why` says).
static int layout_read(const char *code, char *why, size_t size) {
    char path[MAX_PATH];
    layout_path(path, code);
    if (GetFileAttributesA(path) == INVALID_FILE_ATTRIBUTES) return 0;
    int len = read_mvar(path, g_bits, sizeof g_bits);
    if (len <= 0) {
        snprintf(why, size, "%s.mvar is not a map variant file", code);
        return -1;
    }
    if (!mv_decode(g_mv_scratch, g_bits, len)) {
        snprintf(why, size, "%s.mvar does not decode", code);
        return -1;
    }
    int32_t want = scenario_map_id(), got = *(int32_t *)(g_mv_scratch + MV_MAP_ID);
    if (want > 0 && got > 0 && want != got) {
        snprintf(why, size, "%s.mvar is for map id %d, this map is %d", code, got, want);
        return -1;
    }
    *(int32_t *)(g_mv_scratch + MV_MAP_ID) = want;
    return 1;
}

// Make the scratch variant current in `mv` (0x32bdb0, as new-map does with a
// session's). The copy derives the map id from the map GUID, which is zero on
// converted maps, giving -1: put back the scenario's, as its own build has.
static void mv_adopt(void *mv) {
    g_mv_copy(mv, g_mv_scratch, 0);
    *(int32_t *)((uint8_t *)mv + MV_MAP_ID) = scenario_map_id();
}

// Replace the objects of the live variant `mv` with the scratch variant's
// (or, when `scenario`, with the map's own), the way host migration
// (0x304190) recreates them: delete, rebuild, create, resend.
static void mv_replace(uint8_t *tls, void *mv, int scenario) {
    uint8_t *g = *(uint8_t **)(tls + TLS_ENGINE_GLOBALS);
    for (int p = 0; p < MAX_PLAYERS; p++) {
        uint8_t *state = g + G_EDITOR_STATE + (size_t)p * EDITOR_STRIDE;
        *(uint32_t *)(state + EDITOR_CURSOR) = 0xffffffffu;
    }
    g_mv_delete_all();
    if (scenario) g_mv_from_scenario(mv);
    else mv_adopt(mv);
    g_mv_create_all(mv);
    for (uint32_t i = 0; i < MV_ENTRIES; i++) g_mv_entry_dirty(i, 4);
    g_mv_budget(mv);
}

static void layout_save(void) {
    char code[64], path[MAX_PATH];
    uint8_t *mv = (uint8_t *)g_mv_live();
    if (!mv || !running_code(code, sizeof code)) {
        note("no layout to save here");
        return;
    }
    // CE builds its variants at encoding version 32 with a zero map GUID
    // (+0x2b8, 16 bytes), and the decoder refuses exactly that combination
    // (0x32db50). At version 31 the GUID is not written, and the decoder
    // derives it from the map id, which on a converted map gives zero again:
    // the same variant. So save a copy at 31.
    memcpy(g_mv_scratch, mv, MV_SIZE);
    static const uint8_t no_guid[16] = {0};
    if (*(int16_t *)(g_mv_scratch + MV_ENCODING_VERSION) >= 32 && memcmp(g_mv_scratch + MV_GUID, no_guid, 16) == 0)
        *(int16_t *)(g_mv_scratch + MV_ENCODING_VERSION) = 31;
    *(int32_t *)(g_mv_scratch + MV_MAP_ID) = scenario_map_id();
    int len = mv_encode(g_mv_scratch, g_bits, sizeof g_bits);
    if (!len) {
        note("save failed: the layout did not encode");
        return;
    }
    CreateDirectoryA(g_layouts_dir, NULL);
    // Check that it reads back before the saved one is replaced.
    if (!mv_decode(g_mv_scratch, g_bits, len)) {
        snprintf(path, MAX_PATH, "%s%s.unreadable.mvar", g_layouts_dir, code);
        write_mvar(path, g_bits, len);
        note("save failed: the layout does not read back (kept as %s.unreadable.mvar)", code);
        return;
    }
    layout_path(path, code);
    layout_retire(code);
    if (!write_mvar(path, g_bits, len)) {
        note("save failed: cannot write %s.mvar", code);
        return;
    }
    note("saved layout %s, %d objects", code, mv_objects(mv));
    layout_note("%s: saved, %d objects, %d bytes", code, mv_objects(mv), len);
}

static void layout_load(uint8_t *tls) {
    char code[64], why[160];
    uint8_t *mv = (uint8_t *)g_mv_live();
    if (!mv || !running_code(code, sizeof code)) {
        note("no layout to load here");
        return;
    }
    int got = layout_read(code, why, sizeof why);
    if (got == 0) {
        note("no saved layout for %s", code);
        return;
    }
    if (got < 0) {
        note("load failed: %s", why);
        return;
    }
    mv_replace(tls, mv, 0);
    note("loaded layout %s, %d objects", code, mv_objects(mv));
    layout_note("%s: loaded in Forge, %d objects", code, mv_objects(mv));
}

static void layout_revert(uint8_t *tls) {
    char code[64];
    uint8_t *mv = (uint8_t *)g_mv_live();
    if (!mv || !running_code(code, sizeof code)) {
        note("nothing to revert here");
        return;
    }
    layout_retire(code);
    mv_replace(tls, mv, 1);
    note("reverted to the map's own layout");
    layout_note("%s: the map's own layout (saved one moved to history)", code);
}

// New-map's call that builds the live variant from the scenario lands here:
// build it, then, when the map has a saved layout, make that current instead,
// as new-map does with a variant the session supplies. Simulation thread.
static void layout_new_map(void *mv) {
    // Palette slots first: a saved layout names palette entries, and a slot's
    // object is what its entry places (no Forge tick has run yet, and none
    // runs at all under Megalo).
    uint8_t *scenario = *(uint8_t **)(g_base + RVA_SCENARIO);
    if (scenario) apply_slots(scenario);
    g_mv_from_scenario(mv);
    char code[64], why[160];
    // A client's objects are the host's: its own saved layout must not
    // decide what it builds.
    if (is_client(tls_block()) || !running_code(code, sizeof code)) return;
    int got = layout_read(code, why, sizeof why);
    if (got == 0) {
        layout_note("%s: the map's own layout", code);
        return;
    }
    if (got < 0) {
        layout_note("%s: own layout, saved one refused: %s", code, why);
        return;
    }
    mv_adopt(mv);
    layout_note("%s: saved layout, %d objects", code, mv_objects((const uint8_t *)mv));
}

// Memory for a jump within reach of a rel32 call in the simulation DLL.
static uint8_t *alloc_near(uint8_t *base) {
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    uintptr_t gran = si.dwAllocationGranularity;
    uintptr_t start = (uintptr_t)base & ~(gran - 1);
    for (uintptr_t p = start - gran; p > gran && start - p < 0x7ff00000u; p -= gran) {
        void *m = VirtualAlloc((void *)p, 4096, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
        if (m) return (uint8_t *)m;
    }
    return NULL;
}

// Point the `call` at `site` (which must call `expect`) at `fn`, through a
// `mov rax, fn; jmp rax` stub at `stub`. 1 done or already done.
static int hook_call(uint8_t *site, uint8_t *expect, void *fn, uint8_t *stub) {
    if (site[0] != 0xe8) return 0;
    uint8_t *target = site + 5 + *(int32_t *)(site + 1);
    if (target == stub) return 1;
    if (target != expect) return 0;
    intptr_t rel = stub - (site + 5);
    if (rel != (int32_t)rel) return 0;
    stub[0] = 0x48;
    stub[1] = 0xb8;
    memcpy(stub + 2, &fn, 8);
    stub[10] = 0xff;
    stub[11] = 0xe0;
    FlushInstructionCache(GetCurrentProcess(), stub, 12);
    DWORD old;
    if (!VirtualProtect(site + 1, 4, PAGE_EXECUTE_READWRITE, &old)) return 0;
    int32_t rel32 = (int32_t)rel;
    memcpy(site + 1, &rel32, 4);
    VirtualProtect(site + 1, 4, old, &old);
    FlushInstructionCache(GetCurrentProcess(), site, 5);
    return 1;
}

// ---- Object properties (request 5) ------------------------------------------------
//
// Each map-variant entry carries the object's Forge properties at +0x30
// (codec 0x330230). Request 5 sends the object and a whole new block; the
// applier (0x3071e0) writes it into the entry and applies it to the object
// (0x32fcd0). The object knows its entry: object data +0x1c.
#define MV_LABEL_STRINGS     0x2f4      // 0x1000 bytes of NUL-terminated label names
#define MV_LABELS            0x12f8     // i16 per label: its name's offset in the strings, -1 none
#define MV_LABEL_COUNT       0x14f8
#define MV_ENTRY_PROPS       0x30
#define PROPS_SIZE           0x1c
#define PROPS_ORDER          0x11       // s8: spawn sequence
#define PROPS_RESPAWN        0x12       // u8: respawn time, seconds
#define PROPS_TYPE           0x13       // u8: multiplayer object type
#define PROPS_LABEL          0x14       // i16: Megalo label, -1 none
#define PROPS_TEAM           0x17       // u8: 0 red, 1 blue, ..., 8 neutral
#define TEAM_NEUTRAL         8
#define OBJECT_MV_ENTRY      0x1c       // i16 in the object: its map-variant entry, -1 none

static const uint8_t RESPAWN_TIMES[] = {0, 5, 10, 15, 30, 45, 60, 90, 120, 180};
#define MAX_ORDER 9

static uint8_t *object_data(uint8_t *tls, uint32_t handle) {
    if (handle == 0xffffffffu) return NULL;
    uint8_t *objects = *(uint8_t **)(tls + TLS_OBJECTS);
    uint8_t *data = objects ? *(uint8_t **)(objects + ARRAY_DATA) : NULL;
    return data ? *(uint8_t **)(data + 0x10 + (size_t)(handle & 0xffff) * OBJECT_ENTRY) : NULL;
}

// The object's map-variant entry's properties, or NULL.
static uint8_t *object_props(uint8_t *tls, uint8_t *mv, uint32_t handle) {
    uint8_t *object = object_data(tls, handle);
    if (!object || !mv) return NULL;
    int entry = *(int16_t *)(object + OBJECT_MV_ENTRY);
    if (entry < 0 || entry >= MV_ENTRIES) return NULL;
    uint8_t *e = mv + MV_ENTRY_TABLE + (size_t)entry * MV_ENTRY_STRIDE;
    return (e[0] & 1) ? e + MV_ENTRY_PROPS : NULL;
}

// A player's handle (salt << 16 | index), -1 if none.
static int player_handle(uint8_t *tls, int player) {
    uint8_t *players = *(uint8_t **)(tls + TLS_PLAYERS);
    uint8_t *data = players ? *(uint8_t **)(players + ARRAY_DATA) : NULL;
    if (!data) return -1;
    uint16_t salt = *(uint16_t *)(data + (size_t)player * PLAYER_STRIDE);
    return (int)((uint32_t)salt << 16 | (uint32_t)player);
}

static int label_count(const uint8_t *mv) {
    int n = *(const int32_t *)(mv + MV_LABEL_COUNT);
    return n < 0 ? 0 : n > 256 ? 256 : n;
}

// A label's name, or "" (none, or no name).
static void label_name(const uint8_t *mv, int label, char *out, size_t size) {
    out[0] = '\0';
    if (label < 0 || label >= label_count(mv)) return;
    int at = *(const int16_t *)(mv + MV_LABELS + label * 2);
    if (at < 0 || at >= 0x1000) return;
    const char *name = (const char *)(mv + MV_LABEL_STRINGS + at);
    strncpy_s(out, size, name, strnlen(name, 0x1000 - (size_t)at));
}

static const char *team_name(int team) {
    static const char *names[] = {"red", "blue", "green", "orange", "purple", "gold", "brown", "pink"};
    return team >= 0 && team < 8 ? names[team] : "neutral";
}

// Change one property of `target`, as request 5 would; or of `carried`, the
// properties of an object the DLL carries, which it gets when dropped.
static void edit_property(uint8_t *tls, int player, uint32_t target, LONG which, uint8_t *carried) {
    uint8_t *mv = (uint8_t *)g_mv_live();
    uint8_t *props = carried ? carried : object_props(tls, mv, target);
    if (!props) {
        note(target == 0xffffffffu ? "nothing targeted" : "that object has no Forge properties");
        return;
    }
    __declspec(align(16)) uint8_t block[PROPS_SIZE];
    memcpy(block, props, sizeof block);
    char name[64];
    if (which == CMD_TEAM) {
        // Neutral, red, blue: the teams a two-team game uses.
        uint8_t t = block[PROPS_TEAM];
        block[PROPS_TEAM] = t == TEAM_NEUTRAL ? 0 : t == 0 ? 1 : TEAM_NEUTRAL;
        note("team %s", team_name(block[PROPS_TEAM]));
    } else if (which == CMD_LABEL) {
        int label = *(int16_t *)(block + PROPS_LABEL) + 1;
        if (label >= label_count(mv)) label = -1;
        *(int16_t *)(block + PROPS_LABEL) = (int16_t)label;
        label_name(mv, label, name, sizeof name);
        note("label %s", label < 0 ? "none" : name[0] ? name : "(unnamed)");
    } else if (which == CMD_RESPAWN) {
        size_t n = sizeof RESPAWN_TIMES, i = 0;
        while (i < n && RESPAWN_TIMES[i] <= block[PROPS_RESPAWN]) i++;
        block[PROPS_RESPAWN] = RESPAWN_TIMES[i % n];
        note("respawn %u s", block[PROPS_RESPAWN]);
    } else {
        int8_t order = (int8_t)block[PROPS_ORDER];
        order = order >= MAX_ORDER || order < 0 ? 0 : (int8_t)(order + 1);
        block[PROPS_ORDER] = (uint8_t)order;
        note("spawn order %d", order);
    }
    if (carried) {
        memcpy(carried, block, sizeof block);
        return;
    }
    // Request 5 itself does not survive the trip through the simulation's
    // event queue intact: sent with respawn 45, the entry came back with 45
    // in its flags and the fields before them zeroed (2026-11-01). On the
    // host the DLL already runs where the queue's consumer does, so it calls
    // the applier the consumer would (0x3071e0): the same permission check
    // (0x307390), the same write into the entry, the same resend to the
    // session (0x32e870).
    // The applier takes the player's handle (salt << 16 | index): it checks
    // the holder of the object against it.
    int handle = player_handle(tls, player);
    if (handle != -1) g_apply_properties((uint32_t)handle, target, block);
}

// ---- Objects without physics: placed, carried and dropped by the DLL ----------------
//
// The editor's grab (0x306d30 -> 0x306890) drags an object by its Havok body:
// it reads object +0xcc (the physics component, 0xffff none) through the
// table at 0x10ccc90 and faults on an object without one. CE's flag stands,
// spawn points, health packs and teleporters have none, and placing from the
// palette grabs what it creates (0x306260 -> 0x306d30), so placing one
// crashed the simulation thread (UE4SS then sat in its crash dialog, which
// looked like a hang; 2026-11-01, and likely the first Forge run's hang).
//
// So for those the DLL does what the placement applier does minus the grab:
// make the map-variant entry (0x32eff0) and its object (0x32f450), count the
// quota (0x32e3b0), resend the entry (0x4d1b70). "Picking one up" remembers
// its palette entry, variant, facing and properties and deletes it; dropping
// makes it again at the cursor. Rotate turns what is carried or placed next.
#define RVA_MV_ADD_ENTRY     0x32eff0   // int (mv*, palette, entry, variant, point*, forward*, up*): entry, -1
#define RVA_MV_CREATE        0x32f450   // u32 (mv*, entry, bool): the entry's object, -1
#define RVA_MV_FLAT_INDEX    0x32ce10   // int (unused, palette, entry): the entry's index over all palettes
#define RVA_MV_QUOTA_ADD     0x32e3b0   // void (mv*, flat index)
#define OBJECT_PHYSICS       0xcc       // u16 in the object: what the grab drags by (below), 0xffff none
#define RVA_DRAG_ARRAY       0x10ccc90  // pointer to the data array object +0xcc indexes
#define DRAG_ELEMENT         0xc0
#define MV_ENTRY_PALETTE     0x2        // i16: flat palette index
#define MV_ENTRY_POSITION    0x8        // 3 floats
#define MV_ENTRY_FORWARD     0x14       // 3 floats, then up at +0x20
#define MV_ENTRY_VARIANT     0x2e       // u8
#define YAW_STEP             0.39269908f // 22.5 degrees
#define HELD_CARRIED         0xfffffffeu // the snapshot's `held` while the DLL carries one

typedef int (*mv_add_entry_fn)(void *mv, uint32_t palette, uint32_t entry, uint32_t variant, const float *point,
                               const float *forward, const float *up);
typedef uint32_t (*mv_create_fn)(void *mv, uint32_t entry, uint8_t flag);
typedef void (*mv_quota_fn)(void *mv, int flat);
static mv_add_entry_fn g_mv_add_entry;
static mv_create_fn g_mv_create;
static mv_quota_fn g_mv_quota_add;

static struct {
    int active;
    uint32_t palette, entry, variant;
    __declspec(align(16)) uint8_t props[PROPS_SIZE];
    char tag[96], group[5];
} g_carry;
static float g_yaw;                  // radians, for what is carried or placed next

// Whether the editor's grab can drag `handle`: the chain 0x306890 follows
// from object +0xcc, through the global array at 0x10ccc90 (0xc0-byte
// elements; +0x30, then +0x40), ends at the block it reads from +0x170.
// CE's marker scenery ends at NULL there.
static int has_physics(uint8_t *tls, uint32_t handle) {
    uint8_t *object = object_data(tls, handle);
    if (!object) return 0;
    uint16_t index = *(uint16_t *)(object + OBJECT_PHYSICS);
    uint8_t *array = *(uint8_t **)(g_base + RVA_DRAG_ARRAY);
    if (index == 0xffff || !array || index >= *(int32_t *)(array + ARRAY_COUNT)) return 0;
    uint8_t *element = *(uint8_t **)(array + ARRAY_DATA) + (size_t)index * DRAG_ELEMENT;
    uint8_t *inner = *(uint8_t **)(element + 0x30);
    return inner && *(uint8_t **)(inner + 0x40) != NULL;
}

// A flat palette index back to its palette and entry.
static int palette_of_flat(int flat, uint32_t *palette, uint32_t *entry) {
    uint8_t *scenario = *(uint8_t **)(g_base + RVA_SCENARIO);
    int palettes = scenario ? *(int32_t *)(scenario + SCENARIO_PALETTES) : 0;
    for (int p = 0; p < palettes && p < MAX_PALETTES && flat >= 0; p++) {
        uint8_t *pal = block_element(*(uint32_t *)(scenario + SCENARIO_PALETTES + 4), p, PALETTE_DWORDS);
        int n = pal ? *(int32_t *)(pal + PALETTE_ENTRIES) : 0;
        if (flat < n) {
            *palette = (uint32_t)p;
            *entry = (uint32_t)flat;
            return 1;
        }
        flat -= n;
    }
    return 0;
}

// Make a palette entry's object at `point`, facing `yaw`, and give it
// `props` when set. The object, or -1 (`why` says).
static uint32_t place_entry(int player_handle, uint32_t palette, uint32_t entry, uint32_t variant, const float point[3],
                            float yaw, const uint8_t *props, const char **why) {
    uint8_t *mv = (uint8_t *)g_mv_live();
    uint8_t *scenario = *(uint8_t **)(g_base + RVA_SCENARIO);
    uint32_t tag = scenario ? entry_tag(palette_entry(scenario, (int)palette, (int)entry)) : 0xffffffffu;
    float spot[3] = {point[0], point[1], point[2]};
    *why = NULL;
    if (!mv || tag == 0xffffffffu) {
        *why = "no palette entry";
        return 0xffffffffu;
    }
    if (!g_can_create(tag, spot)) {
        *why = "the map cannot place another here";
        return 0xffffffffu;
    }
    float forward[3] = {cosf(yaw), sinf(yaw), 0.0f}, up[3] = {0.0f, 0.0f, 1.0f};
    int index = g_mv_add_entry(mv, palette, entry, variant, spot, forward, up);
    if (index < 0) {
        *why = "the map variant is full";
        return 0xffffffffu;
    }
    uint32_t object = g_mv_create(mv, (uint32_t)index, 1);
    if (object == 0xffffffffu) {
        *why = "the object could not be made";
        return 0xffffffffu;
    }
    g_mv_quota_add(mv, g_mv_flat(NULL, palette, entry));
    if (props) g_apply_properties((uint32_t)player_handle, object, props);
    g_mv_entry_dirty((uint32_t)index, 4);
    return object;
}

// The object's map-variant entry, or NULL.
static uint8_t *object_entry(uint8_t *tls, uint8_t *mv, uint32_t handle) {
    uint8_t *props = object_props(tls, mv, handle);
    return props ? props - MV_ENTRY_PROPS : NULL;
}

// Markers (spawn points, flag stands) have no collision, so the editor's
// cursor ray (0x301510) never lands on one. When it lands on no object, aim
// at the map-variant object nearest the line from the player's unit through
// the cursor point instead: within 1 m of it, plus 2% of the distance.
#define RVA_OBJECT_ORIGIN    0x5a6780   // void (object, float[3])
#define AIM_REACH            60.0f
typedef void (*object_origin_fn)(uint32_t object, float *out);
static object_origin_fn g_object_origin;

static char g_aim[160];              // the last soft_target's numbers, for the state file

static uint32_t soft_target(uint8_t *tls, int player, const float point[3]) {
    uint8_t *players = *(uint8_t **)(tls + TLS_PLAYERS);
    uint8_t *data = players ? *(uint8_t **)(players + ARRAY_DATA) : NULL;
    if (!data) return 0xffffffffu;
    uint32_t unit = *(uint32_t *)(data + (size_t)player * PLAYER_STRIDE + PLAYER_UNIT);
    if (unit == 0xffffffffu) return 0xffffffffu;
    float o[3], d[3];
    g_object_origin(unit, o);
    float len = 0;
    for (int k = 0; k < 3; k++) {
        d[k] = point[k] - o[k];
        len += d[k] * d[k];
    }
    len = sqrtf(len);
    if (len < 0.01f) return 0xffffffffu;
    for (int k = 0; k < 3; k++) d[k] /= len;
    uint32_t best = 0xffffffffu;
    float best_off = 1e9f;
    uint8_t *objects = *(uint8_t **)(tls + TLS_OBJECTS);
    uint8_t *slots = objects ? *(uint8_t **)(objects + ARRAY_DATA) : NULL;
    int count = objects ? *(int32_t *)(objects + ARRAY_COUNT) : 0, candidates = 0;
    for (int i = 0; slots && i < count; i++) {
        uint8_t *slot = slots + (size_t)i * OBJECT_ENTRY;
        uint16_t salt = *(uint16_t *)slot;
        uint8_t *od = *(uint8_t **)(slot + 0x10);
        if (!salt || !od || *(int16_t *)(od + OBJECT_MV_ENTRY) < 0) continue;
        uint32_t object = (uint32_t)salt << 16 | (uint32_t)i;
        if (object == unit || has_physics(tls, object)) continue;
        float p[3], v[3], t = 0, off = 0;
        g_object_origin(object, p);
        for (int k = 0; k < 3; k++) {
            v[k] = p[k] - o[k];
            t += v[k] * d[k];
        }
        if (t < 0.5f || t > AIM_REACH) continue;
        for (int k = 0; k < 3; k++) off += (v[k] - t * d[k]) * (v[k] - t * d[k]);
        off = sqrtf(off);
        if (off < best_off) {
            best_off = off;
            best = off < 1.0f + 0.02f * t ? object : 0xffffffffu;
        }
        candidates++;
    }
    snprintf(g_aim, sizeof g_aim, "from %.1f %.1f %.1f to %.1f %.1f %.1f, %d markers, nearest %.2f m off", o[0], o[1], o[2],
             point[0], point[1], point[2], candidates, best_off);
    return best;
}

// The facing of an entry as a yaw.
static float entry_yaw(const uint8_t *e) {
    const float *f = (const float *)(e + MV_ENTRY_FORWARD);
    return atan2f(f[1], f[0]);
}

// ---- The simulation-thread side ---------------------------------------------------

static void act(uint8_t *tls, int player, LONG commands) {
    uint8_t *g = *(uint8_t **)(tls + TLS_ENGINE_GLOBALS);
    uint8_t *state = g + G_EDITOR_STATE + (size_t)player * EDITOR_STRIDE;
    uint32_t held = *(uint32_t *)(state + EDITOR_HELD);
    uint32_t cursor = *(uint32_t *)(state + EDITOR_CURSOR);
    int editing = g_is_editing((uint32_t)player) != 0;
    if (cursor == 0xffffffffu && editing) cursor = soft_target(tls, player, (const float *)(state + EDITOR_POINT));
    uint32_t target = held != 0xffffffffu ? held : cursor;

    // On a fireteam client only the engine's own requests (toggle, grab and
    // drop of what it can drag, delete, place and duplicate weapons, vehicles
    // and equipment) and saving the layout it sees; the rest is the host's.
    // Above all a client never asks the host to grab, place or copy a marker:
    // the host's engine would run the grab that faults on one.
    if (is_client(tls)) {
        const LONG host_only = CMD_LOAD | CMD_REVERT | CMD_TEAM | CMD_LABEL | CMD_RESPAWN | CMD_ORDER |
                               CMD_ROTATE_LEFT | CMD_ROTATE_RIGHT;
        if (commands & host_only) note("only the host can do that in a fireteam Forge game");
        commands &= ~host_only;
        if ((commands & CMD_GRAB) && held == 0xffffffffu && cursor != 0xffffffffu && !has_physics(tls, cursor)) {
            note("only the host can move markers in a fireteam Forge game");
            commands &= ~CMD_GRAB;
        }
        if ((commands & CMD_DUPLICATE) && target != 0xffffffffu && !has_physics(tls, target)) {
            note("only the host can copy markers in a fireteam Forge game");
            commands &= ~CMD_DUPLICATE;
        }
        if ((commands & CMD_PLACE) && g_selected >= 0 && g_selected < g_row_count) {
            const char *group = g_rows[g_selected].group;
            if (strcmp(group, "weap") && strcmp(group, "vehi") && strcmp(group, "eqip")) {
                note("only the host can place markers in a fireteam Forge game");
                commands &= ~CMD_PLACE;
            }
        }
        if (!commands) return;
    }

    // Layouts work as the Monitor or the Spartan. Replacing the objects
    // waits a tick for a held one to be dropped the engine's way.
    if (commands & CMD_SAVE) layout_save();
    if (commands & (CMD_LOAD | CMD_REVERT)) {
        static int waited;
        if (held != 0xffffffffu && waited < 30) {
            if (waited++ == 0) {
                uint8_t release[5] = {0};
                memcpy(release, &held, 4);
                send(player, REQ_RELEASE, release, sizeof release);
            }
            InterlockedOr(&g_deferred, commands & (CMD_LOAD | CMD_REVERT));
        } else if (held != 0xffffffffu) {
            waited = 0;
            note("drop what you hold first");
        } else if ((waited = 0), commands & CMD_REVERT) {
            layout_revert(tls);
        } else {
            layout_load(tls);
        }
    }
    commands &= ~(CMD_SAVE | CMD_LOAD | CMD_REVERT);
    if (!commands) return;

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
    int me = player_handle(tls, player);
    uint8_t *mv = (uint8_t *)g_mv_live();
    if (commands & (CMD_ROTATE_LEFT | CMD_ROTATE_RIGHT)) {
        float step = commands & CMD_ROTATE_LEFT ? YAW_STEP : -YAW_STEP;
        if (held != 0xffffffffu) {
            // A held object's orientation is the editor's hold transform,
            // which request 11's applier (0x305f6a) writes: forward, left and
            // up at +0x40, +0x4c, +0x58, and the same basis again at +0x70
            // for the rotation snap (+0xc8, an index into 0, 90, 45, 30, 15,
            // 5 degrees; 0x85dad0). Turn all of it about the vertical, with
            // the snap off so it stays where it is put.
            float c = cosf(step), sn = sinf(step);
            for (int v = 0; v < 3; v++) {
                float *a = (float *)(state + EDITOR_HOLD_AXES + v * 12);
                float x = a[0] * c - a[1] * sn, y = a[0] * sn + a[1] * c;
                a[0] = x;
                a[1] = y;
            }
            memcpy(state + EDITOR_HOLD_BASIS, state + EDITOR_HOLD_AXES, 36);
            *(int32_t *)(state + EDITOR_SNAP) = 0;
            const float *f = (const float *)(state + EDITOR_HOLD_AXES);
            note("facing %d", (int)lroundf(atan2f(f[1], f[0]) * 57.29578f));
        } else {
            g_yaw = atan2f(sinf(g_yaw + step), cosf(g_yaw + step));
            note("facing %d", (int)lroundf(g_yaw * 57.29578f));
        }
    }
    if ((commands & CMD_GRAB) && g_carry.active) {
        // Drop what the DLL carries: make it again at the cursor.
        const char *why;
        uint32_t made = place_entry(me, g_carry.palette, g_carry.entry, g_carry.variant,
                                    (const float *)(state + EDITOR_POINT), g_yaw, g_carry.props, &why);
        if (made == 0xffffffffu) {
            note("cannot drop %s: %s", g_carry.tag, why);
        } else {
            g_carry.active = 0;
            note("released");
        }
        commands &= ~CMD_GRAB;
    } else if ((commands & CMD_GRAB) && held == 0xffffffffu && cursor != 0xffffffffu && !has_physics(tls, cursor)) {
        // Pick up an object the editor cannot drag: remember it, delete it.
        uint8_t *e = object_entry(tls, mv, cursor);
        uint32_t palette, entry;
        if (!e || !palette_of_flat(*(int16_t *)(e + MV_ENTRY_PALETTE), &palette, &entry)) {
            note("this map's palette has no entry for that object");
        } else {
            g_carry.palette = palette;
            g_carry.entry = entry;
            g_carry.variant = e[MV_ENTRY_VARIANT];
            memcpy(g_carry.props, e + MV_ENTRY_PROPS, PROPS_SIZE);
            object_tag_name(tls, cursor, g_carry.tag, sizeof g_carry.tag, g_carry.group);
            g_yaw = entry_yaw(e);
            g_carry.active = 1;
            send(player, REQ_DELETE, &cursor, 4);
            note("grabbed");
        }
        commands &= ~CMD_GRAB;
    }
    if ((commands & CMD_DELETE) && g_carry.active) {
        g_carry.active = 0;
        note("deleted");
        commands &= ~CMD_DELETE;
    }
    if ((commands & CMD_DUPLICATE) && target != 0xffffffffu && !has_physics(tls, target)) {
        uint8_t *e = object_entry(tls, mv, target);
        uint32_t palette, entry;
        const char *why = "this map's palette has no entry for that object";
        uint32_t made = 0xffffffffu;
        if (e && palette_of_flat(*(int16_t *)(e + MV_ENTRY_PALETTE), &palette, &entry)) {
            __declspec(align(16)) uint8_t props[PROPS_SIZE];
            memcpy(props, e + MV_ENTRY_PROPS, PROPS_SIZE);
            made = place_entry(me, palette, entry, e[MV_ENTRY_VARIANT], (const float *)(state + EDITOR_POINT),
                               entry_yaw(e), props, &why);
        }
        if (made == 0xffffffffu) note("cannot duplicate: %s", why);
        else note("duplicated");
        commands &= ~CMD_DUPLICATE;
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
            // The applier asks the same with the cursor point, which also
            // looks for room there (0x2cf130, sized by the tag's bounding
            // radius); ask first, so a refusal says so.
            float spot[3];
            memcpy(spot, state + EDITOR_POINT, sizeof spot);
            if (tag == 0xffffffffu || !g_can_create(tag, NULL)) {
                note("cannot place %s", row->tag);
            } else if (!g_can_create(tag, spot)) {
                note("no room for %s there", row->tag);
            } else if (strcmp(row->group, "weap") && strcmp(row->group, "vehi") && strcmp(row->group, "eqip")) {
                // Not something the editor can drag (see "Objects without
                // physics"): placed where the cursor is, facing g_yaw.
                const char *why;
                if (place_entry(me, row->palette, row->entry, 0, spot, g_yaw, NULL, &why) == 0xffffffffu)
                    note("cannot place %s: %s", row->tag, why);
                else
                    note("placed %s", row->tag);
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
    static const LONG property_commands[] = {CMD_TEAM, CMD_LABEL, CMD_RESPAWN, CMD_ORDER};
    for (int i = 0; i < 4; i++) {
        if (commands & property_commands[i])
            edit_property(tls, player, target, property_commands[i], g_carry.active ? g_carry.props : NULL);
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
        if (s.cursor == 0xffffffffu && s.editing && s.held == 0xffffffffu && !g_carry.active)
            s.cursor = soft_target(tls, player, (const float *)(state + EDITOR_POINT));
        s.distance = *(float *)(state + EDITOR_DISTANCE);
        object_tag_name(tls, s.held, s.held_tag, sizeof s.held_tag, s.held_group);
        object_tag_name(tls, s.cursor, s.cursor_tag, sizeof s.cursor_tag, s.cursor_group);
        uint8_t *mv = (uint8_t *)g_mv_live();
        if (mv) {
            s.budget = *(int32_t *)(mv + MV_BUDGET);
            s.spent = *(int32_t *)(mv + MV_BUDGET + 4);
        }
        uint8_t *props = object_props(tls, mv, s.held != 0xffffffffu ? s.held : s.cursor);
        if (g_carry.active) {
            s.held = HELD_CARRIED;
            strncpy_s(s.held_tag, sizeof s.held_tag, g_carry.tag, _TRUNCATE);
            memcpy(s.held_group, g_carry.group, sizeof s.held_group);
            props = g_carry.props;
        }
        if (props) {
            s.props = 1;
            s.team = props[PROPS_TEAM];
            s.order = (int8_t)props[PROPS_ORDER];
            s.respawn = props[PROPS_RESPAWN];
            s.mp_type = props[PROPS_TYPE];
            s.label = *(int16_t *)(props + PROPS_LABEL);
            label_name(mv, s.label, s.label_name, sizeof s.label_name);
            memcpy(s.raw, props, PROPS_SIZE);
        }
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
    commands |= InterlockedExchange(&g_deferred, 0);
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
    g_mv_live = (mv_live_fn)(base + RVA_MV_LIVE);
    g_mv_encode = (mv_encode_fn)(base + RVA_MV_ENCODE);
    g_mv_decode = (mv_decode_fn)(base + RVA_MV_DECODE);
    g_mv_copy = (mv_copy_fn)(base + RVA_MV_COPY);
    g_mv_from_scenario = (mv_build_fn)(base + RVA_MV_FROM_SCENARIO);
    g_mv_create_all = (mv_build_fn)(base + RVA_MV_CREATE_ALL);
    g_mv_budget = (mv_build_fn)(base + RVA_MV_BUDGET);
    g_mv_delete_all = (mv_void_fn)(base + RVA_MV_DELETE_ALL);
    g_mv_entry_dirty = (mv_entry_fn)(base + RVA_MV_ENTRY_DIRTY);
    g_apply_properties = (apply_properties_fn)(base + RVA_APPLY_PROPERTIES);
    g_mv_add_entry = (mv_add_entry_fn)(base + RVA_MV_ADD_ENTRY);
    g_object_origin = (object_origin_fn)(base + RVA_OBJECT_ORIGIN);
    g_mv_create = (mv_create_fn)(base + RVA_MV_CREATE);
    g_mv_flat = (mv_flat_fn)(base + RVA_MV_FLAT_INDEX);
    g_mv_quota_add = (mv_quota_fn)(base + RVA_MV_QUOTA_ADD);
    // Saved layouts at game start: new-map's build goes through layout_new_map.
    // Optional: Forge itself works without it.
    static uint8_t *stub;
    if (!stub) stub = alloc_near(base);
    g_start_hook = stub && hook_call(base + RVA_NEW_MAP_BUILD, base + RVA_MV_FROM_SCENARIO, (void *)layout_new_map, stub);
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
    set_status("ok base=%p layouts=%s", (void *)base, g_start_hook ? "on" : "off (new-map call not as expected)");
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
__declspec(dllexport) int mjolnir_forge_save(void *L) { (void)L; return command(CMD_SAVE); }
__declspec(dllexport) int mjolnir_forge_load(void *L) { (void)L; return command(CMD_LOAD); }
__declspec(dllexport) int mjolnir_forge_revert(void *L) { (void)L; return command(CMD_REVERT); }
__declspec(dllexport) int mjolnir_forge_team(void *L) { (void)L; return command(CMD_TEAM); }
__declspec(dllexport) int mjolnir_forge_label(void *L) { (void)L; return command(CMD_LABEL); }
__declspec(dllexport) int mjolnir_forge_respawn(void *L) { (void)L; return command(CMD_RESPAWN); }
__declspec(dllexport) int mjolnir_forge_order(void *L) { (void)L; return command(CMD_ORDER); }
__declspec(dllexport) int mjolnir_forge_rotate_left(void *L) { (void)L; return command(CMD_ROTATE_LEFT); }
__declspec(dllexport) int mjolnir_forge_rotate_right(void *L) { (void)L; return command(CMD_ROTATE_RIGHT); }

// Write forge_state.txt when the simulation thread has seen a new tick since
// the last call: `key=value` lines. `forge=0` once ticks stop (no Forge game).
// When the palettes changed, forge_palette.txt first: one line per entry,
// `palette<TAB>entry<TAB>group<TAB>tag<TAB>placeable<TAB>placed<TAB>maximum
// <TAB>price` (maximum 0: no quota); the state's
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
            used += (size_t)snprintf(list + used, sizeof list - used, "%u\t%u\t%s\t%s\t%u\t%d\t%d\t%d\n", r->palette,
                                     r->entry, r->group, r->tag, r->placeable, r->placed, r->maximum, r->price);
        }
        LeaveCriticalSection(&g_lock);
        list[used] = '\0';
        write_file(g_palette_path, list);
        g_rows_published = s.rows_version;
    }
    char layout[sizeof g_layout];
    EnterCriticalSection(&g_lock);
    memcpy(layout, g_layout, sizeof layout);
    LeaveCriticalSection(&g_lock);
    char text[1280];
    snprintf(text, sizeof text,
             "forge=%d\nplayer=%d\nediting=%d\nheld=%08x\nheld_tag=%s\nheld_group=%s\ncursor=%08x\ncursor_tag=%s\n"
             "cursor_group=%s\ndistance=%.1f\nlast=%s\nlast_id=%u\nselected=%d\npalette_version=%u\nlifted=%d\n"
             "layout=%s\nphased=%d\naim=%s\nbudget=%d\nspent=%d\n",
             live, s.player, s.editing, s.held, s.held_tag, s.held_group, s.cursor, s.cursor_tag, s.cursor_group,
             s.distance, s.last, s.last_id, s.selected, s.rows_version, g_lifted, layout, g_phased, g_aim, s.budget, s.spent);
    if (s.props) {
        size_t used = strlen(text);
        snprintf(text + used, sizeof text - used, "team=%s\nlabel=%s\nrespawn=%d\norder=%d\nmp_type=%d\n",
                 team_name(s.team), s.label < 0 ? "" : s.label_name[0] ? s.label_name : "(unnamed)", s.respawn,
                 s.order, s.mp_type);
        // The raw block too: the fields not named above (shape, flags, colour).
        used = strlen(text);
        for (int i = 0; i < PROPS_SIZE && used + 3 < sizeof text; i++, used += 2) {
            snprintf(text + used, sizeof text - used, "%s%02x", i ? "" : "props=", s.raw[i]);
            if (!i) used += 6;
        }
        snprintf(text + used, sizeof text - used, "\n");
    }
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
