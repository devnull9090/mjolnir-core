/**
 * Players in multiplayer: who they are in game, reports against them, and
 * matchmaking bans (docs/player_identity.md, migrations/0018).
 *
 * Identity. Every multiplayer player's game holds its launcher's key, so it
 * can prove its hub account to the host it joined, and the host's game shows
 * the hub name and avatar instead of the Steam or Xbox name. The proof is a
 * ticket: the player's game asks for one naming the host's account and its
 * own in-game name, sends it to the host over the game's own messages, and
 * the host's game trades it here for the account. Only that host can trade
 * it, and the host checks the in-game name against the controller that sent
 * it, so neither a stolen ticket nor a ticket relayed to another host names
 * anyone it should not.
 *
 * Reports. A player reports another from the post-game screen with a reason
 * and a note. The subject is a hub account the host's game resolved, never
 * a bare in-game name. Moderators work the queue at /moderation; the public
 * sees only how many reports an account has that were not dismissed.
 *
 * Bans. A matchmaking ban stops an account listing a game or joining one
 * from the browser, and a public game's host removes a banned player its
 * tickets name. It does not touch the rest of the hub (that is
 * `users.banned_at`).
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { Context } from "hono";

import type { ApiEnv } from "./bindings";
import { requireScoped, sha256Hex } from "./auth";
import { requireModerator } from "./account";
import { audit } from "./moderation";
import { ErrorSchema, avatarUrl } from "./schemas";

type Ctx = Context<ApiEnv>;
type Db = ApiEnv["Bindings"]["DB"];

/** Long enough to join and be seated; a game asks again for every host. */
const TICKET_SECONDS = 15 * 60;
const MAX_RESOLVE = 16;
const PLATFORM_NAME = z.string().min(1).max(64);
const HOST_MATCH_ID = z.string().regex(/^[0-9a-f]{16,64}$/);

export const PLAYER_REPORT_REASONS = [
  "cheating",
  "betraying",
  "harassment",
  "griefing",
  "quitting",
  "name",
  "other",
] as const;

// ── Shared reads ──────────────────────────────────────────────────────

export interface MatchmakingBan {
  reason: string;
  created_at: string;
  /** Null for a permanent ban. */
  expires_at: string | null;
}

/** SQL for "this ban is in force", on a `matchmaking_bans` alias. */
const BAN_ACTIVE = (b: string) =>
  `${b}.lifted_at IS NULL AND (${b}.expires_at IS NULL OR ${b}.expires_at > datetime('now'))`;

/** A user-id column whose account is banned from matchmaking. */
export const banActiveFor = (userColumn: string) =>
  `EXISTS (SELECT 1 FROM matchmaking_bans b WHERE b.user_id = ${userColumn} AND ${BAN_ACTIVE("b")})`;

/** The ban an account is under now, or null. */
export async function activeBan(db: Db, userId: string): Promise<MatchmakingBan | null> {
  return (
    (await db
      .prepare(
        `SELECT reason, created_at, expires_at FROM matchmaking_bans b
         WHERE b.user_id = ?1 AND ${BAN_ACTIVE("b")}
         ORDER BY b.expires_at IS NULL DESC, b.expires_at DESC LIMIT 1`,
      )
      .bind(userId)
      .first<MatchmakingBan>()) ?? null
  );
}

/** What a banned caller is told; the reason is theirs to read. */
export function banMessage(ban: MatchmakingBan): string {
  const until = ban.expires_at ? `until ${ban.expires_at.slice(0, 16).replace("T", " ")} UTC` : "permanently";
  return `Banned from matchmaking ${until}: ${ban.reason}`;
}

/** The public count: reports a moderator has not dismissed. */
export async function playerReportCount(db: Db, userId: string): Promise<number> {
  const row = await db
    .prepare(`SELECT COUNT(*) AS n FROM player_reports WHERE subject_id = ?1 AND status <> 'dismissed'`)
    .bind(userId)
    .first<{ n: number }>();
  return row?.n ?? 0;
}

const displayName = (r: { display_name?: unknown; discord_username?: unknown }) =>
  ((r.display_name as string | null) ?? (r.discord_username as string)) as string;

