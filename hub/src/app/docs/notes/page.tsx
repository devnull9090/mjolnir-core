import type { Metadata } from "next";
import Link from "next/link";
import { FileText } from "lucide-react";
import { docHref, getDocSections } from "@/lib/docs";
import { DocsSearchButton } from "../_components/DocsSearch";

export const metadata: Metadata = {
  title: "All documentation by subject | MJOLNIR Docs",
  description:
    "Every MJOLNIR Core doc by subject: multiplayer, Forge, maps and levels, the game's internals, and the project itself.",
};

export default function DocNotesPage() {
  const sections = getDocSections().filter((section) => section.kind !== "guide");

  return (
    <main id="main" className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-10">
        <p className="mb-3 text-xs font-bold uppercase text-gold">MJOLNIR Docs</p>
        <h1 className="text-3xl font-black sm:text-4xl">By subject</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-text-muted">
          Rendered straight from the repository, where they are written as the work happens. They
          keep their history, superseded conclusions included, and a page that describes a design
          rather than something shipped says so at its top. For step-by-step instructions see the{" "}
          <Link href="/docs/guides" className="text-gold hover:underline">
            guides
          </Link>
          .
        </p>
        <div className="mt-7 max-w-2xl">
          <DocsSearchButton variant="hero" />
        </div>
        <nav className="mt-6 flex flex-wrap gap-2" aria-label="Subjects">
          {sections.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted hover:border-gold/40 hover:text-foreground"
            >
              {section.title}{" "}
              <span className="font-mono font-normal text-text-dim">{section.docs.length}</span>
            </a>
          ))}
        </nav>
      </header>

      {sections.map((section) => (
        <section
          key={section.id}
          id={section.id}
          className="scroll-mt-40 border-b border-border py-10 last:border-b-0"
          aria-labelledby={`${section.id}-heading`}
        >
          <h2 id={`${section.id}-heading`} className="text-xl font-bold">
            {section.title}
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-text-muted">{section.blurb}</p>
          <div className="mt-5 divide-y divide-border border-y border-border">
            {section.docs.map((doc) => (
              <Link key={doc.slug} href={docHref(section, doc)} className="group flex items-start gap-3 py-4">
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                <div className="min-w-0">
                  <h3 className="break-words font-semibold group-hover:text-gold">{doc.title}</h3>
                  <p className="mt-1 line-clamp-2 text-sm leading-6 text-text-muted">{doc.summary}</p>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </main>
  );
}
