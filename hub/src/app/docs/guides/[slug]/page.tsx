import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, BookOpen, ExternalLink } from "lucide-react";
import { getGuide, getGuides } from "@/lib/docs";
import { Markdown } from "../../_components/Markdown";

/**
 * Do not set `dynamicParams = false` here. OpenNext runs with a dummy
 * incremental cache, so every prerendered page misses the cache at runtime.
 * Plain static routes survive that by re-rendering, but a disallowed dynamic
 * param turns the miss into a hard 404. Unknown slugs are still rejected below
 * via `notFound()`.
 */
export function generateStaticParams() {
  return getGuides().map((guide) => ({ slug: guide.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const guide = getGuide(slug);
  if (!guide) return { title: "Guide | MJOLNIR Docs" };
  return {
    title: `${guide.title} | MJOLNIR Guides`,
    description: guide.summary.slice(0, 200),
  };
}

export default async function GuidePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const guide = getGuide(slug);
  if (!guide) notFound();

  return (
    <main className="mx-auto max-w-4xl">
      <Link
        href="/docs/guides"
        className="inline-flex items-center gap-2 text-sm text-text-muted hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Guides
      </Link>

      <header className="mt-6 border-b border-border pb-9">
        <div className="flex items-start gap-4">
          <BookOpen className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div className="min-w-0">
            <h1 className="break-words text-3xl font-black sm:text-4xl">{guide.title}</h1>
            {guide.meta.length > 0 && (
              <dl className="mt-5 grid grid-cols-1 gap-x-5 text-sm sm:grid-cols-[150px_1fr]">
                {guide.meta.map(({ label, value }) => (
                  <div key={label} className="contents">
                    <dt className="py-1 font-semibold text-text-dim">{label}</dt>
                    <dd className="break-words py-1 text-xs text-text-muted sm:text-sm">{value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        </div>
      </header>

      <article className="py-9">
        <Markdown>{guide.body}</Markdown>
      </article>

      <footer className="border-t border-border py-9">
        <a
          href={guide.sourcePath}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 text-sm text-gold hover:underline"
        >
          View the Markdown source on GitHub
          <ExternalLink className="h-4 w-4" />
        </a>
      </footer>
    </main>
  );
}
