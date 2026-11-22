import type { Metadata } from "next";
import Link from "next/link";
import { Binary, BookOpen, Braces, Database, FlaskConical, Package, Terminal } from "lucide-react";
import { docHref, getDocSections, getGuides } from "@/lib/docs";
import { getTagGroups } from "@/lib/tags";
import { getConsoleFamilies } from "@/lib/console";
import { Navbar } from "../components/Navbar";
import { DocsSearch, DocsSearchButton, type SearchPage } from "./_components/DocsSearch";
import { DocsSidebar } from "./_components/DocsSidebar";

export const metadata: Metadata = {
  title: "Docs | MJOLNIR Core",
  description:
    "Guides, feature documentation and reverse-engineering notes for MJOLNIR Core and Halo Campaign Evolved.",
};

/**
 * The hand-made pages: references generated from the game's data, and the
 * curated research summaries. The search palette lists them too, so each
 * carries the sentence a result shows.
 */
const referenceLinks = [
  {
    href: "/docs/api",
    label: "API reference",
    icon: Braces,
    description: "The hub's public HTTP API: mods, maps, lobbies, matches, players and publishing.",
  },
  {
    href: "/docs/tags",
    label: "Tag definitions",
    icon: Database,
    description: "Every tag group's fields, with names, types, byte offsets and enum options.",
  },
  {
    href: "/docs/console",
    label: "Console commands",
    icon: Terminal,
    description: "Every Blam console function and engine global, with signatures.",
  },
  {
    href: "/docs/research/tag-data",
    label: "Blam tag data",
    icon: Package,
    description: "The Blam tag files that ship inside Unreal packages: container format and inventory.",
  },
  {
    href: "/docs/research/tag-format",
    label: "Self-describing tag layout",
    icon: Braces,
    description: "How every tag carries its own field definitions in the blay layout section.",
  },
  {
    href: "/docs/research/multiplayer",
    label: "Multiplayer investigation",
    icon: FlaskConical,
    description: "The early investigation into whether the game still held working multiplayer.",
  },
  {
    href: "/docs/research/halo-simulation",
    label: "HaloSimulation DLL",
    icon: Binary,
    description: "The simulation DLL: build fingerprint, factory ABI, interface tables and loader path.",
  },
];

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const sections = getDocSections();
  const sidebar = sections.map((section) => ({
    id: section.id,
    title: section.title,
    href: section.kind === "guide" ? "/docs/guides" : `/docs/notes#${section.id}`,
    links: section.docs.map((doc) => ({ href: docHref(section, doc), label: doc.title })),
  }));

  const pages: SearchPage[] = [
    { href: "/docs", title: "Documentation", description: "Where the docs start: guides, sections and references." },
    { href: "/docs/guides", title: "Guides", description: "Every step-by-step guide." },
    ...referenceLinks.map(({ href, label, description }) => ({ href, title: label, description })),
  ];
  const suggestions: SearchPage[] = getGuides()
    .slice(0, 5)
    .map((guide) => ({ href: `/docs/guides/${guide.slug}`, title: guide.title, description: guide.summary }));
  const tagGroups = getTagGroups().map(({ slug, name, group }) => ({ slug, name, group }));
  const consoleFamilies = Object.fromEntries(
    getConsoleFamilies().map((family) => [family.slug, family.title]),
  );

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />
      <DocsSearch
        pages={pages}
        tagGroups={tagGroups}
        consoleFamilies={consoleFamilies}
        suggestions={suggestions}
      />

      {/* Docs-specific mobile nav pills */}
      <nav
        className="flex gap-2 overflow-x-auto border-b border-border px-5 py-3 pt-32 md:pt-36 lg:hidden"
        aria-label="Documentation"
      >
        <DocsSearchButton variant="pill" />
        <Link
          href="/docs"
          className="shrink-0 rounded-lg border border-border px-3 py-2 text-xs font-semibold text-text-muted"
        >
          Overview
        </Link>
        {sidebar.map(({ id, title, href }) => (
          <Link
            key={id}
            href={href}
            className="shrink-0 rounded-lg border border-border px-3 py-2 text-xs font-semibold text-text-muted"
          >
            {title}
          </Link>
        ))}
        {referenceLinks.slice(0, 3).map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className="shrink-0 rounded-lg border border-border px-3 py-2 text-xs font-semibold text-text-muted"
          >
            {label}
          </Link>
        ))}
      </nav>

      <div className="mx-auto grid grid-cols-1 max-w-7xl lg:grid-cols-[270px_minmax(0,1fr)]">
        <aside className="hidden min-h-[calc(100vh-4rem)] border-r border-border pl-6 pt-36 lg:block">
          <nav
            className="sticky top-36 max-h-[calc(100vh-9rem)] space-y-6 overflow-y-auto pb-10 pr-5"
            aria-label="Documentation"
          >
            <div className="space-y-2">
              <DocsSearchButton />
              <Link
                href="/docs"
                className="flex items-center gap-2 py-2 text-sm text-text-muted hover:text-foreground"
              >
                <BookOpen className="h-4 w-4" />
                Documentation
              </Link>
            </div>
            <DocsSidebar sections={sidebar} />
            <div>
              <p className="mb-2 text-xs font-bold uppercase text-text-dim">Reference</p>
              <div className="space-y-0.5">
                {referenceLinks.map(({ href, label, icon: Icon }) => (
                  <Link
                    key={href}
                    href={href}
                    className="flex items-center gap-2 py-1.5 text-sm leading-5 text-text-muted hover:text-foreground"
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {label}
                  </Link>
                ))}
              </div>
            </div>
          </nav>
        </aside>

        <div className="min-w-0 px-5 py-10 sm:px-8 lg:px-12 lg:py-14 lg:pt-36">{children}</div>
      </div>

      <footer className="border-t border-border px-5 py-6 text-center text-xs text-text-dim">
        MJOLNIR Core documentation. Game binaries and proprietary assets are not distributed.
      </footer>
    </div>
  );
}
