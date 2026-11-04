/* Portable, data-only automatic Forge door contract and movement math.
 * Positions/lengths in this file are metres. The simulation adapter converts
 * the engine's 3.048-metre world units at its boundary. */
#ifndef MJOLNIR_FORGE_DOORS_CORE_H
#define MJOLNIR_FORGE_DOORS_CORE_H
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define FORGE_DOOR_MAX_DEFINITIONS 256
#define FORGE_DOOR_MAX_ACTIVE 128
#define FORGE_DOOR_PHYSICS_CACHE 256
typedef struct {
    char tag[224];
    float travel, speed, trigger[3], hold, size[3];
} forge_door_config;
typedef struct { float offset, wait; } forge_door_motion;
typedef struct {
    uint32_t tags[FORGE_DOOR_PHYSICS_CACHE];
    unsigned char fixed[FORGE_DOOR_PHYSICS_CACHE];
    unsigned count;
} forge_door_physics_cache;
typedef int (*forge_door_physics_resolver)(uint32_t tag, void *context);

/* The CU4 PHMO body builder reads motion type at +1c in each d0-byte
 * record. Only fixed (5) is stationary: keyframed (4), mixed and unknown
 * models remain obstacles. Empty data cannot prove a model immovable. */
static inline int forge_door_fixed_bodies(const unsigned char *bodies, int count) {
    if (!bodies || count < 1 || count > 64) return 0;
    for (int i = 0; i < count; i++) if (bodies[(size_t)i * 0xd0 + 0x1c] != 5) return 0;
    return 1;
}

/* Both positive and negative classifications are cached once per salted
 * tag/world. At capacity keep unknown tags as obstacles without repeatedly
 * decoding them. The simulation adapter clears this cache on world change. */
static inline int forge_door_cached_fixed(forge_door_physics_cache *cache, uint32_t tag,
                                          forge_door_physics_resolver resolve, void *context) {
    if (tag == UINT32_MAX || !(tag >> 16) || !resolve) return 0;
    for (unsigned i = 0; i < cache->count; i++) if (cache->tags[i] == tag) return cache->fixed[i];
    if (cache->count >= FORGE_DOOR_PHYSICS_CACHE) return 0;
    unsigned i = cache->count++;
    cache->tags[i] = tag;
    cache->fixed[i] = resolve(tag, context) != 0;
    return cache->fixed[i];
}

/* Authored scenario objects can retain the unbound MV handle sentinel even
 * while their salted object datum points back to this active entry. Accept
 * that case only with an independently resolved palette/variant tag. A real
 * but different MV handle must never authorize a recycled object slot. */
static inline int forge_door_binding(uint32_t handle, uint32_t entry_handle,
                                     int object_entry, int entry_index,
                                     uint32_t object_tag, uint32_t palette_tag) {
    return handle != UINT32_MAX && (handle >> 16) && object_entry >= 0
        && object_entry < 651 && object_entry == entry_index
        && object_tag != UINT32_MAX && (object_tag >> 16) && object_tag == palette_tag
        && (entry_handle == UINT32_MAX || entry_handle == handle);
}

static inline int forge_door_token(const char *s, size_t n, int block) {
    if (n < (block ? 1u : 2u) || n > 64 || !((*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9'))) return 0;
    for (size_t i = 0; i < n; i++)
        if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= '0' && s[i] <= '9') || s[i] == '-' || (block && s[i] == '_'))) return 0;
    return 1;
}

static inline int forge_door_tag(const char *s) {
    static const char prefix[] = "objects\\mjolnir\\forge\\";
    if (strncmp(s, prefix, sizeof prefix - 1)) return 0;
    const char *slug = s + sizeof prefix - 1, *slash = strchr(slug, '\\');
    return slash && forge_door_token(slug, (size_t)(slash - slug), 0)
        && forge_door_token(slash + 1, strlen(slash + 1), 1);
}

static inline int forge_door_config_valid(const forge_door_config *c) {
    if (!forge_door_tag(c->tag) || !isfinite(c->travel) || c->travel <= 0 || c->travel > 16
        || !isfinite(c->speed) || c->speed <= 0 || c->speed > 8
        || !isfinite(c->hold) || c->hold < 0 || c->hold > 10) return 0;
    for (int k = 0; k < 3; k++)
        if (!isfinite(c->trigger[k]) || c->trigger[k] <= 0 || c->trigger[k] > 32
            || !isfinite(c->size[k]) || c->size[k] <= 0 || c->size[k] > 64) return 0;
    return 1;
}

/* Exactly ten tab-separated fields. No trailing text, nonfinite numbers,
 * blank fields, control characters, oversized names or extra rows accepted. */
