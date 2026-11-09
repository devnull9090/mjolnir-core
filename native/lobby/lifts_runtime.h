/* Halo 2's lifts on the simulation thread (#235). Included after Lobby's
 * simulation helpers and forge_doors_runtime.h (fd_slot).
 *
 * MJOLNIRLevelLoader's lifts.lua writes the running map's phantoms to
 * native\lifts.txt (lifts_core.h has the form) whenever the set changes, and
 * calls mjolnir_sim_lifts, which reads it on the game thread. Once per
 * simulation tick, lifts_tick then pushes each of this game's own players
 * who is inside a phantom, through object_set_velocity: a player's motion
 * belongs to the game that controls it (two PCs, 2026-10-25: a push the host
 * sends a joiner's unit does nothing, and the joiner's own push reaches the
 * host), so every peer, client or host, pushes only its local players, on
 * foot and not in Forge's editor.
 *
 * What it reads (docs/re/lift_push.md): the players table (TLS+0x30, 0x4b0
 * a player, the unit handle at +0x28), the player-to-local-user map
 * (TLS+0x118, +0x34 + 4p: the local user, -1 for a player of another
 * machine), the object table (TLS+0x20), the unit's parent (+0x14),
 * position (+0x44), forward (+0x50), up (+0x5c) and velocity (+0x68, wu/s),
 * and the tick and its rate (TLS+0x98: +0x0c, +6). Every read is checked
 * against the table's own header first, and a fault turns lifts off until
 * the next set arrives. */
#include "lifts_core.h"

#define LIFT_PLAYERS 16
static SRWLOCK lifts_lock = SRWLOCK_INIT;
static lift_set lifts_staged, lifts_live, lifts_scratch;
static volatile LONG lifts_pending;
static int lifts_on, lifts_last_tick = -1;
static unsigned long long lifts_instance;
static LARGE_INTEGER lifts_frequency;
/* Per player slot: the salt and phantom of the last push, what it meant
   (lift_push's `last`), and what the log last said about the slot. */
static struct {
    unsigned short salt;
    int lift, logged, has_last;
    float last[3];
    unsigned pushes;
    double worst_us, total_us;
} lift_player[LIFT_PLAYERS];

/* object_set_velocity's own body (sim 0x663b90 on CU4, Steam and Xbox alike):
   object, then forward, left and up in the object's frame (lift_unit_frame).
   The script function's evaluator only reads its arguments and calls it, so
   calling it takes the same path without compiling a line a push. Found by
   its bytes, the branch and global displacements left out; when a build no
   longer matches, the push goes through the script evaluator as before. */
typedef void(__fastcall *lift_set_velocity_t)(uint32_t object, float forward, float left, float up);
static lift_set_velocity_t lift_set_velocity;
static const unsigned char LIFT_SET_VELOCITY[] = {
    0x83, 0xF9, 0xFF, 0x0F, 0x84, 0,    0,    0,    0,    0x48, 0x8B, 0xC4, 0x53, 0x48, 0x81, 0xEC, 0x90,
    0x00, 0x00, 0x00, 0x8B, 0x15, 0,    0,    0,    0,    0xC5, 0xF8, 0x29, 0x78, 0xD8, 0xC5, 0x78, 0x29,
    0x50, 0xA8, 0xC5, 0x78, 0x29, 0x58, 0x98, 0x48, 0x89, 0x78, 0x08, 0xC5, 0xF8, 0x29, 0x70, 0xE8};
static const unsigned char LIFT_SET_VELOCITY_MASK[] = {1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1,
                                                       1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1,
                                                       1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1};

static void lifts_find_setter(void) {
    static int looked;
    if (looked) return;
    looked = 1;
    int hits = 0;
    unsigned char *sim = (unsigned char *)GetModuleHandleA("HaloSimulation_tag_release.dll");
    lift_set_velocity = sim ? (lift_set_velocity_t)find_in_module(sim, LIFT_SET_VELOCITY, LIFT_SET_VELOCITY_MASK,
                                                                  sizeof LIFT_SET_VELOCITY, 1, &hits)
                            : NULL;
    fireteam_log("lifts: object_set_velocity's body %s (%d matches)%s", lift_set_velocity ? "found" : "not found", hits,
                 lift_set_velocity ? "" : "; pushes go through the script evaluator");
}

static void lifts_forget(int i) {
    memset(&lift_player[i], 0, sizeof lift_player[i]);
    lift_player[i].lift = lift_player[i].logged = -1;
}

static void lifts_forget_all(void) {
    for (int i = 0; i < LIFT_PLAYERS; i++) lifts_forget(i);
}

/* An object's datum when `handle` names a live biped (type 0) of the table,
   on a host or a fireteam client alike (lift_entry_is_biped). */
