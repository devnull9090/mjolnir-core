import type { Metadata } from "next";
import Link from "next/link";
import { Rss, ScrollText } from "lucide-react";

import { getLatestPerProduct, getProducts, getReleases } from "@/lib/changelog";
import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { ReleaseCard } from "./_components/ReleaseCard";

export const metadata: Metadata = {
  title: "Changelog | MJOLNIR Core",
  description:
    "Every release of the MJOLNIR Launcher, Tag Editor, Runtime and code mods for Halo Campaign Evolved — what changed, what was fixed, and what it means for you.",
  alternates: {
    canonical: "https://mjolnircore.com/changelog",
    types: { "application/rss+xml": "https://mjolnircore.com/changelog/rss.xml" },
  },
  openGraph: {
    title: "MJOLNIR Core changelog",
    description:
      "Every release of the MJOLNIR modding platform for Halo Campaign Evolved, newest first.",
    url: "https://mjolnircore.com/changelog",
    siteName: "MJOLNIR Core",
    type: "website",
  },
};

export default function ChangelogIndexPage() {
  const releases = getReleases();
  const products = getProducts();
  const latest = getLatestPerProduct();

  // An ItemList of the releases is what lets a search engine understand this
  // page as a series of dated entries rather than one long article.
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: "MJOLNIR Core changelog",
    description: metadata.description,
    numberOfItems: releases.length,
    itemListElement: releases.slice(0, 50).map((release, index) => ({
      "@type": "ListItem",
      position: index + 1,
      url: `https://mjolnircore.com${release.path}`,
      name: `${release.productName} ${release.version} — ${release.title}`,
    })),
  };

  return (
    <>
      <Navbar />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <main className="mx-auto max-w-4xl px-4 pt-32 pb-24 sm:px-6 md:pt-36">
        <header className="mb-12">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gold/10 text-gold">
              <ScrollText className="h-6 w-6" />
            </span>
            <h1 className="text-3xl font-black text-foreground sm:text-4xl">Changelog</h1>
          </div>
          <p className="mt-4 max-w-2xl text-lg text-text-muted">
            Every release of the MJOLNIR modding platform for Halo Campaign Evolved — the
            launcher, the tag editor, the runtime and the signed code mods. Newest first.
          </p>
          <a
            href="/changelog/rss.xml"
            className="mt-4 inline-flex items-center gap-2 text-sm text-text-dim hover:text-gold"
          >
            <Rss className="h-4 w-4" />
            Subscribe by RSS
          </a>
        </header>

        {/* Latest per product, so the common question — "what am I meant to be
            on?" — is answered without scrolling a combined timeline. */}
        <section className="mb-14" aria-labelledby="current">
          <h2 id="current" className="mb-4 text-sm font-bold uppercase tracking-wide text-text-dim">
            Current versions
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {latest.map((release) => {
              const product = products.find((p) => p.id === release.product);
              return (
                <Link
                  key={release.product}
                  href={`/changelog/${release.product}`}
                  className="rounded-xl border border-border bg-surface-raised p-4 transition-colors hover:border-gold/40"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-bold text-foreground">{release.productName}</span>
                    <span className="font-mono text-sm text-gold">v{release.version}</span>
                  </div>
                  <p className="mt-1.5 text-sm leading-6 text-text-muted">{product?.blurb}</p>
                </Link>
              );
            })}
          </div>
        </section>

        <section aria-labelledby="all">
          <h2 id="all" className="mb-4 text-sm font-bold uppercase tracking-wide text-text-dim">
            All releases
          </h2>
          <div className="space-y-3">
            {releases.map((release) => (
              <ReleaseCard key={release.tag} release={release} showProduct />
            ))}
          </div>
        </section>
      </main>

      <Footer />
    </>
  );
}
