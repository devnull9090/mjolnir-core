/**
 * The real Hono app against every migration in an in-memory SQLite, for the
 * route tests under tsx (test-match-chat.mts, test-benches.mts). The D1
 * binding is a thin shim over node:sqlite (Node 22.5+), which is enough for
 * what the routes call: prepare, bind, first, all, run and batch.
 */
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { app } from "../src/lib/api/app";
import { sha256Hex } from "../src/lib/api/auth";

interface SqliteStatement {
  all(...params: unknown[]): Record<string, unknown>[];
  run(...params: unknown[]): { changes: number | bigint };
}
export interface SqliteDatabase {
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

/** A fresh database with every migration, and helpers to call the API. */
export function hub() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec("PRAGMA foreign_keys = ON");
  const migrations = join(dirname(fileURLToPath(import.meta.url)), "..", "migrations");
  for (const f of readdirSync(migrations).filter((f) => f.endsWith(".sql")).sort()) {
    sqlite.exec(readFileSync(join(migrations, f), "utf8"));
  }
  const env = { DB: d1(sqlite), SITE_URL: "http://localhost" };
  const ctx = { waitUntil() {}, passThroughOnException() {}, props: {} };

  /** An account with a launcher key; returns the key. */
  async function account(id: string, role: "user" | "moderator" | "admin" = "user"): Promise<string> {
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

  return { sqlite, env, account, call };
}
