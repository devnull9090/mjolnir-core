/* Halo 2's lifts, jump pads and vents (#235): the phantom set, its text form
 * and the push, portable and data-only (no game process needed; tested by
 * test_lifts.c). Everything here is in the simulation's own frame and units:
 * world units (1 wu = 304.8 cm), seconds, z up, and the sim's y is Unreal's
 * -Y. MJOLNIRLevelLoader's lifts.lua converts each phantom from the level
 * file's Unreal centimetres before it writes the set; lifts_runtime.h reads
 * it and pushes on the simulation thread.
 *
 * A phantom is a shape (convex planes, or a pill: a segment and a radius),
 * a bounding sphere, the marker it pushes from (origin) and along (forward),
 * and three acceleration / top speed pairs, each 0 0 when unused:
 * "direction" along forward, "axis" towards the line through origin along
 * forward, and "center" towards origin. "negates gravity" holds the player
 * up while inside.
 *
 * The text form, one record per line, single spaces, nothing after `end`:
 *
 *     mjolnir-lifts 1
 *     lift <name> <negates 0|1> <origin x y z> <forward x y z> <bounds x y z r>
 *          <direction acc max> <axis acc max> <center acc max> planes <n>
 *     plane <a> <b> <c> <d>           (n of them: inside where ax+by+cz+d <= 0)
 *     lift <name> ... pill <ax ay az> <bx by bz> <radius>
 *     end
 *
 * (each `lift` record is one line). The whole file is refused on any line it
 * cannot read, so a half-written file never replaces a good set. */
#ifndef MJOLNIR_LIFTS_CORE_H
#define MJOLNIR_LIFTS_CORE_H
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define LIFT_MAX 128
#define LIFT_MAX_PLANES 256   /* in one phantom: Desolation's lifts have 156 */
#define LIFT_PLANE_POOL 4096  /* in the whole set */
#define LIFT_NAME 48
#define LIFT_WU_CM 304.8f
/* The simulation's gravity on a falling Spartan: 4.1715 wu/s^2 (1271 cm/s^2),
   measured on CU4 (docs/re/lift_push.md: velocity falls 0.13905 wu/s every
   second tick of 60). The Lua pushes before MJOLNIRLobby 0.25.0 assumed Halo
   1's 978 cm/s^2, so a lift that holds gravity off let players sag. */
#define LIFT_GRAVITY 4.1715f
/* Under a centimetre from an axis or centre there is no direction to pull. */
#define LIFT_HEADING_MIN (1.0f / LIFT_WU_CM)
/* The bounding sphere is only a quick reject before the shape's own test:
   the conversion writes it tight (Midship's pills touch it at their caps),
   so it is widened by 3 m, as the Lua pushes did. */
#define LIFT_NEAR_MARGIN (300.0f / LIFT_WU_CM)
/* No converted level is anywhere near this far from its origin. */
#define LIFT_FAR 100000.0f

enum { LIFT_PLANES = 1, LIFT_PILL = 2 };

typedef struct {
    int shape, first_plane, planes, negates_gravity;
    float pill[2][3], radius;
    float bounds[4];
    float origin[3], forward[3];
    float direction[2], axis[2], center[2]; /* acceleration (wu/s^2), top speed (wu/s) */
    char name[LIFT_NAME];
} lift_phantom;

typedef struct {
    int count, plane_count;
    lift_phantom lifts[LIFT_MAX];
    float plane[LIFT_PLANE_POOL][4];
} lift_set;

static inline float lift_dot(const float a[3], const float b[3]) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

/* Whether `p` is within LIFT_NEAR_MARGIN of the phantom's bounding sphere. */
static inline int lift_near(const lift_phantom *lift, const float p[3]) {
    float d[3] = {p[0] - lift->bounds[0], p[1] - lift->bounds[1], p[2] - lift->bounds[2]};
    float r = lift->bounds[3] + LIFT_NEAR_MARGIN;
    return lift_dot(d, d) <= r * r;
}

