/**
 * D1 queries the server-rendered pages share.
 *
 * Pages query D1 directly through getCloudflareContext rather than
 * fetching their own public API — same worker, no self-request hop. The
 * API remains the contract for everyone else.
 */
import type { D1Database } from "@cloudflare/workers-types";

export interface ModCard {
  id: string;
  slug: string;
  name: string;
  summary: string | null;
  type: string;
  category: string;
  download_count: number;
  rating_count: number;
  rating_mean: number | null;
  author: string;
  updated_at: string;
}

export async function listPublishedMods(
  db: D1Database,
  opts: { q?: string; category?: string; sort?: "newest" | "downloads" | "rating"; limit?: number },
): Promise<ModCard[]> {
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
      `SELECT m.id, m.slug, m.name, m.summary, m.type, m.category, m.download_count,
              m.rating_count, m.rating_mean, m.updated_at,
              COALESCE(u.display_name, u.discord_username) AS author
       FROM mods m JOIN users u ON u.id = m.owner_id
       WHERE ${where.join(" AND ")}
       ORDER BY ${order}, m.id DESC LIMIT ?${binds.length + 1}`,
    )
    .bind(...binds, opts.limit ?? 60)
    .all();
  return rows.results as unknown as ModCard[];
}

export interface ModPage extends ModCard {
  description_md: string | null;
  license: string | null;
  nsfw: number;
  owner_id: string;
  status: string;
  created_at: string;
}

export interface MediaRow {
  id: string;
  alt_text: string;
  position: number;
}

export interface ReleaseRow {
  id: string;
  version: string;
  channel: string;
  changelog_md: string | null;
  file_size: number | null;
  sha256: string | null;
  download_count: number;
  created_at: string;
}

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
        `SELECT id, version, channel, changelog_md, file_size, sha256, download_count, created_at
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
