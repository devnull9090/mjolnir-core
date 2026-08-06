/**
 * The gallery, ratings and comments — the community layer of a mod page.
 *
 * Media: any signed-in user may submit screenshots (png/jpeg/webp) and
 * videos (mp4/webm) to a mod's gallery, but nothing shows publicly until a
 * moderator approves it — submissions land as 'pending' and only moderator
 * accounts skip the queue. Files are magic-byte-checked, stored in R2, and
 * served back through /media/{id} with the validated content type and
 * `nosniff`, so a file cannot lie its way into executing. Alt text is
 * required at the API level, not just the UI.
 *
 * Views: per-item and per-mod-page counters, incremented through beacon
 * endpoints. The rate-counter table folds repeats, so one viewer counts
 * once per item per hour, not once per render.
 *
 * Ratings: one per user per mod, upserted. Rollups (count, mean, Wilson
 * lower bound) are recomputed on every write; listings sort by the Wilson
 * bound so one 5★ cannot outrank two hundred 4.8★.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { Context } from "hono";
import { HTTPException } from "hono/http-exception";

import type { ApiEnv } from "./bindings";
import { getTool } from "../tools";
import { authenticate, rateLimit, requireScoped } from "./auth";
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
const MAX_VIDEO_BYTES = 64 * 1024 * 1024;
const MAX_MEDIA_PER_GALLERY = 20;
/** Queue-flooding guard: undecided submissions one user may hold per gallery. */
const MAX_PENDING_PER_USER = 5;

interface MediaSniffer {
  ext: string;
  mime: string;
  kind: "screenshot" | "video";
  match: (b: Uint8Array) => boolean;
}

/** Matched against the first bytes of the upload; the client's claimed
 *  content type is never consulted. */