static unsigned char *lift_biped(unsigned char *tls, uint32_t handle) {
    if (handle == UINT32_MAX || !(handle >> 16)) return NULL;
    unsigned char *slot = fd_slot(*(unsigned char **)(tls + 0x20), handle & 0xffff, 0x18, 4096);
    if (!slot || !lift_entry_is_biped(slot, handle)) return NULL;
    return *(unsigned char **)(slot + 0x10);
}

/* Whether player `i` is Forge's flying editor (a biped too: the monitor),
   which no lift pushes. Asked through the call the doors use, only on the
   builds they know (fd_ready); elsewhere an editor can be pushed. */
static int lift_editing(unsigned char *tls, int i) {
    unsigned char *engine = *(unsigned char **)(tls + 0x38);
    if (!engine || *(int *)(engine + 0x846c) != 1 || !fd.checked || !fd.supported || !fd.base) return 0;
    return ((fd_edit_fn)(fd.base + 0x2fe810))((unsigned)i) != 0;
}

static int lift_vector_ok(const float *v, float limit) {
    for (int k = 0; k < 3; k++)
        if (!isfinite(v[k]) || fabsf(v[k]) > limit) return 0;
    return 1;
}

static void lifts_push_player(unsigned char *tls, unsigned char *users, int i, float dt) {
    unsigned char *player = fd_slot(*(unsigned char **)(tls + 0x30), (unsigned)i, 0x4b0, LIFT_PLAYERS);
    unsigned short salt = player ? *(uint16_t *)player : 0;
    int user = salt ? *(int32_t *)(users + 0x34 + (size_t)i * 4) : -1;
    unsigned char *unit = user >= 0 && user < 4 ? lift_biped(tls, *(uint32_t *)(player + 0x28)) : NULL;
    /* A seated biped's position is its seat's, relative to the vehicle. */
    if (unit && (*(uint32_t *)(unit + 0x14) != UINT32_MAX || lift_editing(tls, i))) unit = NULL;
    const float *p = unit ? (const float *)(unit + 0x44) : NULL, *forward = unit ? (const float *)(unit + 0x50) : NULL,
                *up = unit ? (const float *)(unit + 0x5c) : NULL, *velocity = unit ? (const float *)(unit + 0x68) : NULL;
    if (!unit || !lift_vector_ok(p, LIFT_FAR) || !lift_vector_ok(forward, 1.5f) || !lift_vector_ok(up, 1.5f)
        || !lift_vector_ok(velocity, 1000.0f)) {
        if (lift_player[i].logged >= 0) fireteam_log("lifts: player %d has no biped on foot here any more", i);
        lifts_forget(i);
        return;
    }
    if (lift_player[i].salt != salt) {
        lifts_forget(i);
        lift_player[i].salt = salt;
    }
    float v[3] = {velocity[0], velocity[1], velocity[2]};
    int which = -1, negates = 0;
    for (int k = 0; k < lifts_live.count; k++) {
        const lift_phantom *lift = &lifts_live.lifts[k];
        if (!lift_near(lift, p) || !lift_inside(&lifts_live, lift, p)) continue;
        int carry = which < 0 && lift_player[i].has_last && lift_player[i].lift == k;
        lift_push(lift, p, v, dt, carry ? lift_player[i].last : NULL);
        if (which < 0) which = k;
        negates |= lift->negates_gravity;
    }
    if (which != lift_player[i].logged) {
        if (which >= 0) {
            fireteam_log("lifts: player %d in phantom %d (%s) at (%.2f, %.2f, %.2f)", i, which,
                         lifts_live.lifts[which].name, p[0], p[1], p[2]);
        } else {
            unsigned pushes = lift_player[i].pushes;
            fireteam_log("lifts: player %d left the lift at (%.2f, %.2f, %.2f) after %u pushes (%.0f us mean, %.0f us worst)",
                         i, p[0], p[1], p[2], pushes, pushes ? lift_player[i].total_us / pushes : 0.0,
                         lift_player[i].worst_us);
            lift_player[i].pushes = 0;
            lift_player[i].total_us = lift_player[i].worst_us = 0.0;
        }
        lift_player[i].logged = which;
    }
    lift_player[i].lift = which;
    lift_player[i].has_last = which >= 0;
    if (which < 0) return;
    memcpy(lift_player[i].last, v, sizeof v);
    lift_sent(v, negates, dt);
    float local[3];
    lift_unit_frame(v, forward, up, local);
    if (!lift_vector_ok(local, 1000.0f)) return;
    LARGE_INTEGER start, end;
    QueryPerformanceCounter(&start);
    if (lift_set_velocity) {
        lift_set_velocity(*(uint32_t *)(player + 0x28), local[0], local[1], local[2]);
    } else {
        if (!find_hs_evaluate("lifts do not push")) return;
        char line[SCRIPT_LINE];
        snprintf(line, sizeof line, "(object_set_velocity (player_get %d) %.4f %.4f %.4f)", i, local[0], local[1], local[2]);
        int value = -1, type = 0;
        hs_evaluate(0, "mjolnir_lobby", line, 1, 0, &value, &type);
    }
    QueryPerformanceCounter(&end);
    double us = (double)(end.QuadPart - start.QuadPart) * 1e6 / (double)lifts_frequency.QuadPart;
    lift_player[i].pushes++;
    lift_player[i].total_us += us;
    if (us > lift_player[i].worst_us) lift_player[i].worst_us = us;
}

