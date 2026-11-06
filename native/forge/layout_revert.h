// Going back to a map's own layout takes a second press, and history names
// say which retired save is newest. Independent of Windows and the game.
#ifndef MJOLNIR_LAYOUT_REVERT_H
#define MJOLNIR_LAYOUT_REVERT_H

#include <stdint.h>
#include <string.h>

// Longer than the toast that asks, so the question never outlives its answer.
#define FORGE_CONFIRM_WINDOW_MS 4000u
// Key repeat and an accidental double tap are not a decision. Each press this
// close to the last one restarts the gap, so holding the key never confirms.
#define FORGE_CONFIRM_MIN_GAP_MS 300u

typedef struct {
    uint64_t last;
    int armed;
} forge_confirm;

enum { FORGE_CONFIRM_IGNORED, FORGE_CONFIRM_ASK, FORGE_CONFIRM_DONE };

static int forge_confirm_press(forge_confirm *confirm, uint64_t now) {
    uint64_t gap = now - confirm->last;
    if (!confirm->armed || gap > FORGE_CONFIRM_WINDOW_MS) {
        confirm->armed = 1;
        confirm->last = now;
        return FORGE_CONFIRM_ASK;
    }
    if (gap < FORGE_CONFIRM_MIN_GAP_MS) {
        confirm->last = now;
        return FORGE_CONFIRM_IGNORED;
    }
    confirm->armed = 0;
    return FORGE_CONFIRM_DONE;
}

typedef struct {
    uint64_t time; // YYYYMMDDHHMMSSmmm
    unsigned serial;
} forge_history_stamp;

static const char *forge_history_digits(const char *at, int count, uint64_t *value) {
    for (int i = 0; i < count; i++, at++) {
        if (*at < '0' || *at > '9') return NULL;
        *value = *value * 10 + (uint64_t)(*at - '0');
    }
    return at;
}

// <code>-YYYYMMDD-HHMMSS-mmm-serial.mvar, or the older <code>-YYYYMMDD-HHMMSS.mvar.
// Exact, because a search for FRB-* also finds the saves of a map named FRB-2.
static int forge_history_parse(const char *name, const char *code, forge_history_stamp *out) {
    size_t length = strlen(code);
    if (strncmp(name, code, length) || name[length] != '-') return 0;
    uint64_t time = 0, millis = 0, serial = 0;
    const char *at = forge_history_digits(name + length + 1, 8, &time);
    if (!at || *at != '-') return 0;
    at = forge_history_digits(at + 1, 6, &time);
    if (!at) return 0;
    if (*at == '-') {
        at = forge_history_digits(at + 1, 3, &millis);
        if (!at || *at != '-') return 0;
        at++;
        const char *digits = at;
        while (*at >= '0' && *at <= '9' && at - digits < 5) serial = serial * 10 + (uint64_t)(*at++ - '0');
        if (at == digits) return 0;
    }
    if (strcmp(at, ".mvar")) return 0;
    out->time = time * 1000 + millis;
    out->serial = (unsigned)serial;
    return 1;
}

static int forge_history_newer(const forge_history_stamp *a, const forge_history_stamp *b) {
    return a->time != b->time ? a->time > b->time : a->serial > b->serial;
}

#endif
