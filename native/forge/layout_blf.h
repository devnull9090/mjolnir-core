// Bounded BLF envelope reader. The caller validates/decodes the payload.
#ifndef MJOLNIR_LAYOUT_BLF_H
#define MJOLNIR_LAYOUT_BLF_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

static uint32_t forge_be32(const uint8_t *at) {
    return (uint32_t)at[0] << 24 | (uint32_t)at[1] << 16 | (uint32_t)at[2] << 8 | at[3];
}

static int forge_zero_padding(const uint8_t *bytes, size_t length) {
    for (size_t i = 0; i < length; i++) if (bytes[i]) return 0;
    return 1;
}

static int forge_blf_payload(const uint8_t *bytes, size_t length, uint8_t *out, int capacity, int *pack_marker) {
    *pack_marker = 0;
    size_t at = 0;
    int result = -1;
    while (at <= length && length - at >= 12) {
        uint32_t size = forge_be32(bytes + at + 4);
        if (size < 12 || size > length - at) return -1;
        if (!memcmp(bytes + at, "mvar", 4)) {
            if (result != -1 || size < 36) return -1;
            uint32_t len = forge_be32(bytes + at + 32);
            if (capacity < 0 || len > (uint32_t)capacity || len > size - 36) return -1;
            memcpy(out, bytes + at + 36, len);
            result = (int)len;
        }
        if (!memcmp(bytes + at, "fpk1", 4)) {
            if (size != 12 || *pack_marker || bytes[at + 8] != 0 || bytes[at + 9] != 1
                || bytes[at + 10] != 0 || bytes[at + 11] != 0) return -1;
            *pack_marker = 1;
        }
        if (!memcmp(bytes + at, "_eof", 4)) {
            return size >= 17 && forge_zero_padding(bytes + at + size, length - at - size) ? result : -1;
        }
        at += size;
    }
    return -1;
}
#endif
