/* Native PWR adapter. Included after the established simulation/TLS helpers.
 * Megalo globals are READ ONLY here: phase, score and capture authority stays
 * in the host's native Megalo interpreter and its existing replication.
 * Only owning peers apply biped movement. The host drives named transports.
 * No filesystem, allocation or UObject reflection occurs on a steady tick. */
#include "warfare_core.h"
#include "lua_channel.h"

typedef struct {
    int ready, status, host, rate, tick, layout, insertion_seconds, globals[12];
    uint64_t sampled_ms;
    uint64_t instance;
    warfare_sample sample[WARFARE_PLAYERS];
    int stage[WARFARE_PLAYERS];
    float steering[WARFARE_PLAYERS];
    int braking[WARFARE_PLAYERS];
} warfare_snapshot;
static SRWLOCK warfare_snapshot_lock = SRWLOCK_INIT;
static warfare_snapshot warfare_published;
static volatile LONG warfare_enabled, warfare_action, warfare_recheck;
typedef struct {
    uint64_t instance, updated_ms;
    uint32_t unit;
    float forward, right, yaw;
    int brake, jump;
} warfare_controls;
static SRWLOCK warfare_controls_lock = SRWLOCK_INIT;
static warfare_controls warfare_local_controls[2];
static struct {
    unsigned char *base;
    int supported, last_tick, last_phase, map_ok, disabled, was_client, transport_created, hs_failures, duration_valid;
    float insertion_seconds;
    uint64_t instance;
    warfare_player player[WARFARE_PLAYERS];
    warfare_sample previous[WARFARE_PLAYERS];
    int previous_valid[WARFARE_PLAYERS];
    uint16_t admitted[WARFARE_PLAYERS];
    int seat[WARFARE_PLAYERS];
    uint32_t carrier[2];
} warfare;

static int warfare_build(void) {
    if (warfare.base) return warfare.supported;
    unsigned char *base = (unsigned char *)GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!base) return 0;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    DWORD stamp = nt->FileHeader.TimeDateStamp;
    warfare.base = base;
    warfare.supported = stamp == 0x6a7a740a || stamp == 0x6a7a741d;
    if (!warfare.supported) fireteam_log("warfare: unsupported simulation timestamp %08lx; disabled", stamp);
    return warfare.supported;
}

static const char *warfare_tag_name(uint32_t tag) {
    if (tag == WARFARE_NONE || !(tag >> 16)) return NULL;
    unsigned char *table = *(unsigned char **)(warfare.base + 0x182d1e8);
    unsigned char *entry = fd_slot(table, tag & 0xffff, 0x30, 65536);
    if (!entry || *(uint16_t *)entry != (uint16_t)(tag >> 16)) return NULL;
    return *(const char **)(entry + 0x10);
}

static int warfare_transport(const unsigned char *object) {
    const char *name = object ? warfare_tag_name(*(const uint32_t *)object) : NULL;
    return name && !_stricmp(name, "objects\\mjolnir\\warfare\\pelican\\pwr_pelican");
}

static int warfare_map_layout(const unsigned char *scenario) {
    /* CU4 scenario.cutscene_flags: block+0x404, packed pointer+0x408;
     * 32-byte records, position+8. Both tag definitions and the stock HS
     * object_teleport evaluator agree. No calls through guessed native ABIs. */
    unsigned count = *(const unsigned *)(scenario + 0x404);
    uint32_t handle = *(const uint32_t *)(scenario + 0x408);
    unsigned char **bases = (unsigned char **)(warfare.base + 0x2c2ccc0);
    if (!count || count > 512 || handle == WARFARE_NONE || !bases[handle >> 28]) return 0;
    const unsigned char *flags = bases[handle >> 28] + (uint64_t)handle * 4;
    unsigned found = 0;
    for (unsigned i = 0; i < count; i++) {
        const float *p = (const float *)(flags + i * 32 + 8);
        float metres[3]; for (int k = 0; k < 3; k++) metres[k] = p[k] * WARFARE_METRES_PER_WU;
        found |= warfare_layout_flag(metres);
    }
    return found == WARFARE_LAYOUT_MARKER_MASK;
}

/* Match the active scenario's tag-data pointer, not merely an installed PWR
 * package. Package-derived and legacy tag-name forms are both explicit. */
