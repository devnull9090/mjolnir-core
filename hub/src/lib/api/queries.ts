/**
 * D1 queries the server-rendered pages share.
 *
 * Pages query D1 directly through getCloudflareContext rather than
 * fetching their own public API — same worker, no self-request hop. The
 * API remains the contract for everyone else.
 */
import type { D1Database } from "@cloudflare/workers-types";
import type { Mod, Release } from "@mjolnir/hub-kit";

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
              m.download_count, m.rating_count, m.rating_mean, m.created_at, m.updated_at,
              COALESCE(u.display_name, u.discord_username) AS author
       FROM mods m JOIN users u ON u.id = m.owner_id
       WHERE ${where.join(" AND ")}
       ORDER BY ${order}, m.id DESC LIMIT ?${binds.length + 1}`,
    )
    .bind(...binds, opts.limit ?? 60)
    .all();
  // D1 has no booleans; everything else is already the API shape.
  return rows.results.map((r) => ({ ...r, nsfw: !!r.nsfw })) as unknown as ModListRow[];
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

export interface MediaRow {
  id: string;
  alt_text: string;
  position: number;
}

/**
 * Server-rendered release rows carry the same shape the API publishes, so
 * the page can hand them straight to the shared <ReleaseList>.
 */
export type ReleaseRow = Release;

export async function getModPage(db: D1Database, slug: string) {
  const mod = (await db
    .prepare(
      `SELECT m.*, COALESCE(u.display_name, u.discord_username) AS author
       FROM mods m JOIN users u ON u.id = m.owner_id WHERE m.slug = ?1`,
    )
    .bind(slug)
    .first()) as unknown as ModPage | null;
  if (!mod) return null;

  const [media, releases] = await Promise.all([
    db
      .prepare(`SELECT id, alt_text, position FROM media WHERE mod_id = ?1 ORDER BY position`)
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
  ]);
  return {
    mod,
    media: media.results as unknown as MediaRow[],
    releases: releases.results as unknown as ReleaseRow[],
  };
}
