#ifndef MJOLNIR_FORGE_AUTHORED_UTILITIES_H
#define MJOLNIR_FORGE_AUTHORED_UTILITIES_H
#include <stdio.h>
#include "pack_bindings.h"
#include "../lobby/forge_doors_core.h"

/* Read the same bounded door contract as Lobby, accepting only current
   installed identities. Called at authored-scenario construction, never per
   frame and never while decoding or adopting somebody's saved layout. */
static inline int forge_authored_doors_read(FILE *doors, FILE *inventory,
                                          char tags[FORGE_DOOR_MAX_DEFINITIONS][224]) {
    char line[768];
    int count = 0, rows = 0, matches[FORGE_DOOR_MAX_DEFINITIONS] = {0};
    if (!doors || !inventory || !fgets(line, sizeof line, doors)
        || (strcmp(line, "forge-doors 1\n") && strcmp(line, "forge-doors 1\r\n"))) return -1;
    while (fgets(line, sizeof line, doors)) {
        forge_door_config config;
        if (count == FORGE_DOOR_MAX_DEFINITIONS || (!strchr(line, '\n') && !feof(doors))
            || !forge_door_parse(line, &config)) return -1;
        for (int i = 0; i < count; i++) if (!strcmp(tags[i], config.tag)) return -1;
        memcpy(tags[count++], config.tag, strlen(config.tag) + 1);
    }
    if (ferror(doors)) return -1;
    while (fgets(line, sizeof line, inventory)) {
        forge_pack_binding binding;
        if (++rows > 4096 || (!strchr(line, '\n') && !feof(inventory))
            || !forge_binding_parse(line, 0, &binding)) return -1;
        for (int i = 0; i < count; i++) if (!strcmp(tags[i], binding.tag)) matches[i]++;
    }
    if (ferror(inventory)) return -1;
    for (int i = 0; i < count; i++) if (matches[i] != 1) return -1;
    return count;
}

/* Scenario construction supplies Normal even for fixed crate tags. Seed only
   recognized active authored panels; preserve all other properties and any
   explicit Fixed/Phased mode. Saved variants never pass through this helper. */
static inline int forge_authored_door_fixed(unsigned char *entry, int door) {
    if (!door || !(entry[0] & 1) || (entry[0x46] & 0xc0)) return 0;
    entry[0x46] |= 0x40;
    return 1;
}
#endif
