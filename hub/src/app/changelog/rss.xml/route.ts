import { getReleases } from "@/lib/changelog";

/**
 * The changelog as RSS.
 *
 * Costs one file and gives anyone who wants to follow releases a way that is
 * not "check the website" or "join Discord". Feed readers, and the automations
 * people point at them, are also the cheapest way for a release to reach
 * someone who does not use either.
 */

export const revalidate = 3600;

const SITE = "https://mjolnircore.com";

/** RSS is XML: unescaped text in a title is a malformed feed, not a typo. */
function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

export async function GET() {
  const releases = getReleases();
  const updated = releases[0]
    ? new Date(`${releases[0].date}T00:00:00Z`).toUTCString()
    : new Date().toUTCString();

  const items = releases
    .map((release) => {
      const url = `${SITE}${release.path}`;
      return `    <item>
      <title>${escapeXml(`${release.productName} ${release.version} — ${release.title}`)}</title>
      <link>${url}</link>
      <guid isPermaLink="true">${url}</guid>
      <pubDate>${new Date(`${release.date}T00:00:00Z`).toUTCString()}</pubDate>
      <category>${escapeXml(release.productName)}</category>
      <description>${escapeXml(release.summary)}</description>
    </item>`;
    })
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>MJOLNIR Core releases</title>
    <link>${SITE}/changelog</link>
    <atom:link href="${SITE}/changelog/rss.xml" rel="self" type="application/rss+xml" />
    <description>Releases of the MJOLNIR modding platform for Halo Campaign Evolved.</description>
    <language>en</language>
    <lastBuildDate>${updated}</lastBuildDate>
${items}
  </channel>
</rss>
`;

  return new Response(xml, {
    headers: {
      "content-type": "application/rss+xml; charset=utf-8",
      "cache-control": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400",
    },
  });
}
