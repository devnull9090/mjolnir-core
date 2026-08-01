/**
 * Reports, the moderation queue, yanks, and the audit trail.
 *
 * Every moderator decision writes audit_log — the append-only record of
 * who did what to whose content, queryable when a decision is disputed.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { Context } from "hono";

import type { ApiEnv } from "./bindings";
import { authenticate, rateLimit } from "./auth";
import { requireModerator } from "./account";
import { ErrorSchema } from "./schemas";

type Ctx = Context<ApiEnv>;

const REPORT_REASONS = ["malware", "stolen", "broken", "nsfw", "spam", "other"] as const;

const ReportCreateSchema = z
  .object({
    subject_type: z.enum(["mod", "release", "comment", "media", "user"]),
    subject_id: z.string(),
    reason: z.enum(REPORT_REASONS),
    detail: z.string().max(2000).optional(),
  })
  .openapi("ReportCreate");

const ReportSchema = z
  .object({
    id: z.string(),
    reporter: z.string(),
    subject_type: z.string(),
    subject_id: z.string(),
    reason: z.string(),
    detail: z.string().nullable(),
    status: z.enum(["open", "resolved", "dismissed"]),
    created_at: z.string(),
  })
  .openapi("Report");

export async function audit(
  c: Ctx,
  actorId: string,
  action: string,
  subjectType: string,
  subjectId: string,
  detail?: string,
) {
  await c.env.DB.prepare(
    `INSERT INTO audit_log (actor_id, action, subject_type, subject_id, detail)
     VALUES (?1, ?2, ?3, ?4, ?5)`,
  )
    .bind(actorId, action, subjectType, subjectId, detail ?? null)
    .run();
}

export function registerModerationRoutes(app: OpenAPIHono<ApiEnv>) {
  // ── Reports ─────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/reports",
      tags: ["moderation"],
      summary: "Report content",
      request: { body: { content: { "application/json": { schema: ReportCreateSchema } } } },
      responses: {
        201: { description: "Filed.", content: { "application/json": { schema: z.object({ id: z.string() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        429: { description: "Slow down.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await authenticate(c);
      if (!auth) return c.json({ error: "unauthenticated" }, 401);
      if (!(await rateLimit(c, auth.subject, "reports", 20))) {
        return c.json({ error: "rate_limited" }, 429);
      }
      const body = c.req.valid("json");
      const id = crypto.randomUUID();
      await c.env.DB.prepare(
        `INSERT INTO reports (id, reporter_id, subject_type, subject_id, reason, detail)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
      )
        .bind(id, auth.user.id, body.subject_type, body.subject_id, body.reason, body.detail ?? null)
        .run();
      return c.json({ id }, 201);
    },
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/moderation/reports",
      tags: ["moderation"],
      summary: "The report queue (moderators)",
      request: {
        query: z.object({
          status: z.enum(["open", "resolved", "dismissed"]).default("open"),
        }),
      },
      responses: {
        200: {
          description: "Reports, oldest first.",
          content: { "application/json": { schema: z.object({ reports: z.array(ReportSchema) }) } },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Moderators only.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      await requireModerator(c);
      const { status } = c.req.valid("query");
      const rows = await c.env.DB.prepare(
        `SELECT r.*, COALESCE(u.display_name, u.discord_username) AS reporter
         FROM reports r JOIN users u ON u.id = r.reporter_id
         WHERE r.status = ?1 ORDER BY r.created_at LIMIT 200`,
      )
        .bind(status)
        .all();
      return c.json(
        {
          reports: rows.results.map((r) => ({
            id: r.id as string,
            reporter: r.reporter as string,
            subject_type: r.subject_type as string,
            subject_id: r.subject_id as string,
            reason: r.reason as string,
            detail: (r.detail as string) ?? null,
            status: r.status as "open" | "resolved" | "dismissed",
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
      path: "/moderation/reports/{id}",
      tags: ["moderation"],
      summary: "Resolve or dismiss a report (moderators)",
      request: {
        params: z.object({ id: z.string() }),
        body: {
          content: {
            "application/json": {
              schema: z.object({ action: z.enum(["resolve", "dismiss"]) }).openapi("ReportDecision"),
            },
          },
        },
      },
      responses: {
        200: { description: "Decided.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Moderators only.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such open report.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await requireModerator(c);
      const { id } = c.req.valid("param");
      const { action } = c.req.valid("json");
      const res = await c.env.DB.prepare(
        `UPDATE reports SET status = ?2, resolved_by = ?3, resolved_at = datetime('now')
         WHERE id = ?1 AND status = 'open'`,
      )
        .bind(id, action === "resolve" ? "resolved" : "dismissed", auth.user.id)
        .run();
      if (!res.meta.changes) return c.json({ error: "not_found" }, 404);
      await audit(c, auth.user.id, `report_${action}`, "report", id);
      return c.json({ ok: true }, 200);
    },
  );

  // ── Yank ────────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/releases/{id}/yank",
      tags: ["moderation"],
      summary: "Yank a published release",
      description:
        "Owner or moderator. A yanked release stops being downloadable and " +
        "leaves the conflict index, but its record and scan history remain.",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: { description: "Yanked.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Not yours.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such published release.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await authenticate(c);
      if (!auth) return c.json({ error: "unauthenticated" }, 401);
      const { id } = c.req.valid("param");
      const row = await c.env.DB.prepare(
        `SELECT r.id, m.owner_id FROM mod_releases r JOIN mods m ON m.id = r.mod_id
         WHERE r.id = ?1 AND r.status = 'published'`,
      )
        .bind(id)
        .first<{ id: string; owner_id: string }>();
      if (!row) return c.json({ error: "not_found" }, 404);
      if (row.owner_id !== auth.user.id && auth.user.role === "user") {
        return c.json({ error: "forbidden" }, 403);
      }
      await c.env.DB.batch([
        c.env.DB.prepare(
          `UPDATE mod_releases SET status = 'yanked', yanked_at = datetime('now') WHERE id = ?1`,
        ).bind(id),
        c.env.DB.prepare(`DELETE FROM release_chunks WHERE release_id = ?1`).bind(id),
      ]);
      await audit(c, auth.user.id, "release_yank", "release", id);
      return c.json({ ok: true }, 200);
    },
  );
}

