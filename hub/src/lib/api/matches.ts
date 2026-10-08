/**
 * Match history: what happened in each public multiplayer match
 * (docs/match_stats.md, migrations/0014_matches.sql).
 *
 * The host's game reports a match when it ends: the final standings, and
 * every incident the simulation raised in order, each with where the players
 * involved stood. The host's own seat is linked to the reporting account.
 * Every other participant's game claims its seat with its own key, citing
 * the host's id for the match (which only the fireteam was told); a claim
 * and a report can land in either order, and whichever lands second links
 * the seat. A claim links only a seat of the claimed name.
 *
 * Both writes take `lobbies:write`, the scope a launcher key already has for
 * listing games: reporting and claiming are the same kind of act, taking
 * part in public games, and a new scope would have meant every player
 * signing in again (migrations/0013).
 *
 * What a report says is the host's word. The standings are recorded as
 * reported; ranking built on them later should weigh hosts accordingly.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";

import type { ApiEnv } from "./bindings";
import { requireScoped } from "./auth";
import { ErrorSchema, avatarUrl } from "./schemas";

type Db = ApiEnv["Bindings"]["DB"];

const MAP_CODE = z.string().regex(/^[A-Z0-9]{3}$/);
const GAME_TYPE = z.string().regex(/^[a-z_]{1,24}$/);
const HOST_MATCH_ID = z.string().regex(/^[0-9a-f]{16,64}$/);
const PLAYER_INDEX = z.number().int().min(0).max(15);
const PLAYER_NAME = z.string().trim().min(1).max(64);
const END_REASONS = ["round_over", "game_over", "abandoned"] as const;
const OUTCOMES = ["win", "loss", "draw"] as const;

/** A match longer than this is not one. */
const MAX_DURATION_MS = 6 * 3600 * 1000;
export const MAX_EVENTS = 20000;
const PAGE = 25;

const Position = z
  .tuple([z.number(), z.number(), z.number()])
  .openapi({ description: "Unreal world space, centimetres, Z up.", example: [12034.5, -3310.2, 405.0] });

const MatchEventInputSchema = z
  .object({
    t_ms: z.number().int().min(0).max(MAX_DURATION_MS),
    type: z.string().regex(/^[a-z0-9_]{1,40}$/).openapi({ example: "kill" }),
    cause: z.number().int().min(-1).max(15).default(-1),
    effect: z.number().int().min(-1).max(15).default(-1),
    value: z.number().int().nullable().optional(),
    weapon: z.string().regex(/^[A-Za-z0-9_]{1,48}$/).nullable().optional().openapi({ example: "AssaultRifle" }),
    modifier: z.number().int().min(0).max(64).nullable().optional(),
    cause_pos: Position.nullable().optional(),
    effect_pos: Position.nullable().optional(),
  })
  .openapi("MatchEventInput");

const MatchPlayerInputSchema = z
  .object({
    index: PLAYER_INDEX,
    name: PLAYER_NAME,
    team: z.enum(["red", "blue"]).nullable().optional(),
    score: z.number().int().min(-1000).max(100000).default(0),
    kills: z.number().int().min(0).max(100000).default(0),
    deaths: z.number().int().min(0).max(100000).default(0),
    suicides: z.number().int().min(0).max(100000).default(0),
    captures: z.number().int().min(0).max(100000).default(0),
    left: z.boolean().default(false),
  })
  .openapi("MatchPlayerInput");

const MatchReportSchema = z
  .object({
    host_match_id: HOST_MATCH_ID,
    lobby_id: z.string().min(1).max(64),
    map_code: MAP_CODE,
    game_type: GAME_TYPE,
    team_game: z.boolean().default(false),
    score_to_win: z.number().int().min(0).max(100000).nullable().optional(),
    /** Unix seconds, the host's clock. */
    started_at: z.number().int().min(0),
    duration_ms: z.number().int().min(0).max(MAX_DURATION_MS),
    end_reason: z.enum(END_REASONS),
    /** The host's own seat, linked to the reporting account. */
    host_index: PLAYER_INDEX.nullable().optional(),
    team_scores: z
      .object({ red: z.number().int().min(0), blue: z.number().int().min(0) })
      .nullable()
      .optional(),
    client_version: z.string().max(40).optional(),
    players: z.array(MatchPlayerInputSchema).min(1).max(16),
    events: z.array(MatchEventInputSchema).max(MAX_EVENTS).default([]),
  })
  .openapi("MatchReport");

