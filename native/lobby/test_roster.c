/* Portable tests for roster_core.h over tables built here, laid out as the
 * simulation's are (a data table header, its entries and their in-use bits).
 * With a path argument it also writes the packed roster there, for
 * tools/tests/test_roster.lua to read with MJOLNIRHud's roster.lua. */
#include <stdio.h>
#include <stdlib.h>
#include "roster_core.h"

static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
static int near_to(float a, float b) { return isfinite(a) && fabsf(a - b) <= 0.01f; }

typedef struct {
    unsigned char header[0x60];
    unsigned char *data;
    unsigned char bits[4096 / 8];
} table;

static void put16(unsigned char *p, unsigned v) { uint16_t x = (uint16_t)v; memcpy(p, &x, sizeof x); }
static void put32(unsigned char *p, uint32_t v) { memcpy(p, &v, sizeof v); }
static void putf3(unsigned char *p, float x, float y, float z) {
    float v[3] = {x, y, z};
    memcpy(p, v, sizeof v);
}

static void table_init(table *t, unsigned stride, unsigned maximum, unsigned count) {
    memset(t, 0, sizeof *t);
    t->data = calloc(maximum, stride);
    put32(t->header + 0x20, stride);
    put32(t->header + 0x28, ROSTER_TABLE_MAGIC);
    put32(t->header + 0x2c, maximum);
    t->header[0x31] = 1;
    put32(t->header + 0x44, count);
    unsigned char *data = t->data, *bits = t->bits;
    memcpy(t->header + 0x50, &data, sizeof data);
    memcpy(t->header + 0x58, &bits, sizeof bits);
}

static unsigned char *table_use(table *t, unsigned index) {
    t->bits[index / 8] |= (unsigned char)(1u << (index % 8));
    return t->data + (size_t)index * roster_u32(t->header + 0x20);
}

static table players, objects;
static unsigned char users[0x34 + 4 * 16];
/* Each object's datum: parent +0x14, position +0x44, velocity +0x68. */
static unsigned char datums[12][0x100];

/* Object entry `index`, salt `salt`, of `type`; its datum is datums[d]. */
static uint32_t object(unsigned index, unsigned salt, unsigned type, int d, uint32_t parent, float x, float y, float z) {
    unsigned char *e = table_use(&objects, index);
    put16(e, salt);
    put16(e + 4, type);
    put16(e + 6, 0x1f4);
    put16(e + 0x0c, index + 50); /* a client's entry: the host's index, never checked */
    unsigned char *datum = datums[d];
    memcpy(e + 0x10, &datum, sizeof datum);
    put32(datum + 0x14, parent);
    putf3(datum + 0x44, x, y, z);
    putf3(datum + 0x68, 0.5f, -0.25f, 0.0f);
    return (uint32_t)salt << 16 | index;
}

static void player(unsigned i, unsigned salt, uint32_t unit, int team, int user) {
    unsigned char *p = table_use(&players, i);
    put16(p, salt);
    put32(p + 0x28, unit);
    p[0xad] = (unsigned char)team;
    put32(users + 0x34 + 4 * i, (uint32_t)user);
}