static void lifts_run(void) {
    unsigned char *tls = sim_tls_block();
    unsigned char *g = tls ? *(unsigned char **)(tls + 0x60) : NULL;
    if (!g || g[0] || !g[1]) return;
    unsigned long long instance = *(unsigned long long *)(g + 0x18);
    if (instance != lifts_instance) {
        lifts_instance = instance;
        lifts_last_tick = -1;
        lifts_forget_all();
    }
    unsigned char *time = *(unsigned char **)(tls + 0x98), *users = *(unsigned char **)(tls + 0x118);
    if (!time || !users) return;
    int tick = *(int *)(time + 0x0c), rate = *(int16_t *)(time + 6);
    if (tick == lifts_last_tick || rate < 10 || rate > 240) return;
    /* Never for a paused redraw. A main tick can run two simulation ticks,
       so a push covers the ticks since the last one (four at most: after a
       pause or a hitch it is a fresh start, not a catch-up). */
    int ticks = lifts_last_tick < 0 || tick < lifts_last_tick || tick - lifts_last_tick > 4 ? 1 : tick - lifts_last_tick;
    lifts_last_tick = tick;
    for (int i = 0; i < LIFT_PLAYERS; i++) lifts_push_player(tls, users, i, (float)ticks / (float)rate);
}

static void lifts_tick(void) {
    if (lifts_pending) {
        AcquireSRWLockExclusive(&lifts_lock);
        lifts_live.count = lifts_staged.count;
        lifts_live.plane_count = lifts_staged.plane_count;
        memcpy(lifts_live.lifts, lifts_staged.lifts, sizeof lifts_live.lifts[0] * (size_t)lifts_staged.count);
        memcpy(lifts_live.plane, lifts_staged.plane, sizeof lifts_live.plane[0] * (size_t)lifts_staged.plane_count);
        InterlockedExchange(&lifts_pending, 0);
        ReleaseSRWLockExclusive(&lifts_lock);
        lifts_forget_all();
        lifts_on = lifts_live.count > 0;
        if (!lifts_frequency.QuadPart) QueryPerformanceFrequency(&lifts_frequency);
    }
    if (!lifts_on) return;
    __try {
        lifts_run();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        lifts_on = 0;
        fireteam_log("lifts: faulted (%08lx); off until the next set", GetExceptionCode());
    }
}

/* native\lifts.txt, read on the caller's thread; the next tick takes it. A
   file it cannot read leaves the set in use as it is. */
__declspec(dllexport) int mjolnir_sim_lifts(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    unsigned char *sim = (unsigned char *)GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!sim || !install_main_tick(sim)) return 0;
    char path[MAX_PATH];
    if (snprintf(path, sizeof path, "%slifts.txt", dir) >= (int)sizeof path) return 0;
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    static char text[1 << 20];
    size_t n = fread(text, 1, sizeof text - 1, f);
    int whole = feof(f) && !ferror(f);
    fclose(f);
    text[n] = 0;
    int bad = whole && strlen(text) == n ? lift_parse(text, &lifts_scratch) : -1;
    if (bad) {
        fireteam_log("lifts: %s is unreadable at line %d; the set in use is kept", path, bad);
        return 0;
    }
    /* The one scan of the module, here at the map's start rather than in a tick. */
    if (lifts_scratch.count) lifts_find_setter();
    AcquireSRWLockExclusive(&lifts_lock);
    lifts_staged.count = lifts_scratch.count;
    lifts_staged.plane_count = lifts_scratch.plane_count;
    memcpy(lifts_staged.lifts, lifts_scratch.lifts, sizeof lifts_staged.lifts[0] * (size_t)lifts_scratch.count);
    memcpy(lifts_staged.plane, lifts_scratch.plane, sizeof lifts_staged.plane[0] * (size_t)lifts_scratch.plane_count);
    InterlockedExchange(&lifts_pending, 1);
    ReleaseSRWLockExclusive(&lifts_lock);
    fireteam_log("lifts: %d phantom(s), %d plane(s) for the next tick", lifts_scratch.count, lifts_scratch.plane_count);
    return 0;
}
