/* PWR insertion/descent controller. Engine-independent; all lengths metres,
 * velocities metres/second, time seconds. Megalo exclusively owns match rules.
 * This controller acts only on a player's owning simulation peer. */
#ifndef MJOLNIR_WARFARE_CORE_H
#define MJOLNIR_WARFARE_CORE_H
#include <math.h>
#include <stdint.h>
#include <string.h>
#include "warfare_layout.h"
#include "warfare_flight_terrain.h"

#define WARFARE_PLAYERS 16
#define WARFARE_NONE UINT32_MAX
enum warfare_stage { WF_GROUND, WF_BOARDING, WF_SEATED, WF_FALLING, WF_CANOPY,
                     WF_LANDED, WF_FAILED, WF_EXITING,
                     /* Respawned at home while the team's Pelican cannot be
                      * boarded: shielded and unarmed, the HUD showing a
                      * teammate, until it parks or the player moves. */
                     WF_WAITING };
enum warfare_command {
    WF_WARMUP = 1, WF_HOME = 2, WF_BOARD = 4, WF_EXIT = 8,
    WF_PROTECT = 16, WF_UNPROTECT = 32, WF_VELOCITY = 64, WF_CLEAR_CABIN = 128,
    WF_LOWER_WEAPON = 256, WF_RAISE_WEAPON = 512,
    /* Wake the biped's physics at the start of a fall: a body detached from
     * a stationary (parked) Pelican sleeps and hung at 550 m for seconds. */
    WF_WAKE = 1024,
    /* Kill the unit: it met the ground falling too fast (no parachute, or
     * one pulled too late). The descent is protected from falling damage, so
     * the death is this explicit one, decided on the host at first contact. */
    WF_SPLAT = 2048,
    /* A waiting body cannot take damage, and can again once it stops waiting. */
    WF_SHIELD = 4096, WF_UNSHIELD = 8192
};
typedef struct {
    uint32_t unit, parent;
    int valid, local_user, team, parent_is_transport, present;
    int velocity_valid, carrier_clear, support_world;
    /* Another machine's player, sampled on the host. The host steps it too:
     * vehicle seats, damage and inventory are the host's in a distributed
     * game, while the owning machine applies its biped's movement. */
    int remote;
    uint16_t participant_salt;
    float position[3], velocity[3], facing[2];
    float forward_input, right_input;
    int brake;
} warfare_sample;
typedef struct {
    uint32_t unit, carrier;
    /* saw_insertion: this life has used (or declined) a flight already. */
    int stage, protected_fall, last_phase, saw_insertion, weapon_lowered, sortie;
    /* next_sortie: after a failed combat boarding, the first sortie id to try again. */
    int next_sortie;
    float elapsed, retry, stable, departure_z;
    /* grounded: seconds of unbroken world contact in the descent, whatever
     * the velocity samples say (a joiner's are gappy and jitter). */
    float grounded;
    float carrier_velocity[2], air_velocity[3], steering;
    int air_initialized, braking, deploy_requested;
    /* fresh: this body spawned in combat and has not boarded or left home;
     * a waiting body measures movement from wait_origin, for at most
     * WARFARE_WAIT_MAX_SECONDS (waited). */
    int fresh;
    float wait_origin[2], waited;
    /* fall_sink: the body's own sink (m/s) at the last airborne sample with a
     * velocity, which is what decides a splat: the host never sees a
     * joiner's parachute pull, only the body slowing. */
    float fall_sink;
} warfare_player;
typedef struct { unsigned flags; float velocity[3]; } warfare_output;
/* One Pelican flight a player can ride: the insertion (phase 1) or a team's
 * reinforcement wave in combat. `active`: a transport for it exists (parked
 * or flying), so a seated rider stays seated. `boarding`: a rider may board
 * now (insertion, or a reinforcement Pelican parked at its flight start).
 * `flying`: it is on its route, `age` seconds into a `duration`-second flight. */
/* `id`: 0 for the insertion, k for reinforcement wave k (parked before it
 * leaves, then flying); a rider stays only on the sortie they boarded. */
typedef struct { int active, boarding, flying, id; float age, duration; } warfare_sortie;

/* Reinforcement wave k (k >= 1) leaves at combat second k * interval and flies
 * for `flight` seconds; between flights the team's Pelican waits, parked, for
 * riders. Derived from the replicated combat clock alone, so the host and every
 * client agree without another published value. `seconds` may carry a
 * fraction of a second measured locally since the clock last advanced. */
static void warfare_reinforcement_sortie(float seconds, int interval, float flight, warfare_sortie *out) {
    memset(out, 0, sizeof *out);
    if (interval <= 0 || !isfinite(seconds) || seconds < 0 || !isfinite(flight) || flight <= 0) return;
    int wave = (int)(seconds / (float)interval);
    float age = seconds - (float)wave * (float)interval;
    out->active = 1; out->duration = flight;
    if (wave >= 1 && age < flight) { out->flying = 1; out->age = age; out->id = wave; }
    else { out->boarding = 1; out->id = wave + 1; }
}

static int warfare_inside(const float p[3], const float low[3], const float high[3]) {
    for (int k = 0; k < 3; k++) if (!isfinite(p[k]) || p[k] < low[k] || p[k] > high[k]) return 0;
    return 1;
}

