/**
 * Crash reports from the launcher (docs/crash_reports.md, migrations/0019).
 *
 * When the game crashes, the launcher asks the player, and on a yes files
 * the crash here and uploads a small bundle: the redacted crash context, a
 * slim dump holding only the thread stacks, the UE4SS log and the installed
 * mods. Crashes are grouped by `signature`, which the launcher derives from
 * the build, the crash type and where the game crashed. For a signature
 * and build the hub holds fewer than `DUMPS_WANTED` full dumps of, it asks
 * for the full dump too, and the launcher asks the player a second time.
 *
 * Any signed-in key may file a report: every launcher key qualifies, so the
 * sign-ins players already have work. The files sit in MODS_BUCKET under
 * crashes/<id>/, which nothing serves directly; admins download them here.
 * Reports and their files go after `RETENTION_DAYS`, swept as new reports
 * arrive.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { Context } from "hono";
import { HTTPException } from "hono/http-exception";

import type { ApiEnv } from "./bindings";
import { authenticate, rateLimit, sha256Hex } from "./auth";
import { requireAdmin } from "./admin";
import { MAX_ARCHIVE_BYTES } from "./scan";
import { ErrorSchema } from "./schemas";

type Ctx = Context<ApiEnv>;

/** The bundle is typically about 330 KB; the slim dump compresses to almost nothing. */
export const MAX_BUNDLE_BYTES = 8 * 1024 * 1024;
/** A zipped full dump is about a third of the 170-odd MB dump: ~52 MB. */
export const MAX_DUMP_BYTES = MAX_ARCHIVE_BYTES;
/** Full dumps kept per signature and build before the hub stops asking. */
export const DUMPS_WANTED = 3;
export const RETENTION_DAYS = 90;

const Err = (description: string) => ({
  description,
  content: { "application/json": { schema: ErrorSchema } },
});

/**
 * Any identity will do, with an hourly budget per key. Not `requireScoped`:
 * there is no crash scope, and asking for one would turn away every launcher
 * signed in before it existed.
 */
async function requireSignedIn(c: Ctx, bucket: string, limit: number) {
  const auth = await authenticate(c);
  if (!auth) throw new HTTPException(401, { res: c.json({ error: "unauthenticated" }, 401) });
  if (auth.user.role !== "admin" && !(await rateLimit(c, auth.subject, bucket, limit))) {
    throw new HTTPException(429, { res: c.json({ error: "rate_limited" }, 429) });
  }
  return auth;
}

const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;
/** Free text from the crash, cut rather than refused: a long assert is still a crash. */
const clipped = (max: number) =>
  z
    .string()
    .transform((s) => s.slice(0, max))
    .nullish();

const CrashCreateSchema = z
  .object({
    crash_id: z
      .string()
      .regex(/^UECC-[A-Za-z0-9_-]{1,120}$/)
      .openapi({ description: "UE's crash folder name.", example: "UECC-Windows-A13FF88D473CDE7854D7F18E02EFDA14_0000" }),
    signature: z.string().regex(/^[0-9a-f]{16}$/).openapi({ example: "ccfab15f14e59877" }),
    build_version: z.string().min(1).max(200),
    crash_type: z.string().min(1).max(40).openapi({ example: "Crash" }),
    fault: z.string().min(1).max(400).openapi({ example: "UE4SS.dll+0x2580d7 (0xc0000005)" }),
    error_message: clipped(2000),
    crashed_at: z.string().regex(ISO_UTC).openapi({ example: "2026-10-17T04:28:33Z" }),
    seconds_since_start: z.number().int().min(0).nullish(),
    mode: clipped(40),
    map: clipped(40),
    role: clipped(40),
    launcher_version: clipped(40),
    bundle_bytes: z.number().int().min(1).max(MAX_BUNDLE_BYTES),
    bundle_sha256: z.string().regex(/^[0-9a-f]{64}$/),
    dump_bytes: z.number().int().min(0).nullish(),
  })
  .openapi("CrashReportCreate");

const UploadSchema = z
  .object({
    method: z.literal("PUT"),
    url: z.string().openapi({ description: "A path under /api/v1 (send the key) or an absolute presigned URL (do not)." }),
    max_bytes: z.number().int(),
  })
  .openapi("CrashUpload");