/* Whether `p` is inside the phantom's shape. */
static inline int lift_inside(const lift_set *set, const lift_phantom *lift, const float p[3]) {
    if (lift->shape == LIFT_PLANES) {
        for (int i = 0; i < lift->planes; i++) {
            const float *n = set->plane[lift->first_plane + i];
            if (n[0] * p[0] + n[1] * p[1] + n[2] * p[2] + n[3] > 0.0f) return 0;
        }
        return 1;
    }
    if (lift->shape == LIFT_PILL) {
        const float *a = lift->pill[0], *b = lift->pill[1];
        float ab[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]}, ap[3] = {p[0] - a[0], p[1] - a[1], p[2] - a[2]};
        float len2 = lift_dot(ab, ab), t = 0.0f;
        if (len2 > 0.0f) {
            t = lift_dot(ap, ab) / len2;
            t = t < 0.0f ? 0.0f : t > 1.0f ? 1.0f : t;
        }
        float d[3] = {ap[0] - ab[0] * t, ap[1] - ab[1] * t, ap[2] - ab[2] * t};
        return lift_dot(d, d) <= lift->radius * lift->radius;
    }
    return 0;
}

/* Speed `v` gains towards unit direction `u`, at `acc` up to `max`, over `dt`. */
static inline void lift_towards(float v[3], const float u[3], float acc, float max, float dt) {
    if (!(acc > 0.0f)) return;
    float along = lift_dot(v, u);
    if (along >= max) return;
    float dv = acc * dt;
    if (dv > max - along) dv = max - along;
    for (int k = 0; k < 3; k++) v[k] += u[k] * dv;
}

/* The unit vector along `d` and its length; 0 when it is too short to have one. */
static inline int lift_heading(const float d[3], float u[3], float *len) {
    float l = sqrtf(lift_dot(d, d));
    if (!(l >= LIFT_HEADING_MIN)) return 0;
    for (int k = 0; k < 3; k++) u[k] = d[k] / l;
    *len = l;
    return 1;
}

/* The velocity a player at `p` moving at `v` has after `dt` seconds in the
   phantom (gravity aside: see lift_sent), in place. Speeds towards the axis
   or centre are capped so the player slows into it rather than overshooting.
   `last`, the velocity this phantom meant for the player one push ago (or
   NULL), carries the speed along the push when something held the player:
   a biped on the ground reads still after a small push (the ground holds
   it), so without it a lift never lifts anyone standing. Only a loss of more
   than half counts. The simulation takes gravity off a biped every other
   tick, so between pushes it loses either nothing or twice a tick's worth;
   restoring every loss would keep the gains and drop the losses, and the
   speed would ratchet past the top speed. */
static inline void lift_push(const lift_phantom *lift, const float p[3], float v[3], float dt, const float *last) {
    const float *o = lift->origin, *f = lift->forward;
    float rel[3] = {p[0] - o[0], p[1] - o[1], p[2] - o[2]};
    if (last) {
        float carry = lift_dot(last, f) - (lift->negates_gravity ? 0.0f : LIFT_GRAVITY * dt * f[2]);
        float along = lift_dot(v, f);
        if (carry > 0.0f && along < 0.5f * carry)
            for (int k = 0; k < 3; k++) v[k] += f[k] * (carry - along);
    }
    lift_towards(v, f, lift->direction[0], lift->direction[1], dt);
    float u[3], len;
    if (lift->axis[0] > 0.0f) {
        float along = lift_dot(rel, f);
        float d[3] = {-(rel[0] - f[0] * along), -(rel[1] - f[1] * along), -(rel[2] - f[2] * along)};
        if (lift_heading(d, u, &len)) {
            float cap = len / (2.0f * dt);
            lift_towards(v, u, lift->axis[0], lift->axis[1] < cap ? lift->axis[1] : cap, dt);
        }
    }
    if (lift->center[0] > 0.0f) {
        float d[3] = {-rel[0], -rel[1], -rel[2]};
        if (lift_heading(d, u, &len)) {
            float cap = len / (2.0f * dt);
            lift_towards(v, u, lift->center[0], lift->center[1] < cap ? lift->center[1] : cap, dt);
        }
    }
}

