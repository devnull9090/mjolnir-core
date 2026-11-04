/* Portable tests: no game process, DLL injection, or Windows headers needed. */
#include <stdio.h>
#include <stdlib.h>
#include "forge_doors_core.h"

static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
static int close_to(float a, float b) { return isfinite(a) && fabsf(a - b) < .0001f; }
static const char row[] = "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t4\t4\t8\t16\t6\t2\t4\t0.5\t2.5";

static void test_authored_binding(void) {
    const uint32_t handle = 0xe3830114u, tag = 0xf1e6106eu;
    /* Actual authored Crossline entry 270: object points back to it, but
       the entry handle remains -1. Explicit live linkage also works. */
    CHECK(forge_door_binding(handle, UINT32_MAX, 270, 270, tag, tag));
    CHECK(forge_door_binding(handle, handle, 270, 270, tag, tag));
    CHECK(!forge_door_binding(handle, 0xe3840114u, 270, 270, tag, tag));
    CHECK(!forge_door_binding(handle, 0xe3830115u, 270, 270, tag, tag));
    CHECK(!forge_door_binding(handle, 0, 270, 270, tag, tag));
    CHECK(!forge_door_binding(handle, UINT32_MAX, 271, 270, tag, tag));
    CHECK(!forge_door_binding(handle, UINT32_MAX, -1, -1, tag, tag));
    CHECK(!forge_door_binding(handle, UINT32_MAX, 651, 651, tag, tag));
    CHECK(!forge_door_binding(handle, UINT32_MAX, 270, 270, tag, tag + 1));
    CHECK(!forge_door_binding(handle, UINT32_MAX, 270, 270, tag, tag ^ 0x10000u));
    CHECK(!forge_door_binding(handle, UINT32_MAX, 270, 270, tag, UINT32_MAX));
    CHECK(!forge_door_binding(UINT32_MAX, UINT32_MAX, 270, 270, tag, tag));
    CHECK(!forge_door_binding(0x114, UINT32_MAX, 270, 270, tag, tag));
    CHECK(!forge_door_binding(handle, UINT32_MAX, 270, 270, UINT32_MAX, UINT32_MAX));
    CHECK(!forge_door_binding(handle, UINT32_MAX, 270, 270, 0x106e, 0x106e));
}

static int physics_resolves;
static int resolve_physics(uint32_t tag, void *context) {
    physics_resolves++;
    return tag == *(const uint32_t *)context;
}

static void test_stationary_physics(void) {
    unsigned char bodies[64 * 0xd0] = {0};
    CHECK(!forge_door_fixed_bodies(NULL, 1));
    CHECK(!forge_door_fixed_bodies(bodies, 0));
    CHECK(!forge_door_fixed_bodies(bodies, -1));
    CHECK(!forge_door_fixed_bodies(bodies, 65));
    for (int i = 0; i < 64; i++) bodies[i * 0xd0 + 0x1c] = 5;
    CHECK(forge_door_fixed_bodies(bodies, 1));
    CHECK(forge_door_fixed_bodies(bodies, 64));
    for (unsigned motion = 0; motion < 256; motion++) {
        bodies[63 * 0xd0 + 0x1c] = (unsigned char)motion;
        CHECK(forge_door_fixed_bodies(bodies, 64) == (motion == 5));
    }
    /* The same fixed construction and dynamic stock tag can occur hundreds
       of times; neither should traverse model/PHMO data after its first use. */
    forge_door_physics_cache cache = {0};
    uint32_t fixed = 0xf1e6106eu, dynamic = 0xf1e6106fu;
    physics_resolves = 0;
    for (int i = 0; i < 1000; i++) {
        CHECK(forge_door_cached_fixed(&cache, fixed, resolve_physics, &fixed));
        CHECK(!forge_door_cached_fixed(&cache, dynamic, resolve_physics, &fixed));
    }
    CHECK(physics_resolves == 2 && cache.count == 2);
    /* A reused index with a new salt requires a new classification. */
    CHECK(!forge_door_cached_fixed(&cache, fixed ^ 0x10000u, resolve_physics, &fixed));
    CHECK(physics_resolves == 3);
    CHECK(!forge_door_cached_fixed(&cache, UINT32_MAX, resolve_physics, &fixed));
    CHECK(!forge_door_cached_fixed(&cache, 0x106e, resolve_physics, &fixed));
    CHECK(!forge_door_cached_fixed(&cache, 0xabcd0001u, NULL, &fixed));
    CHECK(physics_resolves == 3);
    while (cache.count < FORGE_DOOR_PHYSICS_CACHE)
        CHECK(!forge_door_cached_fixed(&cache, 0xabcd0000u + cache.count, resolve_physics, &fixed));
    int before = physics_resolves;
    for (int i = 0; i < 100; i++)
        CHECK(!forge_door_cached_fixed(&cache, 0xbcde0001u, resolve_physics, &fixed));
    CHECK(physics_resolves == before);
    CHECK(forge_door_cached_fixed(&cache, fixed, resolve_physics, &fixed));
    /* World change clears both answers, including former fixed tags. */
    memset(&cache, 0, sizeof cache);
    fixed++;
    CHECK(!forge_door_cached_fixed(&cache, 0xf1e6106eu, resolve_physics, &fixed));
    CHECK(physics_resolves == before + 1);
}

