/**
 * Publishing pipeline and the conflict index.
 *
 * Upload flow (docs/mjolnir_format.md):
 *   POST /mods                     create the mod (draft)
 *   POST /mods/{slug}/releases     create a pending release
 *   PUT  /releases/{id}/archive    raw .mjolnir bytes → R2
 *   POST /releases/{id}/complete   scan; publish or reject
 *
 * Only `content` mods take this path. Script and native mods ship from
 * mjolnir-core's reviewed, signed CI releases — the hub never accepts
 * executable uploads (docs/hub_architecture.md §2).
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { Context } from "hono";
import { HTTPException } from "hono/http-exception";

import type { ApiEnv } from "./bindings";
import { requireScoped } from "./auth";
import {
  ConflictCheckRequestSchema,
  ConflictCheckResponseSchema,
  ConflictListSchema,
  ErrorSchema,
  ModCreateSchema,
  ModDetailSchema,
  ReleaseCreateSchema,
  ReleaseSchema,
  ReleaseStatusSchema,
  modFromRow,
  releaseFromRow,
} from "./schemas";
import { MAX_ARCHIVE_BYTES, SCANNER_VERSION, scanArchive } from "./scan";
import { chunkIdToHex } from "./iostore";

type Ctx = Context<ApiEnv>;

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes as BufferSource);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Load a release plus its mod, verifying the session user may write it.
 * Throws an HTTPException carrying the error response — the declared 401,
 * 403 and 404 responses on each route — so handlers stay a straight line.
 */
async function ownedRelease(c: Ctx, releaseId: string) {
  const { user } = await requireScoped(c, "mods:write", "publish", 60);
  const row = await c.env.DB.prepare(
    `SELECT r.*, m.slug AS mod_slug, m.owner_id, m.type AS mod_type
     FROM mod_releases r JOIN mods m ON m.id = r.mod_id WHERE r.id = ?1`,
  )
    .bind(releaseId)
    .first<Record<string, unknown>>();
  if (!row) throw new HTTPException(404, { res: c.json({ error: "not_found" }, 404) });
  if (row.owner_id !== user.id && user.role === "user") {
    throw new HTTPException(403, { res: c.json({ error: "forbidden" }, 403) });
  }
  return { user, release: row };
}

