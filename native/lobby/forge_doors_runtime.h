/* Native automatic pack doors. Included after Lobby's simulation helpers.
 * The host moves native collision bodies and publishes their live MV pose;
 * the private cache retains the authored pose for editing and serialization. */
#include "forge_doors_core.h"
#pragma warning(push)
#pragma warning(disable:4505)
#include "../forge/pack_bindings.h"
#pragma warning(pop)

#define FD_METRES 3.048f
#define FD_ENTRY_COUNT 651
#define FD_ENTRY(mv, i) ((mv) + 0x14fc + (size_t)(i) * 0x4c)
typedef void *(*fd_live_fn)(void);
typedef unsigned char (*fd_edit_fn)(unsigned);
typedef void (*fd_origin_fn)(uint32_t, float *);
typedef void (*fd_pre_fn)(uint32_t, float *, float *, float *);
typedef unsigned char (*fd_pose_fn)(uint32_t, const float *, const float *, const float *, void *, unsigned char,
                                   unsigned char, unsigned char, unsigned char);
typedef void (*fd_modified_fn)(uint32_t);
typedef void (*fd_wake_fn)(uint32_t, unsigned char);
typedef void (*fd_dirty_fn)(unsigned, unsigned);
typedef struct {
    uint32_t handle, tag;
    int entry, palette, definition, seen;
    float closed[3], forward[3], up[3], last[3]; /* native world units */
    forge_door_motion motion;
} fd_panel;
typedef struct { float center[3], radius; uint32_t handle; } fd_obstacle;
static struct {
    unsigned char *base, *mv;
    uint64_t instance;
    int checked, supported, disabled, definitions, last_tick, was_client, forge_checked;
    forge_door_config config[FORGE_DOOR_MAX_DEFINITIONS];
    uint32_t tags[FORGE_DOOR_MAX_DEFINITIONS];
    fd_panel panels[FORGE_DOOR_MAX_ACTIVE];
    fd_obstacle obstacles[4096];
    forge_door_physics_cache physics;
} fd;

static unsigned char *fd_slot(unsigned char *table, unsigned index, unsigned stride, unsigned limit) {
    if (!table || *(uint32_t *)(table + 0x28) != 0x64407440 || !table[0x31]
        || *(uint32_t *)(table + 0x20) != stride) return NULL;
    unsigned maximum = *(uint32_t *)(table + 0x2c), count = *(uint32_t *)(table + 0x44);
    unsigned char *data = *(unsigned char **)(table + 0x50), *bits = *(unsigned char **)(table + 0x58);
    if (!data || !bits || maximum > limit || count > maximum || index >= count
        || !(bits[index / 8] & (1u << (index % 8)))) return NULL;
    return data + (size_t)index * stride;
}

static unsigned char *fd_object(unsigned char *tls, uint32_t handle) {
    if (handle == UINT32_MAX || !(handle >> 16)) return NULL;
    unsigned char *table = *(unsigned char **)(tls + 0x20);
    unsigned index = handle & 0xffff;
    unsigned char *slot = fd_slot(table, index, 0x18, 4096);
    if (!slot || *(uint16_t *)slot != (uint16_t)(handle >> 16) || *(uint16_t *)(slot + 6) < 0xe0
        || *(uint16_t *)(slot + 0x0c) != index) return NULL;
    return *(unsigned char **)(slot + 0x10);
}

static unsigned char *fd_block(uint32_t handle, unsigned index, unsigned dwords) {
    if (handle == UINT32_MAX) return NULL;
    unsigned char **bases = (unsigned char **)(fd.base + 0x2c2ccc0);
    unsigned char *base = bases[handle >> 28];
    return base ? base + ((uint64_t)handle + (uint64_t)index * dwords) * 4 : NULL;
}

