/**
 * The mjolnir.json manifest carried inside every .mjolnir release archive.
 *
 * Documented for authors in docs/mjolnir_format.md; this schema is the
 * enforcement. schema_version lets the launcher refuse archives from a
 * future it does not understand.
 */
import { z } from "@hono/zod-openapi";

export const SEMVER = /^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/;

export const ManifestSchema = z
  .object({
    schema_version: z.literal(1),
    name: z.string().min(1).max(120),
    version: z.string().regex(SEMVER, "semver, e.g. 1.2.0"),
    // Only content archives are community-uploadable; script/native releases
    // are built and signed by mjolnir-core CI, never uploaded here.
    type: z.literal("content"),
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
  .openapi("MjolnirManifest");

export type Manifest = z.infer<typeof ManifestSchema>;
