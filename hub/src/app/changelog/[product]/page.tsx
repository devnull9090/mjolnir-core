import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { getProduct, getProducts, getReleasesFor } from "@/lib/changelog";
import { Navbar } from "../../components/Navbar";
import { Footer } from "../../components/Footer";
import { ReleaseCard } from "../_components/ReleaseCard";

/**
 * Do not set `dynamicParams = false` here. OpenNext runs with a dummy
 * incremental cache, so every prerendered page misses the cache at runtime.
 * Plain static routes survive that by re-rendering, but a disallowed dynamic
 * param turns the miss into a hard 404. Unknown products are still rejected
 * below via `notFound()`.
 */
export function generateStaticParams() {
  return getProducts().map((p) => ({ product: p.id }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ product: string }>;
}): Promise<Metadata> {
  const { product: id } = await params;
  const product = getProduct(id);
  if (!product) return { title: "Changelog | MJOLNIR Core" };

  const releases = getReleasesFor(id);
  const description = `Release notes for ${product.name}, newest first. ${product.blurb}`;

  return {
    title: `${product.name} changelog | MJOLNIR Core`,
    description,
    alternates: {
      canonical: `https://mjolnircore.com/changelog/${id}`,
      types: { "application/rss+xml": "https://mjolnircore.com/changelog/rss.xml" },
    },
    openGraph: {
      title: `${product.name} changelog`,
      description,
      url: `https://mjolnircore.com/changelog/${id}`,
      siteName: "MJOLNIR Core",
      type: "website",
      ...(releases[0] ? { modifiedTime: `${releases[0].date}T00:00:00.000Z` } : {}),
    },
  };
}

export default async function ProductChangelogPage({
  params,
}: {
  params: Promise<{ product: string }>;
}) {
  const { product: id } = await params;
  const product = getProduct(id);
  if (!product) notFound();

  const releases = getReleasesFor(id);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: `${product.name} changelog`,
    numberOfItems: releases.length,
    itemListElement: releases.map((release, index) => ({
      "@type": "ListItem",
      position: index + 1,
      url: `https://mjolnircore.com${release.path}`,
      name: `${product.name} ${release.version} — ${release.title}`,
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
        <Link
          href="/changelog"
          className="inline-flex items-center gap-2 text-sm text-text-muted hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          All products
        </Link>

        <header className="mt-6 mb-10 border-b border-border pb-8">
          <h1 className="text-3xl font-black text-foreground sm:text-4xl">
            {product.name} changelog
          </h1>
          <p className="mt-3 max-w-2xl text-lg text-text-muted">{product.blurb}</p>
          <p className="mt-4 text-sm text-text-dim">
            {releases.length} release{releases.length === 1 ? "" : "s"}
            {releases[0] && (
              <>
                {" · latest "}
                <Link href={releases[0].path} className="font-mono text-gold hover:underline">
                  v{releases[0].version}
                </Link>
              </>
            )}
            {product.docsUrl && (
              <>
                {" · "}
                <Link href={product.docsUrl} className="text-gold hover:underline">
                  Documentation
                </Link>
              </>
            )}
          </p>
        </header>

        <div className="space-y-3">
          {releases.map((release) => (
            <ReleaseCard key={release.tag} release={release} />
          ))}
        </div>
      </main>

      <Footer />
    </>
  );
}
