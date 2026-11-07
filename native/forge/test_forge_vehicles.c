#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "forge_vehicles.h"
static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

#define MV_BYTES (VEHICLE_MV_ENTRY_TABLE + VEHICLE_MV_ENTRY_COUNT * VEHICLE_MV_ENTRY_STRIDE)
static uint8_t mv[MV_BYTES];

static void label(int index, int at, const char *name) {
    int16_t offset = (int16_t)at;
    memcpy(mv + VEHICLE_MV_LABELS + index * 2, &offset, 2);
    memcpy(mv + VEHICLE_MV_LABEL_STRINGS + at, name, strlen(name) + 1);
}
static uint8_t *props(int index) {
    return mv + VEHICLE_MV_ENTRY_TABLE + index * VEHICLE_MV_ENTRY_STRIDE + VEHICLE_MV_ENTRY_PROPS;
}
static void entry(int index, int used, int16_t which, uint8_t flags, uint8_t team) {
    mv[VEHICLE_MV_ENTRY_TABLE + index * VEHICLE_MV_ENTRY_STRIDE] = (uint8_t)used;
    memcpy(props(index) + VEHICLE_PROPS_LABEL, &which, 2);
    props(index)[VEHICLE_PROPS_FLAGS] = flags;
    props(index)[VEHICLE_PROPS_TEAM] = team;
}
static void setup(void) {
    memset(mv, 0, sizeof mv);
    *(int32_t *)(mv + VEHICLE_MV_LABEL_COUNT) = 3;
    label(0, 0, "ce_warthog_1");
    label(1, 16, "ce_warthog_10");
    label(2, 32, "ce_ghost_1");
    entry(0, 1, 0, 0x2c, 0);   // named, either team
    entry(1, 1, 1, 0x2c, 1);   // a longer name sharing the first's start
    entry(2, 1, 2, 0x2c, 0);   // red's only
    entry(3, 1, 2, 0x2c, 1);   // blue's, not named
    entry(4, 1, -1, 0x0c, 8);  // placed from the palette
    entry(5, 0, 0, 0x2c, 0);   // a free slot
}
static forge_vehicle_set set_of(const char *text) {
    FILE *f = tmpfile();
    CHECK(f != NULL);
    fputs(text, f);
    rewind(f);
    forge_vehicle_set set;
    forge_vehicles_read(f, &set);
    fclose(f);
    return set;
}
static int read_count(const char *text) {
    FILE *f = tmpfile();
    CHECK(f != NULL);
    fputs(text, f);
    rewind(f);
    forge_vehicle_set set;
    int got = forge_vehicles_read(f, &set);
    fclose(f);
    return got;
}

int main(void) {
    // The file
    CHECK(read_count("forge-vehicles 1\n") == 0);
    CHECK(read_count("forge-vehicles 1\r\nce_ghost_1\t0\r\nce_warthog_1\t-1\r\n") == 2);
    CHECK(read_count("forge-vehicles 2\n") == -1);
    CHECK(read_count("") == -1);
    CHECK(read_count("forge-vehicles 1\nno tab here\n") == -1);
    CHECK(read_count("forge-vehicles 1\n\t0\n") == -1);
    CHECK(read_count("forge-vehicles 1\nce_ghost_1\t\n") == -1);
    CHECK(read_count("forge-vehicles 1\nce_ghost_1\t9\n") == -1);
    CHECK(read_count("forge-vehicles 1\nce_ghost_1\t0 x\n") == -1);
    CHECK(read_count("forge-vehicles 1\nce_a_very_long_label_past_what_a_row_holds\t0\n") == -1);

    forge_vehicle_set set = set_of("forge-vehicles 1\nce_warthog_1\t-1\nce_ghost_1\t0\n");
    CHECK(set.count == 2);
    CHECK(set.rows[0].team == FORGE_VEHICLE_ANY_TEAM);
    CHECK(!strcmp(set.rows[1].label, "ce_ghost_1"));
    CHECK(set.rows[1].team == 0);

    // Showing them
    setup();
    CHECK(forge_vehicles_mark(mv, &set, 0) == 2);
    CHECK(props(0)[VEHICLE_PROPS_FLAGS] == 0x0c);
    CHECK(props(1)[VEHICLE_PROPS_FLAGS] == 0x2c);  // ce_warthog_10 is not ce_warthog_1
    CHECK(props(2)[VEHICLE_PROPS_FLAGS] == 0x0c);
    CHECK(props(3)[VEHICLE_PROPS_FLAGS] == 0x2c);  // a team constraint holds
    CHECK(props(4)[VEHICLE_PROPS_FLAGS] == 0x0c);
    CHECK(props(5)[VEHICLE_PROPS_FLAGS] == 0x2c);  // a free slot stays as it was
    CHECK(forge_vehicles_mark(mv, &set, 0) == 0);

    // A save puts back only what was shown, and a palette placement stays
    // visible in a match.
    CHECK(forge_vehicles_mark(mv, &set, 1) == 2);
    CHECK(props(0)[VEHICLE_PROPS_FLAGS] == 0x2c);
    CHECK(props(2)[VEHICLE_PROPS_FLAGS] == 0x2c);
    CHECK(props(4)[VEHICLE_PROPS_FLAGS] == 0x0c);

    // No rows, or a label out of range, changes nothing.
    setup();
    forge_vehicle_set none = {0};
    CHECK(forge_vehicles_mark(mv, &none, 0) == 0);
    int16_t past = 9;
    memcpy(props(0) + VEHICLE_PROPS_LABEL, &past, 2);
    CHECK(forge_vehicles_mark(mv, &set, 0) == 1);
    CHECK(props(0)[VEHICLE_PROPS_FLAGS] == 0x2c);

    // A name running off the end of the strings never reads past them.
    setup();
    memset(mv + VEHICLE_MV_LABEL_STRINGS + VEHICLE_MV_LABEL_BYTES - 4, 'c', 4);
    int16_t last = VEHICLE_MV_LABEL_BYTES - 4;
    memcpy(mv + VEHICLE_MV_LABELS, &last, 2);
    forge_vehicle_set cc = set_of("forge-vehicles 1\ncccc\t-1\n");
    CHECK(forge_vehicles_mark(mv, &cc, 0) == 0);

    printf("forge vehicles: %d checks passed\n", checks);
    return 0;
}
