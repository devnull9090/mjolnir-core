import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, FileText } from "lucide-react";
import { getDocNotes } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Research notes | MJOLNIR Docs",
  description:
    "Raw MJOLNIR Core investigation logs, reproduction steps, and working notes rendered from the repository.",
};

export default function DocNotesPage() {
  const notes = getDocNotes();

  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-10">
        <p className="mb-3 text-xs font-bold uppercase text-gold">MJOLNIR Research</p>
        <h1 className="text-3xl font-black sm:text-4xl">Research notes</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-text-muted">
          Raw investigation logs rendered straight from the repository. These keep the full working
          history, including superseded conclusions. For curated summaries, start at{" "}
          <Link href="/docs" className="text-gold hover:underline">
            Documentation
          </Link>
          .
        </p>
      </header>

      <section className="py-10" aria-labelledby="notes-heading">
        <h2 id="notes-heading" className="sr-only">
          Available notes
        </h2>
        <div className="grid gap-4">
          {notes.map((note) => (
            <Link
              key={note.slug}
              href={`/docs/notes/${note.slug}`}
              className="group border border-border bg-surface p-5 transition-colors hover:border-gold/40"
            >
              <div className="flex items-start gap-4">
                <FileText className="mt-1 h-5 w-5 shrink-0 text-gold" />
                <div className="min-w-0">
                  <h3 className="text-lg font-bold group-hover:text-gold">{note.title}</h3>
                  {note.meta.length > 0 && (
                    <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-dim">
                      {note.meta.slice(0, 3).map(({ label, value }) => (
                        <span key={label}>
                          {label}: <span className="font-mono">{value}</span>
                        </span>
                      ))}
                    </p>
                  )}
                  <p className="mt-3 line-clamp-3 text-sm leading-6 text-text-muted">
                    {note.summary}
                  </p>
                  <span className="mt-4 flex items-center gap-2 text-sm font-semibold text-gold">
                    Read note <ArrowRight className="h-4 w-4" />
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
