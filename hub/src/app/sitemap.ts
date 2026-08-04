import type { MetadataRoute } from "next";
import { getDocNotes } from "@/lib/docs";
import { getLastModified, getProducts, getReleases } from "@/lib/changelog";
import { getTagGroups } from "@/lib/tags";

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = "https://mjolnircore.com";
  const notes = getDocNotes();
  const tagGroups = getTagGroups();
  const releases = getReleases();
  const changelogUpdated = getLastModified();

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