/**
 * Where a game fetches an account's avatar: through the hub, because the
 * game's hub call reaches nothing else (and must not carry its key to
 * another host).
 */
const gameAvatarPath = (id: string) => `/users/${id}/avatar`;

// ── Schemas ───────────────────────────────────────────────────────────

const PlayerSchema = z
  .object({
    id: z.string(),
    name: z.string().openapi({ description: "Display name, or the Discord username." }),
    username: z.string(),
    avatar_url: z.string().nullable().openapi({ description: "Discord CDN avatar, when they have one." }),
    avatar_path: z.string().openapi({
      description: "The avatar through the hub, below /api/v1: always a PNG, Discord's default when they have none.",
    }),
  })
  .openapi("Player");

const MatchmakingBanSchema = z
  .object({ reason: z.string(), created_at: z.string(), expires_at: z.string().nullable() })
  .openapi("MatchmakingBan");

function playerFromRow(r: Record<string, unknown>, prefix = "") {
  const id = r[`${prefix}id`] as string;
  return {
    id,
    name: displayName({
      display_name: r[`${prefix}display_name`],
      discord_username: r[`${prefix}discord_username`],
    }),
    username: r[`${prefix}discord_username`] as string,
    avatar_url: avatarUrl(r[`${prefix}discord_id`] as string, r[`${prefix}discord_avatar`] as string | null),
    avatar_path: gameAvatarPath(id),
  };
}

const PlayerReportSchema = z
  .object({
    id: z.string(),
    reporter: PlayerSchema,
    reason: z.enum(PLAYER_REPORT_REASONS),
    detail: z.string().nullable(),
    subject_name: z.string().nullable().openapi({ description: "The name the reporter saw in game." }),
    host_match_id: z.string().nullable(),
    match_id: z.string().nullable().openapi({
      description: "The hub's match, once the host reported it; link /matches/{id}.",
    }),
    reporter_in_match: z.boolean().nullable().openapi({
      description: "Whether the reporter's account is linked to a seat of that match; null without one.",
    }),
    subject_in_match: z.boolean().nullable(),
    status: z.enum(["open", "upheld", "dismissed"]),
    decided_by: z.string().nullable(),
    decided_at: z.string().nullable(),
    decision_note: z.string().nullable(),
    created_at: z.string(),
  })
  .openapi("PlayerReport");

const ReportedPlayerSchema = z
  .object({
    player: PlayerSchema,
    open_reports: z.number().int(),
    counted_reports: z.number().int().openapi({ description: "The public count: every report not dismissed." }),
    ban: MatchmakingBanSchema.nullable(),
    reports: z.array(PlayerReportSchema),
  })
  .openapi("ReportedPlayer");

const BannedPlayerSchema = z
  .object({
    id: z.string(),
    player: PlayerSchema,
    reason: z.string(),
    banned_by: z.string().nullable(),
    created_at: z.string(),
    expires_at: z.string().nullable(),
  })
  .openapi("BannedPlayer");

// ── Routes ────────────────────────────────────────────────────────────

const Ok = { content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } };
const Err = (description: string) => ({ description, content: { "application/json": { schema: ErrorSchema } } });

