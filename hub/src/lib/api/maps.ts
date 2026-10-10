/**
 * The maps catalog: the official classic Halo CE maps and community maps,
 * each with its latest published release (docs/multiplayer_release_plan.md,
 * item 4). A map is a content mod with a map_listings row
 * (migrations/0012_maps_and_lobbies.sql); the launcher installs it like any
 * content mod and then registers it with the game.
 *
 * The listing is also what players search and filter community maps by
 * (migrations/0017_map_metadata.sql). Its unfiltered form is a contract:
 * launcher 0.12 and the game's MULTIPLAYER menu ask for `/maps` or
 * `/maps?official=1` and expect every map, official first, then by title.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";

import type { ApiEnv } from "./bindings";
import { requireScoped } from "./auth";
import { requireModerator } from "./account";
import { audit } from "./moderation";
import { MAP_ORIGINS, MAP_SIZES } from "./manifest";
import { ErrorSchema, avatarUrl, mediaUrl } from "./schemas";

const MapSchema = z
  .object({
    code: z.string(),
    title: z.string(),
    modes: z.array(z.string()),
    official: z.boolean(),
    slug: z.string(),
    summary: z.string().nullable(),
    owner: z.string(),
    /** Discord CDN avatar of the owner, when they have one. */
    owner_avatar: z.string().nullable(),
    download_count: z.number(),
    rating_count: z.number(),
    rating_mean: z.number().nullable(),
    /** The first approved screenshot in the map's gallery, for its card. */
    cover_url: z.string().nullable(),
    size: z.enum(MAP_SIZES).nullable(),
    players_min: z.number().int().nullable(),
    players_max: z.number().int().nullable(),
    vehicles: z.boolean().nullable(),
    origin: z.enum(MAP_ORIGINS).nullable().openapi({
      description:
        "`classic` for the converted stock Halo CE maps, `custom_edition` for a converted " +
        "Halo Custom Edition map, `original` for a map made for Campaign Evolved.",
    }),
    /** When the map's mod was created, for "newest". */
    created_at: z.string(),
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
type MapListing = z.infer<typeof MapSchema>;