static forge_door_config config(void) {
    char line[512];
    forge_door_config c;
    memcpy(line, row, sizeof row);
    CHECK(forge_door_parse(line, &c));
    return c;
}

static int parse(const char *s, forge_door_config *c) {
    char line[1024];
    CHECK(strlen(s) < sizeof line);
    memcpy(line, s, strlen(s) + 1);
    return forge_door_parse(line, c);
}

static void test_inventory_parser(void) {
    forge_door_config c = config(), before;
    CHECK(!strcmp(c.tag, "objects\\mjolnir\\forge\\foundry-wide\\door_panel"));
    CHECK(close_to(c.travel, 4) && close_to(c.speed, 4) && close_to(c.hold, 2));
    CHECK(close_to(c.trigger[0], 8) && close_to(c.trigger[1], 16) && close_to(c.trigger[2], 6));
    CHECK(close_to(c.size[0], 4) && close_to(c.size[1], .5f) && close_to(c.size[2], 2.5f));
    CHECK(parse("objects\\mjolnir\\forge\\foundry-wide\\door_vehicle_panel\t6\t4\t12\t20\t8\t2\t8\t1\t4\r\n", &c));
    CHECK(close_to(c.travel, 6) && close_to(c.size[2], 4));
    const char *bad[] = {
        "", "forge-doors 1", "objects\\mjolnir\\forge\\foundry-wide\\door_panel",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t4\t4\t8\t16\t6\t2\t4\t.5",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t4\t4\t8\t16\t6\t2\t4\t.5\t2.5\textra",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t\t4\t8\t16\t6\t2\t4\t.5\t2.5",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t 4\t4\t8\t16\t6\t2\t4\t.5\t2.5",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t4 \t4\t8\t16\t6\t2\t4\t.5\t2.5",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\tNaN\t4\t8\t16\t6\t2\t4\t.5\t2.5",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t4\tInf\t8\t16\t6\t2\t4\t.5\t2.5",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t4\t4\t8\t16\t6\t1e99\t4\t.5\t2.5",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t4\t4\t8\t16\t6\t2\t4\t.5\t2.5x",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t4\t4\t8\t16\t6\t2\t4\t.5\t2.5\nother",
        "objects\\mjolnir\\forge\\foundry-wide\\door_panel\t4\t4\t8\t16\t6\t2\t4\t.5\t\v2.5",
    };
    before = c;
    for (size_t i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        CHECK(!parse(bad[i], &c));
        CHECK(!memcmp(&before, &c, sizeof c)); /* A rejected row cannot publish partial data. */
    }
    const char *bad_tags[] = {
        "objects\\mjolnir\\forge\\a\\door", "objects\\mjolnir\\forge\\Upper\\door",
        "objects\\mjolnir\\forge\\foundry_wide\\door", "objects\\mjolnir\\forge\\wide\\../door",
        "objects\\mjolnir\\forge\\wide\\door\\nested", "objects\\mjolnir\\forge\\wide\\",
        "objects/mjolnir/forge/wide/door", "objects\\stock\\door", "objects\\mjolnir\\forge\\wide\\door\n",
    };
    for (size_t i = 0; i < sizeof bad_tags / sizeof bad_tags[0]; i++) CHECK(!forge_door_tag(bad_tags[i]));
    char maximum[224] = "objects\\mjolnir\\forge\\";
    size_t prefix = strlen(maximum);
    memset(maximum + prefix, 'a', 64); maximum[prefix + 64] = '\\';
    memset(maximum + prefix + 65, 'b', 64); maximum[prefix + 129] = 0;
    CHECK(forge_door_tag(maximum));
    maximum[prefix + 129] = 'b'; maximum[prefix + 130] = 0;
    CHECK(!forge_door_tag(maximum));

    c = config();
    float *fields[] = {&c.travel, &c.speed, &c.trigger[0], &c.trigger[1], &c.trigger[2], &c.hold, &c.size[0], &c.size[1], &c.size[2]};
    const float upper[] = {16, 8, 32, 32, 32, 10, 64, 64, 64};
    for (int i = 0; i < 9; i++) {
        float saved = *fields[i];
        *fields[i] = upper[i]; CHECK(forge_door_config_valid(&c));
        *fields[i] = upper[i] + .01f; CHECK(!forge_door_config_valid(&c));
        *fields[i] = 0; CHECK(forge_door_config_valid(&c) == (i == 5));
        *fields[i] = -.01f; CHECK(!forge_door_config_valid(&c));
        *fields[i] = NAN; CHECK(!forge_door_config_valid(&c));
        *fields[i] = INFINITY; CHECK(!forge_door_config_valid(&c));
        *fields[i] = saved;
    }
}