int main(int argc, char **argv) {
    table_init(&players, 0x4b0, 16, 16);
    table_init(&objects, 0x18, 2048, 300);
    for (int i = 0; i < 16; i++) put32(users + 0x34 + 4 * i, UINT32_MAX);

    /* 0: this machine's player on foot. */
    uint32_t mine = object(10, 0xe2c3, 0, 0, UINT32_MAX, 38.9f, -81.087f, 1.702f);
    player(0, 0xe9a1, mine, 0, 0);
    /* 1: another machine's player, driving: their biped hangs off a Warthog
       (type 1) whose own place is the world's. */
    uint32_t hog = object(20, 0xe300, 1, 1, UINT32_MAX, 10.0f, 20.0f, 0.5f);
    uint32_t driver = object(21, 0xe301, 0, 2, hog, 0.3f, 0.4f, 0.2f);
    player(1, 0xe9a2, driver, 1, -1);
    /* 2: dead, respawning: no unit. */
    player(2, 0xe9a3, UINT32_MAX, 1, -1);
    /* 3: a unit handle whose salt no longer matches (the entry reused). */
    object(30, 0xe400, 0, 3, UINT32_MAX, 1.0f, 1.0f, 1.0f);
    player(3, 0xe9a4, (uint32_t)0xe3ff << 16 | 30, 0, -1);
    /* 4: a unit that is not a biped. */
    uint32_t crate = object(40, 0xe500, 6, 4, UINT32_MAX, 2.0f, 2.0f, 2.0f);
    player(4, 0xe9a5, crate, 0, -1);
    /* 5: seated on something that is gone. */
    uint32_t orphan = object(50, 0xe600, 0, 5, (uint32_t)0xe601 << 16 | 51, 3.0f, 3.0f, 3.0f);
    player(5, 0xe9a6, orphan, 0, -1);
    /* 6: a place nobody could stand at. */
    uint32_t lost = object(60, 0xe700, 0, 6, UINT32_MAX, NAN, 0.0f, 0.0f);
    player(6, 0xe9a7, lost, 0, -1);
    /* 7: a gunner on a turret on a vehicle: the vehicle's place. */
    uint32_t base = object(70, 0xe800, 1, 7, UINT32_MAX, -5.0f, 6.0f, 7.0f);
    uint32_t turret = object(71, 0xe801, 1, 8, base, 0.1f, 0.1f, 0.1f);
    uint32_t gunner = object(72, 0xe802, 0, 9, turret, 0.0f, 0.0f, 0.0f);
    player(7, 0xe9a8, gunner, 1, -1);

    roster_snapshot s;
    CHECK(roster_read(players.header, users, objects.header, 1234, &s) == 1);
    CHECK(s.count == 8 && s.tick == 1234);

    const roster_seat *e = roster_find(&s, 0);
    CHECK(e && e->flags == (ROSTER_ALIVE | ROSTER_LOCAL) && e->local_user == 0 && e->team == 0);
    CHECK(near_to(e->at[0], 38.9f * 304.8f) && near_to(e->at[1], 81.087f * 304.8f) && near_to(e->at[2], 1.702f * 304.8f));
    CHECK(near_to(e->velocity[0], 0.5f * 304.8f) && near_to(e->velocity[1], 0.25f * 304.8f));
    CHECK(e->unit == mine && e->placed_by == mine && e->salt == 0xe9a1);

    e = roster_find(&s, 1);
    CHECK(e && e->flags == (ROSTER_ALIVE | ROSTER_SEATED) && e->local_user == -1 && e->team == 1);
    CHECK(near_to(e->at[0], 3048.0f) && near_to(e->at[1], -6096.0f) && near_to(e->at[2], 152.4f));
    CHECK(e->unit == driver && e->placed_by == hog);

    e = roster_find(&s, 2);
    CHECK(e && e->flags == 0 && e->unit == UINT32_MAX && e->placed_by == UINT32_MAX);
    for (int i = 3; i <= 6; i++) {
        e = roster_find(&s, i);
        CHECK(e && !(e->flags & ROSTER_ALIVE));
    }
    e = roster_find(&s, 7);
    CHECK(e && (e->flags & ROSTER_SEATED) && (e->flags & ROSTER_ALIVE) && e->placed_by == base);
    CHECK(near_to(e->at[0], -5.0f * 304.8f) && near_to(e->at[1], -6.0f * 304.8f));
    CHECK(roster_find(&s, 8) == NULL);

    /* No users map: everyone is another machine's. */
    roster_snapshot t;
    CHECK(roster_read(players.header, NULL, objects.header, 5, &t) == 1);
    CHECK(roster_find(&t, 0)->local_user == -1 && !(roster_find(&t, 0)->flags & ROSTER_LOCAL));
    /* No object table: everyone listed, nobody alive. */
    CHECK(roster_read(players.header, users, NULL, 5, &t) == 1 && t.count == 8);
    for (int i = 0; i < t.count; i++) CHECK(!(t.seats[i].flags & ROSTER_ALIVE));
    /* A players table that does not check out. */
    put32(players.header + 0x20, 0x4a0);
    CHECK(roster_read(players.header, users, objects.header, 5, &t) == 0 && t.count == 0);
    put32(players.header + 0x20, 0x4b0);
    put32(players.header + 0x28, 0x12345678);
    CHECK(roster_read(players.header, users, objects.header, 5, &t) == 0);
    put32(players.header + 0x28, ROSTER_TABLE_MAGIC);
    CHECK(roster_read(NULL, users, objects.header, 5, &t) == 0);
    /* An object table bigger than the check allows: nobody alive. */
    put32(objects.header + 0x2c, 8192);
    CHECK(roster_read(players.header, users, objects.header, 5, &t) == 1 && !(roster_find(&t, 0)->flags & ROSTER_ALIVE));
    put32(objects.header + 0x2c, 2048);

    /* The packed form. */
    unsigned char packed[ROSTER_PACKED_MAX];
    size_t n = roster_pack(&s, packed, sizeof packed);
    CHECK(n == ROSTER_HEADER + 8 * ROSTER_RECORD);
    CHECK(roster_pack(&s, packed, n - 1) == 0);
    CHECK(roster_u16(packed) == ROSTER_VERSION && roster_u16(packed + 2) == ROSTER_RECORD && roster_u16(packed + 4) == 8);
    CHECK(roster_u32(packed + 8) == 1234);
    const unsigned char *r1 = packed + ROSTER_HEADER + ROSTER_RECORD;
    CHECK(r1[0] == 1 && r1[1] == (ROSTER_ALIVE | ROSTER_SEATED) && (signed char)r1[2] == -1 && r1[3] == 1);
    CHECK(roster_u16(r1 + 4) == 0xe9a2 && roster_u32(r1 + 8) == driver && roster_u32(r1 + 36) == hog);
    float x;
    memcpy(&x, r1 + 12, sizeof x);
    CHECK(near_to(x, 3048.0f));
    roster_snapshot empty = {0};
    CHECK(roster_pack(&empty, packed, sizeof packed) == ROSTER_HEADER);

    /* The packed roster, byte for byte, against the fixture MJOLNIRHud's
       reader is tested with (tools/tests/test_roster.lua), so the two sides
       cannot drift apart; `--write <path>` makes it again. */
    n = roster_pack(&s, packed, sizeof packed);
    if (argc > 2 && !strcmp(argv[1], "--write")) {
        FILE *f = fopen(argv[2], "wb");
        CHECK(f && fwrite(packed, 1, n, f) == n);
        fclose(f);
        printf("roster: wrote %s (%zu bytes)\n", argv[2], n);
    } else if (argc > 1) {
        unsigned char fixture[ROSTER_PACKED_MAX + 1];
        FILE *f = fopen(argv[1], "rb");
        CHECK(f != NULL);
        size_t got = fread(fixture, 1, sizeof fixture, f);
        fclose(f);
        CHECK(got == n && !memcmp(fixture, packed, n));
    }
    printf("roster: %d checks ok\n", checks);
    return 0;
}
