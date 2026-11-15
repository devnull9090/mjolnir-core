/* The players' roster from the simulation's own tables, for MJOLNIRHud's
 * markers (docs/lua_native_audit.md, "Player roster from the simulation").
 * Portable and data-only: no game process or Windows headers, so
 * test_roster.c can run it over tables it builds. roster_runtime.h calls
 * roster_read on the simulation thread and hands the packed form to Lua.
 *
 * What it reads, every table checked against its own header first
 * (roster_slot, the check lifts and doors make):
 *  - the players table (0x4b0 a player, at most 16): salt +0, unit handle
 *    +0x28, team +0xad (the field client_teams_tick keeps right on a
 *    fireteam client);
 *  - the player-to-local-user map: +0x34 + 4p, the local user, -1 for a
 *    player of another machine;
 *  - the object table (0x18 an entry: salt +0, type +4, size +6, datum
 *    +0x10): the unit must be a live biped (type 0); its parent at +0x14,
 *    position +0x44 and velocity +0x68 (world units, per second).
 *
 * An entry's +0x0C is never checked: on a fireteam client it holds the
 * host's index for the object, not the entry's own (#375).
 *
 * A seated player's +0x44 is relative to the seat, so a seated player is
 * where the outermost parent is (#348: their marker stayed where they got
 * in). Positions and velocities go out in Unreal centimetres, the sim's y
 * flipped (lifts_core.h has the frame).
 *
 * The packed form, little-endian, read with string.unpack by
 * mods/MJOLNIRHud/Scripts/roster.lua:
 *
 *     header  "<I2 I2 I2 I2 i4"  version, record size, count, 0, tick
 *     record  "<B B b b I2 I2 I4 f f f f f f I4" (40 bytes) each:
 *             index, flags (1 alive, 2 seated, 4 this machine's), local
 *             user, team, salt, 0, unit handle, x y z (cm), velocity x y z
 *             (cm/s), the handle of the object the place is read from
 *
 * A record size above ROSTER_RECORD adds fields at the end: a reader takes
 * the first ROSTER_RECORD bytes of each. */
#ifndef MJOLNIR_ROSTER_CORE_H
#define MJOLNIR_ROSTER_CORE_H
#include <math.h>
#include <stdint.h>
#include <string.h>

#define ROSTER_SEATS 16
#define ROSTER_VERSION 1
#define ROSTER_HEADER 12
#define ROSTER_RECORD 40
#define ROSTER_PACKED_MAX (ROSTER_HEADER + ROSTER_SEATS * ROSTER_RECORD)
#define ROSTER_WU_CM 304.8f
/* No converted level is anywhere near this far from its origin (LIFT_FAR). */
#define ROSTER_FAR 100000.0f
/* Parents followed up from a seat: a gunner on a turret on a vehicle is 2. */
#define ROSTER_PARENTS 4
#define ROSTER_TABLE_MAGIC 0x64407440u /* 'd@t@' */

enum { ROSTER_ALIVE = 1, ROSTER_SEATED = 2, ROSTER_LOCAL = 4 };

typedef struct {
    int index, flags, local_user, team;
    unsigned short salt;
    uint32_t unit, placed_by;
    float at[3], velocity[3];
} roster_seat;

typedef struct {
    int count, tick;
    roster_seat seats[ROSTER_SEATS];
} roster_snapshot;

static inline uint16_t roster_u16(const unsigned char *p) {
    uint16_t v;
    memcpy(&v, p, sizeof v);
    return v;
}
static inline uint32_t roster_u32(const unsigned char *p) {
    uint32_t v;
    memcpy(&v, p, sizeof v);
    return v;
}
static inline const unsigned char *roster_ptr(const unsigned char *p) {
    const unsigned char *v;
    memcpy(&v, p, sizeof v);
    return v;
}

/* Entry `index` of a simulation data table when the table checks out (its
   magic, its stride, at most `limit` entries) and the entry is in use. */
static inline const unsigned char *roster_slot(const unsigned char *table, unsigned index, unsigned stride,
                                               unsigned limit) {
    if (!table || roster_u32(table + 0x28) != ROSTER_TABLE_MAGIC || !table[0x31] || roster_u32(table + 0x20) != stride)
        return NULL;
    unsigned maximum = roster_u32(table + 0x2c), count = roster_u32(table + 0x44);
    const unsigned char *data = roster_ptr(table + 0x50), *bits = roster_ptr(table + 0x58);
    if (!data || !bits || maximum > limit || count > maximum || index >= count || !(bits[index / 8] & (1u << (index % 8))))
        return NULL;
    return data + (size_t)index * stride;
}

/* The datum of the object `handle` names, any type, when its entry's salt
   matches and the entry is big enough to be an object; `type` is set. */
static inline const unsigned char *roster_object(const unsigned char *objects, uint32_t handle, int *type) {
    if (handle == UINT32_MAX || !(handle >> 16)) return NULL;
    const unsigned char *entry = roster_slot(objects, handle & 0xffff, 0x18, 4096);
    if (!entry || roster_u16(entry) != (uint16_t)(handle >> 16) || roster_u16(entry + 6) < 0x80) return NULL;
    if (type) *type = roster_u16(entry + 4);
    return roster_ptr(entry + 0x10);
}

