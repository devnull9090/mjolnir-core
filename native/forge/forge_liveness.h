// A missed asynchronous poll is not evidence that the Forge game ended.
#ifndef MJOLNIR_FORGE_LIVENESS_H
#define MJOLNIR_FORGE_LIVENESS_H
#include <stdint.h>

#define FORGE_SNAPSHOT_GRACE_MS 1000u

typedef struct {
    uint32_t tick;
    uint64_t advanced_at_ms;
    int started;
} forge_liveness_t;

// Zero-initialize before the first sandbox snapshot (whose tick is nonzero).
// Only a changed simulation tick renews the grace period, not another poll.
// Compare for inequality rather than ordering so UINT32_MAX -> 0 is progress.
static int forge_snapshot_live(forge_liveness_t *state, uint32_t tick, uint64_t now_ms) {
    if (tick != state->tick) {
        state->tick = tick;
        state->advanced_at_ms = now_ms;
        state->started = 1;
    }
    return state->started && now_ms - state->advanced_at_ms < FORGE_SNAPSHOT_GRACE_MS;
}

#endif