const MatchClaimSchema = z
  .object({
    host_match_id: HOST_MATCH_ID,
    player_index: PLAYER_INDEX,
    name: PLAYER_NAME,
  })
  .openapi("MatchClaim");

const LinkedUserSchema = z.object({
  id: z.string(),
  name: z.string(),
  avatar_url: z.string().nullable(),
});

const MatchPlayerSchema = z
  .object({
    index: z.number(),
    name: z.string(),
    team: z.enum(["red", "blue"]).nullable(),
    score: z.number(),
    kills: z.number(),
    deaths: z.number(),
    suicides: z.number(),
    captures: z.number(),
    place: z.number(),
    outcome: z.enum(OUTCOMES).nullable(),
    left_early: z.boolean(),
    is_host: z.boolean(),
    user: LinkedUserSchema.nullable(),
  })
  .openapi("MatchPlayer");

const MatchSummarySchema = z
  .object({
    id: z.string(),
    map_code: z.string(),
    map_title: z.string().nullable(),
    /** The map's hub page (/mods/{slug}), when its listing is published. */
    map_slug: z.string().nullable(),
    game_type: z.string(),
    team_game: z.boolean(),
    score_to_win: z.number().nullable(),
    started_at: z.string(),
    ended_at: z.string(),
    duration_ms: z.number(),
    end_reason: z.enum(END_REASONS),
    red_score: z.number().nullable(),
    blue_score: z.number().nullable(),
    /** 'red', 'blue', 'draw', a player index, or null when abandoned. */
    winner: z.string().nullable(),
    winner_name: z.string().nullable(),
    /** The free-for-all winner's hub account, when their seat is linked. */
    winner_user: LinkedUserSchema.nullable(),
    player_count: z.number(),
    event_count: z.number(),
    host: z.string(),
    /** With a player or user filter: that player's line. */
    player: MatchPlayerSchema.omit({ user: true }).nullable(),
  })
  .openapi("MatchSummary");

const MatchEventSchema = z
  .object({
    seq: z.number(),
    t_ms: z.number(),
    type: z.string(),
    cause: z.number(),
    effect: z.number(),
    value: z.number().nullable(),
    weapon: z.string().nullable(),
    modifier: z.number().nullable(),
    cause_pos: Position.nullable(),
    effect_pos: Position.nullable(),
  })
  .openapi("MatchEvent");

const MatchDetailSchema = MatchSummarySchema.omit({ player: true })
  .extend({
    players: z.array(MatchPlayerSchema),
    events: z.array(MatchEventSchema),
  })
  .openapi("MatchDetail");

const PlayerTotalsSchema = z
  .object({
    matches: z.number(),
    completed: z.number(),
    wins: z.number(),
    losses: z.number(),
    draws: z.number(),
    kills: z.number(),
    deaths: z.number(),
    suicides: z.number(),
    captures: z.number(),
    last_played: z.string().nullable(),
    weapons: z.array(z.object({ weapon: z.string(), kills: z.number() })),
  })
  .openapi("PlayerTotals");

export type MatchSummary = z.infer<typeof MatchSummarySchema>;
export type MatchDetail = z.infer<typeof MatchDetailSchema>;
export type MatchPlayer = z.infer<typeof MatchPlayerSchema>;
export type MatchEvent = z.infer<typeof MatchEventSchema>;
export type PlayerTotals = z.infer<typeof PlayerTotalsSchema>;
type MatchReport = z.infer<typeof MatchReportSchema>;

