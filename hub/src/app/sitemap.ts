import type { MetadataRoute } from "next";
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { getDocNotes } from "@/lib/docs";
import { getLastModified, getProducts, getReleases } from "@/lib/changelog";
import { getAllTags, getBlogLastModified, getPosts } from "@/lib/blog";
import { getTagGroups } from "@/lib/tags";
import {
  listModsForSitemap,
  listProfilesForSitemap,
  listToolImages,
  type MediaRow,
  type SitemapMod,
} from "@/lib/api/queries";
import { TOOLS } from "@/lib/tools";

/**
 * Every other entry here comes from files on disk and could be prerendered,
 * but the mod pages come from D1, which is only bound at request time. Two
 * indexed reads per request, in front of Cloudflare's cache.
 */
export const dynamic = "force-dynamic";

const baseUrl = "https://mjolnircore.com";

/** SQLite writes "YYYY-MM-DD HH:MM:SS" and means UTC; `new Date` does not. */
function utcDate(sqlite: string): Date {
  const parsed = new Date(sqlite.includes("T") ? sqlite : `${sqlite.replace(" ", "T")}Z`);
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
}

async function modEntries(): Promise<MetadataRoute.Sitemap> {
  let mods: SitemapMod[] = [];
  try {
    const { env } = getCloudflareContext();
    mods = await listModsForSitemap(env.DB as never);
  } catch {
    // A sitemap missing its mod pages still beats a 500 that costs the
    // crawler every other page on the site.
    return [];
  }
  return mods.map((mod) => ({
    url: `${baseUrl}/mods/${mod.slug}`,
    lastModified: utcDate(mod.updated_at),
    changeFrequency: "weekly" as const,
    priority: 0.7,
    // Screenshots ride along as an image sitemap, which is how the gallery
    // becomes indexable rather than merely present in the HTML.
    images: mod.images.length > 0 ? mod.images.map((path) => `${baseUrl}${path}`) : undefined,
  }));
}

/**
 * Profiles worth crawling: the accounts that have published something. An
 * account with nothing on it is a page of zeroes, so it is left out rather
 * than offered up.
 */
async function profileEntries(): Promise<MetadataRoute.Sitemap> {
  try {
    const { env } = getCloudflareContext();
    const profiles = await listProfilesForSitemap(env.DB as never);
    return profiles.map((p) => ({
      url: `${baseUrl}/users/${p.id}`,
      lastModified: utcDate(p.updated_at),
      changeFrequency: "weekly" as const,
      priority: 0.4,
    }));
  } catch {
    return [];
  }
}

/** Tool previews, so the screenshots are indexable rather than merely present. */
async function toolImages(): Promise<Map<string, MediaRow[]>> {
  try {
    const { env } = getCloudflareContext();
    return await listToolImages(env.DB as never);
  } catch {
    return new Map();
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const notes = getDocNotes();
  const tagGroups = getTagGroups();
  const releases = getReleases();
  const changelogUpdated = getLastModified();
  const [mods, profiles, previews] = await Promise.all([
    modEntries(),
    profileEntries(),
    toolImages(),
  ]);

  return [
    {
      url: baseUrl,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: `${baseUrl}/docs/tags`,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 0.9,
    },
    ...tagGroups.map((g) => ({
      url: `${baseUrl}/docs/tags/${g.slug}`,
      lastModified: new Date(),
      changeFrequency: "monthly" as const,
      priority: 0.6,
    })),
    {
      url: `${baseUrl}/mods`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 0.9,
    },
    ...mods,
    ...profiles,
    {
      url: `${baseUrl}/tools`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.8,
    },
    // A tool page changes when its tool releases, which the changelog dates.
    ...TOOLS.map((tool) => {
      const images = previews.get(tool.slug) ?? [];
      return {
        url: `${baseUrl}/tools/${tool.slug}`,
        lastModified: changelogUpdated,
        changeFrequency: "weekly" as const,
        priority: 0.7,
        images: images.length > 0 ? images.map((m) => `${baseUrl}${m.url}`) : undefined,
      };
    }),
    {
      url: `${baseUrl}/download`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.8,
    },
    {
      url: `${baseUrl}/changelog`,
      lastModified: changelogUpdated,
      changeFrequency: "weekly",
      priority: 0.8,
    },
    ...getProducts().map((product) => ({
      url: `${baseUrl}/changelog/${product.id}`,
      lastModified: changelogUpdated,
      changeFrequency: "weekly" as const,
      priority: 0.6,
    })),
    {
      url: `${baseUrl}/blog`,
      lastModified: getBlogLastModified(),
      changeFrequency: "weekly" as const,
      priority: 0.8,
    },
    // A tag page changes whenever a post carrying the tag is published, so it
    // is dated by the newest post rather than by today.
    ...getAllTags().map((tag) => ({
      url: `${baseUrl}/blog/tag/${tag}`,
      lastModified: getBlogLastModified(),
      changeFrequency: "weekly" as const,
      priority: 0.5,
    })),
    // A post, like a release, never changes after it is published.
    ...getPosts().map((post) => ({
      url: `${baseUrl}/blog/${post.slug}`,
      lastModified: new Date(`${post.date}T00:00:00Z`),
      changeFrequency: "yearly" as const,
      priority: 0.6,
    })),
    // A release entry never changes after it is published, so it is dated by
    // its own release day rather than by today — which is what stops a crawler
    // re-fetching forty-three unchanged pages every time anything ships.
    ...releases.map((release) => ({
      url: `${baseUrl}${release.path}`,
      lastModified: new Date(`${release.date}T00:00:00Z`),
      changeFrequency: "yearly" as const,
      priority: 0.5,
    })),
    {
      url: `${baseUrl}/docs`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.8,
    },
    {
      url: `${baseUrl}/docs/research/tag-data`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.7,
    },
    {
      url: `${baseUrl}/docs/research/multiplayer`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.7,
    },
    {
      url: `${baseUrl}/docs/research/halo-simulation`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.7,
    },
    {
      url: `${baseUrl}/docs/notes`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.6,
    },
    ...notes.map((note) => ({
      url: `${baseUrl}/docs/notes/${note.slug}`,
      lastModified: new Date(),
      changeFrequency: "weekly" as const,
      priority: 0.5,
    })),
  ];
}
