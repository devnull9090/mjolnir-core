/**
 * The maps catalog: the official classic Halo CE maps and community maps,
 * each with its latest published release (docs/multiplayer_release_plan.md,
 * item 4). A map is a content mod with a map_listings row
 * (migrations/0012_maps_and_lobbies.sql); the launcher installs it like any
 * content mod and then registers it with the game.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";

import type { ApiEnv } from "./bindings";
import { requireModerator } from "./account";
import { audit } from "./moderation";
import { mediaUrl } from "./community";
import { ErrorSchema } from "./schemas";

const MapSchema = z
  .object({
    code: z.string(),
    title: z.string(),
    modes: z.array(z.string()),
    official: z.boolean(),
    slug: z.string(),
    summary: z.string().nullable(),
    owner: z.string(),
    download_count: z.number(),
    rating_mean: z.number().nullable(),
    /** The first approved screenshot in the map's gallery, for its card. */
    cover_url: z.string().nullable(),
    /** The latest published release, the one to install. */
    release: z
      .object({
        id: z.string(),
        version: z.string(),
        file_size: z.number().nullable(),
        sha256: z.string().nullable(),
        created_at: z.string(),
      })
      .nullable(),
  })
  .openapi("MapListing");

type MapRow = Record<string, unknown>;

function toMap(r: MapRow): z.infer<typeof MapSchema> {
  let modes: string[] = [];
  try {
    modes = JSON.parse(r.modes as string) as string[];
  } catch {
    modes = [];
  }
  return {
    code: r.code as string,
    title: r.title as string,
    modes,
    official: (r.official as number) === 1,
    slug: r.slug as string,
    summary: (r.summary as string) ?? null,
    owner: r.owner as string,
    download_count: (r.download_count as number) ?? 0,
    rating_mean: (r.rating_mean as number) ?? null,
    cover_url: r.cover_id ? mediaUrl(r.cover_id as string) : null,
    release: r.release_id
      ? {
          id: r.release_id as string,
          version: r.release_version as string,
          file_size: (r.release_size as number) ?? null,
          sha256: (r.release_sha256 as string) ?? null,
          created_at: r.release_created_at as string,
        }
      : null,
  };
}

/** Published maps, each joined to its newest published release. */
const MAP_SELECT = `
  SELECT ml.code, ml.title, ml.modes, ml.official, m.slug, m.summary, m.download_count,
         m.rating_mean, COALESCE(u.display_name, u.discord_username) AS owner,
         r.id AS release_id, r.version AS release_version, r.file_size AS release_size,
         r.sha256 AS release_sha256, r.created_at AS release_created_at,
         (SELECT md.id FROM media md
          WHERE md.mod_id = m.id AND md.status = 'approved' AND md.kind <> 'video'
          ORDER BY md.position, md.created_at LIMIT 1) AS cover_id
  FROM map_listings ml
  JOIN mods m ON m.id = ml.mod_id AND m.status = 'published'
  JOIN users u ON u.id = m.owner_id
  LEFT JOIN mod_releases r ON r.id = (
    SELECT r2.id FROM mod_releases r2
    WHERE r2.mod_id = m.id AND r2.status = 'published'
    ORDER BY r2.created_at DESC LIMIT 1)`;

type Db = ApiEnv["Bindings"]["DB"];

/** Published maps, official first then by title; the API's and the page's. */
export async function listMaps(
  db: Db,
  query: { official?: boolean; mode?: string } = {},
): Promise<z.infer<typeof MapSchema>[]> {
  const clauses: string[] = [];
  const binds: unknown[] = [];
  if (query.official !== undefined) {
    binds.push(query.official ? 1 : 0);
    clauses.push(`ml.official = ?${binds.length}`);
  }
  if (query.mode) {
    binds.push(`%"${query.mode}"%`);
    clauses.push(`ml.modes LIKE ?${binds.length}`);
  }
  const rows = await db
    .prepare(
      `${MAP_SELECT} ${clauses.length ? `WHERE ${clauses.join(" AND ")}` : ""}
       ORDER BY ml.official DESC, ml.title LIMIT 500`,
    )
    .bind(...binds)
    .all();
  return rows.results.map(toMap);
}

export function registerMapRoutes(app: OpenAPIHono<ApiEnv>) {
  app.openapi(
    createRoute({
      method: "get",
      path: "/maps",
      tags: ["maps"],
      summary: "Every published map: the official classics first, then community maps",
      request: {
        query: z.object({
          official: z.enum(["0", "1"]).optional(),
          mode: z.string().regex(/^[a-z_]{1,24}$/).optional(),
        }),
      },
      responses: {
        200: {
          description: "Maps, official first, then by title.",
          content: { "application/json": { schema: z.object({ maps: z.array(MapSchema) }) } },
        },
      },
    }),
    async (c) => {
      const { official, mode } = c.req.valid("query");
      const maps = await listMaps(c.env.DB, {
        official: official === undefined ? undefined : official === "1",
        mode,
      });
      return c.json({ maps }, 200);
    },
  );

  app.openapi(
    createRoute({
      method: "put",
      path: "/maps/{code}/official",
      tags: ["maps", "moderation"],
      summary: "Mark a map as one of the official classics, or not (moderators)",
      request: {
        params: z.object({ code: z.string().regex(/^[A-Za-z0-9]{3}$/) }),
        body: {
          content: {
            "application/json": { schema: z.object({ official: z.boolean() }).openapi("MapOfficial") },
          },
        },
      },
      responses: {
        200: { description: "Set.", content: { "application/json": { schema: z.object({ ok: z.boolean() }) } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Moderators only.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No map has this code.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const auth = await requireModerator(c);
      const { code } = c.req.valid("param");
      const { official } = c.req.valid("json");
      const res = await c.env.DB.prepare(
        `UPDATE map_listings SET official = ?2, updated_at = datetime('now') WHERE code = ?1`,
      )
        .bind(code.toUpperCase(), official ? 1 : 0)
        .run();
      if (!res.meta.changes) return c.json({ error: "not_found" }, 404);
      await audit(c, auth.user.id, official ? "map_official" : "map_unofficial", "map", code.toUpperCase());
      return c.json({ ok: true }, 200);
    },
  );

  app.openapi(
    createRoute({
      method: "get",
      path: "/maps/{code}",
      tags: ["maps"],
      summary: "One map by its codename",
      request: { params: z.object({ code: z.string().regex(/^[A-Za-z0-9]{3}$/) }) },
      responses: {
        200: { description: "The map.", content: { "application/json": { schema: MapSchema } } },
        404: { description: "No published map has this code.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { code } = c.req.valid("param");
      const row = await c.env.DB.prepare(`${MAP_SELECT} WHERE ml.code = ?1`)
        .bind(code.toUpperCase())
        .first<MapRow>();
      if (!row) return c.json({ error: "not_found" }, 404);
      return c.json(toMap(row), 200);
    },
  );
}
