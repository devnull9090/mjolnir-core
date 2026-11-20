#include <assert.h>
#include <stdio.h>
#include "warfare_core.h"

static warfare_sample sample(uint32_t unit) {
    warfare_sample s; memset(&s, 0, sizeof s); s.valid = 1; s.unit = unit;
    s.carrier_clear = 1; s.velocity_valid = 1;
    s.parent = WARFARE_NONE; s.local_user = 0; s.position[2] = 150; return s;
}
static void step(warfare_player *p, warfare_sample *s, int phase, float age, int key, warfare_output *o) {
    warfare_step(p, s, phase, age, WARFARE_INSERTION_SECONDS, 1.0f / 60.0f, key, o);
}

static void test_routes(void) {
    unsigned flags = 0;
    for (int team = 0; team < 2; team++) {
        flags |= warfare_layout_flag(warfare_routes[team].start);
        flags |= warfare_layout_flag(warfare_routes[team].end);
        assert(warfare_route_distance2(team, warfare_routes[team].end) < 0.001f);
        assert(warfare_route_distance2(1 - team, warfare_routes[team].end) > 100);
        float v[3], position[3]; memcpy(position, warfare_routes[team].start, sizeof position);
        assert(warfare_flight_velocity(team, 0, 1, position, v));
        assert(sqrtf(warfare_dot(v, v)) <= 30.001f); /* short test variant cannot overspeed */
        assert(warfare_flight_velocity(team, 0, 120, position, v));
        assert(fabsf(v[0]) < 15 && fabsf(v[0]) > 14);
        for (int n = 0; n < 600; n++) {
            assert(warfare_flight_velocity(team, (float)n * 0.1f, 60, position, v));
            for (int k = 0; k < 3; k++) position[k] += v[k] * 0.1f;
            position[2] -= 0.07f; /* measured old-flight drift, externally imposed */
            assert(sqrtf(warfare_dot(v, v)) <= 30.001f);
        }
        assert(fabsf(position[0] - warfare_routes[team].end[0]) < 1);
        assert(fabsf(position[2] - warfare_routes[team].end[2]) < 2);
        position[2] = warfare_scenario_max[2] + 1;
        assert(!warfare_flight_velocity(team, 1, 60, position, v));
    }
    assert(flags == 15);
    const float old_flag[3] = {-180, -65, 150};
    assert(warfare_layout_flag(old_flag) == 0); /* old PWR pak cannot arm new DLL */
    assert(flags != WARFARE_LAYOUT_MARKER_MASK); /* routes alone cannot arm a mismatched map */
    for (int marker = 4; marker < WARFARE_LAYOUT_MARKERS; marker++) {
        flags |= warfare_layout_flag(warfare_layout_markers[marker]);
        float stale[3]; memcpy(stale, warfare_layout_markers[marker], sizeof stale); stale[2] += 0.1f;
        assert(warfare_layout_flag(stale) == 0);
    }
    assert(flags == WARFARE_LAYOUT_MARKER_MASK);
    for (int yaw_index = 0; yaw_index < 4; yaw_index++) for (int pitch_index = -1; pitch_index <= 1; pitch_index++) {
        float yaw = (float)yaw_index * 1.57079632679f, pitch = (float)pitch_index * 0.3f, roll = 0.4f;
        float f[3] = {cosf(yaw) * cosf(pitch), sinf(yaw) * cosf(pitch), sinf(pitch)};
        float u[3] = {-cosf(yaw) * sinf(pitch), -sinf(yaw) * sinf(pitch), cosf(pitch)}, l[3], rolled[3];
        warfare_cross(u, f, l);
        for (int k = 0; k < 3; k++) rolled[k] = u[k] * cosf(roll) + l[k] * sinf(roll);
        warfare_cross(rolled, f, l);
        float wanted[3] = {28.33333f, 0, 1.5f}, local[3];
        assert(warfare_velocity_frame(f, rolled, wanted, local));
        for (int k = 0; k < 3; k++) {
            float actual = f[k] * local[0] + l[k] * local[1] + rolled[k] * local[2];
            assert(fabsf(actual - wanted[k]) < 0.0001f);
        }
        assert(!warfare_velocity_frame(f, f, wanted, local));
    }
    assert(fabsf(warfare_forced_exit(1) - 0.9f) < 0.0001f);
    assert(fabsf(warfare_forced_exit(120) - 108) < 0.0001f);
}