static void test_transforms_and_triggers(void) {
    forge_door_config c = config();
    const float origin[3] = {103, -45, 8};
    /* Sweep yaw and pitch: source +X is forward, +Y is left, travel is +Z. */
    for (int yaw = -180; yaw <= 180; yaw += 15) {
        for (int pitch = -90; pitch <= 90; pitch += 30) {
            float y = yaw * .01745329252f, p = pitch * .01745329252f;
            float f[3] = {cosf(y)*cosf(p), sinf(y)*cosf(p), sinf(p)};
            float u[3] = {-cosf(y)*sinf(p), -sinf(y)*sinf(p), cosf(p)}, l[3], point[3], local[3];
            CHECK(forge_door_basis(f, u, l));
            for (int k = 0; k < 3; k++) point[k] = origin[k] + f[k]*1.25f - l[k]*2 + u[k]*3.5f;
            CHECK(forge_door_local(point, origin, f, l, u, local));
            CHECK(close_to(local[0], 1.25f) && close_to(local[1], -2) && close_to(local[2], 3.5f));
            CHECK(forge_door_trigger(&c, local));
        }
    }
    float f[3] = {1,0,0}, u[3] = {0,0,1}, l[3], local[3];
    CHECK(forge_door_basis(f,u,l)); CHECK(close_to(l[1],1));
    f[0] = 2; CHECK(!forge_door_basis(f,u,l));
    f[0] = NAN; CHECK(!forge_door_basis(f,u,l));
    f[0] = 1; u[0] = .1f; CHECK(!forge_door_basis(f,u,l));
    u[0] = 0; u[2] = INFINITY; CHECK(!forge_door_basis(f,u,l));
    u[2] = 1; CHECK(!forge_door_local((float[3]){NAN,0,0}, origin,f,l,u,local));
    CHECK(!forge_door_local(origin,(float[3]){INFINITY,0,0},f,l,u,local));
    const float edges[][3] = {{4,0,0},{-4,0,0},{0,8,0},{0,-8,0},{0,0,-.5f},{0,0,6}};
    for (int i = 0; i < 6; i++) {
        CHECK(forge_door_trigger(&c, edges[i]));
        memcpy(local, edges[i], sizeof local);
        int axis = i / 2;
        local[axis] += i < 4 ? (i % 2 ? -.001f : .001f) : (i == 4 ? -.001f : .001f);
        CHECK(!forge_door_trigger(&c, local));
    }
    CHECK(!forge_door_trigger(&c,(float[3]){0,0,NAN}));
}

static void test_obstruction_sweep(void) {
    forge_door_config c = config();
    /* Closing from 4 to 3 crosses Z 2.9..6.6 after the 10 cm margin. */
    CHECK(forge_door_swept_blocked(&c,4,3,(float[3]){0,0,4},0));
    CHECK(forge_door_swept_blocked(&c,4,3,(float[3]){0,0,2.8f},.11f));
    CHECK(!forge_door_swept_blocked(&c,4,3,(float[3]){0,0,2.7f},.1f));
    CHECK(forge_door_swept_blocked(&c,3,4,(float[3]){0,0,6.7f},.11f));
    CHECK(!forge_door_swept_blocked(&c,3,4,(float[3]){0,0,6.9f},.1f));
    /* A sphere's corner distance is Euclidean, not an inflated box. */
    CHECK(!forge_door_swept_blocked(&c,4,3,(float[3]){2.7f,.95f,4},.8f));
    CHECK(forge_door_swept_blocked(&c,4,3,(float[3]){2.7f,.95f,4},.9f));
    for (int z = -4; z <= 10; z++) {
        for (int x = -4; x <= 4; x++) {
            float p[3] = {(float)x,.25f,(float)z};
            CHECK(forge_door_swept_blocked(&c,0,4,p,.5f) == forge_door_swept_blocked(&c,4,0,p,.5f));
        }
    }
    CHECK(forge_door_swept_blocked(&c,0,0,(float[3]){0,0,1},0));
    CHECK(!forge_door_swept_blocked(&c,0,0,(float[3]){0,0,5},.5f));
    CHECK(forge_door_swept_blocked(&c,0,1,(float[3]){NAN,0,0},1));
    CHECK(forge_door_swept_blocked(&c,0,1,(float[3]){0,0,0},NAN));
    CHECK(forge_door_swept_blocked(&c,0,1,(float[3]){0,0,0},-1));
    CHECK(forge_door_swept_blocked(&c,0,1,(float[3]){0,0,0},129));
    CHECK(forge_door_swept_blocked(&c,INFINITY,1,(float[3]){0,0,0},1));
}

