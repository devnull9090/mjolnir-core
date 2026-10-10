/**
 * The multiplayer lobby browser: games hosts list and players find and join
 * (docs/multiplayer_release_plan.md, item 5).
 *
 * A host registers its game and gets a per-lobby token, proves it on every
 * heartbeat and on removal, and the row disappears from listings once its
 * heartbeat is stale. A listing carries everything a browser shows — map,
 * game type, players, where the host is — but never the connection string,
 * the one thing a client needs to join the host's PlayFab lobby
 * (docs/fireteam_join_and_cap.md). That comes from /join, to signed-in
 * callers only.
 *
 * Ping is an estimate: before players connect nothing can measure the path
 * between them, so it is the great-circle distance between the caller's
 * and the host's Cloudflare-reported locations at fibre speed, plus a fixed
 * overhead. Good enough to sort near games first.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { Context } from "hono";

import type { ApiEnv } from "./bindings";
import { authenticate, rateLimit, requireScoped, sha256Hex } from "./auth";
import { banActiveFor, refuseBanned } from "./players";
import { ErrorSchema } from "./schemas";

type Ctx = Context<ApiEnv>;

/** How often a host should heartbeat, and when its game drops out of view. */
export const HEARTBEAT_SECONDS = 30;
const STALE_SECONDS = 90;
/** Rows this old are deleted rather than merely hidden. */
const SWEEP_SECONDS = 600;
const MAX_LISTED = 100;

const GAME_TYPE = z.string().regex(/^[a-z_]{1,24}$/);
const MAP_CODE = z.string().regex(/^[A-Z0-9]{3}$/);
const STATES = ["open", "in_game", "full"] as const;
/**
 * The host's game settings (docs/host_game_settings.md): `key=value;...`
 * of Megalo variant fields, empty for the variant's own rules. Only the
 * shape is checked here; each player's level loader refuses a field it does
 * not know.
 */
const SETTINGS = z
  .string()
  .max(400)
  .regex(/^([a-z0-9_.]{1,40}=\d{1,5}(;[a-z0-9_.]{1,40}=\d{1,5})*)?$/)
  .openapi({ example: "score.ctf=3;score.slayer=15;time_limit=5;trait.shields=1" });

/**
 * The hub release of its map the host runs (docs/live_map_install.md): a
 * joiner with another release would not start with the host, so the game
 * installs this one first.
 */
const MAP_RELEASE_ID = z.string().uuid();
const MAP_VERSION = z.string().max(40);

const LobbyCreateSchema = z
  .object({
    name: z.string().trim().min(1).max(60),
    map_code: MAP_CODE,
    game_type: GAME_TYPE,
    players: z.number().int().min(0).max(16).default(1),
    max_players: z.number().int().min(1).max(16).default(4),
    client_version: z.string().min(1).max(40),
    game_build: z.string().max(80).optional(),
    platform: z.enum(["steam", "gamepass", "other"]).optional(),
    connection_string: z.string().min(1).max(4096),
    settings: SETTINGS.optional(),
    map_release_id: MAP_RELEASE_ID.optional(),
    map_version: MAP_VERSION.optional(),
  })
  .openapi("LobbyCreate");

const LobbyUpdateSchema = z
  .object({
    token: z.string().min(1),
    players: z.number().int().min(0).max(16).optional(),
    max_players: z.number().int().min(1).max(16).optional(),
    map_code: MAP_CODE.optional(),
    game_type: GAME_TYPE.optional(),
    state: z.enum(STATES).optional(),
    connection_string: z.string().min(1).max(4096).optional(),
    settings: SETTINGS.optional(),
    map_release_id: MAP_RELEASE_ID.optional(),
    map_version: MAP_VERSION.optional(),
  })
  .openapi("LobbyHeartbeat");

const LobbySchema = z
  .object({
    id: z.string(),
    name: z.string(),
    host: z.string(),
    map_code: z.string(),
    map_title: z.string().nullable(),
    game_type: z.string(),
    players: z.number(),
    max_players: z.number(),
    state: z.enum(STATES),
    client_version: z.string(),
    platform: z.string().nullable(),
    colo: z.string().nullable(),
    country: z.string().nullable(),
    /** Estimated round trip from the caller, in ms; null without locations. */
    ping_ms: z.number().nullable(),
    /** The host's game settings; null from a host without them. */
    settings: z.string().nullable(),
    /** The hub release of the map the host runs; null when unknown. */
    map_release_id: z.string().nullable(),
    map_version: z.string().nullable(),
    created_at: z.string(),
  })
  .openapi("Lobby");