static int warfare_map(void) {
    unsigned char *scenario = *(unsigned char **)(warfare.base + 0x10c3558);
    unsigned char *table = *(unsigned char **)(warfare.base + 0x182d1e8);
    if (!scenario || !table) return 0;
    unsigned count = *(unsigned *)(table + 0x44);
    if (count > 65536) return 0;
    unsigned char **bases = (unsigned char **)(warfare.base + 0x2c2ccc0);
    for (unsigned i = 0; i < count; i++) {
        unsigned char *entry = fd_slot(table, i, 0x30, 65536);
        if (!entry || memcmp(entry + 4, "rncs", 4)) continue;
        uint32_t handle = *(uint32_t *)(entry + 0x1c);
        if (handle == WARFARE_NONE || !bases[handle >> 28]
            || bases[handle >> 28] + (uint64_t)handle * 4 != scenario) continue;
        const char *name = *(const char **)(entry + 0x10);
        if (!name) return 0;
        int ok = !_stricmp(name, "levels\\halo1\\solo\\pwr\\_generated_\\pwr")
            || !_stricmp(name, "levels\\halo1\\solo\\pwr\\pwr");
        if (ok && !warfare_map_layout(scenario)) {
            fireteam_log("warfare: PWR baked gameplay flags do not match layout %d; disabled", WARFARE_LAYOUT_REVISION);
            return 0;
        }
        fireteam_log("warfare: active scenario %s: %s (layout %d)", name,
                     ok ? "PWR accepted" : "not PWR; disabled", WARFARE_LAYOUT_REVISION);
        return ok;
    }
    return 0;
}

static int warfare_hs(const char *line) {
    if (!hs_evaluate || GetCurrentThreadId() != sim_thread_id) return 0;
    int value = -1, type = 0;
    int ok = hs_evaluate(0, "mjolnir_warfare", line, 1, 0, &value, &type) != 0;
    if (!ok && warfare.hs_failures < 4) {
        warfare.hs_failures++;
        fireteam_log("warfare: HS evaluator rejected %s (value=%d type=%d; %d/4)",
                     line, value, type, warfare.hs_failures);
    }
    return ok;
}

static unsigned char *warfare_biped(unsigned char *tls, uint32_t handle) {
    unsigned char *object = fd_object(tls, handle);
    unsigned char *slot = object ? fd_slot(*(unsigned char **)(tls + 0x20), handle & 0xffff, 0x18, 4096) : NULL;
    /* Contact fields below are biped-specific; never read them from a small
     * object datum or an arbitrary vehicle returned through a player slot. */
    return slot && *(uint16_t *)(slot + 4) == 0 && *(uint16_t *)(slot + 6) >= 0xa1c ? object : NULL;
}

static int warfare_outside_carrier(unsigned char *tls, uint32_t handle, const unsigned char *unit) {
    unsigned char *carrier = fd_object(tls, handle);
    if (!carrier) return 1; /* the exact salted carrier has already retired */
    if (!warfare_transport(carrier)) return 0;
    float center[3], rider[3];
    for (int k = 0; k < 3; k++) {
        center[k] = ((const float *)(carrier + 0x30))[k] * WARFARE_METRES_PER_WU;
        rider[k] = ((const float *)(unit + 0x30))[k] * WARFARE_METRES_PER_WU;
    }
    return warfare_carrier_clear(center, *(float *)(carrier + 0x3c) * WARFARE_METRES_PER_WU,
                                   rider, *(const float *)(unit + 0x3c) * WARFARE_METRES_PER_WU);
}

static int warfare_clear_cabin(unsigned char *tls, int i, const warfare_sample *s) {
    unsigned char *unit = warfare_biped(tls, s->unit), *carrier = fd_object(tls, warfare.player[i].carrier);
    if (!unit || *(uint32_t *)(unit + 0x14) != WARFARE_NONE || !warfare_transport(carrier)) return 0;
    float center[3], rider[3], origin[3], candidate[3], position[3], forward[3], up[3], zero[3] = {0}, check[3];
    float radius = *(float *)(carrier + 0x3c) * WARFARE_METRES_PER_WU;
    float rider_radius = *(float *)(unit + 0x3c) * WARFARE_METRES_PER_WU;
    for (int k = 0; k < 3; k++) {
        center[k] = ((float *)(carrier + 0x30))[k] * WARFARE_METRES_PER_WU;
        rider[k] = ((float *)(unit + 0x30))[k] * WARFARE_METRES_PER_WU;
        origin[k] = ((float *)(unit + 0x44))[k] * WARFARE_METRES_PER_WU;
    }
    if (!warfare_ejection_point(center, radius, (float *)(carrier + 0x50), rider, rider_radius, origin, candidate)) return 0;
    memcpy(forward, unit + 0x50, sizeof forward); memcpy(up, unit + 0x5c, sizeof up);
    if (!warfare_velocity_frame(forward, up, zero, check)) return 0;
    for (int k = 0; k < 3; k++) position[k] = candidate[k] / WARFARE_METRES_PER_WU;
    /* Verified native teleporter/Forge pose path; no raw position writes.
     * Native setter synchronizes physics and spatial/network dirty state.
     * It is not a terrain penetration query: accept only the bounded route
     * ejection point outside the complete carrier/rider bounding spheres. */
    ((fd_pre_fn)(warfare.base + 0x5ec880))(s->unit, position, forward, up);
    if (!warfare_velocity_frame(forward, up, zero, check)) return 0;
    float actual_center[3], actual_origin[3];
    for (int k = 0; k < 3; k++) {
        actual_origin[k] = position[k] * WARFARE_METRES_PER_WU;
        if (!isfinite(actual_origin[k]) || fabsf(actual_origin[k] - candidate[k]) > 0.05f) return 0;
        actual_center[k] = actual_origin[k] + rider[k] - origin[k];
    }
    if (!warfare_inside(actual_origin, warfare_play_min, warfare_play_max)
        || !warfare_carrier_clear(center, radius, actual_center, rider_radius)) return 0;
    if (!((fd_pose_fn)(warfare.base + 0x59f600))(s->unit, position, forward, up, NULL, 1, 1, 0, 0)) return 0;
    ((fd_wake_fn)(warfare.base + 0x5a5eb0))(s->unit, 0);
    ((fd_modified_fn)(warfare.base + 0x59f470))(s->unit);
    ((fd_modified_fn)(warfare.base + 0x5aa740))(s->unit);
    warfare.previous_valid[i] = 0; /* a teleport is not a velocity sample */
    return warfare_outside_carrier(tls, warfare.player[i].carrier, unit);
}

