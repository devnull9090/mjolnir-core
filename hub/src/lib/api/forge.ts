/** Forge pack metadata is data, never an alternate executable upload path. */
import { createRoute, z, type OpenAPIHono } from "@hono/zod-openapi";
import type { ApiEnv } from "./bindings";
import { ErrorSchema } from "./schemas";

const BLOCK_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const PACK_ID = /^[a-z0-9][a-z0-9-]{1,63}$/;
const FORGE_VERSION = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/;

/** Entry kinds the whole chain (Hub, packer, launcher, bake, Forge) handles.
 * Each names the object tag class behind `objects\mjolnir\forge\<pack>\<id>`.
 * The rest are reserved: a pack using one is refused until it is supported,
 * so no launcher ever installs a weapon as a building block. */
export const FORGE_KINDS: ReadonlySet<string> = new Set(["block"]);
export const FORGE_RESERVED_KINDS: ReadonlySet<string> = new Set(["scenery", "weapon", "vehicle", "equipment", "biped"]);
/** Features a pack may require beyond schema 1. None exist yet; a launcher
 * refuses a pack that requires one it does not know. */
export const FORGE_FEATURES: ReadonlySet<string> = new Set();

/** Exact identity shared with Rust SemVer and the native 96-byte field. */
export const ForgeReleaseVersionSchema = z.string().max(96).regex(FORGE_VERSION).refine((version) => {
  const parts = FORGE_VERSION.exec(version);
  if (!parts) return false;
  const max = BigInt("18446744073709551615");
  return parts.slice(1, 4).every((part) => BigInt(part) <= max)
    && (!parts[4] || parts[4].split(".").every((part) => !/^\d+$/.test(part) || part === "0" || part[0] !== "0"));
}, { message: "Forge versions require exact SemVer with u64 components and no leading-zero numeric prerelease identifiers." });

export const ForgeLightSchema = z.object({
  offset_m: z.tuple([z.number().min(-100).max(100), z.number().min(-100).max(100), z.number().min(-100).max(100)]),
  color_rgb: z.tuple([z.number().min(0).max(1), z.number().min(0).max(1), z.number().min(0).max(1)]),
  intensity_cd: z.number().positive().max(10_000),
  radius_m: z.number().positive().max(100),
}).strict().openapi("ForgeLight");

export const ForgeLiftSchema = z.object({
  offset_m: z.tuple([z.number().min(-100).max(100), z.number().min(-100).max(100), z.number().min(-100).max(100)]),
  size_m: z.tuple([z.number().min(0.1).max(100), z.number().min(0.1).max(100), z.number().min(0.1).max(100)]),
  direction: z.tuple([z.number().min(-1).max(1), z.number().min(-1).max(1), z.number().min(-1).max(1)])
    .refine((v) => Math.abs(v.reduce((n, x) => n + x * x, 0) - 1) <= 0.001, "Direction must be a unit vector."),
  acceleration_m_s2: z.number().min(0.1).max(100),
  max_speed_m_s: z.number().min(0.1).max(30),
  negates_gravity: z.boolean(),
}).strict().openapi("ForgeLift");

export const ForgeDoorSchema = z.object({
  travel_m: z.number().positive().max(16),
  speed_m_s: z.number().positive().max(8),
  trigger_size_m: z.tuple([z.number().positive().max(32), z.number().positive().max(32), z.number().positive().max(32)]),
  hold_open_s: z.number().min(0).max(10),
}).strict().openapi("ForgeDoor");

export const ForgeSurfaceSchema = z.object({
  slot: z.number().int().min(0).max(15),
  profile: z.enum(["glass_cyan", "teleporter_green"]),
}).strict().openapi("ForgeSurface");

export const ForgeBlockSchema = z.object({
  id: z.string().regex(BLOCK_ID),
  /** Absent means "block". See FORGE_KINDS. */
  kind: z.string().regex(BLOCK_ID).optional(),
  name: z.string().trim().min(1).max(80),
  tag: z.string().min(1).max(200),
  category: z.string().regex(BLOCK_ID),
  dimensions_m: z.tuple([z.number().positive(), z.number().positive(), z.number().positive()]),
  snap_m: z.number().positive().optional(),
  light: ForgeLightSchema.nullish(),
  lift: ForgeLiftSchema.nullish(),
  door: ForgeDoorSchema.nullish(),
  surfaces: z.array(ForgeSurfaceSchema).max(16).refine((s) => new Set(s.map((x) => x.slot)).size === s.length,
    "Surface slots must be unique.").nullish(),
}).openapi("ForgeBlock");

export const ForgePackSchema = z.object({
  schema_version: z.literal(1),
  id: z.string().regex(PACK_ID),
  /** Declared here so publishing keeps a future pack's gate instead of
   * stripping it as an unknown key. */
  requires: z.array(z.string().regex(BLOCK_ID)).max(32).optional(),
  blocks: z.array(ForgeBlockSchema).min(1).max(256),
}).superRefine((pack, ctx) => {
  for (const [index, feature] of (pack.requires ?? []).entries()) {
    if (!FORGE_FEATURES.has(feature)) {
      ctx.addIssue({ code: "custom", path: ["requires", index], message: `MJOLNIR does not support the Forge pack feature "${feature}" yet.` });
    }
  }
  const ids = new Set<string>();
  for (const [index, block] of pack.blocks.entries()) {
    if (block.kind !== undefined && !FORGE_KINDS.has(block.kind)) {
      const message = FORGE_RESERVED_KINDS.has(block.kind)
        ? `Forge packs cannot carry ${block.kind} entries yet; that kind is reserved for a later release.`
        : `Unknown Forge entry kind "${block.kind}".`;
      ctx.addIssue({ code: "custom", path: ["blocks", index, "kind"], message });
    }
    if (block.door && block.dimensions_m.some((n) => n > 64)) {
      ctx.addIssue({ code: "custom", path: ["blocks", index, "dimensions_m"], message: "Door panels must fit within 64 metres on each axis." });
    }
    if (ids.has(block.id)) {
      ctx.addIssue({ code: "custom", path: ["blocks", index, "id"], message: "Block IDs must be unique within a pack." });
    }
    ids.add(block.id);
    const expected = `objects\\mjolnir\\forge\\${pack.id}\\${block.id}`;
    if (block.tag !== expected) {
      ctx.addIssue({ code: "custom", path: ["blocks", index, "tag"], message: `Block tag must be ${expected}.` });
    }
  }
}).openapi("ForgePack");