interface Where {
  colo: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
}

/** Cloudflare's view of where a request came from. */
function whereFrom(c: Ctx): Where {
  const cf = (c.req.raw as unknown as { cf?: Record<string, unknown> }).cf ?? {};
  const num = (v: unknown) => (v === undefined || v === null || v === "" ? null : Number(v));
  return {
    colo: (cf.colo as string) ?? null,
    country: (cf.country as string) ?? null,
    latitude: num(cf.latitude),
    longitude: num(cf.longitude),
  };
}

/** Great-circle distance at fibre speed (~200 km/ms each way) plus overhead. */
export function estimatePingMs(
  a: { latitude: number | null; longitude: number | null },
  b: { latitude: number | null; longitude: number | null },
): number | null {
  if (a.latitude === null || a.longitude === null || b.latitude === null || b.longitude === null) {
    return null;
  }
  const rad = Math.PI / 180;
  const dLat = (b.latitude - a.latitude) * rad;
  const dLon = (b.longitude - a.longitude) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.latitude * rad) * Math.cos(b.latitude * rad) * Math.sin(dLon / 2) ** 2;
  const km = 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(h)));
  // Routes run longer than great circles; 1.5x is the usual allowance.
  return Math.round((km * 1.5 * 2) / 200 + 10);
}

function randomToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** The lobby, if `token` is its host's. */
async function hostedLobby(c: Ctx, id: string, token: string) {
  const row = await c.env.DB.prepare(`SELECT id, host_token_hash FROM lobbies WHERE id = ?1`)
    .bind(id)
    .first<{ id: string; host_token_hash: string }>();
  if (!row) return null;
  return row.host_token_hash === (await sha256Hex(token)) ? row : null;
}

function sweep(c: Ctx) {
  c.executionCtx.waitUntil(
    c.env.DB.prepare(`DELETE FROM lobbies WHERE last_heartbeat < datetime('now', ?1)`)
      .bind(`-${SWEEP_SECONDS} seconds`)
      .run() as unknown as Promise<unknown>,
  );
}

type Db = ApiEnv["Bindings"]["DB"];
type LobbyListQuery = {
  map?: string;
  game_type?: string;
  version?: string;
  has_space?: boolean;
  max_ping?: number;
};

/**
 * Live games, nearest first, for a caller at `me`; the API's and the
 * page's.
 */
export async function listLobbies(
  db: Db,
  q: LobbyListQuery,
  me: { latitude: number | null; longitude: number | null },
): Promise<z.infer<typeof LobbySchema>[]> {
  // A host banned from matchmaking has its row deleted when banned; this
  // also hides one that re-listed in the moment between.
  const clauses = [`l.last_heartbeat >= datetime('now', ?1)`, `NOT ${banActiveFor("l.host_user_id")}`];
  const binds: unknown[] = [`-${STALE_SECONDS} seconds`];
  if (q.map) {
    binds.push(q.map);
    clauses.push(`l.map_code = ?${binds.length}`);
  }
  if (q.game_type) {
    binds.push(q.game_type);
    clauses.push(`l.game_type = ?${binds.length}`);
  }
  if (q.version) {
    binds.push(q.version);
    clauses.push(`l.client_version = ?${binds.length}`);
  }
  if (q.has_space) clauses.push(`l.players < l.max_players AND l.state <> 'full'`);
  const rows = await db
    .prepare(
      `SELECT l.*, COALESCE(u.display_name, u.discord_username) AS host, ml.title AS map_title
       FROM lobbies l
       JOIN users u ON u.id = l.host_user_id
       LEFT JOIN map_listings ml ON ml.code = l.map_code
       WHERE ${clauses.join(" AND ")}
       ORDER BY l.created_at DESC LIMIT ${MAX_LISTED}`,
    )
    .bind(...binds)
    .all();
  return rows.results
    .map((r) => ({
      id: r.id as string,
      name: r.name as string,
      host: r.host as string,
      map_code: r.map_code as string,
      map_title: (r.map_title as string) ?? null,
      game_type: r.game_type as string,
      players: r.players as number,
      max_players: r.max_players as number,
      state: r.state as (typeof STATES)[number],
      client_version: r.client_version as string,
      platform: (r.platform as string) ?? null,
      colo: (r.colo as string) ?? null,
      country: (r.country as string) ?? null,
      ping_ms: estimatePingMs(me, {
        latitude: (r.latitude as number) ?? null,
        longitude: (r.longitude as number) ?? null,
      }),
      settings: (r.settings as string) ?? null,
      map_release_id: (r.map_release_id as string) ?? null,
      map_version: (r.map_version as string) ?? null,
      created_at: r.created_at as string,
    }))
    .filter((l) => q.max_ping === undefined || (l.ping_ms !== null && l.ping_ms <= q.max_ping))
    .sort(
      (a, b) =>
        (a.ping_ms ?? Number.MAX_SAFE_INTEGER) - (b.ping_ms ?? Number.MAX_SAFE_INTEGER) ||
        b.players - a.players,
    );
}