static float warfare_dot(const float a[3], const float b[3]) {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

/* CU4's biped contact updater distinguishes BSP/instanced-world support from
 * object support. A velocity pause alone is never evidence of ground. */
static int warfare_world_support(unsigned contact_flags, int surface, int bsp,
                                  int instance, uint32_t object, const float normal[3]) {
    if (!(contact_flags & 8u) || surface < 0 || bsp < 0 || bsp >= 16
        || instance < -1 || instance >= 65536 || object != WARFARE_NONE) return 0;
    for (int k = 0; k < 3; k++) if (!isfinite(normal[k])) return 0;
    float length2 = warfare_dot(normal, normal);
    return length2 > 0.9f && length2 < 1.1f && normal[2] >= 0.5f;
}

/* Runtime object bounds are world-space spheres (+30 center, +3c radius).
 * Use the complete bounds, not a guessed Pelican cabin dimension. */
static int warfare_carrier_clear(const float center[3], float radius,
                                  const float rider_center[3], float rider_radius) {
    if (!isfinite(radius) || radius < 0.5f || radius > 80.0f
        || !isfinite(rider_radius) || rider_radius < 0.1f || rider_radius > 5.0f) return 0;
    float delta[3];
    for (int k = 0; k < 3; k++) {
        if (!isfinite(center[k]) || !isfinite(rider_center[k])) return 0;
        delta[k] = rider_center[k] - center[k];
    }
    float separation = radius + rider_radius + 1.0f;
    return warfare_dot(delta, delta) > separation * separation;
}

static int warfare_ejection_point(const float center[3], float radius, const float forward[3],
                                   const float rider_center[3], float rider_radius,
                                   const float rider_origin[3], float out[3]) {
    if (!isfinite(radius) || radius < 0.5f || radius > 80.0f
        || !isfinite(rider_radius) || rider_radius < 0.1f || rider_radius > 5.0f) return 0;
    for (int k = 0; k < 3; k++)
        if (!isfinite(center[k]) || !isfinite(forward[k])
            || !isfinite(rider_center[k]) || !isfinite(rider_origin[k])) return 0;
    float horizontal = sqrtf(forward[0] * forward[0] + forward[1] * forward[1]);
    if (horizontal < 0.5f || horizontal > 1.05f) return 0;
    float desired_center[3] = {center[0], center[1], fmaxf(center[2], rider_center[2])};
    for (int k = 0; k < 2; k++) desired_center[k] -= forward[k] / horizontal * (radius + rider_radius + 3.0f);
    for (int k = 0; k < 3; k++) out[k] = desired_center[k] - (rider_center[k] - rider_origin[k]);
    return warfare_inside(out, warfare_play_min, warfare_play_max)
        && warfare_carrier_clear(center, radius, desired_center, rider_radius);
}

static void warfare_cross(const float a[3], const float b[3], float out[3]) {
    out[0] = a[1] * b[2] - a[2] * b[1];
    out[1] = a[2] * b[0] - a[0] * b[2];
    out[2] = a[0] * b[1] - a[1] * b[0];
}

/* Exact inverse of HS146's V = F*f + (U cross F)*left + U*vertical.
 * CU4 evaluator 0x663b90 reads F at object+0x50 and U at+0x5c.
 * Horizontal-only projection follows a pitched aircraft into the ground. */
static int warfare_velocity_frame(const float forward[3], const float up[3], const float world[3], float local[3]) {
    for (int k = 0; k < 3; k++)
        if (!isfinite(forward[k]) || !isfinite(up[k]) || !isfinite(world[k])) return 0;
    if (fabsf(warfare_dot(forward, forward) - 1) > 0.05f
        || fabsf(warfare_dot(up, up) - 1) > 0.05f || fabsf(warfare_dot(forward, up)) > 0.05f) return 0;
    float left[3], lu[3], fl[3];
    warfare_cross(up, forward, left); warfare_cross(left, up, lu); warfare_cross(forward, left, fl);
    float determinant = warfare_dot(forward, lu);
    if (!isfinite(determinant) || determinant < 0.8f) return 0;
    local[0] = warfare_dot(world, lu) / determinant;
    local[1] = warfare_dot(world, left) / determinant;
    local[2] = warfare_dot(world, fl) / determinant;
    return 1;
}

static void warfare_limit_speed(float velocity[3]) {
    float speed = sqrtf(warfare_dot(velocity, velocity));
    if (speed > WARFARE_TRANSPORT_MAX_SPEED)
        for (int k = 0; k < 3; k++) velocity[k] *= WARFARE_TRANSPORT_MAX_SPEED / speed;
}

static float warfare_forced_exit(float insertion_seconds) {
    return insertion_seconds * (WARFARE_FORCED_EXIT_SECONDS / WARFARE_INSERTION_SECONDS);
}

static void warfare_route_velocity(int team, float insertion_seconds, float out[3]) {
    for (int k = 0; k < 3; k++) out[k] = (warfare_routes[team].end[k] - warfare_routes[team].start[k]) / insertion_seconds;
    warfare_limit_speed(out);
}

/* Follow a world-space straight route with bounded correction. Short custom
 * test variants traverse part of the route safely, rather than overspeeding.
 * Phase 2 still stops the aircraft regardless of the configured duration. */
static int warfare_flight_velocity(int team, float age, float duration, const float position[3], float out[3]) {
    if (team < 0 || team > 1 || !isfinite(age) || age < 0 || !isfinite(duration) || duration <= 0 || duration > 32767
        || !warfare_inside(position, warfare_scenario_min, warfare_scenario_max)) return 0;
    float fraction = fminf(age / duration, 1.0f);
    warfare_route_velocity(team, duration, out);
    for (int k = 0; k < 3; k++) {
        float target = warfare_routes[team].start[k] + (warfare_routes[team].end[k] - warfare_routes[team].start[k]) * fraction;
        float correction = (target - position[k]) * WARFARE_ROUTE_CORRECTION_GAIN;
        out[k] += fmaxf(-WARFARE_ROUTE_CORRECTION_LIMIT, fminf(correction, WARFARE_ROUTE_CORRECTION_LIMIT));
    }
    warfare_limit_speed(out); return 1;
}

/* A parked reinforcement Pelican holds its flight start: bounded correction
 * toward it, so gravity and drift between velocity writes never build up. */
static int warfare_hold_velocity(int team, const float position[3], float out[3]) {
    if (team < 0 || team > 1 || !warfare_inside(position, warfare_scenario_min, warfare_scenario_max)) return 0;
    for (int k = 0; k < 3; k++) {
        float correction = (warfare_routes[team].start[k] - position[k]) * WARFARE_ROUTE_CORRECTION_GAIN;
        out[k] = fmaxf(-WARFARE_ROUTE_CORRECTION_LIMIT, fminf(correction, WARFARE_ROUTE_CORRECTION_LIMIT));
    }
    return 1;
}

/* Parked means at its flight start, give or take the hold's drift. */
#define WARFARE_PARKED_RADIUS 30.0f
static int warfare_at_flight_start(int team, const float position[3]) {
    if (team < 0 || team > 1) return 0;
    float d2 = 0;
    for (int k = 0; k < 3; k++) {
        if (!isfinite(position[k])) return 0;
        float d = position[k] - warfare_routes[team].start[k]; d2 += d * d;
    }
    return d2 <= WARFARE_PARKED_RADIUS * WARFARE_PARKED_RADIUS;
}

static float warfare_route_distance2(int team, const float position[3]) {
    float delta[3], from[3];
    for (int k = 0; k < 3; k++) {
        delta[k] = warfare_routes[team].end[k] - warfare_routes[team].start[k];
        from[k] = position[k] - warfare_routes[team].start[k];
    }
    float along = fmaxf(0, fminf(1, warfare_dot(delta, from) / warfare_dot(delta, delta)));
    for (int k = 0; k < 3; k++) from[k] -= along * delta[k];
    return warfare_dot(from, from);
}

/* Match every generated flight/home/warmup/capture flag in the baked scenario.
 * Matching routes alone cannot detect a stale base or capture layout. */
static unsigned warfare_layout_flag(const float position[3]) {
    unsigned found = 0;
    for (int marker = 0; marker < WARFARE_LAYOUT_MARKERS; marker++) {
        const float *wanted = warfare_layout_markers[marker];
        int match = 1;
        for (int k = 0; k < 3; k++) if (!isfinite(position[k]) || fabsf(position[k] - wanted[k]) > 0.05f) match = 0;
        if (match) found |= 1u << marker;
    }
    return found;
}

/* HaloScript player_get takes a rank in the valid player data array, not
 * an absolute slot. Dead players and unassigned teams still occupy ranks. */
static int warfare_hs_rank(const warfare_sample all[WARFARE_PLAYERS], int absolute) {
    if (absolute < 0 || absolute >= WARFARE_PLAYERS || !all[absolute].present) return -1;
    int rank = 0;
    for (int i = 0; i < absolute; i++) if (all[i].present) rank++;
    return rank;
}

/* Recomputed only in warmup. Once insertion begins neither departures nor
 * new spawns may renumber another participant's reserved transport seat. */
static void warfare_lock_roster(const warfare_sample all[WARFARE_PLAYERS], uint16_t salts[WARFARE_PLAYERS],
                                int seats[WARFARE_PLAYERS]) {
    int next[2] = {0, 0};
    for (int i = 0; i < WARFARE_PLAYERS; i++) {
        salts[i] = 0; seats[i] = -1;
        if (all[i].present && all[i].team >= 0 && all[i].team < 2) {
            salts[i] = all[i].participant_salt; seats[i] = next[all[i].team]++;
        }
    }
}

static int warfare_finite_sample(const warfare_sample *s) {
    if (!s || !s->valid || s->unit == WARFARE_NONE || (s->local_user < 0 && !s->remote) || s->local_user > 1
        || s->team < 0 || s->team > 1) return 0;
    for (int k = 0; k < 3; k++)
        if (!isfinite(s->position[k]) || !isfinite(s->velocity[k])
            || fabsf(s->position[k]) > WARFARE_POSITION_SANITY_M || fabsf(s->velocity[k]) > 500.0f) return 0;
    return 1;
}

static void warfare_player_reset(warfare_player *p) {
    memset(p, 0, sizeof *p); p->unit = p->carrier = WARFARE_NONE; p->last_phase = -1;
}

static void warfare_ready_weapon(warfare_player *p, warfare_output *o) {
    if (p->weapon_lowered) {
        o->flags |= WF_RAISE_WEAPON;
        p->weapon_lowered = 0;
    }
}

/* Waiting moves the body this far (metres, flat) to end: a step, not a
 * settling spawn (measured flat, so settling onto a floor is not a step). The cap ends a
 * wait the Pelican never ends, so no shield outlives its purpose. */
#define WARFARE_WAIT_MOVE 2.0f
#define WARFARE_WAIT_MAX_SECONDS 75.0f

/* Every way out of waiting but boarding: shield off, weapons back, an
 * ordinary base spawn from here (it never waits again this life). */
static void warfare_end_wait(warfare_player *p, warfare_output *o) {
    if (p->stage != WF_WAITING) return;
    o->flags |= WF_UNSHIELD;
    warfare_ready_weapon(p, o);
    p->stage = WF_GROUND; p->fresh = 0;
}

static void warfare_stop(warfare_player *p, const warfare_sample *s, warfare_output *o) {
    memset(o, 0, sizeof *o);
    if (s && s->valid && s->unit == p->unit && (s->local_user >= 0 || s->remote)) {
        if (p->stage == WF_WAITING) o->flags |= WF_UNSHIELD;
        warfare_ready_weapon(p, o);
        if (p->protected_fall) o->flags |= WF_UNPROTECT;
        if (p->stage == WF_BOARDING || p->stage == WF_SEATED || p->stage == WF_EXITING)
            o->flags |= WF_EXIT | WF_HOME;
    }
    warfare_player_reset(p);
}

static void warfare_fail(warfare_player *p, warfare_output *o) {
    warfare_ready_weapon(p, o);
    o->flags |= WF_EXIT | WF_HOME;
    if (p->protected_fall) o->flags |= WF_UNPROTECT;
    p->protected_fall = 0; p->stage = WF_FAILED;
}

static float warfare_clamp(float x, float a, float b) { return fmaxf(a, fminf(b, x)); }

/* The display interpolates the map surface; deployment uses the highest
 * source vertex in the cell at the biped and along its near-future track. */
static float warfare_terrain(float x, float y, int ceiling) {
    float u = warfare_clamp((x - WF_TERRAIN_X0) / WF_TERRAIN_STEP, 0, WF_TERRAIN_CELLS);
    float v = warfare_clamp((y - WF_TERRAIN_Y0) / WF_TERRAIN_STEP, 0, WF_TERRAIN_CELLS);
    int i = (int)u, j = (int)v;
    if (i == WF_TERRAIN_CELLS) --i;
    if (j == WF_TERRAIN_CELLS) --j;
    if (ceiling) return wf_terrain_ceiling[j][i];
    u -= i; v -= j;
    float south = (1-u)*wf_terrain_surface[j][i] + u*wf_terrain_surface[j][i+1];
    float north = (1-u)*wf_terrain_surface[j+1][i] + u*wf_terrain_surface[j+1][i+1];
    return (1-v)*south + v*north;
}

/* A player who joins once the insertion has begun rides it if less than this
 * fraction of it has gone; later they wait at home for the first wave. */
#define WARFARE_JOIN_INSERTION_FRACTION 0.5f

/* Unbroken world contact that lands a descent whatever its velocity samples. */
#define WARFARE_GROUNDED_SECONDS 1.0f

/* The parachute opens only when the player pulls it. Meeting the ground
 * faster than this (the descent controller's own sink, m/s) is fatal: freefall
 * runs to 55-63 m/s, a canopy settles at 10.5-18.5, so an open canopy always
 * lands and a pull in the last few metres does not. MJOLNIRHud's
 * warfare_voice.lua uses the same figure for "I tried to warn you". */
#define WARFARE_SPLAT_SINK 20.0f

static void warfare_air_motion(warfare_player *p, const warfare_sample *s, float dt, warfare_output *o) {
    int canopy = p->stage == WF_CANOPY;
    if (!p->air_initialized) {
        /* Only velocity observed on the moving carrier can transfer. A
         * stopped aircraft at the end of its run imparts no forward kick. */
        for (int k = 0; k < 2; k++) p->air_velocity[k] = p->carrier_velocity[k];
        p->air_velocity[2] = -6;
        p->air_initialized = 1;
    }
    float throttle = warfare_clamp(s->forward_input, -1, 1);
    float steer = warfare_clamp(s->right_input, -1, 1);
    p->steering += (steer - p->steering) * (1 - expf(-dt / 0.22f));
    p->braking = canopy && s->brake;
    float facing_x = s->facing[0], facing_y = s->facing[1];
    float norm = hypotf(facing_x, facing_y);
    if (!isfinite(norm) || norm < 0.05f) {
        facing_x = s->team ? -1.0f : 1.0f; facing_y = 0;
    } else {
        facing_x /= norm; facing_y /= norm;
    }
    /* Positive physical right is a clockwise turn in the map's +Y north
     * frame. Normalization preserves speed on a diagonal. */
    float lateral = p->steering * (canopy ? 1.0f : 0.85f);
    float along = canopy ? 1 : throttle;
    float direction_length = fmaxf(1, hypotf(along, lateral));
    float speed = canopy ? (p->braking ? 12.0f : 21.0f + 7.0f * throttle) : 17.0f;
    float target[2] = {(facing_x * along + facing_y * lateral) * speed / direction_length,
                       (facing_y * along - facing_x * lateral) * speed / direction_length};
    float response = 1 - expf(-dt / (canopy ? 0.72f : 1.30f));
    for (int k = 0; k < 2; k++) {
        p->air_velocity[k] += (target[k] - p->air_velocity[k]) * response;
        /* Keep an early outward-facing exit flyable at the map boundary.
         * Approach the edge gradually while preserving parallel steering. */
        float low = fminf(0, warfare_play_min[k] + 3 - s->position[k]);
        float high = fmaxf(0, warfare_play_max[k] - 3 - s->position[k]);
        p->air_velocity[k] = warfare_clamp(p->air_velocity[k], low, high);
    }
    if (canopy) {
        float sink = p->braking ? 10.5f : 16.0f + 2.5f * throttle;
        p->air_velocity[2] += (-sink - p->air_velocity[2]) * (1 - expf(-dt / 0.38f));
    } else {
        float terminal = 55.0f + 8.0f * throttle;
        p->air_velocity[2] += (-terminal - p->air_velocity[2]) * (1 - expf(-dt / 3.1f));
    }
    o->flags |= WF_VELOCITY;
    memcpy(o->velocity, p->air_velocity, sizeof o->velocity);
}

/* A reinforcement takes only a player still waiting where they spawned: on
 * foot within this distance of the team's home flag (spawns lie within 23 m).
 * Someone who has walked off or taken a vehicle is playing; never yank them. */
#define WARFARE_REINFORCE_HOME_RADIUS 40.0f
static int warfare_waiting_at_home(const warfare_sample *s) {
    if (s->parent != WARFARE_NONE || s->team < 0 || s->team > 1) return 0;
    const float *home = warfare_layout_markers[4 + s->team]; /* red_home, blue_home */
    return hypotf(s->position[0] - home[0], s->position[1] - home[1]) <= WARFARE_REINFORCE_HOME_RADIUS;
}

/* Called once per unique simulation tick. `sortie` is the flight this player
 * may ride now: the insertion in phase 1, the team's reinforcement wave in
 * combat (inactive when the map has none). A respawn or late join during
 * combat boards the next reinforcement; with none it is an ordinary base spawn.
 * Jump while parked leaves at once: the Pelican waits over the team's own
 * base, so that is the way to stay home (a vehicle, a walk) instead of waiting. */
static void warfare_step(warfare_player *p, const warfare_sample *s, int phase,
                         const warfare_sortie *sortie, float dt, int action, warfare_output *o) {
    memset(o, 0, sizeof *o);
    if (!warfare_finite_sample(s) || !sortie || !isfinite(dt) || dt <= 0 || dt > 0.1f
        || phase < 0 || phase > 3 || !isfinite(sortie->age) || sortie->age < 0
        || (sortie->active && (!isfinite(sortie->duration) || sortie->duration <= 0 || sortie->duration > 32767))) return;
    float forced_exit = sortie->active ? warfare_forced_exit(sortie->duration) : 0;
    int flight_over = sortie->flying && sortie->age >= forced_exit;
    if (p->unit != s->unit) {
        warfare_player_reset(p); p->unit = s->unit;
        if (phase == 0) o->flags |= WF_WARMUP;
        if (phase == 2) p->fresh = 1; /* a respawn, or a join, in combat */
    }
    /* Only the flight a rider boarded keeps them aboard. */
    int on_foot = p->stage == WF_GROUND || p->stage == WF_WAITING;
    int mine = sortie->active && (on_foot || p->sortie == sortie->id);
    if (phase == 3) { warfare_stop(p, s, o); return; }
    if (phase == 0) {
        if (p->last_phase > 0) {
            if (p->stage == WF_WAITING) o->flags |= WF_UNSHIELD;
            warfare_ready_weapon(p, o);
            if (p->protected_fall) o->flags |= WF_UNPROTECT;
            o->flags |= WF_EXIT | WF_WARMUP;
            p->protected_fall = 0; p->saw_insertion = 0; p->stage = WF_GROUND;
        }
        p->last_phase = phase; return;
    }
    int started_seated = p->stage == WF_SEATED;
    if (action && (p->stage == WF_EXITING || p->stage == WF_FALLING)) p->deploy_requested = 1;
    /* A client can lose the race with its host's boarding: a player already
     * seen aboard their team's transport for this sortie rides it. */
    if (on_foot && phase == 2 && sortie->active && s->parent_is_transport && !p->saw_insertion) {
        if (p->stage == WF_WAITING) o->flags |= WF_UNSHIELD;
        p->saw_insertion = 1; p->stage = WF_SEATED; p->sortie = sortie->id; p->fresh = 0;
        p->carrier = s->parent; p->elapsed = 0; p->protected_fall = 1; o->flags |= WF_PROTECT;
    }
    if (sortie->boarding && !p->saw_insertion && on_foot && sortie->id >= p->next_sortie
        && (sortie->id == 0 || warfare_waiting_at_home(s))) {
        /* A waiting body keeps its weapon lowered for the ride: it comes
         * back on landing, as for every rider. */
        if (p->stage == WF_WAITING) o->flags |= WF_UNSHIELD;
        p->saw_insertion = 1; p->stage = WF_BOARDING; p->elapsed = 0; p->retry = 0; p->sortie = sortie->id;
        p->fresh = 0; p->protected_fall = 1; o->flags |= WF_PROTECT;
    }
    /* No world support asked: a base floor is a placed structure, not the
     * map's surface, and a respawn there never reports it (PC 1, 2026-11-24).
     * Movement is measured flat, so a body settling onto it does not count. */
    if (phase == 2 && p->stage == WF_GROUND && p->fresh && sortie->active && s->parent == WARFARE_NONE
        && warfare_waiting_at_home(s)) {
        /* Respawned at home and the Pelican cannot be boarded now (it waits
         * out of sight until shortly before its wave, or this player is
         * barred until a later one): wait shielded and unarmed, so a body
         * left while its player watches a teammate is neither a target nor
         * an invulnerable turret. */
        p->stage = WF_WAITING; p->waited = 0;
        p->wait_origin[0] = s->position[0]; p->wait_origin[1] = s->position[1];
        p->weapon_lowered = 1; o->flags |= WF_SHIELD | WF_LOWER_WEAPON;
    }
    /* Walked off or drove away first: this life plays from home, and a later
     * walk back to base is not a wait. */
    if (p->stage == WF_GROUND && p->fresh && (s->parent != WARFARE_NONE || !warfare_waiting_at_home(s))) p->fresh = 0;
    if (p->stage == WF_WAITING) {
        p->last_phase = phase;
        p->waited += dt;
        if (s->parent != WARFARE_NONE || p->waited > WARFARE_WAIT_MAX_SECONDS
            || hypotf(s->position[0] - p->wait_origin[0], s->position[1] - p->wait_origin[1]) > WARFARE_WAIT_MOVE)
            warfare_end_wait(p, o); /* in a vehicle, timed out, or walking: play from home */
        return;
    }
    p->last_phase = phase;
    p->elapsed += dt;
    if (p->stage == WF_BOARDING) {
        if (s->parent != WARFARE_NONE && s->parent_is_transport) {
            p->carrier = s->parent; p->stage = WF_SEATED; p->elapsed = 0;
        } else if (!sortie->boarding || !mine || p->elapsed > 5.0f || flight_over) {
            if (phase == 2) {
                /* On foot at home already: no teleport; try the next wave. */
                warfare_ready_weapon(p, o);
                if (p->protected_fall) o->flags |= WF_UNPROTECT;
                p->protected_fall = 0; p->stage = WF_GROUND; p->saw_insertion = 0;
                p->next_sortie = p->sortie + 1;
                return;
            }
            warfare_fail(p, o);
            return;
        } else {
            p->retry -= dt;
            if (p->retry <= 0) { o->flags |= WF_BOARD; p->retry = 0.5f; }
        }
    }
    if (p->stage == WF_SEATED) {
        if (s->parent_is_transport && s->velocity_valid) {
            float speed = hypotf(s->velocity[0], s->velocity[1]);
            float fraction = speed > 0 ? fminf(0.6f, 16.0f / speed) : 0;
            for (int k = 0; k < 2; k++) p->carrier_velocity[k] = sortie->flying ? s->velocity[k] * fraction : 0;
        }
        if (s->parent == WARFARE_NONE) {
            p->stage = WF_EXITING; p->elapsed = 0; p->retry = 0;
        } else if (!mine || flight_over || (action && started_seated)) {
            /* A parked jump uses the same verified exit as a flying one (host
             * detach, cabin clearance, canopy): a separate detach-and-teleport
             * home left a remote rider hanging at 550 m (three copies, 2026-11-22). */
            p->stage = WF_EXITING; p->elapsed = 0; p->retry = 0;
        }
    }
    if (p->stage == WF_EXITING) {
        if (s->parent == WARFARE_NONE && s->carrier_clear) {
            p->stage = WF_FALLING; p->elapsed = 0; p->departure_z = s->position[2]; p->fall_sink = 0;
            o->flags |= WF_WAKE;
            /* Clear of a Pelican still out of sight beyond the play area (a
             * jump while it waits there): home, by the biped's own machine. */
            if (!warfare_inside(s->position, warfare_play_min, warfare_play_max)) o->flags |= WF_HOME;
            p->air_initialized = 0;
            if (!p->weapon_lowered) {
                p->weapon_lowered = 1;
                o->flags |= WF_LOWER_WEAPON;
            }
            o->flags |= WF_PROTECT;
        } else if (p->elapsed > 3.0f) { warfare_fail(p, o); return; }
        else {
            p->retry -= dt;
            if (p->retry <= 0) {
                o->flags |= s->parent == WARFARE_NONE ? WF_CLEAR_CABIN : WF_EXIT;
                p->retry = 0.25f;
            }
        }
    }
    if (p->stage != WF_FALLING && p->stage != WF_CANOPY) return;
    if (s->parent != WARFARE_NONE) {
        p->stable = 0;
        if (s->parent_is_transport) {
            p->carrier = s->parent; p->stage = WF_EXITING; p->elapsed = 0; p->retry = 0.25f;
            o->flags |= WF_EXIT;
        } else p->elapsed = 0; /* riding another vehicle is not a timed descent */
        /* A vehicle attachment is not a terrain contact. Keep protection,
         * never apply canopy velocity to a parented unit, and resume the
         * support check when the player exits the other vehicle. */
        return;
    }
    if (p->elapsed > WARFARE_DESCENT_TIMEOUT_SECONDS || !warfare_inside(s->position, warfare_play_min, warfare_play_max)) {
        warfare_fail(p, o); return;
    }
    if (p->stage == WF_FALLING && p->elapsed >= 0.25f && p->deploy_requested) {
        p->stage = WF_CANOPY;
        p->deploy_requested = 0;
    }
    /* Real world support plus continuous sampled motion is required. This
     * rejects an airborne pause, stale samples, and a detached Pelican deck. */
    /* A missing velocity sample (a joiner's simulation updates come in
     * bursts) neither counts nor breaks the run; a second of unbroken world
     * contact lands anyone: a joiner stayed under canopy on the ground two
     * minutes until the descent timeout sent them home (2026-11-23). */
    int grounded = s->support_world && s->carrier_clear && p->departure_z - s->position[2] > 3.0f;
    /* The first real contact decides it, from the speed the body itself was
     * last seen falling at. Not the controller's sink: on the host a joiner's
     * descent is never told of their pull (only the cabin jump is relayed),
     * so its controller stays in freefall while the body hangs under canopy;
     * deciding from it killed every joiner on landing (review, 2026-11-24). */
    if (!s->support_world && s->velocity_valid && isfinite(s->velocity[2])) p->fall_sink = fmaxf(0, -s->velocity[2]);
    if (grounded && p->fall_sink > WARFARE_SPLAT_SINK) {
        warfare_ready_weapon(p, o);
        o->flags |= WF_SPLAT | WF_UNPROTECT; p->protected_fall = 0; p->stage = WF_LANDED; return;
    }
    if (grounded) {
        p->grounded += dt;
        if (s->velocity_valid) {
            if (fabsf(s->velocity[2]) < 0.6f) p->stable += dt; else p->stable = 0;
        }
    } else p->stable = p->grounded = 0;
    if (p->stable >= 0.3f || p->grounded >= WARFARE_GROUNDED_SECONDS) {
        warfare_ready_weapon(p, o);
        o->flags |= WF_UNPROTECT; p->protected_fall = 0; p->stage = WF_LANDED; return;
    }
    /* A real contact always wins over the velocity controller, including
     * during the short stable-support window and on slopes. */
    if (!s->support_world) warfare_air_motion(p, s, dt, o);
}

/* Covenant waves (docs/pelican_warfare_waves.md section 4). The map's bake
 * gives every place to hold squads `wave_koth_hill_<order>_<k>` whose first
 * task holds it (docs/bots.md "Places to hold"); a site's chosen spot is
 * marker spawn order site + 3 * candidate. The host places a wave on the
 * combat clock: the first at WARFARE_WAVE_FIRST seconds, then one every
 * WARFARE_WAVE_INTERVAL, while fewer than WARFARE_WAVE_CAP Covenant live
 * (the Havok proxy budget is unmeasured: docs/pwr_ai_feasibility.md 3). */
#define WARFARE_SITES 3
#define WARFARE_WAVE_FIRST 45
#define WARFARE_WAVE_INTERVAL 90
/* Covenant alive at once: three full Spirits. A Spirit's troop seats (16 on
 * tuning_fork) set a place's wave squads at bake time (level.rs, waves
 * "transport"). The simulation keeps 96 actors; 31 lived and 16 rode, jumped
 * and walked off on PWR (2026-11-23). */
#define WARFARE_WAVE_CAP 48
/* The most squads a fork (one Spirit's load) may have, forks a tier and
 * tiers a map (looked for up to these). */
#define WARFARE_WAVE_SQUADS 32
#define WARFARE_WAVE_FORKS 4
#define WARFARE_WAVE_TIERS 8
/* Waves get harder: this many waves to a tier. */
#define WARFARE_WAVES_PER_TIER 3

/* The tier wave `n` (1-based) takes: 1-3 the first, 4-6 the second, ...,
 * and the last tier the map has from then on. */
static int warfare_wave_tier(int n, int tiers) {
    if (tiers <= 0) return 0;
    int t = n > 0 ? (n - 1) / WARFARE_WAVES_PER_TIER : 0;
    return t < tiers ? t : tiers - 1;
}

/* Which wave the combat clock is in: 0 before the first, then 1, 2, ... */
static int warfare_wave_index(int combat_seconds) {
    if (combat_seconds < WARFARE_WAVE_FIRST) return 0;
    return 1 + (combat_seconds - WARFARE_WAVE_FIRST) / WARFARE_WAVE_INTERVAL;
}

/* A wave falls due when the clock crosses a wave time between two looks,
 * so a skipped second or a late tick still fires it, once. */
static int warfare_wave_due(int last_seconds, int combat_seconds) {
    if (combat_seconds < 0) return 0;
    return warfare_wave_index(combat_seconds) > warfare_wave_index(last_seconds < 0 ? -1 : last_seconds);
}

/* A site's published value (slots 9-11; blam-megalo warfare.rs SiteState):
 * owner in the low two bits (0 neutral, 1 red, 2 blue, 3 Covenant), the
 * chosen candidate in steps of 1024, and WARFARE_SITE_COVENANT_PRESENT above
 * those while Covenant stand in the zone. Decode here, never `/ 1024`. */
#define WARFARE_OWNER_COVENANT 3
#define WARFARE_SITE_CANDIDATE_STRIDE 1024
#define WARFARE_SITE_COVENANT_PRESENT 8192
static int warfare_site_owner(int packed) {
    return packed > 0 ? (packed % WARFARE_SITE_CANDIDATE_STRIDE) & 3 : 0;
}
static int warfare_site_candidate(int packed) {
    return packed > 0 ? (packed % WARFARE_SITE_COVENANT_PRESENT) / WARFARE_SITE_CANDIDATE_STRIDE : 0;
}
static int warfare_site_covenant_present(int packed) {
    return packed >= WARFARE_SITE_COVENANT_PRESENT;
}

/* Who a wave would rather press: a team's site, then a neutral one, then
 * one the Covenant already hold. */
static int warfare_wave_rank(int owner) {
    return owner == 1 || owner == 2 ? 2 : owner == WARFARE_OWNER_COVENANT ? 0 : 1;
}

/* The site a wave goes to: of those with a squad free, the one with the
 * fewest Covenant alive; on a tie the higher warfare_wave_rank, so the waves
 * press whoever holds ground and reinforce their own sites last; then the
 * one after the last target, so equal sites take turns. -1: none. */
static int warfare_wave_target(const int live[WARFARE_SITES], const int free_squads[WARFARE_SITES],
                               const int owner[WARFARE_SITES], int last_target) {
    int best = -1;
    for (int n = 1; n <= WARFARE_SITES; n++) {
        int site = ((last_target < 0 ? -1 : last_target) + n + WARFARE_SITES) % WARFARE_SITES;
        if (free_squads[site] <= 0) continue;
        if (best < 0 || live[site] < live[best]
            || (live[site] == live[best] && warfare_wave_rank(owner[site]) > warfare_wave_rank(owner[best])))
            best = site;
    }
    return best;
}

/* How many squads a wave places: all of the target's free ones, within the
 * cap (each squad is one AI). */
/* Whether two points are within `r` of each other in plan (a Spirit its pilot
 * flew back to where it came in). */
static int warfare_within_xy(const float a[3], const float b[3], float r) {
    float dx = a[0] - b[0], dy = a[1] - b[1];
    return dx * dx + dy * dy < r * r;
}

static int warfare_wave_size(int live_total, int free_squads) {
    int room = WARFARE_WAVE_CAP - live_total;
    if (room <= 0 || free_squads <= 0) return 0;
    return room < free_squads ? room : free_squads;
}

/* Transports out of sight (levels/warfare/pwr/plan_transport_routes.py). A
 * path is the points a transport flies through after its start. These are
 * pure: the runtime turns their velocity into object_set_velocity. */
#define WARFARE_PATH_ARRIVE 15.0f       /* m: close enough to a point on the way */
#define WARFARE_PATH_LAND 1.5f          /* m: close enough to the last point */
#define WARFARE_SPIRIT_SPEED 40.0f      /* m/s cruising */
#define WARFARE_SPIRIT_FINAL_SPEED 12.0f
/* Over its spot a Spirit opens, and its troops jump this long after (so
 * not through the doors); it leaves once they are out, or after
 * WARFARE_SPIRIT_UNLOAD_SECONDS more at most. */
#define WARFARE_SPIRIT_DOOR_SECONDS 2.0f
#define WARFARE_SPIRIT_UNLOAD_SECONDS 12.0f
#define WARFARE_PELICAN_CLIMB_SPEED 40.0f
/* A reinforcement Pelican reaches its flight start this long before its wave
 * leaves, the time its riders have to board. */
#define WARFARE_PELICAN_BOARDING_LEAD 15.0f

static float warfare_length(const float a[3], const float b[3]) {
    float d[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]};
    return sqrtf(warfare_dot(d, d));
}

