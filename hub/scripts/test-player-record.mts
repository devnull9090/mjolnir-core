/**
 * The combat record (docs/match_stats.md): what lib/api/player-record.ts
 * reads from the match tables, against every migration in an in-memory
 * SQLite (hub-harness.mts), and how players/_components/record.ts words it.
 *
 * Plain script under tsx, like the other hub checks. `pnpm test` runs it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { nameAccount, playerMapMarks, playerRecord, type RecordMatch } from "../src/lib/api/player-record.js";
import { medalTotal, personalBests, runningRatio, styleShares, styleTitle, winRate } from "../src/app/players/_components/record.js";
import { hub } from "./hub-harness.mjs";

const { sqlite, env, account } = hub();
const db = env.DB as never;

await account("host");
await account("rival");
await account("twin");

function match(id: string, ended: string, map = "BGL") {
  sqlite
    .prepare(
      `INSERT INTO matches (id, host_match_id, reporter_user_id, map_code, game_type, started_at, ended_at,
         duration_ms, end_reason, player_count)
       VALUES (?1, ?1, 'host', ?2, 'slayer', ?3, ?3, 600000, 'game_over', 3)`,
    )
    .run(id, map, ended);
}

function seat(matchId: string, index: number, name: string, over: { kills?: number; deaths?: number; outcome?: string; user?: string } = {}) {
  sqlite
    .prepare(
      `INSERT INTO match_players (match_id, player_index, name, kills, deaths, place, outcome, user_id)
       VALUES (?1, ?2, ?3, ?4, ?5, ?2 + 1, ?6, ?7)`,
    )
    .run(matchId, index, name, over.kills ?? 0, over.deaths ?? 0, over.outcome ?? null, over.user ?? null);
}

let seq = 0;
function event(
  matchId: string,
  type: string,
  cause: number,
  effect: number,
  over: { weapon?: string; modifier?: number; causeAt?: number[]; effectAt?: number[] } = {},
) {
  const [cx, cy, cz] = over.causeAt ?? [null, null, null];
  const [ex, ey, ez] = over.effectAt ?? [null, null, null];
  sqlite
    .prepare(
      `INSERT INTO match_events (match_id, seq, t_ms, type, cause, effect, weapon, modifier,
         cause_x, cause_y, cause_z, effect_x, effect_y, effect_z)
       VALUES (?1, ?2, 0, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)`,
    )
    .run(matchId, seq++, type, cause, effect, over.weapon ?? null, over.modifier ?? null, cx, cy, cz, ex, ey, ez);
}

// Match one, on Blood Gulch: Chief kills Rival twice, and Rival kills Chief.
match("m1", "2026-10-01 10:00:00");
seat("m1", 0, "Chief", { kills: 2, deaths: 1, outcome: "win" });
seat("m1", 1, "RivalOne", { kills: 1, deaths: 2, outcome: "loss", user: "rival" });
seat("m1", 2, "Idle", { outcome: "loss" });
event("m1", "kill", 0, 1, { weapon: "SniperRifle", modifier: 1, causeAt: [1, 2, 3], effectAt: [4, 5, 6] });
// The run of siblings every kill raises: none of these is a second kill.
event("m1", "sniper_kill", 0, 1, { weapon: "SniperRifle", modifier: 1 });
event("m1", "precision_comm", 0, 1, { weapon: "SniperRifle", modifier: 1 });
event("m1", "headshot_kill", 0, 1, { weapon: "SniperRifle", modifier: 1 });
event("m1", "headshot_comm", 0, 1, { weapon: "SniperRifle", modifier: 1 });
event("m1", "first_blood", 0, 1);
event("m1", "kill", 0, 1, { weapon: "Shotgun", causeAt: [7, 8, 9], effectAt: [1, 1, 1] });
event("m1", "kill", 1, 0, { weapon: "Melee", causeAt: [2, 2, 2], effectAt: [3, 3, 3] });
event("m1", "first_blood", 1, 0); // Someone else's medal.
event("m1", "assist", 0, 1);
event("m1", "kill", 0, 0, { weapon: "FragGrenade", causeAt: [0, 0, 0], effectAt: [0, 0, 0] }); // A suicide.

// Match two, on Prisoner, later: the same rival account under another name.
match("m2", "2026-10-02 10:00:00", "PRS");
seat("m2", 3, "Chief", { kills: 1, deaths: 0, outcome: "loss" });
seat("m2", 4, "RivalTwo", { user: "rival" });
event("m2", "kill", 3, 4, { weapon: "SniperRifle", causeAt: [9, 9, 9], effectAt: [8, 8, 8] });

// A seat that never fought: counted as a match, not drawn as one.
match("m3", "2026-10-03 10:00:00");
seat("m3", 0, "Chief");

test("spokes are the matches fought in, oldest first", async () => {
  const r = await playerRecord(db, { name: "chief" });
  assert.deepEqual(r.matches.map((m) => m.id), ["m1", "m2"]);
  assert.equal(r.fought, 2);
  assert.equal(r.time_played_ms, 1_800_000);
  assert.equal(r.first_played, "2026-10-01 10:00:00");
});

test("a medal counts once, and only the earner's", async () => {
  const r = await playerRecord(db, { name: "Chief" });
  assert.deepEqual(r.medals, { first_blood: 1, headshot_kill: 1 });
  assert.equal(r.assists, 1);
  assert.equal(medalTotal(r), 2);
});

test("weapons count kills, not siblings or suicides", async () => {
  const r = await playerRecord(db, { name: "Chief" });
  assert.deepEqual(r.weapons, [
    { weapon: "SniperRifle", kills: 2, headshots: 1 },
    { weapon: "Shotgun", kills: 1, headshots: 0 },
  ]);
});

test("a rival is one row however many names they used", async () => {
  const r = await playerRecord(db, { name: "Chief" });
  assert.equal(r.rivals.length, 1);
  assert.equal(r.rivals[0].user?.id, "rival");
  assert.equal(r.rivals[0].kills, 3);
  assert.equal(r.rivals[0].deaths, 1);
});

test("a record reads the same by account", async () => {
  const r = await playerRecord(db, { user: "rival" });
  assert.deepEqual(r.matches.map((m) => m.id), ["m1"]);
  assert.equal(r.rivals[0].name, "Chief");
  assert.equal(r.rivals[0].user, null);
  assert.equal(r.rivals[0].kills, 1);
  assert.equal(r.rivals[0].deaths, 3);
});

test("maps come busiest first", async () => {
  const r = await playerRecord(db, { name: "Chief" });
  assert.deepEqual(
    r.maps.map((m) => [m.code, m.matches, m.kills, m.deaths, m.wins]),
    [
      ["BGL", 1, 2, 1, 1],
      ["PRS", 1, 1, 0, 0],
    ],
  );
});

test("a kill marks where the player stood, a death where they fell, on that map only", async () => {
  const marks = await playerMapMarks(db, { name: "Chief" }, "BGL");
  const at = (kind: string) => marks.filter((m) => m.kind === kind).map((m) => [m.x, m.y, m.z]);
  assert.deepEqual(at("kill").sort(), [[1, 2, 3], [7, 8, 9]]);
  assert.deepEqual(at("death"), [[3, 3, 3]]);
  const shot = marks.find((m) => m.weapon === "SniperRifle");
  assert.equal(shot?.other, "RivalOne");
  assert.equal(shot?.headshot, true);
  assert.equal(marks.find((m) => m.kind === "death")?.other, "RivalOne");
});

test("a name names an account only when one account uses it", async () => {
  assert.equal((await nameAccount(db, "rivalone"))?.id, "rival");
  assert.equal(await nameAccount(db, "Chief"), null);
  match("m4", "2026-10-04 10:00:00");
  seat("m4", 0, "RivalOne", { user: "twin" });
  assert.equal(await nameAccount(db, "RivalOne"), null);
});

const played = (kills: number, deaths: number, outcome: RecordMatch["outcome"]): RecordMatch => ({
  id: `${kills}-${deaths}`,
  map_code: "BGL",
  map_title: null,
  game_type: "slayer",
  ended_at: "2026-10-01 10:00:00",
  kills,
  deaths,
  place: 1,
  outcome,
});

test("an abandoned match neither extends a win streak nor ends it", () => {
  const b = personalBests([played(1, 1, "win"), played(1, 1, null), played(1, 1, "win"), played(1, 1, "loss"), played(1, 1, "win")]);
  assert.equal(b.winStreak, 2);
});

test("a best ratio needs enough kills to mean anything", () => {
  const b = personalBests([played(4, 0, "win"), played(10, 5, "win")]);
  assert.equal(b.bestRatio?.kills, 10);
  assert.equal(b.mostKills?.kills, 10);
});

test("the form line is the career to date", () => {
  assert.deepEqual(runningRatio([played(2, 0, null), played(0, 2, null), played(4, 2, null)]), [2, 1, 1.5]);
});

test("win rate is of finished matches", () => {
  assert.equal(winRate(1, 3, 0), "25%");
  assert.equal(winRate(0, 0, 0), "–");
});

test("a style needs enough kills, and a clear lead", () => {
  const w = (weapon: string, kills: number) => ({ weapon, kills, headshots: 0 });
  assert.equal(styleTitle(styleShares([w("SniperRifle", 10)])), null);
  assert.equal(styleTitle(styleShares([w("SniperRifle", 12), w("Shotgun", 6)])), "Marksman");
  assert.equal(
    styleTitle(styleShares([w("SniperRifle", 5), w("Shotgun", 5), w("AssaultRifle", 5), w("Ghost", 5)])),
    "All-rounder",
  );
});
