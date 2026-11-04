// The limits a layout file must stay within before the game reads it: how many
// labels it has and how large their names are. This walks a payload far enough
// to read those sizes, and refuses one over a limit or one that ends before
// them. Portable: no Windows.
#ifndef MJOLNIR_LAYOUT_BOUNDS_H
#define MJOLNIR_LAYOUT_BOUNDS_H
#include <stdint.h>
#include <stddef.h>

enum { FORGE_MV_LABELS = 256, FORGE_MV_STRINGS = 0x1000 };

typedef struct {
    const uint8_t *bytes;
    size_t bits, at;
    int ended;
} forge_bit_reader;

// The next `count` bits, most significant first, as the engine's stream reads.
static uint64_t forge_read_bits(forge_bit_reader *r, int count) {
    uint64_t value = 0;
    for (int i = 0; i < count; i++) {
        if (r->at >= r->bits) {
            r->ended = 1;
            return 0;
        }
        value = value << 1 | (uint64_t)(r->bytes[r->at >> 3] >> (7 - (r->at & 7)) & 1);
        r->at++;
    }
    return value;
}

// Characters until a zero, at most `max` of them (the grammar's zstring).
static void forge_skip_zstring(forge_bit_reader *r, int char_bits, int max) {
    for (int i = 0; i < max && !r->ended; i++)
        if (forge_read_bits(r, char_bits) == 0) return;
}

// AUTHOR: timestamp, xuid, name (8-bit, 16), online flag.
static void forge_skip_author(forge_bit_reader *r) {
    forge_read_bits(r, 64);
    forge_read_bits(r, 64);
    forge_skip_zstring(r, 8, 16);
    forge_read_bits(r, 1);
}

// CONTENT_HEADER (0x38f5d0), as crates/blam-megalo/grammar/megalo_cu4.json
// lays it out.
static void forge_skip_content_header(forge_bit_reader *r) {
    int64_t content_type = (int64_t)forge_read_bits(r, 4) - 1;
    forge_read_bits(r, 32);                       // file length
    for (int i = 0; i < 4; i++) forge_read_bits(r, 64);
    forge_read_bits(r, 3);                        // activity
    uint64_t game_mode = forge_read_bits(r, 3);
    forge_read_bits(r, 3);                        // engine
    forge_read_bits(r, 32);                       // map id
    forge_read_bits(r, 8);                        // engine category
    forge_skip_author(r);
    forge_skip_author(r);
    forge_skip_zstring(r, 16, 128);               // title
    forge_skip_zstring(r, 16, 128);               // description
    if (content_type == 3 || content_type == 4) forge_read_bits(r, 32);
    else if (content_type == 6) forge_read_bits(r, 8);
    if (game_mode == 1) forge_read_bits(r, 8 + 2 + 2 + 8 + 32);
    else if (game_mode == 2) forge_read_bits(r, 2 + 32);
}

// 1 when the decoder can read `payload` within its tables; 0 and a reason
// otherwise.
static int forge_mv_bounds(const uint8_t *payload, size_t length, const char **why) {
    forge_bit_reader r = {payload, length * 8, 0, 0};
    *why = NULL;
    forge_skip_content_header(&r);
    uint64_t version = forge_read_bits(&r, 8);
    if (r.ended) {
        *why = "it ends inside its header";
        return 0;
    }
    if (version < 31) return 1;                   // the decoder stops here
    forge_read_bits(&r, 32 + 32 + 9 + 32 + 1 + 1);
    for (int i = 0; i < 8; i++) forge_read_bits(&r, 32); // bounds and two more
    uint64_t labels = forge_read_bits(&r, 9);
    if (r.ended) {
        *why = "it ends before its labels";
        return 0;
    }
    if (labels > FORGE_MV_LABELS) {
        *why = "it has more than 256 labels";
        return 0;
    }
    for (uint64_t i = 0; i < labels; i++)
        if (forge_read_bits(&r, 1)) forge_read_bits(&r, 12);
    if (labels > 0) {
        uint64_t strings = forge_read_bits(&r, 13);
        if (r.ended) {
            *why = "it ends inside its labels";
            return 0;
        }
        if (strings > FORGE_MV_STRINGS) {
            *why = "its label names exceed 4096 bytes";
            return 0;
        }
        // Compressed names carry their own size too, with the same limit.
        if (forge_read_bits(&r, 1) && forge_read_bits(&r, 13) > 3) {
            uint64_t inflated = forge_read_bits(&r, 32);
            if (r.ended) {
                *why = "it ends inside its label names";
                return 0;
            }
            if (inflated > FORGE_MV_STRINGS) {
                *why = "its compressed label names exceed 4096 bytes";
                return 0;
            }
        }
        if (r.ended) {
            *why = "it ends inside its label names";
            return 0;
        }
    }
    return 1;
}
#endif
