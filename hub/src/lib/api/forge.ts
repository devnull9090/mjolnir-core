/** Forge pack metadata is data, never an alternate executable upload path. */
import { createRoute, z, type OpenAPIHono } from "@hono/zod-openapi";
import type { ApiEnv } from "./bindings";
import { ErrorSchema } from "./schemas";

const BLOCK_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const PACK_ID = /^[a-z0-9][a-z0-9-]{1,63}$/;
const FORGE_VERSION = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/;

/** Exact identity shared with Rust SemVer and the native 96-byte field. */
export const ForgeReleaseVersionSchema = z.string().max(96).regex(FORGE_VERSION).refine((version) => {
  const parts = FORGE_VERSION.exec(version);
  if (!parts) return false;
  const max = BigInt("18446744073709551615");
  return parts.slice(1, 4).every((part) => BigInt(part) <= max)
    && (!parts[4] || parts[4].split(".").every((part) => !/^\d+$/.test(part) || part === "0" || part[0] !== "0"));
}, { message: "Forge versions require exact SemVer with u64 components and no leading-zero numeric prerelease identifiers." });

export const ForgeBlockSchema = z.object({
  id: z.string().regex(BLOCK_ID),
  name: z.string().trim().min(1).max(80),
  tag: z.string().min(1).max(200),
  category: z.string().regex(BLOCK_ID),
  dimensions_m: z.tuple([z.number().positive(), z.number().positive(), z.number().positive()]),
  snap_m: z.number().positive().optional(),
}).openapi("ForgeBlock");

export const ForgePackSchema = z.object({
  schema_version: z.literal(1),
  id: z.string().regex(PACK_ID),
  blocks: z.array(ForgeBlockSchema).min(1).max(256),
}).superRefine((pack, ctx) => {
  const ids = new Set<string>();
  for (const [index, block] of pack.blocks.entries()) {
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
