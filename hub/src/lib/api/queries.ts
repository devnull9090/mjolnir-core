/**
 * D1 queries the server-rendered pages share.
 *
 * Pages query D1 directly through getCloudflareContext rather than
 * fetching their own public API — same worker, no self-request hop. The
 * API remains the contract for everyone else.
 */
import type { D1Database } from "@cloudflare/workers-types";
import type { Media, Mod, Release, ReleaseChanges, UserProfile } from "@mjolnir/hub-kit";

import { OWNER_COLUMNS, avatarUrl, modFromRow } from "./schemas";

// Every mod row here goes through `modFromRow`, the same mapper the API
// uses, rather than being spread wholesale. That is not tidiness: a D1 row
// selected against OWNER_COLUMNS carries the owner's Discord snowflake, and
// a mod handed to <ModCard> is serialised into the payload the browser
// receives. Naming the fields is what keeps that snowflake behind
// /admin/users, where it is meant to stay.

/**
 * Listing rows are the API's `Mod` shape so pages can hand them straight to
 * the shared <ModCard>, which the launcher renders too.
 */
export type ModListRow = Mod;

export async function listPublishedMods(
  db: D1Database,
  opts: { q?: string; category?: string; sort?: "newest" | "downloads" | "rating"; limit?: number },
): Promise<ModListRow[]> {
  const where: string[] = ["m.status = 'published'"];
  const binds: (string | number)[] = [];
  if (opts.category && opts.category !== "all") {
    where.push(`m.category = ?${binds.length + 1}`);
    binds.push(opts.category);
  }
  if (opts.q) {
    where.push(`(m.name LIKE ?${binds.length + 1} OR m.summary LIKE ?${binds.length + 1})`);
    binds.push(`%${opts.q}%`);
  }
  const order =
    opts.sort === "downloads"
      ? "m.download_count DESC"
      : opts.sort === "rating"
        ? "COALESCE(m.rating_wilson, -1) DESC"
        : "m.created_at DESC";

  const rows = await db
    .prepare(
      `SELECT m.id, m.slug, m.name, m.summary, m.type, m.category, m.license, m.nsfw,
              m.download_count, m.view_count, m.rating_count, m.rating_mean,
              m.created_at, m.updated_at, ${OWNER_COLUMNS}
       FROM mods m JOIN users u ON u.id = m.owner_id
       WHERE ${where.join(" AND ")}
       ORDER BY ${order}, m.id DESC LIMIT ?${binds.length + 1}`,
    )
    .bind(...binds, opts.limit ?? 60)
    .all();
  return rows.results.map(modFromRow);
}

/**
 * The approved previews for one tool, in gallery order.
 *
 * Server-rendered so a tool page paints its screenshots on first load and
 * can put one in its link preview. The client gallery refetches on mount,
 * which is what layers in anything a moderator has yet to approve.
 */
export async function listToolMedia(db: D1Database, slug: string): Promise<MediaRow[]> {
  const rows = await db
    .prepare(
      `SELECT media.id, media.mod_id, media.tool_slug, media.kind, media.alt_text,
              media.status, media.view_count, media.uploader_id, media.width,
              media.height, media.position, media.created_at,
              COALESCE(u.display_name, u.discord_username) AS uploader
       FROM media JOIN users u ON u.id = media.uploader_id
       WHERE media.tool_slug = ?1 AND media.status = 'approved'
       ORDER BY media.position, media.created_at`,
    )
    .bind(slug)
    .all();
  return rows.results.map((r) => ({
    ...r,
    url: `/api/v1/media/${r.id}`,
  })) as unknown as MediaRow[];
}

/**
 * Every tool's approved stills, keyed by slug and in gallery order — one
 * query for the whole /tools index and for the sitemap, rather than one per
 * tool. The index takes the first of each as the card image.
 *
 * Videos are skipped for the same reason the mod sitemap skips them: a card
 * and an `<image:loc>` both want a picture, and none is generated for a clip.
 */
export async function listToolImages(db: D1Database): Promise<Map<string, MediaRow[]>> {
  const rows = await db
    .prepare(
      `SELECT media.id, media.mod_id, media.tool_slug, media.kind, media.alt_text,
              media.status, media.view_count, media.uploader_id, media.width,
              media.height, media.position, media.created_at,
              COALESCE(u.display_name, u.discord_username) AS uploader
       FROM media JOIN users u ON u.id = media.uploader_id
       WHERE media.tool_slug IS NOT NULL AND media.status = 'approved'
         AND media.kind <> 'video'
       ORDER BY media.position, media.created_at`,
    )
    .all();
  const bySlug = new Map<string, MediaRow[]>();
  for (const row of rows.results as unknown as MediaRow[]) {
    const slug = row.tool_slug;
    if (!slug) continue;
    const item = { ...row, url: `/api/v1/media/${row.id}` };
    const list = bySlug.get(slug);
    if (list) list.push(item);
    else bySlug.set(slug, [item]);
  }
  return bySlug;
}

