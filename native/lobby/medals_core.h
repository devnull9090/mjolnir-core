/* Medals for MJOLNIRHud (docs/re/medals.md): which incidents are medals,
 * what each is called and how it is shown, which one hides another, and in
 * what order one kill's medals come up. Portable C with no Windows or Lua
 * calls, so test_medals.c builds it on its own; medals_runtime.h hands it
 * to Lua.
 *
 * The simulation raises a medal as a named incident, the same channel the
 * kill feed reads. Its incident definitions (globals\incident\game_incident)
 * also say which incidents a medal hides, but that is applied only to the
 * game's own HUD and statistics, not to what reaches Unreal: every recorded
 * sniper headshot also arrived as a plain headshot (172 public matches,
 * 2026-11-10). So the hiding is done here, between medals of one player that
 * arrive within MEDALS_WINDOW of each other.
 *
 * Use: medals_add() for each incident as the HUD takes it (anything that is
 * not a medal is refused and costs a string compare per catalogue entry),
 * then medals_settle() once per HUD drain for the awards, best first per
 * player. */
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* How a medal is shown. Every one is counted; the hub reads the match log. */
enum {
    MEDAL_HIDDEN = 0,  /* counted only */
    MEDAL_CALLOUT = 1, /* the earner's own screen, in the middle */
    MEDAL_FEED = 2,    /* a feed line for everyone, and the earner's callout */
};

/* The medal classes of globals\medals, in the order one kill's medals come
   up: a multi-kill before the spree it also completed, both before the
   headshot that made the kill. */
enum {
    MEDAL_MULTIKILL = 0,
    MEDAL_SPREE,
    MEDAL_OBJECTIVE,
    MEDAL_SPECIAL,
    MEDAL_ROLE_SPREE,
    MEDAL_FINESSE,
    MEDAL_CIRCUMSTANCE,
};

typedef struct {
    const char *incident; /* as the HUD has it: lower case */
    const char *title;
    const char *glyph;    /* T_MJHud_<glyph>, cooked in chunk 984 */
    const char *colour;   /* a key of the HUD's FEED colours */
    unsigned char klass, rank, show;
    const char *hides[2]; /* medals of the same player this one stands for */
} medal_def;

/* Every multiplayer medal the game's incident definitions award. Titles are
   ours where the series has none we are sure of. */
