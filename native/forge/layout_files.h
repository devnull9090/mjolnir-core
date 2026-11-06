// Two-file layout commits, independent of Windows and the game. Moves never
// overwrite a destination. A rollback failure leaves prior bytes in history
// and reports recovery needed instead of claiming that the save succeeded.
#ifndef MJOLNIR_LAYOUT_FILES_H
#define MJOLNIR_LAYOUT_FILES_H

typedef struct {
    void *context;
    int (*exists)(void *, const char *); // 1 file, 0 absent, -1 inaccessible
    int (*move)(void *, const char *, const char *); // no overwrite
    int (*remove)(void *, const char *);
} forge_file_ops;

enum { FORGE_FILES_RECOVERY = -1, FORGE_FILES_FAILED = 0, FORGE_FILES_OK = 1 };

static int forge_restore_pair(const forge_file_ops *ops, const char *map, const char *side,
                              const char *history_map, const char *history_side, unsigned old) {
    // The .mvar becomes visible only after its matching sidecar is in place.
    if ((old & 2) && !ops->move(ops->context, history_side, side)) return FORGE_FILES_RECOVERY;
    if ((old & 1) && !ops->move(ops->context, history_map, map)) return FORGE_FILES_RECOVERY;
    return FORGE_FILES_FAILED;
}

static int forge_retire_pair(const forge_file_ops *ops, const char *map, const char *side,
                             const char *history_map, const char *history_side, unsigned *old) {
    int have_map = ops->exists(ops->context, map), have_side = ops->exists(ops->context, side);
    *old = 0;
    if (have_map < 0 || have_side < 0) return FORGE_FILES_FAILED;
    *old = (have_map ? 1u : 0u) | (have_side ? 2u : 0u);
    if (!*old) return FORGE_FILES_OK;
    if (ops->exists(ops->context, history_map) != 0 || ops->exists(ops->context, history_side) != 0)
        return FORGE_FILES_FAILED;
    if (have_map && !ops->move(ops->context, map, history_map)) return FORGE_FILES_FAILED;
    if (have_side && !ops->move(ops->context, side, history_side)) {
        if (have_map && !ops->move(ops->context, history_map, map)) return FORGE_FILES_RECOVERY;
        return FORGE_FILES_FAILED;
    }
    return FORGE_FILES_OK;
}

// Bring a retired pair back as the active one. It never replaces an active
// file, and a save from before .packs existed comes back alone.
static int forge_unretire_pair(const forge_file_ops *ops, const char *map, const char *side,
                               const char *history_map, const char *history_side) {
    int have_map = ops->exists(ops->context, history_map), have_side = ops->exists(ops->context, history_side);
    if (have_map != 1 || have_side < 0) return FORGE_FILES_FAILED;
    if (ops->exists(ops->context, map) != 0 || ops->exists(ops->context, side) != 0) return FORGE_FILES_FAILED;
    // The .mvar becomes visible only after its matching sidecar is in place.
    if (have_side && !ops->move(ops->context, history_side, side)) return FORGE_FILES_FAILED;
    if (!ops->move(ops->context, history_map, map)) {
        if (have_side && !ops->move(ops->context, side, history_side)) return FORGE_FILES_RECOVERY;
        return FORGE_FILES_FAILED;
    }
    return FORGE_FILES_OK;
}

static int forge_publish_pair(const forge_file_ops *ops, const char *map, const char *side,
                              const char *staged_map, const char *staged_side,
                              const char *history_map, const char *history_side) {
    if (ops->exists(ops->context, staged_map) != 1 || ops->exists(ops->context, staged_side) != 1)
        return FORGE_FILES_FAILED;
    unsigned old;
    int retired = forge_retire_pair(ops, map, side, history_map, history_side, &old);
    if (retired != FORGE_FILES_OK) return retired;
    if (!ops->move(ops->context, staged_side, side))
        return forge_restore_pair(ops, map, side, history_map, history_side, old);
    if (!ops->move(ops->context, staged_map, map)) {
        if (!ops->remove(ops->context, side)) return FORGE_FILES_RECOVERY;
        return forge_restore_pair(ops, map, side, history_map, history_side, old);
    }
    return FORGE_FILES_OK;
}
#endif
