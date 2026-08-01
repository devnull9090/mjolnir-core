/**
 * Screenshots, ratings and comments — the community layer of a mod page.
 *
 * Media: files are magic-byte-checked (png/jpeg/webp only), stored in R2,
 * and served back through /media/{id} with the validated content type and
 * `nosniff`, so a file cannot lie its way into executing. Alt text is
 * required at the API level, not just the UI.
 *
 * Ratings: one per user per mod, upserted. Rollups (count, mean, Wilson
 * lower bound) are recomputed on every write; listings sort by the Wilson
 * bound so one 5★ cannot outrank two hundred 4.8★.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { Context } from "hono";
import { HTTPException } from "hono/http-exception";

import type { ApiEnv, SessionUser } from "./bindings";
import { requireScoped, sessionUser } from "./auth";
import {
  CommentCreateSchema,
  CommentListSchema,
  ErrorSchema,
  MediaListSchema,
  MediaSchema,
  RatingPutSchema,
  RatingSummarySchema,
} from "./schemas";

type Ctx = Context<ApiEnv>;

const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_MEDIA_PER_MOD = 20;

const IMAGE_TYPES: { ext: string; mime: string; match: (b: Uint8Array) => boolean }[] = [
  {
    ext: "png",
    mime: "image/png",
    match: (b) => b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47,
  },
  {
    ext: "jpg",
    mime: "image/jpeg",
    match: (b) => b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff,
  },
  {
    ext: "webp",
    mime: "image/webp",
    match: (b) =>
      b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 &&
      b[8] === 0x57 && b[9] === 0x45 && b[10] === 0x42 && b[11] === 0x50,
  },
];

async function modBySlug(c: Ctx, slug: string) {
  const mod = await c.env.DB.prepare(
    `SELECT id, owner_id, status FROM mods WHERE slug = ?1`,
  )
    .bind(slug)
    .first<{ id: string; owner_id: string; status: string }>();
  if (!mod) throw new HTTPException(404, { res: c.json({ error: "not_found" }, 404) });
  return mod;
}

/**
 * Wilson score lower bound (95%) of the positive fraction, with 1–5 stars
 * mapped onto [0, 1]. The ranking statistic listings sort by: pessimistic
 * for tiny sample sizes, converging on the mean as votes accumulate.
 */