static void test_nonflat_drop(void) {
    const float floors[] = {-8, 36, 120, 400};
    for (int floor = 0; floor < 4; floor++) {
        warfare_player p; warfare_player_reset(&p);
        warfare_sample s = sample(42); warfare_output o;
        p.unit = 42; p.stage = WF_CANOPY; p.departure_z = warfare_routes[0].start[2]; p.protected_fall = 1; p.saw_insertion = 1;
        s.position[0] = 900; s.position[2] = floors[floor]; s.velocity[0] = 3; s.velocity[2] = -1;
        for (int n = 0; n < 30; n++) step(&p, &s, 2, 1, 0, &o);
        assert(p.stage == WF_CANOPY && p.protected_fall); /* sliding is not a stationary landing */
        s.velocity[0] = 0; s.velocity[2] = 0; s.support_world = 1;
        for (int n = 0; n < 20; n++) step(&p, &s, 2, 2, 0, &o);
        assert(p.stage == WF_LANDED && !p.protected_fall);
    }
    warfare_player p; warfare_player_reset(&p); warfare_sample s = sample(42); warfare_output o;
    p.unit = 42; p.stage = WF_CANOPY; p.departure_z = 240; p.protected_fall = 1;
    s.position[0] = 1100; /* outside new layout, but still a valid sampled coordinate */
    assert(warfare_finite_sample(&s));
    step(&p, &s, 2, 1, 0, &o);
    assert(p.stage == WF_FAILED && (o.flags & (WF_HOME | WF_UNPROTECT)) == (WF_HOME | WF_UNPROTECT));
    warfare_player_reset(&p); s = sample(43); p.unit = 43; p.stage = WF_SEATED; p.saw_insertion = 1;
    s.parent = 12; s.parent_is_transport = 1;
    warfare_step(&p, &s, 1, 0.89f, 1, 1.0f / 60, 0, &o); assert(p.stage == WF_SEATED);
    warfare_step(&p, &s, 1, 0.91f, 1, 1.0f / 60, 0, &o); assert(p.stage == WF_EXITING && (o.flags & WF_EXIT));
}

static void test_high_altitude_late_exit(void) {
    /* Conservative no-air-friction launch from the forced-exit point. Native
     * drag must keep the full descent inside the map and release protection
     * when landing on either a low valley or high mountain, before timeout. */
    const float floors[] = {50, 170, 400};
    for (int team = 0; team < 2; team++) for (int floor = 0; floor < 3; floor++) {
        warfare_player p; warfare_player_reset(&p); warfare_sample s = sample(42); warfare_output o;
        p.unit = 42; p.stage = WF_FALLING; p.protected_fall = 1; p.saw_insertion = 1; s.team = team;
        float fraction = WARFARE_FORCED_EXIT_SECONDS / WARFARE_INSERTION_SECONDS;
        for (int k = 0; k < 3; k++)
            s.position[k] = warfare_routes[team].start[k] + (warfare_routes[team].end[k] - warfare_routes[team].start[k]) * fraction;
        p.departure_z = s.position[2];
        assert(p.departure_z > 500 && p.departure_z > floors[floor]);
        warfare_route_velocity(team, WARFARE_INSERTION_SECONDS, s.velocity); s.velocity[2] = -1;
        int landed = 0;
        for (int n = 0; n < (int)(WARFARE_DESCENT_TIMEOUT_SECONDS * 60); n++) {
            s.velocity[2] -= 9.8f / 60;
            step(&p, &s, 2, (float)n / 60, 0, &o);
            assert(p.stage != WF_FAILED);
            if (o.flags & WF_VELOCITY) memcpy(s.velocity, o.velocity, sizeof s.velocity);
            for (int k = 0; k < 3; k++) s.position[k] += s.velocity[k] / 60;
            if (s.position[2] <= floors[floor]) { s.position[2] = floors[floor]; s.velocity[2] = 0; s.support_world = 1; }
            assert(warfare_inside(s.position, warfare_play_min, warfare_play_max));
            if (p.stage == WF_LANDED) { landed = 1; break; }
        }
        assert(landed && !p.protected_fall && p.elapsed < WARFARE_DESCENT_TIMEOUT_SECONDS);
    }
}

