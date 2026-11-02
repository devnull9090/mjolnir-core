#ifndef MJOLNIR_FORGE_PLACEMENT_CONTROLS_H
#define MJOLNIR_FORGE_PLACEMENT_CONTROLS_H
#include <math.h>
#include <stdint.h>

#define FORGE_METRES_PER_UNIT 3.048f
#define FORGE_PHYSICS_FLAGS 0x16

/* The native resolver tests phased first. Native release can turn 0x80
   into 0xc0, so it is not an equality test against a two-bit enum. */
static int forge_physics_mode(const uint8_t *props) {
    return props[FORGE_PHYSICS_FLAGS] & 0x80 ? 2 : props[FORGE_PHYSICS_FLAGS] & 0x40 ? 1 : 0;
}
static const char *forge_physics_name(int mode) {
    return mode == 2 ? "phased" : mode == 1 ? "fixed" : "normal";
}
static void forge_next_physics(uint8_t *props) {
    int mode = (forge_physics_mode(props) + 1) % 3;
    props[FORGE_PHYSICS_FLAGS] = (uint8_t)((props[FORGE_PHYSICS_FLAGS] & 0x3f) | (mode == 2 ? 0x80 : mode == 1 ? 0x40 : 0));
}

static const float FORGE_GRID_METRES[] = {0, 0.25f, 0.5f, 1, 2, 4};
static const int FORGE_ROTATION_DEGREES[] = {0, 90, 45, 30, 15, 5};

/* Return the new yaw in radians, wrapped to [-pi, pi]. Both the native held
   object and a carried marker use the next absolute grid boundary. Treat
   tiny roundoff around a boundary as already on it, so each key advances.
   direction=0 leaves the angle unchanged apart from wrapping. */
static float forge_turn_yaw(float yaw, int direction, int snapDegrees) {
    if (!isfinite(yaw) || snapDegrees < 0) return NAN;
    yaw = atan2f(sinf(yaw), cosf(yaw));
    if (!direction) return yaw;
    float radians = 0.01745329252f;
    float step = snapDegrees ? (float)snapDegrees * radians : 22.5f * radians;
    if (snapDegrees) {
        float cells = yaw / step;
        yaw = (direction > 0 ? floorf(cells + 0.0001f) + 1 : ceilf(cells - 0.0001f) - 1) * step;
    } else {
        yaw += direction > 0 ? step : -step;
    }
    return atan2f(sinf(yaw), cosf(yaw));
}

/* Validate again after an engine pre-move callback, which can change the
   pose. Bounds are interleaved xmin,xmax,ymin,ymax,zmin,zmax, in world units.
   Axes must be finite; their native normalization is a separate invariant. */
static int forge_pose_in_bounds(const float point[3], const float forward[3], const float up[3], const float bounds[6]) {
    for (int k = 0; k < 3; k++) {
        if (!isfinite(point[k]) || !isfinite(forward[k]) || !isfinite(up[k]) ||
            !isfinite(bounds[k * 2]) || !isfinite(bounds[k * 2 + 1]) ||
            bounds[k * 2] > bounds[k * 2 + 1] || fabsf(point[k]) > 32767.0f ||
            point[k] < bounds[k * 2] || point[k] > bounds[k * 2 + 1]) return 0;
    }
    return 1;
}

/* Quantize the object's authored origin in world axes, not its bounds or
   the camera-relative grab offset. A nonfinite input is never accepted. */
static int forge_grid_point(const float point[3], float metres, float out[3]) {
    if (!isfinite(metres) || metres < 0) return 0;
    for (int k = 0; k < 3; k++) if (!isfinite(point[k])) return 0;
    for (int k = 0; k < 3; k++) {
        out[k] = metres > 0 ? roundf(point[k] * FORGE_METRES_PER_UNIT / metres) * metres / FORGE_METRES_PER_UNIT : point[k];
        if (!isfinite(out[k])) return 0;
    }
    return 1;
}

/* Soft marker targeting follows the actual visible cursor segment. The
   previous code treated metres as world units and searched 183 m through
   surfaces, letting a distant spawn steal the target card. */
static int forge_marker_score(const float from[3], const float end[3], const float point[3], float *score) {
    float direction[3], delta[3], length2 = 0, along = 0, off2 = 0;
    for (int k = 0; k < 3; k++) {
        if (!isfinite(from[k]) || !isfinite(end[k]) || !isfinite(point[k])) return 0;
        direction[k] = end[k] - from[k];
        delta[k] = point[k] - from[k];
        length2 += direction[k] * direction[k];
    }
    float length = sqrtf(length2);
    if (!isfinite(length) || length < 0.01f) return 0;
    for (int k = 0; k < 3; k++) { direction[k] /= length; along += delta[k] * direction[k]; }
    const float radius = 0.35f / FORGE_METRES_PER_UNIT;
    if (along < 0.1f / FORGE_METRES_PER_UNIT || along > length) return 0;
    for (int k = 0; k < 3; k++) { float off = delta[k] - along * direction[k]; off2 += off * off; }
    if (off2 > radius * radius) return 0;
    *score = off2;
    return 1;
}
#endif
