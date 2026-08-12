/**
 * Device pairing for desktop clients.
 *
 * The launcher cannot hold a browser session and must never see a Discord
 * password, so it pairs the way a TV app does (RFC 8628 in shape, not in
 * wire format): it asks for a handshake, shows the user a short code, the
 * user approves that code on mjolnircore.com while signed in, and the next
 * poll hands the launcher an ordinary scoped API key.
 *
 * A client asks for the scopes it needs and gets no more. The launcher asks
 * for read, rate and comment; the tag editor, which publishes, also asks for
 * `mods:write`. Granting that to a desktop app is a real widening — a stolen
 * key can then publish — but the flow it replaces was pasting a hand-minted
 * key into a text box, and a key that arrives this way is narrower, expires,
 * and is named on the account page. The trade is worth making explicitly,
 * not avoiding by leaving the harder path in place.
 *
 * Approval is a confirmed, user-initiated action on a page that names the
 * client, lists what it is asking for, and warns against approving codes
 * someone else read out. That warning is the only defence against the
 * phishing case this flow has, so it is part of the design, not decoration —
 * and it matters more now that a code can carry publishing rights.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { Context } from "hono";

import type { ApiEnv } from "./bindings";
import { authenticate, rateLimit, sha256Hex } from "./auth";
import { KNOWN_SCOPES, mintApiKey } from "./account";
import { ErrorSchema, UserSchema, avatarUrl } from "./schemas";

type Ctx = Context<ApiEnv>;

/**
 * What a paired client gets when it does not ask for anything specific.
 * Launchers built before scopes were requestable send no list, and this is
 * what they were minted before, so they keep working untouched.
 */
export const DEVICE_SCOPES = ["mods:read", "ratings:write", "comments:write"] as const;

/**
 * Scopes a device may ask for. Every known scope is pairable — the check
 * that matters is the user reading what they are approving, not a list here
 * second-guessing which client deserves what.
 */
const PAIRABLE_SCOPES = KNOWN_SCOPES;

const CODE_TTL_SECONDS = 600;
const POLL_INTERVAL_SECONDS = 3;
/**
 * Keys minted by pairing expire; a client re-pairs rather than holding
 * forever. A key that can publish is worth more stolen than one that can
 * only comment, so it gets less time to be worth stealing.
 */
const KEY_TTL_DAYS = 180;
const PUBLISHING_KEY_TTL_DAYS = 90;

function ttlDaysFor(scopes: readonly string[]): number {
  return scopes.includes("mods:write") ? PUBLISHING_KEY_TTL_DAYS : KEY_TTL_DAYS;
}

type Scope = (typeof PAIRABLE_SCOPES)[number];

/**
 * Stored space-joined, like `api_keys.scopes`. Unknown entries are dropped:
 * a scope this build cannot name is one the approval page cannot describe,
 * and granting something the user was not shown is the one outcome this
 * flow exists to prevent.
 */
function parseScopes(stored: string): Scope[] {
  return stored.split(" ").filter((s): s is Scope => PAIRABLE_SCOPES.includes(s as Scope));
}

/**
 * Digits and letters that survive being read off a screen and typed back:
 * no 0/O, no 1/I/L, no 5/S, no 2/Z.
 */
const CODE_ALPHABET = "ABCDEFGHJKMNPQRTUVWXY34679";

function randomUserCode(): string {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  const chars = Array.from(bytes, (b) => CODE_ALPHABET[b % CODE_ALPHABET.length]);
  return `${chars.slice(0, 4).join("")}-${chars.slice(4).join("")}`;
}