static int warfare_samples(unsigned char *tls, float dt, warfare_sample out[WARFARE_PLAYERS]) {
    unsigned char *players = *(unsigned char **)(tls + 0x30);
    unsigned char *users = *(unsigned char **)(tls + 0x118);
    memset(out, 0, sizeof(warfare_sample) * WARFARE_PLAYERS);
    int count = 0;
    for (int i = 0; i < WARFARE_PLAYERS; i++) {
        warfare_sample *s = &out[i]; s->local_user = -1; s->unit = s->parent = WARFARE_NONE;
        unsigned char *player = fd_slot(players, (unsigned)i, 0x4b0, WARFARE_PLAYERS);
        if (!player) { warfare.previous_valid[i] = 0; continue; }
        s->present = 1; s->participant_salt = *(uint16_t *)player;
        s->unit = *(uint32_t *)(player + 0x28); s->team = (signed char)player[0xad];
        unsigned char *unit = warfare_biped(tls, s->unit);
        if (!unit || s->team < 0 || s->team > 1) { warfare.previous_valid[i] = 0; continue; }
        s->local_user = users ? *(int *)(users + 0x34 + i * 4) : -1;
        if (s->local_user < 0 || s->local_user > 1) s->local_user = -1;
        s->parent = *(uint32_t *)(unit + 0x14);
        unsigned char *parent = fd_object(tls, s->parent);
        s->parent_is_transport = warfare_transport(parent);
        s->carrier_clear = !s->parent_is_transport && warfare_outside_carrier(tls, warfare.player[i].carrier, unit);
        /* CU4 0x669f27 clears contact-valid bit3;0x669f75 clears old support.
         * 0x66a437/474 set a static surface;0x66a4d7 sets dynamic object
         * support and clears that surface.0x66a523 normalizes the contact
         * normal and0x66a5b5 sets bit3 only for a valid physics contact.
         * The gate is independent of the AI pathfinding sector at+9e8. */
        s->support_world = warfare_world_support(*(unsigned *)(unit + 0x9d8), *(int *)(unit + 0x9e4),
            *(int16_t *)(unit + 0x9de), *(int *)(unit + 0x9ec), *(uint32_t *)(unit + 0x9f0), (float *)(unit + 0xa04));
        /* Attached units store relative coordinates. A carrier's origin is
         * sufficient for display/exit tracking; only detached units receive
         * velocity commands. No guessed raw-velocity unit conversion. */
        const float *at = (const float *)((parent ? parent : unit) + 0x44);
        for (int k = 0; k < 3; k++) s->position[k] = at[k] * WARFARE_METRES_PER_WU;
        const float *forward = (const float *)(unit + 0x50);
        s->facing[0] = forward[0]; s->facing[1] = forward[1];
        s->valid = 1;
        if (warfare.previous_valid[i] && warfare.previous[i].unit == s->unit
            && warfare.previous[i].parent == s->parent && dt > 0) {
            for (int k = 0; k < 3; k++) s->velocity[k] = (s->position[k] - warfare.previous[i].position[k]) / dt;
            s->velocity_valid = 1;
        }
        warfare.previous[i] = *s; warfare.previous_valid[i] = 1; count++;
    }
    return count;
}

#include "warfare_inventory.h"
static warfare_inventory warfare_kits[WARFARE_PLAYERS];

