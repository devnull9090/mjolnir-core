/**
 * Bench reports: frame times players measured on their own PCs
 * (docs/performance.md, migrations/0021_bench_reports.sql).
 *
 * MJOLNIRHud's bench holds the camera and times the map as it is against
 * the map without one thing (its foliage, the foliage's shadows, its wind)
 * or with one console variable changed. A player sends a run with /bench in
 * match chat; MJOLNIRLobby posts it with the launcher's key, under the
 * `lobbies:write` scope every launcher key already has (as match reports
 * do, migrations/0013).
 *
 * Reports are shown by GPU and map, never by account. What a report says is
 * the player's game's word: the page averages many and shows how many.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";

import type { ApiEnv } from "./bindings";
import { requireScoped } from "./auth";
import { ErrorSchema } from "./schemas";

type Db = ApiEnv["Bindings"]["DB"];

const MAP_CODE = z.string().regex(/^[A-Z0-9]{3}$/);
const BENCH_ID = z.string().regex(/^[0-9a-f]{16,64}$/);
const MS = z.number().positive().max(10000);
const PAGE = 25;
/** The quality levels a report carries (sg.<name>Quality). */
const SG_NAMES = [
  "ViewDistance", "AntiAliasing", "Shadow", "GlobalIllumination", "Reflection", "PostProcess",
  "Texture", "Effects", "Foliage", "Shading",
] as const;

const BenchResultSchema = z
  .object({
    name: z.string().trim().min(1).max(80).openapi({ example: "no foliage" }),
    ms: MS.openapi({ example: 6.42 }),
  })
  .openapi("BenchResult");

const BenchSettingsSchema = z
  .object({
    viewport_w: z.number().int().min(1).max(16384),
    viewport_h: z.number().int().min(1).max(16384),
    window_mode: z.enum(["fullscreen", "borderless", "windowed"]).nullable().optional(),
    vsync: z.boolean().default(false),
    fps_limit: z.number().min(0).max(1000).nullable().optional().openapi({ description: "0 or absent: none." }),
    screen_percentage: z.number().min(1).max(400).nullable().optional(),
    sg: z.partialRecord(z.enum(SG_NAMES), z.number().int().min(0).max(4)).default({}),
    gpu_name: z.string().trim().max(120).nullable().optional().openapi({ example: "NVIDIA GeForce RTX 5090" }),
    gpu_score: z.number().int().min(0).max(1000000).nullable().optional(),
    cpu: z.string().trim().max(120).nullable().optional(),
    cpu_threads: z.number().int().min(1).max(1024).nullable().optional(),
  })
  .openapi("BenchSettings");

const BenchReportSchema = z
  .object({
    bench_id: BENCH_ID,
    map_code: MAP_CODE,
    kind: z.enum(["foliage", "cvar"]),
    label: z.string().trim().min(1).max(120).openapi({ example: "foliage (245 meshes)" }),
    settings: BenchSettingsSchema,
    seconds_in_world: z.number().int().min(0).max(30 * 86400).nullable().optional(),
    base_ms: MS,
    base_min_ms: MS.nullable().optional(),
    base_max_ms: MS.nullable().optional(),
    results: z.array(BenchResultSchema).min(1).max(12),
    client_version: z.string().max(40).optional(),
  })
  .openapi("BenchReport");

const BenchSchema = z
  .object({
    id: z.string(),
    map_code: z.string(),
    kind: z.string(),
    label: z.string(),
    gpu_name: z.string().nullable(),
    gpu_score: z.number().nullable(),
    cpu: z.string().nullable(),
    cpu_threads: z.number().nullable(),
    viewport_w: z.number().nullable(),
    viewport_h: z.number().nullable(),
    window_mode: z.string().nullable(),
    vsync: z.boolean(),
    fps_limit: z.number().nullable(),
    screen_percentage: z.number().nullable(),
    sg: z.record(z.string(), z.number()),
    seconds_in_world: z.number().nullable(),
    base_ms: z.number(),
    base_min_ms: z.number().nullable(),
    base_max_ms: z.number().nullable(),
    results: z.array(BenchResultSchema),
    foliage_delta_ms: z.number().nullable(),
    client_version: z.string().nullable(),
    created_at: z.string(),
  })
  .openapi("Bench");

const BenchSummaryRowSchema = z
  .object({
    gpu_name: z.string().nullable(),
    map_code: z.string(),
    viewport_h: z.number().nullable(),
    foliage_quality: z.number().nullable(),
    reports: z.number(),
    base_ms: z.number().openapi({ description: "Mean of the reports' base frame times." }),
    foliage_delta_ms: z.number().nullable().openapi({ description: "Mean of what the foliage cost." }),
  })
  .openapi("BenchSummaryRow");