const MEDIA_TYPES: MediaSniffer[] = [
  {
    ext: "png",
    mime: "image/png",
    kind: "screenshot",
    match: (b) => b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47,
  },
  {
    ext: "jpg",
    mime: "image/jpeg",
    kind: "screenshot",
    match: (b) => b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff,
  },
  {
    ext: "webp",
    mime: "image/webp",
    kind: "screenshot",
    match: (b) =>
      b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 &&
      b[8] === 0x57 && b[9] === 0x45 && b[10] === 0x42 && b[11] === 0x50,
  },
  {
    ext: "mp4",
    mime: "video/mp4",
    kind: "video",
    // ISO BMFF: a size box then 'ftyp' at offset 4.
    match: (b) => b[4] === 0x66 && b[5] === 0x74 && b[6] === 0x79 && b[7] === 0x70,
  },
  {
    ext: "webm",
    mime: "video/webm",
    kind: "video",
    // EBML header, shared by webm and mkv; served as webm either way.
    match: (b) => b[0] === 0x1a && b[1] === 0x45 && b[2] === 0xdf && b[3] === 0xa3,
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
 * What a gallery hangs off, as the queries below need it: a mod's row id, or
 * a tool's slug. Exactly one is set, which is what the `media` CHECK
 * constraint enforces on the way in (migration 0009).
 */
type GalleryOwner = { modId: string | null; toolSlug: string | null };

/**
 * Resolve a tool gallery. Tools live in the code registry rather than in D1,
 * so this is the only thing standing between a URL and a row keyed by an
 * arbitrary string — hence the registry lookup rather than a bare accept.
 */
function toolOwner(c: Ctx, slug: string): GalleryOwner {
  if (!getTool(slug)) throw new HTTPException(404, { res: c.json({ error: "not_found" }, 404) });
  return { modId: null, toolSlug: slug };
}

/**
 * `WHERE` fragment for "the media belonging to this owner", against the
 * given placeholder — which differs per statement, so it is passed in rather
 * than assumed to be `?1`.
 */
function ownerFilter(owner: GalleryOwner, placeholder: string, qualified = true): string {
  const column = owner.modId !== null ? "mod_id" : "tool_slug";
  return `${qualified ? "media." : ""}${column} = ${placeholder}`;
}

/** The value that fragment's placeholder takes. */
function ownerBind(owner: GalleryOwner): string {
  return owner.modId ?? owner.toolSlug!;
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
    mod_id: (r.mod_id as string) ?? null,
    tool_slug: (r.tool_slug as string) ?? null,
    url: mediaUrl(r.id as string),
    kind: r.kind as "screenshot" | "thumbnail" | "video",
    alt_text: r.alt_text as string,
    status: r.status as "pending" | "approved" | "rejected",
    view_count: (r.view_count as number) ?? 0,
    uploader: (r.uploader as string) ?? null,
    uploader_id: r.uploader_id as string,
    width: (r.width as number) ?? null,
    height: (r.height as number) ?? null,
    position: r.position as number,
    created_at: r.created_at as string,
  };
}

/** What view counting folds repeats by: the connecting IP. The beacons are
 *  open to signed-out visitors, so the key cannot require an account. */
function viewerKey(c: Ctx): string {
  return `ip:${c.req.header("cf-connecting-ip") ?? c.req.header("x-forwarded-for") ?? "unknown"}`;
}

/**
 * One owner's gallery: approved items for everyone, plus the caller's own
 * unreviewed submissions, plus everything for a moderator.
 */
async function listGallery(c: Ctx, owner: GalleryOwner) {
  const me = (await authenticate(c))?.user ?? null;
  const moderator = me !== null && me.role !== "user";
  const rows = await c.env.DB.prepare(
    `SELECT media.*, COALESCE(u.display_name, u.discord_username) AS uploader
     FROM media JOIN users u ON u.id = media.uploader_id
     WHERE ${ownerFilter(owner, "?1")}
       AND (?3 OR media.status = 'approved' OR media.uploader_id = ?2)
     ORDER BY media.position, media.created_at`,
  )
    .bind(ownerBind(owner), me?.id ?? "", moderator ? 1 : 0)
    .all();
  return { media: rows.results.map(mediaFromRow) };
}

/**
 * The upload path, shared by both kinds of gallery.
 *
 * Everything about handling the bytes is identical — magic-byte sniffing,
 * size ceilings, R2 storage, the row — so the only thing an owner changes is
 * where the object lands in the bucket. Who may submit is decided by the
 * route before it gets here, because the two answer it differently and only
 * one of them can answer 403.
 */
async function submitMedia(
  c: Ctx,
  owner: GalleryOwner,
  user: { id: string; role: string },
  keyPrefix: string,
) {
  const form = await c.req.parseBody();
  const file = form["file"];
  const alt = form["alt_text"];
  if (typeof alt !== "string" || alt.trim().length === 0) {
    return c.json(
      { error: "alt_text_required", message: "Describe the file for people who cannot see it." },
      400,
    );
  }
  if (!(file instanceof File)) {
    return c.json({ error: "no_file", message: "Attach the image or video as `file`." }, 400);
  }
  if (file.size > MAX_VIDEO_BYTES) return c.json({ error: "too_large" }, 413);

  // Sniff the leading bytes only; a 64 MiB video never needs a second
  // in-memory copy just to be identified.
  const head = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  const type = MEDIA_TYPES.find((t) => t.match(head));
  if (!type) {
    return c.json(
      { error: "unsupported_type", message: "Only png, jpeg, webp, mp4 and webm are accepted." },
      400,
    );
  }
  if (type.kind === "screenshot" && file.size > MAX_IMAGE_BYTES) {
    return c.json({ error: "too_large" }, 413);
  }

  const counts = await c.env.DB.prepare(
    `SELECT
       SUM(CASE WHEN status <> 'rejected' THEN 1 ELSE 0 END) AS live,
       SUM(CASE WHEN status = 'pending' AND uploader_id = ?2 THEN 1 ELSE 0 END) AS mine_pending
     FROM media WHERE ${ownerFilter(owner, "?1", false)}`,
  )
    .bind(ownerBind(owner), user.id)
    .first<{ live: number | null; mine_pending: number | null }>();
  if ((counts?.live ?? 0) >= MAX_MEDIA_PER_GALLERY) {
    return c.json({ error: "too_many", message: `At most ${MAX_MEDIA_PER_GALLERY} items each.` }, 400);
  }
  if (user.role === "user" && (counts?.mine_pending ?? 0) >= MAX_PENDING_PER_USER) {
    return c.json(
      { error: "too_many_pending", message: `At most ${MAX_PENDING_PER_USER} submissions awaiting review.` },
      400,
    );
  }

  const status = user.role === "user" ? "pending" : "approved";
  const id = crypto.randomUUID();
  const key = `${keyPrefix}/${id}.${type.ext}`;
  // The File goes to R2 as a Blob: known length (which a bare stream
  // would lack) and no second in-memory copy of a large video.
  await c.env.MODS_BUCKET.put(key, file as unknown as Parameters<typeof c.env.MODS_BUCKET.put>[1], {
    httpMetadata: { contentType: type.mime },
  });
  await c.env.DB.prepare(
    `INSERT INTO media (id, mod_id, tool_slug, uploader_id, r2_key, kind, alt_text, status, file_size, position)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9,
             COALESCE((SELECT MAX(position) + 1 FROM media WHERE ${ownerFilter(owner, "?10", false)}), 0))`,
  )
    .bind(id, owner.modId, owner.toolSlug, user.id, key, type.kind, alt.trim(), status, file.size, ownerBind(owner))
    .run();

  const row = await c.env.DB.prepare(
    `SELECT media.*, COALESCE(u.display_name, u.discord_username) AS uploader
     FROM media JOIN users u ON u.id = media.uploader_id WHERE media.id = ?1`,
  )
    .bind(id)
    .first();
  return c.json(mediaFromRow(row), 201);
}

export function registerCommunityRoutes(app: OpenAPIHono<ApiEnv>) {
  // ── Media ───────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/mods/{slug}/media",
      tags: ["media"],
      summary: "A mod's gallery",
      description:
        "Approved screenshots and videos. A signed-in caller also gets " +
        "their own pending and rejected submissions, marked by `status`; " +
        "moderators see everything.",
      request: { params: z.object({ slug: z.string() }) },
      responses: {
        200: { description: "The gallery.", content: { "application/json": { schema: MediaListSchema } } },
        404: { description: "No such mod.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { slug } = c.req.valid("param");
      const mod = await modBySlug(c, slug);
      return c.json(await listGallery(c, { modId: mod.id, toolSlug: null }), 200);
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/mods/{slug}/media",
      tags: ["media"],
      summary: "Submit a screenshot or video to a mod's gallery",
      description:
        "multipart/form-data with `file` (png/jpeg/webp ≤ 8 MiB, or " +
        "mp4/webm ≤ 64 MiB) and `alt_text` (required — every item ships " +
        "with a description). Any signed-in account may submit; the item " +
        "stays `pending` and invisible to others until a moderator " +
        "approves it. Moderator submissions publish immediately.",
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
        201: { description: "The stored item, with its moderation status.", content: { "application/json": { schema: MediaSchema } } },
        400: { description: "Missing alt text, unsupported file, or a full gallery.", content: { "application/json": { schema: ErrorSchema } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such mod.", content: { "application/json": { schema: ErrorSchema } } },
        413: { description: "File too large.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "mods:write", "media", 60);
      const { slug } = c.req.valid("param");
      const mod = await modBySlug(c, slug);
      return submitMedia(c, { modId: mod.id, toolSlug: null }, user, `media/${mod.id}`);
    },
  );

  // ── Tool previews ───────────────────────────────────────────────────
  //
  // The same gallery, against a tool in the code registry rather than a mod
  // row. The one difference is who may add: tools are first-party, so their
  // screenshots are curated by moderators rather than submitted by anyone.

  app.openapi(
    createRoute({
      method: "get",
      path: "/tools/{slug}/media",
      tags: ["media"],
      summary: "A tool's previews",
      description:
        "Approved screenshots and videos for one of the tools on /tools. " +
        "Moderators additionally see anything not yet approved.",
      request: { params: z.object({ slug: z.string() }) },
      responses: {
        200: { description: "The gallery.", content: { "application/json": { schema: MediaListSchema } } },
        404: { description: "No such tool.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { slug } = c.req.valid("param");
      return c.json(await listGallery(c, toolOwner(c, slug)), 200);
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/tools/{slug}/media",
      tags: ["media"],
      summary: "Add a preview to a tool (moderators)",
      description:
        "multipart/form-data with `file` (png/jpeg/webp ≤ 8 MiB, or " +
        "mp4/webm ≤ 64 MiB) and `alt_text` (required — every item ships " +
        "with a description). Moderators only, and the item publishes " +
        "immediately: there is no queue for a gallery only moderators can " +
        "write to.",
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
        201: { description: "The stored item.", content: { "application/json": { schema: MediaSchema } } },
        400: { description: "Missing alt text, unsupported file, or a full gallery.", content: { "application/json": { schema: ErrorSchema } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Moderators only.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such tool.", content: { "application/json": { schema: ErrorSchema } } },
        413: { description: "File too large.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "mods:write", "media", 60);
      const { slug } = c.req.valid("param");
      const owner = toolOwner(c, slug);
      if (user.role === "user") {
        return c.json(
          { error: "forbidden", message: "Tool previews are curated by moderators." },
          403,
        );
      }
      return submitMedia(c, owner, user, `media/tools/${slug}`);
    },
  );

  app.openapi(
    createRoute({
      method: "delete",
      path: "/media/{id}",
      tags: ["media"],
      summary: "Delete a gallery item",
      description:
        "The uploader, the mod's owner, or a moderator. A tool preview has " +
        "no owner, so it is the uploader or a moderator.",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: { description: "Gone.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Not yours.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such item.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "mods:write", "media", 60);
      const { id } = c.req.valid("param");
      // LEFT JOIN: a tool preview has no mod row behind it, and an inner
      // join would report it as missing rather than as undeletable.
      const row = await c.env.DB.prepare(
        `SELECT media.id, media.r2_key, media.uploader_id, mods.owner_id FROM media
         LEFT JOIN mods ON mods.id = media.mod_id WHERE media.id = ?1`,
      )
        .bind(id)
        .first<{ id: string; r2_key: string; uploader_id: string; owner_id: string | null }>();
      if (!row) return c.json({ error: "not_found" }, 404);
      if (row.owner_id !== user.id && row.uploader_id !== user.id && user.role === "user") {
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
      summary: "Serve a gallery file",
      description:
        "Streams the image or video. Byte ranges are honoured so videos " +
        "can seek. Items not yet approved are served only to their " +
        "uploader and moderators; everyone else gets 404, not 403 — the " +
        "queue's existence is nobody else's business.",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: { description: "The file bytes." },
        206: { description: "The requested byte range." },
        404: { description: "No such item.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const row = await c.env.DB.prepare(`SELECT r2_key, status, uploader_id FROM media WHERE id = ?1`)
        .bind(id)
        .first<{ r2_key: string; status: string; uploader_id: string }>();
      if (!row) return c.json({ error: "not_found" }, 404);

      const approved = row.status === "approved";
      if (!approved) {
        const me = (await authenticate(c))?.user ?? null;
        if (!me || (me.id !== row.uploader_id && me.role === "user")) {
          return c.json({ error: "not_found" }, 404);
        }
      }

      const headers: Record<string, string> = {
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        // Unreviewed bytes never land in a shared cache.
        "Cache-Control": approved ? "public, max-age=31536000, immutable" : "private, no-store",
      };

      // Minimal range support — `bytes=start-` and `bytes=start-end` — which
      // is all <video> seeking sends.
      const rangeHeader = c.req.header("range");
      const parsed = rangeHeader ? /^bytes=(\d+)-(\d*)$/.exec(rangeHeader) : null;
      if (parsed) {
        const offset = Number(parsed[1]);
        const end = parsed[2] ? Number(parsed[2]) : undefined;
        const obj = await c.env.MODS_BUCKET.get(row.r2_key, {
          range: end === undefined ? { offset } : { offset, length: end - offset + 1 },
        });
        if (!obj || !("body" in obj) || offset >= obj.size) {
          return c.json({ error: "not_found" }, 404);
        }
        const last = end === undefined ? obj.size - 1 : Math.min(end, obj.size - 1);
        return c.body(obj.body as unknown as ReadableStream, 206, {
          ...headers,
          "Content-Type": obj.httpMetadata?.contentType ?? "application/octet-stream",
          "Content-Range": `bytes ${offset}-${last}/${obj.size}`,
          "Content-Length": String(last - offset + 1),
        });
      }

      const obj = await c.env.MODS_BUCKET.get(row.r2_key);
      if (!obj) return c.json({ error: "not_found" }, 404);
      return c.body(obj.body as unknown as ReadableStream, 200, {
        ...headers,
        // The type recorded at upload after magic-byte validation — never
        // whatever a client claimed.
        "Content-Type": obj.httpMetadata?.contentType ?? "application/octet-stream",
        "Content-Length": String(obj.size),
      });
    },
  );

  // ── Views ───────────────────────────────────────────────────────────
  //
  // Open beacons, deliberately: view counts include signed-out visitors or
  // they are fiction. The rate-counter table folds repeats — one count per
  // viewer per item per hour — so refresh-spam moves nothing.

  app.openapi(
    createRoute({
      method: "post",
      path: "/media/{id}/view",
      tags: ["media"],
      summary: "Count a gallery item view",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: {
          description: "The current total.",
          content: { "application/json": { schema: z.object({ views: z.number().int() }) } },
        },
        404: { description: "No such item.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const row = await c.env.DB.prepare(
        `SELECT view_count FROM media WHERE id = ?1 AND status = 'approved'`,
      )
        .bind(id)
        .first<{ view_count: number }>();
      if (!row) return c.json({ error: "not_found" }, 404);
      if (await rateLimit(c, viewerKey(c), `view:m:${id}`, 1)) {
        await c.env.DB.prepare(`UPDATE media SET view_count = view_count + 1 WHERE id = ?1`)
          .bind(id)
          .run();
        return c.json({ views: row.view_count + 1 }, 200);
      }
      return c.json({ views: row.view_count }, 200);
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/mods/{slug}/view",
      tags: ["mods"],
      summary: "Count a mod page view",
      request: { params: z.object({ slug: z.string() }) },
      responses: {
        200: {
          description: "The current total.",
          content: { "application/json": { schema: z.object({ views: z.number().int() }) } },
        },
        404: { description: "No such mod.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { slug } = c.req.valid("param");
      const mod = await c.env.DB.prepare(
        `SELECT id, view_count FROM mods WHERE slug = ?1 AND status = 'published'`,
      )
        .bind(slug)
        .first<{ id: string; view_count: number }>();
      if (!mod) return c.json({ error: "not_found" }, 404);
      if (await rateLimit(c, viewerKey(c), `view:p:${mod.id}`, 1)) {
        await c.env.DB.prepare(`UPDATE mods SET view_count = view_count + 1 WHERE id = ?1`)
          .bind(mod.id)
          .run();
        return c.json({ views: mod.view_count + 1 }, 200);
      }
      return c.json({ views: mod.view_count }, 200);
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
      // Either credential identifies "mine": the launcher rates with a
      // paired API key, and it has to be able to see its own score.
      const me = (await authenticate(c))?.user ?? null;

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
                COALESCE(u.display_name, u.discord_username) AS author, u.id AS author_id,
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
            author_id: r.deleted_at ? null : (r.author_id as string),
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
