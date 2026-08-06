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
    view_count: z.number().int(),
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
    signature: z.string().nullable().openapi({
      description:
        "Base64 Ed25519 signature over the lowercase hex `sha256`, made with " +
        "the platform release key (keys/mod-signing.pub). Present on signed " +
        "script/native releases; null for community content uploads, whose " +
        "integrity rests on `sha256` plus the upload scan. Clients that know " +
        "the key must reject a release whose signature is present and wrong.",
    }),
    build_min: z.string().nullable().openapi({
      description: "Oldest game build this release is declared compatible with.",
    }),
    build_max: z.string().nullable(),
    download_count: z.number().int(),
    created_at: z.string(),
    published_by: z.string().nullable().openapi({
      description: "Account that created this release; null for releases predating attribution.",
    }),
    published_by_username: z.string().nullable(),
    signer_fingerprint: z.string().nullable().openapi({
      description:
        "Fingerprint of the author signing key whose signature verified at publish. " +
        "Distinct from `signature`, which is the platform key over the archive hash; " +
        "this one is the author's own key over the archive contents " +
        "(docs/mod_signing_design.md).",
    }),
    signer_key_revoked: z.boolean().openapi({
      description: "True when the author's signing key has been revoked since publish.",
    }),
  })
  .openapi("Release");

export const ReleaseListSchema = z
  .object({ releases: z.array(ReleaseSchema) })
  .openapi("ReleaseList");

// ── Publishing ────────────────────────────────────────────────────────

export const SLUG = /^[a-z0-9][a-z0-9-]{1,63}$/;

export const ModCreateSchema = z
  .object({
    slug: z.string().regex(SLUG, "lowercase letters, digits and dashes").openapi({
      example: "my-texture-pack",
    }),
    name: z.string().min(1).max(120),
    summary: z.string().max(300).optional(),
    description_md: z.string().max(65536).optional(),
    category: z.string().max(40).default("gameplay"),
    license: z.string().max(60).optional(),
    nsfw: z.boolean().default(false),
  })
  .openapi("ModCreate");

export const ReleaseCreateSchema = z
  .object({
    version: z.string().regex(/^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/, "semver"),
    channel: z.enum(["stable", "beta"]).default("stable"),
    changelog_md: z.string().max(65536).optional(),
    build_min: z.string().max(80).optional(),
    build_max: z.string().max(80).optional(),
  })
  .openapi("ReleaseCreate");

export const FindingSchema = z
  .object({
    level: z.enum(["error", "warning"]),
    code: z.string().openapi({ example: "forbidden_file" }),
    message: z.string(),
  })
  .openapi("ScanFinding");

export const ReleaseStatusSchema = z
  .object({
    id: z.string(),
    mod_id: z.string(),
    version: z.string(),
    status: z.enum(["pending", "scanning", "published", "rejected", "yanked"]),
    sha256: z.string().nullable(),
    signature: z.string().nullable(),
    file_size: z.number().int().nullable(),
    chunk_count: z.number().int().openapi({
      description: "IoStore chunks this release claims, once scanned.",
    }),
    findings: z.array(FindingSchema),
    created_at: z.string(),
    published_by: z.string().nullable().openapi({
      description: "Account that created this release; null for releases predating attribution.",
    }),
    published_by_username: z.string().nullable(),
    signer_fingerprint: z.string().nullable().openapi({
      description: "Fingerprint of the author key whose signature verified at publish, if any.",
    }),
    signer_key_revoked: z.boolean().openapi({
      description: "True when the signing key has been revoked since this release published.",
    }),
  })
  .openapi("ReleaseStatus");

// ── Conflicts ─────────────────────────────────────────────────────────

export const ConflictEntrySchema = z
  .object({
    release_id: z.string(),
    mod_slug: z.string(),
    mod_name: z.string(),
    version: z.string(),
    shared_chunks: z.number().int().openapi({
      description: "How many IoStore chunk IDs both releases claim.",
    }),
  })
  .openapi("ConflictEntry");

export const ConflictListSchema = z
  .object({
    release_id: z.string(),
    conflicts: z.array(ConflictEntrySchema),
  })
  .openapi("ConflictList");