/** One published mod as the sitemap needs it, with its listable images. */
export interface SitemapMod {
  slug: string;
  /** SQLite `datetime('now')` text: "YYYY-MM-DD HH:MM:SS", always UTC. */
  updated_at: string;
  /** Hub-relative paths to approved screenshots, in gallery order. */
  images: string[];
}

/**
 * Every published mod and the screenshots worth listing beside it.
 *
 * Two queries rather than one per mod: the second pulls the media for the
 * whole site at once and they are grouped here. Videos are left out because
 * an image sitemap's `<image:loc>` wants a still, and the gallery does not
 * generate one — `media.kind = 'thumbnail'` exists for that day.
 */
export async function listModsForSitemap(db: D1Database): Promise<SitemapMod[]> {
  const [mods, media] = await Promise.all([
    db
      .prepare(
        `SELECT slug, updated_at FROM mods
         WHERE status = 'published' ORDER BY updated_at DESC`,
      )
      .all(),
    db
      .prepare(
        `SELECT m.slug AS slug, media.id AS id
         FROM media JOIN mods m ON m.id = media.mod_id
         WHERE m.status = 'published' AND media.status = 'approved' AND media.kind <> 'video'
         ORDER BY media.position, media.created_at`,
      )
      .all(),
  ]);

  const bySlug = new Map<string, string[]>();
  for (const row of media.results as unknown as { slug: string; id: string }[]) {
    const list = bySlug.get(row.slug);
    if (list) list.push(`/api/v1/media/${row.id}`);
    else bySlug.set(row.slug, [`/api/v1/media/${row.id}`]);
  }

  return (mods.results as unknown as { slug: string; updated_at: string }[]).map((m) => ({
    ...m,
    images: bySlug.get(m.slug) ?? [],
  }));
}

/**
 * A mod row straight out of D1: the API shape plus the columns only the
 * server-rendered page needs, and `nsfw` still as the integer SQLite stores.
 */
export interface ModPage extends Omit<Mod, "nsfw"> {
  description_md: string | null;
  nsfw: number;
  owner_id: string;
  status: string;
}

/** Server-rendered gallery rows are the API's `Media` shape so the page can
 *  hand them straight to the shared <ModGallery> as its first paint. */
export type MediaRow = Media;

/**
 * Server-rendered release rows carry the same shape the API publishes, so
 * the page can hand them straight to the shared <ReleaseList>.
 */
export type ReleaseRow = Release;

export async function getModPage(db: D1Database, slug: string) {
  const row = await db
    .prepare(
      `SELECT m.*, ${OWNER_COLUMNS}
       FROM mods m JOIN users u ON u.id = m.owner_id WHERE m.slug = ?1`,
    )
    .bind(slug)
    .first();
  if (!row) return null;
  const mod: ModPage = {
    ...modFromRow(row),
    description_md: (row.description_md as string) ?? null,
    // The page needs the raw integer for its own checks; the API's boolean
    // is what `modFromRow` already produced and is discarded here.
    nsfw: row.nsfw as number,
    owner_id: row.owner_id as string,
    status: row.status as string,
  };

  const [media, releases, latest] = await Promise.all([
    // Approved only: the page is public, and a caller's own pending items
    // arrive through the API refetch that knows who is asking.
    db
      .prepare(
        `SELECT media.id, media.mod_id, media.kind, media.alt_text, media.status,
                media.view_count, media.uploader_id, media.width, media.height,
                media.position, media.created_at,
                COALESCE(u.display_name, u.discord_username) AS uploader
         FROM media JOIN users u ON u.id = media.uploader_id
         WHERE media.mod_id = ?1 AND media.status = 'approved'
         ORDER BY media.position, media.created_at`,
      )
      .bind(mod.id)
      .all(),
    db
      .prepare(
        `SELECT id, mod_id, version, channel, changelog_md, file_size, sha256, signature,
                build_min, build_max, download_count, created_at
         FROM mod_releases WHERE mod_id = ?1 AND status = 'published'
         ORDER BY created_at DESC`,
      )
      .bind(mod.id)
      .all(),
    // The latest release's declared change list, for the transparency
    // section — same shape the /releases/{id}/changes endpoint serves.
    db
      .prepare(
        `SELECT r.id, r.version, r.changes_json,
                (SELECT COUNT(*) FROM release_chunks rc WHERE rc.release_id = r.id) AS chunk_count
         FROM mod_releases r WHERE r.mod_id = ?1 AND r.status = 'published'
         ORDER BY r.created_at DESC LIMIT 1`,
      )
      .bind(mod.id)
      .first<{ id: string; version: string; changes_json: string | null; chunk_count: number }>(),
  ]);
  return {
    mod,
    // `url` is derived, not stored — the API's mediaFromRow does the same.
    media: media.results.map((r) => ({
      ...r,
      url: `/api/v1/media/${r.id}`,
    })) as unknown as MediaRow[],
    releases: releases.results as unknown as ReleaseRow[],
    latestChanges: latest
      ? ({
          release_id: latest.id,
          version: latest.version,
          chunk_count: latest.chunk_count,
          changes: latest.changes_json ? JSON.parse(latest.changes_json) : null,
        } satisfies ReleaseChanges)
      : null,
  };
}