// ── Standings ─────────────────────────────────────────────────────────

/**
 * Place, outcome and the match's winner from the reported standings. A
 * team game is won by the team with more points; a free-for-all by the top
 * score, alone (a shared top is a draw). An abandoned match has places but
 * no outcomes.
 */
export function standings(report: Pick<MatchReport, "team_game" | "team_scores" | "end_reason" | "players">) {
  const sorted = [...report.players].sort(
    (a, b) => b.score - a.score || b.kills - a.kills || a.deaths - b.deaths || a.index - b.index,
  );
  const place = new Map<number, number>();
  sorted.forEach((p, i) => {
    const prev = sorted[i - 1];
    place.set(p.index, prev && prev.score === p.score ? place.get(prev.index)! : i + 1);
  });
  const outcome = new Map<number, (typeof OUTCOMES)[number] | null>();
  let winner: string | null = null;
  const finished = report.end_reason !== "abandoned";
  if (report.team_game) {
    const red = report.team_scores?.red ?? sum(report.players, "red");
    const blue = report.team_scores?.blue ?? sum(report.players, "blue");
    const top = red === blue ? null : red > blue ? "red" : "blue";
    if (finished) winner = top ?? "draw";
    for (const p of report.players) {
      outcome.set(p.index, !finished ? null : top === null || !p.team ? "draw" : p.team === top ? "win" : "loss");
    }
  } else {
    const best = sorted[0]?.score ?? 0;
    const atTop = sorted.filter((p) => p.score === best).length;
    const solo = atTop === 1 && best > 0 ? sorted[0] : null;
    if (finished) winner = solo ? String(solo.index) : "draw";
    for (const p of report.players) {
      outcome.set(p.index, !finished ? null : !solo ? (p.score === best ? "draw" : "loss") : p === solo ? "win" : "loss");
    }
  }
  return { place, outcome, winner };
}

function sum(players: MatchReport["players"], team: "red" | "blue"): number {
  return players.filter((p) => p.team === team).reduce((n, p) => n + p.score, 0);
}

/** The host's clock, kept to the last week and never ahead of ours. */
function matchTimes(startedAt: number, durationMs: number): { started: string; ended: string } {
  const now = Date.now();
  let start = startedAt * 1000;
  if (!(start >= now - 7 * 86400 * 1000) || start + durationMs > now + 60_000) start = now - durationMs;
  const iso = (ms: number) => new Date(ms).toISOString().replace("T", " ").replace(/\.\d+Z$/, "");
  return { started: iso(start), ended: iso(start + durationMs) };
}

// ── Reads ─────────────────────────────────────────────────────────────

type Row = Record<string, unknown>;

function linkedUser(r: Row, prefix = "u_"): z.infer<typeof LinkedUserSchema> | null {
  if (!r[`${prefix}id`]) return null;
  return {
    id: r[`${prefix}id`] as string,
    name: ((r[`${prefix}display_name`] ?? r[`${prefix}username`]) as string) ?? "",
    avatar_url: avatarUrl(r[`${prefix}discord_id`] as string, r[`${prefix}avatar`] as string | null),
  };
}

function playerFromRow(r: Row): Omit<MatchPlayer, "user"> {
  return {
    index: r.player_index as number,
    name: r.name as string,
    team: (r.team as "red" | "blue" | null) ?? null,
    score: r.score as number,
    kills: r.kills as number,
    deaths: r.deaths as number,
    suicides: r.suicides as number,
    captures: r.captures as number,
    place: r.place as number,
    outcome: (r.outcome as (typeof OUTCOMES)[number] | null) ?? null,
    left_early: r.left_early === 1,
    is_host: r.is_host === 1,
  };
}

const SUMMARY_COLUMNS = `
  m.*, ml.title AS map_title, mo.slug AS map_slug,
  COALESCE(h.display_name, h.discord_username) AS host,
  wp.name AS winner_name, wu.id AS w_id, wu.display_name AS w_display_name,
  wu.discord_username AS w_username, wu.discord_id AS w_discord_id, wu.discord_avatar AS w_avatar`;

