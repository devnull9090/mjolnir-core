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
                     WF_LANDED, WF_FAILED, WF_EXITING };
enum warfare_command {
    WF_WARMUP = 1, WF_HOME = 2, WF_BOARD = 4, WF_EXIT = 8,
    WF_PROTECT = 16, WF_UNPROTECT = 32, WF_VELOCITY = 64, WF_CLEAR_CABIN = 128,
    WF_LOWER_WEAPON = 256, WF_RAISE_WEAPON = 512
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
    int stage, protected_fall, last_phase, saw_insertion, weapon_lowered;
    float elapsed, retry, stable, departure_z;
    float carrier_velocity[2], air_velocity[3], steering;
    int air_initialized, braking, deploy_requested;
} warfare_player;
typedef struct { unsigned flags; float velocity[3]; } warfare_output;

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

static void warfare_stop(warfare_player *p, const warfare_sample *s, warfare_output *o) {
    memset(o, 0, sizeof *o);
    if (s && s->valid && s->unit == p->unit && (s->local_user >= 0 || s->remote)) {
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

static int warfare_need_canopy(const warfare_player *p, const warfare_sample *s) {
    float roof = warfare_terrain(s->position[0], s->position[1], 1);
    float ahead = warfare_terrain(s->position[0] + p->air_velocity[0],
                                  s->position[1] + p->air_velocity[1], 1);
    float sink = fmaxf(0, -p->air_velocity[2]);
    return s->position[2] - fmaxf(roof, ahead) <= fmaxf(38, 18 + sink * 1.05f);
}

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

/* Called once per unique simulation tick. A late join or respawn during
 * active play is an ordinary base spawn, never a second insertion. */
static void warfare_step(warfare_player *p, const warfare_sample *s, int phase,
                         float phase_seconds, float insertion_seconds, float dt, int action, warfare_output *o) {
    memset(o, 0, sizeof *o);
    if (!warfare_finite_sample(s) || !isfinite(dt) || dt <= 0 || dt > 0.1f
        || !isfinite(phase_seconds) || phase_seconds < 0 || phase < 0 || phase > 3
        || !isfinite(insertion_seconds) || insertion_seconds <= 0 || insertion_seconds > 32767) return;
    float forced_exit = warfare_forced_exit(insertion_seconds);
    if (p->unit != s->unit) {
        warfare_player_reset(p); p->unit = s->unit;
        if (phase == 0) o->flags |= WF_WARMUP;
    }
    if (phase == 3) { warfare_stop(p, s, o); return; }
    if (phase == 0) {
        if (p->last_phase > 0) {
            warfare_ready_weapon(p, o);
            if (p->protected_fall) o->flags |= WF_UNPROTECT;
            o->flags |= WF_EXIT | WF_WARMUP;
            p->protected_fall = 0; p->saw_insertion = 0; p->stage = WF_GROUND;
        }
        p->last_phase = phase; return;
    }
    int started_seated = p->stage == WF_SEATED;
    if (action && (p->stage == WF_EXITING || p->stage == WF_FALLING)) p->deploy_requested = 1;
    if (phase == 1 && !p->saw_insertion && p->stage == WF_GROUND) {
        p->saw_insertion = 1; p->stage = WF_BOARDING; p->elapsed = 0; p->retry = 0;
        p->protected_fall = 1; o->flags |= WF_PROTECT;
    }
    p->last_phase = phase;
    p->elapsed += dt;
    if (p->stage == WF_BOARDING) {
        if (s->parent != WARFARE_NONE && s->parent_is_transport) {
            p->carrier = s->parent; p->stage = WF_SEATED; p->elapsed = 0;
        } else if (phase != 1 || p->elapsed > 5.0f || phase_seconds >= forced_exit) {
            warfare_fail(p, o); return;
        } else {
            p->retry -= dt;
            if (p->retry <= 0) { o->flags |= WF_BOARD; p->retry = 0.5f; }
        }
    }
    if (p->stage == WF_SEATED) {
        if (s->parent_is_transport && s->velocity_valid) {
            float speed = hypotf(s->velocity[0], s->velocity[1]);
            float fraction = speed > 0 ? fminf(0.6f, 16.0f / speed) : 0;
            for (int k = 0; k < 2; k++) p->carrier_velocity[k] = phase == 1 ? s->velocity[k] * fraction : 0;
        }
        if (s->parent == WARFARE_NONE) {
            p->stage = WF_EXITING; p->elapsed = 0; p->retry = 0;
        } else if (phase == 2 || phase_seconds >= forced_exit
                   || (action && started_seated)) {
            p->stage = WF_EXITING; p->elapsed = 0; p->retry = 0;
        }
    }
    if (p->stage == WF_EXITING) {
        if (s->parent == WARFARE_NONE && s->carrier_clear) {
            p->stage = WF_FALLING; p->elapsed = 0; p->departure_z = s->position[2];
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
    if (p->stage == WF_FALLING && p->elapsed >= 0.25f
        && (p->deploy_requested || warfare_need_canopy(p, s))) {
        p->stage = WF_CANOPY;
        p->deploy_requested = 0;
    }
    /* Real world support plus continuous sampled motion is required. This
     * rejects an airborne pause, stale samples, and a detached Pelican deck. */
    if (s->support_world && s->carrier_clear && s->velocity_valid
        && p->departure_z - s->position[2] > 3.0f && fabsf(s->velocity[2]) < 0.6f)
        p->stable += dt;
    else p->stable = 0;
    if (p->stable >= 0.3f) {
        warfare_ready_weapon(p, o);
        o->flags |= WF_UNPROTECT; p->protected_fall = 0; p->stage = WF_LANDED; return;
    }
    /* A real contact always wins over the velocity controller, including
     * during the short stable-support window and on slopes. */
    if (!s->support_world) warfare_air_motion(p, s, dt, o);
}
#endif
