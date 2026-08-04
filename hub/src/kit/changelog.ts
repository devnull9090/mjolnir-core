/**
 * The changelog, once.
 *
 * Entries are authored as Markdown in `changelog/<product>/<version>.md` and
 * snapshotted into the website's build. Everything that is not the website —
 * the launcher, the tag editor — reads the same entries over HTTP from
 * `/api/changelog`, so a release is described in exactly one place and no
 * surface can drift from another.
 *
 * These types mirror what `hub/scripts/sync-changelog.mjs` writes. That script
 * is the only producer.
 */
import { compareVersions } from "./ui/format";

/** A `### Added` block and its bullets, pre-parsed out of the Markdown body. */
export type ChangelogSection = {
  heading: string;
  items: string[];
};

export type ChangelogRelease = {
  /** Product id, e.g. `launcher`. */
  product: string;
  productName: string;
  version: string;
  /** The git tag this entry documents, e.g. `launcher-v0.5.3`. */
  tag: string;
  /** Public-facing headline. Not "v0.5.3". */
  title: string;
  /** `YYYY-MM-DD`. */
  date: string;
  /** One sentence. Meta description, feed description, modal opening line. */
  summary: string;
  /** Markdown, with the H1 and meta block already stripped. */
  body: string;
  /** The same body as structure, for consumers that do not render Markdown. */
  sections: ChangelogSection[];
  path: string;
  sourcePath: string;
  releaseUrl: string;
};

export type ChangelogProduct = {
  id: string;
  name: string;
  tagPrefix: string;
  blurb: string;
  docsUrl?: string;
};

export type ChangelogFeed = {
  products: ChangelogProduct[];
  releases: ChangelogRelease[];
};

export const CHANGELOG_ORIGIN = "https://mjolnircore.com";

export type ChangelogQuery = {
  /** Only this product's releases. Omit for everything. */
  product?: string;
  /** Only releases newer than this version. Requires `product`. */
  since?: string;
  /** Newest N. */
  limit?: number;
};

/**
 * How a surface actually performs the request.
 *
 * Injectable for the same reason the hub client's transport is: a desktop
 * webview should not be the thing making the call. A request issued from Rust
 * is not subject to the webview's origin rules or to a content security
 * policy, so it behaves identically under a dev server and in a packaged
 * build — and a CSP that only bites once packaged has already cost this
 * project a release.
 */
export type ChangelogTransport = (query: ChangelogQuery) => Promise<ChangelogFeed>;

export type FetchChangelogOptions = ChangelogQuery & {
  /** Defaults to mjolnircore.com; overridden in development. */
  origin?: string;
  transport?: ChangelogTransport;
  signal?: AbortSignal;
};

/**
 * Reads the published changelog.
 *
 * The endpoint is public, unauthenticated and read-only, so the default
 * transport is a plain `fetch` and needs no token.
 */
export async function fetchChangelog(
  options: FetchChangelogOptions = {},
): Promise<ChangelogFeed> {
  const { product, since, limit, origin = CHANGELOG_ORIGIN, transport, signal } = options;

  if (transport) return transport({ product, since, limit });

  const query = new URLSearchParams();
  if (product) query.set("product", product);
  if (since) query.set("since", since);
  if (limit) query.set("limit", String(limit));

  const suffix = query.toString();
  const res = await fetch(`${origin}/api/changelog${suffix ? `?${suffix}` : ""}`, { signal });
  if (!res.ok) throw new Error(`changelog: ${res.status} ${res.statusText}`);
  return (await res.json()) as ChangelogFeed;
}

/**
 * The releases a user moved across, newest first.
 *
 * An update can cross several versions at once — a launcher that sat unopened
 * for a week arrives several releases later — so "what's new" is a list, not
 * the single newest entry. A first install has no previous version and gets
 * nothing: someone who has never seen the app does not need to be told what
 * changed in it.
 */
export function releasesBetween(
  releases: ChangelogRelease[],
  product: string,
  from: string | null,
  to: string,
): ChangelogRelease[] {
  if (!from) return [];
  return releases
    .filter(
      (r) =>
        r.product === product &&
        compareVersions(r.version, from) > 0 &&
        compareVersions(r.version, to) <= 0,
    )
    .sort((a, b) => compareVersions(b.version, a.version));
}
