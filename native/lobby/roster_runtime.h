/* The players' roster for MJOLNIRHud (docs/lua_native_audit.md, "Player
 * roster from the simulation"). Included after lifts_runtime.h, which brings
 * the simulation helpers (sim_tls_block, install_main_tick).
 *
 * The HUD read every other player's place from actors: twelve to nineteen
 * reflection calls a player, five times a second in King and Juggernaut,
 * and a fireteam client's actor for a remote player could sit where that
 * player spawned while its simulation followed them to 2 cm (two copies on
 * PC 1, 2026-11-09). Here the simulation thread copies its own players
 * table once a tick (roster_core.h has what it reads), while the HUD has
 * asked in the last few seconds, and Lua takes the copy through
 * lua_channel.h: no files, no handles kept in Lua.
 *
 *     mjolnir_roster()        the packed roster, or nil and why
 *     mjolnir_roster_at(i)    seat i's x, y, z (cm), alive, velocity (cm/s) and
 *                             the copy's age (s), or nil and why
 *
 * Every peer reads its own simulation; handles are per peer and never
 * compared across machines. Nothing here raises into Lua (a Lua error would
 * longjmp past the lock): a reason string comes back instead. */
#include "lua_channel.h"
#include "roster_core.h"

/* After this long without a call the tick stops copying. */
#define ROSTER_IDLE_MS 5000
/* A copy older than this is not handed out: the simulation is not ticking
   (a load, the menus), and the HUD reads actors instead. */
#define ROSTER_STALE_MS 1500

static SRWLOCK roster_lock = SRWLOCK_INIT;
static roster_snapshot roster_live, roster_scratch;
static unsigned long long roster_live_at;   /* GetTickCount64 of the copy, 0 for none */
static LONGLONG roster_live_qpc;            /* and its QueryPerformanceCounter, for its age */
static LARGE_INTEGER roster_frequency;
static volatile LONG64 roster_wanted_at;    /* the last call's GetTickCount64 */
static unsigned long long roster_instance;
static int roster_faulted;                  /* off until the next game */
static int roster_said;                     /* the first copy of a game is logged */
/* The main tick could not be hooked on this build: asked once, as the
   lobby's own startup does (main_tick_failed), not on every call. */
static volatile LONG roster_no_tick;

static void roster_clear(void) {
    AcquireSRWLockExclusive(&roster_lock);
    roster_live.count = 0;
    roster_live_at = 0;
    ReleaseSRWLockExclusive(&roster_lock);
}

static void roster_run(void) {
    unsigned char *tls = sim_tls_block();
    unsigned char *g = tls ? *(unsigned char **)(tls + 0x60) : NULL;
    if (!g || g[0] || !g[1]) return;
    unsigned long long instance = *(unsigned long long *)(g + 0x18);
    if (instance != roster_instance) {
        roster_instance = instance;
        roster_faulted = roster_said = 0;
        roster_clear();
    }
    if (roster_faulted) return;
    unsigned char *time = *(unsigned char **)(tls + 0x98);
    int tick = time ? *(int *)(time + 0x0c) : -1;
    if (!roster_read(*(unsigned char **)(tls + 0x30), *(unsigned char **)(tls + 0x118), *(unsigned char **)(tls + 0x20),
                     tick, &roster_scratch))
        return;
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    AcquireSRWLockExclusive(&roster_lock);
    roster_live = roster_scratch;
    roster_live_at = GetTickCount64();
    roster_live_qpc = now.QuadPart;
    ReleaseSRWLockExclusive(&roster_lock);
    if (!roster_said) {
        roster_said = 1;
        int alive = 0, here = 0;
        for (int i = 0; i < roster_scratch.count; i++) {
            alive += (roster_scratch.seats[i].flags & ROSTER_ALIVE) != 0;
            here += (roster_scratch.seats[i].flags & ROSTER_LOCAL) != 0;
        }
        fireteam_log("roster: first copy of this game at tick %d: %d player(s), %d alive, %d of this machine", tick,
                     roster_scratch.count, alive, here);
    }
}

