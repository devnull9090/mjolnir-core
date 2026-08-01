/**
 * Zod schemas for every API payload.
 *
 * One schema per shape, used three ways at once: request validation,
 * response typing, and the published OpenAPI document. The spec cannot
 * drift from the implementation because it is generated from these.
 */
import { z } from "@hono/zod-openapi";

// ── Common ────────────────────────────────────────────────────────────

export const ErrorSchema = z
  .object({
    error: z.string().openapi({ example: "not_found" }),
    message: z.string().optional().openapi({ example: "No mod with that slug." }),
  })
  .openapi("Error");

export const HealthSchema = z
  .object({
    status: z.literal("ok"),
    service: z.literal("mjolnir-hub"),
    timestamp: z.string(),
  })
  .openapi("Health");

/** Opaque keyset cursor; clients must treat it as a token, not parse it. */
export const CursorQuerySchema = z.object({
  cursor: z.string().optional().openapi({
    description: "Opaque pagination cursor from a previous response.",
  }),
  limit: z.coerce.number().int().min(1).max(100).default(20).openapi({
    description: "Page size, 1-100.",
  }),
});

// ── Users ─────────────────────────────────────────────────────────────

export const UserSchema = z
  .object({
    id: z.string().openapi({ example: "0198c2f4-6c1e-7c33-a1b0-9a1c2d3e4f56" }),
    username: z.string().openapi({ example: "devnull9090" }),
    display_name: z.string().nullable(),
    avatar_url: z.string().nullable().openapi({
      description: "Discord CDN avatar, when the user has one.",
    }),
    role: z.enum(["user", "moderator", "admin"]),
    created_at: z.string(),
  })
  .openapi("User");

// ── Mods ──────────────────────────────────────────────────────────────

export const ModTypeSchema = z.enum(["content", "script", "native"]).openapi({
  description:
    "Trust tier. `content` mods are inert game data and open to community upload. " +
    "`script` (UE4SS Lua) and `native` (DLL) mods can execute code, so they ship " +
    "exclusively from the mjolnir-core repository's reviewed, signed CI releases.",
});

export const ModSchema = z
  .object({
    id: z.string(),
    slug: z.string().openapi({ example: "mjolnir-flycam" }),
    name: z.string().openapi({ example: "MJOLNIRFlyCam" }),
    summary: z.string().nullable(),
    type: ModTypeSchema,
    category: z.string().openapi({ example: "camera" }),
    license: z.string().nullable(),
    nsfw: z.boolean(),
    download_count: z.number().int(),
    rating_count: z.number().int(),
    rating_mean: z.number().nullable(),
    author: z.string().openapi({
      description: "Owner's display name (or Discord username).",
    }),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .openapi("Mod");

export const ModDetailSchema = ModSchema.extend({
  description_md: z.string().nullable().openapi({
    description: "Full mod page body, Markdown.",
  }),
}).openapi("ModDetail");

export const ModListSchema = z
  .object({
    mods: z.array(ModSchema),
    next_cursor: z.string().nullable().openapi({
      description: "Pass as `cursor` to fetch the next page; null when exhausted.",
    }),
  })
  .openapi("ModList");

export const ModListQuerySchema = CursorQuerySchema.extend({
  q: z.string().optional().openapi({ description: "Search in name and summary." }),
  category: z.string().optional(),
  type: z.enum(["content", "script", "native"]).optional(),
  sort: z.enum(["newest", "downloads", "rating"]).default("newest"),
});

// ── Releases ──────────────────────────────────────────────────────────

export const ReleaseSchema = z
  .object({
    id: z.string(),
    mod_id: z.string(),
    version: z.string().openapi({ example: "1.2.0" }),
    channel: z.enum(["stable", "beta"]),
    changelog_md: z.string().nullable(),
    file_size: z.number().int().nullable(),
    sha256: z.string().nullable().openapi({
      description: "Hash of the release archive; verify after download.",
    }),
    build_min: z.string().nullable().openapi({
      description: "Oldest game build this release is declared compatible with.",
    }),
    build_max: z.string().nullable(),
    download_count: z.number().int(),
    created_at: z.string(),
  })
  .openapi("Release");

export const ReleaseListSchema = z
  .object({ releases: z.array(ReleaseSchema) })
  .openapi("ReleaseList");

// ── Row mappers (D1 → API shapes) ─────────────────────────────────────

/* eslint-disable @typescript-eslint/no-explicit-any */

export function modFromRow(r: any): z.infer<typeof ModSchema> {
  return {
    id: r.id,
    slug: r.slug,
    name: r.name,
    summary: r.summary ?? null,
    type: r.type,
    category: r.category,
    license: r.license ?? null,
    nsfw: !!r.nsfw,
    download_count: r.download_count ?? 0,
    rating_count: r.rating_count ?? 0,
    rating_mean: r.rating_mean ?? null,
    author: r.author ?? "unknown",
    created_at: r.created_at,
    updated_at: r.updated_at,
  };
}

export function releaseFromRow(r: any): z.infer<typeof ReleaseSchema> {
  return {
    id: r.id,
    mod_id: r.mod_id,
    version: r.version,
    channel: r.channel,
    changelog_md: r.changelog_md ?? null,
    file_size: r.file_size ?? null,
    sha256: r.sha256 ?? null,
    build_min: r.build_min ?? null,
    build_max: r.build_max ?? null,
    download_count: r.download_count ?? 0,
    created_at: r.created_at,
  };
}