static void test_world_support(void) {
    const float up[3] = {0,0,1}, slope[3] = {0.6f,0,0.8f}, wall[3] = {1,0,0}, bad[3] = {0,NAN,1};
    assert(warfare_world_support(8, 123, 0, -1, WARFARE_NONE, up)); /* shell */
    assert(warfare_world_support(8, 77, 0, 4702, WARFARE_NONE, slope)); /* static instance */
    assert(!warfare_world_support(0, 123, 0, -1, WARFARE_NONE, up)); /* stale record */
    assert(!warfare_world_support(8, -1, 0, -1, WARFARE_NONE, up)); /* no surface */
    assert(!warfare_world_support(8, 123, -1, -1, WARFARE_NONE, up));
    assert(!warfare_world_support(8, 123, 0, -1, 0x12340001, up)); /* Pelican/dynamic support */
    assert(!warfare_world_support(8, 123, 0, -1, WARFARE_NONE, wall));
    assert(!warfare_world_support(8, 123, 0, -1, WARFARE_NONE, bad));
}

static void test_ejection_bounds(void) {
    for (int team = 0; team < 2; team++) for (int pitch = -1; pitch <= 1; pitch++) {
        float direction = team ? -1.0f : 1.0f;
        float center[3] = {direction * 700, direction * -180, 335};
        float forward[3] = {direction * cosf(pitch * 0.3f), 0, sinf(pitch * 0.3f)};
        float rider[3] = {center[0]+1,center[1]+2,center[2]}, origin[3] = {rider[0],rider[1],rider[2]-1};
        float point[3], after_center[3];
        assert(!warfare_carrier_clear(center, 18, rider, 1.2f));
        assert(warfare_ejection_point(center, 18, forward, rider, 1.2f, origin, point));
        for (int k = 0; k < 3; k++) after_center[k] = point[k] + rider[k] - origin[k];
        assert(warfare_carrier_clear(center, 18, after_center, 1.2f));
        assert((point[0]-center[0])*direction < -22);
        assert(fabsf(point[2]-origin[2]) < 0.001f);
        assert(!warfare_ejection_point(center, NAN, forward, rider, 1.2f, origin, point));
        float vertical[3] = {0,0,1};
        assert(!warfare_ejection_point(center, 18, vertical, rider, 1.2f, origin, point));
        center[0] = -949; forward[0] = 1; forward[2] = 0;
        assert(!warfare_ejection_point(center, 18, forward, rider, 1.2f, origin, point));
    }
}