function randomDeviceCode(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * Where to send the user to approve. The configured site URL wins, so a
 * spoofed Host header cannot aim a launcher at another page — except on
 * localhost, where the request origin is what a developer running both
 * halves locally actually wants.
 */
function siteUrl(c: Ctx): string {
  const origin = new URL(c.req.url).origin;
  if (/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) return origin;
  return process.env.SITE_URL ?? c.env.SITE_URL ?? origin;
}

/**
 * `expires_at` is stored as an ISO-8601 string, which does **not** order
 * against SQLite's `datetime('now')` ("2026-08-02 01:00:00"): the `T` at
 * index 10 sorts above a space, so every same-day ISO timestamp compares as
 * later than every same-day SQLite one. Comparisons therefore either happen
 * in JavaScript or bind an ISO bound computed here — never `datetime('now')`.
 */
function isoNow(offsetMs = 0): string {
  return new Date(Date.now() + offsetMs).toISOString();
}

function expired(expiresAt: string): boolean {
  return expiresAt <= isoNow();
}

const DeviceStartSchema = z
  .object({
    device_code: z.string().openapi({ description: "Secret for polling. Never display it." }),
    user_code: z.string().openapi({ example: "H7QK-M3XB", description: "Show this to the user." }),
    verification_url: z.string().openapi({ example: "https://mjolnircore.com/link" }),
    interval: z.number().int().openapi({ description: "Seconds to wait between polls." }),
    expires_in: z.number().int(),
    scopes: z.array(z.enum(PAIRABLE_SCOPES)).openapi({
      description: "What approval will grant — echoed back so a client can show it too.",
    }),
  })
  .openapi("DeviceStart");

const DevicePollSchema = z
  .object({
    status: z.enum(["pending", "approved", "denied", "expired"]),
    key: z.string().optional().openapi({
      description:
        "The minted API key, returned exactly once — on the first poll after " +
        "approval. Store it; it is not retrievable again.",
    }),
    user: UserSchema.optional(),
    scopes: z.array(z.enum(PAIRABLE_SCOPES)).optional().openapi({
      description:
        "What the key carries. Sent with the key so a client can check it " +
        "got what it asked for instead of failing later at the write.",
    }),
  })
  .openapi("DevicePoll");

function userPayload(row: {
  id: string;
  discord_id: string;
  discord_username: string;
  discord_avatar: string | null;
  display_name: string | null;
  role: string;
  created_at: string;
}) {
  return {
    id: row.id,
    username: row.discord_username,
    display_name: row.display_name,
    avatar_url: avatarUrl(row.discord_id, row.discord_avatar),
    role: row.role as "user" | "moderator" | "admin",
    created_at: row.created_at,
  };
}

export function registerDeviceRoutes(app: OpenAPIHono<ApiEnv>) {
  // ── Start ───────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/auth/device/start",
      tags: ["auth"],
      summary: "Begin pairing a desktop client",
      description:
        "Returns a short `user_code` to show the user and a secret " +
        "`device_code` to poll with. Send the user to `verification_url` to " +
        "approve. Codes live for 10 minutes.",
      request: {
        body: {
          content: {
            "application/json": {
              schema: z.object({
                client_name: z.string().min(1).max(60).default("MJOLNIR Launcher").openapi({
                  description: "Shown on the approval page so the user knows what they are approving.",
                }),
                scopes: z
                  .array(z.enum(PAIRABLE_SCOPES))
                  .min(1)
                  .optional()
                  .openapi({
                    description:
                      "What to ask for. Omit for read, rate and comment — what " +
                      "pairing granted before scopes were requestable. Ask for " +
                      "the narrowest set that works: the user sees this list.",
                    example: ["mods:read", "mods:write"],
                  }),
              }),
            },
          },
        },
      },
      responses: {
        201: {
          description: "Pairing started.",
          content: { "application/json": { schema: DeviceStartSchema } },
        },
        429: { description: "Too many handshakes.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const ip = c.req.header("cf-connecting-ip") ?? "local";
      if (!(await rateLimit(c, `ip:${ip}`, "device_start", 20))) {
        return c.json({ error: "rate_limited" }, 429);
      }

      const deviceCode = randomDeviceCode();
      const userCode = randomUserCode();
      const expiresAt = isoNow(CODE_TTL_SECONDS * 1000);
      const body = c.req.valid("json");
      // Deduplicated so a client asking for the same scope twice cannot pad
      // the list the approval page shows.
      const scopes = [...new Set(body.scopes ?? DEVICE_SCOPES)];

      await c.env.DB.prepare(
        `INSERT INTO device_codes (device_code_hash, user_code, client_name, scopes, expires_at)
         VALUES (?1, ?2, ?3, ?4, ?5)`,
      )
        .bind(
          await sha256Hex(deviceCode),
          userCode,
          body.client_name,
          scopes.join(" "),
          expiresAt,
        )
        .run();

      // Expired handshakes are worthless; drop them off the request path.
      // An approval nobody ever collected leaves a live key behind, so it is
      // revoked before the row that would have delivered it goes away.
      const staleBefore = isoNow(-3600_000);
      c.executionCtx.waitUntil(
        c.env.DB.batch([
          c.env.DB.prepare(
            `UPDATE api_keys SET revoked_at = datetime('now')
             WHERE revoked_at IS NULL AND id IN (
               SELECT api_key_id FROM device_codes
               WHERE api_key_id IS NOT NULL AND granted_key IS NOT NULL
                 AND expires_at < ?1)`,
          ).bind(staleBefore),
          c.env.DB.prepare(`DELETE FROM device_codes WHERE expires_at < ?1`).bind(staleBefore),
        ]) as unknown as Promise<unknown>,
      );

      return c.json(
        {
          device_code: deviceCode,
          user_code: userCode,
          verification_url: `${siteUrl(c)}/link`,
          interval: POLL_INTERVAL_SECONDS,
          expires_in: CODE_TTL_SECONDS,
          scopes,
        },
        201,
      );
    },
  );

  // ── Poll ────────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/auth/device/token",
      tags: ["auth"],
      summary: "Poll a pairing for its key",
      description:
        "Answers `pending` until the user decides. The first poll after " +
        "approval carries the key and is the only one that does.",
      request: {
        body: {
          content: {
            "application/json": { schema: z.object({ device_code: z.string().min(1) }) },
          },
        },
      },
      responses: {
        200: {
          description: "Current state of the pairing.",
          content: { "application/json": { schema: DevicePollSchema } },
        },
        404: { description: "Unknown device code.", content: { "application/json": { schema: ErrorSchema } } },
        429: { description: "Polling too fast.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { device_code } = c.req.valid("json");
      const hash = await sha256Hex(device_code);

      // Budgets one pairing generously but caps a code-guessing loop: at
      // 3-second intervals a well-behaved client uses 200 of these.
      if (!(await rateLimit(c, `device:${hash.slice(0, 32)}`, "device_poll", 400))) {
        return c.json({ error: "rate_limited" }, 429);
      }

      const row = await c.env.DB.prepare(
        `SELECT device_code_hash, status, user_id, granted_key, scopes, expires_at
         FROM device_codes WHERE device_code_hash = ?1`,
      )
        .bind(hash)
        .first<{
          device_code_hash: string;
          status: string;
          user_id: string | null;
          granted_key: string | null;
          scopes: string;
          expires_at: string;
        }>();
      if (!row) return c.json({ error: "not_found" }, 404);

      if (row.status === "denied") {
        await c.env.DB.prepare(`DELETE FROM device_codes WHERE device_code_hash = ?1`)
          .bind(hash)
          .run();
        return c.json({ status: "denied" as const }, 200);
      }
      if (row.status !== "approved" && expired(row.expires_at)) {
        await c.env.DB.prepare(`DELETE FROM device_codes WHERE device_code_hash = ?1`)
          .bind(hash)
          .run();
        return c.json({ status: "expired" as const }, 200);
      }
      if (row.status !== "approved" || !row.user_id) {
        return c.json({ status: "pending" as const }, 200);
      }

      // Approved. The key is handed over once and the handshake is spent —
      // deleting the row here is what makes "exactly once" true even if two
      // polls race, because only the first sees a non-null granted_key.
      const user = await c.env.DB.prepare(
        `SELECT id, discord_id, discord_username, discord_avatar, display_name, role, created_at
         FROM users WHERE id = ?1`,
      )
        .bind(row.user_id)
        .first<Parameters<typeof userPayload>[0]>();
      const key = row.granted_key;
      await c.env.DB.prepare(`DELETE FROM device_codes WHERE device_code_hash = ?1`)
        .bind(hash)
        .run();

      return c.json(
        {
          status: "approved" as const,
          ...(key ? { key, scopes: parseScopes(row.scopes) } : {}),
          ...(user ? { user: userPayload(user) } : {}),
        },
        200,
      );
    },
  );

  // ── Approve or deny ─────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/auth/device/approve",
      tags: ["auth"],
      summary: "Approve or deny a pairing code",
      description:
        "Called from a signed-in browser session. Approving mints an API " +
        "key carrying the scopes the client asked for at handshake time — " +
        `expiring in ${KEY_TTL_DAYS} days, or ${PUBLISHING_KEY_TTL_DAYS} if it can publish — ` +
        "which the waiting client collects on its next poll. Only cookie " +
        "sessions may approve — a key cannot pair another device.",
      request: {
        body: {
          content: {
            "application/json": {
              schema: z.object({
                user_code: z.string().min(4).max(20),
                approve: z.boolean(),
              }),
            },
          },
        },
      },
      responses: {
        200: {
          description: "Decision recorded.",
          content: {
            "application/json": {
              schema: z.object({
                status: z.enum(["approved", "denied"]),
                client_name: z.string(),
                scopes: z.array(z.enum(PAIRABLE_SCOPES)),
              }),
            },
          },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "API keys cannot approve pairings.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such code, or it expired.", content: { "application/json": { schema: ErrorSchema } } },
        409: { description: "Already decided.", content: { "application/json": { schema: ErrorSchema } } },
        429: { description: "Too many attempts.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await authenticate(c);
      if (!auth) return c.json({ error: "unauthenticated" }, 401);
      if (auth.scopes !== null) {
        return c.json(
          {
            error: "session_required",
            message: "Pairings are approved from a signed-in browser, not from an API key.",
          },
          403,
        );
      }
      // A wrong code should cost something: user codes are short, and this
      // is the only endpoint that can be used to hunt for one.
      if (!(await rateLimit(c, auth.subject, "device_approve", 30))) {
        return c.json({ error: "rate_limited" }, 429);
      }

      const { user_code, approve } = c.req.valid("json");
      const code = user_code.trim().toUpperCase();
      const row = await c.env.DB.prepare(
        `SELECT device_code_hash, client_name, status, scopes, expires_at FROM device_codes
         WHERE user_code = ?1`,
      )
        .bind(code)
        .first<{
          device_code_hash: string;
          client_name: string;
          status: string;
          scopes: string;
          expires_at: string;
        }>();
      if (!row || expired(row.expires_at)) {
        return c.json({ error: "not_found", message: "That code is unknown or has expired." }, 404);
      }
      if (row.status !== "pending") {
        return c.json({ error: "already_decided", message: `Already ${row.status}.` }, 409);
      }

      const scopes = parseScopes(row.scopes);

      if (!approve) {
        await c.env.DB.prepare(
          `UPDATE device_codes SET status = 'denied' WHERE device_code_hash = ?1`,
        )
          .bind(row.device_code_hash)
          .run();
        return c.json({ status: "denied" as const, client_name: row.client_name, scopes }, 200);
      }

      const expiresAt = new Date(Date.now() + ttlDaysFor(scopes) * 86400_000).toISOString();
      const minted = await mintApiKey(
        c.env.DB,
        auth.user.id,
        row.client_name,
        scopes,
        expiresAt,
      );
      await c.env.DB.prepare(
        `UPDATE device_codes
         SET status = 'approved', user_id = ?2, api_key_id = ?3, granted_key = ?4
         WHERE device_code_hash = ?1 AND status = 'pending'`,
      )
        .bind(row.device_code_hash, auth.user.id, minted.id, minted.key)
        .run();

      return c.json({ status: "approved" as const, client_name: row.client_name, scopes }, 200);
    },
  );

  // ── What a code is for, before approving it ─────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/auth/device/pending/{user_code}",
      tags: ["auth"],
      summary: "Describe a pending pairing",
      description:
        "Lets the approval page name the client, and say what it is asking " +
        "for, before the user commits. Returns nothing that helps an " +
        "attacker: the client name is a label the client chose for itself, " +
        "and the scopes are what it would be granted anyway.",
      request: { params: z.object({ user_code: z.string() }) },
      responses: {
        200: {
          description: "The pending pairing.",
          content: {
            "application/json": {
              schema: z.object({
                client_name: z.string(),
                scopes: z.array(z.enum(PAIRABLE_SCOPES)),
                key_ttl_days: z.number().int().openapi({
                  description:
                    "How long the minted key would last. Served rather than " +
                    "assumed so the approval page cannot promise a lifetime " +
                    "the mint no longer honours.",
                }),
                expires_at: z.string().openapi({ description: "When this code stops working." }),
              }),
            },
          },
        },
        404: { description: "Unknown or expired.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const code = c.req.valid("param").user_code.trim().toUpperCase();
      const row = await c.env.DB.prepare(
        `SELECT client_name, scopes, expires_at FROM device_codes
         WHERE user_code = ?1 AND status = 'pending'`,
      )
        .bind(code)
        .first<{ client_name: string; scopes: string; expires_at: string }>();
      if (!row || expired(row.expires_at)) return c.json({ error: "not_found" }, 404);
      const scopes = parseScopes(row.scopes);
      return c.json(
        {
          client_name: row.client_name,
          scopes,
          key_ttl_days: ttlDaysFor(scopes),
          expires_at: row.expires_at,
        },
        200,
      );
    },
  );
}
