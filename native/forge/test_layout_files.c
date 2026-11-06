// Failure-injection checks of the same transaction code used by F5/F2.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "layout_files.h"

enum { MAP, SIDE, STAGED_MAP, STAGED_SIDE, HISTORY_MAP, HISTORY_SIDE, FILES };
enum { EMPTY, OLD_MAP, OLD_SIDE, NEW_MAP, NEW_SIDE, PRIOR_HISTORY };
static const char *names[] = { "map", "side", "staged-map", "staged-side", "history-map", "history-side" };
static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
typedef struct { int files[FILES]; unsigned failed_ops, op; } fake_fs;

static int index_of(const char *name) {
    for (int i = 0; i < FILES; i++) if (!strcmp(name, names[i])) return i;
    abort();
}
static int exists(void *context, const char *name) { return ((fake_fs *)context)->files[index_of(name)] != EMPTY; }
static int blocked(fake_fs *fs) { fs->op++; return (fs->failed_ops & (1u << fs->op)) != 0; }
static int move(void *context, const char *from, const char *to) {
    fake_fs *fs = context;
    int source = index_of(from), target = index_of(to);
    if (blocked(fs) || !fs->files[source] || fs->files[target]) return 0;
    fs->files[target] = fs->files[source]; fs->files[source] = EMPTY;
    return 1;
}
static int remove_file(void *context, const char *name) {
    fake_fs *fs = context;
    if (blocked(fs) || !fs->files[index_of(name)]) return 0;
    fs->files[index_of(name)] = EMPTY;
    return 1;
}
static forge_file_ops ops_for(fake_fs *fs) {
    forge_file_ops ops = {fs, exists, move, remove_file}; return ops;
}
static fake_fs initial(unsigned failed_ops, int legacy) {
    fake_fs fs = {{OLD_MAP, OLD_SIDE, NEW_MAP, NEW_SIDE, EMPTY, EMPTY}, failed_ops, 0};
    if (legacy) fs.files[SIDE] = EMPTY;
    return fs;
}
static int publish(fake_fs *fs) {
    forge_file_ops ops = ops_for(fs);
    return forge_publish_pair(&ops, names[MAP], names[SIDE], names[STAGED_MAP], names[STAGED_SIDE], names[HISTORY_MAP], names[HISTORY_SIDE]);
}
static int count_bytes(const fake_fs *fs, int content) {
    int count = 0; for (int i = 0; i < FILES; i++) count += fs->files[i] == content; return count;
}
static void old_bytes_survive(const fake_fs *fs) {
    CHECK(count_bytes(fs, OLD_MAP) == 1);
    CHECK(count_bytes(fs, OLD_SIDE) == 1);
}