static const medal_def MEDALS[] = {
    /* Kills in quick succession: each within 4 s of the last. */
    {"multikill_x2", "Double Kill", "Medal", "medal", MEDAL_MULTIKILL, 1, MEDAL_FEED, {0}},
    {"multikill_x3", "Triple Kill", "Medal", "medal", MEDAL_MULTIKILL, 2, MEDAL_FEED, {0}},
    {"multikill_x4", "Overkill", "Medal", "medal", MEDAL_MULTIKILL, 3, MEDAL_FEED, {0}},
    {"multikill_x5", "Killtacular", "Medal", "medal", MEDAL_MULTIKILL, 4, MEDAL_FEED, {0}},
    {"multikill_x6", "Killtrocity", "Medal", "medal", MEDAL_MULTIKILL, 5, MEDAL_FEED, {0}},
    {"multikill_x7", "Killimanjaro", "Medal", "medal", MEDAL_MULTIKILL, 6, MEDAL_FEED, {0}},
    {"multikill_x8", "Killtastrophe", "Medal", "medal", MEDAL_MULTIKILL, 7, MEDAL_FEED, {0}},
    {"multikill_x9", "Killpocalypse", "Medal", "medal", MEDAL_MULTIKILL, 8, MEDAL_FEED, {0}},
    {"multikill_x10", "Killionaire", "Medal", "medal", MEDAL_MULTIKILL, 9, MEDAL_FEED, {0}},
    /* Kills without dying. */
    {"5_in_a_row", "Killing Spree", "Spree", "spree", MEDAL_SPREE, 1, MEDAL_FEED, {0}},
    {"10_in_a_row", "Killing Frenzy", "Spree", "spree", MEDAL_SPREE, 2, MEDAL_FEED, {0}},
    {"15_in_a_row", "Running Riot", "Spree", "spree", MEDAL_SPREE, 3, MEDAL_FEED, {0}},
    {"20_in_a_row", "Rampage", "Spree", "spree", MEDAL_SPREE, 4, MEDAL_FEED, {0}},
    {"25_in_a_row", "Untouchable", "Spree", "spree", MEDAL_SPREE, 5, MEDAL_FEED, {0}},
    {"30_in_a_row", "Invincible", "Spree", "spree", MEDAL_SPREE, 6, MEDAL_FEED, {0}},
    {"35_in_a_row", "Inconceivable", "Spree", "spree", MEDAL_SPREE, 7, MEDAL_FEED, {0}},
    {"40_in_a_row", "Unfrigginbelievable", "Spree", "spree", MEDAL_SPREE, 8, MEDAL_FEED, {0}},
    /* Objectives. A capture has its own feed line already. */
    {"flag_scored", "Flag Capture", "Flag", "medal", MEDAL_OBJECTIVE, 0, MEDAL_CALLOUT, {0}},
    {"flagcarrier_kill", "Flag Carrier Kill", "Flag", "medal", MEDAL_OBJECTIVE, 0, MEDAL_FEED, {0}},
    {"kill_with_flag", "Flag Kill", "Flag", "medal", MEDAL_OBJECTIVE, 0, MEDAL_FEED, {"melee_kill"}},
    {"ball_carrier_kill", "Ball Carrier Kill", "Medal", "medal", MEDAL_OBJECTIVE, 0, MEDAL_FEED, {0}},
    {"kill_with_oddball", "Oddball Kill", "Medal", "medal", MEDAL_OBJECTIVE, 0, MEDAL_FEED, {"melee_kill"}},
    {"bomb_carrier_kill", "Bomb Carrier Kill", "Medal", "medal", MEDAL_OBJECTIVE, 0, MEDAL_FEED, {0}},
    {"bomb_planted", "Bomb Planted", "Medal", "medal", MEDAL_OBJECTIVE, 0, MEDAL_FEED, {0}},
    {"juggernaut_kill", "Juggernaut Kill", "Medal", "medal", MEDAL_OBJECTIVE, 0, MEDAL_FEED, {0}},
    {"vip_kill", "VIP Kill", "Medal", "medal", MEDAL_OBJECTIVE, 0, MEDAL_FEED, {0}},
    {"inf_last_man", "Last Man Standing", "Medal", "medal", MEDAL_OBJECTIVE, 0, MEDAL_FEED, {0}},
    {"infection_survive", "Hold Out", "Medal", "medal", MEDAL_OBJECTIVE, 0, MEDAL_FEED, {0}},
    {"koth_spree", "Hill Spree", "Spree", "spree", MEDAL_OBJECTIVE, 1, MEDAL_FEED, {0}},
    {"juggernaut_5x", "Juggernaut Spree", "Spree", "spree", MEDAL_OBJECTIVE, 1, MEDAL_FEED, {"gravity_hammer_5x"}},
    {"juggernaut_10x", "Immovable Object", "Spree", "spree", MEDAL_OBJECTIVE, 2, MEDAL_FEED, {"gravity_hammer_10x"}},
    {"juggernaut_15x", "Unstoppable Force", "Spree", "spree", MEDAL_OBJECTIVE, 3, MEDAL_FEED, {"gravity_hammer_15x"}},
    /* Special. */
    {"first_blood", "First Blood", "FirstBlood", "blood", MEDAL_SPECIAL, 1, MEDAL_FEED, {0}},
    {"extermination", "Extermination", "Medal", "medal", MEDAL_SPECIAL, 1, MEDAL_FEED, {0}},
    {"perfection", "Perfection", "Medal", "medal", MEDAL_SPECIAL, 1, MEDAL_FEED, {0}},
    {"skullamanjaro", "Skullamanjaro", "Medal", "medal", MEDAL_SPECIAL, 0, MEDAL_FEED, {0}},
    {"headshot_kill", "Headshot", "Headshot", "headshot", MEDAL_SPECIAL, 0, MEDAL_CALLOUT, {0}},
    {"supercombine_kill", "Supercombine", "Explosion", "medal", MEDAL_SPECIAL, 0, MEDAL_CALLOUT, {0}},
    {"emp_assist", "EMP Assist", "Medal", "medal", MEDAL_SPECIAL, 0, MEDAL_CALLOUT, {0}},
    {"assist", "Assist", "Medal", "medal", MEDAL_SPECIAL, 0, MEDAL_CALLOUT, {0}},
    {"avenger", "Avenger", "Medal", "medal", MEDAL_SPECIAL, 0, MEDAL_CALLOUT, {0}},
    /* One weapon's kills without dying. */
    {"sniper_5x", "Sniper Spree", "Headshot", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {0}},
    {"sniper_10x", "Sharpshooter", "Headshot", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {0}},
    {"sniper_15x", "Be the Bullet", "Headshot", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {0}},
    {"shotgun_5x", "Shotgun Spree", "Spree", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {0}},
    {"shotgun_10x", "Open Season", "Spree", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {0}},
    {"shotgun_15x", "Buck Wild", "Spree", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {0}},
    {"splatter_5x", "Splatter Spree", "Splatter", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {0}},
    {"splatter_10x", "Vehicular Manslaughter", "Splatter", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {0}},
    {"splatter_15x", "Sunday Driver", "Splatter", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {0}},
    {"sword_5x", "Sword Spree", "Melee", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {0}},
    {"sword_10x", "Slice 'n Dice", "Melee", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {0}},
    {"sword_15x", "Cutting Crew", "Melee", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {0}},
    {"gravity_hammer_5x", "Hammer Spree", "Melee", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {0}},
    {"gravity_hammer_10x", "Dream Crusher", "Melee", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {0}},
    {"gravity_hammer_15x", "Wrecking Crew", "Melee", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {0}},
    {"laser_5x", "Laser Spree", "Explosion", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {0}},
    {"laser_10x", "Red Menace", "Explosion", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {0}},
    {"laser_15x", "Sunburst", "Explosion", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {0}},
    {"sticky_grenade_5x", "Sticky Spree", "Stuck", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {0}},
    {"sticky_grenade_10x", "Sticky Fingers", "Stuck", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {0}},
    {"sticky_grenade_15x", "Sticky Riot", "Stuck", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {0}},
    {"assist_5x", "Assist Spree", "Medal", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {"assist"}},
    {"assist_10x", "Sidekick", "Medal", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {"assist"}},
    {"assist_15x", "Second Gunman", "Medal", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {"assist"}},
    {"wheelman_5x", "Wheelman Spree", "Splatter", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED,
     {"driver_assist_gunner", "assist_5x"}},
    {"wheelman_10x", "Road Hog", "Splatter", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED,
     {"driver_assist_gunner", "assist_10x"}},
    {"wheelman_15x", "Road Rage", "Splatter", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED,
     {"driver_assist_gunner", "assist_15x"}},
    {"wingman_5x", "Wingman Spree", "Joined", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {0}},
    {"wingman_10x", "Wingman Frenzy", "Joined", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {0}},
    {"wingman_15x", "Wingman Riot", "Joined", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {0}},
    {"infection_5x", "Infection Spree", "Skull", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {0}},
    {"infection_10x", "Mmmm Brains", "Skull", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {0}},
    {"infection_15x", "Zombie Apocalypse", "Skull", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {0}},
    {"zombie_kill_5x", "Zombie Killing Spree", "Skull", "spree", MEDAL_ROLE_SPREE, 1, MEDAL_FEED, {0}},
    {"zombie_kill_10x", "Zombie Killing Frenzy", "Skull", "spree", MEDAL_ROLE_SPREE, 2, MEDAL_FEED, {0}},
    {"zombie_kill_15x", "Zombie Killing Riot", "Skull", "spree", MEDAL_ROLE_SPREE, 3, MEDAL_FEED, {0}},
    /* How the kill was made. */
    {"sniper_headshot_kill", "Sniper Headshot", "Headshot", "headshot", MEDAL_FINESSE, 1, MEDAL_CALLOUT,
     {"headshot_kill"}},
    {"melee_kill", "Pummel", "Melee", "medal", MEDAL_FINESSE, 0, MEDAL_CALLOUT, {0}},
    {"assassination_kill", "Beat Down", "Assassination", "medal", MEDAL_FINESSE, 1, MEDAL_CALLOUT, {"melee_kill"}},
    {"finishing_move_kill", "Assassination", "Assassination", "medal", MEDAL_FINESSE, 2, MEDAL_CALLOUT,
     {"yoink"}},
    {"splatter_kill", "Splatter", "Splatter", "medal", MEDAL_FINESSE, 0, MEDAL_CALLOUT, {0}},
    {"sticky_grenade_kill", "Stuck", "Stuck", "medal", MEDAL_FINESSE, 0, MEDAL_CALLOUT, {0}},
    {"laser_kill", "Laser Kill", "Explosion", "medal", MEDAL_FINESSE, 0, MEDAL_CALLOUT, {0}},
    {"sprinting_kill", "Speed Kill", "Medal", "medal", MEDAL_FINESSE, 0, MEDAL_CALLOUT, {0}},
    {"pull_kill", "Pull", "Medal", "medal", MEDAL_FINESSE, 0, MEDAL_CALLOUT, {0}},
    {"showstopper", "Showstopper", "Medal", "medal", MEDAL_FINESSE, 0, MEDAL_CALLOUT, {0}},
    {"yoink", "Yoink", "Medal", "medal", MEDAL_FINESSE, 0, MEDAL_CALLOUT, {0}},
    {"second_wind", "Second Wind", "Medal", "medal", MEDAL_FINESSE, 0, MEDAL_CALLOUT, {0}},
    {"firebird", "Firebird", "Medal", "medal", MEDAL_FINESSE, 0, MEDAL_CALLOUT, {0}},
    /* What was going on around it. */
    {"revenge_kill", "Revenge", "Medal", "medal", MEDAL_CIRCUMSTANCE, 0, MEDAL_CALLOUT, {0}},
    {"killjoy", "Killjoy", "Medal", "medal", MEDAL_CIRCUMSTANCE, 0, MEDAL_CALLOUT, {0}},
    {"opportunist_kill", "Opportunist", "Medal", "medal", MEDAL_CIRCUMSTANCE, 0, MEDAL_CALLOUT, {0}},
    {"close_call", "Close Call", "Medal", "medal", MEDAL_CIRCUMSTANCE, 0, MEDAL_CALLOUT, {0}},
    {"kill_from_the_grave", "From the Grave", "Skull", "medal", MEDAL_CIRCUMSTANCE, 0, MEDAL_CALLOUT, {0}},
    {"lifesaver", "Lifesaver", "Medal", "medal", MEDAL_CIRCUMSTANCE, 0, MEDAL_CALLOUT, {0}},
    {"driver_assist_gunner", "Wheelman", "Splatter", "medal", MEDAL_CIRCUMSTANCE, 0, MEDAL_CALLOUT, {"assist"}},
    {"highjack", "Hijack", "Medal", "medal", MEDAL_CIRCUMSTANCE, 0, MEDAL_CALLOUT, {0}},
    {"skyjack", "Skyjack", "Medal", "medal", MEDAL_CIRCUMSTANCE, 1, MEDAL_CALLOUT, {0}},
    {"shotgun_kill_sword", "Bulltrue", "Medal", "medal", MEDAL_CIRCUMSTANCE, 1, MEDAL_CALLOUT, {0}},
};
#define MEDALS_COUNT ((int)(sizeof MEDALS / sizeof MEDALS[0]))

