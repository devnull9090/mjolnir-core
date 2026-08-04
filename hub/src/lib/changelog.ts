import generated from "@/generated/changelog.json";
// Deep import rather than the kit barrel: this module is read by server
// components and route handlers, and the barrel re-exports client components.
import type { ChangelogFeed, ChangelogProduct, ChangelogRelease } from "@mjolnir/hub-kit/changelog";

/**
 * Release notes are authored as Markdown in the repository `changelog/`
 * directory. `scripts/sync-changelog.mjs` snapshots them into
 * `src/generated/changelog.json` before every build, so nothing here touches
 * the filesystem — same reasoning as `lib/docs.ts`.
 *
 * The types live in the kit rather than here, because the launcher and the tag
 * editor consume the same shapes over `/api/changelog`.
 */

const feed = generated as ChangelogFeed;

/** Every release, newest first. */
export function getReleases(): ChangelogRelease[] {
  return feed.releases;
}

export function getProducts(): ChangelogProduct[] {
  return feed.products;
}

export function getProduct(id: string): ChangelogProduct | null {
  return feed.products.find((p) => p.id === id) ?? null;
}

export function getReleasesFor(product: string): ChangelogRelease[] {
  return feed.releases.filter((r) => r.product === product);
}

export function getRelease(product: string, version: string): ChangelogRelease | null {
  return feed.releases.find((r) => r.product === product && r.version === version) ?? null;
}

/** The newest release of each product, in the order products are registered. */
export function getLatestPerProduct(): ChangelogRelease[] {
  return feed.products
    .map((p) => feed.releases.find((r) => r.product === p.id))
    .filter((r): r is ChangelogRelease => !!r);
}

/**
 * The release before this one, for the same product.
 *
 * `feed.releases` is sorted newest-first across all products, so the previous
 * release of *this* product is the next one in that product's own filtered
 * list — not the next entry overall.
 */
export function getAdjacentReleases(release: ChangelogRelease): {
  newer: ChangelogRelease | null;
  older: ChangelogRelease | null;
} {
  const siblings = getReleasesFor(release.product);
  const index = siblings.findIndex((r) => r.version === release.version);
  return {
    newer: index > 0 ? siblings[index - 1] : null,
    older: index >= 0 && index < siblings.length - 1 ? siblings[index + 1] : null,
  };
}

/** The most recent date any release carries, for sitemap and feed timestamps. */
export function getLastModified(): Date {
  const newest = feed.releases[0];
  return newest ? new Date(`${newest.date}T00:00:00Z`) : new Date();
}
