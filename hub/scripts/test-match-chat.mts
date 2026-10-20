/**
 * Match chat logs (migrations/0020): the host's POST /matches/chat and the
 * moderators' GET /moderation/match-chat/{host_match_id}, driven through the
 * real Hono app against every migration in an in-memory SQLite
 * (hub-harness.mts).
 *
 * The hub has no test runner; this is a plain script under tsx, like the
 * signing conformance check. `pnpm test` runs it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { hub } from "./hub-harness.mjs";

const { sqlite, account, call } = hub();

const host = await account("host");
const other = await account("other");
const mod = await account("mod", "moderator");
await account("subject");

const MATCH = "0123456789abcdef0123";
const line = (over: Record<string, unknown> = {}) => ({
  t_ms: 61_000,
  index: 1,
  name: "SubjectSteam",
  text: "gg ez",
  ...over,
});

// ── POST /matches/chat ────────────────────────────────────────────────

test("first send records the log", async () => {
  const r = await call("POST", "/matches/chat", host, {
    host_match_id: MATCH,
    map_code: "BGL",
    started_at: Math.floor(Date.now() / 1000) - 120,
    lines: [
      line({ user_id: "subject", display: "subject display", team: "red" }),
      line({ index: 0, name: "HostSteam", text: "report him", channel: "team", team: "blue" }),
    ],
  });
  assert.equal(r.status, 201);
  assert.deepEqual(r.body, { host_match_id: MATCH, lines: 2 });
  const rows = sqlite.prepare(`SELECT * FROM match_chat_lines WHERE host_match_id = ?1 ORDER BY seq`).all(MATCH);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].seq, 0);
  assert.equal(rows[0].user_id, "subject");
  assert.equal(rows[0].channel, "all");
  assert.equal(rows[1].channel, "team");
});

test("the same host's resend replaces every line", async () => {
  const r = await call("POST", "/matches/chat", host, {
    host_match_id: MATCH,
    lines: [line({ text: "first" }), line({ text: "second" }), line({ text: "third", index: -1, name: "Server" })],
  });
  assert.equal(r.status, 200);
  assert.deepEqual(r.body, { host_match_id: MATCH, lines: 3 });
  const rows = sqlite
    .prepare(`SELECT seq, text FROM match_chat_lines WHERE host_match_id = ?1 ORDER BY seq`)
    .all(MATCH);
  assert.deepEqual(
    rows.map((x) => [x.seq, x.text]),
    [
      [0, "first"],
      [1, "second"],
      [2, "third"],
    ],
  );
  const head = sqlite.prepare(`SELECT * FROM match_chat_logs WHERE host_match_id = ?1`).all(MATCH)[0];
  assert.equal(head.line_count, 3);
  // A resend without map or start keeps what the first said.
  assert.equal(head.map_code, "BGL");
  assert.ok(head.started_at);
});

test("another account's send for the same match is a 409 and changes nothing", async () => {
  const r = await call("POST", "/matches/chat", other, { host_match_id: MATCH, lines: [line({ text: "forged" })] });
  assert.equal(r.status, 409);
  const n = sqlite.prepare(`SELECT COUNT(*) AS n FROM match_chat_lines WHERE host_match_id = ?1`).all(MATCH)[0].n;
  assert.equal(n, 3);
});

test("an empty log is recorded, then replaced", async () => {
  const id = "fedcba9876543210";
  const a = await call("POST", "/matches/chat", other, { host_match_id: id, lines: [] });
  assert.equal(a.status, 201);
  assert.equal(a.body.lines, 0);
  const b = await call("POST", "/matches/chat", other, { host_match_id: id, lines: [] });
  assert.equal(b.status, 200);
});

test("a log of more lines than one insert takes is stored whole", async () => {
  const id = "aaaaaaaaaaaaaaaa";
  const lines = Array.from({ length: 2500 }, (_, i) => line({ t_ms: i * 100, text: `line ${i}` }));
  const r = await call("POST", "/matches/chat", host, { host_match_id: id, lines });
  assert.equal(r.status, 201);
  const rows = sqlite
    .prepare(`SELECT COUNT(*) AS n, MAX(seq) AS top FROM match_chat_lines WHERE host_match_id = ?1`)
    .all(id)[0];
  assert.equal(rows.n, 2500);
  assert.equal(rows.top, 2499);
});

test("invalid logs are 400s", async () => {
  const bad: unknown[] = [
    { host_match_id: "not-hex", lines: [] },
    { host_match_id: MATCH, lines: [line({ text: "x".repeat(301) })] },
    { host_match_id: MATCH, lines: [line({ text: "" })] },
    { host_match_id: MATCH, lines: [line({ index: 16 })] },
    { host_match_id: MATCH, lines: [line({ name: "   " })] },
    { host_match_id: MATCH, lines: [line({ channel: "whisper" })] },
    { host_match_id: MATCH, lines: [line({ team: "green" })] },
    { host_match_id: MATCH, map_code: "bgl", lines: [] },
    { host_match_id: MATCH, lines: Array.from({ length: 5001 }, () => line()) },
  ];
  for (const body of bad) {
    const r = await call("POST", "/matches/chat", host, body);
    assert.equal(r.status, 400, JSON.stringify(body).slice(0, 120));
  }
});

test("sending needs a key", async () => {
  const r = await call("POST", "/matches/chat", null, { host_match_id: MATCH, lines: [] });
  assert.equal(r.status, 401);
});

// ── GET /moderation/match-chat/{host_match_id} ────────────────────────

test("a moderator reads the log", async () => {
  await call("POST", "/matches/chat", host, {
    host_match_id: MATCH,
    lines: [
      line({ user_id: "subject", display: "subject display", team: "red" }),
      line({ index: 0, name: "HostSteam", text: "report him", channel: "team", team: "blue", t_ms: 75_500 }),
    ],
  });
  const r = await call("GET", `/moderation/match-chat/${MATCH}`, mod);
  assert.equal(r.status, 200);
  assert.equal(r.body.host_match_id, MATCH);
  assert.equal(r.body.map_code, "BGL");
  assert.equal((r.body.reporter as { id: string }).id, "host");
  assert.equal((r.body.reporter as { name: string }).name, "host display");
  assert.deepEqual(r.body.lines, [
    {
      seq: 0,
      t_ms: 61_000,
      index: 1,
      name: "SubjectSteam",
      user_id: "subject",
      display_name: "subject display",
      team: "red",
      channel: "all",
      text: "gg ez",
    },
    {
      seq: 1,
      t_ms: 75_500,
      index: 0,
      name: "HostSteam",
      user_id: null,
      display_name: null,
      team: "blue",
      channel: "team",
      text: "report him",
    },
  ]);
});

test("no log is a 404", async () => {
  const r = await call("GET", "/moderation/match-chat/1111111111111111", mod);
  assert.equal(r.status, 404);
});

test("players cannot read logs, not even their own match's", async () => {
  assert.equal((await call("GET", `/moderation/match-chat/${MATCH}`, host)).status, 403);
  assert.equal((await call("GET", `/moderation/match-chat/${MATCH}`, other)).status, 403);
  assert.equal((await call("GET", "/moderation/match-chat/1111111111111111", other)).status, 403);
  assert.equal((await call("GET", `/moderation/match-chat/${MATCH}`, null)).status, 401);
});

// ── The report queue says which reports have a log ────────────────────

test("player reports carry the log's line count", async () => {
  sqlite
    .prepare(
      `INSERT INTO player_reports (id, reporter_id, subject_id, reason, host_match_id) VALUES
       ('r1', 'host', 'subject', 'harassment', ?1), ('r2', 'other', 'subject', 'cheating', NULL)`,
    )
    .run(MATCH);
  const r = await call("GET", "/moderation/player-reports", mod);
  assert.equal(r.status, 200);
  const players = r.body.players as { reports: { id: string; chat_lines: number | null }[] }[];
  const byId = new Map(players[0].reports.map((x) => [x.id, x.chat_lines]));
  assert.equal(byId.get("r1"), 2);
  assert.equal(byId.get("r2"), null);
});

// ── A public match's chat on its match page ───────────────────────────

const PUBLIC = "b0b0b0b0b0b0b0b0b0b0";

async function reportMatch(key: string, hostMatchId: string) {
  return call("POST", "/matches", key, {
    host_match_id: hostMatchId,
    lobby_id: `lobby-${hostMatchId}`,
    map_code: "BGL",
    game_type: "slayer",
    team_game: true,
    started_at: Math.floor(Date.now() / 1000) - 600,
    duration_ms: 300_000,
    end_reason: "game_over",
    host_index: 0,
    players: [
      { index: 0, name: "HostSteam", team: "blue", score: 5, kills: 5 },
      { index: 1, name: "SubjectSteam", team: "red", score: 3, kills: 3 },
      { index: 2, name: "Stranger", team: "red", score: 1, kills: 1 },
    ],
  });
}

test("a public match's page carries its chat, linking only linked seats' accounts", async () => {
  const subject = "mjc_test_subject";
  const reported = await reportMatch(host, PUBLIC);
  assert.equal(reported.status, 201);
  const matchId = reported.body.id as string;
  const claim = await call("POST", "/matches/claims", subject, {
    host_match_id: PUBLIC,
    player_index: 1,
    name: "SubjectSteam",
  });
  assert.equal(claim.body.linked, true);
  const sent = await call("POST", "/matches/chat", host, {
    host_match_id: PUBLIC,
    map_code: "BGL",
    lines: [
      line({ index: 0, name: "HostSteam", user_id: "host", display: "host display", team: "blue", t_ms: 1000, text: "glhf" }),
      line({ index: 1, name: "SubjectSteam", user_id: "subject", display: "subject display", team: "red", t_ms: 2000, text: "push top", channel: "team" }),
      // The host names an account the seat is not linked to: no link.
      line({ index: 2, name: "Stranger", user_id: "other", display: "other display", team: "red", t_ms: 3000, text: "hi" }),
      // A linked seat, but the line names someone else's account.
      line({ index: 1, name: "SubjectSteam", user_id: "mod", display: "mod display", team: "red", t_ms: 4000, text: "x" }),
    ],
  });
  assert.equal(sent.status, 201);

  const r = await call("GET", `/matches/${matchId}`, null);
  assert.equal(r.status, 200);
  const chat = r.body.chat as {
    t_ms: number;
    index: number;
    name: string;
    display_name: string | null;
    user: { id: string; name: string } | null;
    team: string | null;
    channel: string;
    text: string;
  }[];
  assert.deepEqual(
    chat.map((l) => [l.t_ms, l.index, l.name, l.user?.id ?? null, l.display_name, l.channel, l.text]),
    [
      [1000, 0, "HostSteam", "host", "host display", "all", "glhf"],
      [2000, 1, "SubjectSteam", "subject", "subject display", "team", "push top"],
      [3000, 2, "Stranger", null, null, "all", "hi"],
      [4000, 1, "SubjectSteam", null, null, "all", "x"],
    ],
  );
  assert.equal(chat[1].user?.name, "subject display");
  assert.equal(chat[1].team, "red");
});

test("a match with no chat log has an empty chat", async () => {
  const id = "c1c1c1c1c1c1c1c1";
  const reported = await reportMatch(host, id);
  const r = await call("GET", `/matches/${reported.body.id as string}`, null);
  assert.deepEqual(r.body.chat, []);
});

test("a log sent under a public match's id by another account stays off its page", async () => {
  const id = "d2d2d2d2d2d2d2d2";
  assert.equal((await call("POST", "/matches/chat", other, { host_match_id: id, lines: [line({ text: "planted" })] })).status, 201);
  const reported = await reportMatch(host, id);
  assert.equal(reported.status, 201);
  const r = await call("GET", `/matches/${reported.body.id as string}`, null);
  assert.deepEqual(r.body.chat, []);
});

test("a private game's log is not on any public page", async () => {
  // MATCH has a chat log but was never reported as a match.
  const list = await call("GET", "/matches?limit=50", null);
  assert.equal(list.status, 200);
  assert.ok(!JSON.stringify(list.body).includes("gg ez"));
  assert.equal((await call("GET", `/matches/${MATCH}`, null)).status, 404);
  for (const m of list.body.matches as { id: string }[]) {
    const page = await call("GET", `/matches/${m.id}`, null);
    assert.ok(!JSON.stringify(page.body).includes("gg ez"));
  }
});
