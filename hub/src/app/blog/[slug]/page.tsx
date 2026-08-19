import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, ExternalLink } from "lucide-react";

import { getAdjacentPosts, getPost, getPosts } from "@/lib/blog";
import { Navbar } from "../../components/Navbar";
import { Footer } from "../../components/Footer";
import { Markdown } from "../../docs/_components/Markdown";

/**
 * Do not set `dynamicParams = false` here — same OpenNext incremental-cache
 * reasoning as `docs/notes/[slug]`. Unknown slugs are rejected via
 * `notFound()` below.
 */
export function generateStaticParams() {
  return getPosts().map((post) => ({ slug: post.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = getPost(slug);
  if (!post) return { title: "Blog | MJOLNIR Core" };
  return {
    title: `${post.title} | MJOLNIR Core`,
    description: post.summary.slice(0, 200),
    alternates: { canonical: `https://mjolnircore.com/blog/${post.slug}` },
    openGraph: {
      title: post.title,
      description: post.summary,
      url: `https://mjolnircore.com/blog/${post.slug}`,
      siteName: "MJOLNIR Core",
      type: "article",
      publishedTime: post.date,
      authors: [post.author],
    },
  };
}

function formatDate(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

export default async function BlogPostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const post = getPost(slug);
  if (!post) notFound();
  const { newer, older } = getAdjacentPosts(post);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: post.title,
    description: post.summary,
    datePublished: post.date,
    author: { "@type": "Organization", name: post.author },
    url: `https://mjolnircore.com/blog/${post.slug}`,
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
          href="/blog"
          className="inline-flex items-center gap-2 text-sm text-text-muted hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Blog
        </Link>

        <header className="mt-6 border-b border-border pb-9">
          <h1 className="break-words text-3xl font-black sm:text-4xl">{post.title}</h1>
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-text-muted">
            <time dateTime={post.date} className="font-mono text-xs">
              {formatDate(post.date)}
            </time>
            <span>{post.author}</span>
            {post.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-md bg-gold/10 px-2 py-0.5 font-mono text-xs text-gold"
              >
                {tag}
              </span>
            ))}
          </div>
        </header>

        <article className="py-9">
          <Markdown>{post.body}</Markdown>
        </article>

        <footer className="border-t border-border py-9">
          <div className="flex flex-wrap items-center justify-between gap-4 text-sm">
            {older ? (
              <Link
                href={`/blog/${older.slug}`}
                className="inline-flex items-center gap-2 text-text-muted hover:text-foreground"
              >
                <ArrowLeft className="h-4 w-4" />
                {older.title}
              </Link>
            ) : (
              <span />
            )}
            {newer && (
              <Link
                href={`/blog/${newer.slug}`}
                className="inline-flex items-center gap-2 text-text-muted hover:text-foreground"
              >
                {newer.title}
                <ArrowRight className="h-4 w-4" />
              </Link>
            )}
          </div>
          <a
            href={post.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-6 inline-flex items-center gap-2 text-xs text-text-dim hover:text-gold"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            View source on GitHub
          </a>
        </footer>
      </main>

      <Footer />
    </>
  );
}