static void test_carrier_deck_and_airborne_pause(void) {
    warfare_player p; warfare_player_reset(&p); warfare_sample s = sample(42); warfare_output o;
    p.unit = s.unit; p.carrier = 0x12340005; p.stage = WF_SEATED; p.protected_fall = 1; p.saw_insertion = 1;
    s.parent = p.carrier; s.parent_is_transport = 1; s.carrier_clear = 0;
    step(&p, &s, 1, 54, 0, &o);
    assert(p.stage == WF_EXITING && (o.flags & WF_EXIT));
    s.parent = WARFARE_NONE; s.parent_is_transport = 0;
    /* objects_detach succeeded, but the biped is still in the cabin. */
    int clear_commands = 0;
    for (int n = 0; n < 45; n++) {
        step(&p, &s, 1, 55, 0, &o);
        clear_commands += !!(o.flags & WF_CLEAR_CABIN);
        assert(p.stage == WF_EXITING && p.protected_fall && !(o.flags & WF_UNPROTECT));
    }
    assert(clear_commands >= 2 && clear_commands <= 4);
    s.carrier_clear = 1; s.position[2] = 337;
    step(&p, &s, 1, 56, 0, &o);
    assert(p.stage == WF_FALLING && (o.flags & WF_VELOCITY));
    s.position[2] = 325.935f; /* exact V8 false landing altitude */
    s.velocity[2] = 0;
    for (int n = 0; n < 180; n++) step(&p, &s, 2, 3, n == 60, &o);
    assert(p.stage == WF_CANOPY && p.protected_fall); /* no terrain support */
    s.support_world = 1; s.carrier_clear = 0;
    for (int n = 0; n < 30; n++) step(&p, &s, 2, 4, 0, &o);
    assert(p.stage == WF_CANOPY && p.protected_fall); /* even stale ground cannot credit a nearby carrier */
    s.carrier_clear = 1; s.velocity_valid = 0;
    for (int n = 0; n < 30; n++) step(&p, &s, 2, 5, 0, &o);
    assert(p.stage == WF_CANOPY && p.protected_fall);
    s.velocity_valid = 1;
    for (int n = 0; n < 10; n++) step(&p, &s, 2, 6, 0, &o);
    s.support_world = 0; step(&p, &s, 2, 6, 0, &o);
    s.support_world = 1;
    for (int n = 0; n < 10; n++) step(&p, &s, 2, 6, 0, &o);
    assert(p.stage == WF_CANOPY && p.protected_fall); /* support must be continuous */
    for (int n = 0; n < 10; n++) step(&p, &s, 2, 6, 0, &o);
    assert(p.stage == WF_LANDED && !p.protected_fall);
    /* Reattachment to a transport must retry exit, not count as landing. */
    p.stage = WF_CANOPY; p.protected_fall = 1; s.parent = p.carrier; s.parent_is_transport = 1;
    step(&p, &s, 2, 6, 0, &o);
    assert(p.stage == WF_EXITING && p.protected_fall && (o.flags & WF_EXIT) && !(o.flags & WF_UNPROTECT));
    /* Unverifiable clearance has a bounded existing failure/home path. */
    s.parent = WARFARE_NONE; s.parent_is_transport = 0; s.carrier_clear = 0;
    for (int n = 0; n < 185; n++) step(&p, &s, 2, 7, 0, &o);
    assert(p.stage == WF_FAILED && !p.protected_fall);
    /* Boarding another vehicle does not inject canopy motion or make a
     * later exit fail merely because the ride exceeded the drop timeout. */
    p.stage = WF_CANOPY; p.protected_fall = 1; p.elapsed = 119;
    s.parent = 0x12340009; s.parent_is_transport = 0; s.carrier_clear = 1;
    for (int n = 0; n < 180; n++) step(&p, &s, 2, 200, 0, &o);
    assert(p.stage == WF_CANOPY && p.protected_fall && p.elapsed == 0 && o.flags == 0);
    s.parent = WARFARE_NONE; s.position[2] = 150; s.support_world = 1;
    for (int n = 0; n < 20; n++) step(&p, &s, 2, 201, 0, &o);
    assert(p.stage == WF_LANDED && !p.protected_fall);
}

#include "warfare_inventory.h"

typedef struct { float opened, landed, remaining, horizontal, max_sink, final_sink; } flight_result;

static flight_result fly_course(int rate, float open_at, int brake) {
    float dt = 1.0f / rate;
    warfare_player p; warfare_player_reset(&p);
    warfare_sample s = sample(42); warfare_output o;
    p.unit = s.unit; p.stage = WF_EXITING; p.protected_fall = 1; p.saw_insertion = 1;
    s.position[0] = -590; s.position[1] = -130; s.position[2] = 550; s.facing[0] = 1;
    p.carrier_velocity[0] = 15;
    float x0 = s.position[0];
    flight_result result = {0};
    for (int tick = 0; tick < 90*rate; tick++) {
        float age = tick * dt;
        s.brake = brake;
        int key = open_at >= 0 && tick == (int)ceilf(open_at * rate);
        warfare_step(&p, &s, 2, age, 60, dt, key, &o);
        assert(p.stage != WF_FAILED);
        if (p.stage == WF_CANOPY && !result.opened) {
            result.opened = age;
            result.remaining = s.position[2] - warfare_terrain(s.position[0], s.position[1], 0);
        }
        if (p.stage == WF_LANDED) {
            result.landed = age;
            result.horizontal = s.position[0] - x0;
            return result;
        }
        if (o.flags & WF_VELOCITY) memcpy(s.velocity, o.velocity, sizeof s.velocity);
        result.max_sink = fmaxf(result.max_sink, -s.velocity[2]);
        if (p.stage == WF_CANOPY && !s.support_world) result.final_sink = -s.velocity[2];
        for (int k=0; k<3; k++) s.position[k] += s.velocity[k] * dt;
        float terrain = warfare_terrain(s.position[0], s.position[1], 0);
        if (s.position[2] <= terrain) {
            s.position[2] = terrain; s.support_world = 1;
            memset(s.velocity, 0, sizeof s.velocity);
        }
    }
    assert(!"Flight did not land");
    return result;
}