const CrashCreatedSchema = z
  .object({
    id: z.string(),
    bundle_upload: UploadSchema.optional().openapi({ description: "Absent when the bundle is already stored." }),
    wants_dump: z.boolean(),
    dump_upload: UploadSchema.optional(),
  })
  .openapi("CrashReportCreated");

const StoredSchema = z.object({ sha256: z.string(), bytes: z.number().int() }).openapi("CrashFileStored");

const CrashSignatureSchema = z
  .object({
    signature: z.string(),
    build_version: z.string(),
    crash_type: z.string(),
    fault: z.string(),
    reports: z.number().int(),
    players: z.number().int(),
    dumps: z.number().int(),
    maps: z.array(z.string()),
    first_seen: z.string(),
    last_seen: z.string(),
  })
  .openapi("CrashSignature");

const CrashReportSchema = z
  .object({
    id: z.string(),
    crash_id: z.string(),
    user: z.object({ id: z.string(), name: z.string() }),
    crash_type: z.string(),
    fault: z.string(),
    error_message: z.string().nullable(),
    crashed_at: z.string(),
    seconds_since_start: z.number().int().nullable(),
    mode: z.string().nullable(),
    map: z.string().nullable(),
    role: z.string().nullable(),
    launcher_version: z.string().nullable(),
    bundle_bytes: z.number().int().nullable(),
    dump_bytes: z.number().int().nullable(),
    dump_zip_bytes: z.number().int().nullable(),
    has_bundle: z.boolean(),
    has_dump: z.boolean(),
    dump_wanted: z.boolean(),
    created_at: z.string(),
  })
  .openapi("CrashReport");

function created(id: string, needsBundle: boolean, wantsDump: boolean) {
  return {
    id,
    ...(needsBundle
      ? { bundle_upload: { method: "PUT" as const, url: `/crashes/${id}/bundle`, max_bytes: MAX_BUNDLE_BYTES } }
      : {}),
    wants_dump: wantsDump,
    ...(wantsDump
      ? { dump_upload: { method: "PUT" as const, url: `/crashes/${id}/dump`, max_bytes: MAX_DUMP_BYTES } }
      : {}),
  };
}

/** Deletes up to a batch of expired reports and their files. Off the request path. */
async function sweep(c: Ctx) {
  const old = await c.env.DB.prepare(
    `SELECT id, bundle_key, dump_key FROM crash_reports
     WHERE created_at < datetime('now', ?1) LIMIT 50`,
  )
    .bind(`-${RETENTION_DAYS} days`)
    .all<{ id: string; bundle_key: string | null; dump_key: string | null }>();
  if (!old.results.length) return;
  const keys = old.results.flatMap((r) => [r.bundle_key, r.dump_key]).filter((k): k is string => !!k);
  if (keys.length) await c.env.MODS_BUCKET.delete(keys);
  const ids = old.results.map((r) => r.id);
  await c.env.DB.prepare(`DELETE FROM crash_reports WHERE id IN (${ids.map((_, i) => `?${i + 1}`).join(", ")})`)
    .bind(...ids)
    .run();
}

function isZip(bytes: Uint8Array): boolean {
  return bytes.length >= 4 && bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 0x03 && bytes[3] === 0x04;
}

/** The request body, refused past `max` before and after reading it. */
async function readUpload(c: Ctx, max: number): Promise<Uint8Array> {
  const declared = Number(c.req.header("content-length") ?? 0);
  if (declared > max) {
    throw new HTTPException(413, { res: c.json({ error: "too_large", message: `At most ${max} bytes.` }, 413) });
  }
  const bytes = new Uint8Array(await c.req.arrayBuffer());
  if (bytes.length > max) {
    throw new HTTPException(413, { res: c.json({ error: "too_large", message: `At most ${max} bytes.` }, 413) });
  }
  if (!isZip(bytes)) {
    throw new HTTPException(400, { res: c.json({ error: "not_zip", message: "Expected a zip." }, 400) });
  }
  return bytes;
}

interface OwnedReport {
  user_id: string;
  crash_id: string;
  bundle_sha256: string;
  dump_wanted: number;
  dump_key: string | null;
}

async function ownedReport(c: Ctx, id: string, userId: string): Promise<OwnedReport> {
  const row = await c.env.DB.prepare(
    `SELECT user_id, crash_id, bundle_sha256, dump_wanted, dump_key FROM crash_reports WHERE id = ?1`,
  )
    .bind(id)
    .first<OwnedReport>();
  // Someone else's report reads as missing, not forbidden: ids are not for probing.
  if (!row || row.user_id !== userId) {
    throw new HTTPException(404, { res: c.json({ error: "not_found" }, 404) });
  }
  return row;
}