/* Medals of one player this close together (seconds) are one moment: one
   can hide another. A kill's medals arrive in the same simulation tick. */
#define MEDALS_WINDOW 0.5
#define MEDALS_PENDING 96
#define MEDALS_HISTORY 32
#define MEDALS_NAME_MAX 40

typedef struct {
    short def;          /* index into MEDALS */
    int cause, effect;  /* absolute player indices, -1 for none */
    double at;          /* the caller's clock, seconds */
    unsigned seq;       /* arrival order */
} medal_entry;

typedef struct {
    medal_entry pending[MEDALS_PENDING];
    int pending_count;
    /* Settled medals, kept MEDALS_WINDOW for one that arrives later and is
       hidden by them. */
    medal_entry history[MEDALS_HISTORY];
    int history_next;
    unsigned seq;
    unsigned dropped; /* pending was full */
} medals_state;

typedef struct {
    const medal_def *def;
    int cause, effect;
} medal_award;

static void medals_reset(medals_state *s) {
    memset(s, 0, sizeof *s);
    for (int i = 0; i < MEDALS_HISTORY; i++) s->history[i].def = -1;
}

/* The catalogue entry for incident `name`, or -1. */
static int medals_find(const char *name) {
    if (!name || !name[0]) return -1;
    for (int i = 0; i < MEDALS_COUNT; i++)
        if (strcmp(MEDALS[i].incident, name) == 0) return i;
    return -1;
}

