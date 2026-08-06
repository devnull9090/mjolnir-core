/**
 * The wire shapes of the MJOLNIR Hub API v1.
 *
 * Hand-mirrored from hub/src/lib/api/schemas.ts, which is the single source
 * of truth — those zod schemas generate the published OpenAPI document, and
 * these types must agree with them. The hub's own typecheck catches drift:
 * the API handlers and these types meet in the shared UI components.
 */

export type ModType = "content" | "script" | "native";
export type ModSort = "newest" | "downloads" | "rating";
export type ReleaseChannel = "stable" | "beta";
export type ReleaseStatus = "pending" | "scanning" | "published" | "rejected" | "yanked";

export interface Mod {
  id: string;
  slug: string;
  name: string;
  summary: string | null;
  type: ModType;
  category: string;
  license: string | null;
  nsfw: boolean;
  download_count: number;
  view_count: number;
  rating_count: number;
  rating_mean: number | null;
  author: string;
  created_at: string;
  updated_at: string;
}

export interface ModDetail extends Mod {
  description_md: string | null;
}

export interface ModList {
  mods: Mod[];
  next_cursor: string | null;
}

export interface ModListQuery {
  q?: string;
  category?: string;
  type?: ModType;
  sort?: ModSort;
  cursor?: string;
  limit?: number;
}

export interface Release {
  id: string;
  mod_id: string;
  version: string;
  channel: ReleaseChannel;
  changelog_md: string | null;
  file_size: number | null;
  sha256: string | null;
  /** Ed25519 over the release's sha256, base64, for signed releases. */
  signature: string | null;
  build_min: string | null;
  build_max: string | null;
  download_count: number;
  created_at: string;
  /** Account that created this release; null predates attribution. */
  published_by?: string | null;
  published_by_username?: string | null;
  /** Author signing-key fingerprint that verified at publish, if any. */
  signer_fingerprint?: string | null;
  /** The author's signing key has been revoked since publish. */
  signer_key_revoked?: boolean;
}

export interface ScanFinding {
  level: "error" | "warning";
  code: string;
  message: string;
}

export interface ReleaseStatusDetail {
  id: string;
  mod_id: string;
  version: string;
  status: ReleaseStatus;
  sha256: string | null;
  signature: string | null;
  file_size: number | null;
  chunk_count: number;
  findings: ScanFinding[];
  created_at: string;
  /** Account that created this release; null predates attribution. */
  published_by?: string | null;
  published_by_username?: string | null;
  /** Author-signature fingerprint that verified at publish, if any. */
  signer_fingerprint?: string | null;
  /** The signing key has been revoked since this release published. */
  signer_key_revoked?: boolean;
}

export type MediaStatus = "pending" | "approved" | "rejected";

/**
 * What a gallery hangs off: a community mod, or one of the first-party tools
 * on /tools. The two differ in who may add to them — anyone signed in for a
 * mod, moderators only for a tool — but in nothing else, so every media path
 * below takes this rather than a bare slug.
 */
export interface MediaOwner {
  type: "mod" | "tool";
  slug: string;
}

export interface Media {
  id: string;
  /** Set for a mod's gallery; null for a tool's. */
  mod_id: string | null;
  /** Set for a tool's gallery; null for a mod's. */
  tool_slug: string | null;
  url: string;
  kind: "screenshot" | "thumbnail" | "video";
  alt_text: string;
  /** Moderation state; listings only carry non-approved items for their uploader. */
  status: MediaStatus;
  view_count: number;
  /** Display name of whoever submitted this item. */
  uploader: string | null;
  /** The submitter's user id, for deciding whose items carry controls. */
  uploader_id: string;
  width: number | null;
  height: number | null;
  position: number;
  created_at: string;
}

/** A gallery submission as the moderation queue lists it. */
export interface QueuedMedia {
  id: string;
  url: string;
  kind: "screenshot" | "thumbnail" | "video";
  alt_text: string;
  status: MediaStatus;
  file_size: number | null;
  uploader: string;
  /** What it was submitted to, and where that lives on the site. */
  owner: MediaOwner;
  owner_name: string;
  created_at: string;
}

export interface Report {
  id: string;
  reporter: string;
  subject_type: string;
  subject_id: string;
  reason: string;
  detail: string | null;
  status: "open" | "resolved" | "dismissed";
  created_at: string;
}

export interface Review {
  author: string;
  score: number;
  review_md: string;
  created_at: string;
}

export interface RatingSummary {
  count: number;
  mean: number | null;
  distribution: Record<string, number>;
  mine: number | null;
  reviews: Review[];
}

export interface Comment {
  id: string;
  mod_id: string;
  parent_id: string | null;
  author: string | null;
  author_id: string | null;
  author_avatar: string | null;
  body_md: string | null;
  deleted: boolean;
  created_at: string;
}

export interface User {
  id: string;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  role: "user" | "moderator" | "admin";
  created_at: string;
}

export interface ConflictPair {
  a: string;
  b: string;
  shared_chunks: number;
  sample_chunk_ids: string[];
}

export type ReportSubject = "mod" | "release" | "comment" | "media" | "user";
export type ReportReason = "malware" | "stolen" | "broken" | "nsfw" | "spam" | "other";

/** What a device-pairing handshake hands back to a desktop client. */
export interface DeviceStart {
  device_code: string;
  user_code: string;
  verification_url: string;
  interval: number;
  expires_in: number;
}

export interface DevicePoll {
  status: "pending" | "approved" | "denied" | "expired";
  /** Present exactly once, on the poll that observes approval. */
  key?: string;
  user?: User;
}
