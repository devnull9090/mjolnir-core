#include <stdio.h>
#include <stdlib.h>
#include "forge_liveness.h"

static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

int main(void) {
    forge_liveness_t state = {0};
    // The initial zero snapshot must never advertise Forge, even when the
    // process has been running for a long time before the mod starts polling.
    CHECK(!forge_snapshot_live(&state, 0, 0));
    CHECK(!forge_snapshot_live(&state, 0, 100));
    CHECK(!forge_snapshot_live(&state, 0, 60000));

    // Reproduce the real failure: 100ms asynchronous polls can see the same
    // snapshot across a 110ms game-thread hitch. The old changed-tick test
    // would hide/show the HUD here, although the Forge session continues.
    CHECK(forge_snapshot_live(&state, 1, 60100));
    CHECK(forge_snapshot_live(&state, 1, 60200));
    CHECK(forge_snapshot_live(&state, 1, 60210));
    CHECK(forge_snapshot_live(&state, 7, 60300));
    CHECK(forge_snapshot_live(&state, 13, 60400));
    CHECK(forge_snapshot_live(&state, 13, 60500));
    CHECK(forge_snapshot_live(&state, 19, 60600));

    // True inactivity still hides the HUD. Repeated polling must not slide
    // the deadline forward, and a new snapshot must recover immediately.
    for (uint64_t elapsed = 100; elapsed < 1000; elapsed += 100)
        CHECK(forge_snapshot_live(&state, 19, 60600 + elapsed));
    CHECK(forge_snapshot_live(&state, 19, 61599));
    CHECK(!forge_snapshot_live(&state, 19, 61600));
    CHECK(!forge_snapshot_live(&state, 19, 62600));
    CHECK(forge_snapshot_live(&state, 20, 62601));
    CHECK(forge_snapshot_live(&state, 20, 63600));
    CHECK(!forge_snapshot_live(&state, 20, 63601));

    // The native snapshot uses an unsigned 32-bit tick. Its zero value after
    // wrap is a live snapshot, not the "never saw Forge" startup sentinel.
    CHECK(forge_snapshot_live(&state, UINT32_MAX, 64000));
    CHECK(forge_snapshot_live(&state, 0, 64900));
    CHECK(forge_snapshot_live(&state, 0, 65899));
    CHECK(!forge_snapshot_live(&state, 0, 65900));
    CHECK(forge_snapshot_live(&state, 1, 66000));

    // Unsigned elapsed-time arithmetic also preserves the deadline across
    // a clock wrap; no signed narrowing or equality-at-zero assumptions.
    CHECK(forge_snapshot_live(&state, 2, UINT64_MAX - 499));
    CHECK(forge_snapshot_live(&state, 2, 0));
    CHECK(forge_snapshot_live(&state, 2, 499));
    CHECK(!forge_snapshot_live(&state, 2, 500));
    CHECK(forge_snapshot_live(&state, 3, 501));

    printf("Forge snapshot liveness: %d checks passed\n", checks);
    return 0;
}