/* What to set for intended velocity `v`: a phantom that negates gravity adds
   back what the simulation's gravity takes before the next push. */
static inline void lift_sent(float v[3], int negates_gravity, float dt) {
    if (negates_gravity) v[2] += LIFT_GRAVITY * dt;
}

/* A world velocity as object_set_velocity's forward, left and up for an
   object whose forward and up vectors are `forward` and `up`: the script
   function rebuilds the world velocity as forward*F + left*(U x F) + up*U
   (sim 0x663b90 on CU4), so for an orthonormal pair this is its inverse. */
static inline void lift_unit_frame(const float v[3], const float forward[3], const float up[3], float out[3]) {
    float left[3] = {up[1] * forward[2] - up[2] * forward[1], up[2] * forward[0] - up[0] * forward[2],
                     up[0] * forward[1] - up[1] * forward[0]};
    out[0] = lift_dot(v, forward);
    out[1] = lift_dot(v, left);
    out[2] = lift_dot(v, up);
}

/* Whether an object table entry (0x18 bytes: salt +0, type +4, datum size +6)
   holds the live biped `handle` names: the handle's salt, type 0 and a
   biped-sized datum. Not its +0x0c: that is the object's index on the host,
   the entry's own index only on a host. A fireteam client's entries 84 and 88
   read 139 and 140 (two copies, 2026-11-09), so checking it there turned
   away every unit, the client's own player included, and no joiner was ever
   pushed. */
static inline int lift_entry_is_biped(const unsigned char *entry, unsigned handle) {
    unsigned short salt, type, size;
    memcpy(&salt, entry, sizeof salt);
    memcpy(&type, entry + 4, sizeof type);
    memcpy(&size, entry + 6, sizeof size);
    return salt == (unsigned short)(handle >> 16) && type == 0 && size >= 0x80;
}

/* --- The text form -------------------------------------------------------- */

#define LIFT_TOKENS 32

/* Splits a line (no newline) at single spaces; -1 on a control character, an
   empty field or too many fields. */
static inline int lift_split(char *line, char **tokens) {
    int n = 0;
    if (!*line) return 0;
    tokens[n++] = line;
    for (char *p = line; *p; p++) {
        if (*p == ' ') {
            if (n == LIFT_TOKENS || p[1] == ' ' || !p[1]) return -1;
            *p = 0;
            tokens[n++] = p + 1;
        } else if ((unsigned char)*p < 32) return -1;
    }
    if (tokens[0][0] == 0) return -1;
    return n;
}

static inline int lift_number(const char *token, float *out, float lo, float hi) {
    char *end;
    float v = strtof(token, &end);
    if (end == token || *end || !isfinite(v) || v < lo || v > hi) return 0;
    *out = v;
    return 1;
}

static inline int lift_numbers(char **tokens, float *out, int n, float lo, float hi) {
    for (int i = 0; i < n; i++)
        if (!lift_number(tokens[i], out + i, lo, hi)) return 0;
    return 1;
}

static inline int lift_name_ok(const char *name) {
    size_t len = strlen(name);
    if (!len || len >= LIFT_NAME) return 0;
    for (const char *p = name; *p; p++) {
        char c = *p;
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.'))
            return 0;
    }
    return 1;
}

/* One `lift` record (tokens after the keyword) into `lift`; the planes that
   follow are read by the caller. */