export type Bench = z.infer<typeof BenchSchema>;
export type BenchSummaryRow = z.infer<typeof BenchSummaryRowSchema>;
type BenchReport = z.infer<typeof BenchReportSchema>;
type Row = Record<string, unknown>;

/** The "no foliage" result less the base: what a foliage bench is for. */
export function foliageDelta(body: Pick<BenchReport, "kind" | "base_ms" | "results">): number | null {
  if (body.kind !== "foliage") return null;
  const r = body.results.find((x) => x.name === "no foliage");
  return r ? Math.round((r.ms - body.base_ms) * 1000) / 1000 : null;
}

function parse<T>(text: unknown, fallback: T): T {
  try {
    return typeof text === "string" ? (JSON.parse(text) as T) : fallback;
  } catch {
    return fallback;
  }
}

function toBench(r: Row): Bench {
  const n = (v: unknown) => (v === null || v === undefined ? null : Number(v));
  const s = (v: unknown) => (v === null || v === undefined ? null : String(v));
  return {
    id: String(r.id),
    map_code: String(r.map_code),
    kind: String(r.kind),
    label: String(r.label),
    gpu_name: s(r.gpu_name),
    gpu_score: n(r.gpu_score),
    cpu: s(r.cpu),
    cpu_threads: n(r.cpu_threads),
    viewport_w: n(r.viewport_w),
    viewport_h: n(r.viewport_h),
    window_mode: s(r.window_mode),
    vsync: Number(r.vsync) === 1,
    fps_limit: n(r.fps_limit),
    screen_percentage: n(r.screen_percentage),
    sg: parse<Record<string, number>>(r.sg_json, {}),
    seconds_in_world: n(r.seconds_in_world),
    base_ms: Number(r.base_ms),
    base_min_ms: n(r.base_min_ms),
    base_max_ms: n(r.base_max_ms),
    results: parse<{ name: string; ms: number }[]>(r.results_json, []),
    foliage_delta_ms: n(r.foliage_delta_ms),
    client_version: s(r.client_version),
    created_at: String(r.created_at),
  };
}

/** Recent reports, newest first, by map and GPU name (a substring). */
export async function listBenches(
  db: Db,
  q: { map?: string; gpu?: string; before?: string; limit?: number },
): Promise<{ benches: Bench[]; next: string | null }> {
  const where: string[] = [];
  const args: unknown[] = [];
  if (q.map) {
    args.push(q.map);
    where.push(`map_code = ?${args.length}`);
  }
  if (q.gpu) {
    args.push(`%${q.gpu.replace(/[%_]/g, "")}%`);
    where.push(`gpu_name LIKE ?${args.length}`);
  }
  if (q.before) {
    args.push(q.before);
    where.push(`created_at < ?${args.length}`);
  }
  const limit = q.limit ?? PAGE;
  args.push(limit + 1);
  const rows = await db
    .prepare(
      `SELECT * FROM bench_reports ${where.length ? "WHERE " + where.join(" AND ") : ""}
       ORDER BY created_at DESC LIMIT ?${args.length}`,
    )
    .bind(...args)
    .all<Row>();
  const list = (rows.results ?? []).map(toBench);
  const more = list.length > limit;
  const benches = list.slice(0, limit);
  return { benches, next: more ? benches[benches.length - 1].created_at : null };
}

/**
 * Foliage benches averaged by GPU, map, height drawn and foliage quality:
 * what a map costs on a card like yours. Only runs taken after the first
 * minutes in the world count, as the game warns (docs/performance.md).
 */
export async function benchSummary(db: Db, q: { map?: string }): Promise<BenchSummaryRow[]> {
  const rows = await db
    .prepare(
      `SELECT gpu_name, map_code, viewport_h, foliage_quality, COUNT(*) AS reports,
              AVG(base_ms) AS base_ms, AVG(foliage_delta_ms) AS foliage_delta_ms
       FROM bench_reports
       WHERE kind = 'foliage' AND (seconds_in_world IS NULL OR seconds_in_world >= 120)
         AND (?1 IS NULL OR map_code = ?1)
       GROUP BY gpu_name, map_code, viewport_h, foliage_quality
       ORDER BY map_code, base_ms DESC
       LIMIT 500`,
    )
    .bind(q.map ?? null)
    .all<Row>();
  return (rows.results ?? []).map((r) => ({
    gpu_name: r.gpu_name === null ? null : String(r.gpu_name),
    map_code: String(r.map_code),
    viewport_h: r.viewport_h === null ? null : Number(r.viewport_h),
    foliage_quality: r.foliage_quality === null ? null : Number(r.foliage_quality),
    reports: Number(r.reports),
    base_ms: Math.round(Number(r.base_ms) * 100) / 100,
    foliage_delta_ms: r.foliage_delta_ms === null ? null : Math.round(Number(r.foliage_delta_ms) * 100) / 100,
  }));
}

