/**
 * Reports, the moderation queues (reports and gallery submissions), yanks,
 * and the audit trail.
 *
 * Every moderator decision writes audit_log — the append-only record of
 * who did what to whose content, queryable when a decision is disputed.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { Context } from "hono";

import type { ApiEnv } from "./bindings";
import { getTool } from "../tools";
import { authenticate, rateLimit } from "./auth";
import { requireModerator } from "./account";
import { ErrorSchema } from "./schemas";

type Ctx = Context<ApiEnv>;

const REPORT_REASONS = ["malware", "stolen", "broken", "nsfw", "spam", "other"] as const;

/**
 * Publishing is unmoderated, so this is the brake: once this many distinct
 * accounts hold open reports against a mod (or its releases), it leaves
 * public view until a moderator decides. Low on purpose — a hidden mod
 * costs its author a review; a live bad mod costs players.
 */
const AUTO_HIDE_REPORTERS = 3;

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

/** A hidden mod as the review queue sees it: enough to judge whether the
 *  reports that pulled it were right. */
const HiddenModSchema = z
  .object({
    id: z.string(),
    slug: z.string(),
    name: z.string(),
    owner: z.string(),
    open_reporters: z.number().int().openapi({
      description: "Distinct accounts currently holding open reports against it.",
    }),
    hidden_at: z.string(),
  })
  .openapi("HiddenMod");

/** A gallery submission as the review queue sees it: the item plus enough
 *  context (what it was submitted to, uploader) to judge it without leaving
 *  the page. */
const QueuedMediaSchema = z
  .object({
    id: z.string(),
    url: z.string(),
    kind: z.enum(["screenshot", "thumbnail", "video"]),
    alt_text: z.string(),
    status: z.enum(["pending", "approved", "rejected"]),
    file_size: z.number().int().nullable(),
    uploader: z.string(),
    owner: z
      .object({ type: z.enum(["mod", "tool"]), slug: z.string() })
      .openapi({ description: "What it was submitted to, and where that lives on the site." }),
    owner_name: z.string(),
    created_at: z.string(),
  })
  .openapi("QueuedMedia");

