#include <float.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "placement_controls.h"

static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

static int close_metres(float units, float metres) {
    return fabsf(units * FORGE_METRES_PER_UNIT - metres) < 0.0001f;
}

static int close_degrees(float radians, float expected) {
    float difference = radians - expected * 0.01745329252f;
    return isfinite(radians) && fabsf(atan2f(sinf(difference), cosf(difference))) < 0.00001f;
}

static void test_turn_yaw(void) {
    const float radians = 0.01745329252f;
    /* These off-grid marker headings exposed the difference between native
       held-object snapping and merely adding the increment to a marker. */
    CHECK(close_degrees(forge_turn_yaw(17 * radians, 1, 90), 90));
    CHECK(close_degrees(forge_turn_yaw(-73 * radians, -1, 90), -90));
    CHECK(close_degrees(forge_turn_yaw(-73 * radians, 1, 90), 0));
    CHECK(close_degrees(forge_turn_yaw(17 * radians, -1, 90), 0));
    CHECK(close_degrees(forge_turn_yaw(180 * radians, 1, 90), -90));
    CHECK(close_degrees(forge_turn_yaw(-180 * radians, -1, 90), 90));
    CHECK(close_degrees(forge_turn_yaw(170 * radians, 1, 90), 180));
    CHECK(close_degrees(forge_turn_yaw(-170 * radians, -1, 90), -180));
    CHECK(close_degrees(forge_turn_yaw(17 * radians, 1, 0), 39.5f));
    CHECK(close_degrees(forge_turn_yaw(-73 * radians, -1, 0), -95.5f));
    CHECK(close_degrees(forge_turn_yaw(175 * radians, 1, 0), -162.5f));
    CHECK(close_degrees(forge_turn_yaw(-175 * radians, -1, 0), 162.5f));
    CHECK(close_degrees(forge_turn_yaw(377 * radians, 0, 90), 17));
    for (int setting = 1; setting < 6; setting++) {
        int degrees = FORGE_ROTATION_DEGREES[setting];
        float step = (float)degrees;
        /* Include every negative/positive boundary and both sides of the
           roundoff tolerance. No key press may stick on the current cell. */
        for (int cell = -180 / degrees; cell <= 180 / degrees; cell++) {
            float at = cell * step;
            CHECK(close_degrees(forge_turn_yaw(at * radians, 1, degrees), at + step));
            CHECK(close_degrees(forge_turn_yaw(at * radians, -1, degrees), at - step));
            CHECK(close_degrees(forge_turn_yaw((at - step * .00005f) * radians, 1, degrees), at + step));
            CHECK(close_degrees(forge_turn_yaw((at + step * .00005f) * radians, -1, degrees), at - step));
            CHECK(close_degrees(forge_turn_yaw((at - step * .001f) * radians, 1, degrees), at));
            CHECK(close_degrees(forge_turn_yaw((at + step * .001f) * radians, -1, degrees), at));
            float turned = forge_turn_yaw(at * radians, 1, degrees);
            CHECK(close_degrees(forge_turn_yaw(turned, -1, degrees), at));
        }
        float yaw = 17 * radians;
        for (int n = 0; n < 360 / degrees; n++) yaw = forge_turn_yaw(yaw, 1, degrees);
        /* After a full cycle from off-grid, land on the preceding boundary. */
        CHECK(close_degrees(yaw, floorf(17 / step) * step));
    }
    CHECK(isnan(forge_turn_yaw(NAN, 1, 90)));
    CHECK(isnan(forge_turn_yaw(INFINITY, 1, 90)));
    CHECK(isnan(forge_turn_yaw(-INFINITY, -1, 0)));
    CHECK(isnan(forge_turn_yaw(0, 1, -5)));
}

