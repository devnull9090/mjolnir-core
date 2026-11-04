#include <stdio.h>
#include <stdlib.h>
#include "utility_properties.h"
static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
int main(void) {
    uint8_t props[28], before[28];
    for (int type = 0; type < 256; type++) {
        memset(props, 0xa5, sizeof props); props[0x13] = (uint8_t)type;
        memcpy(before, props, sizeof props);
        int teleporter = type >= 12 && type <= 14;
        CHECK(forge_teleporter_defaults(props) == teleporter);
        if (!teleporter) { CHECK(!memcmp(props, before, sizeof props)); CHECK(!forge_next_channel(props)); continue; }
        float shape[4]; memcpy(shape, props, sizeof shape);
        CHECK(shape[0] == 0.35f && shape[1] == 0.35f && shape[2] == 0.6f && shape[3] == 0.1f);
        CHECK(props[0x10] == 2 && props[0x18] == 0 && props[0x19] == 0);
        CHECK(!memcmp(props + 0x11, before + 0x11, 7));
        CHECK(!memcmp(props + 0x1a, before + 0x1a, 2));
        memcpy(before, props, sizeof props);
        for (int channel = 1; channel <= 32; channel++) {
            CHECK(forge_next_channel(props)); CHECK(props[0x18] == channel % 32);
            before[0x18] = props[0x18]; CHECK(!memcmp(props, before, sizeof props));
        }
        props[0x18] = 255; CHECK(forge_next_channel(props) && props[0x18] == 0);
    }
    CHECK(!strcmp(forge_channel_name(0), "alpha"));
    CHECK(!strcmp(forge_channel_name(25), "zulu"));
    CHECK(!strcmp(forge_channel_name(31), "31"));
    CHECK(!strcmp(forge_channel_name(32), "invalid"));
    printf("Forge utility properties: %d checks passed\n", checks);
    return 0;
}
