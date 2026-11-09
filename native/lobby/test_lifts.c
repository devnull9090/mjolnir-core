/* Portable tests for lifts_core.h: no game process or Windows headers. The
 * push cases are tools/tests/test_lifts.lua's, in the simulation's units. */
#include <stdio.h>
#include <stdlib.h>
#include "lifts_core.h"

static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
static int near_to(float a, float b, float tolerance) { return isfinite(a) && fabsf(a - b) <= tolerance; }

/* Lockout's lower lift, as lifts.lua writes it from the level file: a tube
   3.7 m across and 13.7 m tall, tilted 7 degrees. */
static const char LOCKOUT[] =
    "mjolnir-lifts 1\n"
    "lift lockout_lift_tube 1 -1.496719 12.517388 -12.201115 0 -0.1217 0.9926 -1.496719 12.244094 -9.96063 2.46063 "
    "10 4 10 10 0 0 planes 6\n"
    "plane 0 0.1217 -0.9926 -13.634186\n"
    "plane -1 0 0 -2.101706\n"
    "plane 0 -0.9926 -0.1217 10.344488\n"
    "plane 0 0.9926 0.1217 -11.55479\n"
    "plane 1 0 0 0.891732\n"
    "plane 0 -0.1217 0.9926 9.133858\n"
    "lift power_lift 0 0 0 0 0 0 1 0 0 1.7 2 1 4 0 0 0 0 pill 0 0 0 0 0 3.28 0.49\n"
    "end\n";

static lift_set set, scratch;

static int parse(const char *text, lift_set *out) {
    static char buffer[16384];
    size_t n = strlen(text);
    if (n >= sizeof buffer) return -1;
    memcpy(buffer, text, n + 1);
    return lift_parse(buffer, out);
}

static void test_parse(void) {
    CHECK(parse(LOCKOUT, &set) == 0);
    CHECK(set.count == 2 && set.plane_count == 6);
    CHECK(set.lifts[0].shape == LIFT_PLANES && set.lifts[0].planes == 6 && set.lifts[0].negates_gravity);
    CHECK(!strcmp(set.lifts[0].name, "lockout_lift_tube"));
    CHECK(set.lifts[1].shape == LIFT_PILL && near_to(set.lifts[1].radius, 0.49f, 1e-6f) && !set.lifts[1].negates_gravity);
    CHECK(near_to(lift_dot(set.lifts[0].forward, set.lifts[0].forward), 1.0f, 1e-5f));

    /* Windows line ends read the same. */
    char crlf[4096] = {0};
    size_t c = 0;
    for (const char *p = LOCKOUT; *p; p++) {
        if (*p == '\n') crlf[c++] = '\r';
        crlf[c++] = *p;
    }
    CHECK(parse(crlf, &scratch) == 0 && scratch.count == 2);
    CHECK(parse("mjolnir-lifts 1\nend\n", &scratch) == 0 && scratch.count == 0);
    CHECK(parse("mjolnir-lifts 1\nend", &scratch) == 0);

    /* Refused whole: the line number of the first bad line. */
    CHECK(parse("", &scratch) == 1);
    CHECK(parse("mjolnir-lifts 2\nend\n", &scratch) == 1);
    CHECK(parse("mjolnir-lifts 1\n", &scratch) == 2);                       /* no end: half written */
    CHECK(parse("mjolnir-lifts 1\nend\nend\n", &scratch) == 3);              /* nothing after end */
    CHECK(parse("mjolnir-lifts 1\n\nend\n", &scratch) != 0);                 /* no blank lines */
    CHECK(parse("mjolnir-lifts 1\nend \n", &scratch) == 2);                  /* trailing space */
    CHECK(parse("mjolnir-lifts 1\nplane 0 0 1 0\nend\n", &scratch) == 2);    /* a plane with no lift */
    CHECK(parse("mjolnir-lifts 1\nteleport 1 2 3\nend\n", &scratch) == 2);
    const char *pill = "lift a 0 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 pill 0 0 0 0 0 3 0.5\n";
    char text[1024];
    snprintf(text, sizeof text, "mjolnir-lifts 1\n%send\n", pill);
    CHECK(parse(text, &scratch) == 0);
    const char *bad[] = {
        "lift a 0 0 0 0 0 0 2 0 0 1 2 1 4 0 0 0 0 pill 0 0 0 0 0 3 0.5\n",    /* forward not a unit vector */
        "lift a 0 0 0 0 0 0 1 0 0 1 0 1 4 0 0 0 0 pill 0 0 0 0 0 3 0.5\n",    /* no bounding radius */
        "lift a 0 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 pill 0 0 0 0 0 3 0\n",      /* no pill radius */
        "lift a 2 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 pill 0 0 0 0 0 3 0.5\n",    /* negates is 0 or 1 */
        "lift a 0 nan 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 pill 0 0 0 0 0 3 0.5\n",
        "lift a 0 1e9 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 pill 0 0 0 0 0 3 0.5\n",
        "lift a 0 0 0 0 0 0 1 0 0 1 2 -1 4 0 0 0 0 pill 0 0 0 0 0 3 0.5\n",   /* negative acceleration */
        "lift a 0 0 0 0 0 0 1 0 0 1 2 1 400 0 0 0 0 pill 0 0 0 0 0 3 0.5\n",  /* top speed past 100 wu/s */
        "lift a b 0 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 pill 0 0 0 0 0 3 0.5\n",  /* one field too many */
        "lift a 0 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 pill 0 0 0 0 0 3\n",        /* one too few */
        "lift a/b 0 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 pill 0 0 0 0 0 3 0.5\n",  /* names are plain */
        "lift a 0 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 cube 0 0 0 0 0 3 0.5\n",
        "lift a 0 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 planes 0\n",
        "lift a 0 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 planes 1.5\n",
        "lift a 0 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 planes 257\n",
        "lift a 0 0 0 0 0 0 1 0 0 1 2 1 4 0 0 0 0 planes 2\nplane 0 0 1 0\n", /* one plane short */
    };
    for (size_t i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        snprintf(text, sizeof text, "mjolnir-lifts 1\n%send\n", bad[i]);
        CHECK(parse(text, &scratch) == 2 || (i == 15 && parse(text, &scratch) == 4));
    }
    /* Too many phantoms. */
    static char many[(LIFT_MAX + 3) * 80];
    size_t at = (size_t)snprintf(many, sizeof many, "mjolnir-lifts 1\n");
    for (int i = 0; i <= LIFT_MAX; i++) at += (size_t)snprintf(many + at, sizeof many - at, "%s", pill);
    snprintf(many + at, sizeof many - at, "end\n");
    CHECK(lift_parse(many, &scratch) == LIFT_MAX + 2);
}