static inline int roster_vector_ok(const float *v, float limit) {
    for (int k = 0; k < 3; k++)
        if (!isfinite(v[k]) || fabsf(v[k]) > limit) return 0;
    return 1;
}

/* Simulation units to Unreal's: centimetres, y flipped. */
static inline void roster_to_unreal(const float *sim, float *out) {
    out[0] = sim[0] * ROSTER_WU_CM;
    out[1] = -sim[1] * ROSTER_WU_CM;
    out[2] = sim[2] * ROSTER_WU_CM;
}

/* Every player in the table into `out`; a player without a live biped is
   listed, not alive. 0 when the players table does not check out (out->count
   0), else 1. A seat whose numbers are not believable is listed not alive. */
static inline int roster_read(const unsigned char *players, const unsigned char *users, const unsigned char *objects,
                              int tick, roster_snapshot *out) {
    out->count = 0;
    out->tick = tick;
    if (!players || roster_u32(players + 0x28) != ROSTER_TABLE_MAGIC || roster_u32(players + 0x20) != 0x4b0) return 0;
    for (int i = 0; i < ROSTER_SEATS; i++) {
        const unsigned char *player = roster_slot(players, (unsigned)i, 0x4b0, ROSTER_SEATS);
        if (!player || !roster_u16(player)) continue;
        roster_seat *s = &out->seats[out->count++];
        memset(s, 0, sizeof *s);
        s->index = i;
        s->salt = roster_u16(player);
        s->team = (signed char)player[0xad];
        s->local_user = users ? (int)roster_u32(users + 0x34 + (size_t)i * 4) : -1;
        if (s->local_user < -1 || s->local_user > 3) s->local_user = -1;
        if (s->local_user >= 0) s->flags |= ROSTER_LOCAL;
        s->unit = roster_u32(player + 0x28);
        s->placed_by = UINT32_MAX;
        int type = -1;
        const unsigned char *unit = roster_object(objects, s->unit, &type);
        if (!unit || type != 0) continue;
        const unsigned char *place = unit;
        uint32_t placed_by = s->unit;
        for (int depth = 0; depth < ROSTER_PARENTS; depth++) {
            uint32_t parent = roster_u32(place + 0x14);
            if (parent == UINT32_MAX) break;
            const unsigned char *up = roster_object(objects, parent, NULL);
            if (!up) {
                place = NULL;
                break;
            }
            place = up;
            placed_by = parent;
            s->flags |= ROSTER_SEATED;
        }
        if (!place) continue;
        float at[3], velocity[3];
        memcpy(at, place + 0x44, sizeof at);
        memcpy(velocity, place + 0x68, sizeof velocity);
        if (roster_u32(place + 0x14) != UINT32_MAX || !roster_vector_ok(at, ROSTER_FAR)
            || !roster_vector_ok(velocity, 1000.0f))
            continue;
        roster_to_unreal(at, s->at);
        roster_to_unreal(velocity, s->velocity);
        s->placed_by = placed_by;
        s->flags |= ROSTER_ALIVE;
    }
    return 1;
}

static inline unsigned char *roster_put16(unsigned char *p, unsigned v) {
    p[0] = (unsigned char)(v & 0xff);
    p[1] = (unsigned char)(v >> 8 & 0xff);
    return p + 2;
}
static inline unsigned char *roster_put32(unsigned char *p, uint32_t v) {
    for (int k = 0; k < 4; k++) p[k] = (unsigned char)(v >> (8 * k) & 0xff);
    return p + 4;
}
static inline unsigned char *roster_putf(unsigned char *p, float f) {
    uint32_t v;
    memcpy(&v, &f, sizeof v);
    return roster_put32(p, v);
}

/* The packed form of `s` into out (ROSTER_PACKED_MAX bytes is always
   enough); its length, or 0 when `cap` is too small. */
static inline size_t roster_pack(const roster_snapshot *s, unsigned char *out, size_t cap) {
    int count = s->count < 0 ? 0 : s->count > ROSTER_SEATS ? ROSTER_SEATS : s->count;
    size_t n = ROSTER_HEADER + (size_t)count * ROSTER_RECORD;
    if (n > cap) return 0;
    unsigned char *p = out;
    p = roster_put16(p, ROSTER_VERSION);
    p = roster_put16(p, ROSTER_RECORD);
    p = roster_put16(p, (unsigned)count);
    p = roster_put16(p, 0);
    p = roster_put32(p, (uint32_t)s->tick);
    for (int i = 0; i < count; i++) {
        const roster_seat *e = &s->seats[i];
        *p++ = (unsigned char)e->index;
        *p++ = (unsigned char)e->flags;
        *p++ = (unsigned char)(signed char)e->local_user;
        *p++ = (unsigned char)(signed char)e->team;
        p = roster_put16(p, e->salt);
        p = roster_put16(p, 0);
        p = roster_put32(p, e->unit);
        for (int k = 0; k < 3; k++) p = roster_putf(p, e->at[k]);
        for (int k = 0; k < 3; k++) p = roster_putf(p, e->velocity[k]);
        p = roster_put32(p, e->placed_by);
    }
    return (size_t)(p - out);
}

/* Seat `index` of `s`, or NULL. */
static inline const roster_seat *roster_find(const roster_snapshot *s, int index) {
    for (int i = 0; i < s->count; i++)
        if (s->seats[i].index == index) return &s->seats[i];
    return NULL;
}

#endif