export async function audit(
  c: Ctx,
  actorId: string | null,
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

/** The mod a report is ultimately about, when its subject is a mod or one
 *  of a mod's releases; reports on comments, media and users don't feed
 *  the auto-hide count. */
async function reportedModId(c: Ctx, subjectType: string, subjectId: string) {
  if (subjectType === "mod") {
    const row = await c.env.DB.prepare(`SELECT id FROM mods WHERE id = ?1`)
      .bind(subjectId)
      .first<{ id: string }>();
    return row?.id ?? null;
  }
  if (subjectType === "release") {
    const row = await c.env.DB.prepare(`SELECT mod_id FROM mod_releases WHERE id = ?1`)
      .bind(subjectId)
      .first<{ mod_id: string }>();
    return row?.mod_id ?? null;
  }
  return null;
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

      // Publishing needs no approval, so reporting is what pulls the brake:
      // enough distinct accounts with open reports against one mod hides it
      // until a moderator restores or removes it. Counting accounts rather
      // than reports keeps one determined reporter from doing it alone.
      const modId = await reportedModId(c, body.subject_type, body.subject_id);
      if (modId) {
        const reporters = await c.env.DB.prepare(
          `SELECT COUNT(DISTINCT reporter_id) AS n FROM reports
           WHERE status = 'open'
             AND ((subject_type = 'mod' AND subject_id = ?1)
               OR (subject_type = 'release' AND subject_id IN
                    (SELECT id FROM mod_releases WHERE mod_id = ?1)))`,
        )
          .bind(modId)
          .first<{ n: number }>();
        if ((reporters?.n ?? 0) >= AUTO_HIDE_REPORTERS) {
          const res = await c.env.DB.prepare(
            `UPDATE mods SET status = 'hidden', updated_at = datetime('now')
             WHERE id = ?1 AND status = 'published'`,
          )
            .bind(modId)
            .run();
          if (res.meta.changes) {
            await audit(
              c,
              null,
              "mod_auto_hidden",
              "mod",
              modId,
              `${reporters!.n} accounts with open reports`,
            );
          }
        }
      }
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

  // ── Hidden mods ─────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/moderation/mods",
      tags: ["moderation"],
      summary: "Hidden mods awaiting a decision (moderators)",
      description:
        "Mods pulled from public view — automatically by report volume, or " +
        "by a moderator — each with its open-report tally so the queue can " +
        "be worked without cross-referencing.",
      responses: {
        200: {
          description: "Hidden mods, oldest first.",
          content: { "application/json": { schema: z.object({ mods: z.array(HiddenModSchema) }) } },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Moderators only.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      await requireModerator(c);
      const rows = await c.env.DB.prepare(
        `SELECT m.id, m.slug, m.name, m.updated_at,
                COALESCE(u.display_name, u.discord_username) AS owner,
                (SELECT COUNT(DISTINCT r.reporter_id) FROM reports r
                 WHERE r.status = 'open'
                   AND ((r.subject_type = 'mod' AND r.subject_id = m.id)
                     OR (r.subject_type = 'release' AND r.subject_id IN
                          (SELECT id FROM mod_releases WHERE mod_id = m.id)))) AS open_reporters
         FROM mods m JOIN users u ON u.id = m.owner_id
         WHERE m.status = 'hidden' ORDER BY m.updated_at LIMIT 200`,
      ).all();
      return c.json(
        {
          mods: rows.results.map((r) => ({
            id: r.id as string,
            slug: r.slug as string,
            name: r.name as string,
            owner: r.owner as string,
            open_reporters: r.open_reporters as number,
            hidden_at: r.updated_at as string,
          })),
        },
        200,
      );
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/moderation/mods/{slug}",
      tags: ["moderation"],
      summary: "Restore, hide, or remove a mod (moderators)",
      description:
        "`restore` returns a hidden mod to public view, `hide` pulls a " +
        "published one pending review, `remove` takes it down for good. " +
        "Every decision lands in the audit log.",
      request: {
        params: z.object({ slug: z.string() }),
        body: {
          content: {
            "application/json": {
              schema: z
                .object({ action: z.enum(["restore", "hide", "remove"]) })
                .openapi("ModDecision"),
            },
          },
        },
      },
      responses: {
        200: { description: "Decided.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Moderators only.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such mod, or not in a state the action applies to.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await requireModerator(c);
      const { slug } = c.req.valid("param");
      const { action } = c.req.valid("json");
      // Each action only makes sense from certain states; acting on a mod
      // that already left that state 404s rather than silently rewriting.
      const from = action === "restore" ? ["hidden"] : ["published", "hidden"];
      const to = action === "restore" ? "published" : action === "hide" ? "hidden" : "removed";
      const marks = from.map((_, i) => `?${i + 3}`).join(", ");
      const res = await c.env.DB.prepare(
        `UPDATE mods SET status = ?2, updated_at = datetime('now')
         WHERE slug = ?1 AND status IN (${marks})`,
      )
        .bind(slug, to, ...from)
        .run();
      if (!res.meta.changes) return c.json({ error: "not_found" }, 404);
      await audit(c, auth.user.id, `mod_${action}`, "mod", slug);
      return c.json({ ok: true }, 200);
    },
  );

  // ── Gallery queue ───────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/moderation/media",
      tags: ["moderation"],
      summary: "The gallery review queue (moderators)",
      request: {
        query: z.object({
          status: z.enum(["pending", "approved", "rejected"]).default("pending"),
        }),
      },
      responses: {
        200: {
          description: "Submissions, oldest first.",
          content: { "application/json": { schema: z.object({ media: z.array(QueuedMediaSchema) }) } },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Moderators only.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      await requireModerator(c);
      const { status } = c.req.valid("query");
      // LEFT JOIN on mods: a tool preview has no mod row, and an inner join
      // would drop it out of the queue entirely.
      const rows = await c.env.DB.prepare(
        `SELECT media.id, media.kind, media.alt_text, media.status, media.file_size,
                media.created_at, media.tool_slug, m.slug AS mod_slug, m.name AS mod_name,
                COALESCE(u.display_name, u.discord_username) AS uploader
         FROM media
         LEFT JOIN mods m ON m.id = media.mod_id
         JOIN users u ON u.id = media.uploader_id
         WHERE media.status = ?1 ORDER BY media.created_at LIMIT 200`,
      )
        .bind(status)
        .all();
      return c.json(
        {
          media: rows.results.map((r) => {
            const toolSlug = (r.tool_slug as string) ?? null;
            const tool = toolSlug ? getTool(toolSlug) : null;
            return {
              id: r.id as string,
              url: `/api/v1/media/${r.id}`,
              kind: r.kind as "screenshot" | "thumbnail" | "video",
              alt_text: r.alt_text as string,
              status: r.status as "pending" | "approved" | "rejected",
              file_size: (r.file_size as number) ?? null,
              uploader: r.uploader as string,
              owner: toolSlug
                ? { type: "tool" as const, slug: toolSlug }
                : { type: "mod" as const, slug: r.mod_slug as string },
              // A tool that has since left the registry still names itself
              // by its slug rather than rendering as a blank row.
              owner_name: toolSlug ? (tool?.name ?? toolSlug) : (r.mod_name as string),
              created_at: r.created_at as string,
            };
          }),
        },
        200,
      );
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/moderation/media/{id}",
      tags: ["moderation"],
      summary: "Approve or reject a gallery submission (moderators)",
      description:
        "Approval publishes the item to the mod's gallery. Rejection keeps " +
        "the record (and the bytes, visible only to the uploader) so the " +
        "submitter can see what happened and delete it themselves.",
      request: {
        params: z.object({ id: z.string() }),
        body: {
          content: {
            "application/json": {
              schema: z.object({ action: z.enum(["approve", "reject"]) }).openapi("MediaDecision"),
            },
          },
        },
      },
      responses: {
        200: { description: "Decided.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Moderators only.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such pending submission.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await requireModerator(c);
      const { id } = c.req.valid("param");
      const { action } = c.req.valid("json");
      const res = await c.env.DB.prepare(
        `UPDATE media SET status = ?2, reviewed_by = ?3, reviewed_at = datetime('now')
         WHERE id = ?1 AND status = 'pending'`,
      )
        .bind(id, action === "approve" ? "approved" : "rejected", auth.user.id)
        .run();
      if (!res.meta.changes) return c.json({ error: "not_found" }, 404);
      await audit(c, auth.user.id, `media_${action}`, "media", id);
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

