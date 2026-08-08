import { cache } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { ArrowLeft, ArrowRight, Download, ScrollText, Terminal } from "lucide-react";

import { Navbar } from "../../components/Navbar";
import { Footer } from "../../components/Footer";
import { ToolGallery } from "../../components/HubKit";
import { LatestBuild } from "../_components/LatestBuild";
import { ToolIcon } from "../_components/icons";
import { listToolMedia, type MediaRow } from "@/lib/api/queries";
import { getTool, getToolVersion } from "@/lib/tools";
import { GitHubIcon } from "../../components/icons";

/**
 * The page body is generated from the code registry, but its previews come
 * from D1, which is only bound at request time — so this renders per request
 * like the mod pages rather than at build.
 */
export const dynamic = "force-dynamic";

/**
 * `generateMetadata` and the page both want the previews, and `cache`
 * collapses that into one read per request. A gallery is not worth failing a
 * page over, so an unreachable database renders a tool with no screenshots.
 */
const loadPreviews = cache(async (slug: string): Promise<MediaRow[]> => {
  try {
    const { env } = getCloudflareContext();
    return await listToolMedia(env.DB as never, slug);
  } catch {
    return [];
  }
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const tool = getTool(slug);
  if (!tool) return { title: "Tools | MJOLNIR Core" };

  const description = `${tool.tagline} ${tool.summary}`.slice(0, 300);
  // The link preview is the first screenshot, the same one the gallery shows
  // first. Videos are skipped: a card wants a still and none is generated.
  const hero = (await loadPreviews(slug)).find((m) => m.kind !== "video");

  return {
    title: `${tool.name} | MJOLNIR Core`,
    description,
    alternates: { canonical: `https://mjolnircore.com/tools/${tool.slug}` },
    openGraph: {
      title: tool.name,
      description: tool.tagline,
      url: `https://mjolnircore.com/tools/${tool.slug}`,
      siteName: "MJOLNIR Core",
      type: "website",
      images: hero ? [{ url: hero.url, alt: hero.alt_text }] : undefined,
    },
    twitter: {
      // Without an image the wide card renders as an empty box, so a tool
      // with no previews yet asks for the small one instead.
      card: hero ? "summary_large_image" : "summary",
      title: tool.name,
      description: tool.tagline,
      images: hero ? [hero.url] : undefined,
    },
  };
}

export default async function ToolPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const tool = getTool(slug);
  if (!tool) notFound();

  const version = getToolVersion(tool);
  const previews = await loadPreviews(slug);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: tool.name,
    description: tool.tagline,
    url: `https://mjolnircore.com/tools/${tool.slug}`,
    applicationCategory: "DeveloperApplication",
    operatingSystem: "Windows 10, Windows 11",
    ...(version ? { softwareVersion: version } : {}),
    ...(previews.length > 0
      ? { screenshot: previews.map((m) => `https://mjolnircore.com${m.url}`) }
      : {}),
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
    license: "https://opensource.org/licenses/MIT",
  };

  return (
    <>
      <Navbar />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <main className="mx-auto max-w-4xl px-4 pt-32 pb-24 sm:px-6 md:pt-36">
        <Link
          href="/tools"
          className="inline-flex items-center gap-2 text-sm text-text-muted hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          All tools
        </Link>

        <header className="mt-6 mb-10 border-b border-border pb-8">
          <div className="flex items-start gap-4">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gold/10 text-gold sm:h-14 sm:w-14">
              <ToolIcon name={tool.icon} className="h-6 w-6 sm:h-7 sm:w-7" />
            </span>
            <div className="min-w-0">
              <h1 className="text-3xl font-black text-foreground sm:text-4xl">{tool.name}</h1>
              <p className="mt-2 text-lg text-text-muted">{tool.tagline}</p>
            </div>
          </div>

          <p className="mt-6 max-w-2xl leading-7 text-text-muted">{tool.summary}</p>

          <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            {version && (
              <span className="text-text-dim">
                Latest <span className="font-mono text-gold">v{version}</span>
              </span>
            )}
            {tool.docsUrl && (
              <Link href={tool.docsUrl} className="inline-flex items-center gap-1.5 text-gold hover:underline">
                <ScrollText className="h-4 w-4" />
                Guide
              </Link>
            )}
            {tool.changelogProduct && (
              <Link
                href={`/changelog/${tool.changelogProduct}`}
                className="inline-flex items-center gap-1.5 text-gold hover:underline"
              >
                <ScrollText className="h-4 w-4" />
                Changelog
              </Link>
            )}
            <Link
              href={tool.repoUrl}
              target="_blank"
              className="inline-flex items-center gap-1.5 text-text-muted hover:text-foreground"
            >
              <GitHubIcon className="h-4 w-4" />
              Source
            </Link>
          </div>
        </header>

        {/* Previews. The strip, the lightbox and the upload flow are the same
            components the mod galleries use; the difference is the policy —
            moderators curate here, so nobody else is shown a control. */}
        <section className="mb-12" aria-labelledby="previews">
          <h2
            id="previews"
            className="mb-4 text-sm font-bold uppercase tracking-wide text-text-dim"
          >
            Previews
          </h2>
          <ToolGallery slug={tool.slug} initial={previews} />
        </section>

        {/* Getting it — downloads for a published tool, a build for one that
            ships no binary yet. */}
        <section className="mb-12" aria-labelledby="get">
          <h2 id="get" className="mb-4 text-sm font-bold uppercase tracking-wide text-text-dim">
            {tool.availability === "download" ? "Get it" : "Build it"}
          </h2>

          {tool.availability === "download" ? (
            <div className="space-y-4">
              <div className="rounded-2xl border border-border bg-surface-raised p-5 sm:p-6">
                <h3 className="text-lg font-bold text-foreground">Install from the launcher</h3>
                <p className="mt-2 text-sm leading-6 text-text-muted">
                  The launcher&apos;s Tools view installs this, checks the download against
                  the hash below, keeps it updated, and starts it on whichever installation
                  the launcher is set to. This is the path to take unless you have a reason
                  not to.
                </p>
                <Link
                  href="/download"
                  className="mt-4 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-gold to-gold-dim px-5 py-3 text-sm font-bold text-background shadow-lg shadow-gold/20 transition-all hover:brightness-110"
                >
                  <Download className="h-4 w-4" />
                  Download the launcher
                </Link>
              </div>

              <div className="rounded-2xl border border-border bg-surface-raised p-5 sm:p-6">
                <h3 className="text-lg font-bold text-foreground">Or download it directly</h3>
                <div className="mt-4 space-y-2">
                  {tool.downloads.map((download) => (
                    <a
                      key={download.href}
                      href={download.href}
                      className="group flex items-center gap-3 rounded-xl border border-border bg-surface-card p-3 transition-colors hover:border-gold/40"
                    >
                      <Download className="h-4 w-4 shrink-0 text-gold" />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold text-foreground">
                          {download.label}
                        </span>
                        <span className="block text-xs text-text-muted">{download.note}</span>
                      </span>
                      <ArrowRight className="h-4 w-4 shrink-0 text-text-dim transition-transform group-hover:translate-x-0.5" />
                    </a>
                  ))}
                </div>
                <div className="mt-4">
                  <LatestBuild slug={tool.slug} fallbackVersion={version} />
                </div>
                <p className="mt-3 text-xs text-text-dim">
                  Verify a direct download against that hash the same way you would the
                  launcher —{" "}
                  <Link href="/download" className="text-accent-blue hover:underline">
                    the steps are on the download page
                  </Link>
                  .
                </p>
              </div>
            </div>
          ) : (
            tool.build && (
              <div className="rounded-2xl border border-border bg-surface-raised p-5 sm:p-6">
                <p className="text-sm leading-6 text-text-muted">{tool.build.intro}</p>
                <div className="mt-5 space-y-4">
                  {tool.build.steps.map((step, index) => (
                    <div key={step.command} className="flex items-start gap-3">
                      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gold/15 text-xs font-bold text-gold">
                        {index + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="mb-1 flex items-center gap-2">
                          <Terminal className="h-3 w-3 text-text-dim" />
                          <span className="text-xs font-medium uppercase tracking-wider text-text-dim">
                            {step.label}
                          </span>
                        </div>
                        <pre className="overflow-x-auto rounded-lg border border-border bg-surface-card p-3 font-mono text-sm text-foreground">
                          <code>{step.command}</code>
                        </pre>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          )}
        </section>

        <section className="mb-12" aria-labelledby="what">
          <h2 id="what" className="mb-4 text-sm font-bold uppercase tracking-wide text-text-dim">
            What it does
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {tool.highlights.map((highlight) => (
              <div
                key={highlight.title}
                className="rounded-2xl border border-border bg-surface-raised p-5"
              >
                <h3 className="font-bold text-foreground">{highlight.title}</h3>
                <p className="mt-2 text-sm leading-6 text-text-muted">{highlight.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="requirements">
          <h2
            id="requirements"
            className="mb-4 text-sm font-bold uppercase tracking-wide text-text-dim"
          >
            What you need
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {tool.requirements.map((requirement) => (
              <div
                key={requirement.label}
                className="flex items-center gap-3 rounded-lg border border-border bg-surface-card p-3"
              >
                <span className="w-20 shrink-0 text-xs font-medium uppercase tracking-wider text-text-dim">
                  {requirement.label}
                </span>
                <span className="text-sm text-foreground">{requirement.value}</span>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-text-dim">
            Nothing shipped is ever modified: the game&apos;s containers are opened
            read-only, and an edit produces a new file.
          </p>
        </section>
      </main>

      <Footer />
    </>
  );
}
