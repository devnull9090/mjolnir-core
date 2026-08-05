import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, ExternalLink, Tag } from "lucide-react";

import {
  getAdjacentReleases,
  getProduct,
  getRelease,
  getReleases,
} from "@/lib/changelog";
import { Navbar } from "../../../components/Navbar";
import { Footer } from "../../../components/Footer";
import { Markdown } from "../../../docs/_components/Markdown";

/** See the note in ../page.tsx: `dynamicParams` must stay on under OpenNext. */
export function generateStaticParams() {
  return getReleases().map((r) => ({ product: r.product, version: r.version }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ product: string; version: string }>;
}): Promise<Metadata> {
  const { product, version } = await params;
  const release = getRelease(product, version);
  if (!release) return { title: "Release notes | MJOLNIR Core" };

  const url = `https://mjolnircore.com${release.path}`;

  return {
    // Product, version and headline: the three things someone searching
    // "mjolnir launcher 0.4.1" or "tag editor audio not working" needs to see
    // in a result to know it is the right one.
    title: `${release.productName} ${release.version} — ${release.title} | MJOLNIR Core`,
    description: release.summary,
    alternates: { canonical: url },
    openGraph: {
      title: `${release.productName} ${release.version} — ${release.title}`,
      description: release.summary,
      url,
      siteName: "MJOLNIR Core",
      type: "article",
      publishedTime: `${release.date}T00:00:00.000Z`,
    },
  };
}

export default async function ReleasePage({
  params,
}: {
  params: Promise<{ product: string; version: string }>;
}) {
  const { product: productId, version } = await params;
  const release = getRelease(productId, version);
  if (!release) notFound();

  const product = getProduct(productId);
  const { newer, older } = getAdjacentReleases(release);

  const url = `https://mjolnircore.com${release.path}`;
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "TechArticle",
        headline: `${release.productName} ${release.version} — ${release.title}`,
        description: release.summary,
        datePublished: `${release.date}T00:00:00.000Z`,
        url,
        mainEntityOfPage: url,
        author: { "@type": "Organization", name: "MJOLNIR Core" },
        publisher: { "@type": "Organization", name: "MJOLNIR Core" },
        about: {
          "@type": "SoftwareApplication",
          name: release.productName,
          softwareVersion: release.version,
          applicationCategory: "GameApplication",
          operatingSystem: "Windows",
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          {
            "@type": "ListItem",
            position: 1,
            name: "Changelog",
            item: "https://mjolnircore.com/changelog",
          },
          {
            "@type": "ListItem",
            position: 2,
            name: release.productName,
            item: `https://mjolnircore.com/changelog/${release.product}`,
          },
          { "@type": "ListItem", position: 3, name: release.version, item: url },
        ],
      },
    ],
  };

  return (
    <>
      <Navbar />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <main className="mx-auto max-w-3xl px-4 pt-32 pb-24 sm:px-6 md:pt-36">
        <Link
          href={`/changelog/${release.product}`}
          className="inline-flex items-center gap-2 text-sm text-text-muted hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          {release.productName} changelog
        </Link>

        <header className="mt-6 border-b border-border pb-8">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span className="rounded bg-surface-hover px-2 py-0.5 text-xs font-medium text-text-muted">
              {release.productName}
            </span>
            <span className="font-mono text-sm font-semibold text-gold">v{release.version}</span>
            <time dateTime={release.date} className="text-sm text-text-dim">
              {release.date}
            </time>
          </div>

          <h1 className="mt-4 break-words text-3xl font-black text-foreground sm:text-4xl">
            {release.title}
          </h1>
          <p className="mt-4 text-lg leading-8 text-text-muted">{release.summary}</p>

          <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            <a
              href={release.releaseUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-gold hover:underline"
            >
              <Tag className="h-4 w-4" />
              {release.tag} on GitHub
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
            {product?.docsUrl && (
              <Link href={product.docsUrl} className="text-text-muted hover:text-foreground">
                Documentation
              </Link>
            )}
          </div>
        </header>

        <article className="py-9">
          <Markdown>{release.body}</Markdown>
        </article>

        <nav
          className="grid grid-cols-1 gap-3 border-t border-border pt-8 sm:grid-cols-2"
          aria-label="Adjacent releases"
        >
          {older ? (
            <Link
              href={older.path}
              className="rounded-xl border border-border p-4 transition-colors hover:border-gold/40"
            >
              <span className="flex items-center gap-1.5 text-xs text-text-dim">
                <ArrowLeft className="h-3.5 w-3.5" />
                Previous
              </span>
              <span className="mt-1 block font-mono text-sm text-gold">v{older.version}</span>
              <span className="mt-0.5 block text-sm text-text-muted">{older.title}</span>
            </Link>
          ) : (
            <span />
          )}
          {newer && (
            <Link
              href={newer.path}
              className="rounded-xl border border-border p-4 transition-colors hover:border-gold/40 sm:text-right"
            >
              <span className="flex items-center gap-1.5 text-xs text-text-dim sm:justify-end">
                Next
                <ArrowRight className="h-3.5 w-3.5" />
              </span>
              <span className="mt-1 block font-mono text-sm text-gold">v{newer.version}</span>
              <span className="mt-0.5 block text-sm text-text-muted">{newer.title}</span>
            </Link>
          )}
        </nav>

        <footer className="mt-8 border-t border-border pt-8">
          <a
            href={release.sourcePath}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 text-sm text-text-dim hover:text-gold"
          >
            View this entry&apos;s Markdown source on GitHub
            <ExternalLink className="h-4 w-4" />
          </a>
        </footer>
      </main>

      <Footer />
    </>
  );
}
