/* Portable tests for medals_core.h: the catalogue, what hides what, the
 * order one kill's medals come in, and the text Lua reads. */
#include <stdlib.h>
#include "medals_core.h"

static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

static medals_state s;
static medal_award out[MEDALS_PENDING];

static int settle(double now, double hold) { return medals_settle(&s, now, hold, out, MEDALS_PENDING); }
static const char *name(int i) { return out[i].def->incident; }

int main(void) {
    /* The catalogue: unique names, every hidden name a medal, a title and
       glyph each, names that fit the channel's buffer. */
    for (int i = 0; i < MEDALS_COUNT; i++) {
        const medal_def *d = &MEDALS[i];
        CHECK(strlen(d->incident) < MEDALS_NAME_MAX);
        CHECK(d->title[0] && d->glyph[0] && d->colour[0]);
        CHECK(!strchr(d->title, '|') && !strchr(d->title, '\n'));
        CHECK(d->show <= MEDAL_FEED && d->klass <= MEDAL_CIRCUMSTANCE);
        CHECK(medals_find(d->incident) == i);
        for (int h = 0; h < 2 && d->hides[h]; h++) CHECK(medals_find(d->hides[h]) >= 0);
    }
    CHECK(MEDALS_COUNT == 100);
    CHECK(medals_find("kill") < 0 && medals_find("death") < 0 && medals_find("") < 0 && medals_find(NULL) < 0);
    CHECK(medals_find("Kill") < 0); /* the HUD lower-cases names first */

    /* Anything that is not a medal is refused and leaves nothing behind. */
    medals_reset(&s);
    CHECK(!medals_add(&s, "kill", 1, 0, 1.0));
    CHECK(!medals_add(&s, "technician_comm", 1, 0, 1.0));
    CHECK(settle(2.0, 0.0) == 0);

    /* A sniper headshot hides the headshot that came with it (the engine
       sends both: 191 of 191 recorded), but only for the same player. */
    medals_reset(&s);
    CHECK(medals_add(&s, "headshot_kill", 1, 0, 10.0));
    CHECK(medals_add(&s, "headshot_kill", 2, 3, 10.0));
    CHECK(medals_add(&s, "sniper_headshot_kill", 1, 0, 10.0));
    int n = settle(10.1, 0.0);
    CHECK(n == 2);
    CHECK(strcmp(name(0), "sniper_headshot_kill") == 0 && out[0].cause == 1 && out[0].effect == 0);
    CHECK(strcmp(name(1), "headshot_kill") == 0 && out[1].cause == 2);

    /* One kill's medals: the multi-kill first, then the spree, then the
       special and the finesse ones, whatever order they arrived in. */
    medals_reset(&s);
    medals_add(&s, "revenge_kill", 4, 1, 20.0);
    medals_add(&s, "headshot_kill", 4, 1, 20.0);
    medals_add(&s, "5_in_a_row", 4, -1, 20.0);
    medals_add(&s, "multikill_x2", 4, -1, 20.0);
    medals_add(&s, "first_blood", 4, 1, 20.0);
    n = settle(20.0, 0.0);
    CHECK(n == 5);
    CHECK(strcmp(name(0), "multikill_x2") == 0);
    CHECK(strcmp(name(1), "5_in_a_row") == 0);
    CHECK(strcmp(name(2), "first_blood") == 0);   /* special, rank 1 */
    CHECK(strcmp(name(3), "headshot_kill") == 0); /* special, rank 0 */
    CHECK(strcmp(name(4), "revenge_kill") == 0);

    /* Players stay in the order they first earned one. */
    medals_reset(&s);
    medals_add(&s, "headshot_kill", 5, 2, 30.0);
    medals_add(&s, "multikill_x3", 6, -1, 30.0);
    medals_add(&s, "multikill_x2", 5, -1, 30.0);
    n = settle(30.0, 0.0);
    CHECK(n == 3 && out[0].cause == 5 && out[1].cause == 5 && out[2].cause == 6);
    CHECK(strcmp(name(0), "multikill_x2") == 0);

    /* A medal younger than `hold` waits; the one that hides it, arriving
       next drain, still does. */
    medals_reset(&s);
    medals_add(&s, "assist", 3, 1, 40.0);
    CHECK(settle(40.02, 0.05) == 0);
    medals_add(&s, "driver_assist_gunner", 3, 1, 40.03);
    n = settle(40.2, 0.05);
    CHECK(n == 1 && strcmp(name(0), "driver_assist_gunner") == 0);

    /* One already settled hides a later one within the window, not after. */
    medals_reset(&s);
    medals_add(&s, "sniper_headshot_kill", 1, 0, 50.0);
    CHECK(settle(50.0, 0.0) == 1);
    medals_add(&s, "headshot_kill", 1, 0, 50.2);
    CHECK(settle(50.3, 0.0) == 0);
    medals_add(&s, "headshot_kill", 1, 0, 52.0);
    CHECK(settle(52.0, 0.0) == 1);

    /* The fifth assist is a spree, and the plain assist goes; a wheelman
       spree stands for both its assist spree and the driver's assist. */
    medals_reset(&s);
    medals_add(&s, "assist", 2, 0, 60.0);
    medals_add(&s, "assist_5x", 2, -1, 60.0);
    n = settle(60.0, 0.0);
    CHECK(n == 1 && strcmp(name(0), "assist_5x") == 0);
    medals_add(&s, "driver_assist_gunner", 2, 0, 70.0);
    medals_add(&s, "assist_5x", 2, -1, 70.0);
    medals_add(&s, "wheelman_5x", 2, -1, 70.0);
    n = settle(70.0, 0.0);
    CHECK(n == 1 && strcmp(name(0), "wheelman_5x") == 0);

    /* Two of one medal in one drain (two kills a tick apart) are two. */
    medals_reset(&s);
    medals_add(&s, "headshot_kill", 1, 0, 80.0);
    medals_add(&s, "headshot_kill", 1, 2, 80.0);
    CHECK(settle(80.0, 0.0) == 2);

    /* Pending is bounded: past it medals are counted as dropped. */
    medals_reset(&s);
    for (int i = 0; i < MEDALS_PENDING + 5; i++) CHECK(medals_add(&s, "assist", i % 16, 0, 90.0 + i));
    CHECK(s.dropped == 5);
    CHECK(settle(1000.0, 0.0) == MEDALS_PENDING);

    /* The text Lua reads, and a buffer too small for the second line. */
    medals_reset(&s);
    medals_add(&s, "multikill_x2", 1, -1, 100.0);
    medals_add(&s, "headshot_kill", 1, 0, 100.0);
    n = settle(100.0, 0.0);
    char text[256];
    size_t len = medals_pack(out, n, text, sizeof text);
    CHECK(strcmp(text, "multikill_x2|1|-1|Double Kill|Medal|medal|2\nheadshot_kill|1|0|Headshot|Headshot|headshot|1\n") == 0);
    CHECK(len == strlen(text));
    len = medals_pack(out, n, text, 50);
    CHECK(strcmp(text, "multikill_x2|1|-1|Double Kill|Medal|medal|2\n") == 0 && len == strlen(text));
    CHECK(medals_pack(out, n, text, 10) == 0 && text[0] == 0);

    printf("medals: %d checks passed\n", checks);
    return 0;
}
