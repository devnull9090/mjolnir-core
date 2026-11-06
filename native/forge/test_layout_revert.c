// Portable tests of the second press and of history names.
#include <stdio.h>
#include <stdlib.h>
#include "layout_revert.h"

static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

static void confirm_tests(void) {
    forge_confirm c = {0, 0};
    // The first press only asks, and a deliberate second one answers.
    CHECK(forge_confirm_press(&c, 10000) == FORGE_CONFIRM_ASK);
    CHECK(forge_confirm_press(&c, 11000) == FORGE_CONFIRM_DONE);
    // Answered: the next press asks again.
    CHECK(forge_confirm_press(&c, 11100) == FORGE_CONFIRM_ASK);

    // A press after the window asks again instead of acting.
    c = (forge_confirm){0, 0};
    CHECK(forge_confirm_press(&c, 10000) == FORGE_CONFIRM_ASK);
    CHECK(forge_confirm_press(&c, 10000 + FORGE_CONFIRM_WINDOW_MS + 1) == FORGE_CONFIRM_ASK);
    CHECK(forge_confirm_press(&c, 10000 + FORGE_CONFIRM_WINDOW_MS + 1 + FORGE_CONFIRM_MIN_GAP_MS) == FORGE_CONFIRM_DONE);

    // Exactly at the edges of the window it still counts.
    c = (forge_confirm){0, 0};
    CHECK(forge_confirm_press(&c, 10000) == FORGE_CONFIRM_ASK);
    CHECK(forge_confirm_press(&c, 10000 + FORGE_CONFIRM_WINDOW_MS) == FORGE_CONFIRM_DONE);

    // An accidental double tap never confirms, but a real press after it does.
    c = (forge_confirm){0, 0};
    CHECK(forge_confirm_press(&c, 10000) == FORGE_CONFIRM_ASK);
    CHECK(forge_confirm_press(&c, 10150) == FORGE_CONFIRM_IGNORED);
    CHECK(forge_confirm_press(&c, 10150 + FORGE_CONFIRM_MIN_GAP_MS) == FORGE_CONFIRM_DONE);

    // Key repeat at the Lua throttle's rate never confirms, however long.
    c = (forge_confirm){0, 0};
    CHECK(forge_confirm_press(&c, 10000) == FORGE_CONFIRM_ASK);
    for (uint64_t now = 10200; now < 30000; now += 200) CHECK(forge_confirm_press(&c, now) == FORGE_CONFIRM_IGNORED);

    // Another command disarms: the caller clears `armed`.
    c = (forge_confirm){0, 0};
    CHECK(forge_confirm_press(&c, 10000) == FORGE_CONFIRM_ASK);
    c.armed = 0;
    CHECK(forge_confirm_press(&c, 11000) == FORGE_CONFIRM_ASK);
}

static void history_tests(void) {
    forge_history_stamp a, b;
    CHECK(forge_history_parse("FRB-20261102-150123-440-0.mvar", "FRB", &a));
    CHECK(a.time == 20261102150123440ull && a.serial == 0);
    CHECK(forge_history_parse("FRB-20261102-150123-440-12.mvar", "FRB", &b));
    CHECK(b.serial == 12 && forge_history_newer(&b, &a) && !forge_history_newer(&a, &b));
    // The numbers order them, not the text: serial 9 is before serial 10.
    CHECK(forge_history_parse("FRB-20261102-150123-440-9.mvar", "FRB", &a));
    CHECK(forge_history_parse("FRB-20261102-150123-440-10.mvar", "FRB", &b));
    CHECK(forge_history_newer(&b, &a));
    // The older name, from before a save kept its milliseconds.
    CHECK(forge_history_parse("BGL-20261101-194959.mvar", "BGL", &a));
    CHECK(a.time == 20261101194959000ull && a.serial == 0);
    CHECK(forge_history_parse("BGL-20261101-195000-000-0.mvar", "BGL", &b));
    CHECK(forge_history_newer(&b, &a));
    CHECK(!forge_history_newer(&a, &a));

    // A map whose code extends this one's, and any other name, is not its save.
    CHECK(!forge_history_parse("FRB-2-20261102-150123-440-0.mvar", "FRB", &a));
    CHECK(forge_history_parse("FRB-2-20261102-150123-440-0.mvar", "FRB-2", &a));
    CHECK(!forge_history_parse("FRBX-20261102-150123-440-0.mvar", "FRB", &a));
    CHECK(!forge_history_parse("frb-20261102-150123-440-0.mvar", "FRB", &a));
    CHECK(!forge_history_parse("FRB.mvar", "FRB", &a));
    CHECK(!forge_history_parse("FRB-.mvar", "FRB", &a));
    CHECK(!forge_history_parse("FRB-backup.mvar", "FRB", &a));
    CHECK(!forge_history_parse("FRB-20261102-150123-440-0.mvar.packs", "FRB", &a));
    CHECK(!forge_history_parse("FRB-20261102-150123-440-.mvar", "FRB", &a));
    CHECK(!forge_history_parse("FRB-20261102-150123-44-0.mvar", "FRB", &a));
    CHECK(!forge_history_parse("FRB-20261102-15012.mvar", "FRB", &a));
    CHECK(!forge_history_parse("FRB-20261102-150123-440-123456.mvar", "FRB", &a));
}

int main(void) {
    confirm_tests();
    history_tests();
    printf("Forge revert: %d checks passed\n", checks);
    return 0;
}