/* Velocity toward the path's point `*leg` (advanced on arrival), at most
 * `speed`, slowing into the last point. Returns 1 once at the last point.
 * `reverse` flies the points the other way, ending at `start`. */
static int warfare_path_velocity(const warfare_path *path, int reverse, const float start[3], int *leg,
                                 const float position[3], float speed, float out[3]) {
    out[0] = out[1] = out[2] = 0;
    if (!path || path->count <= 0 || path->count > WARFARE_ROUTE_POINTS || !leg || !isfinite(speed) || speed <= 0) return 0;
    int last = reverse ? path->count : path->count - 1; /* reverse ends at start, one past the points */
    for (;;) {
        if (*leg < 0) *leg = 0;
        if (*leg > last) *leg = last;
        const float *target;
        if (!reverse) target = path->point[*leg];
        else target = *leg >= path->count ? start : path->point[path->count - 1 - *leg];
        float d = warfare_length(position, target);
        int final = *leg == last;
        if (!final && d <= WARFARE_PATH_ARRIVE) { (*leg)++; continue; }
        if (final && d <= WARFARE_PATH_LAND) return 1;
        float want = final ? fminf(speed, fmaxf(1.0f, d * 0.6f)) : speed;
        for (int k = 0; k < 3; k++) out[k] = (target[k] - position[k]) / (d > 1e-3f ? d : 1) * want;
        return 0;
    }
}

