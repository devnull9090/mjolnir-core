// What a FORGE game shows of a converted map's own vehicles. Independent of
// Windows and the game.
//
// A converted map places them hidden, and a match reveals them with label
// filters on its variant (MJOLNIRLevelLoader's vehicle_sets.lua). The sandbox
// builds a variant of its own, so nothing does, though its map variant lists
// them all with the hidden bit set. The loader writes the labels a Slayer game
// would place to forge_vehicles.txt; the bit comes off those entries while a
// Forge game runs and goes back on in what a save writes, since a saved layout
// replaces the map's own in every game and the host's vehicle sets must still
// decide there.
#ifndef MJOLNIR_FORGE_VEHICLES_H
#define MJOLNIR_FORGE_VEHICLES_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Far more than a variant's 16 filters, so a real file never runs out.
#define FORGE_VEHICLE_ROWS 32
#define FORGE_VEHICLE_LABEL 32
#define FORGE_VEHICLE_ANY_TEAM (-1)

// The map variant, as mjolnir_forge.c reads it.
#define VEHICLE_MV_LABEL_STRINGS 0x2f4
#define VEHICLE_MV_LABEL_BYTES 0x1000
#define VEHICLE_MV_LABELS 0x12f8
#define VEHICLE_MV_LABEL_COUNT 0x14f8
#define VEHICLE_MV_ENTRY_TABLE 0x14fc
#define VEHICLE_MV_ENTRY_STRIDE 0x4c
#define VEHICLE_MV_ENTRY_COUNT 651
#define VEHICLE_MV_ENTRY_PROPS 0x30
#define VEHICLE_PROPS_LABEL 0x14
#define VEHICLE_PROPS_FLAGS 0x16
#define VEHICLE_PROPS_TEAM 0x17
// "Hide unless Megalo required": a palette placement reads 0x0c, a converted
// map's vehicle 0x2c, and only the first is created without a filter.
#define VEHICLE_PROPS_HIDDEN 0x20

typedef struct {
    char label[FORGE_VEHICLE_LABEL];
    int team;  // FORGE_VEHICLE_ANY_TEAM, or the only team that takes the label
} forge_vehicle_row;

typedef struct {
    int count;
    forge_vehicle_row rows[FORGE_VEHICLE_ROWS];
} forge_vehicle_set;

// One `label<TAB>team` line. 1 when it reads.
static inline int forge_vehicle_parse(const char *line, forge_vehicle_row *row) {
    const char *tab = strchr(line, '\t');
    if (!tab || tab == line || (size_t)(tab - line) >= FORGE_VEHICLE_LABEL) return 0;
    char *end = NULL;
    long team = strtol(tab + 1, &end, 10);
    if (end == tab + 1 || team < FORGE_VEHICLE_ANY_TEAM || team > 8) return 0;
    while (*end == '\r' || *end == '\n') end++;
    if (*end) return 0;
    memcpy(row->label, line, (size_t)(tab - line));
    row->label[tab - line] = '\0';
    row->team = (int)team;
    return 1;
}

// `forge-vehicles 1`, then a row a line. The rows read, or -1 for a file that is
// not this: a Forge game then shows what it did before.
static inline int forge_vehicles_read(FILE *f, forge_vehicle_set *set) {
    char line[128];
    set->count = 0;
    if (!f || !fgets(line, sizeof line, f)
        || (strcmp(line, "forge-vehicles 1\n") && strcmp(line, "forge-vehicles 1\r\n"))) return -1;
    while (fgets(line, sizeof line, f)) {
        if (set->count == FORGE_VEHICLE_ROWS || (!strchr(line, '\n') && !feof(f))
            || !forge_vehicle_parse(line, &set->rows[set->count])) {
            set->count = 0;
            return -1;
        }
        set->count++;
    }
    if (ferror(f)) {
        set->count = 0;
        return -1;
    }
    return set->count;
}

static inline int forge_vehicle_wanted(const forge_vehicle_set *set, const char *label, size_t room, int team) {
    for (int i = 0; i < set->count; i++) {
        const forge_vehicle_row *row = &set->rows[i];
        size_t size = strlen(row->label) + 1;
        if (size <= room && !memcmp(row->label, label, size)
            && (row->team == FORGE_VEHICLE_ANY_TEAM || row->team == team)) return 1;
    }
    return 0;
}

// Set the hidden bit (`hide`) or clear it on every entry the set names. Returns
// how many changed.
static inline int forge_vehicles_mark(uint8_t *mv, const forge_vehicle_set *set, int hide) {
    int labels = *(const int32_t *)(mv + VEHICLE_MV_LABEL_COUNT), changed = 0;
    for (int i = 0; i < VEHICLE_MV_ENTRY_COUNT; i++) {
        uint8_t *entry = mv + VEHICLE_MV_ENTRY_TABLE + (size_t)i * VEHICLE_MV_ENTRY_STRIDE;
        if (!(entry[0] & 1)) continue;
        uint8_t *props = entry + VEHICLE_MV_ENTRY_PROPS;
        int16_t label;
        memcpy(&label, props + VEHICLE_PROPS_LABEL, sizeof label);
        if (label < 0 || label >= labels) continue;
        int16_t at;
        memcpy(&at, mv + VEHICLE_MV_LABELS + (size_t)label * 2, sizeof at);
        if (at < 0 || at >= VEHICLE_MV_LABEL_BYTES) continue;
        const char *name = (const char *)(mv + VEHICLE_MV_LABEL_STRINGS + at);
        if (!forge_vehicle_wanted(set, name, (size_t)(VEHICLE_MV_LABEL_BYTES - at), props[VEHICLE_PROPS_TEAM])) continue;
        uint8_t was = props[VEHICLE_PROPS_FLAGS];
        uint8_t now = hide ? (uint8_t)(was | VEHICLE_PROPS_HIDDEN) : (uint8_t)(was & ~VEHICLE_PROPS_HIDDEN);
        props[VEHICLE_PROPS_FLAGS] = now;
        changed += now != was;
    }
    return changed;
}

#endif
