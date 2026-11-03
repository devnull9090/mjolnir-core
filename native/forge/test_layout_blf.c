#include <stdio.h>
#include <stdlib.h>
#include "layout_blf.h"
static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
static void be32(uint8_t *at, uint32_t value) {
    at[0] = (uint8_t)(value >> 24); at[1] = (uint8_t)(value >> 16);
    at[2] = (uint8_t)(value >> 8); at[3] = (uint8_t)value;
}
static size_t chunk(uint8_t *bytes, size_t at, const char *name, uint32_t size, int major) {
    memset(bytes + at, 0, size); memcpy(bytes + at, name, 4);
    be32(bytes + at + 4, size); bytes[at + 9] = (uint8_t)major;
    return at + size;
}
static size_t fixture(uint8_t *bytes, int marker) {
    size_t at = chunk(bytes, 0, "_blf", 48, 1);
    size_t mv = at;
    at = chunk(bytes, at, "mvar", 40, 31);
    be32(bytes + mv + 32, 4); memcpy(bytes + mv + 36, "test", 4);
    if (marker) at = chunk(bytes, at, "fpk1", 12, 1);
    return chunk(bytes, at, "_eof", 17, 1);
}
int main(void) {
    uint8_t bytes[1024] = {0}, out[8]; int marker;
    for (int marked = 0; marked <= 1; marked++) {
        size_t size = fixture(bytes, marked);
        CHECK(forge_blf_payload(bytes, size, out, sizeof out, &marker) == 4);
        CHECK(marker == marked && !memcmp(out, "test", 4));
        memset(bytes + size, 0, sizeof bytes - size);
        CHECK(forge_blf_payload(bytes, sizeof bytes, out, sizeof out, &marker) == 4);
        CHECK(marker == marked);
        bytes[sizeof bytes - 1] = 1;
        CHECK(forge_blf_payload(bytes, sizeof bytes, out, sizeof out, &marker) == -1);
        CHECK(forge_blf_payload(bytes, size - 1, out, sizeof out, &marker) == -1);
        CHECK(forge_blf_payload(bytes, size, out, 3, &marker) == -1);
    }
    size_t size = fixture(bytes, 1);
    bytes[88 + 9] = 2;
    CHECK(forge_blf_payload(bytes, size, out, sizeof out, &marker) == -1);
    size = fixture(bytes, 1);
    be32(bytes + 88 + 4, 13);
    CHECK(forge_blf_payload(bytes, size, out, sizeof out, &marker) == -1);
    size = fixture(bytes, 1);
    size = chunk(bytes, size - 17, "fpk1", 12, 1);
    size = chunk(bytes, size, "_eof", 17, 1);
    CHECK(forge_blf_payload(bytes, size, out, sizeof out, &marker) == -1);
    size = fixture(bytes, 0);
    size_t duplicate = size - 17;
    size = chunk(bytes, duplicate, "mvar", 40, 31);
    be32(bytes + duplicate + 32, 4);
    size = chunk(bytes, size, "_eof", 17, 1);
    CHECK(forge_blf_payload(bytes, size, out, sizeof out, &marker) == -1);
    size = fixture(bytes, 0);
    be32(bytes + 48 + 32, 0xffffffffu);
    CHECK(forge_blf_payload(bytes, size, out, sizeof out, &marker) == -1);
    // A previous marked read must not leak marker state into a legacy file.
    size = fixture(bytes, 0); marker = 1;
    CHECK(forge_blf_payload(bytes, size, out, sizeof out, &marker) == 4 && marker == 0);
    printf("Forge layout BLF envelopes: %d checks passed\n", checks);
    return 0;
}
