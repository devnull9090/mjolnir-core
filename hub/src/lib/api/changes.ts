/**
 * The changes.json a .mjolnir archive may carry: the author's recipe,
 * resolved against their installation at export time, declared for players.
 *
 * This is what the mod page renders as "what this mod does". It is a
 * declaration, not a proof — the containers are the bytes that ship, and
 * the scanner-verified chunk count is shown beside the declared list so a
 * mod claiming one tweak while overriding half the game is visibly odd.
 * Documented in docs/mjolnir_format.md; written by the tag editor
 * (apps/tag-editor/src-tauri/src/modpack.rs), which is why the caps are
 * generous but firm — a machine-written file has no excuse to hit them.
 */
import { z } from "@hono/zod-openapi";

/** Raw size cap on changes.json; anything larger fails the scan. */
export const MAX_CHANGES_BYTES = 512 * 1024;

const DeclaredFieldSchema = z
  .object({
    field: z.string().min(1).max(512),
    before: z.string().max(4096).nullish().openapi({
      description: "The shipped value at export time, when it resolved.",
    }),
    value: z.string().max(4096),
  })
  .openapi("DeclaredField");

const DeclaredTagSchema = z
  .object({
    group: z.string().min(1).max(64).openapi({ example: "weapon" }),
    tag: z.string().min(1).max(512).openapi({ example: "objects/weapons/pistol/pistol" }),
    fields: z.array(DeclaredFieldSchema).max(500),
  })
  .openapi("DeclaredTag");

export const DeclaredChangesSchema = z
  .object({
    schema_version: z.literal(1),
    tags: z.array(DeclaredTagSchema).max(1000),
    textures: z
      .array(
        z.object({
          path: z.string().min(1).max(512),
          bytes: z.number().int().nonnegative().optional(),
        }),
      )
      .max(500)
      .default([]),
    scripts: z
      .array(z.object({ group: z.string().min(1).max(64), tag: z.string().min(1).max(512) }))
      .max(500)
      .default([]),
  })
  .openapi("DeclaredChanges");

export type DeclaredChanges = z.infer<typeof DeclaredChangesSchema>;