export type ForgePack = z.infer<typeof ForgePackSchema>;

type Core = { core: [bigint, bigint, bigint]; pre: string[] };

function core(version: string): Core | null {
  const parts = FORGE_VERSION.exec(version);
  if (!parts) return null;
  return { core: [BigInt(parts[1]), BigInt(parts[2]), BigInt(parts[3])], pre: parts[4] ? parts[4].split(".") : [] };
}

/** SemVer precedence: negative when a < b. */
export function compareForgeVersions(a: string, b: string): number {
  const x = core(a), y = core(b);
  if (!x || !y) throw new Error("not a Forge release version");
  for (let i = 0; i < 3; i++) if (x.core[i] !== y.core[i]) return x.core[i] < y.core[i] ? -1 : 1;
  if (!x.pre.length || !y.pre.length) return y.pre.length - x.pre.length;
  for (let i = 0; i < Math.min(x.pre.length, y.pre.length); i++) {
    const p = x.pre[i], q = y.pre[i];
    if (p === q) continue;
    const pn = /^\d+$/.test(p), qn = /^\d+$/.test(q);
    if (pn && qn) return BigInt(p) < BigInt(q) ? -1 : 1;
    if (pn !== qn) return pn ? -1 : 1;
    return p < q ? -1 : 1;
  }
  return x.pre.length - y.pre.length;
}

/** The caret line maps and saved layouts accept: the same major version, the
 * same minor while the major is 0, and the same patch while both are 0 (as
 * the launcher's Rust semver and native Forge read `^`). Releases in one line
 * must keep every entry of the earlier ones (forgeUpdateIssues). */
export function sameForgeLine(a: string, b: string): boolean {
  const x = core(a), y = core(b);
  if (!x || !y || x.core[0] !== y.core[0]) return false;
  if (x.core[0] > BigInt(0)) return true;
  return x.core[1] === y.core[1] && (x.core[1] > BigInt(0) || x.core[2] === y.core[2]);
}

/** What a release in the same line breaks for maps and layouts built with
 * `previous`: an entry removed, or changed in kind, size or snap. */
export function forgeUpdateIssues(previous: ForgePack, next: ForgePack): string[] {
  const now = new Map(next.blocks.map((b) => [b.id, b]));
  const issues: string[] = [];
  for (const old of previous.blocks) {
    const entry = now.get(old.id);
    if (!entry) issues.push(`removes ${old.id}`);
    else if ((entry.kind ?? "block") !== (old.kind ?? "block")) issues.push(`changes the kind of ${old.id}`);
    else if (entry.dimensions_m.some((n, i) => n !== old.dimensions_m[i]) || entry.snap_m !== old.snap_m) {
      issues.push(`changes the size or snap of ${old.id}`);
    }
  }
  return issues;
}

export const ReleaseForgePackSchema = z.object({
  release_id: z.string(),
  slug: z.string(),
  version: ForgeReleaseVersionSchema,
  sha256: z.string().nullable(),
  forge_pack: ForgePackSchema,
  deps: z.array(z.object({ slug: z.string(), range: z.string() })),
}).openapi("ReleaseForgePack");

/** Public metadata only for published releases of published mods. */
export function registerForgeRoutes(app: OpenAPIHono<ApiEnv>) {
  app.openapi(createRoute({
    method: "get",
    path: "/releases/{id}/forge-pack",
    tags: ["forge"],
    summary: "The models and dependencies in a Forge pack release",
    request: { params: z.object({ id: z.string() }) },
    responses: {
      200: { description: "The validated inventory, with stable pack and block IDs.", content: { "application/json": { schema: ReleaseForgePackSchema } } },
      404: { description: "No published Forge pack release.", content: { "application/json": { schema: ErrorSchema } } },
    },
  }), async (c) => {
    const { id } = c.req.valid("param");
    const row = await c.env.DB.prepare(
      `SELECT r.id, m.slug, r.version, r.sha256, r.forge_pack_json
       FROM mod_releases r JOIN mods m ON m.id = r.mod_id
       WHERE r.id = ?1 AND r.status = 'published' AND m.status = 'published'
         AND r.forge_pack_json IS NOT NULL`,
    ).bind(id).first<{ id: string; slug: string; version: string; sha256: string | null; forge_pack_json: string }>();
    if (!row) return c.json({ error: "not_found" }, 404);
    const deps = await c.env.DB.prepare(
      `SELECT dep_slug AS slug, semver_range AS range FROM release_deps WHERE release_id = ?1 ORDER BY dep_slug`,
    ).bind(id).all<{ slug: string; range: string }>();
    return c.json({
      release_id: row.id, slug: row.slug, version: row.version, sha256: row.sha256,
      forge_pack: ForgePackSchema.parse(JSON.parse(row.forge_pack_json)), deps: deps.results,
    }, 200);
  });
}