static unsigned char *fd_tag_root(uint32_t tag, const char group[4]) {
    if (tag == UINT32_MAX || !(tag >> 16)) return NULL;
    unsigned char *table = *(unsigned char **)(fd.base + 0x182d1e8);
    unsigned char *slot = fd_slot(table, tag & 0xffff, 0x30, 65536);
    if (!slot || *(uint16_t *)slot != (uint16_t)(tag >> 16) || memcmp(slot + 4, group, 4)) return NULL;
    return fd_block(*(uint32_t *)(slot + 0x1c), 0, 1);
}

static int fd_tag_fixed(uint32_t tag, void *context) {
    (void)context;
    unsigned char *crate = fd_tag_root(tag, "colb");
    unsigned char *model = crate ? fd_tag_root(*(uint32_t *)(crate + 0x60), "tmlh") : NULL;
    unsigned char *physics = model ? fd_tag_root(*(uint32_t *)(model + 0x2c), "omhp") : NULL;
    int count = physics ? *(int *)(physics + 0x5c) : 0;
    if (count < 1 || count > 64) return 0;
    return forge_door_fixed_bodies(fd_block(*(uint32_t *)(physics + 0x60), 0, 0x34), count);
}

static int fd_stationary_crate(const unsigned char *object) {
    /* Attached crates can move with their parent. For free crates the native
       builder forces fixed on +dc bit6, otherwise uses the PHMO motion types.
       MV Normal alone does not turn a fixed construction PHMO dynamic. */
    if (*(const uint32_t *)(object + 0x14) != UINT32_MAX) return 0;
    return (*(const uint32_t *)(object + 0xdc) & 0x40) != 0
        || forge_door_cached_fixed(&fd.physics, *(const uint32_t *)object, fd_tag_fixed, NULL);
}

/* Resolve the entry's actual variant, as native 32f450 does. Do not infer
 * identity from a flat index alone: a palette can be rebound by the editor. */
static uint32_t fd_palette_tag(const unsigned char *entry) {
    int flat = *(const int16_t *)(entry + 2);
    unsigned variant = entry[0x2e];
    unsigned char *scenario = *(unsigned char **)(fd.base + 0x10c3558);
    int count = scenario ? *(int *)(scenario + 0x214) : 0;
    if (flat < 0 || count < 0 || count > 16) return UINT32_MAX;
    for (int p = 0; p < count; p++) {
        unsigned char *palette = fd_block(*(uint32_t *)(scenario + 0x218), (unsigned)p, 5);
        if (!palette) return UINT32_MAX;
        int entries = *(int *)(palette + 8);
        if (entries < 0 || entries > 256) return UINT32_MAX;
        if (flat < entries) {
            unsigned char *row = fd_block(*(uint32_t *)(palette + 0x0c), (unsigned)flat, 7);
            int variants = row ? *(int *)(row + 4) : 0;
            if (variants <= 0 || variants > 256 || variant >= (unsigned)variants) return UINT32_MAX;
            unsigned char *v = fd_block(*(uint32_t *)(row + 8), variant, 6);
            return v ? *(uint32_t *)(v + 0x10) : UINT32_MAX;
        }
        flat -= entries;
    }
    return UINT32_MAX;
}

static int fd_binding(const unsigned char *object, const unsigned char *entry, uint32_t handle, int index) {
    return forge_door_binding(handle, *(const uint32_t *)(entry + 4), *(const int16_t *)(object + 0x1c),
                              index, *(const uint32_t *)object, fd_palette_tag(entry));
}

static int fd_entry_ok(unsigned char *tls, const fd_panel *p) {
    unsigned char *od = fd_object(tls, p->handle);
    if (!od || !fd.mv || p->entry < 0 || p->entry >= FD_ENTRY_COUNT
        || *(uint32_t *)od != p->tag || *(int16_t *)(od + 0x1c) != p->entry
        || *(uint32_t *)(od + 0x14) != UINT32_MAX) return 0;
    unsigned char *e = FD_ENTRY(fd.mv, p->entry);
    return (*(uint16_t *)e & 1) && fd_binding(od, e, p->handle, p->entry)
        && *(int16_t *)(e + 2) == p->palette && (e[0x46] & 0xc0);
}