export const ConflictCheckRequestSchema = z
  .object({
    release_ids: z.array(z.string()).min(2).max(50).openapi({
      description: "Releases a client intends to install together.",
    }),
  })
  .openapi("ConflictCheckRequest");

export const ConflictPairSchema = z
  .object({
    a: z.string(),
    b: z.string(),
    shared_chunks: z.number().int(),
    sample_chunk_ids: z.array(z.string()).openapi({
      description: "Up to 10 shared chunk IDs, hex-encoded 12-byte identifiers.",
    }),
  })
  .openapi("ConflictPair");

export const ConflictCheckResponseSchema = z
  .object({
    pairs: z.array(ConflictPairSchema).openapi({
      description:
        "Every conflicting pair among the requested releases. Empty means " +
        "the set installs cleanly in any order.",
    }),
  })
  .openapi("ConflictCheckResponse");

// ── Media ─────────────────────────────────────────────────────────────

export const MediaSchema = z
  .object({
    id: z.string(),
    mod_id: z.string(),
    url: z.string().openapi({ description: "Where the file is served from." }),
    kind: z.enum(["screenshot", "thumbnail", "video"]),
    alt_text: z.string().openapi({
      description: "Author-provided description; required on upload.",
    }),
    status: z.enum(["pending", "approved", "rejected"]).openapi({
      description:
        "Moderation state. Listings only include non-approved items for " +
        "their own uploader; everyone else sees approved media only.",
    }),
    view_count: z.number().int(),
    uploader: z.string().nullable().openapi({
      description: "Display name of whoever submitted this item.",
    }),
    uploader_id: z.string().openapi({
      description:
        "The submitter's user id, so a client can tell whose items carry " +
        "controls without matching on display names.",
    }),
    width: z.number().int().nullable(),
    height: z.number().int().nullable(),
    position: z.number().int(),
    created_at: z.string(),
  })
  .openapi("Media");

export const MediaListSchema = z.object({ media: z.array(MediaSchema) }).openapi("MediaList");

// ── Ratings ───────────────────────────────────────────────────────────

export const RatingPutSchema = z
  .object({
    score: z.number().int().min(1).max(5),
    review_md: z.string().max(8192).optional(),
  })
  .openapi("RatingPut");

export const RatingSummarySchema = z
  .object({
    count: z.number().int(),
    mean: z.number().nullable(),
    distribution: z.record(z.string(), z.number().int()).openapi({
      description: "Score → number of ratings, keys '1'..'5'.",
    }),
    mine: z.number().int().nullable().openapi({
      description: "The caller's own score, when signed in and rated.",
    }),
    reviews: z.array(
      z.object({
        author: z.string(),
        score: z.number().int(),
        review_md: z.string(),
        created_at: z.string(),
      }),
    ),
  })
  .openapi("RatingSummary");

// ── Comments ──────────────────────────────────────────────────────────

export const CommentCreateSchema = z
  .object({
    body_md: z.string().min(1).max(8192),
    parent_id: z.string().optional(),
  })
  .openapi("CommentCreate");

export const CommentSchema = z
  .object({
    id: z.string(),
    mod_id: z.string(),
    parent_id: z.string().nullable(),
    author: z.string().nullable().openapi({
      description: "Null when the comment was deleted.",
    }),
    author_id: z.string().nullable().openapi({
      description:
        "The author's user id, so a client can tell whose comments carry a " +
        "delete button without matching on display names. Null when deleted.",
    }),
    author_avatar: z.string().nullable(),
    body_md: z.string().nullable(),
    deleted: z.boolean(),
    created_at: z.string(),
  })
  .openapi("Comment");

export const CommentListSchema = z
  .object({ comments: z.array(CommentSchema) })
  .openapi("CommentList");

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
    view_count: r.view_count ?? 0,
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
    signature: r.signature ?? null,
    build_min: r.build_min ?? null,
    build_max: r.build_max ?? null,
    download_count: r.download_count ?? 0,
    created_at: r.created_at,
    published_by: r.published_by ?? null,
    // Joined in by routes that select alongside users/user_keys; a bare
    // `SELECT * FROM mod_releases` honestly reports them absent.
    published_by_username: r.publisher_display_name ?? r.publisher_discord_username ?? null,
    signer_fingerprint: r.signer_fingerprint ?? null,
    signer_key_revoked: Boolean(r.signer_key_revoked_at),
  };
}
