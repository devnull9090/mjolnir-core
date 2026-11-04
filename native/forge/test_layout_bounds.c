#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "layout_blf.h"
#include "layout_bounds.h"
static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

typedef struct { uint8_t bytes[4096]; size_t at; } writer;
static void put(writer *w, uint64_t value, int count) {
    for (int i = count - 1; i >= 0; i--, w->at++)
        if (value >> i & 1) w->bytes[w->at >> 3] |= (uint8_t)(0x80 >> (w->at & 7));
}
static void zstring(writer *w, const char *text, int char_bits) {
    for (; *text; text++) put(w, (uint8_t)*text, char_bits);
    put(w, 0, char_bits);
}
static void author(writer *w, const char *name) {
    put(w, 0, 64); put(w, 0, 64); zstring(w, name, 8); put(w, 0, 1);
}
// A map variant payload as the engine writes one, up to its label strings:
// plain (`compressed` < 0), or a zlib stream of `compressed` bytes whose
// big-endian prefix says it inflates to `inflated`.
static size_t payload_names(writer *w, int content_type, int game_mode, int version,
                            int labels, int present, int strings, int compressed,
                            uint32_t inflated) {
    memset(w, 0, sizeof *w);
    put(w, (uint64_t)content_type + 1, 4);
    put(w, 0, 32);
    for (int i = 0; i < 4; i++) put(w, 0, 64);
    put(w, 0, 3); put(w, (uint64_t)game_mode, 3); put(w, 0, 3);
    put(w, 0, 32); put(w, 0, 8);
    author(w, "spartan"); author(w, "");
    zstring(w, "Crossline", 16); zstring(w, "", 16);
    if (content_type == 3 || content_type == 4) put(w, 0, 32);
    else if (content_type == 6) put(w, 0, 8);
    if (game_mode == 1) put(w, 0, 52);
    else if (game_mode == 2) put(w, 0, 34);
    put(w, (uint64_t)version, 8);
    if (version >= 31) {
        put(w, 0, 32); put(w, 0, 32); put(w, 0, 9); put(w, 0, 32); put(w, 0, 2);
        for (int i = 0; i < 8; i++) put(w, 0, 32);
        put(w, (uint64_t)labels, 9);
        for (int i = 0; i < labels; i++) {
            put(w, present, 1);
            if (present) put(w, (uint64_t)i & 0xfff, 12);
        }
        if (labels > 0) {
            put(w, (uint64_t)strings, 13);
            put(w, compressed >= 0, 1);
            if (compressed >= 0) {
                put(w, (uint64_t)compressed, 13);
                if (compressed > 3) put(w, inflated, 32);
            }
        }
    }
    return (w->at + 7) / 8 + 64;                  // objects and more follow
}
static size_t payload(writer *w, int content_type, int game_mode, int version,
                      int labels, int present, int strings) {
    return payload_names(w, content_type, game_mode, version, labels, present, strings, -1, 0);
}

static int ok(writer *w, size_t length) {
    const char *why;
    int result = forge_mv_bounds(w->bytes, length, &why);
    CHECK(result ? why == NULL : why != NULL);
    return result;
}

// Optional: check real files, e.g. a game's layouts\history folder's .mvar.
static int check_files(int argc, char **argv) {
    static uint8_t file[1 << 20], out[1 << 16];
    int failed = 0;
    for (int i = 1; i < argc; i++) {
        FILE *f = fopen(argv[i], "rb");
        if (!f) { fprintf(stderr, "%s: cannot open\n", argv[i]); failed = 1; continue; }
        size_t n = fread(file, 1, sizeof file, f);
        fclose(f);
        int marker, len = forge_blf_payload(file, n, out, (int)sizeof out, &marker);
        const char *why = "not a map variant file";
        int pass = len > 0 && forge_mv_bounds(out, (size_t)len, &why);
        printf("%s %s%s%s\n", pass ? "ok     " : "REFUSED", argv[i], pass ? "" : ": ", pass ? "" : why);
        failed |= !pass;
    }
    return failed;
}

int main(int argc, char **argv) {
    if (argc > 1) return check_files(argc, argv);
    writer w;
    // Ordinary layouts, every header branch, with and without labels.
    for (int type = -1; type <= 14; type++)
        for (int mode = 0; mode <= 7; mode++)
            CHECK(ok(&w, payload(&w, type, mode, 31, 3, 1, 40)));
    CHECK(ok(&w, payload(&w, 5, 4, 31, 0, 0, 0)));
    // The decoder's own limits are accepted exactly.
    CHECK(ok(&w, payload(&w, 5, 4, 31, 256, 1, 4096)));
    CHECK(ok(&w, payload(&w, 5, 4, 31, 256, 0, 4096)));
    // One more of either is refused, present or absent labels alike.
    CHECK(!ok(&w, payload(&w, 5, 4, 31, 257, 0, 0)));
    CHECK(!ok(&w, payload(&w, 5, 4, 31, 258, 1, 0)));
    CHECK(!ok(&w, payload(&w, 5, 4, 31, 511, 1, 0)));
    CHECK(!ok(&w, payload(&w, 5, 4, 31, 4, 1, 4097)));
    CHECK(!ok(&w, payload(&w, 5, 4, 31, 4, 0, 8191)));
    // Compressed names: the inflater's limit is the stream's own prefix, not
    // the declared size, so the prefix is what is capped.
    CHECK(ok(&w, payload_names(&w, 5, 4, 31, 4, 1, 100, 40, 4096)));
    CHECK(!ok(&w, payload_names(&w, 5, 4, 31, 4, 1, 100, 40, 4097)));
    CHECK(!ok(&w, payload_names(&w, 5, 4, 31, 4, 1, 100, 40, 0xffffffffu)));
    CHECK(ok(&w, payload_names(&w, 5, 4, 31, 4, 1, 100, 3, 0)));    // no prefix: inflates nothing
    size_t named = payload_names(&w, 5, 4, 31, 4, 1, 100, 40, 4096) - 64;
    CHECK(!ok(&w, named - 2));                    // cut inside the prefix
    // Below version 31 the decoder reads nothing more.
    CHECK(ok(&w, payload(&w, 5, 4, 30, 511, 1, 8191)));
    // A payload that ends before the counts is refused, not guessed at.
    size_t written = payload(&w, 5, 4, 31, 2, 1, 10) - 64;
    int reads = 0;
    for (size_t cut = 0; cut <= written; cut++) {
        int result = ok(&w, cut);
        CHECK(!reads || result);                  // longer never fails again
        reads |= result;
    }
    CHECK(reads && !ok(&w, 0) && !ok(&w, written / 2));
    // Long strings stop at the grammar's maximum: a 128-character title with
    // no terminator does not swallow the fields after it.
    memset(&w, 0, sizeof w);
    put(&w, 6, 4); put(&w, 0, 32); for (int i = 0; i < 4; i++) put(&w, 0, 64);
    put(&w, 0, 9); put(&w, 0, 32); put(&w, 0, 8);
    author(&w, ""); author(&w, "");
    for (int i = 0; i < 128; i++) put(&w, 'x', 16);
    zstring(&w, "", 16);
    put(&w, 31, 8);
    put(&w, 0, 107); for (int i = 0; i < 8; i++) put(&w, 0, 32);
    put(&w, 300, 9);
    CHECK(!ok(&w, (w.at + 7) / 8 + 64));
    printf("Forge layout decoder bounds: %d checks passed\n", checks);
    return 0;
}