static int fd_same_pose(const fd_panel *p, const unsigned char *entry) {
    const float *position = (const float *)(entry + 8), *forward = (const float *)(entry + 0x14),
                *up = (const float *)(entry + 0x20);
    for (int k = 0; k < 3; k++)
        if (!isfinite(position[k]) || fabsf(position[k] - p->last[k]) > 0.0004f
            || !isfinite(forward[k]) || fabsf(forward[k] - p->forward[k]) > 0.0002f
            || !isfinite(up[k]) || fabsf(up[k] - p->up[k]) > 0.0002f) return 0;
    return 1;
}

static int fd_bounds(const float position[3], const float forward[3], const float up[3]) {
    float left[3];
    if (!forge_door_basis(forward, up, left)) return 0;
    const float *bounds = (const float *)(fd.mv + 0x2c8);
    for (int k = 0; k < 3; k++)
        if (!isfinite(position[k]) || !isfinite(bounds[k * 2]) || !isfinite(bounds[k * 2 + 1])
            || position[k] < bounds[k * 2] || position[k] > bounds[k * 2 + 1]) return 0;
    return 1;
}

static int fd_move(fd_panel *p, float offset) {
    float position[3], forward[3], up[3];
    for (int k = 0; k < 3; k++) position[k] = p->closed[k] + p->up[k] * offset / FD_METRES;
    memcpy(forward, p->forward, sizeof forward); memcpy(up, p->up, sizeof up);
    if (!fd_bounds(position, forward, up)) return 0;
    if (!memcmp(position, p->last, sizeof position)) return 1;
    ((fd_pre_fn)(fd.base + 0x5ec880))(p->handle, position, forward, up);
    if (!fd_bounds(position, forward, up)) return 0;
    for (int k = 0; k < 3; k++) {
        float desired = p->closed[k] + p->up[k] * offset / FD_METRES;
        if (fabsf(position[k] - desired) > 0.0001f || fabsf(forward[k] - p->forward[k]) > 0.00001f
            || fabsf(up[k] - p->up[k]) > 0.00001f) return 0;
    }
    if (!((fd_pose_fn)(fd.base + 0x59f600))(p->handle, position, forward, up, NULL, 1, 1, 0, 0)) return 0;
    /* Fixed crates otherwise remain asleep: the pose/physics setter alone
       does not schedule the active-object pass which publishes the render
       interpolation transform. Use the same wake/modified/active sequence as
       native Forge's held-object update (303060), without changing its mode. */
    ((fd_wake_fn)(fd.base + 0x5a5eb0))(p->handle, 0);
    ((fd_modified_fn)(fd.base + 0x59f470))(p->handle);
    ((fd_modified_fn)(fd.base + 0x5aa740))(p->handle);
    /* Forge reapplies every live MV pose each tick. Keep this transient pose
       in sync; only the save copy receives the authored closed origin. */
    unsigned char *e = FD_ENTRY(fd.mv, p->entry);
    memcpy(e + 8, position, sizeof position);
    memcpy(e + 0x14, forward, sizeof forward); memcpy(e + 0x20, up, sizeof up);
    memcpy(p->last, position, sizeof position);
    ((fd_dirty_fn)(fd.base + 0x4d1b70))((unsigned)p->entry, 2);
    return 1;
}