/** The host, the map's listing and page, and a free-for-all winner's seat and account. */
const SUMMARY_JOINS = `
  JOIN users h ON h.id = m.reporter_user_id
  LEFT JOIN map_listings ml ON ml.code = m.map_code
  LEFT JOIN mods mo ON mo.id = ml.mod_id AND mo.status = 'published'
  LEFT JOIN match_players wp ON wp.match_id = m.id AND CAST(wp.player_index AS TEXT) = m.winner
  LEFT JOIN users wu ON wu.id = wp.user_id AND wu.banned_at IS NULL`;

function summaryFromRow(r: Row): MatchSummary {
  return {
    id: r.id as string,
    map_code: r.map_code as string,
    map_title: (r.map_title as string) ?? null,
    map_slug: (r.map_slug as string) ?? null,
    game_type: r.game_type as string,
    team_game: r.team_game === 1,
    score_to_win: (r.score_to_win as number) ?? null,
    started_at: r.started_at as string,
    ended_at: r.ended_at as string,
    duration_ms: r.duration_ms as number,
    end_reason: r.end_reason as (typeof END_REASONS)[number],
    red_score: (r.red_score as number) ?? null,
    blue_score: (r.blue_score as number) ?? null,
    winner: (r.winner as string) ?? null,
    winner_name: (r.winner_name as string) ?? null,
    winner_user: linkedUser(r, "w_"),
    player_count: r.player_count as number,
    event_count: r.event_count as number,
    host: (r.host as string) ?? "",
    player: r.player_index === undefined || r.player_index === null ? null : playerFromRow(r),
  };
}

export interface MatchListQuery {
  map?: string;
  game_type?: string;
  /** A player by the name the game gave them (case-insensitive). */
  player?: string;
  /** A hub account, through its linked seats. */
  user?: string;
  /** ended_at of the last match on the previous page. */
  before?: string;
  limit?: number;
}

/** Matches, newest first; with a player or user, that player's line on each. */
export async function listMatches(db: Db, q: MatchListQuery): Promise<{ matches: MatchSummary[]; next: string | null }> {
  const limit = Math.min(Math.max(q.limit ?? PAGE, 1), 50);
  const clauses: string[] = [];
  const binds: unknown[] = [];
  const bind = (v: unknown) => {
    binds.push(v);
    return `?${binds.length}`;
  };
  let join = "";
  let seat = "";
  if (q.user) {
    join = `JOIN match_players p ON p.match_id = m.id AND p.user_id = ${bind(q.user)}`;
    seat = ", p.*";
  } else if (q.player) {
    join = `JOIN match_players p ON p.match_id = m.id AND p.name = ${bind(q.player)} COLLATE NOCASE`;
    seat = ", p.*";
  }
  if (q.map) clauses.push(`m.map_code = ${bind(q.map)}`);
  if (q.game_type) clauses.push(`m.game_type = ${bind(q.game_type)}`);
  if (q.before) clauses.push(`m.ended_at < ${bind(q.before)}`);
  const rows = await db
    .prepare(
      `SELECT ${SUMMARY_COLUMNS}${seat}
       FROM matches m
       ${join}
       ${SUMMARY_JOINS}
       ${clauses.length ? `WHERE ${clauses.join(" AND ")}` : ""}
       ORDER BY m.ended_at DESC LIMIT ${limit + 1}`,
    )
    .bind(...binds)
    .all();
  // `p.*` shares column names with `m.*` only in match_id, which is m.id.
  const matches = rows.results.slice(0, limit).map((r) => summaryFromRow(r as Row));
  const next = rows.results.length > limit ? matches[matches.length - 1].ended_at : null;
  return { matches, next };
}