export function registerPublishRoutes(app: OpenAPIHono<ApiEnv>) {
  // ── Create mod ──────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/mods",
      tags: ["publish"],
      summary: "Create a mod",
      description:
        "Creates a draft `content` mod owned by the signed-in user. Script " +
        "and native mods cannot be created here; they ship from the " +
        "mjolnir-core repository's release pipeline.",
      request: {
        body: { content: { "application/json": { schema: ModCreateSchema } } },
      },
      responses: {
        201: {
          description: "The new mod.",
          content: { "application/json": { schema: ModDetailSchema } },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        409: { description: "Slug taken.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "mods:write", "publish", 30);
      const body = c.req.valid("json");

      const id = crypto.randomUUID();
      try {
        await c.env.DB.batch([
          c.env.DB.prepare(
            `INSERT INTO mods (id, slug, name, summary, description_md, owner_id, type, category, license, nsfw, status)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, 'content', ?7, ?8, ?9, 'draft')`,
          ).bind(
            id,
            body.slug,
            body.name,
            body.summary ?? null,
            body.description_md ?? null,
            user.id,
            body.category,
            body.license ?? null,
            body.nsfw ? 1 : 0,
          ),
          c.env.DB.prepare(
            `INSERT INTO mod_authors (mod_id, user_id, role) VALUES (?1, ?2, 'owner')`,
          ).bind(id, user.id),
        ]);
      } catch (e) {
        if (String(e).includes("UNIQUE")) {
          return c.json({ error: "slug_taken", message: `'${body.slug}' already exists.` }, 409);
        }
        throw e;
      }

      const row = await c.env.DB.prepare(
        `SELECT m.*, COALESCE(u.display_name, u.discord_username) AS author
         FROM mods m JOIN users u ON u.id = m.owner_id WHERE m.id = ?1`,
      )
        .bind(id)
        .first();
      return c.json(
        { ...modFromRow(row), description_md: (row?.description_md as string) ?? null },
        201,
      );
    },
  );

  // ── Create release ──────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/mods/{slug}/releases",
      tags: ["publish"],
      summary: "Create a pending release",
      request: {
        params: z.object({ slug: z.string() }),
        body: { content: { "application/json": { schema: ReleaseCreateSchema } } },
      },
      responses: {
        201: {
          description: "The pending release; upload its archive next.",
          content: { "application/json": { schema: ReleaseSchema } },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Not the owner, or not a content mod.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such mod.", content: { "application/json": { schema: ErrorSchema } } },
        409: { description: "Version exists.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "mods:write", "publish", 60);
      const { slug } = c.req.valid("param");
      const body = c.req.valid("json");

      const mod = await c.env.DB.prepare(`SELECT id, owner_id, type FROM mods WHERE slug = ?1`)
        .bind(slug)
        .first<{ id: string; owner_id: string; type: string }>();
      if (!mod) return c.json({ error: "not_found" }, 404);
      if (mod.owner_id !== user.id && user.role === "user") {
        return c.json({ error: "forbidden" }, 403);
      }
      if (mod.type !== "content") {
        return c.json(
          {
            error: "not_uploadable",
            message: "Script and native mods ship from mjolnir-core CI releases, not uploads.",
          },
          403,
        );
      }

      const id = crypto.randomUUID();
      try {
        await c.env.DB.prepare(
          `INSERT INTO mod_releases (id, mod_id, version, channel, changelog_md, build_min, build_max, status)
           VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 'pending')`,
        )
          .bind(
            id,
            mod.id,
            body.version,
            body.channel,
            body.changelog_md ?? null,
            body.build_min ?? null,
            body.build_max ?? null,
          )
          .run();
      } catch (e) {
        if (String(e).includes("UNIQUE")) {
          return c.json({ error: "version_exists" }, 409);
        }
        throw e;
      }
      const row = await c.env.DB.prepare(`SELECT * FROM mod_releases WHERE id = ?1`)
        .bind(id)
        .first();
      return c.json(releaseFromRow(row), 201);
    },
  );

  // ── Upload archive ──────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "put",
      path: "/releases/{id}/archive",
      tags: ["publish"],
      summary: "Upload the .mjolnir archive",
      description: `Raw zip bytes, at most ${MAX_ARCHIVE_BYTES / (1024 * 1024)} MiB. Re-uploading while pending or rejected replaces the archive and resets the release to pending.`,
      request: {
        params: z.object({ id: z.string() }),
        body: {
          content: {
            "application/zip": {
              schema: z.any().openapi({ type: "string", format: "binary" }),
            },
          },
        },
      },
      responses: {
        200: {
          description: "Stored; call /complete to scan and publish.",
          content: {
            "application/json": {
              schema: z.object({ sha256: z.string(), file_size: z.number().int() }),
            },
          },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Not the owner.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such release.", content: { "application/json": { schema: ErrorSchema } } },
        409: { description: "Release is published or yanked.", content: { "application/json": { schema: ErrorSchema } } },
        413: { description: "Archive too large.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const { release } = await ownedRelease(c, id);
      const status = release.status as string;
      if (status !== "pending" && status !== "rejected") {
        return c.json({ error: "immutable", message: `Release is ${status}.` }, 409);
      }

      const declared = Number(c.req.header("content-length") ?? 0);
      if (declared > MAX_ARCHIVE_BYTES) return c.json({ error: "too_large" }, 413);
      const bytes = new Uint8Array(await c.req.arrayBuffer());
      if (bytes.length > MAX_ARCHIVE_BYTES) return c.json({ error: "too_large" }, 413);
      if (bytes.length === 0) return c.json({ error: "too_large", message: "Empty body." }, 413);

      const key = `releases/${id}.mjolnir`;
      const hash = await sha256Hex(bytes);
      await c.env.MODS_BUCKET.put(key, bytes as unknown as ArrayBuffer);
      await c.env.DB.prepare(
        `UPDATE mod_releases
         SET r2_key = ?2, sha256 = ?3, file_size = ?4, status = 'pending'
         WHERE id = ?1`,
      )
        .bind(id, key, hash, bytes.length)
        .run();
      return c.json({ sha256: hash, file_size: bytes.length }, 200);
    },
  );

  // ── Complete: scan & publish ────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/releases/{id}/complete",
      tags: ["publish"],
      summary: "Scan the uploaded archive and publish or reject",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: {
          description: "Scan finished; status says whether it published.",
          content: { "application/json": { schema: ReleaseStatusSchema } },
        },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Not the owner.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No such release.", content: { "application/json": { schema: ErrorSchema } } },
        409: { description: "No archive uploaded, or already decided.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const { release } = await ownedRelease(c, id);
      if (release.status !== "pending" || !release.r2_key) {
        return c.json(
          { error: "not_ready", message: "Upload an archive first; scans run on pending releases." },
          409,
        );
      }

      const obj = await c.env.MODS_BUCKET.get(release.r2_key as string);
      if (!obj) return c.json({ error: "not_ready", message: "Archive missing from storage." }, 409);
      const bytes = new Uint8Array(await obj.arrayBuffer());

      const scan = scanArchive(bytes);
      // The manifest must agree with what the release claims to be.
      if (scan.manifest && scan.manifest.version !== release.version) {
        scan.findings.push({
          level: "error",
          code: "version_mismatch",
          message: `mjolnir.json says ${scan.manifest.version}, release is ${release.version}.`,
        });
        scan.verdict = "fail";
      }

      const statements = [
        c.env.DB.prepare(
          `INSERT INTO release_scans (id, release_id, verdict, findings, scanner_version)
           VALUES (?1, ?2, ?3, ?4, ?5)`,
        ).bind(
          crypto.randomUUID(),
          id,
          scan.verdict,
          JSON.stringify(scan.findings),
          SCANNER_VERSION,
        ),
        c.env.DB.prepare(`DELETE FROM release_chunks WHERE release_id = ?1`).bind(id),
        c.env.DB.prepare(`UPDATE mod_releases SET status = ?2 WHERE id = ?1`).bind(
          id,
          scan.verdict === "pass" ? "published" : "rejected",
        ),
      ];
      if (scan.verdict === "pass") {
        // A first published release takes its draft mod live with it.
        statements.push(
          c.env.DB.prepare(
            `UPDATE mods SET status = 'published', updated_at = datetime('now')
             WHERE id = ?1 AND status = 'draft'`,
          ).bind(release.mod_id as string),
        );
        // Chunk identity, batched under D1's bound-parameter budget.
        const PER = 40;
        for (let i = 0; i < scan.chunkIds.length; i += PER) {
          const slice = scan.chunkIds.slice(i, i + PER);
          const values = slice.map((_, j) => `(?1, ?${j + 2})`).join(", ");
          statements.push(
            c.env.DB.prepare(
              `INSERT OR IGNORE INTO release_chunks (release_id, chunk_id) VALUES ${values}`,
            ).bind(id, ...slice.map((s) => s.buffer.slice(s.byteOffset, s.byteOffset + 12))),
          );
        }
      }
      await c.env.DB.batch(statements);

      return c.json(
        {
          id,
          mod_id: release.mod_id as string,
          version: release.version as string,
          status: (scan.verdict === "pass" ? "published" : "rejected") as
            | "published"
            | "rejected",
          sha256: (release.sha256 as string) ?? null,
          file_size: (release.file_size as number) ?? null,
          chunk_count: scan.verdict === "pass" ? scan.chunkIds.length : 0,
          findings: scan.findings,
          created_at: release.created_at as string,
        },
        200,
      );
    },
  );

  // ── Release status ──────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/releases/{id}",
      tags: ["releases"],
      summary: "Release status and scan findings",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: {
          description: "The release.",
          content: { "application/json": { schema: ReleaseStatusSchema } },
        },
        404: { description: "No such release.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const release = await c.env.DB.prepare(`SELECT * FROM mod_releases WHERE id = ?1`)
        .bind(id)
        .first<Record<string, unknown>>();
      if (!release) return c.json({ error: "not_found" }, 404);

      const [scan, chunks] = await Promise.all([
        c.env.DB.prepare(
          `SELECT findings FROM release_scans WHERE release_id = ?1
           ORDER BY created_at DESC LIMIT 1`,
        )
          .bind(id)
          .first<{ findings: string }>(),
        c.env.DB.prepare(`SELECT COUNT(*) AS n FROM release_chunks WHERE release_id = ?1`)
          .bind(id)
          .first<{ n: number }>(),
      ]);

      return c.json(
        {
          id,
          mod_id: release.mod_id as string,
          version: release.version as string,
          status: release.status as "pending" | "scanning" | "published" | "rejected" | "yanked",
          sha256: (release.sha256 as string) ?? null,
          file_size: (release.file_size as number) ?? null,
          chunk_count: chunks?.n ?? 0,
          findings: scan ? JSON.parse(scan.findings) : [],
          created_at: release.created_at as string,
        },
        200,
      );
    },
  );

  // ── Download ────────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/releases/{id}/download",
      tags: ["releases"],
      summary: "Download the release archive",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: { description: "The .mjolnir archive (zip)." },
        302: { description: "Signed code-mod artifact; redirect to its canonical URL." },
        404: { description: "Not published.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const release = await c.env.DB.prepare(
        `SELECT r.r2_key, r.download_url, r.mod_id, m.slug, r.version FROM mod_releases r
         JOIN mods m ON m.id = r.mod_id
         WHERE r.id = ?1 AND r.status = 'published'`,
      )
        .bind(id)
        .first<{
          r2_key: string | null;
          download_url: string | null;
          mod_id: string;
          slug: string;
          version: string;
        }>();
      if (!release || (!release.r2_key && !release.download_url)) {
        return c.json({ error: "not_found" }, 404);
      }

      // Counter rollups; good enough until download volume argues for
      // Analytics Engine (docs/hub_architecture.md §6).
      c.executionCtx.waitUntil(
        c.env.DB.batch([
          c.env.DB.prepare(
            `UPDATE mod_releases SET download_count = download_count + 1 WHERE id = ?1`,
          ).bind(id),
          c.env.DB.prepare(
            `UPDATE mods SET download_count = download_count + 1 WHERE id = ?1`,
          ).bind(release.mod_id),
        ]) as unknown as Promise<unknown>,
      );

      // Signed code-mod artifacts live in the releases bucket; redirect to
      // the exact URL the signed manifest named.
      if (release.download_url) {
        return c.redirect(release.download_url, 302);
      }

      const obj = await c.env.MODS_BUCKET.get(release.r2_key!);
      if (!obj) return c.json({ error: "not_found" }, 404);
      return c.body(obj.body as unknown as ReadableStream, 200, {
        "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename="${release.slug}-${release.version}.mjolnir"`,
      });
    },
  );

  // ── Conflicts ───────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/releases/{id}/conflicts",
      tags: ["conflicts"],
      summary: "Published releases that claim any of the same chunks",
      description:
        "Two content releases conflict exactly when their IoStore containers " +
        "claim at least one chunk ID in common; whichever mounts later wins " +
        "those chunks. Computed from the uploaded containers, not from " +
        "author declarations.",
      request: { params: z.object({ id: z.string() }) },
      responses: {
        200: {
          description: "Conflicting releases, most-overlapping first.",
          content: { "application/json": { schema: ConflictListSchema } },
        },
        404: { description: "No such release.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { id } = c.req.valid("param");
      const exists = await c.env.DB.prepare(`SELECT id FROM mod_releases WHERE id = ?1`)
        .bind(id)
        .first();
      if (!exists) return c.json({ error: "not_found" }, 404);

      const rows = await c.env.DB.prepare(
        `SELECT rc2.release_id, m.slug AS mod_slug, m.name AS mod_name,
                r2.version, COUNT(*) AS shared_chunks
         FROM release_chunks rc1
         JOIN release_chunks rc2 ON rc2.chunk_id = rc1.chunk_id
                                AND rc2.release_id != rc1.release_id
         JOIN mod_releases r2 ON r2.id = rc2.release_id AND r2.status = 'published'
         JOIN mods m ON m.id = r2.mod_id AND m.status = 'published'
         WHERE rc1.release_id = ?1
         GROUP BY rc2.release_id
         ORDER BY shared_chunks DESC`,
      )
        .bind(id)
        .all();

      return c.json(
        {
          release_id: id,
          conflicts: rows.results.map((r) => ({
            release_id: r.release_id as string,
            mod_slug: r.mod_slug as string,
            mod_name: r.mod_name as string,
            version: r.version as string,
            shared_chunks: r.shared_chunks as number,
          })),
        },
        200,
      );
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/conflicts/check",
      tags: ["conflicts"],
      summary: "Conflict matrix for a set of releases",
      description:
        "The endpoint mod managers integrate against: given the releases a " +
        "profile intends to install, returns every pair that claims the same " +
        "chunk. An empty list means any load order works.",
      request: {
        body: {
          content: { "application/json": { schema: ConflictCheckRequestSchema } },
        },
      },
      responses: {
        200: {
          description: "All conflicting pairs.",
          content: { "application/json": { schema: ConflictCheckResponseSchema } },
        },
      },
    }),
    async (c) => {
      const { release_ids } = c.req.valid("json");
      const unique = [...new Set(release_ids)];
      const marks = unique.map((_, i) => `?${i + 1}`).join(", ");

      const rows = await c.env.DB.prepare(
        `SELECT a.release_id AS ra, b.release_id AS rb, a.chunk_id
         FROM release_chunks a
         JOIN release_chunks b ON b.chunk_id = a.chunk_id AND a.release_id < b.release_id
         WHERE a.release_id IN (${marks}) AND b.release_id IN (${marks})`,
      )
        .bind(...unique)
        .all();

      const pairs = new Map<string, { a: string; b: string; n: number; sample: string[] }>();
      for (const r of rows.results) {
        const key = `${r.ra}|${r.rb}`;
        let p = pairs.get(key);
        if (!p) {
          p = { a: r.ra as string, b: r.rb as string, n: 0, sample: [] };
          pairs.set(key, p);
        }
        p.n++;
        if (p.sample.length < 10) {
          p.sample.push(chunkIdToHex(new Uint8Array(r.chunk_id as ArrayBuffer)));
        }
      }

      return c.json(
        {
          pairs: [...pairs.values()].map((p) => ({
            a: p.a,
            b: p.b,
            shared_chunks: p.n,
            sample_chunk_ids: p.sample,
          })),
        },
        200,
      );
    },
  );
}
