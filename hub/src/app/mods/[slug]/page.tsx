import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { Download } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Navbar } from "../../components/Navbar";
import { Footer } from "../../components/Footer";
import { Markdown } from "../../docs/_components/Markdown";
import { getModPage } from "@/lib/api/queries";
import { Gallery } from "./Gallery";
import { Rating } from "./Rating";
import { Comments } from "./Comments";
import { OwnerBar } from "./OwnerBar";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const { env } = getCloudflareContext();
  const page = await getModPage(env.DB as never, slug);
  if (!page || page.mod.status !== "published") return { title: "Mods | MJOLNIR Core" };
  return {
    title: `${page.mod.name} | MJOLNIR Core`,
    description: page.mod.summary ?? undefined,
  };
}

function fmtBytes(n: number | null): string {
  if (n === null) return "";
  if (n > 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MiB`;
  if (n > 1024) return `${(n / 1024).toFixed(0)} KiB`;
  return `${n} B`;
}

export default async function ModDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { env } = getCloudflareContext();
  const page = await getModPage(env.DB as never, slug);
  // Draft mods stay invisible here; owners reach them at /mods/{slug}/manage.
  if (!page || page.mod.status !== "published") notFound();
  const { mod, media, releases } = page;

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
              by <span className="text-foreground">{mod.author}</span>
              {mod.license ? <span className="text-text-dim"> · {mod.license}</span> : null}
              <span className="text-text-dim"> · {mod.download_count} downloads</span>
            </p>
          </div>
          <OwnerBar slug={mod.slug} ownerId={mod.owner_id} />
        </div>

        {mod.summary && <p className="text-lg text-text-muted mb-8">{mod.summary}</p>}

        {/* Screenshots */}
        {media.length > 0 && (
          <div className="mb-10">
            <Gallery
              items={media.map((m) => ({
                id: m.id,
                url: `/api/v1/media/${m.id}`,
                alt: m.alt_text,
              }))}
            />
          </div>
        )}

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

            {/* Comments */}
            <Comments slug={mod.slug} />
          </div>

          <aside className="space-y-8">
            {/* Releases */}
            <div>
              <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Releases</h2>
              {releases.length === 0 ? (
                <p className="text-sm text-text-dim">None published.</p>
              ) : (
                <div className="space-y-2">
                  {releases.map((r) => (
                    <div key={r.id} className="rounded-lg border border-border p-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono text-sm text-foreground">v{r.version}</span>
                        <a
                          href={`/api/v1/releases/${r.id}/download`}
                          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-gold/10 text-gold hover:bg-gold/20 transition-colors"
                        >
                          <Download className="w-3 h-3" />
                          {fmtBytes(r.file_size)}
                        </a>
                      </div>
                      <div className="text-[11px] text-text-dim">
                        {r.channel !== "stable" && (
                          <span className="uppercase font-bold mr-2">{r.channel}</span>
                        )}
                        {r.created_at.slice(0, 10)} · {r.download_count} downloads
                      </div>
                      {r.sha256 && (
                        <div
                          className="mt-1 font-mono text-[10px] text-text-dim truncate"
                          title={`sha256: ${r.sha256}`}
                        >
                          sha256 {r.sha256.slice(0, 16)}…
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Rating */}
            <div>
              <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Rating</h2>
              <Rating slug={mod.slug} />
            </div>

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