export async function getMatch(db: Db, id: string): Promise<MatchDetail | null> {
  const [head, players, events] = await db.batch([
    db.prepare(
      `SELECT ${SUMMARY_COLUMNS}
       FROM matches m
       ${SUMMARY_JOINS}
       WHERE m.id = ?1`,
    ).bind(id),
    db.prepare(
      `SELECT p.*, u.id AS u_id, u.display_name AS u_display_name, u.discord_username AS u_username,
              u.discord_id AS u_discord_id, u.discord_avatar AS u_avatar
       FROM match_players p
       LEFT JOIN users u ON u.id = p.user_id AND u.banned_at IS NULL
       WHERE p.match_id = ?1
       ORDER BY p.place, p.player_index`,
    ).bind(id),
    db.prepare(`SELECT * FROM match_events WHERE match_id = ?1 ORDER BY seq`).bind(id),
  ]);
  const row = head.results[0] as Row | undefined;
  if (!row) return null;
  const summary: Omit<MatchSummary, "player"> & { player?: unknown } = summaryFromRow(row);
  delete summary.player;
  const pos = (r: Row, k: string): [number, number, number] | null =>
    r[`${k}_x`] === null || r[`${k}_x`] === undefined
      ? null
      : [r[`${k}_x`] as number, r[`${k}_y`] as number, r[`${k}_z`] as number];
  return {
    ...summary,
    players: (players.results as Row[]).map((r) => ({ ...playerFromRow(r), user: linkedUser(r) })),
    events: (events.results as Row[]).map((r) => ({
      seq: r.seq as number,
      t_ms: r.t_ms as number,
      type: r.type as string,
      cause: r.cause as number,
      effect: r.effect as number,
      value: (r.value as number) ?? null,
      weapon: (r.weapon as string) ?? null,
      modifier: (r.modifier as number) ?? null,
      cause_pos: pos(r, "cause"),
      effect_pos: pos(r, "effect"),
    })),
  };
}

/** A player's career: by the name games gave them, or by hub account. */
export async function playerTotals(db: Db, who: { name: string } | { user: string }): Promise<PlayerTotals> {
  const seat = "name" in who ? `p.name = ?1 COLLATE NOCASE` : `p.user_id = ?1`;
  const key = "name" in who ? who.name : who.user;
  const [totals, weapons] = await db.batch([
    db.prepare(
      `SELECT COUNT(*) AS matches,
              SUM(m.end_reason <> 'abandoned') AS completed,
              SUM(p.outcome = 'win') AS wins,
              SUM(p.outcome = 'loss') AS losses,
              SUM(p.outcome = 'draw') AS draws,
              SUM(p.kills) AS kills, SUM(p.deaths) AS deaths,
              SUM(p.suicides) AS suicides, SUM(p.captures) AS captures,
              MAX(m.ended_at) AS last_played
       FROM match_players p JOIN matches m ON m.id = p.match_id
       WHERE ${seat}`,
    ).bind(key),
    db.prepare(
      `SELECT e.weapon, COUNT(*) AS kills
       FROM match_players p
       JOIN match_events e ON e.match_id = p.match_id AND e.cause = p.player_index
       WHERE ${seat} AND e.type = 'kill' AND e.effect <> p.player_index AND e.weapon IS NOT NULL
       GROUP BY e.weapon ORDER BY kills DESC LIMIT 5`,
    ).bind(key),
  ]);
  const t = (totals.results[0] ?? {}) as Row;
  const n = (v: unknown) => (typeof v === "number" ? v : 0);
  return {
    matches: n(t.matches),
    completed: n(t.completed),
    wins: n(t.wins),
    losses: n(t.losses),
    draws: n(t.draws),
    kills: n(t.kills),
    deaths: n(t.deaths),
    suicides: n(t.suicides),
    captures: n(t.captures),
    last_played: (t.last_played as string) ?? null,
    weapons: (weapons.results as Row[]).map((w) => ({ weapon: w.weapon as string, kills: n(w.kills) })),
  };
}

// ── Writes ────────────────────────────────────────────────────────────

/**
 * The statements that store a report, all in one batch. Seats and events go
 * in through json_each, one statement each however many there are: D1
 * counts every statement against a request's query budget.
 */
