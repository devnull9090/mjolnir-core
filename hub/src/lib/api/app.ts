/**
 * The public API: an OpenAPIHono app mounted under /api/v1 by the Next.js
 * catch-all route handler.
 *
 * Kept free of Next.js and OpenNext imports on purpose — the spec export
 * script (scripts/export-openapi.mts) imports this module under plain Node,
 * so it must not drag in anything that assumes a Workers runtime at import
 * time.
 */
import { OpenAPIHono, createRoute, z } from "@hono/zod-openapi";
import { cors } from "hono/cors";

import type { ApiEnv } from "./bindings";
import { loginCallback, loginRedirect, logout, sessionUser } from "./auth";
import { registerPublishRoutes } from "./publish";
import { registerCommunityRoutes } from "./community";
import { registerAccountRoutes } from "./account";
import { registerModerationRoutes } from "./moderation";
import { registerCodeSyncRoutes } from "./codesync";
import {
  ErrorSchema,
  HealthSchema,
  ModDetailSchema,
  ModListQuerySchema,
  ModListSchema,
  ReleaseListSchema,
  UserSchema,
  modFromRow,
  releaseFromRow,
} from "./schemas";

export const openApiInfo = {
  openapi: "3.1.0" as const,
  info: {
    title: "MJOLNIR Hub API",
    version: "1.0.0",
    description:
      "Open API for the MJOLNIR mod platform for Halo Campaign Evolved. " +
      "Reads are public and unauthenticated. Browser sessions use Discord " +
      "OAuth with an HttpOnly cookie; third-party tools authenticate with " +
      "`Authorization: Bearer mjc_…` API keys carrying scopes (mods:read, " +
      "mods:write, ratings:write, comments:write), minted at /account/api-keys. " +
      "Any authenticated write may additionally answer 401 (no identity), " +
      "403 (missing scope), or 429 (per-subject hourly write budget) with " +
      "the standard Error shape.",
  },
  servers: [
    { url: "https://mjolnircore.com", description: "Production" },
    { url: "http://localhost:3000", description: "Local development" },
  ],
};

// ── Cursor pagination ─────────────────────────────────────────────────
// Opaque keyset cursors: base64url of {v, id}. Never expose the shape.

interface Cursor {
  v: string | number;
  id: string;
}

