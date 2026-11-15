/* Medals for MJOLNIRHud through lua_channel.h (medals_core.h has the rules).
 *
 * The HUD's one incident hook stays in Lua: it is the kill feed's and the
 * match log's source too, and a bot's incidents name it by its biped actor,
 * which only Lua reads. The HUD hands each incident it takes here, once
 * (after its own dedupe of a host's relay), and asks for the awards once a
 * drain:
 *
 *     mjolnir_medal_info(name)                  title, glyph, colour, show,
 *                                               class, rank; nil when `name`
 *                                               is not a medal
 *     mjolnir_medal_incident(name, cause, effect, at)
 *                                               true when it was a medal
 *     mjolnir_medals_take(now, hold)            the settled awards, packed
 *                                               (medals_pack); "" for none
 *     mjolnir_medals_reset()                    a new match
 *
 * Only the HUD's game-thread code calls these; the lock is for a second
 * caller, never needed so far. Nothing raises into Lua. */
#include "lua_channel.h"
#include "medals_core.h"

static SRWLOCK medals_lock = SRWLOCK_INIT;
static medals_state medals_live;
static int medals_ready;

static void medals_ensure(void) {
    if (!medals_ready) {
        medals_reset(&medals_live);
        medals_ready = 1;
    }
}

__declspec(dllexport) int mjolnir_medal_info(void *L) {
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    char name[MEDALS_NAME_MAX];
    size_t length = 0;
    int def = lc_take_string(&f, 1, name, sizeof name, &length) && length < sizeof name ? medals_find(name) : -1;
    if (def < 0) {
        lc_push_nil(&f);
        lc_end(&f);
        return 1;
    }
    const medal_def *d = &MEDALS[def];
    lc_push_text(&f, d->title);
    lc_push_text(&f, d->glyph);
    lc_push_text(&f, d->colour);
    lc_push_integer(&f, d->show);
    lc_push_integer(&f, d->klass);
    lc_push_integer(&f, d->rank);
    lc_end(&f);
    return 6;
}

__declspec(dllexport) int mjolnir_medal_incident(void *L) {
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    char name[MEDALS_NAME_MAX];
    size_t length = 0;
    int ok = lc_take_string(&f, 1, name, sizeof name, &length) && length < sizeof name;
    long long cause = lc_take_integer(&f, 1, -1);
    long long effect = lc_take_integer(&f, 1, -1);
    double at = lc_take_number(&f, 1, 0.0);
    int taken = 0;
    if (ok && cause >= -1 && cause < 256 && effect >= -1 && effect < 256) {
        AcquireSRWLockExclusive(&medals_lock);
        medals_ensure();
        taken = medals_add(&medals_live, name, (int)cause, (int)effect, at);
        ReleaseSRWLockExclusive(&medals_lock);
    }
    lc_push_bool(&f, taken);
    lc_end(&f);
    return 1;
}

__declspec(dllexport) int mjolnir_medals_take(void *L) {
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    double now = lc_take_number(&f, 1, 0.0);
    double hold = lc_take_number(&f, 1, 0.0);
    medal_award awards[MEDALS_PENDING];
    char packed[MEDALS_PENDING * 160];
    AcquireSRWLockExclusive(&medals_lock);
    medals_ensure();
    int n = medals_settle(&medals_live, now, hold, awards, MEDALS_PENDING);
    ReleaseSRWLockExclusive(&medals_lock);
    size_t len = medals_pack(awards, n, packed, sizeof packed);
    lc_push_string(&f, packed, len);
    lc_end(&f);
    return 1;
}

__declspec(dllexport) int mjolnir_medals_reset(void *L) {
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    AcquireSRWLockExclusive(&medals_lock);
    medals_reset(&medals_live);
    medals_ready = 1;
    ReleaseSRWLockExclusive(&medals_lock);
    lc_end(&f);
    return 0;
}
