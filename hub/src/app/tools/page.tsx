import type { Metadata } from "next";
import Link from "next/link";
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { ArrowRight, Download, Wrench } from "lucide-react";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { ToolIcon } from "./_components/icons";
import { listToolImages, type MediaRow } from "@/lib/api/queries";
import { TOOLS, getToolVersion } from "@/lib/tools";

/** The cards carry preview images, which live in D1 — bound per request. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Tools | MJOLNIR Core",
  description:
    "The tools that ship beside the MJOLNIR Launcher for Halo Campaign Evolved — the Tag Editor for browsing and editing tags, textures and audio, and the mjolnir command line.",
  alternates: { canonical: "https://mjolnircore.com/tools" },
  openGraph: {
    title: "MJOLNIR tools",
    description:
      "Standalone tools for Halo Campaign Evolved: the Tag Editor and the mjolnir command line.",
    url: "https://mjolnircore.com/tools",
    siteName: "MJOLNIR Core",
    type: "website",
  },
};

/** A card image per tool, or an empty map when the database is unreachable. */
async function previewImages(): Promise<Map<string, MediaRow[]>> {
  try {
    const { env } = getCloudflareContext();
    return await listToolImages(env.DB as never);
  } catch {
    return new Map();
  }
}

export default async function ToolsIndexPage() {
  const images = await previewImages();

  // An ItemList is what lets a search engine read this as a catalogue of
  // separate applications rather than one page about tooling in general.
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: "MJOLNIR tools",
    numberOfItems: TOOLS.length,
    itemListElement: TOOLS.map((tool, index) => ({
      "@type": "ListItem",
      position: index + 1,
      url: `https://mjolnircore.com/tools/${tool.slug}`,
      name: tool.name,
    })),
  };

  return (
    <>
      <Navbar />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <main className="mx-auto max-w-6xl px-4 pt-32 pb-24 sm:px-6 md:pt-36">
        <header className="mb-12">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gold/10 text-gold">
              <Wrench className="h-6 w-6" />
            </span>
            <h1 className="text-3xl font-black text-foreground sm:text-4xl">Tools</h1>
          </div>
          <p className="mt-4 max-w-2xl text-lg text-text-muted">
            The launcher installs mods. These are the tools that make them — standalone
            apps and commands that read your installed copy of Halo Campaign Evolved
            directly, on their own release cadence.
          </p>
        </header>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {TOOLS.map((tool) => {
            const version = getToolVersion(tool);
            const hero = images.get(tool.slug)?.[0];
            return (
              <Link
                key={tool.slug}
                href={`/tools/${tool.slug}`}
                className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-surface-raised transition-colors hover:border-gold/40"
              >
                {hero && (
                  // Plain <img>: the bytes come from /api/v1/media/{id}, which
                  // next/image cannot optimise and would only proxy.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={hero.url}
                    alt={hero.alt_text}
                    className="h-44 w-full border-b border-border object-cover"
                  />
                )}
                <div className="flex flex-1 flex-col p-6">
                  <div className="mb-4 flex items-start gap-4">
                    <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gold/10 text-gold transition-colors group-hover:bg-gold/20">
                      <ToolIcon name={tool.icon} className="h-6 w-6" />
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                        <h2 className="text-lg font-bold text-foreground">{tool.name}</h2>
                        {version && (
                          <span className="font-mono text-sm text-gold">v{version}</span>
                        )}
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                            tool.availability === "download"
                              ? "bg-accent-green/10 text-accent-green"
                              : "bg-accent-blue/10 text-accent-blue"
                          }`}
                        >
                          {tool.availability === "download" ? "Download" : "Build from source"}
                        </span>
                      </div>
                      <p className="mt-1.5 text-sm leading-6 text-text-muted">{tool.tagline}</p>
                    </div>
                  </div>

                  <ul className="mb-5 space-y-1.5 text-sm text-text-muted">
                    {tool.highlights.slice(0, 3).map((highlight) => (
                      <li key={highlight.title} className="flex gap-2">
                        <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-gold" />
                        {highlight.title}
                      </li>
                    ))}
                  </ul>

                  <span className="mt-auto inline-flex items-center gap-1.5 text-sm font-semibold text-gold">
                    View tool
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                  </span>
                </div>
              </Link>
            );
          })}
        </div>

        {/* Two questions this page invites, answered where they are asked. */}
        <section className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-border bg-surface-raised p-6">
            <h2 className="flex items-center gap-2 text-lg font-bold text-foreground">
              <Download className="h-5 w-5 text-gold" />
              Install them from the launcher
            </h2>
            <p className="mt-3 text-sm leading-6 text-text-muted">
              The launcher&apos;s Tools view installs and updates every tool that publishes
              a build, checks the download against its published hash, and keeps it beside
              your game — so you do not have to track versions by hand.
            </p>
            <Link
              href="/download"
              className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline"
            >
              Get the launcher
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <div className="rounded-2xl border border-dashed border-border-bright p-6">
            <h2 className="text-lg font-bold text-foreground">More to come</h2>
            <p className="mt-3 text-sm leading-6 text-text-muted">
              Anything that publishes a manifest here becomes installable from the
              launcher, so new tools land without a launcher release. If you are building
              one, or want one built, say so — the roadmap is set in the open.
            </p>
            <div className="mt-4 flex flex-wrap gap-4 text-sm font-semibold">
              <Link
                href="https://discord.gg/9gxYZsByW9"
                target="_blank"
                className="text-gold hover:underline"
              >
                Discord
              </Link>
              <Link
                href="https://github.com/devnull9090/mjolnir-core/issues"
                target="_blank"
                className="text-gold hover:underline"
              >
                Open an issue
              </Link>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </>
  );
}