export function registerLobbyRoutes(app: OpenAPIHono<ApiEnv>) {
  // ── Register ────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/lobbies",
      tags: ["lobbies"],
      summary: "List a game in the lobby browser",
      description:
        "Registers the caller's game and returns a per-lobby token the host proves on " +
        "every heartbeat and on removal. A host has one listed game: registering again " +
        "replaces the previous one. Needs the `lobbies:write` scope.",
      request: { body: { content: { "application/json": { schema: LobbyCreateSchema } } } },
      responses: {
        201: {
          description: "Listed.",
          content: {
            "application/json": {
              schema: z.object({
                id: z.string(),
                token: z.string(),
                heartbeat_seconds: z.number(),
                stale_seconds: z.number(),
              }),
            },
          },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: {
          description: "Missing scope, or banned from matchmaking.",
          content: { "application/json": { schema: ErrorSchema } },
        },
        429: { description: "Too many games listed.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await requireScoped(c, "lobbies:write", "lobby_create", 60);
      const banned = await refuseBanned(c, auth.user.id);
      if (banned) return banned;
      const body = c.req.valid("json");
      const id = crypto.randomUUID();
      const token = randomToken();
      const where = whereFrom(c);
      await c.env.DB.batch([
        c.env.DB.prepare(`DELETE FROM lobbies WHERE host_user_id = ?1`).bind(auth.user.id),
        c.env.DB.prepare(
          `INSERT INTO lobbies (id, host_user_id, host_token_hash, name, map_code, game_type,
             players, max_players, client_version, game_build, platform, connection_string,
             colo, country, latitude, longitude, settings, map_release_id, map_version)
           VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19)`,
        ).bind(
          id,
          auth.user.id,
          await sha256Hex(token),
          body.name,
          body.map_code,
          body.game_type,
          Math.min(body.players, body.max_players),
          body.max_players,
          body.client_version,
          body.game_build ?? null,
          body.platform ?? null,
          body.connection_string,
          where.colo,
          where.country,
          where.latitude,
          where.longitude,
          body.settings ?? null,
          body.map_release_id ?? null,
          body.map_version ?? null,
        ),
      ]);
      sweep(c);
      return c.json(
        { id, token, heartbeat_seconds: HEARTBEAT_SECONDS, stale_seconds: STALE_SECONDS },
        201,
      );
    },
  );

  // ── Heartbeat ───────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/lobbies/{id}/heartbeat",
      tags: ["lobbies"],
      summary: "Keep a listed game alive, and update what changed",
      request: {
        params: z.object({ id: z.string() }),
        body: { content: { "application/json": { schema: LobbyUpdateSchema } } },
      },
      responses: {
        200: { description: "Alive.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        404: { description: "No such game, or not its host.", content: { "application/json": { schema: ErrorSchema } } },
        429: { description: "Heartbeating too fast.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const body = c.req.valid("json");
      // Twice the expected rate, per lobby.
      if (!(await rateLimit(c, `lobby:${id}`, "lobby_heartbeat", (3600 / HEARTBEAT_SECONDS) * 2))) {
        return c.json({ error: "rate_limited" }, 429);
      }
      if (!(await hostedLobby(c, id, body.token))) return c.json({ error: "not_found" }, 404);
      await c.env.DB.prepare(
        `UPDATE lobbies SET
           players = COALESCE(?2, players),
           max_players = COALESCE(?3, max_players),
           map_code = COALESCE(?4, map_code),
           game_type = COALESCE(?5, game_type),
           state = COALESCE(?6, state),
           connection_string = COALESCE(?7, connection_string),
           settings = COALESCE(?8, settings),
           map_release_id = CASE WHEN ?4 IS NULL THEN COALESCE(?9, map_release_id) ELSE ?9 END,
           map_version = CASE WHEN ?4 IS NULL THEN COALESCE(?10, map_version) ELSE ?10 END,
           last_heartbeat = datetime('now')
         WHERE id = ?1`,
      )
        .bind(
          id,
          body.players ?? null,
          body.max_players ?? null,
          body.map_code ?? null,
          body.game_type ?? null,
          body.state ?? null,
          body.connection_string ?? null,
          body.settings ?? null,
          body.map_release_id ?? null,
          body.map_version ?? null,
        )
        .run();
      return c.json({ ok: true }, 200);
    },
  );

  // ── Remove ──────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "delete",
      path: "/lobbies/{id}",
      tags: ["lobbies"],
      summary: "Take a game out of the lobby browser",
      request: {
        params: z.object({ id: z.string() }),
        body: { content: { "application/json": { schema: z.object({ token: z.string().min(1) }) } } },
      },
      responses: {
        200: { description: "Removed.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        404: { description: "No such game, or not its host.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const { token } = c.req.valid("json");
      if (!(await hostedLobby(c, id, token))) return c.json({ error: "not_found" }, 404);
      await c.env.DB.prepare(`DELETE FROM lobbies WHERE id = ?1`).bind(id).run();
      return c.json({ ok: true }, 200);
    },
  );

  // ── Browse ──────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/lobbies",
      tags: ["lobbies"],
      summary: "Find games: by map, game type, version and room, nearest first",
      request: {
        query: z.object({
          map: MAP_CODE.optional(),
          game_type: GAME_TYPE.optional(),
          version: z.string().max(40).optional(),
          has_space: z.enum(["0", "1"]).default("0"),
          max_ping: z.coerce.number().int().min(1).max(1000).optional(),
        }),
      },
      responses: {
        200: {
          description: "Live games, sorted by estimated ping then players.",
          content: { "application/json": { schema: z.object({ lobbies: z.array(LobbySchema) }) } },
        },
      },
    }),
    async (c) => {
      const q = c.req.valid("query");
      const lobbies = await listLobbies(
        c.env.DB,
        { ...q, has_space: q.has_space === "1" },
        whereFrom(c),
      );
      sweep(c);
      return c.json({ lobbies }, 200);
    },
  );

  // ── Join ────────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/lobbies/{id}/join",
      tags: ["lobbies"],
      summary: "The connection string to join a listed game (signed in)",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: {
          description: "Join with this.",
          content: {
            "application/json": {
              schema: z.object({
                connection_string: z.string(),
                map_code: z.string(),
                game_type: z.string(),
                /** The host's game settings, to play the match by its rules. */
                settings: z.string().nullable(),
                /** The release of the map to have before joining; null when unknown. */
                map_release_id: z.string().nullable(),
                map_version: z.string().nullable(),
              }),
            },
          },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Banned from matchmaking.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "Gone, or not live.", content: { "application/json": { schema: ErrorSchema } } },
        409: { description: "Full.", content: { "application/json": { schema: ErrorSchema } } },
        429: { description: "Too many joins.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await authenticate(c);
      if (!auth) return c.json({ error: "unauthenticated" }, 401);
      if (!(await rateLimit(c, auth.subject, "lobby_join", 120))) {
        return c.json({ error: "rate_limited" }, 429);
      }
      const banned = await refuseBanned(c, auth.user.id);
      if (banned) return banned;
      const { id } = c.req.valid("param");
      const row = await c.env.DB.prepare(
        `SELECT connection_string, map_code, game_type, players, max_players, state, settings,
           map_release_id, map_version
         FROM lobbies WHERE id = ?1 AND last_heartbeat >= datetime('now', ?2)`,
      )
        .bind(id, `-${STALE_SECONDS} seconds`)
        .first<{
          connection_string: string;
          map_code: string;
          game_type: string;
          players: number;
          max_players: number;
          state: string;
          settings: string | null;
          map_release_id: string | null;
          map_version: string | null;
        }>();
      if (!row) return c.json({ error: "not_found" }, 404);
      if (row.state === "full" || row.players >= row.max_players) {
        return c.json({ error: "full", message: "That game is full." }, 409);
      }
      return c.json(
        {
          connection_string: row.connection_string,
          map_code: row.map_code,
          game_type: row.game_type,
          settings: row.settings ?? null,
          map_release_id: row.map_release_id ?? null,
          map_version: row.map_version ?? null,
        },
        200,
      );
    },
  );
}
