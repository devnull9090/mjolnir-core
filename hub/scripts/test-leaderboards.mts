/**
 * The leaderboards (docs/match_stats.md): who places and in what order,
 * against every migration in an in-memory SQLite (hub-harness.mts).
 *
 * Plain script under tsx, like the other hub checks. `pnpm test` runs it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { MIN_KD_KILLS, MIN_RATE_FINISHED, leaderboard, podiumSpokes } from "../src/lib/api/leaderboards.js";
import { hub } from "./hub-harness.mjs";

const { sqlite, env, account } = hub();
const db = env.DB as never;

for (const id of ["ace", "bee", "cee", "solo", "banned"]) await account(id);
sqlite.prepare(`UPDATE users SET banned_at = datetime('now') WHERE id = 'banned'`).run();

const daysAgo = (n: number) =>
  new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 19).replace("T", " ");

function match(id: string, ended = daysAgo(1), map = "BGL") {
  sqlite
    .prepare(
      `INSERT INTO matches (id, host_match_id, reporter_user_id, map_code, game_type, started_at, ended_at,
         duration_ms, end_reason, player_count)
       VALUES (?1, ?1, 'ace', ?2, 'slayer', ?3, ?3, 600000, 'game_over', 4)`,
    )
    .run(id, map, ended);
}

function seat(matchId: string, index: number, user: string | null, kills: number, deaths: number, outcome: string | null) {
  sqlite
    .prepare(
      `INSERT INTO match_players (match_id, player_index, name, kills, deaths, place, outcome, user_id)
       VALUES (?1, ?2, ?3, ?4, ?5, ?2 + 1, ?6, ?7)`,
    )
    .run(matchId, index, user ?? `guest${index}`, kills, deaths, outcome, user);
}

let seq = 0;
function kill(matchId: string, cause: number, effect: number, modifier: number | null) {
  sqlite
    .prepare(
      `INSERT INTO match_events (match_id, seq, t_ms, type, cause, effect, modifier) VALUES (?1, ?2, 0, 'kill', ?3, ?4, ?5)`,
    )
    .run(matchId, seq++, cause, effect, modifier);
}

// Counts: two linked seats. A guest's seat is in it but cannot place.
match("two-linked");
seat("two-linked", 0, "ace", 30, 10, "win");
seat("two-linked", 1, "bee", 10, 30, "loss");
seat("two-linked", 2, null, 99, 0, "loss");
kill("two-linked", 0, 1, 1);
kill("two-linked", 0, 1, 1);
kill("two-linked", 0, 0, 1); // A suicide is no headshot.
kill("two-linked", 1, 0, 1);

// Does not count: one account against guests or bots.
match("alone");
seat("alone", 0, "solo", 500, 0, "win");
seat("alone", 1, null, 0, 500, "loss");

// Counts, but a banned account never shows.
match("with-banned");
seat("with-banned", 0, "banned", 900, 0, "win");
seat("with-banned", 1, "bee", 5, 5, "loss");
seat("with-banned", 2, "cee", 5, 5, "loss");

// Counts all time, and not this week.
match("old", daysAgo(20), "PRS");
seat("old", 0, "cee", 40, 2, "win");
seat("old", 1, "ace", 2, 40, "loss");

const ids = (board: Awaited<ReturnType<typeof leaderboard>>) => board.standings.map((s) => s.user.id);

test("a match needs two linked seats, and a guest never places", async () => {
  const b = await leaderboard(db, "kills", "all");
  assert.deepEqual(ids(b), ["cee", "ace", "bee"]);
  assert.equal(b.standings[1].value, 32);
  assert.equal(b.matches, 3);
});

test("a period keeps only its matches", async () => {
  const week = await leaderboard(db, "kills", "7d");
  assert.deepEqual(ids(week), ["ace", "bee", "cee"]);
  const month = await leaderboard(db, "kills", "30d");
  assert.equal(month.standings[0].user.id, "cee");
});

test("K/D needs enough kills and matches to place", async () => {
  // Two matches each so far: nobody has played enough.
  assert.deepEqual(ids(await leaderboard(db, "kd", "all")), []);
  match("third-kd");
  seat("third-kd", 0, "ace", 0, 0, null);
  seat("third-kd", 1, "cee", 0, 0, null);
  seat("third-kd", 2, "bee", 0, 0, null);
  seat("third-kd", 3, null, 1, 0, null); // Someone fought, or the match would not count.
  const b = await leaderboard(db, "kd", "all");
  // cee: 45 kills, 7 deaths. ace: 32, 50. bee's 15 kills is under the bar.
  assert.ok(15 < MIN_KD_KILLS);
  assert.deepEqual(ids(b), ["cee", "ace"]);
  assert.equal(b.standings[0].value, 45 / 7);
});

test("win rate needs enough finished matches to place", async () => {
  assert.equal(MIN_RATE_FINISHED, 3);
  const b = await leaderboard(db, "win_rate", "all");
  assert.deepEqual(ids(b), []);
  match("third");
  seat("third", 0, "ace", 1, 0, "win");
  seat("third", 1, "cee", 0, 1, "loss");
  match("fourth");
  seat("fourth", 0, "ace", 1, 0, "win");
  seat("fourth", 1, "cee", 0, 1, "loss");
  const after = await leaderboard(db, "win_rate", "all");
  assert.equal(after.standings[0].user.id, "ace");
  assert.equal(after.standings[0].value, 3 / 4);
  assert.equal(after.standings[1].user.id, "cee");
  assert.equal(after.standings[1].wins, 1);
  assert.equal(after.standings[1].finished, 4);
});

test("headshots are kills by modifier, not suicides", async () => {
  const b = await leaderboard(db, "headshots", "all");
  assert.deepEqual(b.standings.map((s) => [s.user.id, s.value]), [["ace", 2], ["bee", 1]]);
});

test("best match names the match it was", async () => {
  const b = await leaderboard(db, "best_match", "all");
  assert.equal(b.standings[0].user.id, "cee");
  assert.equal(b.standings[0].value, 40);
  assert.equal(b.standings[0].best_match?.id, "old");
  assert.equal(b.standings[1].user.id, "ace");
  assert.equal(b.standings[1].best_match?.id, "two-linked");
});

test("a tie shares its place", async () => {
  match("tie");
  seat("tie", 0, "ace", 1, 0, "win");
  seat("tie", 1, "bee", 0, 0, "loss");
  seat("tie", 2, "cee", 0, 0, "loss");
  sqlite.prepare(`UPDATE match_players SET outcome = 'win' WHERE match_id = 'tie' AND user_id = 'bee'`).run();
  const b = await leaderboard(db, "wins", "all");
  // ace 4 wins; cee and bee 1 each. Whoever comes next would be fourth.
  assert.deepEqual(b.standings.map((s) => [s.user.id, s.rank]), [["ace", 1], ["cee", 2], ["bee", 2]]);
  sqlite.prepare(`UPDATE match_players SET outcome = 'win' WHERE match_id = 'with-banned' AND user_id = 'bee'`).run();
  const broken = await leaderboard(db, "wins", "all");
  assert.deepEqual(broken.standings.map((s) => [s.user.id, s.rank]), [["ace", 1], ["bee", 2], ["cee", 3]]);
});

test("podium rings run oldest first, and only matches fought in", async () => {
  match("idle");
  seat("idle", 0, "cee", 0, 0, "loss");
  const rings = await podiumSpokes(db, ["cee"]);
  const seen = rings.cee.map((m) => m.id);
  assert.equal(seen[0], "old");
  assert.ok(!seen.includes("idle"));
  assert.deepEqual(await podiumSpokes(db, []), {});
});
