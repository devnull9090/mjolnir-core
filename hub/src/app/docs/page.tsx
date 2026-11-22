import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Binary,
  BookOpen,
  Boxes,
  Braces,
  Database,
  FlaskConical,
  Hammer,
  Map as MapIcon,
  Package,
  Swords,
  Terminal,
  Wrench,
} from "lucide-react";
import { docHref, getDocSections } from "@/lib/docs";
import { getTotals } from "@/lib/tags";
import { getConsoleTotals } from "@/lib/console";
import { DocsSearchButton } from "./_components/DocsSearch";
import { EvidenceBadge, type EvidenceLevel } from "./_components/EvidenceBadge";

const totals = getTotals();
const consoleTotals = getConsoleTotals();

export const metadata: Metadata = {
  title: "Documentation | MJOLNIR Core",
  description:
    "Guides, feature documentation and reverse-engineering notes for MJOLNIR Core: multiplayer, Forge, maps, modding tools and the game's internals.",
};

/** One icon per section of docs/site.json; a section added there without one gets the book. */
const sectionIcons: Record<string, typeof BookOpen> = {
  guides: BookOpen,
  multiplayer: Swords,
  forge: Hammer,
  maps: MapIcon,
  internals: Binary,
  project: Boxes,
};

// Counts come from the generated data, never typed in: a number written here
// by hand was true for the build it was written against and no later one.
const references = [
  {
    href: "/docs/tags",
    title: "Tag definitions",
    description: `Field-level reference for all ${totals.groups} tag groups: ${totals.fields.toLocaleString()} fields with names, types, byte offsets and enum options, generated from the shipped game data.`,
    icon: Database,
  },
  {
    href: "/docs/console",
    title: "Console commands",
    description: `Every Blam console function in the game: ${consoleTotals.names.toLocaleString()} names with signatures and return types, ${consoleTotals.live.toLocaleString()} of them live in this build, plus ${consoleTotals.globals} engine globals.`,
    icon: Terminal,
  },
  {
    href: "/docs/api",
    title: "Hub API",
    description:
      "The hub's public HTTP API, as an OpenAPI reference: mods, maps, lobbies, matches, players and publishing.",
    icon: Braces,
  },
];

const research = [
  {
    href: "/docs/research/tag-data",
    title: "Blam tag data",
    description:
      "Real Blam tag files ship inside the game's Unreal packages. Container format, inventory, and the simulation-versus-rendering split.",
    status: "Verified" as EvidenceLevel,
    icon: Package,
  },
  {
    href: "/docs/research/tag-format",
    title: "Self-describing tag layout",
    description:
      "Every tag carries its own field definitions: the blay layout section ships field names, type names and enum options for every group.",
    status: "Verified" as EvidenceLevel,
    icon: Braces,
  },
  {
    href: "/docs/research/halo-simulation",
    title: "HaloSimulation_tag_release.dll",
    description:
      "Build fingerprint, factory ABI, shell object layout, interface tables, and the UE5 loader call path.",
    status: "Verified" as EvidenceLevel,
    icon: Binary,
  },
  {
    href: "/docs/research/multiplayer",
    title: "Multiplayer viability (history)",
    description:
      "The first investigation into whether the campaign build still held working multiplayer. It did: what it proposed has since shipped, and the Multiplayer section documents what runs today.",
    status: "Observed" as EvidenceLevel,
    icon: FlaskConical,
  },
];

const evidenceLevels: Array<{ level: EvidenceLevel; meaning: string }> = [
  { level: "Verified", meaning: "Reproduced by an executable check or direct decompilation." },
  { level: "Observed", meaning: "Present in an artifact, but runtime reachability is not proven." },
  { level: "Hypothesis", meaning: "A testable interpretation of current evidence." },
  { level: "Unverified", meaning: "Proposed behavior that still needs a discriminating test." },
];