export function registerBenchRoutes(app: OpenAPIHono<ApiEnv>) {
  app.openapi(
    createRoute({
      method: "post",
      path: "/benches",
      tags: ["benches"],
      summary: "Send a bench the caller's game ran",
      description:
        "The game's /bench chat command times the map as it is against the map without its foliage, " +
        "the foliage's shadows and its wind, at a held camera, and sends the result with the settings it " +
        "ran at. `bench_id` is the game's own id for the run: sending it again returns the report made " +
        "the first time. Reports are shown by GPU and map, never by account. Needs the `lobbies:write` scope.",
      request: { body: { content: { "application/json": { schema: BenchReportSchema } } } },
      responses: {
        201: {
          description: "Recorded.",
          content: { "application/json": { schema: z.object({ id: z.string(), duplicate: z.boolean() }) } },
        },
        200: {
          description: "Sent before.",
          content: { "application/json": { schema: z.object({ id: z.string(), duplicate: z.boolean() }) } },
        },
        400: { description: "Invalid report.", content: { "application/json": { schema: ErrorSchema } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Missing scope.", content: { "application/json": { schema: ErrorSchema } } },
        429: { description: "Too many reports.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await requireScoped(c, "lobbies:write", "bench_report", 30);
      const body = c.req.valid("json");
      const db = c.env.DB;
      const existing = await db
        .prepare(`SELECT id FROM bench_reports WHERE user_id = ?1 AND bench_id = ?2`)
        .bind(auth.user.id, body.bench_id)
        .first<{ id: string }>();
      if (existing) return c.json({ id: existing.id, duplicate: true }, 200);
      const s = body.settings;
      const id = crypto.randomUUID();
      await db
        .prepare(
          `INSERT INTO bench_reports (id, user_id, bench_id, map_code, kind, label, gpu_name, gpu_score, cpu,
             cpu_threads, viewport_w, viewport_h, window_mode, vsync, fps_limit, screen_percentage, sg_json,
             foliage_quality, seconds_in_world, base_ms, base_min_ms, base_max_ms, results_json,
             foliage_delta_ms, client_version)
           VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19, ?20,
             ?21, ?22, ?23, ?24, ?25)`,
        )
        .bind(
          id, auth.user.id, body.bench_id, body.map_code, body.kind, body.label,
          s.gpu_name ?? null, s.gpu_score ?? null, s.cpu ?? null, s.cpu_threads ?? null,
          s.viewport_w, s.viewport_h, s.window_mode ?? null, s.vsync ? 1 : 0, s.fps_limit ?? null,
          s.screen_percentage ?? null, JSON.stringify(s.sg), s.sg.Foliage ?? null,
          body.seconds_in_world ?? null, body.base_ms, body.base_min_ms ?? null, body.base_max_ms ?? null,
          JSON.stringify(body.results), foliageDelta(body), body.client_version ?? null,
        )
        .run();
      return c.json({ id, duplicate: false }, 201);
    },
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/benches",
      tags: ["benches"],
      summary: "Recent bench reports, by map and GPU",
      request: {
        query: z.object({
          map: MAP_CODE.optional(),
          gpu: z.string().max(80).optional().openapi({ description: "Part of the GPU's name." }),
          before: z.string().max(32).optional().openapi({ description: "`next` from the previous page." }),
          limit: z.coerce.number().int().min(1).max(100).optional(),
        }),
      },
      responses: {
        200: {
          description: "Newest first.",
          content: {
            "application/json": {
              schema: z.object({ benches: z.array(BenchSchema), next: z.string().nullable() }),
            },
          },
        },
      },
    }),
    async (c) => c.json(await listBenches(c.env.DB, c.req.valid("query")), 200),
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/benches/summary",
      tags: ["benches"],
      summary: "Foliage benches averaged by GPU, map, resolution and foliage quality",
      request: { query: z.object({ map: MAP_CODE.optional() }) },
      responses: {
        200: {
          description: "One row per GPU, map, height drawn and foliage quality.",
          content: { "application/json": { schema: z.object({ rows: z.array(BenchSummaryRowSchema) }) } },
        },
      },
    }),
    async (c) => c.json({ rows: await benchSummary(c.env.DB, c.req.valid("query")) }, 200),
  );
}