/* A path's flying time at `speed` from `from`, the points in order. */
static float warfare_path_seconds(const warfare_path *path, const float from[3], float speed) {
    if (!path || path->count <= 0 || speed <= 0) return 0;
    float total = warfare_length(from, path->point[0]);
    for (int i = 1; i < path->count; i++) total += warfare_length(path->point[i - 1], path->point[i]);
    return total / speed;
}

/* A reinforcement Pelican out of sight and on its way in: anywhere in the
 * column over its staging point (the path's first point, any height), on the
 * path's legs, or at its flight start, within `radius` m. Every machine
 * judges boarding by this alone, from the layout. */
static int warfare_on_pelican_path(int team, const float position[3], float radius) {
    if (team < 0 || team > 1) return 0;
    const warfare_path *path = &warfare_pelican_paths[team];
    if (path->count <= 0) return warfare_at_flight_start(team, position);
    float dx = position[0] - path->point[0][0], dy = position[1] - path->point[0][1];
    if (dx * dx + dy * dy <= radius * radius) return 1;
    for (int i = 1; i < path->count; i++) {
        const float *a = path->point[i - 1], *b = path->point[i];
        float ab[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]}, ap[3] = {position[0] - a[0], position[1] - a[1], position[2] - a[2]};
        float t = fmaxf(0, fminf(1, warfare_dot(ab, ap) / fmaxf(warfare_dot(ab, ab), 1e-6f)));
        float closest[3] = {a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t};
        if (warfare_length(position, closest) <= radius) return 1;
    }
    return warfare_at_flight_start(team, position);
}
#endif
