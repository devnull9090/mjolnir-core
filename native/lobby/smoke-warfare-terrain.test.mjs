import test from 'node:test';
import assert from 'node:assert/strict';
import { guardPlan, motion, settled, crossedSeam, floorResult, movementForYaw, verifyDirectedStep, main } from './smoke-warfare-terrain.mjs';

const snapshot = (tick, position = [1, 2, 100]) => ({ instance: '90071992547409999', tick, rate: 30, players: [{ position }] });

test('live bridge cannot be imported or called without explicit opt-in', async () => {
  await assert.rejects(main([]), /No game calls made/);
  await assert.rejects(main(['--probe']), /--plan/);
});

test('settling uses simulation time and rejects stale/airborne samples', () => {
  assert.deepEqual(motion(snapshot(0), snapshot(15, [1, 2, 99])).velocity_mps, [0, 0, -2]);
  assert.throws(() => motion(snapshot(1), snapshot(1)), /stale/);
  assert.equal(settled([snapshot(0), snapshot(12), snapshot(24)]), true);
  assert.equal(settled([snapshot(0), snapshot(3), snapshot(6)]), false);
  assert.equal(settled([snapshot(0, [1, 2, 102]), snapshot(12, [1, 2, 101]), snapshot(24)]), false);
});

test('finite seam crossing cannot pass by moving along or around boundary', () => {
  const p = { seam: { a_m: [0, -5, 10], b_m: [0, 5, 10] }, crossing_normal: [1, 0], crossing_center_m: [0, 0], max_walk_metres: 14 };
  assert.equal(crossedSeam(p, [-3, 0, 10], [4, 0, 10]), true);
  assert.equal(crossedSeam(p, [-3, 8, 10], [4, 8, 10]), false);
  assert.equal(crossedSeam(p, [-3, 0, 10], [-1, 3, 10]), false);
  assert.equal(crossedSeam(p, [-3, 0, 10], [15, 0, 10]), false);
});

test('floor residual removes measured avatar origin offset, never assumes feet origin', () => {
  const p = { max_residual_m: .35 };
  assert.equal(floorResult(p, [1, 2, 107.45], 107.4, .05).pass, true);
  assert.equal(floorResult(p, [1, 2, 106], 107.4, .05).pass, false);
});

test('opposite and lateral poses select explicit bounded axes, never arbitrary angles', () => {
  assert.equal(movementForYaw([0, 1], -90).key, 's');
  assert.equal(movementForYaw([-1, 0], -180).key, 'w');
  assert.equal(movementForYaw([Math.SQRT1_2, Math.SQRT1_2], -45).key, 'a');
  assert.equal(movementForYaw([0, -1], 0).key, 'd');
  assert.throws(() => movementForYaw([1, 0], 25), /not aligned/);
});

test('verification pulse must actually move in the intended world direction', () => {
  const p = { crossing_normal: [0, 1] };
  assert.equal(verifyDirectedStep(p, [10, 0, 0], [10.01, .6, 0], 2.5).crossing_progress_m, .6);
  assert.throws(() => verifyDirectedStep(p, [0, 0, 0], [0, 0, 0], 2.5), /did not follow/);
  assert.throws(() => verifyDirectedStep(p, [0, 0, 0], [0, -.6, 0], 2.5), /did not follow/);
  assert.throws(() => verifyDirectedStep(p, [0, 0, 0], [.6, 0, 0], 2.5), /did not follow/);
  assert.throws(() => verifyDirectedStep(p, [0, 0, 0], [0, 3, 0], 2.5), /did not follow/);
});

test('installed flag geometry and probe stamp must match the complete plan', () => {
  const plan = { schema: 'pwr-terrain-probe-v1', protocol: 20569, layout_revision: 3,
    provenance: { compiled_boundaries_verified: true }, master_manifest_sha256: 'a'.repeat(64),
    probes: Array.from({ length: 8 }, (_, i) => ({ id: `p${i}`, flag: `terrain_probe_p${i}`,
      kind: i ? 'road' : 'calibration', position_m: [i, 2, 3], floor_m: 2.2, yaw: 0, max_residual_m: .35 })) };
  const hash = 'b'.repeat(64), level = { warfare: { protocol: 20569, layout_revision: 3 }, blam: { cutscene_flags: [
    { name: `terrain_probe_hash_${hash.slice(0, 12)}` },
    ...plan.probes.map(p => ({ name: p.flag, pos: [p.position_m[0] * 100, -200, 300], yaw: 0 }))] } };
  assert.equal(guardPlan(plan, level, hash), plan);
  assert.throws(() => guardPlan(plan, level, 'c'.repeat(64)), /different probe-plan stamp/);
  level.blam.cutscene_flags[2].pos[2] += 1;
  assert.throws(() => guardPlan(plan, level, hash), /differs/);
});