function toMap(r: MapRow): MapListing {
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
    owner_avatar: avatarUrl(r.owner_discord_id as string, r.owner_discord_avatar as string | null),
    download_count: (r.download_count as number) ?? 0,
    rating_count: (r.rating_count as number) ?? 0,
    rating_mean: (r.rating_mean as number) ?? null,
    cover_url: r.cover_id ? mediaUrl(r.cover_id as string) : null,
    size: (r.size as MapListing["size"]) ?? null,
    players_min: (r.players_min as number) ?? null,
    players_max: (r.players_max as number) ?? null,
    vehicles: r.vehicles === null || r.vehicles === undefined ? null : r.vehicles === 1,
    origin: (r.origin as MapListing["origin"]) ?? null,
    created_at: r.created_at as string,
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
  SELECT ml.code, ml.title, ml.modes, ml.official, ml.size, ml.players_min, ml.players_max,
         ml.vehicles, ml.origin, m.slug, m.summary, m.download_count, m.rating_count,
         m.rating_mean, m.created_at, COALESCE(u.display_name, u.discord_username) AS owner,
         u.discord_id AS owner_discord_id, u.discord_avatar AS owner_discord_avatar,
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

/**
 * Explicit orders. Each ends on the code so an offset cursor pages through
 * a stable sequence; with no `sort` the listing keeps its original order.
 */
const MAP_SORTS = {
  newest: "m.created_at DESC, ml.code",
  downloads: "m.download_count DESC, ml.code",
  rating: "COALESCE(m.rating_wilson, -1) DESC, ml.code",
  title: "ml.title COLLATE NOCASE, ml.code",
} as const;

/** The unfiltered listing's page: every map the catalog is likely to hold. */
const MAX_MAPS = 500;

type Db = ApiEnv["Bindings"]["DB"];

export interface MapListQuery {
  official?: boolean;
  mode?: string;
  /** Title, code or summary contains this. */
  q?: string;
  size?: (typeof MAP_SIZES)[number];
  vehicles?: boolean;
  origin?: (typeof MAP_ORIGINS)[number];
  /** Suits this many players: inside the map's range, or the range unknown. */
  players?: number;
  sort?: keyof typeof MAP_SORTS;
  limit?: number;
  /** `next_cursor` from the previous page. */
  cursor?: string;
}

/** LIKE wildcards in a search are literal characters, not patterns. */
function likeContains(q: string): string {
  return `%${q.replace(/[\\%_]/g, (ch) => `\\${ch}`)}%`;
}

/**
 * Published maps, filtered, in pages; the API's and the pages'. With no
 * `sort`, official first then by title, as every caller before the filters
 * expected.
 */
export async function searchMaps(
  db: Db,
  query: MapListQuery = {},
): Promise<{ maps: MapListing[]; next_cursor: string | null }> {
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
  if (query.q) {
    binds.push(likeContains(query.q));
    const n = binds.length;
    clauses.push(
      `(ml.title LIKE ?${n} ESCAPE '\\' OR ml.code LIKE ?${n} ESCAPE '\\' OR m.summary LIKE ?${n} ESCAPE '\\')`,
    );
  }
  if (query.size) {
    binds.push(query.size);
    clauses.push(`ml.size = ?${binds.length}`);
  }
  if (query.vehicles !== undefined) {
    binds.push(query.vehicles ? 1 : 0);
    clauses.push(`ml.vehicles = ?${binds.length}`);
  }
  if (query.origin) {
    binds.push(query.origin);
    clauses.push(`ml.origin = ?${binds.length}`);
  }
  if (query.players !== undefined) {
    // A map that never said how many it suits is not hidden by the filter.
    binds.push(query.players);
    const n = binds.length;
    clauses.push(
      `(ml.players_min IS NULL OR ml.players_min <= ?${n}) AND (ml.players_max IS NULL OR ml.players_max >= ?${n})`,
    );
  }

  const order = query.sort ? MAP_SORTS[query.sort] : "ml.official DESC, ml.title, ml.code";
  const limit = query.limit ?? MAX_MAPS;
  const offset = query.cursor ? Number.parseInt(query.cursor, 10) || 0 : 0;
  binds.push(limit + 1, offset);
  const rows = await db
    .prepare(
      `${MAP_SELECT} ${clauses.length ? `WHERE ${clauses.join(" AND ")}` : ""}
       ORDER BY ${order} LIMIT ?${binds.length - 1} OFFSET ?${binds.length}`,
    )
    .bind(...binds)
    .all();
  const more = rows.results.length > limit;
  return {
    maps: rows.results.slice(0, limit).map(toMap),
    next_cursor: more ? String(offset + limit) : null,
  };
}

/** Every published map matching the filters, official first then by title. */
export async function listMaps(db: Db, query: MapListQuery = {}): Promise<MapListing[]> {
  return (await searchMaps(db, query)).maps;
}

const MapMetadataSchema = z
  .object({
    code: z.string(),
    size: z.enum(MAP_SIZES).nullable(),
    players_min: z.number().int().nullable(),
    players_max: z.number().int().nullable(),
    vehicles: z.boolean().nullable(),
    origin: z.enum(MAP_ORIGINS).nullable(),
  })
  .openapi("MapMetadata");

const MapMetadataPatchSchema = z
  .object({
    size: z.enum(MAP_SIZES).nullable().optional(),
    players_min: z.number().int().min(1).max(16).nullable().optional(),
    players_max: z.number().int().min(1).max(16).nullable().optional(),
    vehicles: z.boolean().nullable().optional(),
    origin: z.enum(MAP_ORIGINS).nullable().optional(),
  })
  .openapi("MapMetadataPatch", {
    description: "Fields to change; an absent field is kept and null clears one.",
  });

const PATCH_FIELDS = ["size", "players_min", "players_max", "vehicles", "origin"] as const;

const BOOL = z.enum(["0", "1"]);

export function registerMapRoutes(app: OpenAPIHono<ApiEnv>) {
  app.openapi(
    createRoute({
      method: "get",
      path: "/maps",
      tags: ["maps"],
      summary: "Published maps: every one by default, or searched, filtered and paged",
      description:
        "With no `sort` or `limit`, every published map (up to 500), the official classics " +
        "first and then by title; the launcher and the game's menu rely on that form. " +
        "Filters narrow it, and a map that never declared a filtered field passes the " +
        "players filter but not the others.",
      request: {
        query: z.object({
          official: BOOL.optional(),
          mode: z.string().regex(/^[a-z_]{1,24}$/).optional(),
          q: z.string().trim().max(80).optional().openapi({
            description: "Search in title, code and summary.",
          }),
          size: z.enum(MAP_SIZES).optional(),
          vehicles: BOOL.optional(),
          origin: z.enum(MAP_ORIGINS).optional(),
          players: z.coerce.number().int().min(1).max(16).optional().openapi({
            description:
              "Maps that suit this many players: within the map's range, or with no range declared.",
          }),
          sort: z.enum(["newest", "downloads", "rating", "title"]).optional().openapi({
            description: "Absent: official first, then by title.",
          }),
          limit: z.coerce.number().int().min(1).max(100).optional().openapi({
            description: "Page size, 1-100. Absent: up to 500 maps in one page.",
          }),
          cursor: z.string().regex(/^\d{1,6}$/).optional().openapi({
            description: "Opaque pagination cursor from a previous response's `next_cursor`.",
          }),
        }),
      },
      responses: {
        200: {
          description: "Maps, official first and then by title unless `sort` says otherwise.",
          content: {
            "application/json": {
              schema: z
                .object({
                  maps: z.array(MapSchema),
                  next_cursor: z.string().nullable().openapi({
                    description: "Pass as `cursor` to fetch the next page; null when exhausted.",
                  }),
                })
                .openapi("MapList"),
            },
          },
        },
      },
    }),
    async (c) => {
      const query = c.req.valid("query");
      const page = await searchMaps(c.env.DB, {
        official: query.official === undefined ? undefined : query.official === "1",
        mode: query.mode,
        q: query.q || undefined,
        size: query.size,
        vehicles: query.vehicles === undefined ? undefined : query.vehicles === "1",
        origin: query.origin,
        players: query.players,
        sort: query.sort,
        limit: query.limit,
        cursor: query.cursor,
      });
      return c.json(page, 200);
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
      method: "patch",
      path: "/maps/{code}",
      tags: ["maps"],
      summary: "Set a map's catalog metadata (its authors, or moderators)",
      description:
        "Size, player range, vehicles and origin, as the catalog filters by them. The " +
        "mod's owner and authors may set them; only moderators may set or change " +
        "`origin: classic`, which marks the converted stock maps.",
      request: {
        params: z.object({ code: z.string().regex(/^[A-Za-z0-9]{3}$/) }),
        body: { content: { "application/json": { schema: MapMetadataPatchSchema } } },
      },
      responses: {
        200: { description: "The map's metadata as it now stands.", content: { "application/json": { schema: MapMetadataSchema } } },
        400: { description: "Nothing to change, or a minimum above the maximum.", content: { "application/json": { schema: ErrorSchema } } },
        401: { description: "Not signed in.", content: { "application/json": { schema: ErrorSchema } } },
        403: { description: "Not an author of this map, or `classic` without being a moderator.", content: { "application/json": { schema: ErrorSchema } } },
        404: { description: "No map has this code.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const { user } = await requireScoped(c, "mods:write", "map_metadata", 60);
      const code = c.req.valid("param").code.toUpperCase();
      const patch = c.req.valid("json");
      const fields = PATCH_FIELDS.filter((f) => patch[f] !== undefined);
      if (fields.length === 0) {
        return c.json({ error: "validation", message: "Nothing to change." }, 400);
      }

      const row = await c.env.DB.prepare(
        `SELECT ml.mod_id, ml.size, ml.players_min, ml.players_max, ml.vehicles, ml.origin,
                m.owner_id,
                EXISTS (SELECT 1 FROM mod_authors a
                        WHERE a.mod_id = ml.mod_id AND a.user_id = ?2
                          AND a.role IN ('owner', 'author')) AS is_author
         FROM map_listings ml JOIN mods m ON m.id = ml.mod_id WHERE ml.code = ?1`,
      )
        .bind(code, user.id)
        .first<{
          mod_id: string;
          size: string | null;
          players_min: number | null;
          players_max: number | null;
          vehicles: number | null;
          origin: string | null;
          owner_id: string;
          is_author: number;
        }>();
      if (!row) return c.json({ error: "not_found" }, 404);

      const moderator = user.role !== "user";
      if (!moderator && row.owner_id !== user.id && !row.is_author) {
        return c.json({ error: "forbidden" }, 403);
      }
      // `classic` is the official catalog's mark: an author can neither
      // claim it nor take it off a map a moderator gave it to.
      if (!moderator && patch.origin !== undefined && (patch.origin === "classic" || row.origin === "classic")) {
        return c.json(
          { error: "forbidden", message: "Only moderators set or change the classic origin." },
          403,
        );
      }

      const min = patch.players_min !== undefined ? patch.players_min : row.players_min;
      const max = patch.players_max !== undefined ? patch.players_max : row.players_max;
      if (min !== null && max !== null && min > max) {
        return c.json(
          { error: "validation", message: "players_min must not exceed players_max." },
          400,
        );
      }

      const values = fields.map((f) =>
        f === "vehicles" ? (patch.vehicles === null ? null : patch.vehicles ? 1 : 0) : patch[f],
      );
      await c.env.DB.prepare(
        `UPDATE map_listings SET ${fields.map((f, i) => `${f} = ?${i + 2}`).join(", ")},
           updated_at = datetime('now')
         WHERE code = ?1`,
      )
        .bind(code, ...values)
        .run();
      await audit(
        c,
        user.id,
        "map_metadata",
        "map",
        code,
        JSON.stringify(Object.fromEntries(fields.map((f) => [f, patch[f]]))),
      );

      const merged = { ...row, ...Object.fromEntries(fields.map((f, i) => [f, values[i]])) };
      return c.json(
        {
          code,
          size: (merged.size as z.infer<typeof MapMetadataSchema>["size"]) ?? null,
          players_min: (merged.players_min as number | null) ?? null,
          players_max: (merged.players_max as number | null) ?? null,
          vehicles: merged.vehicles === null ? null : merged.vehicles === 1,
          origin: (merged.origin as z.infer<typeof MapMetadataSchema>["origin"]) ?? null,
        },
        200,
      );
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
