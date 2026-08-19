import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Tag } from "lucide-react";

import { getAllTags, getPostsByTag } from "@/lib/blog";
import { Navbar } from "../../../components/Navbar";
import { Footer } from "../../../components/Footer";
import { PostCard } from "../../_components/PostCard";
import { TagChip } from "../../_components/TagChip";

/**
 * Do not set `dynamicParams = false` here — same OpenNext incremental-cache
 * reasoning as `blog/[slug]`. Unknown tags are rejected via `notFound()`.
 */
export function generateStaticParams() {
  return getAllTags().map((tag) => ({ tag }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ tag: string }>;
}): Promise<Metadata> {
  const { tag } = await params;
  if (!getAllTags().includes(tag)) return { title: "Blog | MJOLNIR Core" };
  const description = `Every MJOLNIR Core post tagged "${tag}" — what Halo Campaign Evolved updates change under the hood, uncovered tag by tag.`;
  return {
    title: `Posts tagged ${tag} | MJOLNIR Core`,
    description,
    alternates: { canonical: `https://mjolnircore.com/blog/tag/${tag}` },
    openGraph: {
      title: `Posts tagged ${tag}`,
      description,
      url: `https://mjolnircore.com/blog/tag/${tag}`,
      siteName: "MJOLNIR Core",
      type: "website",
    },
  };
}

export default async function BlogTagPage({
  params,
}: {
  params: Promise<{ tag: string }>;
}) {
  const { tag } = await params;
  if (!getAllTags().includes(tag)) notFound();
  const posts = getPostsByTag(tag);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: `MJOLNIR Core blog — posts tagged ${tag}`,
    url: `https://mjolnircore.com/blog/tag/${tag}`,
    hasPart: posts.map((post) => ({
      "@type": "BlogPosting",
      headline: post.title,
      datePublished: post.date,
      url: `https://mjolnircore.com/blog/${post.slug}`,
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
          href="/blog"
          className="inline-flex items-center gap-2 text-sm text-text-muted hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          All posts
        </Link>

        <header className="mt-6 mb-12">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gold/10 text-gold">
              <Tag className="h-6 w-6" />
            </span>
            <h1 className="text-3xl font-black text-foreground sm:text-4xl">
              <span className="font-mono text-gold">{tag}</span>
            </h1>
          </div>
          <p className="mt-4 max-w-2xl text-lg text-text-muted">
            {posts.length === 1 ? "One post" : `${posts.length} posts`} tagged{" "}
            <span className="font-mono">{tag}</span>, newest first.
          </p>
          <div className="mt-4 flex flex-wrap gap-1.5">
            {getAllTags()
              .filter((t) => t !== tag)
              .map((t) => (
                <TagChip key={t} tag={t} />
              ))}
          </div>
        </header>

        <div className="space-y-3">
          {posts.map((post) => (
            <PostCard key={post.slug} post={post} />
          ))}
        </div>
      </main>

      <Footer />
    </>
  );
}
