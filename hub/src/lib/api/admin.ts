/**
 * Admin-only routes: the user directory.
 *
 * Admin is a stricter bar than moderator — the role is seated exclusively
 * through SUPER_ADMIN_DISCORD_ID (auth.ts), so in practice these routes
 * answer to one account. Moderators get 403 like everyone else: the
 * directory exposes Discord IDs, which the moderation queues never needed.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { Context } from "hono";
import { HTTPException } from "hono/http-exception";

import type { ApiEnv } from "./bindings";
import { authenticate } from "./auth";
import { ErrorSchema } from "./schemas";

type Ctx = Context<ApiEnv>;

const AdminUserSchema = z
  .object({
    id: z.string(),
    discord_id: z.string().openapi({ example: "867190209217429514" }),
    discord_username: z.string(),
    display_name: z.string().nullable(),
    avatar_url: z.string().nullable(),
    role: z.enum(["user", "moderator", "admin"]),
    trust_level: z.number().int(),
    created_at: z.string(),
    banned_at: z.string().nullable(),
  })
  .openapi("AdminUser");

/** Guard for admin-only routes; moderators don't clear this bar. */
export async function requireAdmin(c: Ctx) {
  const auth = await authenticate(c);
  if (!auth) throw new HTTPException(401, { res: c.json({ error: "unauthenticated" }, 401) });
  if (auth.user.role !== "admin") {
    throw new HTTPException(403, { res: c.json({ error: "forbidden" }, 403) });
  }
  return auth;
}

export function registerAdminRoutes(app: OpenAPIHono<ApiEnv>) {
  app.openapi(
    createRoute({
      method: "get",
      path: "/admin/users",
      tags: ["admin"],
      summary: "Look up registered accounts (admin)",
      description:
        "Every account that has signed in, with its Discord snowflake. " +
        "`q` matches a Discord ID exactly, or the Discord username / " +
        "display name as a substring; empty lists the newest signups.",
      request: {
        query: z.object({
          q: z.string().max(100).optional().openapi({
            description: "Discord ID (exact) or name fragment.",
          }),
          limit: z.coerce.number().int().min(1).max(100).default(50),
        }),
      },
      responses: {
        200: {
          description: "Matching accounts, newest first, plus the match count.",
          content: {
            "application/json": {
              schema: z
                .object({ users: z.array(AdminUserSchema), total: z.number().int() })
                .openapi("AdminUserList"),
            },
          },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Admins only.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      await requireAdmin(c);
      const { q, limit } = c.req.valid("query");

      let where = "1=1";
      const binds: string[] = [];
      if (q) {
        // LIKE wildcards in the query text are literals, not patterns.
        const fragment = `%${q.replace(/([\\%_])/g, "\\$1")}%`;
        where = `(discord_id = ?1
                  OR discord_username LIKE ?2 ESCAPE '\\'
                  OR display_name LIKE ?2 ESCAPE '\\')`;
        binds.push(q, fragment);
      }

      const [rows, count] = await Promise.all([
        c.env.DB.prepare(
          `SELECT id, discord_id, discord_username, discord_avatar, display_name,
                  role, trust_level, created_at, banned_at
           FROM users WHERE ${where}
           ORDER BY created_at DESC, id DESC LIMIT ?${binds.length + 1}`,
        )
          .bind(...binds, limit)
          .all(),
        c.env.DB.prepare(`SELECT COUNT(*) AS n FROM users WHERE ${where}`)
          .bind(...binds)
          .first<{ n: number }>(),
      ]);

      return c.json(
        {
          users: rows.results.map((r) => ({
            id: r.id as string,
            discord_id: r.discord_id as string,
            discord_username: r.discord_username as string,
            display_name: (r.display_name as string) ?? null,
            avatar_url: r.discord_avatar
              ? `https://cdn.discordapp.com/avatars/${r.discord_id}/${r.discord_avatar}.png`
              : null,
            role: r.role as "user" | "moderator" | "admin",
            trust_level: r.trust_level as number,
            created_at: r.created_at as string,
            banned_at: (r.banned_at as string) ?? null,
          })),
          total: count?.n ?? rows.results.length,
        },
        200,
      );
    },
  );
}