static void warfare_apply(unsigned char *tls, const warfare_sample all[WARFARE_PLAYERS], int i,
                          const warfare_output *out) {
    const warfare_sample *s = &all[i];
    if ((!out->flags && !warfare_kits[i].restoring) || !warfare_finite_sample(s)) return;
    int hs_player = warfare_hs_rank(all, i);
    if (hs_player < 0) return;
    unsigned char *unit = fd_object(tls, s->unit);
    if (!unit) return;
    char line[256];
    if (out->flags & WF_EXIT) {
        /* The Pelican has no functioning player exit/ejection animation:
         * live CU4 tests of both normal exit and ejection left it attached.
         * objects_detach calls the unit's seat-aware detach callback before
         * the generic hierarchy removal. The compiler and engine resolve
         * the actual parent; no raw parent/seat fields are overwritten. */
        if (s->parent_is_transport)
            snprintf(line, sizeof line, "(objects_detach (unit_get_vehicle (player_get %d)) (player_get %d))", hs_player, hs_player);
        else
            snprintf(line, sizeof line, "(unit_exit_vehicle (player_get %d) 1)", hs_player);
        warfare_hs(line);
    }
    if (out->flags & WF_CLEAR_CABIN) {
        int cleared = warfare_clear_cabin(tls, i, s);
        fireteam_log("warfare: player %d carrier %08x cabin clearance %s", i,
                     warfare.player[i].carrier, cleared ? "verified" : "rejected");
    }
    if (out->flags & WF_UNPROTECT) {
        snprintf(line, sizeof line, "(unit_falling_damage_disable (player_get %d) false)", hs_player); warfare_hs(line);
    }
    if (out->flags & (WF_HOME | WF_WARMUP)) {
        const char *flag = out->flags & WF_WARMUP ? "pwr_warmup"
            : s->team == 0 ? "pwr_red_home" : "pwr_blue_home";
        snprintf(line, sizeof line, "(object_teleport (player_get %d) %s)", hs_player, flag); warfare_hs(line);
    }
    if (out->flags & WF_PROTECT) {
        snprintf(line, sizeof line, "(unit_falling_damage_disable (player_get %d) true)", hs_player); warfare_hs(line);
    }
    warfare_inventory_apply(&warfare_kits[i], warfare.instance, s->unit, hs_player, out->flags, warfare_hs);
    if (out->flags & WF_BOARD) {
        /* Prefer the four stock player-capable positions. Live l04/l01 A/B
         * removed the first-person geometry clipping for the first rider.
         * The six newly enabled passenger seats remain available afterward. */
        static const char *seat[10] = {"pelican_p_l04", "pelican_p_l05", "pelican_p_r04", "pelican_p_r05", "pelican_p_l01",
                                      "pelican_p_l02", "pelican_p_l03", "pelican_p_r01", "pelican_p_r02", "pelican_p_r03"};
        int rank = warfare.seat[i];
        if (rank < 0 || rank >= 10) return;
        if (s->parent != WARFARE_NONE && !s->parent_is_transport) {
            snprintf(line, sizeof line, "(unit_exit_vehicle (player_get %d) 1)", hs_player); warfare_hs(line);
        }
        snprintf(line, sizeof line, "(unit_enter_vehicle_immediate (player_get %d) pwr_pelican_%s \"%s\")",
                 hs_player, s->team == 0 ? "red" : "blue", seat[rank]);
        warfare_hs(line);
    }
    if ((out->flags & WF_VELOCITY) && s->parent == WARFARE_NONE) {
        float local[3];
        if (!warfare_velocity_frame((const float *)(unit + 0x50), (const float *)(unit + 0x5c), out->velocity, local)) return;
        snprintf(line, sizeof line, "(object_set_velocity (player_get %d) %.5f %.5f %.5f)",
                 hs_player, local[0] / WARFARE_METRES_PER_WU, local[1] / WARFARE_METRES_PER_WU,
                 local[2] / WARFARE_METRES_PER_WU);
        warfare_hs(line);
    }
}

static void warfare_carriers(unsigned char *tls) {
    warfare.carrier[0] = warfare.carrier[1] = WARFARE_NONE;
    float nearest[2] = {1.0e30f, 1.0e30f};
    unsigned char *table = *(unsigned char **)(tls + 0x20);
    unsigned count = table ? *(unsigned *)(table + 0x44) : 0;
    if (count > 4096) return;
    for (unsigned i = 0; i < count; i++) {
        unsigned char *entry = fd_slot(table, i, 0x18, 4096);
        if (!entry || *(uint16_t *)(entry + 4) != 1) continue;
        uint32_t handle = (uint32_t)*(uint16_t *)entry << 16 | i;
        unsigned char *object = fd_object(tls, handle);
        if (warfare_transport(object)) {
            const float *p = (const float *)(object + 0x44);
            float metres[3]; for (int k = 0; k < 3; k++) metres[k] = p[k] * WARFARE_METRES_PER_WU;
            if (!warfare_inside(metres, warfare_scenario_min, warfare_scenario_max)) continue;
            float red = warfare_route_distance2(0, metres), blue = warfare_route_distance2(1, metres);
            int team = red < blue ? 0 : 1;
            float distance = team ? blue : red;
            if (distance < nearest[team]) { nearest[team] = distance; warfare.carrier[team] = handle; }
        }
    }
}

