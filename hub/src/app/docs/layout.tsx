import type { Metadata } from "next";
import Link from "next/link";
import { Binary, BookOpen, Braces, Database, FileText, FlaskConical, Package } from "lucide-react";
import { getDocNotes } from "@/lib/docs";
import { Navbar } from "../components/Navbar";

export const metadata: Metadata = {
  title: "Docs | MJOLNIR Core",
  description:
    "Technical documentation and evidence-based reverse-engineering research for Halo Campaign Evolved.",
};

const researchLinks = [
  {
    href: "/docs/tags",
    label: "Tag definitions",
    icon: Database,
  },
  {
    href: "/docs/research/tag-data",
    label: "Blam tag data",
    icon: Package,
  },
  {
    href: "/docs/research/tag-format",
    label: "Self-describing tag layout",
    icon: Braces,
  },
  {
    href: "/docs/research/multiplayer",
    label: "Multiplayer investigation",
    icon: FlaskConical,
  },
  {
    href: "/docs/research/halo-simulation",
    label: "HaloSimulation DLL",
    icon: Binary,
  },
];

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const noteLinks = getDocNotes().map((note) => ({
    href: `/docs/notes/${note.slug}`,
    label: note.title,
  }));
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />

      {/* Docs-specific mobile nav pills */}
      <nav
        className="flex gap-2 overflow-x-auto border-b border-border px-5 py-3 pt-32 md:pt-36 lg:hidden"
        aria-label="Documentation"
      >
        <Link
          href="/docs"
          className="shrink-0 rounded-lg border border-border px-3 py-2 text-xs font-semibold text-text-muted"
        >
          Overview
        </Link>
        {researchLinks.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className="shrink-0 rounded-lg border border-border px-3 py-2 text-xs font-semibold text-text-muted"
          >
            {label}
          </Link>
        ))}
        <Link
          href="/docs/notes"
          className="shrink-0 rounded-lg border border-border px-3 py-2 text-xs font-semibold text-text-muted"
        >
          Notes
        </Link>
      </nav>

      <div className="mx-auto grid grid-cols-1 max-w-7xl lg:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="hidden min-h-[calc(100vh-4rem)] border-r border-border px-6 pt-36 pb-10 lg:block">
          <nav className="sticky top-36 space-y-8" aria-label="Documentation">
            <div>
              <p className="mb-3 text-xs font-bold uppercase text-text-dim">Start</p>
              <Link
                href="/docs"
                className="flex items-center gap-2 py-2 text-sm text-text-muted hover:text-foreground"
              >
                <BookOpen className="h-4 w-4" />
                Documentation
              </Link>
            </div>
            <div>
              <p className="mb-3 text-xs font-bold uppercase text-text-dim">Research</p>
              <div className="space-y-1">
                {researchLinks.map(({ href, label, icon: Icon }) => (
                  <Link
                    key={href}
                    href={href}
                    className="flex items-center gap-2 py-2 text-sm leading-5 text-text-muted hover:text-foreground"
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {label}
                  </Link>
                ))}
              </div>
            </div>
            <div>
              <p className="mb-3 text-xs font-bold uppercase text-text-dim">Notes</p>
              <div className="space-y-1">
                {noteLinks.map(({ href, label }) => (
                  <Link
                    key={href}
                    href={href}
                    className="flex items-start gap-2 py-2 text-sm leading-5 text-text-muted hover:text-foreground"
                  >
                    <FileText className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{label}</span>
                  </Link>
                ))}
              </div>
            </div>
          </nav>
        </aside>

        <div className="min-w-0 px-5 py-10 sm:px-8 lg:px-12 lg:py-14 lg:pt-36">{children}</div>
      </div>

      <footer className="border-t border-border px-5 py-6 text-center text-xs text-text-dim">
        MJOLNIR Core research documentation. Game binaries and proprietary assets are not distributed.
      </footer>
    </div>
  );
}