export function wilsonLowerBound(mean: number, n: number): number {
  if (n === 0) return 0;
  const p = (mean - 1) / 4;
  const z = 1.96;
  const z2 = z * z;
  return (
    (p + z2 / (2 * n) - z * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / (1 + z2 / n)
  );
}

async function recomputeRating(c: Ctx, modId: string) {
  const agg = await c.env.DB.prepare(
    `SELECT COUNT(*) AS n, AVG(score) AS mean FROM ratings WHERE mod_id = ?1`,
  )
    .bind(modId)
    .first<{ n: number; mean: number | null }>();
  const n = agg?.n ?? 0;
  const mean = agg?.mean ?? null;
  await c.env.DB.prepare(
    `UPDATE mods SET rating_count = ?2, rating_mean = ?3, rating_wilson = ?4,
     updated_at = datetime('now') WHERE id = ?1`,
  )
    .bind(modId, n, mean, mean === null ? null : wilsonLowerBound(mean, n))
    .run();
}

function mediaUrl(id: string): string {
  return `/api/v1/media/${id}`;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function mediaFromRow(r: any) {
  return {
    id: r.id as string,
    mod_id: r.mod_id as string,
    url: mediaUrl(r.id as string),
    kind: r.kind as "screenshot" | "thumbnail",
    alt_text: r.alt_text as string,
    width: (r.width as number) ?? null,
    height: (r.height as number) ?? null,
    position: r.position as number,
    created_at: r.created_at as string,
  };
}

export function registerCommunityRoutes(app: OpenAPIHono<ApiEnv>) {
  // ── Media ───────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/mods/{slug}/media",
      tags: ["media"],
      summary: "A mod's screenshots",
      request: { params: z.object({ slug: z.string() }) },
      responses: {
        200: { description: "The images.", content: { "application/json": { schema: MediaListSchema } } },
        404: { description: "No such mod.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { slug } = c.req.valid("param");
      const mod = await modBySlug(c, slug);
      const rows = await c.env.DB.prepare(
        `SELECT * FROM media WHERE mod_id = ?1 ORDER BY position, created_at`,
      )
        .bind(mod.id)
        .all();
      return c.json({ media: rows.results.map(mediaFromRow) }, 200);
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/mods/{slug}/media",
      tags: ["media"],
      summary: "Upload a screenshot",
      description:
        "multipart/form-data with `file` (png, jpeg or webp, ≤ 8 MiB) and " +
        "`alt_text` (required — every image ships with a description).",
      request: {
        params: z.object({ slug: z.string() }),
        body: {
          content: {
            "multipart/form-data": {
              schema: z.object({
                file: z.any().openapi({ type: "string", format: "binary" }),
                alt_text: z.string().min(1).max(500),
              }),
            },
          },
        },
      },
      responses: {
        201: { description: "The stored image.", content: { "application/json": { schema: MediaSchema } } },
        400: { description: "Missing alt text or not an image.", content: { "application/json": { schema: ErrorSchema } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Not the owner.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such mod.", content: { "application/json": { schema: ErrorSchema } } },
        413: { description: "Image too large.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "mods:write", "media", 60);
      const { slug } = c.req.valid("param");
      const mod = await modBySlug(c, slug);
      if (mod.owner_id !== user.id && user.role === "user") {
        return c.json({ error: "forbidden" }, 403);
      }

      const form = await c.req.parseBody();
      const file = form["file"];
      const alt = form["alt_text"];
      if (typeof alt !== "string" || alt.trim().length === 0) {
        return c.json(
          { error: "alt_text_required", message: "Describe the image for people who cannot see it." },
          400,
        );
      }
      if (!(file instanceof File)) {
        return c.json({ error: "no_file", message: "Attach the image as `file`." }, 400);
      }
      if (file.size > MAX_IMAGE_BYTES) return c.json({ error: "too_large" }, 413);

      const bytes = new Uint8Array(await file.arrayBuffer());
      const kind = IMAGE_TYPES.find((t) => t.match(bytes));
      if (!kind) {
        return c.json(
          { error: "not_an_image", message: "Only png, jpeg and webp are accepted." },
          400,
        );
      }

      const count = await c.env.DB.prepare(`SELECT COUNT(*) AS n FROM media WHERE mod_id = ?1`)
        .bind(mod.id)
        .first<{ n: number }>();
      if ((count?.n ?? 0) >= MAX_MEDIA_PER_MOD) {
        return c.json({ error: "too_many", message: `At most ${MAX_MEDIA_PER_MOD} images per mod.` }, 400);
      }

      const id = crypto.randomUUID();
      const key = `media/${mod.id}/${id}.${kind.ext}`;
      await c.env.MODS_BUCKET.put(key, bytes as unknown as ArrayBuffer, {
        httpMetadata: { contentType: kind.mime },
      });
      await c.env.DB.prepare(
        `INSERT INTO media (id, mod_id, uploader_id, r2_key, kind, alt_text, position)
         VALUES (?1, ?2, ?3, ?4, 'screenshot', ?5,
                 COALESCE((SELECT MAX(position) + 1 FROM media WHERE mod_id = ?2), 0))`,
      )
        .bind(id, mod.id, user.id, key, alt.trim())
        .run();

      const row = await c.env.DB.prepare(`SELECT * FROM media WHERE id = ?1`).bind(id).first();
      return c.json(mediaFromRow(row), 201);
    },
  );

  app.openapi(
    createRoute({
      method: "delete",
      path: "/media/{id}",
      tags: ["media"],
      summary: "Delete a screenshot",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: { description: "Gone.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Not the owner.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such image.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "mods:write", "media", 60);
      const { id } = c.req.valid("param");
      const row = await c.env.DB.prepare(
        `SELECT media.id, media.r2_key, mods.owner_id FROM media
         JOIN mods ON mods.id = media.mod_id WHERE media.id = ?1`,
      )
        .bind(id)
        .first<{ id: string; r2_key: string; owner_id: string }>();
      if (!row) return c.json({ error: "not_found" }, 404);
      if (row.owner_id !== user.id && user.role === "user") {
        return c.json({ error: "forbidden" }, 403);
      }
      await c.env.MODS_BUCKET.delete(row.r2_key);
      await c.env.DB.prepare(`DELETE FROM media WHERE id = ?1`).bind(id).run();
      return c.json({ ok: true }, 200);
    },
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/media/{id}",
      tags: ["media"],
      summary: "Serve an image",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: { description: "The image bytes." },
        404: { description: "No such image.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const row = await c.env.DB.prepare(`SELECT r2_key FROM media WHERE id = ?1`)
        .bind(id)
        .first<{ r2_key: string }>();
      if (!row) return c.json({ error: "not_found" }, 404);
      const obj = await c.env.MODS_BUCKET.get(row.r2_key);
      if (!obj) return c.json({ error: "not_found" }, 404);
      return c.body(obj.body as unknown as ReadableStream, 200, {
        // The type recorded at upload after magic-byte validation — never
        // whatever a client claimed.
        "Content-Type": obj.httpMetadata?.contentType ?? "application/octet-stream",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=31536000, immutable",
      });
    },
  );

  // ── Ratings ─────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "put",
      path: "/mods/{slug}/ratings/me",
      tags: ["ratings"],
      summary: "Rate a mod",
      description: "One rating per user per mod; calling again replaces yours.",
      request: {
        params: z.object({ slug: z.string() }),
        body: { content: { "application/json": { schema: RatingPutSchema } } },
      },
      responses: {
        200: { description: "Recorded.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such mod.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "ratings:write", "ratings", 60);
      const { slug } = c.req.valid("param");
      const { score, review_md } = c.req.valid("json");
      const mod = await modBySlug(c, slug);

      await c.env.DB.prepare(
        `INSERT INTO ratings (mod_id, user_id, score, review_md)
         VALUES (?1, ?2, ?3, ?4)
         ON CONFLICT(mod_id, user_id) DO UPDATE SET
           score = excluded.score, review_md = excluded.review_md,
           updated_at = datetime('now')`,
      )
        .bind(mod.id, user.id, score, review_md ?? null)
        .run();
      await recomputeRating(c, mod.id);
      return c.json({ ok: true }, 200);
    },
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/mods/{slug}/ratings",
      tags: ["ratings"],
      summary: "Rating summary and recent reviews",
      request: { params: z.object({ slug: z.string() }) },
      responses: {
        200: { description: "The summary.", content: { "application/json": { schema: RatingSummarySchema } } },
        404: { description: "No such mod.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { slug } = c.req.valid("param");
      const mod = await modBySlug(c, slug);
      const me = await sessionUser(c);

      const [agg, dist, mine, reviews] = await Promise.all([
        c.env.DB.prepare(`SELECT COUNT(*) AS n, AVG(score) AS mean FROM ratings WHERE mod_id = ?1`)
          .bind(mod.id)
          .first<{ n: number; mean: number | null }>(),
        c.env.DB.prepare(
          `SELECT score, COUNT(*) AS n FROM ratings WHERE mod_id = ?1 GROUP BY score`,
        )
          .bind(mod.id)
          .all(),
        me
          ? c.env.DB.prepare(`SELECT score FROM ratings WHERE mod_id = ?1 AND user_id = ?2`)
              .bind(mod.id, me.id)
              .first<{ score: number }>()
          : Promise.resolve(null),
        c.env.DB.prepare(
          `SELECT COALESCE(u.display_name, u.discord_username) AS author, r.score,
                  r.review_md, r.created_at
           FROM ratings r JOIN users u ON u.id = r.user_id
           WHERE r.mod_id = ?1 AND r.review_md IS NOT NULL AND length(r.review_md) > 0
           ORDER BY r.updated_at DESC LIMIT 20`,
        )
          .bind(mod.id)
          .all(),
      ]);

      const distribution: Record<string, number> = { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 };
      for (const r of dist.results) distribution[String(r.score)] = r.n as number;

      return c.json(
        {
          count: agg?.n ?? 0,
          mean: agg?.mean ?? null,
          distribution,
          mine: mine?.score ?? null,
          reviews: reviews.results.map((r) => ({
            author: r.author as string,
            score: r.score as number,
            review_md: r.review_md as string,
            created_at: r.created_at as string,
          })),
        },
        200,
      );
    },
  );

  // ── Comments ────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/mods/{slug}/comments",
      tags: ["comments"],
      summary: "A mod's comment thread",
      description: "Flat list, oldest first; `parent_id` links replies. Clients assemble the tree.",
      request: { params: z.object({ slug: z.string() }) },
      responses: {
        200: { description: "The comments.", content: { "application/json": { schema: CommentListSchema } } },
        404: { description: "No such mod.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { slug } = c.req.valid("param");
      const mod = await modBySlug(c, slug);
      const rows = await c.env.DB.prepare(
        `SELECT cm.id, cm.mod_id, cm.parent_id, cm.body_md, cm.deleted_at, cm.created_at,
                COALESCE(u.display_name, u.discord_username) AS author,
                u.discord_id, u.discord_avatar
         FROM comments cm JOIN users u ON u.id = cm.user_id
         WHERE cm.mod_id = ?1 ORDER BY cm.created_at`,
      )
        .bind(mod.id)
        .all();
      return c.json(
        {
          comments: rows.results.map((r) => ({
            id: r.id as string,
            mod_id: r.mod_id as string,
            parent_id: (r.parent_id as string) ?? null,
            author: r.deleted_at ? null : (r.author as string),
            author_avatar:
              !r.deleted_at && r.discord_avatar
                ? `https://cdn.discordapp.com/avatars/${r.discord_id}/${r.discord_avatar}.png`
                : null,
            body_md: r.deleted_at ? null : (r.body_md as string),
            deleted: !!r.deleted_at,
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
      path: "/mods/{slug}/comments",
      tags: ["comments"],
      summary: "Post a comment",
      request: {
        params: z.object({ slug: z.string() }),
        body: { content: { "application/json": { schema: CommentCreateSchema } } },
      },
      responses: {
        201: { description: "Posted.", content: { "application/json": { schema: z.object({ id: z.string() }) } } },
        400: { description: "Bad parent.", content: { "application/json": { schema: ErrorSchema } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such mod.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "comments:write", "comments", 60);
      const { slug } = c.req.valid("param");
      const { body_md, parent_id } = c.req.valid("json");
      const mod = await modBySlug(c, slug);

      if (parent_id) {
        const parent = await c.env.DB.prepare(
          `SELECT id FROM comments WHERE id = ?1 AND mod_id = ?2`,
        )
          .bind(parent_id, mod.id)
          .first();
        if (!parent) return c.json({ error: "bad_parent" }, 400);
      }

      const id = crypto.randomUUID();
      await c.env.DB.prepare(
        `INSERT INTO comments (id, mod_id, user_id, parent_id, body_md)
         VALUES (?1, ?2, ?3, ?4, ?5)`,
      )
        .bind(id, mod.id, user.id, parent_id ?? null, body_md)
        .run();
      return c.json({ id }, 201);
    },
  );

  app.openapi(
    createRoute({
      method: "delete",
      path: "/comments/{id}",
      tags: ["comments"],
      summary: "Delete a comment",
      description: "Author or moderator. Soft delete: the thread keeps its shape, the body is blanked.",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: { description: "Deleted.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Not yours.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such comment.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "comments:write", "comments", 60);
      const { id } = c.req.valid("param");
      const row = await c.env.DB.prepare(`SELECT user_id FROM comments WHERE id = ?1`)
        .bind(id)
        .first<{ user_id: string }>();
      if (!row) return c.json({ error: "not_found" }, 404);
      if (row.user_id !== user.id && user.role === "user") {
        return c.json({ error: "forbidden" }, 403);
      }
      await c.env.DB.prepare(
        `UPDATE comments SET deleted_at = datetime('now'), body_md = '' WHERE id = ?1`,
      )
        .bind(id)
        .run();
      return c.json({ ok: true }, 200);
    },
  );
}
