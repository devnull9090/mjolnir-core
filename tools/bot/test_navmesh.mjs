// node --test tools/bot/test_navmesh.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { Navmesh } from "./navmesh.mjs";

// Unit squares as two counter-clockwise triangles each, as the bake makes
// them, joined into a mesh with a door on every shared edge.
function grid(cells) {
  const sectors = [];
  const edges = new Map();
  const doors = [];
  for (const [cx, cy] of cells) {
    const p = (x, y) => [cx + x, cy + y, 0];
    for (const ring of [[p(0, 0), p(1, 0), p(1, 1)], [p(0, 0), p(1, 1), p(0, 1)]]) {
      const s = sectors.length;
      sectors.push({ ring, floor: true, component: 0 });
      for (let i = 0; i < 3; i++) {
        const a = ring[i];
        const b = ring[(i + 1) % 3];
        const back = edges.get(`${b}|${a}`);
        if (back !== undefined) doors.push([back.s, s, back.a, back.b]);
        else edges.set(`${a}|${b}`, { s, a, b });
      }
    }
  }
  return Navmesh.load({ version: 1, sectors, doors, main_component: 0 });
}

const near = (a, b) => Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6;

test("a point finds the area under it, and its height", () => {
  const mesh = grid([[0, 0]]);
  assert.equal(mesh.locate([0.8, 0.2, 0.5]), 0);
  assert.equal(mesh.locate([0.2, 0.8, 0.5]), 1);
  assert.equal(mesh.locate([0.5, 0.5, -0.5]), -1, "a floor above the point is not it");
  assert.equal(mesh.locate([9, 9, 0]), -1);
});

test("a straight corridor is one straight line", () => {
  const mesh = grid([[0, 0], [1, 0], [2, 0], [3, 0]]);
  const r = mesh.route([0.5, 0.5, 0.6], [3.5, 0.5, 0.6]);
  assert.deepEqual(r.points.length, 1);
  assert.ok(near(r.points[0], [3.5, 0.5]));
});

test("an L-shaped corridor turns at its inner corner", () => {
  // (0,0) (1,0) (2,0) then up (2,1) (2,2): the inner corner is (2,1).
  const mesh = grid([[0, 0], [1, 0], [2, 0], [2, 1], [2, 2]]);
  const r = mesh.route([0.5, 0.5, 0.6], [2.5, 2.5, 0.6]);
  assert.equal(r.points.length, 2, JSON.stringify(r.points));
  assert.ok(near(r.points[0], [2, 1]), `corner ${r.points[0]}`);
  assert.ok(near(r.points[1], [2.5, 2.5]));
});

test("it turns the other way too", () => {
  // (0,2) (1,2) (2,2) then down (2,1) (2,0): the inner corner is (2,2).
  const mesh = grid([[0, 2], [1, 2], [2, 2], [2, 1], [2, 0]]);
  const r = mesh.route([0.5, 2.5, 0.6], [2.5, 0.5, 0.6]);
  assert.equal(r.points.length, 2, JSON.stringify(r.points));
  assert.ok(near(r.points[0], [2, 2]), `corner ${r.points[0]}`);
});

test("no route between areas nothing joins", () => {
  const mesh = grid([[0, 0], [5, 5]]);
  assert.equal(mesh.route([0.5, 0.5, 0.6], [5.5, 5.5, 0.6]), null);
});

test("a route goes around a blocked area, and through it when it must", () => {
  // A 3x3 field: from the left middle to the right middle, the middle cell
  // blocked by a tree.
  const cells = [];
  for (let x = 0; x < 3; x++) for (let y = 0; y < 3; y++) cells.push([x, y]);
  const mesh = grid(cells);
  const straight = mesh.route([0.5, 1.5, 0.6], [2.5, 1.5, 0.6]);
  assert.equal(straight.points.length, 1);
  assert.ok(mesh.block([1.5, 1.5], 0.3) > 0);
  const around = mesh.route([0.5, 1.5, 0.6], [2.5, 1.5, 0.6]);
  assert.ok(around.points.length > 1, "it bends");
  for (const s of around.sectors.slice(1, -1)) assert.equal(mesh.sectors[s].blocked, false);
  // Blocked all the way across: the route still exists, through the trees.
  const lane = grid([[0, 0], [1, 0], [2, 0]]);
  lane.block([1.5, 0.5], 0.3);
  assert.ok(lane.route([0.5, 0.5, 0.6], [2.5, 0.5, 0.6]));
});
