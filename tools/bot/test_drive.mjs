// node --test tools/bot/test_drive.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { steer } from "./drive.mjs";
import { Navmesh } from "./navmesh.mjs";

// No areas, only walls: what steering reads.
const meshWith = (walls) => Navmesh.load({ version: 1, sectors: [], doors: [], main_component: 0, walls });
// A square post 0.2 wu across centred at (cx, cy), standing 0..2 wu.
const post = (cx, cy, r = 0.1) => [
  [cx - r, cy - r, cx + r, cy - r, 0, 2], [cx + r, cy - r, cx + r, cy + r, 0, 2],
  [cx + r, cy + r, cx - r, cy + r, 0, 2], [cx - r, cy + r, cx - r, cy - r, 0, 2],
];

test("a clear line keeps its heading", () => {
  const way = steer(meshWith(post(2, 3)), [0, 0], [4, 0], 0);
  assert.equal(way.around, false);
  assert.equal(way.heading, 0);
});

test("a post just left of the line is passed on the right", () => {
  const way = steer(meshWith(post(2, 0.12)), [0, 0], [4, 0], 0);
  assert.equal(way.around, true);
  assert.ok(way.heading < 0, `heading ${way.heading}`);
});

test("a post just right of the line is passed on the left", () => {
  const way = steer(meshWith(post(2, -0.12)), [0, 0], [4, 0], 0);
  assert.equal(way.around, true);
  assert.ok(way.heading > 0, `heading ${way.heading}`);
});

test("the new heading clears the post", () => {
  const mesh = meshWith(post(2, 0));
  const way = steer(mesh, [0, 0], [4, 0], 0);
  const h = (way.heading * Math.PI) / 180;
  assert.equal(mesh.firstWall([0, 0], [Math.cos(h) * 4, Math.sin(h) * 4], 0, 0.1), null);
});

test("a wall below the knees or overhead does not count", () => {
  assert.equal(steer(meshWith([[2, -1, 2, 1, 0, 0.05]]), [0, 0], [4, 0], 0).around, false);
  assert.equal(steer(meshWith([[2, -1, 2, 1, 1.5, 3]]), [0, 0], [4, 0], 0).around, false);
});

test("a post behind, or past the point, is ignored", () => {
  assert.equal(steer(meshWith(post(-1, 0)), [0, 0], [4, 0], 0).around, false);
  assert.equal(steer(meshWith(post(3, 0)), [0, 0], [1, 0], 0).around, false);
});
