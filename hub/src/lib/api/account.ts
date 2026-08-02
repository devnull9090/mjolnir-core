/**
 * API keys for third-party tools.
 *
 * A key is `mjc_` + 32 random url-safe chars, shown exactly once at
 * creation; only its SHA-256 lands in D1. Keys carry a scope list checked
 * on every write (`authenticate` in auth.ts) and can be revoked without
 * touching the others.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { D1Database } from "@cloudflare/workers-types";
import { HTTPException } from "hono/http-exception";

import type { ApiEnv } from "./bindings";
import { authenticate, sha256Hex } from "./auth";
import { ErrorSchema } from "./schemas";

export const KNOWN_SCOPES = ["mods:read", "mods:write", "ratings:write", "comments:write"] as const;
const MAX_KEYS_PER_USER = 20;

const ApiKeySchema = z
  .object({
    id: z.string(),
    name: z.string(),
    key_prefix: z.string().openapi({ example: "mjc_a1b2c3", description: "For telling keys apart; not the key." }),
    scopes: z.array(z.enum(KNOWN_SCOPES)),
    last_used_at: z.string().nullable(),
    expires_at: z.string().nullable(),
    created_at: z.string(),
  })
  .openapi("ApiKey");

const ApiKeyCreateSchema = z
  .object({
    name: z.string().min(1).max(80).openapi({ example: "my-mod-manager" }),
    scopes: z.array(z.enum(KNOWN_SCOPES)).min(1).default(["mods:read"]),
    /** Days until expiry; omit for a non-expiring key. */
    expires_in_days: z.number().int().min(1).max(365).optional(),
  })
  .openapi("ApiKeyCreate");

const ApiKeyCreatedSchema = ApiKeySchema.extend({
  key: z.string().openapi({
    description: "The full key. Shown exactly once — store it now.",
    example: "mjc_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  }),
}).openapi("ApiKeyCreated");

function randomKey(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return "mjc_" + btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * Mint a key and store only its hash. Shared with device pairing, which
 * mints on the user's behalf once they approve a device — the same key
 * shape, the same storage rule, so a paired launcher is indistinguishable
 * from any other API client afterwards.
 */
export async function mintApiKey(
  db: D1Database,
  userId: string,
  name: string,
  scopes: readonly string[],
  expiresAt: string | null = null,
): Promise<{ id: string; key: string; prefix: string }> {
  const key = randomKey();
  const id = crypto.randomUUID();
  const prefix = key.slice(0, 10);
  await db
    .prepare(
      `INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, scopes, expires_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`,
    )
    .bind(id, userId, name, await sha256Hex(key), prefix, scopes.join(" "), expiresAt)
    .run();
  return { id, key, prefix };
}

export function registerAccountRoutes(app: OpenAPIHono<ApiEnv>) {
  app.openapi(
    createRoute({
      method: "get",
      path: "/account/api-keys",
      tags: ["account"],
      summary: "List your API keys",
      responses: {
        200: {
          description: "Active (non-revoked) keys.",
          content: { "application/json": { schema: z.object({ keys: z.array(ApiKeySchema) }) } },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await authenticate(c);
      if (!auth) return c.json({ error: "unauthenticated" }, 401);
      const rows = await c.env.DB.prepare(
        `SELECT id, name, key_prefix, scopes, last_used_at, expires_at, created_at
         FROM api_keys WHERE user_id = ?1 AND revoked_at IS NULL ORDER BY created_at DESC`,
      )
        .bind(auth.user.id)
        .all();
      return c.json(
        {
          keys: rows.results.map((r) => ({
            id: r.id as string,
            name: r.name as string,
            key_prefix: r.key_prefix as string,
            scopes: (r.scopes as string)
              .split(/\s+/)
              .filter(Boolean) as (typeof KNOWN_SCOPES)[number][],
            last_used_at: (r.last_used_at as string) ?? null,
            expires_at: (r.expires_at as string) ?? null,
            created_at: r.created_at as string,
          })),
        },
        200,
      );
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/account/api-keys",
      tags: ["account"],
      summary: "Create an API key",
      description:
        "Keys are created from a browser session only — a key cannot mint " +
        "more keys. The full key appears once in the response and never again.",
      request: {
        body: { content: { "application/json": { schema: ApiKeyCreateSchema } } },
      },
      responses: {
        201: { description: "The key — store it now.", content: { "application/json": { schema: ApiKeyCreatedSchema } } },
        400: { description: "Too many keys.", content: { "application/json": { schema: ErrorSchema } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "API keys cannot create keys.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await authenticate(c);
      if (!auth) return c.json({ error: "unauthenticated" }, 401);
      if (auth.scopes !== null) {
        return c.json({ error: "session_required", message: "Keys are minted from a signed-in browser session, not from another key." }, 403);
      }
      const body = c.req.valid("json");

      const count = await c.env.DB.prepare(
        `SELECT COUNT(*) AS n FROM api_keys WHERE user_id = ?1 AND revoked_at IS NULL`,
      )
        .bind(auth.user.id)
        .first<{ n: number }>();
      if ((count?.n ?? 0) >= MAX_KEYS_PER_USER) {
        return c.json({ error: "too_many_keys", message: `At most ${MAX_KEYS_PER_USER} active keys.` }, 400);
      }

      const expiresAt = body.expires_in_days
        ? new Date(Date.now() + body.expires_in_days * 86400_000).toISOString()
        : null;
      const { id, key, prefix } = await mintApiKey(
        c.env.DB,
        auth.user.id,
        body.name,
        body.scopes,
        expiresAt,
      );

      return c.json(
        {
          id,
          key,
          name: body.name,
          key_prefix: prefix,
          scopes: body.scopes,
          last_used_at: null,
          expires_at: expiresAt,
          created_at: new Date().toISOString(),
        },
        201,
      );
    },
  );

  app.openapi(
    createRoute({
      method: "delete",
      path: "/account/api-keys/{id}",
      tags: ["account"],
      summary: "Revoke an API key",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: { description: "Revoked.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such key.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await authenticate(c);
      if (!auth) return c.json({ error: "unauthenticated" }, 401);
      const { id } = c.req.valid("param");
      const res = await c.env.DB.prepare(
        `UPDATE api_keys SET revoked_at = datetime('now')
         WHERE id = ?1 AND user_id = ?2 AND revoked_at IS NULL`,
      )
        .bind(id, auth.user.id)
        .run();
      if (!res.meta.changes) return c.json({ error: "not_found" }, 404);
      return c.json({ ok: true }, 200);
    },
  );
}

/** Guard shared by moderation-only routes. */
export async function requireModerator(c: Parameters<typeof authenticate>[0]) {
  const auth = await authenticate(c);
  if (!auth) throw new HTTPException(401, { res: c.json({ error: "unauthenticated" }, 401) });
  if (auth.user.role === "user") {
    throw new HTTPException(403, { res: c.json({ error: "forbidden" }, 403) });
  }
  return auth;
}