static void warfare_flight(unsigned char *tls, const warfare_snapshot *snapshot, int tick) {
    int phase = snapshot->globals[0], age = snapshot->globals[1], rate = snapshot->rate;
    if (!snapshot->host) return;
    if (phase == 1 && warfare.last_phase != 1) {
        warfare_hs("(object_create_anew pwr_pelican_red)");
        warfare_hs("(object_create_anew pwr_pelican_blue)");
        warfare_hs("(object_teleport pwr_pelican_red pwr_red_flight_start)");
        warfare_hs("(object_teleport pwr_pelican_blue pwr_blue_flight_start)");
        warfare_hs("(object_cannot_take_damage pwr_pelican_red)");
        warfare_hs("(object_cannot_take_damage pwr_pelican_blue)");
        warfare.transport_created = 1;
        fireteam_log("warfare: insertion started; native physics transports requested");
    }
    if (!warfare.transport_created || tick % (rate / 10 ? rate / 10 : 1)) return;
    if (phase == 1) {
        warfare_carriers(tls);
        for (int team = 0; team < 2; team++) {
            unsigned char *object = fd_object(tls, warfare.carrier[team]);
            if (!object || !warfare_transport(object)) continue;
            const float *p = (const float *)(object + 0x44);
            float metres[3], world[3], local[3];
            for (int k = 0; k < 3; k++) metres[k] = p[k] * WARFARE_METRES_PER_WU;
            if (!warfare_flight_velocity(team, (float)age / (float)rate, warfare.insertion_seconds, metres, world)
                || !warfare_velocity_frame((const float *)(object + 0x50), (const float *)(object + 0x5c), world, local)) continue;
            char line[192];
            snprintf(line, sizeof line, "(object_set_velocity pwr_pelican_%s %.5f %.5f %.5f)", team ? "blue" : "red",
                     local[0] / WARFARE_METRES_PER_WU, local[1] / WARFARE_METRES_PER_WU, local[2] / WARFARE_METRES_PER_WU);
            warfare_hs(line);
        }
    } else {
        warfare_hs("(object_set_velocity pwr_pelican_red 0 0 0)");
        warfare_hs("(object_set_velocity pwr_pelican_blue 0 0 0)");
        if (phase == 2 && (float)age < WARFARE_TRANSPORT_CLEANUP_SECONDS * (float)rate) return;
        warfare_carriers(tls);
        int occupied = 0;
        for (int i = 0; i < WARFARE_PLAYERS; i++)
            if (snapshot->sample[i].valid && (snapshot->sample[i].parent_is_transport
                || (warfare.player[i].carrier != WARFARE_NONE && !snapshot->sample[i].carrier_clear))) occupied = 1;
        if (!occupied) {
            warfare_hs("(object_destroy pwr_pelican_red)"); warfare_hs("(object_destroy pwr_pelican_blue)");
            warfare.transport_created = 0;
        }
    }
}

#include "warfare_map.h"

static void warfare_publish(const warfare_snapshot *s) {
    AcquireSRWLockExclusive(&warfare_snapshot_lock); warfare_published = *s;
    ReleaseSRWLockExclusive(&warfare_snapshot_lock);
    if (!s->ready) warfare_tactical_clear();
}

