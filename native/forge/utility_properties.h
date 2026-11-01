#ifndef MJOLNIR_FORGE_UTILITY_PROPERTIES_H
#define MJOLNIR_FORGE_UTILITY_PROPERTIES_H
#include <stdint.h>
#include <string.h>

/* Reach's 28-byte multiplayer property block. Shape dimensions are Blam
   world units (3.048 m), channel is a five-bit field in the saved codec. */
static int forge_is_teleporter(const uint8_t *props) {
    return props[0x13] >= 12 && props[0x13] <= 14;
}
static const char *forge_channel_name(unsigned channel) {
    static const char *names[] = {
        "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
        "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa",
        "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey", "xray",
        "yankee", "zulu", "26", "27", "28", "29", "30", "31"
    };
    return channel < 32 ? names[channel] : "invalid";
}
static int forge_next_channel(uint8_t *props) {
    if (!forge_is_teleporter(props)) return 0;
    props[0x18] = (uint8_t)((props[0x18] + 1u) % 32u);
    return 1;
}
/* Only new Insert placements get these defaults. A moved, duplicated or
   loaded teleporter keeps its original shape/channel/passability exactly. */
static int forge_teleporter_defaults(uint8_t *props) {
    const float shape[4] = {0.35f, 0.35f, 0.6f, 0.1f};
    if (!forge_is_teleporter(props)) return 0;
    memcpy(props, shape, sizeof shape);
    props[0x10] = 2; /* cylinder */
    props[0x18] = 0; /* alpha */
    props[0x19] = 0; /* players allowed; vehicles/projectiles excluded */
    return 1;
}
#endif
