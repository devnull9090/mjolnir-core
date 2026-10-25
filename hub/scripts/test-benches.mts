/**
 * Bench reports (migrations/0021): a signed-in player's POST /benches, and
 * the admins' GET /admin/benches and GET /admin/benches/summary, driven
 * through the real Hono app against every migration in an in-memory SQLite
 * (hub-harness.mts).
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
const mod = await account("mod", "moderator");
const admin = await account("admin", "admin");

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

test("only admins read reports", async () => {
  for (const path of ["/admin/benches", "/admin/benches/summary"]) {
    assert.equal((await call("GET", path, null)).status, 401, path);
    assert.equal((await call("GET", path, player)).status, 403, path);
    assert.equal((await call("GET", path, mod)).status, 403, path);
  }
});

test("an admin's list names who sent each run", async () => {
  const r = await call("GET", "/admin/benches?map=DTI", admin);
  assert.equal(r.status, 200);
  const benches = r.body.benches as Record<string, unknown>[];
  assert.equal(benches.length, 3);
  assert.ok(benches.every((b) => !("user_id" in b)));
  assert.deepEqual(
    benches.map((b) => (b.user as { name: string }).name).sort(),
    ["other display", "player display", "player display"],
  );
  const foliage = benches.find((b) => b.kind === "foliage")!;
  assert.equal((foliage.results as unknown[]).length, 3);
  assert.equal((foliage.sg as Record<string, number>).Foliage, 3);
  assert.equal(((await call("GET", "/admin/benches?gpu=3060", admin)).body.benches as unknown[]).length, 0);
});

test("the summary averages foliage runs by GPU, map, height and quality", async () => {
  // A run in the first two minutes on the map is left out.
  await call("POST", "/benches", player, report({ bench_id: "fedcba9876543210fedcba9876543210", seconds_in_world: 30 }));
  const r = await call("GET", "/admin/benches/summary?map=DTI", admin);
  assert.equal(r.status, 200);
  const rows = r.body.rows as Record<string, unknown>[];
  assert.equal(rows.length, 1);
  assert.equal(rows[0].reports, 2);
  assert.equal(rows[0].viewport_h, 2160);
  assert.equal(rows[0].foliage_quality, 3);
  assert.equal(rows[0].base_ms, 15.52);
  assert.equal(rows[0].foliage_delta_ms, -2.54);
});

test("a report from MJOLNIRHud 0.11.0 keeps its camera and frame split", async () => {
  const times = { game: 19.6, game_cp: 6.1, draw: 7.4, draw_cp: 5.9, rhit: 3.2, gpu: 19.1 };
  const view = { x: -4521.5, y: 1830.25, z: 312, pitch: -8.5, yaw: 143.2 };
  const results = (fixture.results as { name: string; ms: number }[]).map((r) => ({
    ...r,
    times: { ...times, gpu: times.gpu - 2 },
  }));
  const r = await call("POST", "/benches", player, report({
    bench_id: "00112233445566778899aabbccddeeff",
    base_times: times,
    view,
    results,
  }));
  assert.equal(r.status, 201, JSON.stringify(r.body));
  const list = (await call("GET", "/admin/benches?map=DTI", admin)).body.benches as Record<string, unknown>[];
  const got = list.find((b) => b.id === r.body.id)!;
  assert.deepEqual(got.view, view);
  assert.deepEqual(got.base_times, times);
  assert.equal((got.results as { times: { gpu: number } }[])[0].times.gpu, times.gpu - 2);
  // Older clients' reports read as null, not as zeros.
  const old = list.find((b) => b.id !== r.body.id && b.kind === "foliage")!;
  assert.equal(old.view, null);
  assert.equal(old.base_times, null);
  // A camera with no place, or a negative time, is refused.
  assert.equal((await call("POST", "/benches", player, report({ bench_id: "aa112233445566778899aabbccddeeff", view: { x: 1 } }))).status, 400);
  assert.equal((await call("POST", "/benches", player, report({ bench_id: "bb112233445566778899aabbccddeeff", base_times: { gpu: -1 } }))).status, 400);
});