static void warfare_tick_inner(void) {
    if (!warfare.supported) return;
    unsigned char *tls = sim_tls_block(), *g = tls ? *(unsigned char **)(tls + 0x60) : NULL;
    unsigned char *engine = tls ? *(unsigned char **)(tls + 0x38) : NULL;
    warfare_snapshot s; memset(&s, 0, sizeof s); s.status = 1; s.layout = WARFARE_LAYOUT_REVISION;
    if (!g || g[0] || !g[1] || g[0x10] != 3 || !engine || *(int *)(engine + 0x846c) != 2) {
        warfare.instance = 0; warfare.last_phase = -1;
        if (warfare_enabled) warfare_publish(&s);
        return;
    }
    uint64_t instance = *(uint64_t *)(g + 0x18);
    LONG recheck = InterlockedExchange(&warfare_recheck, 0);
    if (instance != warfare.instance) {
        warfare.instance = instance; warfare.disabled = 0; warfare.last_tick = -1; warfare.last_phase = -1;
        warfare.hs_failures = 0;
        warfare.duration_valid = 0; warfare.insertion_seconds = WARFARE_INSERTION_SECONDS;
        warfare.transport_created = 0; warfare.was_client = g[0x11] == 4;
        warfare.map_ok = warfare_enabled ? warfare_map() : 0;
        memset(warfare.previous_valid, 0, sizeof warfare.previous_valid);
        memset(warfare.admitted, 0, sizeof warfare.admitted);
        for (int i = 0; i < WARFARE_PLAYERS; i++) warfare.seat[i] = -1;
        for (int i = 0; i < WARFARE_PLAYERS; i++) warfare_player_reset(&warfare.player[i]);
    } else if (recheck) {
        /* Re-arming the same map must not lose an outstanding cleanup or
         * recreate transports. Only the map identity needs another check. */
        warfare.map_ok = warfare_enabled ? warfare_map() : 0;
    }
    if (!warfare.map_ok) { s.status = -2; if (warfare_enabled) warfare_publish(&s); return; }
    unsigned char *time = *(unsigned char **)(tls + 0x98);
    if (!time) return;
    int tick = *(int *)(time + 0x0c), rate = *(int16_t *)(time + 6);
    if (tick == warfare.last_tick || rate < 10 || rate > 240) return;
    int tick_delta = warfare.last_tick >= 0 ? tick - warfare.last_tick : 1;
    warfare.last_tick = tick;
    /* Catch up short gaps in simulation updates, while rejecting velocity
     * observations that straddle a discontinuity or a pause. */
    float dt = fminf(0.1f, (float)(tick_delta > 0 ? tick_delta : 1) / (float)rate);
    if (tick_delta != 1) memset(warfare.previous_valid, 0, sizeof warfare.previous_valid);
    s.instance = instance; s.rate = rate; s.tick = tick; s.sampled_ms = GetTickCount64(); s.host = g[0x11] != 4;
    memcpy(s.globals, engine + 0x234, sizeof s.globals);
    /* Slot3 is the configured deployment duration before combat; the VM
     * resets it to zero on phase2 and then uses it for combat elapsed time. */
    if (s.globals[2] == WARFARE_MAGIC && s.globals[0] <= 1 && s.globals[3] > 0 && s.globals[3] <= 32767) {
        warfare.insertion_seconds = (float)s.globals[3]; warfare.duration_valid = 1;
    }
    s.insertion_seconds = (int)warfare.insertion_seconds;
    warfare_samples(tls, dt, s.sample);
    if (!s.host) warfare.was_client = 1;
    if (warfare.was_client && s.host) warfare.disabled = 1; /* explicit rehost required */
    int valid_mode = s.globals[2] == WARFARE_MAGIC && s.globals[0] >= 0 && s.globals[0] <= 3
        && s.globals[1] >= 0 && s.globals[1] <= 32767 && (warfare.duration_valid || s.globals[0] >= 2);
    if (!warfare_enabled || warfare.disabled || !valid_mode) {
        for (int i = 0; i < WARFARE_PLAYERS; i++) {
            warfare_output out; warfare_stop(&warfare.player[i], &s.sample[i], &out);
            warfare_apply(tls, s.sample, i, &out);
        }
        if (warfare.transport_created) {
            warfare_snapshot stopping = s; stopping.globals[0] = 3; stopping.globals[1] = 0;
            warfare_flight(tls, &stopping, tick);
        }
        s.status = warfare.disabled ? -4 : valid_mode ? 0 : -3;
        warfare_publish(&s); return;
    }
    s.ready = 1; s.status = 2;
    if (s.globals[0] == 0) warfare_lock_roster(s.sample, warfare.admitted, warfare.seat);
    warfare_flight(tls, &s, tick);
    LONG action = InterlockedExchange(&warfare_action, 0);
    warfare_controls controls[2];
    AcquireSRWLockExclusive(&warfare_controls_lock);
    memcpy(controls, warfare_local_controls, sizeof controls);
    warfare_local_controls[0].jump = warfare_local_controls[1].jump = 0;
    ReleaseSRWLockExclusive(&warfare_controls_lock);
    uint64_t controls_read_ms = GetTickCount64();
    for (int i = 0; i < WARFARE_PLAYERS; i++) {
        warfare_output out;
        int before = warfare.player[i].stage;
        /* A new participant after roster lock waits at a home base. A new
         * unit for an existing participant still uses that participant's
         * reserved seat; disconnected slot reuse cannot steal it. */
        int player_phase = s.globals[0];
        if (player_phase == 1 && (!s.sample[i].participant_salt || warfare.admitted[i] != s.sample[i].participant_salt))
            player_phase = 2;
        warfare_sample *sample = &s.sample[i];
        int jump = action && sample->local_user == 0;
        if (sample->valid && sample->local_user >= 0 && sample->local_user < 2) {
            const warfare_controls *c = &controls[sample->local_user];
            if (c->instance == instance && c->unit == sample->unit && controls_read_ms - c->updated_ms <= 350) {
                sample->forward_input = c->forward;
                sample->right_input = c->right;
                sample->brake = c->brake;
                jump |= c->jump;
                if (isfinite(c->yaw)) {
                    float radians = -c->yaw * 0.01745329252f; /* UE +Y is map -Y */
                    sample->facing[0] = cosf(radians); sample->facing[1] = sinf(radians);
                }
            }
        }
        warfare_step(&warfare.player[i], sample, player_phase, (float)s.globals[1] / (float)rate,
                     warfare.insertion_seconds, dt, jump, &out);
        warfare_apply(tls, s.sample, i, &out);
        s.stage[i] = warfare.player[i].stage;
        s.steering[i] = warfare.player[i].steering;
        s.braking[i] = warfare.player[i].braking;
        if (before != s.stage[i]) fireteam_log("warfare: player %d local %d state %d -> %d support=%d clear=%d velocity_valid=%d parent=%08x", i,
            s.sample[i].local_user, before, s.stage[i], s.sample[i].support_world, s.sample[i].carrier_clear,
            s.sample[i].velocity_valid, s.sample[i].parent);
    }
    warfare_tactical_tick(tls, &s);
    warfare.last_phase = s.globals[0]; warfare_publish(&s);
}

