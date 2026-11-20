/* Stage transitions own the two named, map-authored loadout operations. */
#pragma once
#include <stdint.h>
#include <stdio.h>

typedef struct {
    uint64_t instance;
    uint32_t unit;
    int cleared, restoring, retry_ticks, attempts;
} warfare_inventory;

static void warfare_inventory_apply(warfare_inventory *kit, uint64_t instance, uint32_t unit,
                                    int player, unsigned flags, int (*submit)(const char *)) {
    char line[224];
    if (kit->instance != instance || kit->unit != unit) {
        *kit = (warfare_inventory){0};
        kit->instance = instance;
        kit->unit = unit;
    }
    if ((flags & WF_LOWER_WEAPON) && !kit->cleared) {
        snprintf(line, sizeof line, "(begin (unit_lower_weapon (player_get %d) 6) "
                 "(unit_add_equipment (player_get %d) pwr_unarmed true false))", player, player);
        kit->cleared = submit(line);
    }
    if (flags & WF_RAISE_WEAPON) {
        if (!kit->cleared) {
            snprintf(line, sizeof line, "(unit_raise_weapon (player_get %d) 6)", player);
            submit(line);
            return;
        }
        kit->restoring = 1;
    }
    if (!kit->restoring || kit->retry_ticks-- > 0) return;
    snprintf(line, sizeof line, "(begin (unit_add_equipment (player_get %d) pwr_starter false false) "
             "(unit_raise_weapon (player_get %d) 6))", player, player);
    if (submit(line)) {
        kit->cleared = 0;
        kit->restoring = 0;
    } else if (++kit->attempts >= 3) {
        kit->restoring = 0; /* The evaluator records the failures; never spam a missing profile. */
    } else {
        kit->retry_ticks = 30;
    }
}