function reportFromRow(r: Record<string, unknown>) {
  return {
    id: r.id as string,
    crash_id: r.crash_id as string,
    user: {
      id: r.user_id as string,
      name: ((r.display_name as string | null) ?? (r.discord_username as string)) || "unknown",
    },
    crash_type: r.crash_type as string,
    fault: r.fault as string,
    error_message: (r.error_message as string | null) ?? null,
    crashed_at: r.crashed_at as string,
    seconds_since_start: (r.seconds_since_start as number | null) ?? null,
    mode: (r.mode as string | null) ?? null,
    map: (r.map as string | null) ?? null,
    role: (r.role as string | null) ?? null,
    launcher_version: (r.launcher_version as string | null) ?? null,
    bundle_bytes: r.bundle_key ? ((r.bundle_bytes as number | null) ?? null) : null,
    dump_bytes: (r.dump_bytes as number | null) ?? null,
    dump_zip_bytes: (r.dump_zip_bytes as number | null) ?? null,
    has_bundle: !!r.bundle_key,
    has_dump: !!r.dump_key,
    dump_wanted: !!r.dump_wanted,
    created_at: r.created_at as string,
  };
}

export function registerCrashRoutes(app: OpenAPIHono<ApiEnv>) {
  // ── Filing a crash ──────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "post",
      path: "/crashes",
      tags: ["crashes"],
      summary: "File a crash report",
      description:
        "The launcher's summary of one game crash. Upload the bundle where `bundle_upload` says; " +
        "when `wants_dump` is true and the player agrees, the zipped full dump goes where " +
        "`dump_upload` says. Filing the same `crash_id` again answers 200 with the report already " +
        "made. Any signed-in key.",
      request: {
        body: { content: { "application/json": { schema: CrashCreateSchema } } },
      },
      responses: {
        200: { description: "Filed before.", content: { "application/json": { schema: CrashCreatedSchema } } },
        201: { description: "Filed.", content: { "application/json": { schema: CrashCreatedSchema } } },
        400: Err("Invalid report."),
        401: Err("Not signed in."),
        429: Err("Slow down."),
      },
    }),
    async (c) => {
      const auth = await requireSignedIn(c, "crash_report", 20);
      const b = c.req.valid("json");
      c.executionCtx.waitUntil(sweep(c).catch(() => {}));

      const existing = () =>
        c.env.DB.prepare(
          `SELECT id, bundle_key, dump_wanted, dump_key FROM crash_reports WHERE user_id = ?1 AND crash_id = ?2`,
        )
          .bind(auth.user.id, b.crash_id)
          .first<{ id: string; bundle_key: string | null; dump_wanted: number; dump_key: string | null }>();
      const again = async () => {
        const row = await existing();
        return row ? c.json(created(row.id, !row.bundle_key, !!row.dump_wanted && !row.dump_key), 200) : null;
      };
      const before = await again();
      if (before) return before;

      const held = await c.env.DB.prepare(
        `SELECT COUNT(*) AS n FROM crash_reports
         WHERE signature = ?1 AND build_version = ?2 AND dump_key IS NOT NULL`,
      )
        .bind(b.signature, b.build_version)
        .first<{ n: number }>();
      const wantsDump = (b.dump_bytes ?? 0) > 0 && (held?.n ?? 0) < DUMPS_WANTED;

      const id = crypto.randomUUID();
      try {
        await c.env.DB.prepare(
          `INSERT INTO crash_reports (id, user_id, crash_id, signature, build_version, crash_type, fault,
             error_message, crashed_at, seconds_since_start, mode, map, role, launcher_version,
             bundle_sha256, bundle_bytes, dump_bytes, dump_wanted)
           VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18)`,
        )
          .bind(
            id,
            auth.user.id,
            b.crash_id,
            b.signature,
            b.build_version,
            b.crash_type,
            b.fault,
            b.error_message ?? null,
            b.crashed_at,
            b.seconds_since_start ?? null,
            b.mode ?? null,
            b.map ?? null,
            b.role ?? null,
            b.launcher_version ?? null,
            b.bundle_sha256,
            b.bundle_bytes,
            b.dump_bytes ?? null,
            wantsDump ? 1 : 0,
          )
          .run();
      } catch (e) {
        // Two sends of one crash at once: the second gets the first's report.
        if (String(e).includes("UNIQUE")) {
          const raced = await again();
          if (raced) return raced;
        }
        throw e;
      }
      return c.json(created(id, true, wantsDump), 201);
    },
  );

  // ── Its files ───────────────────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "put",
      path: "/crashes/{id}/bundle",
      tags: ["crashes"],
      summary: "Upload a crash report's bundle",
      description: `The zip the report announced: its SHA-256 must match \`bundle_sha256\`. At most ${MAX_BUNDLE_BYTES / (1024 * 1024)} MiB.`,
      request: {
        params: z.object({ id: z.string() }),
        body: {
          content: { "application/zip": { schema: z.any().openapi({ type: "string", format: "binary" }) } },
        },
      },
      responses: {
        200: { description: "Stored.", content: { "application/json": { schema: StoredSchema } } },
        400: Err("Not a zip, or not the one announced."),
        401: Err("Not signed in."),
        404: Err("No such report of yours."),
        413: Err("Too large."),
        429: Err("Slow down."),
      },
    }),
    async (c) => {
      const auth = await requireSignedIn(c, "crash_upload", 40);
      const { id } = c.req.valid("param");
      const report = await ownedReport(c, id, auth.user.id);
      const bytes = await readUpload(c, MAX_BUNDLE_BYTES);
      const sha256 = await sha256Hex(bytes);
      if (sha256 !== report.bundle_sha256) {
        return c.json({ error: "hash_mismatch", message: "This is not the bundle the report announced." }, 400);
      }
      const key = `crashes/${id}/bundle.zip`;
      await c.env.MODS_BUCKET.put(key, bytes as unknown as ArrayBuffer, {
        httpMetadata: { contentType: "application/zip" },
      });
      await c.env.DB.prepare(`UPDATE crash_reports SET bundle_key = ?2, bundle_bytes = ?3 WHERE id = ?1`)
        .bind(id, key, bytes.length)
        .run();
      return c.json({ sha256, bytes: bytes.length }, 200);
    },
  );

  app.openapi(
    createRoute({
      method: "put",
      path: "/crashes/{id}/dump",
      tags: ["crashes"],
      summary: "Upload a crash report's full dump",
      description:
        `The zipped UEMinidump.dmp, only for a report the hub asked (\`wants_dump\`). At most ` +
        `${MAX_DUMP_BYTES / (1024 * 1024)} MiB.`,
      request: {
        params: z.object({ id: z.string() }),
        body: {
          content: { "application/zip": { schema: z.any().openapi({ type: "string", format: "binary" }) } },
        },
      },
      responses: {
        200: { description: "Stored.", content: { "application/json": { schema: StoredSchema } } },
        400: Err("Not a zip."),
        401: Err("Not signed in."),
        404: Err("No such report of yours."),
        409: Err("The hub did not ask for this dump, or has it."),
        413: Err("Too large."),
        429: Err("Slow down."),
      },
    }),
    async (c) => {
      const auth = await requireSignedIn(c, "crash_dump", 6);
      const { id } = c.req.valid("param");
      const report = await ownedReport(c, id, auth.user.id);
      if (!report.dump_wanted) {
        return c.json({ error: "not_wanted", message: "The hub did not ask for this crash's dump." }, 409);
      }
      if (report.dump_key) return c.json({ error: "duplicate", message: "The hub has this dump." }, 409);
      const bytes = await readUpload(c, MAX_DUMP_BYTES);
      const sha256 = await sha256Hex(bytes);
      const key = `crashes/${id}/dump.zip`;
      await c.env.MODS_BUCKET.put(key, bytes as unknown as ArrayBuffer, {
        httpMetadata: { contentType: "application/zip" },
      });
      await c.env.DB.prepare(`UPDATE crash_reports SET dump_key = ?2, dump_zip_bytes = ?3 WHERE id = ?1`)
        .bind(id, key, bytes.length)
        .run();
      return c.json({ sha256, bytes: bytes.length }, 200);
    },
  );

  // ── Reading them (admins) ───────────────────────────────────────────

  app.openapi(
    createRoute({
      method: "get",
      path: "/admin/crashes",
      tags: ["admin"],
      summary: "Crash signatures (admin)",
      description:
        "Crash reports grouped by signature and build, most recently seen first: how many, from " +
        "how many players, how many full dumps, on which maps.",
      request: {
        query: z.object({
          build: z.string().max(200).optional(),
          limit: z.coerce.number().int().min(1).max(500).default(200),
        }),
      },
      responses: {
        200: {
          description: "Signatures.",
          content: { "application/json": { schema: z.object({ signatures: z.array(CrashSignatureSchema) }) } },
        },
        401: Err("Not signed in."),
        403: Err("Admins only."),
      },
    }),
    async (c) => {
      await requireAdmin(c);
      const { build, limit } = c.req.valid("query");
      const rows = await c.env.DB.prepare(
        `SELECT signature, build_version,
                MAX(crash_type) AS crash_type, MAX(fault) AS fault,
                COUNT(*) AS reports, COUNT(DISTINCT user_id) AS players,
                SUM(dump_key IS NOT NULL) AS dumps,
                GROUP_CONCAT(DISTINCT map) AS maps,
                MIN(crashed_at) AS first_seen, MAX(crashed_at) AS last_seen
         FROM crash_reports
         ${build ? "WHERE build_version = ?2" : ""}
         GROUP BY signature, build_version
         ORDER BY MAX(created_at) DESC
         LIMIT ?1`,
      )
        .bind(...(build ? [limit, build] : [limit]))
        .all<Record<string, unknown>>();
      return c.json(
        {
          signatures: rows.results.map((r) => ({
            signature: r.signature as string,
            build_version: r.build_version as string,
            crash_type: r.crash_type as string,
            fault: r.fault as string,
            reports: r.reports as number,
            players: r.players as number,
            dumps: (r.dumps as number | null) ?? 0,
            maps: ((r.maps as string | null) ?? "").split(",").filter(Boolean),
            first_seen: r.first_seen as string,
            last_seen: r.last_seen as string,
          })),
        },
        200,
      );
    },
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/admin/crashes/{signature}",
      tags: ["admin"],
      summary: "The reports under one crash signature (admin)",
      request: {
        params: z.object({ signature: z.string().regex(/^[0-9a-f]{16}$/) }),
        query: z.object({ build: z.string().max(200).optional() }),
      },
      responses: {
        200: {
          description: "Reports, newest first.",
          content: { "application/json": { schema: z.object({ reports: z.array(CrashReportSchema) }) } },
        },
        401: Err("Not signed in."),
        403: Err("Admins only."),
      },
    }),
    async (c) => {
      await requireAdmin(c);
      const { signature } = c.req.valid("param");
      const { build } = c.req.valid("query");
      const rows = await c.env.DB.prepare(
        `SELECT r.*, u.display_name, u.discord_username
         FROM crash_reports r JOIN users u ON u.id = r.user_id
         WHERE r.signature = ?1 ${build ? "AND r.build_version = ?2" : ""}
         ORDER BY r.created_at DESC LIMIT 200`,
      )
        .bind(...(build ? [signature, build] : [signature]))
        .all<Record<string, unknown>>();
      return c.json({ reports: rows.results.map(reportFromRow) }, 200);
    },
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/admin/crash-reports/{id}/{file}",
      tags: ["admin"],
      summary: "Download a crash report's bundle or full dump (admin)",
      request: { params: z.object({ id: z.string(), file: z.enum(["bundle", "dump"]) }) },
      responses: {
        200: { description: "The zip." },
        401: Err("Not signed in."),
        403: Err("Admins only."),
        404: Err("No such file."),
      },
    }),
    async (c) => {
      await requireAdmin(c);
      const { id, file } = c.req.valid("param");
      const row = await c.env.DB.prepare(`SELECT crash_id, bundle_key, dump_key FROM crash_reports WHERE id = ?1`)
        .bind(id)
        .first<{ crash_id: string; bundle_key: string | null; dump_key: string | null }>();
      const key = file === "bundle" ? row?.bundle_key : row?.dump_key;
      if (!row || !key) return c.json({ error: "not_found" }, 404);
      const obj = await c.env.MODS_BUCKET.get(key);
      if (!obj) return c.json({ error: "not_found" }, 404);
      return c.body(obj.body as unknown as ReadableStream, 200, {
        "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename="${file}-${row.crash_id}.zip"`,
        "Cache-Control": "private, no-store",
      });
    },
  );
}