static void warfare_tick(void) {
    if (!warfare_enabled && !warfare.instance) return;
    __try { warfare_tick_inner(); }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        if (!warfare.disabled) fireteam_log("warfare: invalid simulation state (%08lx); disabled for this world", GetExceptionCode());
        warfare.disabled = 1;
        warfare_tactical_clear();
    }
}

/* Existing native end-check already recognizes reasons 0/2. Only this
 * validated map/variant may keep waiting or playing when a team is empty;
 * score victory, the script's own ending and invalid-team reason13 remain. */
static int warfare_keep_playing(void) {
    if (!warfare_enabled || !warfare.supported || !warfare.map_ok || warfare.disabled) return 0;
    __try {
        unsigned char *g = sim_game_globals(), *e = sim_tls_slot(0x38);
        return g && g[1] && !g[0] && g[0x10] == 3 && *(uint64_t *)(g + 0x18) == warfare.instance
            && e && *(int *)(e + 0x846c) == 2 && *(int *)(e + 0x234 + 2 * 4) == WARFARE_MAGIC
            && *(int *)(e + 0x234) >= 0 && *(int *)(e + 0x234) < 3;
    } __except (EXCEPTION_EXECUTE_HANDLER) { return 0; }
}

__declspec(dllexport) int mjolnir_warfare_open(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    char path[MAX_PATH], header[64], map[64], revision[64], protocol[64], expected_revision[64], expected_protocol[64];
    snprintf(path, sizeof path, "%swarfare_config.txt", dir);
    FILE *file = fopen(path, "r");
    int valid = file && fgets(header, sizeof header, file) && fgets(map, sizeof map, file)
        && fgets(revision, sizeof revision, file) && fgets(protocol, sizeof protocol, file);
    if (file) fclose(file);
    if (valid) {
        header[strcspn(header, "\r\n")] = 0; map[strcspn(map, "\r\n")] = 0;
        revision[strcspn(revision, "\r\n")] = 0; protocol[strcspn(protocol, "\r\n")] = 0;
    }
    snprintf(expected_revision, sizeof expected_revision, "layout %d", WARFARE_LAYOUT_REVISION);
    snprintf(expected_protocol, sizeof expected_protocol, "protocol %d", WARFARE_MAGIC);
    if (!valid || strcmp(header, "warfare-config 2") || strcmp(map, "map PWR")
        || strcmp(revision, expected_revision) || strcmp(protocol, expected_protocol)
        || !warfare_build() || !install_main_tick(warfare.base) || !find_hs_evaluate("warfare disabled")) {
        fireteam_log("warfare: open refused (config/build/hook/evaluator)");
        InterlockedExchange(&warfare_enabled, 0); warfare_tactical_clear(); return 0;
    }
    hook_end_check_once(warfare.base);
    if (!InterlockedExchange(&warfare_enabled, 1)) InterlockedExchange(&warfare_recheck, 1);
    fireteam_log("warfare: armed for PWR and matching Megalo protocol only");
    return 0;
}
__declspec(dllexport) int mjolnir_warfare_close(void *L) {
    (void)L; InterlockedExchange(&warfare_enabled, 0); InterlockedExchange(&warfare_action, 0);
    AcquireSRWLockExclusive(&warfare_controls_lock);
    memset(warfare_local_controls, 0, sizeof warfare_local_controls);
    ReleaseSRWLockExclusive(&warfare_controls_lock);
    warfare_snapshot empty; memset(&empty, 0, sizeof empty); warfare_publish(&empty); return 0;
}
__declspec(dllexport) int mjolnir_warfare_action(void *L) {
    (void)L; if (warfare_enabled) InterlockedExchange(&warfare_action, 1); return 0;
}

/* One local controller's intent. The simulation owns the flight law and all
 * velocity changes. A message cannot target a remote player or a recycled unit. */