/* On the simulation thread, every main tick (hook_main_tick). */
static void roster_tick(void) {
    unsigned long long now = GetTickCount64(), wanted = (unsigned long long)roster_wanted_at;
    if (!wanted || now - wanted > ROSTER_IDLE_MS) return;
    __try {
        roster_run();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        roster_faulted = 1;
        roster_clear();
        fireteam_log("roster: faulted (%08lx); off until the next game", GetExceptionCode());
    }
}

/* Marks the roster wanted and copies the latest snapshot out: NULL, or why
   there is none. `age`, when asked, is the copy's age in seconds. */
static const char *roster_take(roster_snapshot *out, double *age) {
    InterlockedExchange64(&roster_wanted_at, (LONG64)GetTickCount64());
    if (!main_tick_trampoline) {
        if (roster_no_tick) return "no main tick hook on this build";
        unsigned char *sim = (unsigned char *)GetModuleHandleA("HaloSimulation_tag_release.dll");
        if (!sim) return "no simulation";
        if (!install_main_tick(sim)) {
            InterlockedExchange(&roster_no_tick, 1);
            return "no main tick hook on this build";
        }
    }
    AcquireSRWLockShared(&roster_lock);
    unsigned long long at = roster_live_at;
    LONGLONG copied = roster_live_qpc;
    if (at) *out = roster_live;
    ReleaseSRWLockShared(&roster_lock);
    if (age) {
        LARGE_INTEGER now;
        QueryPerformanceCounter(&now);
        if (!roster_frequency.QuadPart) QueryPerformanceFrequency(&roster_frequency);
        *age = at && roster_frequency.QuadPart ? (double)(now.QuadPart - copied) / (double)roster_frequency.QuadPart : 0.0;
    }
    if (roster_faulted) return "faulted; off until the next game";
    if (!at) return "no copy yet";
    if (GetTickCount64() - at > ROSTER_STALE_MS) return "stale: the simulation is not ticking";
    return NULL;
}

__declspec(dllexport) int mjolnir_roster(void *L) {
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    /* On the caller's stack: the HUD's game-thread code and a LoopAsync can
       both call. */
    roster_snapshot copy;
    const char *why = roster_take(&copy, NULL);
    if (why) {
        lc_push_nil(&f);
        lc_push_text(&f, why);
        lc_end(&f);
        return 2;
    }
    unsigned char packed[ROSTER_PACKED_MAX];
    size_t n = roster_pack(&copy, packed, sizeof packed);
    lc_push_string(&f, (const char *)packed, n);
    lc_end(&f);
    return 1;
}

/* One seat, for a marker that follows a player every frame, without
   unpacking the whole roster: x, y, z (Unreal centimetres), whether they
   are alive, their velocity (cm/s) and the copy's age (seconds). The
   simulation moves 60 times a second, so a marker drawn faster than that
   carries the place on by velocity x age. */
__declspec(dllexport) int mjolnir_roster_at(void *L) {
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    long long index = lc_take_integer(&f, 1, -1);
    roster_snapshot copy;
    double age = 0.0;
    const char *why = index < 0 || index >= ROSTER_SEATS ? "no such seat" : roster_take(&copy, &age);
    const roster_seat *s = why ? NULL : roster_find(&copy, (int)index);
    if (!why && !s) why = "nobody in that seat";
    if (why) {
        lc_push_nil(&f);
        lc_push_text(&f, why);
        lc_end(&f);
        return 2;
    }
    lc_push_number(&f, s->at[0]);
    lc_push_number(&f, s->at[1]);
    lc_push_number(&f, s->at[2]);
    lc_push_bool(&f, (s->flags & ROSTER_ALIVE) != 0);
    lc_push_number(&f, s->velocity[0]);
    lc_push_number(&f, s->velocity[1]);
    lc_push_number(&f, s->velocity[2]);
    lc_push_number(&f, age);
    lc_end(&f);
    return 8;
}
