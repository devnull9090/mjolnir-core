import { cache } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Navbar } from "../../components/Navbar";
import { Footer } from "../../components/Footer";
import { Markdown } from "../../docs/_components/Markdown";
import { getModPage } from "@/lib/api/queries";
// Module import, not the barrel: ChangeList is hook-free and renders on the
// server; the barrel would drag client-only components into this graph.
import { ChangeList } from "@mjolnir/hub-kit/ui/ChangeList";
import {
  CommentThread,
  ModGallery,
  ModViewBeacon,
  RatingPanel,
  ReleaseDownloadList,
  ReportButton,
} from "../../components/HubKit";
import { OwnerBar } from "./OwnerBar";

/**
 * `generateMetadata` and the page itself both need the whole mod row, and
 * `cache` collapses that into one set of D1 reads per request rather than two.
 */
const loadModPage = cache((slug: string) => {
  const { env } = getCloudflareContext();
  return getModPage(env.DB as never, slug);
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const page = await loadModPage(slug);
  if (!page || page.mod.status !== "published") return { title: "Mods | MJOLNIR Core" };

  // The card image is the first approved screenshot, which is the one the
  // gallery shows first: `media` arrives ordered by position. Videos are
  // skipped because a link preview wants a still and none is generated.
  const hero = page.media.find((m) => m.kind !== "video");
  const description = page.mod.summary ?? undefined;

  return {
    title: `${page.mod.name} | MJOLNIR Core`,
    description,
    alternates: { canonical: `/mods/${page.mod.slug}` },
    openGraph: {
      title: page.mod.name,
      description,
      url: `/mods/${page.mod.slug}`,
      siteName: "MJOLNIR Core",
      type: "article",
      images: hero ? [{ url: hero.url, alt: hero.alt_text }] : undefined,
    },
    twitter: {
      // Without an image the wide card renders as an empty box, so a mod
      // with no screenshots yet asks for the small one instead.
      card: hero ? "summary_large_image" : "summary",
      title: page.mod.name,
      description,
      images: hero ? [hero.url] : undefined,
    },
  };
}

export default async function ModDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const page = await loadModPage(slug);
  // Draft mods stay invisible here; owners reach them at /mods/{slug}/manage.
  if (!page || page.mod.status !== "published") notFound();
  const { mod, media, releases, latestChanges } = page;

  return (
    <>
      <Navbar />

      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl md:text-4xl font-black text-foreground">{mod.name}</h1>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-surface-card border border-border text-text-dim">
                {mod.category}
              </span>
            </div>
            <p className="text-text-muted">
              by{" "}
              <Link
                href={`/users/${mod.owner_id}`}
                className="inline-flex items-center gap-1.5 align-middle text-foreground hover:text-gold transition-colors"
              >
                {mod.author_avatar ? (
                  // Plain <img>: Discord's CDN is not a configured next/image
                  // host, and the avatar is served at the size it renders.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={mod.author_avatar} alt="" className="w-5 h-5 rounded-full" />
                ) : null}
                {mod.author}
              </Link>
              {mod.license ? <span className="text-text-dim"> · {mod.license}</span> : null}
              <span className="text-text-dim"> · {mod.download_count} downloads</span>
              <span className="text-text-dim"> · {mod.view_count} views</span>
            </p>
          </div>
          <OwnerBar slug={mod.slug} ownerId={mod.owner_id} />
        </div>

        {mod.summary && <p className="text-lg text-text-muted mb-8">{mod.summary}</p>}

        {/* Gallery: server-rendered approved media as the first paint; the
            client refetch layers in the viewer's own pending submissions
            and the upload flow. */}
        <div className="mb-10">
          <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Gallery</h2>
          <ModGallery slug={mod.slug} allowUpload initial={media} />
        </div>

        <ModViewBeacon slug={mod.slug} />

        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-10">
          <div>
            {/* Description */}
            {mod.description_md ? (
              <article className="mb-12">
                <Markdown>{mod.description_md}</Markdown>
              </article>
            ) : (
              <p className="mb-12 text-text-dim text-sm">No description yet.</p>
            )}

            {/* Transparency: what the latest release actually edits, from
                the declared change list stored at scan time. */}
            {latestChanges && (
              <section className="mb-12">
                <h2 className="text-sm font-bold uppercase text-text-dim mb-3">
                  What this mod does
                  <span className="normal-case font-normal"> · v{latestChanges.version}</span>
                </h2>
                <ChangeList data={latestChanges} />
              </section>
            )}

            {/* Comments */}
            <CommentThread slug={mod.slug} />
          </div>

          <aside className="space-y-8">
            {/* Releases */}
            <div>
              <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Releases</h2>
              <ReleaseDownloadList releases={releases} />
            </div>

            {/* Rating */}
            <div>
              <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Rating</h2>
              <RatingPanel slug={mod.slug} compact />
            </div>

            <ReportButton subjectId={mod.id} label="Report this mod" />

            <div className="text-xs text-text-dim">
              <Link href="/docs/api" className="hover:text-foreground">
                Integrate via the open API →
              </Link>
            </div>
          </aside>
        </div>
      </main>

      <Footer />
    </>
  );
}
