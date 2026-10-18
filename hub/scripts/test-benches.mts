/**
 * Bench reports (migrations/0021): a player's POST /benches, and the public
 * GET /benches and GET /benches/summary, driven through the real Hono app
 * against every migration in an in-memory SQLite (hub-harness.mts).
 *
 * fixtures/bench-dti-4k.json is a report exactly as MJOLNIRHud wrote it for
 * a /bench on Death Island (RTX 5090, 3840x2160, 2026-10-17).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { hub } from "./hub-harness.mjs";

const { sqlite, account, call } = hub();
const fixture = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), "fixtures", "bench-dti-4k.json"), "utf8"),
) as Record<string, unknown>;

const player = await account("player");
const other = await account("other");

const report = (over: Record<string, unknown> = {}) => ({ ...fixture, ...over });

test("the game's own report is recorded", async () => {
  const r = await call("POST", "/benches", player, fixture);
  assert.equal(r.status, 201, JSON.stringify(r.body));
  assert.equal(r.body.duplicate, false);
  const row = sqlite.prepare(`SELECT * FROM bench_reports WHERE id = ?1`).all(r.body.id)[0];
  assert.equal(row.user_id, "player");
  assert.equal(row.map_code, "DTI");
  assert.equal(row.gpu_name, "NVIDIA GeForce RTX 5090");
  assert.equal(row.viewport_h, 2160);
  assert.equal(row.foliage_quality, 3);
  // "no foliage" less the base.
  assert.ok(Math.abs(Number(row.foliage_delta_ms) - (12.976 - 15.516)) < 1e-9);
});

test("the same run sent again returns the first report", async () => {
  const first = sqlite.prepare(`SELECT id FROM bench_reports`).all()[0].id;
  const r = await call("POST", "/benches", player, fixture);
  assert.equal(r.status, 200);
  assert.deepEqual(r.body, { id: first, duplicate: true });
  assert.equal(sqlite.prepare(`SELECT COUNT(*) AS n FROM bench_reports`).all()[0].n, 1);
});

test("another account may send a run with the same id", async () => {
  const r = await call("POST", "/benches", other, fixture);
  assert.equal(r.status, 201);
});

test("a report needs a key, and a sane body", async () => {
  assert.equal((await call("POST", "/benches", null, fixture)).status, 401);
  assert.equal((await call("POST", "/benches", player, report({ bench_id: "not hex" }))).status, 400);
  assert.equal((await call("POST", "/benches", player, report({ map_code: "dti" }))).status, 400);
  assert.equal((await call("POST", "/benches", player, report({ results: [] }))).status, 400);
  assert.equal((await call("POST", "/benches", player, report({ base_ms: -1 }))).status, 400);
  const sg = { ...(fixture.settings as Record<string, unknown>), sg: { Bogus: 3 } };
  assert.equal((await call("POST", "/benches", player, report({ settings: sg }))).status, 400);
});

test("a cvar bench has no foliage figure", async () => {
  const r = await call("POST", "/benches", player, report({
    bench_id: "0123456789abcdef0123456789abcdef",
    kind: "cvar",
    label: "r.Shadow.Virtual.Enable 0 against 1",
    results: [{ name: "r.Shadow.Virtual.Enable 0", ms: 17.2 }],
  }));
  assert.equal(r.status, 201);
  const row = sqlite.prepare(`SELECT foliage_delta_ms FROM bench_reports WHERE id = ?1`).all(r.body.id)[0];
  assert.equal(row.foliage_delta_ms, null);
});

test("the list shows reports without accounts", async () => {
  const r = await call("GET", "/benches?map=DTI", null);
  assert.equal(r.status, 200);
  const benches = r.body.benches as Record<string, unknown>[];
  assert.equal(benches.length, 3);
  assert.ok(benches.every((b) => !("user_id" in b)));
  const foliage = benches.find((b) => b.kind === "foliage")!;
  assert.equal((foliage.results as unknown[]).length, 3);
  assert.equal((foliage.sg as Record<string, number>).Foliage, 3);
  assert.equal(((await call("GET", "/benches?gpu=3060", null)).body.benches as unknown[]).length, 0);
});

test("the summary averages foliage runs by GPU, map, height and quality", async () => {
  // A run in the first two minutes on the map is left out.
  await call("POST", "/benches", player, report({ bench_id: "fedcba9876543210fedcba9876543210", seconds_in_world: 30 }));
  const r = await call("GET", "/benches/summary?map=DTI", null);
  assert.equal(r.status, 200);
  const rows = r.body.rows as Record<string, unknown>[];
  assert.equal(rows.length, 1);
  assert.equal(rows[0].reports, 2);
  assert.equal(rows[0].viewport_h, 2160);
  assert.equal(rows[0].foliage_quality, 3);
  assert.equal(rows[0].base_ms, 15.52);
  assert.equal(rows[0].foliage_delta_ms, -2.54);
});