function randomToken(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Discord's own default avatar for an account with none (new usernames). */
function defaultAvatar(discordId: string): string {
  let index = 0;
  try {
    index = Number((BigInt(discordId) >> BigInt(22)) % BigInt(6));
  } catch {
    // Not a snowflake (a system identity); the first default will do.
  }
  return `https://cdn.discordapp.com/embed/avatars/${index}.png`;
}

export function registerPlayerRoutes(app: OpenAPIHono<ApiEnv>) {
  // ── Identity tickets ────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/identity/tickets",
      tags: ["players"],
      summary: "A ticket proving the caller's account to one host",
      description:
        "The caller's game hands the ticket to the host of the game it joined, which trades it " +
        "with POST /identity/tickets/resolve. `audience` is the host's account (the host's game " +
        "says which); `platform_name` is the caller's own in-game name, which the host checks " +
        "against the player that sent it. Without an audience no ticket is made, and the call " +
        "only answers who the caller is and whether it may play matchmaking. Needs `lobbies:write`.",
      request: {
        body: {
          content: {
            "application/json": {
              schema: z
                .object({ platform_name: PLATFORM_NAME, audience: z.string().uuid().optional() })
                .openapi("IdentityTicketRequest"),
            },
          },
        },
      },
      responses: {
        201: {
          description: "Issued.",
          content: {
            "application/json": {
              schema: z
                .object({
                  ticket: z.string().nullable(),
                  expires_at: z.string().nullable(),
                  player: PlayerSchema,
                  matchmaking_ban: MatchmakingBanSchema.nullable(),
                })
                .openapi("IdentityTicket"),
            },
          },
        },
        401: Err("Not signed in."),
        403: Err("Missing scope."),
        404: Err("No such host account."),
        429: Err("Slow down."),
      },
    }),
    async (c) => {
      const auth = await requireScoped(c, "lobbies:write", "identity_ticket", 240);
      const { platform_name, audience } = c.req.valid("json");
      const u = auth.user;
      const player = playerFromRow(u as unknown as Record<string, unknown>);
      const ban = await activeBan(c.env.DB, u.id);
      if (!audience) {
        return c.json({ ticket: null, expires_at: null, player, matchmaking_ban: ban }, 201);
      }
      const host = await c.env.DB.prepare(`SELECT id FROM users WHERE id = ?1 AND banned_at IS NULL`)
        .bind(audience)
        .first<{ id: string }>();
      if (!host) return c.json({ error: "not_found", message: "No such host account." }, 404);
      const ticket = randomToken();
      const expires = new Date(Date.now() + TICKET_SECONDS * 1000).toISOString();
      await c.env.DB.batch([
        c.env.DB.prepare(`DELETE FROM identity_tickets WHERE expires_at < ?1`).bind(new Date().toISOString()),
        c.env.DB.prepare(
          `INSERT INTO identity_tickets (token_hash, user_id, audience_user_id, platform_name, expires_at)
           VALUES (?1, ?2, ?3, ?4, ?5)`,
        ).bind(await sha256Hex(ticket), u.id, audience, platform_name, expires),
      ]);
      return c.json({ ticket, expires_at: expires, player, matchmaking_ban: ban }, 201);
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/identity/tickets/resolve",
      tags: ["players"],
      summary: "Trade players' tickets for their accounts (the host they name)",
      description:
        "Answers each ticket that names the caller as its audience and has not expired; others " +
        "are left out. The host's game must check `platform_name` against the player that sent " +
        "the ticket. `matchmaking_ban` is set for a banned player, whom a public game removes. " +
        "Needs `lobbies:write`.",
      request: {
        body: {
          content: {
            "application/json": {
              schema: z
                .object({ tickets: z.array(z.string().regex(/^[0-9a-f]{48}$/)).min(1).max(MAX_RESOLVE) })
                .openapi("IdentityResolveRequest"),
            },
          },
        },
      },
      responses: {
        200: {
          description: "The tickets that were good.",
          content: {
            "application/json": {
              schema: z
                .object({
                  players: z.array(
                    z.object({
                      ticket: z.string(),
                      platform_name: z.string(),
                      player: PlayerSchema,
                      reports: z.number().int().openapi({ description: "The public report count." }),
                      matchmaking_ban: MatchmakingBanSchema.nullable(),
                    }),
                  ),
                })
                .openapi("IdentityResolved"),
            },
          },
        },
        401: Err("Not signed in."),
        403: Err("Missing scope."),
        429: Err("Slow down."),
      },
    }),
    async (c) => {
      const auth = await requireScoped(c, "lobbies:write", "identity_resolve", 600);
      const { tickets } = c.req.valid("json");
      const hashes = await Promise.all(tickets.map((t) => sha256Hex(t)));
      const marks = hashes.map((_, i) => `?${i + 3}`).join(", ");
      const rows = await c.env.DB.prepare(
        `SELECT t.token_hash, t.platform_name, u.id, u.discord_id, u.discord_username,
                u.discord_avatar, u.display_name,
                (SELECT COUNT(*) FROM player_reports r
                  WHERE r.subject_id = u.id AND r.status <> 'dismissed') AS reports,
                (SELECT b.reason || char(31) || b.created_at || char(31) || COALESCE(b.expires_at, '')
                   FROM matchmaking_bans b WHERE b.user_id = u.id AND ${BAN_ACTIVE("b")}
                   ORDER BY b.expires_at IS NULL DESC, b.expires_at DESC LIMIT 1) AS ban
         FROM identity_tickets t JOIN users u ON u.id = t.user_id
         WHERE t.audience_user_id = ?1 AND t.expires_at > ?2 AND u.banned_at IS NULL
           AND t.token_hash IN (${marks})`,
      )
        .bind(auth.user.id, new Date().toISOString(), ...hashes)
        .all();
      const byHash = new Map(rows.results.map((r) => [r.token_hash as string, r]));
      const players = tickets.flatMap((ticket, i) => {
        const r = byHash.get(hashes[i]);
        if (!r) return [];
        const ban = r.ban ? (r.ban as string).split("\u001f") : null;
        return [
          {
            ticket,
            platform_name: r.platform_name as string,
            player: playerFromRow(r),
            reports: r.reports as number,
            matchmaking_ban: ban ? { reason: ban[0], created_at: ban[1], expires_at: ban[2] || null } : null,
          },
        ];
      });
      return c.json({ players }, 200);
    },
  );

  // ── Avatars for the game ────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/users/{id}/avatar",
      tags: ["players"],
      summary: "An account's avatar as a 64-pixel PNG",
      description:
        "The Discord avatar through the hub, or Discord's default one, for the game, whose hub " +
        "calls reach nothing but the hub.",
      request: { params: z.object({ id: z.string().uuid() }) },
      responses: {
        200: { description: "PNG bytes." },
        404: Err("No such account."),
        502: Err("Discord did not answer."),
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const u = await c.env.DB.prepare(
        `SELECT discord_id, discord_avatar FROM users WHERE id = ?1 AND banned_at IS NULL`,
      )
        .bind(id)
        .first<{ discord_id: string; discord_avatar: string | null }>();
      if (!u) return c.json({ error: "not_found" }, 404);
      const own = avatarUrl(u.discord_id, u.discord_avatar);
      const url = own ? `${own}?size=64` : defaultAvatar(u.discord_id);
      const res = await fetch(url, { cf: { cacheTtl: 86400, cacheEverything: true } } as RequestInit);
      if (!res.ok || !res.body) return c.json({ error: "upstream", message: `Discord answered ${res.status}.` }, 502);
      return new Response(res.body, {
        status: 200,
        headers: {
          "Content-Type": "image/png",
          "X-Content-Type-Options": "nosniff",
          // An avatar changes at the next sign-in; an hour is fresh enough.
          "Cache-Control": "public, max-age=3600",
        },
      }) as never;
    },
  );

  // ── Reporting a player ──────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/players/reports",
      tags: ["players"],
      summary: "Report a player",
      description:
        "From the post-game screen: the account the host's game resolved for that seat, a reason, " +
        "and what happened. One report per reporter, player and match. Needs `lobbies:write`.",
      request: {
        body: {
          content: {
            "application/json": {
              schema: z
                .object({
                  subject_id: z.string().uuid(),
                  reason: z.enum(PLAYER_REPORT_REASONS),
                  detail: z.string().trim().max(1000).optional(),
                  subject_name: PLATFORM_NAME.optional(),
                  host_match_id: HOST_MATCH_ID.optional(),
                })
                .openapi("PlayerReportCreate"),
            },
          },
        },
      },
      responses: {
        201: { description: "Filed.", content: { "application/json": { schema: z.object({ id: z.string() }) } } },
        400: Err("Reporting yourself."),
        401: Err("Not signed in."),
        403: Err("Missing scope."),
        404: Err("No such player."),
        409: Err("Already reported for this match."),
        429: Err("Slow down."),
      },
    }),
    async (c) => {
      const auth = await requireScoped(c, "lobbies:write", "player_report", 30);
      const body = c.req.valid("json");
      if (body.subject_id === auth.user.id) {
        return c.json({ error: "self", message: "You cannot report yourself." }, 400);
      }
      const subject = await c.env.DB.prepare(`SELECT id FROM users WHERE id = ?1`)
        .bind(body.subject_id)
        .first<{ id: string }>();
      if (!subject) return c.json({ error: "not_found" }, 404);
      const id = crypto.randomUUID();
      try {
        await c.env.DB.prepare(
          `INSERT INTO player_reports (id, reporter_id, subject_id, reason, detail, subject_name, host_match_id)
           VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`,
        )
          .bind(
            id,
            auth.user.id,
            body.subject_id,
            body.reason,
            body.detail || null,
            body.subject_name ?? null,
            body.host_match_id ?? null,
          )
          .run();
      } catch (e) {
        if (String(e).includes("UNIQUE")) {
          return c.json({ error: "duplicate", message: "You already reported this player for this match." }, 409);
        }
        throw e;
      }
      return c.json({ id }, 201);
    },
  );

  // ── The moderation queue ────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/moderation/player-reports",
      tags: ["moderation"],
      summary: "Reported players and their reports (moderators)",
      description:
        "Grouped by the player reported, most open reports first. `status=open` lists players " +
        "with an open report, each with every report against them so the history is in view; " +
        "`upheld` and `dismissed` list decided ones.",
      request: {
        query: z.object({ status: z.enum(["open", "upheld", "dismissed"]).default("open") }),
      },
      responses: {
        200: {
          description: "Reported players.",
          content: { "application/json": { schema: z.object({ players: z.array(ReportedPlayerSchema) }) } },
        },
        401: Err("Not signed in."),
        403: Err("Moderators only."),
      },
    }),
    async (c) => {
      await requireModerator(c);
      const { status } = c.req.valid("query");
      const subjects = await c.env.DB.prepare(
        `SELECT subject_id, MIN(created_at) AS first FROM player_reports WHERE status = ?1
         GROUP BY subject_id ORDER BY COUNT(*) DESC, first LIMIT 100`,
      )
        .bind(status)
        .all<{ subject_id: string }>();
      const ids = subjects.results.map((s) => s.subject_id);
      if (!ids.length) return c.json({ players: [] }, 200);
      const marks = ids.map((_, i) => `?${i + 1}`).join(", ");
      const rows = await c.env.DB.prepare(
        `SELECT r.*,
                s.id AS s_id, s.discord_id AS s_discord_id, s.discord_username AS s_discord_username,
                s.discord_avatar AS s_discord_avatar, s.display_name AS s_display_name,
                p.id AS p_id, p.discord_id AS p_discord_id, p.discord_username AS p_discord_username,
                p.discord_avatar AS p_discord_avatar, p.display_name AS p_display_name,
                COALESCE(d.display_name, d.discord_username) AS decider,
                m.id AS match_id,
                (SELECT COUNT(*) FROM match_players mp
                  WHERE mp.match_id = m.id AND mp.user_id = r.reporter_id) AS reporter_seats,
                (SELECT COUNT(*) FROM match_players mp
                  WHERE mp.match_id = m.id AND mp.user_id = r.subject_id) AS subject_seats
         FROM player_reports r
         JOIN users s ON s.id = r.subject_id
         JOIN users p ON p.id = r.reporter_id
         LEFT JOIN users d ON d.id = r.decided_by
         LEFT JOIN matches m ON m.host_match_id = r.host_match_id
         WHERE r.subject_id IN (${marks})
         ORDER BY r.created_at DESC`,
      )
        .bind(...ids)
        .all();
      const bans = await c.env.DB.prepare(
        `SELECT b.user_id, b.reason, b.created_at, b.expires_at FROM matchmaking_bans b
         WHERE b.user_id IN (${marks}) AND ${BAN_ACTIVE("b")}`,
      )
        .bind(...ids)
        .all<MatchmakingBan & { user_id: string }>();
      const banOf = new Map(bans.results.map((b) => [b.user_id, b]));
      const players = ids.map((id) => {
        const reports = rows.results.filter((r) => r.subject_id === id);
        const ban = banOf.get(id);
        return {
          player: playerFromRow(reports[0], "s_"),
          open_reports: reports.filter((r) => r.status === "open").length,
          counted_reports: reports.filter((r) => r.status !== "dismissed").length,
          ban: ban ? { reason: ban.reason, created_at: ban.created_at, expires_at: ban.expires_at } : null,
          reports: reports.map((r) => ({
            id: r.id as string,
            reporter: playerFromRow(r, "p_"),
            reason: r.reason as (typeof PLAYER_REPORT_REASONS)[number],
            detail: (r.detail as string) ?? null,
            subject_name: (r.subject_name as string) ?? null,
            host_match_id: (r.host_match_id as string) ?? null,
            match_id: (r.match_id as string) ?? null,
            reporter_in_match: r.match_id ? (r.reporter_seats as number) > 0 : null,
            subject_in_match: r.match_id ? (r.subject_seats as number) > 0 : null,
            status: r.status as "open" | "upheld" | "dismissed",
            decided_by: (r.decider as string) ?? null,
            decided_at: (r.decided_at as string) ?? null,
            decision_note: (r.decision_note as string) ?? null,
            created_at: r.created_at as string,
          })),
        };
      });
      return c.json({ players }, 200);
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/moderation/player-reports/{id}",
      tags: ["moderation"],
      summary: "Uphold or dismiss a player report (moderators)",
      description:
        "`uphold` agrees with it; `dismiss` finds it unfounded and takes it out of the public " +
        "count. Banning is its own call (POST /moderation/matchmaking-bans).",
      request: {
        params: z.object({ id: z.string() }),
        body: {
          content: {
            "application/json": {
              schema: z
                .object({ action: z.enum(["uphold", "dismiss"]), note: z.string().max(500).optional() })
                .openapi("PlayerReportDecision"),
            },
          },
        },
      },
      responses: {
        200: { description: "Decided.", ...Ok },
        401: Err("Not signed in."),
        403: Err("Moderators only."),
        404: Err("No such open report."),
      },
    }),
    async (c) => {
      const auth = await requireModerator(c);
      const { id } = c.req.valid("param");
      const { action, note } = c.req.valid("json");
      const res = await c.env.DB.prepare(
        `UPDATE player_reports SET status = ?2, decided_by = ?3, decided_at = datetime('now'),
           decision_note = ?4
         WHERE id = ?1 AND status = 'open'`,
      )
        .bind(id, action === "uphold" ? "upheld" : "dismissed", auth.user.id, note ?? null)
        .run();
      if (!res.meta.changes) return c.json({ error: "not_found" }, 404);
      await audit(c, auth.user.id, `player_report_${action}`, "player_report", id, note);
      return c.json({ ok: true }, 200);
    },
  );

  // ── Matchmaking bans ────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/moderation/matchmaking-bans",
      tags: ["moderation"],
      summary: "Bans in force (moderators)",
      responses: {
        200: {
          description: "Newest first.",
          content: { "application/json": { schema: z.object({ bans: z.array(BannedPlayerSchema) }) } },
        },
        401: Err("Not signed in."),
        403: Err("Moderators only."),
      },
    }),
    async (c) => {
      await requireModerator(c);
      const rows = await c.env.DB.prepare(
        `SELECT b.id AS ban_id, b.reason, b.created_at, b.expires_at,
                COALESCE(m.display_name, m.discord_username) AS banned_by,
                u.id, u.discord_id, u.discord_username, u.discord_avatar, u.display_name
         FROM matchmaking_bans b
         JOIN users u ON u.id = b.user_id
         LEFT JOIN users m ON m.id = b.banned_by
         WHERE ${BAN_ACTIVE("b")} ORDER BY b.created_at DESC LIMIT 200`,
      ).all();
      return c.json(
        {
          bans: rows.results.map((r) => ({
            id: r.ban_id as string,
            player: playerFromRow(r),
            reason: r.reason as string,
            banned_by: (r.banned_by as string) ?? null,
            created_at: r.created_at as string,
            expires_at: (r.expires_at as string) ?? null,
          })),
        },
        200,
      );
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/moderation/matchmaking-bans",
      tags: ["moderation"],
      summary: "Ban a player from matchmaking (moderators)",
      description:
        "For `days` days, or for good without. A ban in force is replaced. The player's open " +
        "reports are upheld with it, and their listed game is taken down.",
      request: {
        body: {
          content: {
            "application/json": {
              schema: z
                .object({
                  user_id: z.string().uuid(),
                  reason: z.string().trim().min(1).max(500),
                  days: z.number().int().min(1).max(3650).optional(),
                })
                .openapi("MatchmakingBanCreate"),
            },
          },
        },
      },
      responses: {
        201: { description: "Banned.", content: { "application/json": { schema: z.object({ id: z.string() }) } } },
        400: Err("Not an account to ban."),
        401: Err("Not signed in."),
        403: Err("Moderators only."),
        404: Err("No such account."),
      },
    }),
    async (c) => {
      const auth = await requireModerator(c);
      const { user_id, reason, days } = c.req.valid("json");
      if (user_id === auth.user.id) return c.json({ error: "self", message: "Not yourself." }, 400);
      const target = await c.env.DB.prepare(`SELECT role FROM users WHERE id = ?1`)
        .bind(user_id)
        .first<{ role: string }>();
      if (!target) return c.json({ error: "not_found" }, 404);
      if (target.role !== "user" && auth.user.role !== "admin") {
        return c.json({ error: "forbidden", message: "Only an admin bans staff." }, 403);
      }
      const id = crypto.randomUUID();
      const expires = days ? new Date(Date.now() + days * 86400 * 1000).toISOString().slice(0, 19).replace("T", " ") : null;
      await c.env.DB.batch([
        c.env.DB.prepare(
          `UPDATE matchmaking_bans SET lifted_at = datetime('now'), lifted_by = ?2
           WHERE user_id = ?1 AND ${BAN_ACTIVE("matchmaking_bans")}`,
        ).bind(user_id, auth.user.id),
        c.env.DB.prepare(
          `INSERT INTO matchmaking_bans (id, user_id, reason, banned_by, expires_at) VALUES (?1, ?2, ?3, ?4, ?5)`,
        ).bind(id, user_id, reason, auth.user.id, expires),
        c.env.DB.prepare(
          `UPDATE player_reports SET status = 'upheld', decided_by = ?2, decided_at = datetime('now'),
             decision_note = 'Banned: ' || ?3
           WHERE subject_id = ?1 AND status = 'open'`,
        ).bind(user_id, auth.user.id, reason),
        c.env.DB.prepare(`DELETE FROM lobbies WHERE host_user_id = ?1`).bind(user_id),
      ]);
      await audit(c, auth.user.id, "matchmaking_ban", "user", user_id, `${days ? `${days} days` : "permanent"}: ${reason}`);
      return c.json({ id }, 201);
    },
  );

  app.openapi(
    createRoute({
      method: "delete",
      path: "/moderation/matchmaking-bans/{user_id}",
      tags: ["moderation"],
      summary: "Lift a player's matchmaking ban (moderators)",
      request: { params: z.object({ user_id: z.string() }) },
      responses: {
        200: { description: "Lifted.", ...Ok },
        401: Err("Not signed in."),
        403: Err("Moderators only."),
        404: Err("No ban in force."),
      },
    }),
    async (c) => {
      const auth = await requireModerator(c);
      const { user_id } = c.req.valid("param");
      const res = await c.env.DB.prepare(
        `UPDATE matchmaking_bans SET lifted_at = datetime('now'), lifted_by = ?2
         WHERE user_id = ?1 AND ${BAN_ACTIVE("matchmaking_bans")}`,
      )
        .bind(user_id, auth.user.id)
        .run();
      if (!res.meta.changes) return c.json({ error: "not_found" }, 404);
      await audit(c, auth.user.id, "matchmaking_unban", "user", user_id);
      return c.json({ ok: true }, 200);
    },
  );
}

/** For the routes that let a player into matchmaking: the 403 a banned caller gets, or null. */
export async function refuseBanned(c: Ctx, userId: string) {
  const ban = await activeBan(c.env.DB, userId);
  return ban ? c.json({ error: "matchmaking_banned", message: banMessage(ban) }, 403) : null;
}