static int fd_load(void) {
    char path[MAX_PATH], line[768];
    FILE *file = NULL;
    fd.definitions = 0;
    if (!dir[0]) find_dir();
    if (snprintf(path, sizeof path, "%s..\\..\\..\\MJOLNIRForgePacks\\doors.txt", dir) >= (int)sizeof path) return 0;
    if (fopen_s(&file, path, "rb") || !file) return 1; /* no packs installed */
    int good = fgets(line, sizeof line, file)
        && (!strcmp(line, "forge-doors 1\n") || !strcmp(line, "forge-doors 1\r\n"));
    while (good && fgets(line, sizeof line, file)) {
        if ((!strchr(line, '\n') && !feof(file)) || fd.definitions == FORGE_DOOR_MAX_DEFINITIONS
            || !forge_door_parse(line, &fd.config[fd.definitions])) { good = 0; break; }
        for (int i = 0; i < fd.definitions; i++)
            if (!strcmp(fd.config[i].tag, fd.config[fd.definitions].tag)) good = 0;
        fd.definitions++;
    }
    if (ferror(file)) good = 0;
    fclose(file);
    if (!good || !fd.definitions) return good;
    if (snprintf(path, sizeof path, "%s..\\..\\..\\MJOLNIRForgePacks\\installed.txt", dir) >= (int)sizeof path) return 0;
    if (fopen_s(&file, path, "rb") || !file) return 0;
    int matches[FORGE_DOOR_MAX_DEFINITIONS] = {0}, rows = 0;
    while (good && fgets(line, sizeof line, file)) {
        forge_pack_binding binding;
        if (++rows > 4096 || (!strchr(line, '\n') && !feof(file)) || !forge_binding_parse(line, 0, &binding)) {
            good = 0; break;
        }
        for (int i = 0; i < fd.definitions; i++)
            if (!strcmp(fd.config[i].tag, binding.tag) && ++matches[i] != 1) good = 0;
    }
    if (ferror(file)) good = 0;
    fclose(file);
    for (int i = 0; i < fd.definitions; i++) if (matches[i] != 1) good = 0;
    if (!good) return 0;
    memset(fd.tags, 0xff, sizeof fd.tags);
    unsigned char *table = *(unsigned char **)(fd.base + 0x182d1e8);
    unsigned char *data = table ? *(unsigned char **)(table + 0x50) : NULL;
    int count = table ? *(int *)(table + 0x44) : 0;
    if (!data || count < 0 || count > 65536) return 0;
    for (int n = 0; n < count; n++) {
        unsigned char *tag = fd_slot(table, (unsigned)n, 0x30, 65536);
        if (!tag || !*(uint16_t *)tag || memcmp(tag + 4, "colb", 4)) continue;
        const char *name = *(const char **)(tag + 0x10);
        if (!name) continue;
        for (int i = 0; i < fd.definitions; i++)
            if (!strcmp(name, fd.config[i].tag)) fd.tags[i] = (uint32_t)*(uint16_t *)tag << 16 | (uint32_t)n;
    }
    return 1;
}

static int fd_ready(unsigned char **tls_out) {
    if (!fd.checked) {
        fd.base = (unsigned char *)GetModuleHandleA("HaloSimulation_tag_release.dll");
        if (!fd.base) return 0;
        IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(fd.base + ((IMAGE_DOS_HEADER *)fd.base)->e_lfanew);
        DWORD stamp = nt->FileHeader.TimeDateStamp;
        fd.supported = stamp == 0x6a7a740a || stamp == 0x6a7a741d;
        fd.checked = 1;
        if (!fd.supported) fireteam_log("forge doors: unsupported simulation timestamp %08lx; disabled", stamp);
    }
    if (!fd.supported) return 0;
    unsigned char *tls = sim_tls_block(), *g = tls ? *(unsigned char **)(tls + 0x60) : NULL;
    if (!g || g[0] || !g[1] || g[0x10] != 3) {
        fd.mv = NULL; memset(fd.panels, 0, sizeof fd.panels); return 0;
    }
    unsigned char *mv = ((fd_live_fn)(fd.base + 0x32b600))();
    if (!mv) return 0;
    uint64_t instance = *(uint64_t *)(g + 0x18);
    if (fd.mv != mv || fd.instance != instance) {
        fd.mv = mv; fd.instance = instance; fd.last_tick = -1;
        fd.was_client = g[0x11] == 4; fd.forge_checked = 0;
        memset(fd.panels, 0, sizeof fd.panels);
        memset(&fd.physics, 0, sizeof fd.physics);
        fd.disabled = !fd_load();
        fireteam_log("forge doors: world %llx, %d definitions%s", (unsigned long long)instance, fd.definitions,
                     fd.disabled ? "; inventory or compatibility check failed, disabled" : "");
    }
    // Forge can load after Lobby. Keep checking until a module is present;
    // once found it is pinned for the process lifetime by its own DllMain.
    if (fd.definitions && !fd.forge_checked) {
        HMODULE forge = GetModuleHandleA("mjolnir_forge.dll");
        if (forge) {
            fd.forge_checked = 1;
            if (!GetProcAddress(forge, "mjolnir_forge_utility_api_v1")) {
                fd.disabled = 1;
                fireteam_log("forge doors: update MJOLNIRForge to 0.4.0 for safe closed-pose saves; disabled");
            }
        }
    }
    *tls_out = tls;
    if (g[0x11] == 4) { fd.was_client = 1; return 0; }
    /* A join-in-progress client can receive a raised MV pose without its
       closed origin. Do not invent a new origin after host migration. */
    if (fd.was_client && !fd.disabled) {
        fd.disabled = 1;
        fireteam_log("forge doors: host migration requires rehosting to recover authored closed poses; disabled");
    }
    // Never animate before a compatible serializer is loaded: an older Forge
    // module arriving later must not inherit already-raised live MV poses.
    return !fd.disabled && fd.definitions > 0 && fd.forge_checked;
}