static void test_flight_controls(void) {
    flight_result early = fly_course(60, 1, 0), brake = fly_course(60, 1, 1);
    flight_result automatic = fly_course(60, -1, 0);
    assert(early.opened == 1 && early.landed > 19 && early.landed < 35);
    assert(brake.landed > early.landed && brake.landed < 50 && brake.horizontal < early.horizontal);
    assert(fabsf(early.final_sink - 16.0f) < 0.1f && fabsf(brake.final_sink - 10.5f) < 0.1f);
    assert(automatic.opened > 6 && automatic.remaining > 45 && automatic.remaining < 130);
    assert(automatic.max_sink > 45 && automatic.landed < early.landed);
    for (int rate=30; rate<=120; rate*=2) {
        flight_result r = fly_course(rate, -1, 0);
        assert(fabsf(r.opened - automatic.opened) < 0.08f && fabsf(r.landed - automatic.landed) < 0.13f);
    }
    printf("PWR 550m route exit above red home: auto %.2fs at %.1fm, peak sink %.1fm/s, landed %.2fs; "
           "1s pull landed %.2fs/%.0fm forward, held brake %.2fs/%.0fm forward.\n",
           automatic.opened, automatic.remaining, automatic.max_sink, automatic.landed,
           early.landed, early.horizontal, brake.landed, brake.horizontal);
    warfare_player p; warfare_player_reset(&p); warfare_sample s = sample(42); warfare_output o;
    p.unit = s.unit; p.stage = WF_CANOPY; p.departure_z = 550; s.position[2] = 350;
    s.facing[0] = 1; s.right_input = 1;
    for (int n=0; n<180; n++) step(&p,&s,2,0,0,&o);
    assert(o.velocity[0] > 13 && o.velocity[1] < -13 && p.steering > 0.99f);
    s.facing[0] = 0; s.facing[1] = 1; s.right_input = 0; s.forward_input = 1;
    for (int n=0; n<240; n++) step(&p,&s,2,0,0,&o);
    assert(o.velocity[1] > 27 && fabsf(o.velocity[0]) < 0.2f && fabsf(p.steering) < 0.01f);
    s.brake = 1;
    for (int n=0; n<240; n++) step(&p,&s,2,0,0,&o);
    assert(p.braking && fabsf(o.velocity[1]-12) < 0.1f && fabsf(o.velocity[2]+10.5f) < 0.1f);
    s.brake = 0; s.support_world = 1; step(&p,&s,2,0,0,&o);
    assert(!(o.flags & WF_VELOCITY));

    /* One tap leaves the seat. A distinct tap during line stretch is
     * retained until deployment is safe without requiring a third press. */
    warfare_player_reset(&p); s = sample(42); s.position[2] = 550;
    p.unit = s.unit; p.stage = WF_SEATED; p.saw_insertion = 1;
    s.parent = 45; s.parent_is_transport = 1; s.carrier_clear = 0;
    step(&p,&s,1,0.2f,1,&o);
    assert(p.stage == WF_EXITING && !p.deploy_requested);
    step(&p,&s,1,0.3f,1,&o); assert(p.deploy_requested);
    s.parent = WARFARE_NONE; s.parent_is_transport = 0; s.carrier_clear = 1;
    step(&p,&s,1,0.4f,0,&o); assert(p.stage == WF_FALLING);
    for (int n=0;n<17;n++) step(&p,&s,1,0.6f,0,&o);
    assert(p.stage == WF_CANOPY && !p.deploy_requested);
}