int main(void) {
    fake_fs fs = initial(0, 0);
    CHECK(publish(&fs) == FORGE_FILES_OK);
    CHECK(fs.files[MAP] == NEW_MAP && fs.files[SIDE] == NEW_SIDE);
    CHECK(fs.files[HISTORY_MAP] == OLD_MAP && fs.files[HISTORY_SIDE] == OLD_SIDE);
    old_bytes_survive(&fs);
    // Existing history can never be overwritten, even for two quick saves.
    fs.files[STAGED_MAP] = NEW_MAP; fs.files[STAGED_SIDE] = NEW_SIDE;
    CHECK(publish(&fs) == FORGE_FILES_FAILED);
    CHECK(fs.files[MAP] == NEW_MAP && fs.files[SIDE] == NEW_SIDE);
    old_bytes_survive(&fs);

    // Every ordinary failure leaves the previous active pair usable.
    for (unsigned op = 1; op <= 4; op++) {
        fs = initial(1u << op, 0);
        CHECK(publish(&fs) == FORGE_FILES_FAILED);
        CHECK(fs.files[MAP] == OLD_MAP && fs.files[SIDE] == OLD_SIDE);
        CHECK(fs.files[HISTORY_MAP] == EMPTY && fs.files[HISTORY_SIDE] == EMPTY);
        old_bytes_survive(&fs);
    }
    // If rollback also fails, report recovery and never discard old bytes.
    const unsigned double_failures[] = {(1u << 2) | (1u << 3), (1u << 4) | (1u << 5),
                                       (1u << 4) | (1u << 6), (1u << 4) | (1u << 7)};
    for (unsigned i = 0; i < sizeof double_failures / sizeof *double_failures; i++) {
        fs = initial(double_failures[i], 0);
        CHECK(publish(&fs) == FORGE_FILES_RECOVERY);
        CHECK(fs.files[MAP] == EMPTY); // never expose mismatched active data
        old_bytes_survive(&fs);
    }
    // Old layouts without sidecars remain recoverable on every commit failure.
    for (unsigned op = 1; op <= 3; op++) {
        fs = initial(1u << op, 1);
        CHECK(publish(&fs) == FORGE_FILES_FAILED);
        CHECK(fs.files[MAP] == OLD_MAP && fs.files[SIDE] == EMPTY);
        CHECK(count_bytes(&fs, OLD_MAP) == 1);
    }
    fs = initial(0, 0); fs.files[STAGED_SIDE] = EMPTY;
    CHECK(publish(&fs) == FORGE_FILES_FAILED && fs.op == 0);
    CHECK(fs.files[MAP] == OLD_MAP && fs.files[SIDE] == OLD_SIDE);
    fs = initial(0, 0); fs.files[MAP] = fs.files[SIDE] = EMPTY;
    CHECK(publish(&fs) == FORGE_FILES_OK);
    CHECK(fs.files[MAP] == NEW_MAP && fs.files[SIDE] == NEW_SIDE);

    for (unsigned op = 0; op <= 2; op++) {
        fs = initial(op ? 1u << op : 0, 0);
        forge_file_ops ops = ops_for(&fs);
        unsigned old;
        int result = forge_retire_pair(&ops, names[MAP], names[SIDE], names[HISTORY_MAP], names[HISTORY_SIDE], &old);
        CHECK(old == 3);
        if (!op) {
            CHECK(result == FORGE_FILES_OK && fs.files[MAP] == EMPTY && fs.files[SIDE] == EMPTY);
        } else {
            CHECK(result == FORGE_FILES_FAILED && fs.files[MAP] == OLD_MAP && fs.files[SIDE] == OLD_SIDE);
        }
        old_bytes_survive(&fs);
    }

    // F6 brings a retired pair back, the sidecar first.
    fake_fs back = {{EMPTY, EMPTY, EMPTY, EMPTY, OLD_MAP, OLD_SIDE}, 0, 0};
    forge_file_ops back_ops = ops_for(&back);
    CHECK(forge_unretire_pair(&back_ops, names[MAP], names[SIDE], names[HISTORY_MAP], names[HISTORY_SIDE]) == FORGE_FILES_OK);
    CHECK(back.files[MAP] == OLD_MAP && back.files[SIDE] == OLD_SIDE);
    CHECK(back.files[HISTORY_MAP] == EMPTY && back.files[HISTORY_SIDE] == EMPTY);
    // A save from before sidecars comes back alone.
    back = (fake_fs){{EMPTY, EMPTY, EMPTY, EMPTY, OLD_MAP, EMPTY}, 0, 0};
    back_ops = ops_for(&back);
    CHECK(forge_unretire_pair(&back_ops, names[MAP], names[SIDE], names[HISTORY_MAP], names[HISTORY_SIDE]) == FORGE_FILES_OK);
    CHECK(back.files[MAP] == OLD_MAP && back.files[SIDE] == EMPTY);
    // A sidecar with no layout is nothing to restore.
    back = (fake_fs){{EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, OLD_SIDE}, 0, 0};
    back_ops = ops_for(&back);
    CHECK(forge_unretire_pair(&back_ops, names[MAP], names[SIDE], names[HISTORY_MAP], names[HISTORY_SIDE]) == FORGE_FILES_FAILED);
    CHECK(back.op == 0 && back.files[HISTORY_SIDE] == OLD_SIDE);
    // An active file is never replaced, whichever half of the pair it is.
    for (int active = MAP; active <= SIDE; active++) {
        back = (fake_fs){{EMPTY, EMPTY, EMPTY, EMPTY, OLD_MAP, OLD_SIDE}, 0, 0};
        back.files[active] = NEW_MAP;
        back_ops = ops_for(&back);
        CHECK(forge_unretire_pair(&back_ops, names[MAP], names[SIDE], names[HISTORY_MAP], names[HISTORY_SIDE]) == FORGE_FILES_FAILED);
        CHECK(back.op == 0);
        old_bytes_survive(&back);
    }
    // A failed move leaves history as it was, or reports recovery with every byte kept.
    for (unsigned op = 1; op <= 2; op++) {
        back = (fake_fs){{EMPTY, EMPTY, EMPTY, EMPTY, OLD_MAP, OLD_SIDE}, 1u << op, 0};
        back_ops = ops_for(&back);
        CHECK(forge_unretire_pair(&back_ops, names[MAP], names[SIDE], names[HISTORY_MAP], names[HISTORY_SIDE]) == FORGE_FILES_FAILED);
        CHECK(back.files[HISTORY_MAP] == OLD_MAP && back.files[HISTORY_SIDE] == OLD_SIDE);
        CHECK(back.files[MAP] == EMPTY && back.files[SIDE] == EMPTY);
    }
    back = (fake_fs){{EMPTY, EMPTY, EMPTY, EMPTY, OLD_MAP, OLD_SIDE}, (1u << 2) | (1u << 3), 0};
    back_ops = ops_for(&back);
    CHECK(forge_unretire_pair(&back_ops, names[MAP], names[SIDE], names[HISTORY_MAP], names[HISTORY_SIDE]) == FORGE_FILES_RECOVERY);
    CHECK(back.files[MAP] == EMPTY); // never expose mismatched active data
    old_bytes_survive(&back);
    printf("Forge layout transactions: %d checks passed\n", checks);
    return 0;
}
