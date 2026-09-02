import type { Metadata } from "next";
import { Newspaper, Rss } from "lucide-react";

import { getAllTags, getPosts } from "@/lib/blog";
import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { PostCard } from "./_components/PostCard";
import { TagChip } from "./_components/TagChip";

export const metadata: Metadata = {
  title: "Blog | MJOLNIR Core",
  description:
    "Writing from the MJOLNIR Core project — what each Halo Campaign Evolved update changed under the hood, and what we learn taking the game apart.",
  alternates: {
    canonical: "https://mjolnircore.com/blog",
    types: { "application/rss+xml": "https://mjolnircore.com/blog/rss.xml" },
  },
  openGraph: {
    title: "MJOLNIR Core blog",
    description:
      "What each Halo Campaign Evolved update changed under the hood, and what we learn taking the game apart.",
    url: "https://mjolnircore.com/blog",
    siteName: "MJOLNIR Core",
    type: "website",
  },
};

export default function BlogIndexPage() {
  const posts = getPosts();
  const tags = getAllTags();

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Blog",
    name: "MJOLNIR Core blog",
    description: metadata.description,
    url: "https://mjolnircore.com/blog",
    blogPost: posts.slice(0, 50).map((post) => ({
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
        <header className="mb-12">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gold/10 text-gold">
              <Newspaper className="h-6 w-6" />
            </span>
            <h1 className="text-3xl font-black text-foreground sm:text-4xl">Blog</h1>
          </div>
          <p className="mt-4 max-w-2xl text-lg text-text-muted">
            What each game update changed under the hood, and what we learn taking Halo
            Campaign Evolved apart. Newest first.
          </p>
          {tags.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-sm text-text-dim">Filter by tag:</span>
              {tags.map((tag) => (
                <TagChip key={tag} tag={tag} />
              ))}
            </div>
          )}
          <a
            href="/blog/rss.xml"
            className="mt-4 inline-flex items-center gap-2 text-sm text-text-dim hover:text-gold"
          >
            <Rss className="h-4 w-4" />
            Subscribe by RSS
          </a>
        </header>

        <div className="space-y-3">
          {posts.map((post) => (
            <PostCard key={post.slug} post={post} />
          ))}
          {posts.length === 0 && (
            <p className="text-text-muted">Nothing published yet.</p>
          )}
        </div>
      </main>

      <Footer />
    </>
  );
}