static void test_inside(void) {
    const lift_phantom *tube = &set.lifts[0], *pill = &set.lifts[1];
    const float *o = tube->origin, *f = tube->forward;
    const float up1[3] = {o[0] + 0.328f * f[0], o[1] + 0.328f * f[1], o[2] + 0.328f * f[2]};
    float below[3] = {o[0], o[1], o[2] - 0.164f}, beside[3] = {o[0] + 0.984f, up1[1], up1[2]};
    CHECK(lift_inside(&set, tube, up1));       /* a metre up the tube */
    CHECK(!lift_inside(&set, tube, below));    /* half a metre under it */
    CHECK(!lift_inside(&set, tube, beside));   /* three metres beside it */
    CHECK(lift_near(tube, o));
    float far[3] = {o[0] + 6.56f, o[1], o[2]};
    CHECK(!lift_near(tube, far));              /* 20 m away */
    float tip[3] = {0, 0, 3.76f};              /* the pill's cap, past its tight bounds */
    CHECK(lift_near(pill, tip) && lift_inside(&set, pill, tip));
    float a[3] = {0.328f, 0, 1.64f}, cap[3] = {0, 0, 3.6f}, out[3] = {0.66f, 0, 1.64f}, under[3] = {0, 0, -0.66f};
    CHECK(lift_inside(&set, pill, a));
    CHECK(lift_inside(&set, pill, cap));
    CHECK(!lift_inside(&set, pill, out));
    CHECK(!lift_inside(&set, pill, under));
}