/* Takes incident `name` if it is a medal: 1 when taken, 0 otherwise. */
static int medals_add(medals_state *s, const char *name, int cause, int effect, double at) {
    int def = medals_find(name);
    if (def < 0) return 0;
    if (s->pending_count >= MEDALS_PENDING) {
        s->dropped++;
        return 1;
    }
    medal_entry *e = &s->pending[s->pending_count++];
    e->def = (short)def;
    e->cause = cause;
    e->effect = effect;
    e->at = at;
    e->seq = s->seq++;
    return 1;
}

static int medals_hides(const medal_entry *by, const medal_entry *e) {
    if (by == e || by->def < 0 || by->cause != e->cause) return 0;
    double gap = by->at - e->at;
    if (gap > MEDALS_WINDOW || gap < -MEDALS_WINDOW) return 0;
    const medal_def *d = &MEDALS[by->def];
    for (int h = 0; h < 2 && d->hides[h]; h++)
        if (strcmp(d->hides[h], MEDALS[e->def].incident) == 0) return 1;
    return 0;
}

/* Whether a over b: the earlier player first, then class, then the higher
   rank, then arrival. `first` is each entry's player's first arrival. */
static int medals_before(const medal_entry *a, unsigned first_a, const medal_entry *b, unsigned first_b) {
    if (first_a != first_b) return first_a < first_b;
    const medal_def *da = &MEDALS[a->def], *db = &MEDALS[b->def];
    if (da->klass != db->klass) return da->klass < db->klass;
    if (da->rank != db->rank) return da->rank > db->rank;
    return a->seq < b->seq;
}

