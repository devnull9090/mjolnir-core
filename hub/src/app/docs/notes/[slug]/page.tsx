import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ExternalLink, FileText } from "lucide-react";
import { getDocNote, getDocNotes } from "@/lib/docs";
import { Markdown } from "../../_components/Markdown";

export const dynamicParams = false;

export function generateStaticParams() {
  return getDocNotes().map((note) => ({ slug: note.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const note = getDocNote(slug);
  if (!note) return { title: "Research note | MJOLNIR Docs" };
  return {
    title: `${note.title} | MJOLNIR Docs`,
    description: note.summary.slice(0, 200),
  };
}

export default async function DocNotePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const note = getDocNote(slug);
  if (!note) notFound();

  return (
    <main className="mx-auto max-w-4xl">
      <Link
        href="/docs/notes"
        className="inline-flex items-center gap-2 text-sm text-text-muted hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Research notes
      </Link>

      <header className="mt-6 border-b border-border pb-9">
        <div className="flex items-start gap-4">
          <FileText className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div className="min-w-0">
            <h1 className="break-words text-3xl font-black sm:text-4xl">{note.title}</h1>
            {note.meta.length > 0 && (
              <dl className="mt-5 grid gap-x-5 text-sm sm:grid-cols-[150px_1fr]">
                {note.meta.map(({ label, value }) => (
                  <div key={label} className="contents">
                    <dt className="py-1 font-semibold text-text-dim">{label}</dt>
                    <dd className="break-all py-1 font-mono text-xs text-text-muted sm:text-sm">
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        </div>
        <p className="mt-6 text-xs leading-6 text-text-dim">
          Raw investigation log, rendered from the repository. Curated summaries live under{" "}
          <Link href="/docs" className="text-gold hover:underline">
            Documentation
          </Link>
          .
        </p>
      </header>

      <article className="py-9">
        <Markdown>{note.body}</Markdown>
      </article>

      <footer className="border-t border-border py-9">
        <a
          href={note.sourcePath}
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