// ── Profiles ──────────────────────────────────────────────────────────

/**
 * Every activity total a profile reports, as one round trip.
 *
 * Two directions kept apart: the `_received` figures are what this account's
 * published work drew, and the rest is what it did. All of it is counts —
 * the queries deliberately never assemble a list of what someone downloaded
 * or viewed, because no route publishes one.
 */
const PROFILE_STATS_SQL = `
  SELECT
    (SELECT COUNT(*) FROM mods
      WHERE owner_id = ?1 AND status = 'published') AS mods_published,
    (SELECT COALESCE(SUM(download_count), 0) FROM mods
      WHERE owner_id = ?1 AND status = 'published') AS downloads_received,
    (SELECT COALESCE(SUM(view_count), 0) FROM mods
      WHERE owner_id = ?1 AND status = 'published') AS views_received,
    (SELECT COALESCE(SUM(rating_count), 0) FROM mods
      WHERE owner_id = ?1 AND status = 'published') AS ratings_received,
    -- Weighted by rating_count, so a single-vote 5★ mod cannot outweigh a
    -- hundred-vote 4★ one in the author's headline average.
    (SELECT SUM(rating_mean * rating_count) / NULLIF(SUM(rating_count), 0) FROM mods
      WHERE owner_id = ?1 AND status = 'published' AND rating_mean IS NOT NULL) AS rating_mean,
    (SELECT COUNT(DISTINCT mod_id) FROM mod_downloads WHERE user_id = ?1) AS mods_downloaded,
    (SELECT COUNT(*) FROM ratings WHERE user_id = ?1) AS ratings_given,
    (SELECT COUNT(*) FROM comments
      WHERE user_id = ?1 AND deleted_at IS NULL) AS comments_posted,
    (SELECT COUNT(*) FROM media
      WHERE uploader_id = ?1 AND status = 'approved') AS media_contributed
`;

interface ProfileUserRow {
  id: string;
  discord_id: string;
  discord_username: string;
  discord_avatar: string | null;
  display_name: string | null;
  role: "user" | "moderator" | "admin";
  trust_level: number;
  created_at: string;
}

/**
 * One public profile: identity, activity totals, and published mods.
 *
 * Shared by the page and by `GET /api/v1/users/{id}` so the two cannot
 * disagree about what a profile says. A banned account reads as absent —
 * the route turns that into a 404 and the page into `notFound()`.
 */
export async function getUserProfile(db: D1Database, id: string): Promise<UserProfile | null> {
  const user = await db
    .prepare(
      `SELECT id, discord_id, discord_username, discord_avatar, display_name,
              role, trust_level, created_at
       FROM users WHERE id = ?1 AND banned_at IS NULL`,
    )
    .bind(id)
    .first<ProfileUserRow>();
  if (!user) return null;

  const [stats, mods] = await Promise.all([
    db.prepare(PROFILE_STATS_SQL).bind(user.id).first<UserProfile["stats"]>(),
    db
      .prepare(
        `SELECT m.id, m.slug, m.name, m.summary, m.type, m.category, m.license, m.nsfw,
                m.download_count, m.view_count, m.rating_count, m.rating_mean,
                m.created_at, m.updated_at, ${OWNER_COLUMNS}
         FROM mods m JOIN users u ON u.id = m.owner_id
         WHERE m.owner_id = ?1 AND m.status = 'published'
         ORDER BY m.created_at DESC, m.id DESC LIMIT 100`,
      )
      .bind(user.id)
      .all(),
  ]);

  return {
    user: {
      id: user.id,
      username: user.discord_username,
      display_name: user.display_name,
      avatar_url: avatarUrl(user.discord_id, user.discord_avatar),
      role: user.role,
      trust_level: user.trust_level,
      created_at: user.created_at,
    },
    // A fresh account has no rows behind any of these; D1 still answers the
    // aggregate query, so the fallback is only for a read that failed.
    stats: stats ?? {
      mods_published: 0,
      downloads_received: 0,
      views_received: 0,
      ratings_received: 0,
      rating_mean: null,
      mods_downloaded: 0,
      ratings_given: 0,
      comments_posted: 0,
      media_contributed: 0,
    },
    mods: mods.results.map(modFromRow),
  };
}

/** Accounts with something published, for the sitemap's profile entries. */
export async function listProfilesForSitemap(
  db: D1Database,
): Promise<{ id: string; updated_at: string }[]> {
  const rows = await db
    .prepare(
      `SELECT m.owner_id AS id, MAX(m.updated_at) AS updated_at
       FROM mods m WHERE m.status = 'published'
       GROUP BY m.owner_id`,
    )
    .all();
  return rows.results as unknown as { id: string; updated_at: string }[];
}