static int inventory_calls, inventory_grants, inventory_clears, reject_next;
static int fake_inventory_submit(const char *command) {
    inventory_calls++;
    if (strstr(command, "pwr_unarmed true false")) inventory_clears++;
    if (strstr(command, "pwr_starter false false")) inventory_grants++;
    if (reject_next) { reject_next = 0; return 0; }
    return 1;
}
static void test_owned_inventory(void) {
    warfare_inventory kit = {0};
    warfare_player p; warfare_player_reset(&p); warfare_output o; warfare_sample s = sample(42);
    p.unit=42; p.stage=WF_EXITING; p.protected_fall=1; p.saw_insertion=1;
    step(&p,&s,1,20,0,&o);
    assert(p.stage==WF_FALLING);
    warfare_inventory_apply(&kit,80,s.unit,3,o.flags,fake_inventory_submit);
    assert(kit.cleared && inventory_calls==1 && inventory_clears==1 && inventory_grants==0);
    s.position[2]=100; s.velocity[2]=-5;
    for(int n=0;n<160;n++) {
        step(&p,&s,1,21,0,&o);
        warfare_inventory_apply(&kit,80,s.unit,3,o.flags,fake_inventory_submit);
    }
    assert(p.stage==WF_CANOPY && inventory_calls==1);
    s.support_world=1; s.velocity[2]=0;
    for(int n=0;n<120;n++) {
        step(&p,&s,2,1,0,&o);
        warfare_inventory_apply(&kit,80,s.unit,3,o.flags,fake_inventory_submit);
    }
    assert(p.stage==WF_LANDED && !kit.cleared && inventory_calls==2 && inventory_grants==1);
    warfare_inventory_apply(&kit,80,43,4,WF_LOWER_WEAPON,fake_inventory_submit);
    reject_next=1;
    warfare_inventory_apply(&kit,80,43,4,WF_RAISE_WEAPON,fake_inventory_submit);
    assert(kit.cleared && kit.restoring && inventory_grants==2);
    for(int n=0;n<35;n++) warfare_inventory_apply(&kit,80,43,4,0,fake_inventory_submit);
    assert(!kit.cleared && !kit.restoring && inventory_grants==3);
    warfare_inventory_apply(&kit,80,43,4,WF_LOWER_WEAPON,fake_inventory_submit);
    reject_next=1;
    warfare_inventory_apply(&kit,80,43,4,WF_RAISE_WEAPON,fake_inventory_submit);
    int grants=inventory_grants;
    warfare_inventory_apply(&kit,80,44,4,0,fake_inventory_submit);
    warfare_inventory_apply(&kit,80,44,4,WF_RAISE_WEAPON,fake_inventory_submit);
    assert(inventory_grants==grants && !kit.cleared && !kit.restoring);
    warfare_inventory_apply(&kit,80,45,4,WF_LOWER_WEAPON,fake_inventory_submit);
    warfare_inventory_apply(&kit,81,45,4,WF_RAISE_WEAPON,fake_inventory_submit);
    assert(inventory_grants==grants);
    reject_next=1;
    warfare_inventory_apply(&kit,81,46,4,WF_LOWER_WEAPON,fake_inventory_submit);
    warfare_inventory_apply(&kit,81,46,4,WF_RAISE_WEAPON,fake_inventory_submit);
    assert(inventory_grants==grants);
    puts("inventory: once on exit/ground, additive retry only on rejection, salt/instance reset and rejected clear passed");
}