static void test_pose_validation(void) {
    const float bounds[6] = {-64, 64, -96, 96, -8, 64};
    const float forward[3] = {1, 0, 0}, up[3] = {0, 0, 1};
    const float origin[3] = {0, 0, 0};
    CHECK(forge_pose_in_bounds(origin, forward, up, bounds));
    for (int axis = 0; axis < 3; axis++) {
        for (int side = 0; side < 2; side++) {
            float point[3] = {0, 0, 0};
            point[axis] = bounds[axis * 2 + side];
            CHECK(forge_pose_in_bounds(point, forward, up, bounds));
            /* A pre-move callback can shift a previously valid snapped
               point outside the map, so validate the returned pose too. */
            point[axis] += side ? .01f : -.01f;
            CHECK(!forge_pose_in_bounds(point, forward, up, bounds));
        }
        float inverted[6]; memcpy(inverted, bounds, sizeof inverted);
        inverted[axis * 2] = bounds[axis * 2 + 1] + 1;
        CHECK(!forge_pose_in_bounds(origin, forward, up, inverted));
    }
    const float invalid[] = {NAN, INFINITY, -INFINITY};
    for (int bad = 0; bad < 3; bad++) {
        for (int axis = 0; axis < 3; axis++) {
            float bad_vector[3] = {0, 0, 0}; bad_vector[axis] = invalid[bad];
            CHECK(!forge_pose_in_bounds(bad_vector, forward, up, bounds));
            CHECK(!forge_pose_in_bounds(origin, bad_vector, up, bounds));
            CHECK(!forge_pose_in_bounds(origin, forward, bad_vector, bounds));
        }
        for (int bound = 0; bound < 6; bound++) {
            float bad_bounds[6]; memcpy(bad_bounds, bounds, sizeof bad_bounds);
            bad_bounds[bound] = invalid[bad];
            CHECK(!forge_pose_in_bounds(origin, forward, up, bad_bounds));
        }
    }
    const float large_bounds[6] = {-40000, 40000, -40000, 40000, -40000, 40000};
    const float allowed[3] = {-32767, 32767, 32767};
    CHECK(forge_pose_in_bounds(allowed, forward, up, large_bounds));
    for (int axis = 0; axis < 3; axis++) {
        float outside[3] = {0, 0, 0}; outside[axis] = 32768;
        CHECK(!forge_pose_in_bounds(outside, forward, up, large_bounds));
        outside[axis] = -32768;
        CHECK(!forge_pose_in_bounds(outside, forward, up, large_bounds));
    }
}

static void test_physics_properties(void) {
    const char *names[] = {"normal", "fixed", "phased"};
    const uint8_t next_flags[] = {0x40, 0x80, 0x00};
    uint8_t props[28], original[28];
    /* Every possible existing flag byte can arrive from a saved layout.
       Exercise complete cycles, preserving shapes, teams, labels, channels
       and all lower flags rather than testing an empty property block. */
    for (int flags = 0; flags < 256; flags++) {
        for (int k = 0; k < 28; k++) props[k] = (uint8_t)(k * 37 + flags);
        props[FORGE_PHYSICS_FLAGS] = (uint8_t)flags;
        memcpy(original, props, sizeof original);
        int initial = flags >= 128 ? 2 : flags >= 64 ? 1 : 0;
        CHECK(forge_physics_mode(props) == initial);
        CHECK(!strcmp(forge_physics_name(initial), names[initial]));
        for (int step = 0; step < 6; step++) {
            int previous = (initial + step) % 3;
            int expected = (previous + 1) % 3;
            forge_next_physics(props);
            CHECK(forge_physics_mode(props) == expected);
            CHECK(!strcmp(forge_physics_name(forge_physics_mode(props)), names[expected]));
            CHECK(props[FORGE_PHYSICS_FLAGS] == ((flags & 0x3f) | next_flags[previous]));
            for (int k = 0; k < 28; k++)
                if (k != FORGE_PHYSICS_FLAGS) CHECK(props[k] == original[k]);
        }
        CHECK(forge_physics_mode(props) == initial);
    }
    /* Native Phased release adds the Fixed bit; 0xcc must still display
       Phased and cycle to Normal, retaining the unrelated 0x0c flags. */
    memset(props, 0, sizeof props);
    props[FORGE_PHYSICS_FLAGS] = 0xcc;
    CHECK(forge_physics_mode(props) == 2);
    forge_next_physics(props);
    CHECK(props[FORGE_PHYSICS_FLAGS] == 0x0c);
}