static void test_push(void) {
    const lift_phantom *tube = &set.lifts[0];
    const float *o = tube->origin, *f = tube->forward;
    const float up1[3] = {o[0] + 0.328f * f[0], o[1] + 0.328f * f[1], o[2] + 0.328f * f[2]};
    const float dt = 0.05f, step = 10.0f * dt * 0.9926f; /* 3048 cm/s^2 up a 7-degree tube */
    float v[3] = {0, 0, 0};
    lift_push(tube, up1, v, dt, NULL);
    CHECK(near_to(v[2], step, 0.002f));
    CHECK(near_to(v[0], 0, 1e-4f));            /* on the axis: no sideways push */
    float sent[3] = {v[0], v[1], v[2]};
    lift_sent(sent, 1, dt);
    CHECK(near_to(sent[2], v[2] + LIFT_GRAVITY * dt, 1e-5f));
    /* The ground holds a biped still after a small push: the last push's
       speed carries on, so the lift gains a step each time. */
    float first[3] = {0, 0, 0}, second[3] = {0, 0, 0};
    lift_push(tube, up1, first, dt, NULL);
    lift_push(tube, up1, second, dt, first);
    CHECK(near_to(second[2], first[2] + step, 0.002f));
    /* Twenty steps from still reach the top speed, 4 wu/s, and no more. */
    float w[3] = {0, 0, 0};
    for (int i = 0; i < 20; i++) {
        float still[3] = {0, 0, 0}, last[3] = {w[0], w[1], w[2]};
        lift_push(tube, up1, still, dt, i ? last : NULL);
        memcpy(w, still, sizeof w);
    }
    CHECK(near_to(lift_dot(w, f), 4.0f, 0.004f));
    float top[3] = {4.0f * f[0], 4.0f * f[1], 4.0f * f[2]}, held[3] = {top[0], top[1], top[2]};
    lift_push(tube, up1, held, dt, NULL);
    CHECK(near_to(held[2], top[2], 0.002f));
    /* A metre off the axis the pull is towards it, slowing into it. */
    float off[3] = {up1[0] + 0.328f, up1[1], up1[2]}, pulled[3] = {0, 0, 0};
    lift_push(tube, off, pulled, dt, NULL);
    CHECK(pulled[0] < 0 && pulled[0] >= -1000.0f / LIFT_WU_CM);
    /* A phantom that does not hold gravity off carries less the next push. */
    lift_phantom heavy = *tube;
    heavy.negates_gravity = 0;
    float g1[3] = {0, 0, 0}, g2[3] = {0, 0, 0};
    lift_push(&heavy, up1, g1, dt, NULL);
    lift_push(&heavy, up1, g2, dt, g1);
    CHECK(near_to(lift_dot(g2, f), lift_dot(g1, f) * 2 - LIFT_GRAVITY * dt * f[2], 0.001f));
    /* Horizontal steering survives a vertical push. */
    lift_phantom pad = set.lifts[1];
    float steer[3] = {1.25f, -0.5f, 0}, at[3] = {0, 0, 1.0f};
    pad.axis[0] = pad.center[0] = 0;
    lift_push(&pad, at, steer, dt, NULL);
    CHECK(steer[0] == 1.25f && steer[1] == -0.5f && steer[2] > 0);
}

/* The simulation as measured on CU4 (docs/re/lift_push.md): 60 ticks a
   second, a biped's velocity loses gravity every other tick, two ticks' worth
   at once. Pushed every tick through Lockout's tube, the speed along it must
   settle at the top speed, not ratchet past it. */
static float ride(const lift_phantom *lift, const float at[3], int ticks, float start) {
    const float dt = 1.0f / 60.0f;
    const float *f = lift->forward;
    float v[3] = {f[0] * start, f[1] * start, f[2] * start}, last[3] = {0, 0, 0}, top = -1e9f;
    int has_last = 0;
    for (int t = 0; t < ticks; t++) {
        float push[3] = {v[0], v[1], v[2]};
        lift_push(lift, at, push, dt, has_last ? last : NULL);
        memcpy(last, push, sizeof last);
        has_last = 1;
        lift_sent(push, lift->negates_gravity, dt);
        memcpy(v, push, sizeof v);
        if (t % 2) v[2] -= LIFT_GRAVITY * 2.0f * dt; /* the simulation's own step */
        float along = lift_dot(v, f);
        if (t > ticks / 2 && along > top) top = along;
    }
    return top;
}

static void test_ratchet(void) {
    const lift_phantom *tube = &set.lifts[0];
    const float *o = tube->origin, *f = tube->forward;
    const float at[3] = {o[0] + 1.0f * f[0], o[1] + 1.0f * f[1], o[2] + 1.0f * f[2]};
    /* From still and from the top speed: held within a tick's gravity of 4. */
    float top = ride(tube, at, 240, 0.0f);
    CHECK(top <= 4.0f + LIFT_GRAVITY / 60.0f + 0.002f && top >= 4.0f - 2.0f * LIFT_GRAVITY / 60.0f);
    top = ride(tube, at, 240, 4.0f);
    CHECK(top <= 4.0f + LIFT_GRAVITY / 60.0f + 0.002f);
    /* A pad that does not hold gravity off still feels all of it: Midship's
       power lift (18 wu/s^2 up to 3.8 wu/s) reaches its top speed less
       gravity's share, and no more. */
    lift_phantom pad = set.lifts[1];
    pad.direction[0] = 18.0f, pad.direction[1] = 3.8f;
    const float up[3] = {0, 0, 1.0f};
    top = ride(&pad, up, 240, 0.0f);
    CHECK(top <= 3.8f + 0.002f && top >= 3.8f - 2.0f * LIFT_GRAVITY / 60.0f - 0.002f);
    /* Standing: the ground reads still after every push, and the carry still
       lifts. */
    float still[3] = {0, 0, 0}, last[3] = {0, 0, 0};
    for (int t = 0; t < 30; t++) {
        float push[3] = {0, 0, 0};
        lift_push(tube, at, push, 1.0f / 60.0f, t ? last : NULL);
        memcpy(last, push, sizeof last);
        memcpy(still, push, sizeof still);
    }
    CHECK(lift_dot(still, f) > 4.0f - 0.01f);
}

