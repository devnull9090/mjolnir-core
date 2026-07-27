import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen } from "lucide-react";
import { getGuides } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Guides | MJOLNIR Docs",
  description:
    "Step-by-step guides for modding Halo Campaign Evolved: editing a tag, getting it into the game, and driving the game from a script.",
};

export default function GuidesPage() {
  const guides = getGuides();

  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-10">
        <p className="mb-3 text-xs font-bold uppercase text-gold">MJOLNIR Guides</p>
        <h1 className="text-3xl font-black sm:text-4xl">Guides</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-text-muted">
          Follow one start to finish and you will have done the thing. Every step here has been run
          against the real game. For the working history behind them — including the turns that were
          wrong — see{" "}
          <Link href="/docs/notes" className="text-gold hover:underline">
            research notes
          </Link>
          .
        </p>
      </header>

      <section className="py-10" aria-labelledby="guides-heading">
        <h2 id="guides-heading" className="sr-only">
          Available guides
        </h2>
        <div className="grid grid-cols-1 gap-4">
          {guides.map((guide) => (
            <Link
              key={guide.slug}
              href={`/docs/guides/${guide.slug}`}
              className="group border border-border bg-surface p-5 transition-colors hover:border-gold/40"
            >
              <div className="flex items-start gap-4">
                <BookOpen className="mt-1 h-5 w-5 shrink-0 text-gold" />
                <div className="min-w-0">
                  <h3 className="break-words text-lg font-bold group-hover:text-gold">
                    {guide.title}
                  </h3>
                  {guide.meta.length > 0 && (
                    <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-dim">
                      {guide.meta.slice(0, 3).map(({ label, value }) => (
                        <span key={label}>
                          {label}: <span className="text-text-muted">{value}</span>
                        </span>
                      ))}
                    </p>
                  )}
                  <p className="mt-3 line-clamp-3 text-sm leading-6 text-text-muted">
                    {guide.summary}
                  </p>
                  <span className="mt-4 flex items-center gap-2 text-sm font-semibold text-gold">
                    Read guide <ArrowRight className="h-4 w-4" />
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