export default function DocsPage() {
  const sections = getDocSections();
  const guides = sections.find((section) => section.kind === "guide");
  const topics = sections.filter((section) => section.kind !== "guide");

  return (
    <main id="main" className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-10">
        <p className="mb-3 text-xs font-bold uppercase text-gold">MJOLNIR Core</p>
        <h1 className="text-3xl font-black sm:text-4xl">Documentation</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-text-muted">
          How to mod Halo Campaign Evolved with MJOLNIR, how the multiplayer, Forge and maps it
          ships work, and the reverse-engineering notes underneath all of it.
        </p>
        <div className="mt-7 max-w-2xl">
          <DocsSearchButton variant="hero" />
        </div>
      </header>

      {guides && (
        <section className="py-10" aria-labelledby="guides-heading">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 id="guides-heading" className="text-xl font-bold">
              Guides
            </h2>
            <Link href="/docs/guides" className="text-sm font-semibold text-gold hover:underline">
              View all
            </Link>
          </div>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-text-muted">
            Follow one start to finish and you will have done the thing. New here? Start with{" "}
            <Link href="/docs/guides/getting-started" className="text-gold hover:underline">
              your first tag edit
            </Link>
            . Here to play rather than build?{" "}
            <Link href="/multiplayer" className="text-gold hover:underline">
              Multiplayer
            </Link>{" "}
            has the three steps to a match.
          </p>
          <div className="mt-5 grid grid-cols-1 gap-x-8 md:grid-cols-2">
            {guides.docs.map((guide) => (
              <Link
                key={guide.slug}
                href={docHref(guides, guide)}
                className="group flex items-start gap-3 border-t border-border py-4"
              >
                <BookOpen className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                <div className="min-w-0">
                  <p className="font-semibold group-hover:text-gold">{guide.title}</p>
                  <p className="mt-1 line-clamp-2 text-sm leading-6 text-text-muted">
                    {guide.summary}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section className="border-t border-border py-10" aria-labelledby="topics-heading">
        <h2 id="topics-heading" className="text-xl font-bold">
          By subject
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-text-muted">
          What each feature does and how it is built, written as the work happened. A page that
          describes a design rather than something shipped says so at its top.
        </p>
        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
          {topics.map((section) => {
            const Icon = sectionIcons[section.id] ?? Wrench;
            return (
              <div key={section.id} className="flex flex-col border border-border bg-surface p-5">
                <div className="flex items-center justify-between gap-4">
                  <Icon className="h-5 w-5 text-gold" />
                  <span className="font-mono text-xs text-text-dim">
                    {section.docs.length} pages
                  </span>
                </div>
                <h3 className="mt-4 text-lg font-bold">
                  <Link href={`/docs/notes#${section.id}`} className="hover:text-gold">
                    {section.title}
                  </Link>
                </h3>
                <p className="mt-2 text-sm leading-6 text-text-muted">{section.blurb}</p>
                <ul className="mt-4 space-y-1.5 text-sm">
                  {section.docs.slice(0, 4).map((doc) => (
                    <li key={doc.slug}>
                      <Link
                        href={docHref(section, doc)}
                        className="line-clamp-1 text-text-muted hover:text-gold"
                      >
                        {doc.title}
                      </Link>
                    </li>
                  ))}
                </ul>
                <Link
                  href={`/docs/notes#${section.id}`}
                  className="mt-auto flex items-center gap-2 pt-5 text-sm font-semibold text-gold hover:underline"
                >
                  All of {section.title} <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            );
          })}
        </div>
      </section>

      <section className="border-t border-border py-10" aria-labelledby="reference-heading">
        <h2 id="reference-heading" className="text-xl font-bold">
          Reference
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-text-muted">
          Generated from the game&apos;s own data and from the hub&apos;s code, so it changes when
          they do.
        </p>
        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
          {references.map(({ href, title, description, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="group border border-border bg-surface p-5 transition-colors hover:border-gold/40"
            >
              <Icon className="h-5 w-5 text-gold" />
              <h3 className="mt-4 text-base font-bold group-hover:text-gold">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-text-muted">{description}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="border-t border-border py-10" aria-labelledby="research-heading">
        <h2 id="research-heading" className="text-xl font-bold">
          Research summaries
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-text-muted">
          Curated findings about the game&apos;s UE5 and Blam architecture. Claims are separated
          from hypotheses so each result can be checked and revised as the game changes.
        </p>
        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
          {research.map(({ href, title, description, status, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="group border border-border bg-surface p-5 transition-colors hover:border-gold/40"
            >
              <div className="flex items-start justify-between gap-4">
                <Icon className="h-5 w-5 text-gold" />
                <EvidenceBadge level={status} />
              </div>
              <h3 className="mt-5 text-lg font-bold group-hover:text-gold">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-text-muted">{description}</p>
            </Link>
          ))}
        </div>
        <h3 className="mt-10 text-sm font-bold uppercase text-text-dim">Evidence model</h3>
        <div className="mt-3 divide-y divide-border border-y border-border">
          {evidenceLevels.map(({ level, meaning }) => (
            <div key={level} className="grid grid-cols-1 gap-3 py-4 sm:grid-cols-[110px_1fr] sm:items-center">
              <EvidenceBadge level={level} />
              <p className="text-sm leading-6 text-text-muted">{meaning}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
