/**
 * Public user profiles: who an account is, and what it has done here.
 *
 * Open like every other read on this API. What that means for privacy is
 * decided by what the payload carries, not by a guard: the profile reports
 * counts, never a history. "Downloaded 14 mods" is public; *which* fourteen
 * is not exposed by any route, because the account being browsed never asked
 * to publish its library.
 *
 * Discord snowflakes stay out of it too — those live behind /admin/users,
 * which is admin-only for exactly that reason.
 *
 * The payload is assembled in queries.ts, which the profile page reads
 * directly, so the page and this route cannot come to disagree.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";

import type { ApiEnv } from "./bindings";
import { getUserProfile } from "./queries";
import { ErrorSchema, UserProfileSchema } from "./schemas";

export function registerProfileRoutes(app: OpenAPIHono<ApiEnv>) {
  app.openapi(
    createRoute({
      method: "get",
      path: "/users/{id}",
      tags: ["users"],
      summary: "A public profile",
      description:
        "An account's identity, its activity totals, and the mods it has " +
        "published. Counts only — no download or viewing history is exposed. " +
        "A banned account answers 404 like a missing one.",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: {
          description: "The profile.",
          content: { "application/json": { schema: UserProfileSchema } },
        },
        404: {
          description: "No such account.",
          content: { "application/json": { schema: ErrorSchema } },
        },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const profile = await getUserProfile(c.env.DB, id);
      if (!profile) return c.json({ error: "not_found" }, 404);
      return c.json(profile, 200);
    },
  );
}