function reportStatements(db: Db, id: string, userId: string, body: MatchReport) {
  const { place, outcome, winner } = standings(body);
  const { started, ended } = matchTimes(body.started_at, body.duration_ms);
  const teamScores = body.team_game
    ? body.team_scores ?? { red: sum(body.players, "red"), blue: sum(body.players, "blue") }
    : null;
  const seats = body.players.map((p) => ({
    index: p.index,
    name: p.name,
    team: body.team_game ? p.team ?? null : null,
    score: p.score,
    kills: p.kills,
    deaths: p.deaths,
    suicides: p.suicides,
    captures: p.captures,
    place: place.get(p.index),
    outcome: outcome.get(p.index),
    left: p.left ? 1 : 0,
    host: p.index === body.host_index ? 1 : 0,
  }));
  const events = body.events.map((e) => ({
    t: e.t_ms,
    type: e.type,
    c: e.cause,
    e: e.effect,
    v: e.value ?? null,
    w: e.weapon ?? null,
    m: e.modifier ?? null,
    cp: e.cause_pos ?? null,
    ep: e.effect_pos ?? null,
  }));
  return [
    db.prepare(
      `INSERT INTO matches (id, host_match_id, reporter_user_id, lobby_id, map_code, game_type, team_game,
         score_to_win, started_at, ended_at, duration_ms, end_reason, red_score, blue_score, winner,
         player_count, event_count, client_version)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18)`,
    ).bind(
      id,
      body.host_match_id,
      userId,
      body.lobby_id,
      body.map_code,
      body.game_type,
      body.team_game ? 1 : 0,
      body.score_to_win ?? null,
      started,
      ended,
      body.duration_ms,
      body.end_reason,
      teamScores?.red ?? null,
      teamScores?.blue ?? null,
      winner,
      body.players.length,
      body.events.length,
      body.client_version ?? null,
    ),
    db.prepare(
      `INSERT INTO match_players (match_id, player_index, name, team, score, kills, deaths, suicides,
         captures, place, outcome, left_early, is_host, user_id)
       SELECT ?1, json_extract(s.value, '$.index'), json_extract(s.value, '$.name'),
              json_extract(s.value, '$.team'), json_extract(s.value, '$.score'),
              json_extract(s.value, '$.kills'), json_extract(s.value, '$.deaths'),
              json_extract(s.value, '$.suicides'), json_extract(s.value, '$.captures'),
              json_extract(s.value, '$.place'), json_extract(s.value, '$.outcome'),
              json_extract(s.value, '$.left'), json_extract(s.value, '$.host'),
              CASE json_extract(s.value, '$.host') WHEN 1 THEN ?2 END
       FROM json_each(?3) s`,
    ).bind(id, userId, JSON.stringify(seats)),
    db.prepare(
      `INSERT INTO match_events (match_id, seq, t_ms, type, cause, effect, value, weapon, modifier,
         cause_x, cause_y, cause_z, effect_x, effect_y, effect_z)
       SELECT ?1, CAST(e.key AS INTEGER), json_extract(e.value, '$.t'), json_extract(e.value, '$.type'),
              json_extract(e.value, '$.c'), json_extract(e.value, '$.e'), json_extract(e.value, '$.v'),
              json_extract(e.value, '$.w'), json_extract(e.value, '$.m'),
              json_extract(e.value, '$.cp[0]'), json_extract(e.value, '$.cp[1]'), json_extract(e.value, '$.cp[2]'),
              json_extract(e.value, '$.ep[0]'), json_extract(e.value, '$.ep[1]'), json_extract(e.value, '$.ep[2]')
       FROM json_each(?2) e`,
    ).bind(id, JSON.stringify(events)),
    // Claims that came first. A seat is one account's, and an account has
    // one seat in a match.
    db.prepare(
      `UPDATE match_players
       SET user_id = (SELECT c.user_id FROM match_claims c
                      WHERE c.host_match_id = ?2 AND c.player_index = match_players.player_index)
       WHERE match_id = ?1 AND user_id IS NULL
         AND EXISTS (SELECT 1 FROM match_claims c
                     WHERE c.host_match_id = ?2 AND c.player_index = match_players.player_index
                       AND c.name = match_players.name AND c.user_id <> ?3)`,
    ).bind(id, body.host_match_id, userId),
  ];
}