static void test_frame(void) {
    /* object_set_velocity's frame: forward, left (up x forward), up. */
    const float x[3] = {1, 0, 0}, z[3] = {0, 0, 1};
    float out[3], v[3] = {1, 0, 0};
    lift_unit_frame(v, x, z, out);
    CHECK(near_to(out[0], 1, 1e-6f) && near_to(out[1], 0, 1e-6f) && near_to(out[2], 0, 1e-6f));
    v[0] = 0, v[1] = 1;
    lift_unit_frame(v, x, z, out);
    CHECK(near_to(out[1], 1, 1e-6f));          /* the sim's +y is left of +x (Unreal's -Y) */
    /* PC 2's push "4 0 0" at Unreal yaw 110.8 moved it along Unreal
       (-0.355, 0.935): the sim's (-0.355, -0.935). */
    const float yaw[3] = {-0.35511f, -0.93483f, 0};
    float moved[3] = {-0.355f * 4.0f, -0.935f * 4.0f, 0};
    lift_unit_frame(moved, yaw, z, out);
    CHECK(near_to(out[0], 4, 0.01f) && near_to(out[1], 0, 0.01f));
    /* The engine's rebuild of a tilted object's velocity gives it back. */
    const float s = 0.70710678f, fwd[3] = {s, 0, s}, up[3] = {-s, 0, s};
    float any[3] = {0.3f, -2.0f, 1.5f};
    lift_unit_frame(any, fwd, up, out);
    float left[3] = {up[1] * fwd[2] - up[2] * fwd[1], up[2] * fwd[0] - up[0] * fwd[2], up[0] * fwd[1] - up[1] * fwd[0]};
    for (int k = 0; k < 3; k++) CHECK(near_to(out[0] * fwd[k] + out[1] * left[k] + out[2] * up[k], any[k], 1e-5f));
}

/* The file lifts.lua writes for Lockout's tube and Midship's power lift
   (tools/tests/test_lifts.lua checks it is exactly what serialize writes). */
static void test_fixture(const char *path) {
    static char text[1 << 16];
    FILE *f = fopen(path, "rb");
    CHECK(f != NULL);
    size_t n = fread(text, 1, sizeof text - 1, f);
    fclose(f);
    text[n] = 0;
    CHECK(lift_parse(text, &scratch) == 0);
    CHECK(scratch.count == 2 && scratch.plane_count == 6);
    CHECK(!strcmp(scratch.lifts[0].name, "lockout_lift_tube") && !strcmp(scratch.lifts[1].name, "cov_power_lift"));
    CHECK(scratch.lifts[1].shape == LIFT_PILL && near_to(scratch.lifts[1].radius, 0.5f, 1e-6f));
    CHECK(near_to(scratch.lifts[1].direction[0], 18.0f, 1e-5f) && !scratch.lifts[1].negates_gravity);
    /* The same tube as LOCKOUT: the same points are in and out. */
    const lift_phantom *tube = &scratch.lifts[0];
    const float *o = tube->origin, *fw = tube->forward;
    const float up1[3] = {o[0] + 0.328f * fw[0], o[1] + 0.328f * fw[1], o[2] + 0.328f * fw[2]};
    float below[3] = {o[0], o[1], o[2] - 0.164f};
    CHECK(lift_near(tube, up1) && lift_inside(&scratch, tube, up1) && !lift_inside(&scratch, tube, below));
    /* A metre above the power lift's lower end. */
    const float *a = scratch.lifts[1].pill[0];
    float above[3] = {a[0], a[1], a[2] + 0.328f};
    CHECK(lift_inside(&scratch, &scratch.lifts[1], above));
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: test_lifts <tools/tests/fixtures/lifts_lockout_midship.txt>\n");
        return 2;
    }
    test_fixture(argv[1]);
    test_parse();
    test_inside();
    test_push();
    test_ratchet();
    test_frame();
    printf("test_lifts: %d checks ok\n", checks);
    return 0;
}