static inline int forge_door_parse(char *line, forge_door_config *out) {
    char *fields[10];
    size_t len = strlen(line);
    while (len && (line[len - 1] == '\r' || line[len - 1] == '\n')) line[--len] = 0;
    if (!len) return 0;
    int n = 1;
    fields[0] = line;
    for (char *p = line; *p; p++) {
        if (*p == '\t') {
            if (n >= 10) return 0;
            *p = 0;
            fields[n++] = p + 1;
        } else if ((unsigned char)*p < 32) return 0;
    }
    if (n != 10 || strlen(fields[0]) >= sizeof out->tag) return 0;
    forge_door_config c = {0};
    memcpy(c.tag, fields[0], strlen(fields[0]) + 1);
    float values[9];
    for (int i = 1; i < 10; i++) {
        char *end;
        if (!*fields[i] || *fields[i] == ' ') return 0;
        values[i - 1] = strtof(fields[i], &end);
        if (*end || end == fields[i] || !isfinite(values[i - 1])) return 0;
    }
    c.travel = values[0]; c.speed = values[1];
    memcpy(c.trigger, values + 2, sizeof c.trigger);
    c.hold = values[5];
    memcpy(c.size, values + 6, sizeof c.size);
    if (!forge_door_config_valid(&c)) return 0;
    *out = c;
    return 1;
}

static inline float forge_door_dot(const float a[3], const float b[3]) {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static inline int forge_door_basis(const float forward[3], const float up[3], float left[3]) {
    for (int k = 0; k < 3; k++) if (!isfinite(forward[k]) || !isfinite(up[k])) return 0;
    if (fabsf(forge_door_dot(forward, forward) - 1) > 0.02f
        || fabsf(forge_door_dot(up, up) - 1) > 0.02f
        || fabsf(forge_door_dot(forward, up)) > 0.02f) return 0;
    left[0] = up[1] * forward[2] - up[2] * forward[1];
    left[1] = up[2] * forward[0] - up[0] * forward[2];
    left[2] = up[0] * forward[1] - up[1] * forward[0];
    return 1;
}

/* Forge fills the map variant's bounds; other game modes leave all six at
   zero. All zero means there is no box to check, not a box at the origin. */
static inline int forge_door_in_bounds(const float position[3], const float bounds[6]) {
    int unset = 1;
    for (int k = 0; k < 6; k++) {
        if (!isfinite(bounds[k])) return 0;
        if (bounds[k] != 0) unset = 0;
    }
    for (int k = 0; k < 3; k++) if (!isfinite(position[k])) return 0;
    if (unset) return 1;
    for (int k = 0; k < 3; k++)
        if (position[k] < bounds[k * 2] || position[k] > bounds[k * 2 + 1]) return 0;
    return 1;
}

static inline int forge_door_local(const float point[3], const float origin[3], const float forward[3],
                                  const float left[3], const float up[3], float local[3]) {
    float d[3];
    for (int k = 0; k < 3; k++) {
        if (!isfinite(point[k]) || !isfinite(origin[k])) return 0;
        d[k] = point[k] - origin[k];
    }
    local[0] = forge_door_dot(d, forward);
    local[1] = forge_door_dot(d, left);
    local[2] = forge_door_dot(d, up);
    return isfinite(local[0]) && isfinite(local[1]) && isfinite(local[2]);
}

static inline int forge_door_trigger(const forge_door_config *c, const float local[3]) {
    return isfinite(local[0]) && isfinite(local[1]) && isfinite(local[2])
        && fabsf(local[0]) <= c->trigger[0] * 0.5f
        && fabsf(local[1]) <= c->trigger[1] * 0.5f
        && local[2] >= -0.5f && local[2] <= c->trigger[2];
}

/* Conservative sphere vs the whole closing swept panel, including a small
 * clearance margin. Opening also uses this for overhead obstacles. */
static inline int forge_door_swept_blocked(const forge_door_config *c, float from, float to,
                                         const float local[3], float radius) {
    if (!isfinite(radius) || radius < 0 || radius > 128 || !isfinite(from) || !isfinite(to)) return 1;
    const float margin = 0.1f;
    float lo[3] = {-c->size[0] * 0.5f - margin, -c->size[1] * 0.5f - margin, fminf(from, to) - margin};
    float hi[3] = { c->size[0] * 0.5f + margin,  c->size[1] * 0.5f + margin, fmaxf(from, to) + c->size[2] + margin};
    float distance = 0;
    for (int k = 0; k < 3; k++) {
        if (!isfinite(local[k])) return 1;
        float d = local[k] < lo[k] ? lo[k] - local[k] : local[k] > hi[k] ? local[k] - hi[k] : 0;
        distance += d * d;
    }
    return distance <= radius * radius;
}

static inline float forge_door_advance(const forge_door_config *c, forge_door_motion *m,
                                      float dt, int approach, int blocked, int editing) {
    if (editing) { m->offset = 0; m->wait = 0; return 0; }
    if (!isfinite(dt) || dt <= 0 || dt > 0.1f) return m->offset;
    if (!isfinite(m->offset) || m->offset < 0 || m->offset > c->travel || !isfinite(m->wait)) {
        m->offset = 0; m->wait = 0;
    }
    if (approach || blocked) m->wait = c->hold;
    else m->wait = fmaxf(0, m->wait - dt);
    float target = (approach || blocked || m->wait > 0) ? c->travel : 0;
    float step = c->speed * dt;
    m->offset = target > m->offset ? fminf(target, m->offset + step) : fmaxf(target, m->offset - step);
    return m->offset;
}
#endif
