/**
 * Match chat logs (migrations/0020): the host's POST /matches/chat and the
 * moderators' GET /moderation/match-chat/{host_match_id}, driven through the
 * real Hono app against every migration in an in-memory SQLite.
 *
 * The hub has no test runner; this is a plain script under tsx, like the
 * signing conformance check. `pnpm test` runs it. The D1 binding is a thin
 * shim over node:sqlite (Node 22.5+), which is enough for what these routes
 * call: prepare, bind, first, all, run and batch.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { app } from "../src/lib/api/app";
import { sha256Hex } from "../src/lib/api/auth";

// ── A D1 over node:sqlite ─────────────────────────────────────────────

interface SqliteStatement {
  all(...params: unknown[]): Record<string, unknown>[];
  run(...params: unknown[]): { changes: number | bigint };
}
interface SqliteDatabase {
  exec(sql: string): void;
  prepare(sql: string): SqliteStatement;
}
// Through a variable, so the type check (on @types/node 20, which has no
// node:sqlite) does not go looking for the module.
const sqliteModule = "node:sqlite";
const { DatabaseSync } = (await import(sqliteModule)) as {
  DatabaseSync: new (path: string) => SqliteDatabase;
};

class Stmt {
  constructor(
    private readonly db: SqliteDatabase,
    private readonly sql: string,
    private readonly params: unknown[] = [],
  ) {}
  bind(...params: unknown[]) {
    return new Stmt(this.db, this.sql, params);
  }
  exec() {
    const rows = this.db.prepare(this.sql).all(...this.params);
    const changes = Number(this.db.prepare("SELECT changes() AS n").all()[0].n);
    return { results: rows, success: true, meta: { changes } };
  }
  async first<T>(column?: string): Promise<T | null> {
    const row = this.exec().results[0];
    if (!row) return null;
    return (column ? row[column] : row) as T;
  }
  async all() {
    return this.exec();
  }
  async run() {
    return this.exec();
  }
}

function d1(db: SqliteDatabase) {
  return {
    prepare: (sql: string) => new Stmt(db, sql),
    // D1 runs a batch as one transaction.
    batch: async (stmts: Stmt[]) => {
      db.exec("BEGIN");
      try {
        const out = stmts.map((s) => s.exec());
        db.exec("COMMIT");
        return out;
      } catch (e) {
        db.exec("ROLLBACK");
        throw e;
      }
    },
  };
}

// ── Fixture ───────────────────────────────────────────────────────────

const sqlite = new DatabaseSync(":memory:");
sqlite.exec("PRAGMA foreign_keys = ON");
const migrations = join(dirname(fileURLToPath(import.meta.url)), "..", "migrations");
for (const f of readdirSync(migrations).filter((f) => f.endsWith(".sql")).sort()) {
  sqlite.exec(readFileSync(join(migrations, f), "utf8"));
}
const env = { DB: d1(sqlite), SITE_URL: "http://localhost" };
const ctx = { waitUntil() {}, passThroughOnException() {}, props: {} };

/** An account with a launcher key; returns the key. */
async function account(id: string, role: "user" | "moderator" = "user"): Promise<string> {
  const key = `mjc_test_${id}`;
  sqlite
    .prepare(`INSERT INTO users (id, discord_id, discord_username, display_name, role) VALUES (?1, ?2, ?3, ?4, ?5)`)
    .run(id, `discord-${id}`, `${id}_discord`, `${id} display`, role);
  sqlite
    .prepare(
      `INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, scopes) VALUES (?1, ?2, 'test', ?3, 'mjc_', 'lobbies:write')`,
    )
    .run(`key-${id}`, id, await sha256Hex(key));
  return key;
}

async function call(method: string, path: string, key: string | null, body?: unknown) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (key) headers.authorization = `Bearer ${key}`;
  const res = await app.request(
    `/api/v1${path}`,
    { method, headers, body: body === undefined ? undefined : JSON.stringify(body) },
    env,
    ctx as never,
  );
  return { status: res.status, body: (await res.json()) as Record<string, unknown> };
}

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