static int fd_held(unsigned char *tls, uint32_t handle) {
    unsigned char *engine = *(unsigned char **)(tls + 0x38);
    if (!engine || *(int *)(engine + 0x846c) != 1) return 0;
    for (int i = 0; i < 16; i++)
        if (*(uint32_t *)(engine + 0x17a4 + (size_t)i * 300 + 4) == handle) return 1;
    return 0;
}

static void fd_run(unsigned char *tls, float dt, int force_editing) {
    float players[16][3]; int player_count = 0, editing = force_editing;
    unsigned char *engine = *(unsigned char **)(tls + 0x38);
    int sandbox = engine && *(int *)(engine + 0x846c) == 1;
    unsigned char *pt = *(unsigned char **)(tls + 0x30), *pd = pt ? *(unsigned char **)(pt + 0x50) : NULL;
    int pn = pt ? *(int *)(pt + 0x44) : 0;
    if (pn < 0 || pn > 16) return;
    for (int i = 0; pd && i < pn; i++) {
        unsigned char *player = fd_slot(pt, (unsigned)i, 0x4b0, 16);
        if (!player || !*(uint16_t *)player) continue;
        uint32_t unit = *(uint32_t *)(player + 0x28);
        if (!fd_object(tls, unit)) continue;
        if (sandbox && ((fd_edit_fn)(fd.base + 0x2fe810))((unsigned)i)) { editing = 1; continue; }
        ((fd_origin_fn)(fd.base + 0x5a6780))(unit, players[player_count]);
        for (int k = 0; k < 3; k++) players[player_count][k] *= FD_METRES;
        player_count++;
    }
    unsigned char *ot = *(unsigned char **)(tls + 0x20), *od = ot ? *(unsigned char **)(ot + 0x50) : NULL;
    int on = ot ? *(int *)(ot + 0x44) : 0, obstacles = 0;
    if (!od || on < 0 || on > 4096) return;
    for (int i = 0; i < FORGE_DOOR_MAX_ACTIVE; i++) fd.panels[i].seen = 0;
    /* Collect once; there is no per-panel world scan or allocation. */
    for (int i = 0; i < on; i++) {
        unsigned char *slot = od + (size_t)i * 0x18;
        uint32_t handle = (uint32_t)*(uint16_t *)slot << 16 | (uint32_t)i;
        unsigned char *object = fd_object(tls, handle);
        if (!object) continue;
        int kind = *(uint16_t *)(slot + 4), entry = *(int16_t *)(object + 0x1c);
        unsigned char *e = entry >= 0 && entry < FD_ENTRY_COUNT ? FD_ENTRY(fd.mv, entry) : NULL;
        if (kind == 0 || kind == 1 || (kind == 10 && (!e || !(e[0x46] & 0xc0)) && !fd_stationary_crate(object))) {
            fd_obstacle *o = &fd.obstacles[obstacles++];
            o->handle = handle;
            for (int k = 0; k < 3; k++) o->center[k] = ((float *)(object + 0x30))[k] * FD_METRES;
            o->radius = *(float *)(object + 0x3c) * FD_METRES;
        }
        if (kind != 10 || !e || !(*(uint16_t *)e & 1) || !(e[0x46] & 0xc0)
            || *(uint32_t *)(object + 0x14) != UINT32_MAX) continue;
        int definition = -1;
        for (int n = 0; n < fd.definitions; n++) if (*(uint32_t *)object == fd.tags[n]) { definition = n; break; }
        if (definition < 0 || !fd_binding(object, e, handle, entry)) continue;
        fd_panel *panel = NULL, *empty = NULL;
        for (int n = 0; n < FORGE_DOOR_MAX_ACTIVE; n++) {
            if (fd.panels[n].handle == handle && fd.panels[n].entry == entry) { panel = &fd.panels[n]; break; }
            if (!fd.panels[n].handle && !empty) empty = &fd.panels[n];
        }
        if (fd_held(tls, handle)) { if (panel) memset(panel, 0, sizeof *panel); continue; }
        if (!panel) panel = empty;
        if (!panel) continue;
        if (!panel->handle || !fd_entry_ok(tls, panel) || !fd_same_pose(panel, e)) {
            memset(panel, 0, sizeof *panel);
            panel->handle = handle; panel->entry = entry; panel->tag = *(uint32_t *)object;
            panel->palette = *(int16_t *)(e + 2); panel->definition = definition;
            memcpy(panel->closed, e + 8, sizeof panel->closed); memcpy(panel->last, e + 8, sizeof panel->last);
            memcpy(panel->forward, e + 0x14, sizeof panel->forward); memcpy(panel->up, e + 0x20, sizeof panel->up);
        }
        panel->seen = 1;
    }
    for (int i = 0; i < FORGE_DOOR_MAX_ACTIVE; i++) {
        fd_panel *p = &fd.panels[i];
        if (!p->seen) { memset(p, 0, sizeof *p); continue; }
        float left[3], origin[3], local[3];
        if (!forge_door_basis(p->forward, p->up, left)) continue;
        for (int k = 0; k < 3; k++) origin[k] = p->closed[k] * FD_METRES;
        const forge_door_config *c = &fd.config[p->definition];
        int approach = 0, blocked = 0;
        for (int n = 0; n < player_count; n++)
            if (forge_door_local(players[n], origin, p->forward, left, p->up, local)
                && forge_door_trigger(c, local)) approach = 1;
        for (int n = 0; n < obstacles; n++) {
            const fd_obstacle *o = &fd.obstacles[n];
            if (o->handle != p->handle && forge_door_local(o->center, origin, p->forward, left, p->up, local)
                && forge_door_swept_blocked(c, p->motion.offset, 0, local, o->radius)) { blocked = 1; break; }
        }
        forge_door_motion next = p->motion;
        // Entering the editor must not slam a raised panel through a parked
        // vehicle. Retain the opening until its whole closing path is clear.
        if (!(editing && blocked)) forge_door_advance(c, &next, dt, approach, blocked, editing);
        /* Stop an opening leaf beneath a dynamic overhead obstacle. A player
           below a closing leaf requests reopening, not a crushing close. */
        int overhead = 0;
        if (!editing && next.offset > p->motion.offset) {
            for (int n = 0; n < obstacles; n++) {
                const fd_obstacle *o = &fd.obstacles[n];
                if (o->handle == p->handle || !forge_door_local(o->center, origin, p->forward, left, p->up, local)) continue;
                if (local[2] - o->radius >= p->motion.offset + c->size[2] - 0.1f
                    && forge_door_swept_blocked(c, p->motion.offset, next.offset, local, o->radius)) overhead = 1;
            }
        }
        if (!overhead && fd_move(p, next.offset)) p->motion = next;
    }
}