static void test_grid(void) {
    const float expected_steps[] = {0, .25f, .5f, 1, 2, 4};
    const int expected_angles[] = {0, 90, 45, 30, 15, 5};
    CHECK(sizeof FORGE_GRID_METRES == sizeof expected_steps);
    CHECK(sizeof FORGE_ROTATION_DEGREES == sizeof expected_angles);
    CHECK(!memcmp(FORGE_GRID_METRES, expected_steps, sizeof expected_steps));
    CHECK(!memcmp(FORGE_ROTATION_DEGREES, expected_angles, sizeof expected_angles));
    float free_point[3] = {-31.2345f, 2.4567f, -0.0f}, out[3], repeated[3];
    CHECK(forge_grid_point(free_point, 0, out));
    CHECK(!memcmp(free_point, out, sizeof out));
    for (int step = 1; step < 6; step++) {
        float metres = FORGE_GRID_METRES[step];
        /* A small offset on either side of a half cell establishes rounding
           direction; both signs must have symmetric, world-axis behavior. */
        for (int sign = -1; sign <= 1; sign += 2) {
            float p[3] = {sign * .49f * metres / FORGE_METRES_PER_UNIT,
                          sign * .51f * metres / FORGE_METRES_PER_UNIT,
                          sign * 2.5f * metres / FORGE_METRES_PER_UNIT};
            CHECK(forge_grid_point(p, metres, out));
            CHECK(close_metres(out[0], 0));
            CHECK(close_metres(out[1], sign * metres));
            CHECK(close_metres(out[2], sign * 3 * metres));
            p[0] = sign * .5f * metres / FORGE_METRES_PER_UNIT;
            p[1] = sign * 1.5f * metres / FORGE_METRES_PER_UNIT;
            p[2] = sign * 3.5f * metres / FORGE_METRES_PER_UNIT;
            CHECK(forge_grid_point(p, metres, out));
            CHECK(close_metres(out[0], sign * metres));
            CHECK(close_metres(out[1], sign * 2 * metres));
            CHECK(close_metres(out[2], sign * 4 * metres));
        }
        /* Cover signed world positions across the enlarged playable canvas.
           A metre-grid point must survive world-unit conversion and repeated
           drops without accumulating drift, including in-place snapping. */
        for (int cell = -48; cell <= 48; cell++) {
            float p[3] = {cell * metres / FORGE_METRES_PER_UNIT,
                          (cell + .2f) * metres / FORGE_METRES_PER_UNIT,
                          (cell - .2f) * metres / FORGE_METRES_PER_UNIT};
            CHECK(forge_grid_point(p, metres, out));
            for (int k = 0; k < 3; k++) CHECK(close_metres(out[k], cell * metres));
            CHECK(forge_grid_point(out, metres, repeated));
            CHECK(!memcmp(out, repeated, sizeof out));
            CHECK(forge_grid_point(out, metres, out));
            CHECK(!memcmp(out, repeated, sizeof out));
        }
    }
    const float invalid[] = {NAN, INFINITY, -INFINITY};
    const float valid[3] = {1, -2, 3};
    for (int bad = 0; bad < 3; bad++) {
        CHECK(!forge_grid_point(valid, invalid[bad], out));
        for (int axis = 0; axis < 3; axis++) {
            float p[3]; memcpy(p, valid, sizeof p); p[axis] = invalid[bad];
            CHECK(!forge_grid_point(p, .25f, out));
            CHECK(!forge_grid_point(p, 0, out));
        }
    }
    CHECK(!forge_grid_point(valid, -.25f, out));
    const float too_large[3] = {FLT_MAX, 0, 0};
    CHECK(!forge_grid_point(too_large, .25f, out));
    CHECK(!forge_grid_point(valid, FLT_MIN, out));
}