static void test_motion_timing(void) {
    forge_door_config c = config();
    forge_door_motion m = {0,0};
    /* Half-second approaches are independent of 20/60/100 Hz stepping. */
    for (int rate = 20; rate <= 100; rate += 20) {
        m = (forge_door_motion){0,0};
        for (int i = 0; i < rate / 2; i++) forge_door_advance(&c,&m,1.0f/rate,1,0,0);
        CHECK(close_to(m.offset,2)); CHECK(close_to(m.wait,2));
    }
    m = (forge_door_motion){0,0};
    for (int i = 0; i < 30; i++) forge_door_advance(&c,&m,.05f,1,0,0);
    CHECK(close_to(m.offset,4));
    const float bad_dt[] = {0,-.1f,.1001f,10,NAN,INFINITY};
    for (size_t i = 0; i < sizeof bad_dt / sizeof bad_dt[0]; i++) {
        forge_door_motion before = m;
        CHECK(close_to(forge_door_advance(&c,&m,bad_dt[i],0,0,0),4));
        CHECK(!memcmp(&before,&m,sizeof m)); /* Paused/catch-up frames do not consume hold. */
    }
    for (int i = 0; i < 38; i++) forge_door_advance(&c,&m,.05f,0,0,0);
    CHECK(close_to(m.offset,4)); CHECK(close_to(m.wait,.1f));
    for (int i = 0; i < 3; i++) forge_door_advance(&c,&m,.05f,0,0,0);
    CHECK(m.offset < 4 && m.offset >= 3.4f);
    for (int i = 0; i < 30; i++) forge_door_advance(&c,&m,.05f,0,0,0);
    CHECK(close_to(m.offset,0));
    /* A player/vehicle in the closing sweep requests reopening and renews hold. */
    m = (forge_door_motion){2,0};
    CHECK(close_to(forge_door_advance(&c,&m,.05f,0,1,0),2.2f)); CHECK(close_to(m.wait,2));
    CHECK(close_to(forge_door_advance(&c,&m,0,1,1,1),0)); CHECK(close_to(m.wait,0));
    m = (forge_door_motion){NAN,NAN};
    CHECK(close_to(forge_door_advance(&c,&m,.05f,0,0,0),0));
    m = (forge_door_motion){5,0};
    CHECK(close_to(forge_door_advance(&c,&m,.05f,0,0,0),0));
    c.hold = 0; m = (forge_door_motion){1,0};
    CHECK(close_to(forge_door_advance(&c,&m,.05f,0,0,0),.8f));
}

static void test_bounds(void) {
    const float zero[6] = {0, 0, 0, 0, 0, 0}, box[6] = {-20, 20, -30, 30, -1, 10};
    const float inside[3] = {-13.1f, -16, 0.5f}, outside[3] = {-21, 0, 0}, above[3] = {0, 0, 10.5f};
    const float origin[3] = {0, 0, 0}, nan_pos[3] = {NAN, 0, 0};
    float nan_box[6] = {-20, 20, -30, 30, -1, 10};
    nan_box[3] = NAN;
    /* Slayer and other modes: nothing to check against, but still finite. */
    CHECK(forge_door_in_bounds(inside, zero));
    CHECK(forge_door_in_bounds(origin, zero));
    CHECK(!forge_door_in_bounds(nan_pos, zero));
    /* Forge: a real box is enforced on every axis. */
    CHECK(forge_door_in_bounds(inside, box));
    CHECK(!forge_door_in_bounds(outside, box));
    CHECK(!forge_door_in_bounds(above, box));
    CHECK(!forge_door_in_bounds(nan_pos, box));
    CHECK(!forge_door_in_bounds(inside, nan_box));
}

int main(void) {
    test_authored_binding();
    test_stationary_physics();
    test_inventory_parser(); test_transforms_and_triggers();
    test_obstruction_sweep(); test_motion_timing(); test_bounds();
    printf("test_forge_doors: %d checks passed\n",checks);
    return 0;
}
