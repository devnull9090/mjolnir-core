/**
 * The mjolnir.json manifest carried inside every .mjolnir release archive.
 *
 * Documented for authors in docs/mjolnir_format.md; this schema is the
 * enforcement. schema_version lets the launcher refuse archives from a
 * future it does not understand.
 */
import { z } from "@hono/zod-openapi";

export const SEMVER = /^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/;

/** What a map's catalog listing is filtered by (migrations/0017_map_metadata.sql). */
export const MAP_SIZES = ["small", "medium", "large"] as const;
export const MAP_ORIGINS = ["classic", "custom_edition", "original"] as const;

export const ManifestSchema = z
  .object({
    schema_version: z.literal(1),
    name: z.string().min(1).max(120),
    version: z.string().regex(SEMVER, "semver, e.g. 1.2.0"),
    // Only content archives are community-uploadable; script/native releases
    // are built and signed by mjolnir-core CI, never uploaded here. A map is
    // content too (containers and JSON), with a `map` block saying which
    // (docs/map_distribution.md).
    type: z.enum(["content", "map"]),
    map: z
      .object({
        // The scenario codename: three characters, the game's own map key.
        code: z.string().regex(/^[A-Z0-9]{3}$/, "three characters, A-Z and 0-9"),
        title: z.string().min(1).max(80),
        modes: z.array(z.string().regex(/^[a-z_]{1,24}$/)).min(1).max(8),
        // Catalog metadata, all optional: a release that leaves one out
        // keeps whatever the listing already says.
        size: z.enum(MAP_SIZES).optional(),
        players: z
          .object({
            min: z.number().int().min(1).max(16),
            max: z.number().int().min(1).max(16),
          })
          .refine((p) => p.min <= p.max, { message: "min must not exceed max" })
          .optional(),
        vehicles: z.boolean().optional(),
        // `classic` marks the converted stock maps and is a moderator's to
        // give, so an author can only say where their own map came from.
        origin: z
          .enum(["custom_edition", "original"], {
            error: "custom_edition or original (classic is set by moderators)",
          })
          .optional(),
      })
      .optional(),
    summary: z.string().max(300).optional(),
    compat: z
      .object({
        min_build: z.string().optional(),
        max_build: z.string().optional(),
      })
      .optional(),
    deps: z
      .array(
        z.object({
          slug: z.string().min(1),
          range: z.string().default("*"),
        }),
      )
      .default([]),
  })
  .refine((m) => (m.type === "map") === (m.map !== undefined), {
    message: "a map archive carries a map block, and only a map archive does",
    path: ["map"],
  })
  .openapi("MjolnirManifest");

export type Manifest = z.infer<typeof ManifestSchema>;