export function registerMatchRoutes(app: OpenAPIHono<ApiEnv>) {
  // ── Report ──────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/matches",
      tags: ["matches"],
      summary: "Report a public match the caller hosted",
      description:
        "The host's game sends this when a public match ends: the standings and every incident " +
        "the simulation raised, in order, with positions. `host_match_id` is the host's own id " +
        "for the match, which its fireteam's games cite to claim their seats; reporting the same " +
        "one again is a no-op. Needs the `lobbies:write` scope.",
      request: { body: { content: { "application/json": { schema: MatchReportSchema } } } },
      responses: {
        201: {
          description: "Recorded.",
          content: { "application/json": { schema: z.object({ id: z.string(), duplicate: z.boolean() }) } },
        },
        200: {
          description: "Already recorded from this account.",
          content: { "application/json": { schema: z.object({ id: z.string(), duplicate: z.boolean() }) } },
        },
        400: { description: "Invalid report.", content: { "application/json": { schema: ErrorSchema } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Missing scope, or not this listing's host.", content: { "application/json": { schema: ErrorSchema } } },
        409: { description: "That match id is another account's.", content: { "application/json": { schema: ErrorSchema } } },
        429: { description: "Too many reports.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await requireScoped(c, "lobbies:write", "match_report", 60);
      const body = c.req.valid("json");
      const indices = new Set(body.players.map((p) => p.index));
      if (indices.size !== body.players.length) {
        return c.json({ error: "validation", message: "players: an index appears twice" }, 400);
      }
      const existing = await c.env.DB.prepare(
        `SELECT id, reporter_user_id FROM matches WHERE host_match_id = ?1`,
      )
        .bind(body.host_match_id)
        .first<{ id: string; reporter_user_id: string }>();
      if (existing) {
        if (existing.reporter_user_id !== auth.user.id) return c.json({ error: "conflict" }, 409);
        return c.json({ id: existing.id, duplicate: true }, 200);
      }
      // A listing still up must be the caller's. One already swept proves
      // nothing either way.
      const lobby = await c.env.DB.prepare(`SELECT host_user_id FROM lobbies WHERE id = ?1`)
        .bind(body.lobby_id)
        .first<{ host_user_id: string }>();
      if (lobby && lobby.host_user_id !== auth.user.id) {
        return c.json({ error: "forbidden", message: "Not this listing's host." }, 403);
      }
      const id = crypto.randomUUID();
      await c.env.DB.batch(reportStatements(c.env.DB, id, auth.user.id, body));
      return c.json({ id, duplicate: false }, 201);
    },
  );

  // ── Claim a seat ────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/matches/claims",
      tags: ["matches"],
      summary: "Claim the caller's seat in a public match",
      description:
        "A participant's game sends this when the host tells it the match's id, so the seat it " +
        "played in links to the caller's account. The match may not be reported yet: the claim " +
        "waits for it. It links only a seat of the claimed name. Needs the `lobbies:write` scope.",
      request: { body: { content: { "application/json": { schema: MatchClaimSchema } } } },
      responses: {
        200: {
          description: "Claimed; `linked` once the match is reported and the seat matched.",
          content: { "application/json": { schema: z.object({ linked: z.boolean() }) } },
        },
        409: { description: "Someone else claimed that seat.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await requireScoped(c, "lobbies:write", "match_claim", 240);
      const body = c.req.valid("json");
      const db = c.env.DB;
      const [, , held, link] = await db.batch([
        // An account claims one seat: a newer claim replaces its own older
        // one, so a game that first cited a stale seat can correct it.
        db.prepare(
          `DELETE FROM match_claims WHERE host_match_id = ?1 AND user_id = ?2 AND player_index <> ?3`,
        ).bind(body.host_match_id, auth.user.id, body.player_index),
        db.prepare(
          `INSERT OR IGNORE INTO match_claims (host_match_id, player_index, user_id, name)
           VALUES (?1, ?2, ?3, ?4)`,
        ).bind(body.host_match_id, body.player_index, auth.user.id, body.name),
        db.prepare(
          `SELECT user_id FROM match_claims WHERE host_match_id = ?1 AND player_index = ?2`,
        ).bind(body.host_match_id, body.player_index),
        db.prepare(
          `UPDATE match_players SET user_id = ?3
           WHERE match_id = (SELECT id FROM matches WHERE host_match_id = ?1)
             AND player_index = ?2 AND name = ?4 AND user_id IS NULL
             AND EXISTS (SELECT 1 FROM match_claims c
                         WHERE c.host_match_id = ?1 AND c.player_index = ?2 AND c.user_id = ?3)
             AND NOT EXISTS (SELECT 1 FROM match_players o
                             WHERE o.match_id = match_players.match_id AND o.user_id = ?3)`,
        ).bind(body.host_match_id, body.player_index, auth.user.id, body.name),
      ]);
      const owner = (held.results[0] as { user_id?: string } | undefined)?.user_id;
      if (owner !== auth.user.id) return c.json({ error: "seat_claimed" }, 409);
      // Claims for matches never reported (a private game, a host that
      // never came back) go after a month.
      c.executionCtx.waitUntil(
        db.prepare(
          `DELETE FROM match_claims WHERE created_at < datetime('now', '-30 days')
             AND host_match_id NOT IN (SELECT host_match_id FROM matches)`,
        ).run() as unknown as Promise<unknown>,
      );
      return c.json({ linked: (link.meta?.changes ?? 0) > 0 }, 200);
    },
  );

  // ── Browse ──────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/matches",
      tags: ["matches"],
      summary: "Recent public matches: by map, game type, player or account",
      request: {
        query: z.object({
          map: MAP_CODE.optional(),
          game_type: GAME_TYPE.optional(),
          player: PLAYER_NAME.optional().openapi({ description: "The name the game gave a player." }),
          user: z.string().max(64).optional().openapi({ description: "A hub account id." }),
          before: z.string().max(32).optional().openapi({ description: "`next` from the previous page." }),
          limit: z.coerce.number().int().min(1).max(50).optional(),
        }),
      },
      responses: {
        200: {
          description: "Newest first.",
          content: {
            "application/json": {
              schema: z.object({ matches: z.array(MatchSummarySchema), next: z.string().nullable() }),
            },
          },
        },
      },
    }),
    async (c) => c.json(await listMatches(c.env.DB, c.req.valid("query")), 200),
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/matches/{id}",
      tags: ["matches"],
      summary: "One match: standings and every event, in order",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: { description: "The match.", content: { "application/json": { schema: MatchDetailSchema } } },
        404: { description: "No such match.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const match = await getMatch(c.env.DB, c.req.valid("param").id);
      if (!match) return c.json({ error: "not_found" }, 404);
      return c.json(match, 200);
    },
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/players/{name}/stats",
      tags: ["matches"],
      summary: "A player's totals across public matches, by in-game name",
      request: { params: z.object({ name: PLAYER_NAME }) },
      responses: {
        200: { description: "Totals.", content: { "application/json": { schema: PlayerTotalsSchema } } },
      },
    }),
    async (c) => c.json(await playerTotals(c.env.DB, { name: c.req.valid("param").name }), 200),
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/users/{id}/match-stats",
      tags: ["matches"],
      summary: "An account's totals across the public matches it is linked to",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: { description: "Totals.", content: { "application/json": { schema: PlayerTotalsSchema } } },
      },
    }),
    async (c) => c.json(await playerTotals(c.env.DB, { user: c.req.valid("param").id }), 200),
  );
}
