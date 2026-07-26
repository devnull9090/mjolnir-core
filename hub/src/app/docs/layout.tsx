import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Binary, BookOpen, Code, FileText, FlaskConical, Package } from "lucide-react";
import { getDocNotes } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Docs | MJOLNIR Core",
  description:
    "Technical documentation and evidence-based reverse-engineering research for Halo Campaign Evolved.",
};

const researchLinks = [
  {
    href: "/docs/research/tag-data",
    label: "Blam tag data",
    icon: Package,
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
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 lg:px-8">
          <Link href="/" className="flex items-center gap-3">
            <Image
              src="/logo-transparent.png"
              alt="MJOLNIR Core"
              width={34}
              height={34}
              className="object-contain"
            />
            <span className="font-bold text-gold">MJOLNIR</span>
            <span className="text-xs font-semibold uppercase text-text-muted">Docs</span>
          </Link>
          <nav className="flex items-center gap-5 text-sm text-text-muted" aria-label="Primary">
            <Link href="/mods" className="hidden hover:text-foreground sm:block">
              Mods
            </Link>
            <Link href="/download" className="hidden hover:text-foreground sm:block">
              Download
            </Link>
            <Link
              href="https://github.com/devnull9090/mjolnir-core"
              target="_blank"
              className="flex items-center gap-2 hover:text-foreground"
            >
              <Code className="h-4 w-4" />
              <span className="hidden sm:inline">GitHub</span>
            </Link>
          </nav>
        </div>
      </header>

      <nav
        className="flex gap-2 overflow-x-auto border-b border-border px-5 py-3 lg:hidden"
        aria-label="Documentation"
      >
        <Link
          href="/docs"
          className="shrink-0 border border-border px-3 py-2 text-xs font-semibold text-text-muted"
        >
          Overview
        </Link>
        {researchLinks.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className="shrink-0 border border-border px-3 py-2 text-xs font-semibold text-text-muted"
          >
            {label}
          </Link>
        ))}
        <Link
          href="/docs/notes"
          className="shrink-0 border border-border px-3 py-2 text-xs font-semibold text-text-muted"
        >
          Notes
        </Link>
      </nav>

      <div className="mx-auto grid max-w-7xl lg:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="hidden min-h-[calc(100vh-4rem)] border-r border-border px-6 py-10 lg:block">
          <nav className="sticky top-24 space-y-8" aria-label="Documentation">
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

        <div className="min-w-0 px-5 py-10 sm:px-8 lg:px-12 lg:py-14">{children}</div>
      </div>

      <footer className="border-t border-border px-5 py-6 text-center text-xs text-text-dim">
        MJOLNIR Core research documentation. Game binaries and proprietary assets are not distributed.
      </footer>
    </div>
  );
}