function encodeCursor(c: Cursor): string {
  return btoa(JSON.stringify(c)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function decodeCursor(s: string | undefined): Cursor | null {
  if (!s) return null;
  try {
    const parsed = JSON.parse(atob(s.replace(/-/g, "+").replace(/_/g, "/")));
    if (typeof parsed?.id !== "string") return null;
    return parsed as Cursor;
  } catch {
    return null;
  }
}

// ── App ───────────────────────────────────────────────────────────────

export const app = new OpenAPIHono<ApiEnv>({
  // Uniform validation failures matching ErrorSchema, instead of raw ZodError.
  defaultHook: (result, c) => {
    if (!result.success) {
      const detail = result.error.issues
        .map((i) => `${i.path.join(".") || "body"}: ${i.message}`)
        .join("; ");
      return c.json({ error: "validation", message: detail }, 400);
    }
  },
}).basePath("/api/v1");

// Fully open reads: any origin may call the API from a browser.
app.use(
  "*",
  cors({
    origin: (origin) => origin,
    credentials: false,
    allowMethods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
  }),
);

// ── Health ────────────────────────────────────────────────────────────

app.openapi(
  createRoute({
    method: "get",
    path: "/health",
    tags: ["meta"],
    summary: "Service health",
    responses: {
      200: {
        description: "The service is up.",
        content: { "application/json": { schema: HealthSchema } },
      },
    },
  }),
  (c) =>
    c.json(
      { status: "ok" as const, service: "mjolnir-hub" as const, timestamp: new Date().toISOString() },
      200,
    ),
);

// ── Auth ──────────────────────────────────────────────────────────────

app.openapi(
  createRoute({
    method: "get",
    path: "/auth/discord",
    tags: ["auth"],
    summary: "Begin Discord OAuth",
    description:
      "Redirects the browser to Discord's consent screen. Pass `next` to " +
      "return to a specific page after login.",
    request: {
      query: z.object({ next: z.string().optional() }),
    },
    responses: {
      302: { description: "Redirect to Discord." },
      500: {
        description: "OAuth is not configured on this deployment.",
        content: { "application/json": { schema: ErrorSchema } },
      },
    },
  }),
  loginRedirect,
);

app.openapi(
  createRoute({
    method: "get",
    path: "/auth/discord/callback",
    tags: ["auth"],
    summary: "OAuth callback",
    description: "Discord redirects here; on success a session cookie is set.",
    request: {
      query: z.object({ code: z.string().optional(), state: z.string().optional() }),
    },
    responses: {
      302: { description: "Logged in; redirect to `next`." },
      400: {
        description: "State mismatch or missing code.",
        content: { "application/json": { schema: ErrorSchema } },
      },
      403: {
        description: "The account is banned.",
        content: { "application/json": { schema: ErrorSchema } },
      },
      502: {
        description: "Discord rejected the exchange.",
        content: { "application/json": { schema: ErrorSchema } },
      },
    },
  }),
  loginCallback,
);

app.openapi(
  createRoute({
    method: "get",
    path: "/auth/me",
    tags: ["auth"],
    summary: "Current session",
    responses: {
      200: {
        description: "The signed-in user.",
        content: { "application/json": { schema: UserSchema } },
      },
      401: {
        description: "No valid session.",
        content: { "application/json": { schema: ErrorSchema } },
      },
    },
  }),
  async (c) => {
    const user = await sessionUser(c);
    if (!user) return c.json({ error: "unauthenticated" }, 401);
    return c.json(
      {
        id: user.id,
        username: user.discord_username,
        display_name: user.display_name,
        avatar_url: user.discord_avatar
          ? `https://cdn.discordapp.com/avatars/${user.discord_id}/${user.discord_avatar}.png`
          : null,
        role: user.role,
        created_at: user.created_at,
      },
      200,
    );
  },
);

app.openapi(
  createRoute({
    method: "post",
    path: "/auth/logout",
    tags: ["auth"],
    summary: "Sign out",
    responses: {
      200: {
        description: "Session cookie cleared.",
        content: { "application/json": { schema: z.object({ ok: z.boolean() }) } },
      },
    },
  }),
  logout,
);

// ── Mods ──────────────────────────────────────────────────────────────

const SORTS = {
  newest: { expr: "m.created_at", type: "string" },
  downloads: { expr: "m.download_count", type: "number" },
  rating: { expr: "COALESCE(m.rating_wilson, -1)", type: "number" },
} as const;

app.openapi(
  createRoute({
    method: "get",
    path: "/mods",
    tags: ["mods"],
    summary: "List published mods",
    request: { query: ModListQuerySchema },
    responses: {
      200: {
        description: "A page of mods.",
        content: { "application/json": { schema: ModListSchema } },
      },
      400: {
        description: "Bad cursor.",
        content: { "application/json": { schema: ErrorSchema } },
      },
    },
  }),
  async (c) => {
    const { q, category, type, sort, cursor, limit } = c.req.valid("query");
    const s = SORTS[sort];

    const where: string[] = ["m.status = 'published'"];
    const binds: (string | number)[] = [];
    if (category) {
      where.push(`m.category = ?${binds.length + 1}`);
      binds.push(category);
    }
    if (type) {
      where.push(`m.type = ?${binds.length + 1}`);
      binds.push(type);
    }
    if (q) {
      where.push(`(m.name LIKE ?${binds.length + 1} OR m.summary LIKE ?${binds.length + 1})`);
      binds.push(`%${q}%`);
    }

    const cur = decodeCursor(cursor);
    if (cursor && !cur) return c.json({ error: "bad_cursor" }, 400);
    if (cur) {
      where.push(`(${s.expr}, m.id) < (?${binds.length + 1}, ?${binds.length + 2})`);
      binds.push(cur.v, cur.id);
    }

    const rows = await c.env.DB.prepare(
      `SELECT m.*, COALESCE(u.display_name, u.discord_username) AS author
       FROM mods m JOIN users u ON u.id = m.owner_id
       WHERE ${where.join(" AND ")}
       ORDER BY ${s.expr} DESC, m.id DESC
       LIMIT ?${binds.length + 1}`,
    )
      .bind(...binds, limit + 1)
      .all();

    const page = rows.results.slice(0, limit);
    const more = rows.results.length > limit;
    const last = page[page.length - 1] as Record<string, unknown> | undefined;
    const next =
      more && last
        ? encodeCursor({
            v: (sort === "newest"
              ? last.created_at
              : sort === "downloads"
                ? last.download_count
                : (last.rating_wilson ?? -1)) as string | number,
            id: last.id as string,
          })
        : null;

    return c.json({ mods: page.map(modFromRow), next_cursor: next }, 200);
  },
);

app.openapi(
  createRoute({
    method: "get",
    path: "/mods/{slug}",
    tags: ["mods"],
    summary: "A mod by slug",
    request: { params: z.object({ slug: z.string() }) },
    responses: {
      200: {
        description: "The mod.",
        content: { "application/json": { schema: ModDetailSchema } },
      },
      404: {
        description: "No such mod.",
        content: { "application/json": { schema: ErrorSchema } },
      },
    },
  }),
  async (c) => {
    const { slug } = c.req.valid("param");
    const row = await c.env.DB.prepare(
      `SELECT m.*, COALESCE(u.display_name, u.discord_username) AS author
       FROM mods m JOIN users u ON u.id = m.owner_id
       WHERE m.slug = ?1`,
    )
      .bind(slug)
      .first();
    if (!row) return c.json({ error: "not_found" }, 404);
    if (row.status !== "published") {
      // Drafts are visible to their owner (and moderators) only, so the
      // manage flow can run before the first release publishes the mod.
      const user = await sessionUser(c);
      if (!user || (row.owner_id !== user.id && user.role === "user")) {
        return c.json({ error: "not_found" }, 404);
      }
    }
    return c.json({ ...modFromRow(row), description_md: (row.description_md as string) ?? null }, 200);
  },
);

app.openapi(
  createRoute({
    method: "get",
    path: "/mods/{slug}/releases",
    tags: ["mods"],
    summary: "Published releases of a mod, newest first",
    request: { params: z.object({ slug: z.string() }) },
    responses: {
      200: {
        description: "The releases.",
        content: { "application/json": { schema: ReleaseListSchema } },
      },
      404: {
        description: "No such mod.",
        content: { "application/json": { schema: ErrorSchema } },
      },
    },
  }),
  async (c) => {
    const { slug } = c.req.valid("param");
    const mod = await c.env.DB.prepare(
      `SELECT id FROM mods WHERE slug = ?1 AND status = 'published'`,
    )
      .bind(slug)
      .first<{ id: string }>();
    if (!mod) return c.json({ error: "not_found" }, 404);

    const rows = await c.env.DB.prepare(
      `SELECT * FROM mod_releases
       WHERE mod_id = ?1 AND status = 'published'
       ORDER BY created_at DESC, id DESC`,
    )
      .bind(mod.id)
      .all();
    return c.json({ releases: rows.results.map(releaseFromRow) }, 200);
  },
);

// ── Publishing & conflicts ────────────────────────────────────────────

registerPublishRoutes(app);

// ── Community: media, ratings, comments ───────────────────────────────

registerCommunityRoutes(app);

// ── API keys & moderation ─────────────────────────────────────────────

registerAccountRoutes(app);
registerModerationRoutes(app);

// ── Signed code-mod mirror ────────────────────────────────────────────

registerCodeSyncRoutes(app);

// ── Spec ──────────────────────────────────────────────────────────────

app.doc31("/openapi.json", openApiInfo);