/* The awards from every medal taken at least `hold` seconds before `now`,
   minus the hidden ones, into out (best first for each player, players in
   the order they first earned one). Returns how many were written; any past
   `cap` are lost. Younger ones wait for a later call, so a medal that hides
   one that came a moment before it is still in time. */
static int medals_settle(medals_state *s, double now, double hold, medal_award *out, int cap) {
    medal_entry ready[MEDALS_PENDING], young[MEDALS_PENDING];
    unsigned first[MEDALS_PENDING];
    int n = 0, keep = 0;
    for (int i = 0; i < s->pending_count; i++) {
        medal_entry *e = &s->pending[i];
        if (now - e->at < hold) {
            young[keep++] = *e;
            continue;
        }
        int hidden = 0;
        for (int j = 0; j < s->pending_count && !hidden; j++) hidden = medals_hides(&s->pending[j], e);
        for (int j = 0; j < MEDALS_HISTORY && !hidden; j++) hidden = medals_hides(&s->history[j], e);
        if (!hidden) ready[n++] = *e;
    }
    /* What settled hides what comes later. */
    for (int i = 0; i < s->pending_count; i++) {
        medal_entry *e = &s->pending[i];
        if (now - e->at < hold) continue;
        s->history[s->history_next] = *e;
        s->history_next = (s->history_next + 1) % MEDALS_HISTORY;
    }
    /* Each player's place: their first medal settling now, hidden or not. */
    for (int i = 0; i < n; i++) {
        first[i] = ready[i].seq;
        for (int j = 0; j < s->pending_count; j++) {
            const medal_entry *e = &s->pending[j];
            if (now - e->at >= hold && e->cause == ready[i].cause && e->seq < first[i]) first[i] = e->seq;
        }
    }
    memcpy(s->pending, young, (size_t)keep * sizeof young[0]);
    s->pending_count = keep;
    /* Insertion sort: a few medals at a time. */
    for (int i = 1; i < n; i++) {
        medal_entry e = ready[i];
        unsigned f = first[i];
        int j = i - 1;
        while (j >= 0 && medals_before(&e, f, &ready[j], first[j])) {
            ready[j + 1] = ready[j];
            first[j + 1] = first[j];
            j--;
        }
        ready[j + 1] = e;
        first[j + 1] = f;
    }
    int w = 0;
    for (int i = 0; i < n && w < cap; i++) {
        out[w].def = &MEDALS[ready[i].def];
        out[w].cause = ready[i].cause;
        out[w].effect = ready[i].effect;
        w++;
    }
    return w;
}

/* Awards as text for Lua, one per line:
       incident|cause|effect|title|glyph|colour|show
   Returns the length written (NUL-terminated); awards that do not fit are
   left off whole. */
static size_t medals_pack(const medal_award *a, int n, char *buf, size_t cap) {
    size_t len = 0;
    if (cap) buf[0] = 0;
    for (int i = 0; i < n; i++) {
        char line[160];
        int k = snprintf(line, sizeof line, "%s|%d|%d|%s|%s|%s|%d\n", a[i].def->incident, a[i].cause, a[i].effect,
                         a[i].def->title, a[i].def->glyph, a[i].def->colour, a[i].def->show);
        if (k <= 0 || (size_t)k >= sizeof line || len + (size_t)k + 1 > cap) break;
        memcpy(buf + len, line, (size_t)k);
        len += (size_t)k;
        buf[len] = 0;
    }
    return len;
}