static void forge_doors_tick(void) {
    __try {
        unsigned char *tls = NULL;
        if (!fd_ready(&tls)) return;
        unsigned char *time = *(unsigned char **)(tls + 0x98);
        if (!time) return;
        int tick = *(int *)(time + 0x0c), rate = *(int16_t *)(time + 6);
        if (tick == fd.last_tick || rate < 10 || rate > 240) return;
        /* Never catch up several ticks through a moving body or advance on
           paused redraws. All movement is bounded by one simulation tick. */
        fd.last_tick = tick;
        fd_run(tls, 1.0f / (float)rate, 0);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        if (!fd.disabled) fireteam_log("forge doors: invalid native state; disabled for this world");
        fd.disabled = 1;
    }
}

/* Typed native exports, never Lua C functions. Both run on the simulation
 * thread. A save edits its scratch copy only; an edit closes panels first. */
__declspec(dllexport) int mjolnir_forge_doors_copy_closed(void *source, void *copy) {
    if (!copy || source == copy || GetCurrentThreadId() != sim_thread_id) return 0;
    __try {
        unsigned char *tls = NULL;
        int ready = fd_ready(&tls);
        if (!fd.supported || !fd.definitions) return 1;
        if (!tls || source != fd.mv) return 0;
        /* A client can save ordinary maps, but cannot safely save a live
           animated panel without the host's verified closed-origin cache. */
        unsigned char *ot = *(unsigned char **)(tls + 0x20), *od = ot ? *(unsigned char **)(ot + 0x50) : NULL;
        int count = ot ? *(int *)(ot + 0x44) : 0;
        if (!od || count < 0 || count > 4096) return 0;
        for (int n = 0; n < count; n++) {
            uint32_t handle = (uint32_t)*(uint16_t *)(od + (size_t)n * 0x18) << 16 | (uint32_t)n;
            unsigned char *object = fd_object(tls, handle);
            if (!object) continue;
            int entry = *(int16_t *)(object + 0x1c);
            if (entry < 0 || entry >= FD_ENTRY_COUNT || !(FD_ENTRY(fd.mv, entry)[0x46] & 0xc0)) continue;
            for (int d = 0; d < fd.definitions; d++) {
                if (*(uint32_t *)object != fd.tags[d]) continue;
                if (!ready) return 0;
                int known = 0;
                for (int i = 0; i < FORGE_DOOR_MAX_ACTIVE; i++) {
                    const fd_panel *p = &fd.panels[i];
                    if (p->handle == handle && fd_entry_ok(tls, p) && fd_same_pose(p, FD_ENTRY(fd.mv, entry))) known = 1;
                }
                if (!known) return 0;
            }
        }
        for (int i = 0; i < FORGE_DOOR_MAX_ACTIVE; i++) {
            const fd_panel *p = &fd.panels[i];
            if (!p->handle || !fd_entry_ok(tls, p) || !fd_same_pose(p, FD_ENTRY(fd.mv, p->entry))) continue;
            unsigned char *e = FD_ENTRY((unsigned char *)copy, p->entry);
            memcpy(e + 8, p->closed, sizeof p->closed);
            memcpy(e + 0x14, p->forward, sizeof p->forward); memcpy(e + 0x20, p->up, sizeof p->up);
        }
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) { fd.disabled = 1; return 0; }
}

__declspec(dllexport) int mjolnir_forge_doors_close_for_edit(uint32_t target) {
    if (GetCurrentThreadId() != sim_thread_id) return 0;
    __try {
        unsigned char *tls = NULL;
        if (!fd_ready(&tls)) return 1;
        fd_run(tls, 0, 1);
        for (int i = 0; i < FORGE_DOOR_MAX_ACTIVE; i++)
            if (fd.panels[i].handle == target && fd.panels[i].motion.offset > 0.001f) return 0;
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) { fd.disabled = 1; return 0; }
}