static void test_marker_targeting(void) {
    const float origin[3] = {0, 0, 0};
    const float visible_end[3] = {10 / FORGE_METRES_PER_UNIT, 0, 0};
    const float radius = .35f / FORGE_METRES_PER_UNIT;
    float point[3] = {5 / FORGE_METRES_PER_UNIT, 0, 0}, score = -1;
    CHECK(forge_marker_score(origin, visible_end, point, &score));
    CHECK(score == 0);
    point[1] = radius;
    CHECK(forge_marker_score(origin, visible_end, point, &score));
    CHECK(fabsf(score - radius * radius) < 0.000001f);
    point[1] = -radius;
    CHECK(forge_marker_score(origin, visible_end, point, &score));
    point[1] = .351f / FORGE_METRES_PER_UNIT;
    score = -1;
    CHECK(!forge_marker_score(origin, visible_end, point, &score));
    CHECK(score == -1);
    /* Reproduce the reported spawn stealing the card from 0.66 WORLD units
       (2.01 metres) off the ray. A metre/WU mistake used to accept it. */
    point[1] = .66f;
    CHECK(!forge_marker_score(origin, visible_end, point, &score));
    point[1] = 0;
    point[0] = visible_end[0];
    CHECK(forge_marker_score(origin, visible_end, point, &score));
    point[0] += .001f / FORGE_METRES_PER_UNIT;
    CHECK(!forge_marker_score(origin, visible_end, point, &score));
    point[0] = 60; /* Previously searched far beyond a wall/cursor hit. */
    CHECK(!forge_marker_score(origin, visible_end, point, &score));
    point[0] = -1;
    CHECK(!forge_marker_score(origin, visible_end, point, &score));
    point[0] = .099f / FORGE_METRES_PER_UNIT;
    CHECK(!forge_marker_score(origin, visible_end, point, &score));
    point[0] = .1f / FORGE_METRES_PER_UNIT;
    CHECK(forge_marker_score(origin, visible_end, point, &score));

    /* Targeting must depend on the actual segment in arbitrary world axes,
       not on distance from the map origin or a privileged horizontal axis. */
    const float from[3] = {-12, 7, 3}, end[3] = {-8, 10, 3};
    const float center[3] = {-10, 8.5f, 3};
    const float inside[3] = {-10, 8.5f, 3 + .349f / FORGE_METRES_PER_UNIT};
    const float outside[3] = {-10, 8.5f, 3 + .351f / FORGE_METRES_PER_UNIT};
    const float occluded[3] = {-7.992f, 10.006f, 3};
    float center_score, edge_score;
    CHECK(forge_marker_score(from, end, center, &center_score));
    CHECK(forge_marker_score(from, end, inside, &edge_score));
    CHECK(center_score < edge_score);
    CHECK(!forge_marker_score(from, end, outside, &score));
    CHECK(!forge_marker_score(from, end, occluded, &score));
    CHECK(!forge_marker_score(origin, origin, point, &score));
    const float very_short[3] = {.001f, 0, 0};
    CHECK(!forge_marker_score(origin, very_short, point, &score));
    const float invalid[] = {NAN, INFINITY, -INFINITY};
    for (int bad = 0; bad < 3; bad++) {
        for (int axis = 0; axis < 3; axis++) {
            float p[3]; memcpy(p, center, sizeof p); p[axis] = invalid[bad];
            CHECK(!forge_marker_score(p, end, center, &score));
            CHECK(!forge_marker_score(from, p, center, &score));
            CHECK(!forge_marker_score(from, end, p, &score));
        }
    }
    const float extreme_from[3] = {-FLT_MAX, 0, 0}, extreme_end[3] = {FLT_MAX, 0, 0};
    CHECK(!forge_marker_score(extreme_from, extreme_end, origin, &score));
}

int main(void) {
    test_turn_yaw();
    test_pose_validation();
    test_physics_properties();
    test_grid();
    test_marker_targeting();
    printf("Forge placement controls: %d checks passed\n", checks);
    return 0;
}