int main(void) {
    test_flight_controls();
    test_owned_inventory();
    test_routes(); test_nonflat_drop(); test_high_altitude_late_exit();
    test_world_support(); test_ejection_bounds(); test_carrier_deck_and_airborne_pause();
    warfare_sample sparse[WARFARE_PLAYERS]; memset(sparse, 0, sizeof sparse);
    sparse[2].present = 1; sparse[2].team = -1; /* present, no living unit */
    sparse[7].present = 1; sparse[7].valid = 1;
    assert(warfare_hs_rank(sparse, 2) == 0 && warfare_hs_rank(sparse, 7) == 1);
    assert(warfare_hs_rank(sparse, 0) == -1 && warfare_hs_rank(sparse, 16) == -1);
    sparse[2].present = 0; assert(warfare_hs_rank(sparse, 7) == 0);
    uint16_t admission[WARFARE_PLAYERS]; int seats[WARFARE_PLAYERS];
    sparse[2].present = 1; sparse[2].team = 0; sparse[2].participant_salt = 55;
    sparse[7].team = 0; sparse[7].participant_salt = 66;
    warfare_lock_roster(sparse, admission, seats);
    assert(seats[2] == 0 && seats[7] == 1 && admission[7] == 66);
    sparse[2].present = 0;
    assert(warfare_hs_rank(sparse, 7) == 0 && seats[7] == 1); /* HS rank changes; reservation cannot */
    warfare_player p; warfare_output o; warfare_sample s = sample(0x12340001);
    warfare_player_reset(&p);
    step(&p, &s, 0, 0, 0, &o); assert(o.flags & WF_WARMUP);
    step(&p, &s, 0, 1, 0, &o); assert(o.flags == 0);
    step(&p, &s, 1, 0, 0, &o); assert((o.flags & (WF_BOARD | WF_PROTECT)) == (WF_BOARD | WF_PROTECT));
    s.parent = 0x12340005; s.parent_is_transport = 1;
    step(&p, &s, 1, 1, 1, &o); assert(p.stage == WF_SEATED && !(o.flags & WF_EXIT));
    step(&p, &s, 1, 4, 1, &o); assert(p.stage == WF_EXITING && (o.flags & WF_EXIT));
    s.parent = WARFARE_NONE;
    step(&p, &s, 1, 4.1f, 0, &o); assert(p.stage == WF_FALLING
        && (o.flags & (WF_PROTECT | WF_VELOCITY)) == (WF_PROTECT | WF_VELOCITY));
    assert(p.weapon_lowered && (o.flags & WF_LOWER_WEAPON));
    s.position[2] = 140; s.velocity[0] = 20; s.velocity[2] = -25;
    for (int n = 0; n < 125; n++) {
        step(&p, &s, 1, 6.2f, 0, &o);
        assert(!(o.flags & (WF_LOWER_WEAPON | WF_RAISE_WEAPON)));
    }
    assert(p.stage == WF_CANOPY && o.velocity[2] < -15 && o.velocity[2] > -17 && o.velocity[0] > 15);
    s.velocity[0] = 0; s.velocity[2] = -0.2f;
    step(&p, &s, 1, 7, 0, &o); assert(o.flags & WF_VELOCITY); /* airborne apex still under flight control */
    s.support_world = 1;
    int raises = 0;
    for (int n = 0; n < 20; n++) {
        step(&p, &s, 2, 0.2f, 0, &o);
        raises += !!(o.flags & WF_RAISE_WEAPON);
    }
    assert(p.stage == WF_LANDED && !p.protected_fall && !p.weapon_lowered && raises == 1);
    step(&p, &s, 2, 2, 1, &o); assert(o.flags == 0);
    /* Respawn uses a new salted unit handle; it must not reinsert or retain
     * fall immunity. Late arrivals during active play have the same rule. */
    s.unit = 0x12350001; step(&p, &s, 2, 10, 1, &o);
    assert(p.stage == WF_GROUND && o.flags == 0 && !p.protected_fall);
    /* No successful boarding: release protection and return to a real base. */
    warfare_player_reset(&p); s = sample(0x12340001);
    for (int n = 0; n < 310; n++) step(&p, &s, 1, (float)n / 60, 0, &o);
    assert(p.stage == WF_FAILED && !p.protected_fall);
    step(&p, &s, 2, 0, 0, &o); assert(o.flags == 0);
    /* Non-owned state, malformed physics and huge catch-up steps never write. */
    warfare_player_reset(&p); s.local_user = -1;
    step(&p, &s, 1, 0, 1, &o); assert(o.flags == 0 && p.unit == WARFARE_NONE);
    s.local_user = 0; s.position[0] = NAN;
    step(&p, &s, 1, 0, 1, &o); assert(o.flags == 0);
    s.position[0] = 0; warfare_step(&p, &s, 1, 0, WARFARE_INSERTION_SECONDS, 1, 1, &o); assert(o.flags == 0);
    /* Ending during boarding cannot strand a passenger or leave fall immunity. */
    step(&p, &s, 1, 0, 0, &o); s.parent = 12; s.parent_is_transport = 1;
    step(&p, &s, 1, 1, 0, &o);
    step(&p, &s, 3, 0, 0, &o);
    assert((o.flags & (WF_UNPROTECT | WF_EXIT | WF_HOME)) == (WF_UNPROTECT | WF_EXIT | WF_HOME));
    /* At an apex, zero velocity without meaningful descent is not landing. */
    warfare_player_reset(&p); s = sample(42); p.unit = 42; p.stage = WF_CANOPY;
    p.departure_z = 150; p.protected_fall = 1; p.saw_insertion = 1;
    for (int n = 0; n < 120; n++) step(&p, &s, 2, 1, 0, &o);
    assert(p.stage == WF_CANOPY && p.protected_fall);
    puts("warfare: layout, flight, ownership, cabin clearance, native world support, airborne pause, slopes and lifecycle tests passed");
    return 0;
}