__declspec(dllexport) int mjolnir_warfare_controls(void *L) {
    lc_frame f;
    if (!warfare_enabled || !lc_begin(&f, L)) return 0;
    long long user = lc_take_integer(&f, 1, -1);
    long long unit = lc_take_integer(&f, 1, -1);
    double forward = lc_take_number(&f, 1, NAN), right = lc_take_number(&f, 1, NAN);
    int brake = lc_take_bool(&f, 1);
    double yaw = lc_take_number(&f, 1, NAN);
    int jump = lc_take_bool(&f, 1);
    lc_end(&f);
    if (user < 0 || user > 1 || unit <= 0 || unit >= WARFARE_NONE
        || !isfinite(forward) || !isfinite(right) || fabs(forward) > 1.001 || fabs(right) > 1.001) return 0;
    uint64_t instance = 0;
    AcquireSRWLockShared(&warfare_snapshot_lock);
    if (warfare_published.ready && warfare_published.globals[0] != 3) {
        for (int i=0; i<WARFARE_PLAYERS; i++) {
            const warfare_sample *p = &warfare_published.sample[i];
            int stage = warfare_published.stage[i];
            if (p->valid && p->local_user == (int)user && p->unit == (uint32_t)unit
                && (stage == WF_SEATED || stage == WF_EXITING || stage == WF_FALLING || stage == WF_CANOPY)) {
                instance = warfare_published.instance;
                break;
            }
        }
    }
    ReleaseSRWLockShared(&warfare_snapshot_lock);
    if (!instance) return 0;
    AcquireSRWLockExclusive(&warfare_controls_lock);
    warfare_controls *c = &warfare_local_controls[(int)user];
    uint64_t now = GetTickCount64();
    int pending = c->unit == (uint32_t)unit && c->instance == instance && now-c->updated_ms <= 350 && c->jump;
    c->instance = instance; c->updated_ms = now; c->unit = (uint32_t)unit;
    c->forward = (float)forward; c->right = (float)right;
    c->yaw = isfinite(yaw) ? (float)remainder(yaw, 360.0) : (float)NAN;
    c->brake = brake; c->jump = jump || pending;
    ReleaseSRWLockExclusive(&warfare_controls_lock);
    return 0;
}
/* The thin M overlay pumps only while open. Its file IO stays off the
 * simulation tick and is independent of the existing 2 Hz HUD snapshot. */
__declspec(dllexport) int mjolnir_warfare_map_pump(void *L) {
    (void)L; if (!dir[0]) find_dir();
    warfare_tactical_pump(dir); return 0;
}
__declspec(dllexport) int mjolnir_warfare_pump(void *L) {
    (void)L; if (!dir[0]) find_dir();
    warfare_snapshot s;
    AcquireSRWLockShared(&warfare_snapshot_lock); s = warfare_published;
    ReleaseSRWLockShared(&warfare_snapshot_lock);
    char path[MAX_PATH]; snprintf(path, sizeof path, "%swarfare_state.txt", dir);
    FILE *file = fopen(path, "w"); if (!file) return 0;
    fprintf(file, "warfare-state 2\nready %d\nstatus %d\nhost %d\ninstance %llu\ntick %d\nsampled_ms %llu\nlayout %d\ninsertion_seconds %d\nphase %d\nelapsed_ticks %d\nrate %d\nconnected %d\nscore %d %d\nowner %d %d %d\nglobals",
            s.ready, s.status, s.host, (unsigned long long)s.instance, s.tick, (unsigned long long)s.sampled_ms, s.layout,
            s.insertion_seconds, s.globals[0], s.globals[1], s.rate,
            s.globals[4], s.globals[7], s.globals[8], s.globals[9], s.globals[10], s.globals[11]);
    for (int n = 0; n < 12; n++) fprintf(file, " %d", s.globals[n]);
    fputc('\n', file);
    for (int i = 0; i < WARFARE_PLAYERS; i++) {
        const warfare_sample *p = &s.sample[i]; if (!p->valid) continue;
        fprintf(file, "player %d %d %d %d %.3f %.3f %.3f %u\n", i, p->team, s.stage[i], p->local_user,
                p->position[0], p->position[1], p->position[2], p->unit);
        fprintf(file, "ordinal %d %d\n", i, warfare_hs_rank(s.sample, i));
        if (p->local_user >= 0 && p->velocity_valid && warfare_finite_sample(p)
            && (s.stage[i] == WF_FALLING || s.stage[i] == WF_CANOPY)) {
            fprintf(file, "flight %d %.3f %.3f %.3f %d %.3f\n", i,
                    p->velocity[0], p->velocity[1], p->velocity[2], s.braking[i], s.steering[i]);
            float clearance = p->position[2] - warfare_terrain(p->position[0], p->position[1], 0);
            fprintf(file, "clearance %d %.2f\n", i, fmaxf(0, clearance));
        }
    }
    fclose(file); return 0;
}