static inline int lift_record(char **t, int n, lift_phantom *lift, int *planes) {
    memset(lift, 0, sizeof *lift);
    if (n != 20 && n != 26) return 0;
    if (!lift_name_ok(t[0])) return 0;
    memcpy(lift->name, t[0], strlen(t[0]) + 1);
    if (strcmp(t[1], "0") && strcmp(t[1], "1")) return 0;
    lift->negates_gravity = t[1][0] == '1';
    float values[16];
    if (!lift_numbers(t + 2, values, 16, -LIFT_FAR, LIFT_FAR)) return 0;
    memcpy(lift->origin, values, sizeof lift->origin);
    memcpy(lift->forward, values + 3, sizeof lift->forward);
    memcpy(lift->bounds, values + 6, sizeof lift->bounds);
    memcpy(lift->direction, values + 10, sizeof lift->direction);
    memcpy(lift->axis, values + 12, sizeof lift->axis);
    memcpy(lift->center, values + 14, sizeof lift->center);
    float length = sqrtf(lift_dot(lift->forward, lift->forward));
    if (!(length > 0.99f && length < 1.01f)) return 0;
    for (int k = 0; k < 3; k++) lift->forward[k] /= length;
    if (!(lift->bounds[3] > 0.0f)) return 0;
    /* At most 1000 wu/s^2 and 100 wu/s: H2's strongest pads are a few tens. */
    for (int k = 10; k < 16; k++)
        if (values[k] < 0.0f || values[k] > (k % 2 ? 100.0f : 1000.0f)) return 0;
    if (n == 20) {
        float count;
        if (strcmp(t[18], "planes") || !lift_number(t[19], &count, 1.0f, (float)LIFT_MAX_PLANES)
            || count != floorf(count)) return 0;
        lift->shape = LIFT_PLANES;
        *planes = (int)count;
        return 1;
    }
    if (strcmp(t[18], "pill")) return 0;
    float pill[7];
    if (!lift_numbers(t + 19, pill, 7, -LIFT_FAR, LIFT_FAR) || !(pill[6] > 0.0f)) return 0;
    memcpy(lift->pill, pill, sizeof lift->pill);
    lift->radius = pill[6];
    lift->shape = LIFT_PILL;
    *planes = 0;
    return 1;
}

/* Parses `text` (NUL-terminated; changed in place) into `out`. Returns 0, or
   the line number of the first line it could not read (`out` is then
   undefined: parse into scratch and copy only on success). */
static inline int lift_parse(char *text, lift_set *out) {
    out->count = out->plane_count = 0;
    int line_number = 0, planes_due = 0, ended = 0, started = 0;
    lift_phantom *lift = NULL;
    char *line = text;
    while (line && *line) {
        char *next = strchr(line, '\n');
        if (next) *next++ = 0;
        size_t len = strlen(line);
        if (len && line[len - 1] == '\r') line[--len] = 0;
        line_number++;
        char *t[LIFT_TOKENS];
        int n = lift_split(line, t);
        if (n <= 0 || ended) return line_number;
        if (!started) {
            if (n != 2 || strcmp(t[0], "mjolnir-lifts") || strcmp(t[1], "1")) return line_number;
            started = 1;
        } else if (!strcmp(t[0], "plane")) {
            float *plane = out->plane[out->plane_count];
            if (!planes_due || n != 5 || !lift_numbers(t + 1, plane, 4, -LIFT_FAR, LIFT_FAR)) return line_number;
            out->plane_count++;
            lift->planes++;
            planes_due--;
        } else if (!strcmp(t[0], "lift")) {
            int planes = 0;
            if (planes_due || out->count == LIFT_MAX) return line_number;
            lift = &out->lifts[out->count];
            if (!lift_record(t + 1, n - 1, lift, &planes) || out->plane_count + planes > LIFT_PLANE_POOL)
                return line_number;
            lift->first_plane = out->plane_count;
            lift->planes = 0;
            planes_due = planes;
            out->count++;
        } else if (!strcmp(t[0], "end")) {
            if (n != 1 || planes_due) return line_number;
            ended = 1;
        } else {
            return line_number;
        }
        line = next;
    }
    return ended ? 0 : line_number + 1;
}

#endif
