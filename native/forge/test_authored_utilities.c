#include <stdlib.h>
#include "authored_utilities.h"
static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
static FILE *input(const char *text) {
    FILE *file = NULL;
#ifdef _MSC_VER
    CHECK(!tmpfile_s(&file));
#else
    file = tmpfile();
#endif
    CHECK(file != NULL); CHECK(fputs(text, file) >= 0); rewind(file); return file;
}
static int read_pair(const char *doors, const char *inventory) {
    FILE *a = input(doors), *b = input(inventory);
    char tags[FORGE_DOOR_MAX_DEFINITIONS][224];
    int n = forge_authored_doors_read(a, b, tags);
    if (n > 0) CHECK(!strcmp(tags[0], "objects\\mjolnir\\forge\\foundry-wide\\door_panel"));
    fclose(a); fclose(b); return n;
}
int main(void) {
    const char *door = "forge-doors 1\nobjects\\mjolnir\\forge\\foundry-wide\\door_panel\t4\t4\t8\t16\t6\t2\t4\t1\t3\n";
    const char *binding = "foundry-wide\t0.2.0\t0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\tobjects\\mjolnir\\forge\\foundry-wide\\door_panel\n";
    CHECK(read_pair(door, binding) == 1);
    CHECK(read_pair("forge-doors 1\n", binding) == 0);
    CHECK(read_pair(door, "") == -1); /* stale/uninstalled utility */
    CHECK(read_pair(door, "corrupt inventory\n") == -1);
    CHECK(read_pair("forge-doors 2\n", binding) == -1);
    CHECK(read_pair("forge-doors 1\nobjects\\mjolnir\\forge\\foundry-wide\\door_panel\t99\t4\t8\t16\t6\t2\t4\t1\t3\n", binding) == -1);
    char duplicate[1024];
    snprintf(duplicate, sizeof duplicate, "%s%s", binding, binding);
    CHECK(read_pair(door, duplicate) == -1);
    snprintf(duplicate, sizeof duplicate, "%s%s", door, strchr(door, '\n') + 1);
    CHECK(read_pair(duplicate, binding) == -1);
    CHECK(read_pair(door, "other-pack\t0.2.0\t0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\tobjects\\mjolnir\\forge\\other-pack\\door_panel\n") == -1);
    /* Exhaust all property-byte combinations: only active recognized Normal
       authored entries gain bit6; Fixed/Phased, other objects, and every
       byte of the pose/properties remain unchanged. */
    for (int active = 0; active < 2; active++) for (int known = 0; known < 2; known++)
        for (int flags = 0; flags < 256; flags++) {
            unsigned char entry[0x4c], expected[0x4c];
            memset(entry, 0xa5, sizeof entry); entry[0] = (unsigned char)active; entry[0x46] = (unsigned char)flags;
            memcpy(expected, entry, sizeof entry);
            int change = active && known && !(flags & 0xc0);
            if (change) expected[0x46] |= 0x40;
            CHECK(forge_authored_door_fixed(entry, known) == change);
            CHECK(!memcmp(entry, expected, sizeof entry));
            CHECK(!forge_authored_door_fixed(entry, known)); /* idempotent */
        }
    printf("Forge authored utility defaults: %d checks passed\n", checks);
    return 0;
}
