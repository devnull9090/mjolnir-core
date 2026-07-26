import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Binary, FileText, FlaskConical, Package } from "lucide-react";
import { getDocNotes } from "@/lib/docs";
import { EvidenceBadge, type EvidenceLevel } from "./_components/EvidenceBadge";

export const metadata: Metadata = {
  title: "Technical Documentation | MJOLNIR Core",
  description: "Curated MJOLNIR Core research, architecture notes, and reproducible findings.",
};

const research = [
  {
    href: "/docs/research/tag-data",
    title: "Blam tag data",
    description:
      "12,328 real Blam tag files ship inside Unreal packages across 101 classic tag groups. Container format, inventory, and the simulation-versus-rendering split.",
    status: "Verified" as EvidenceLevel,
    icon: Package,
  },
  {
    href: "/docs/research/multiplayer",
    title: "Multiplayer viability",
    description:
      "Inventory of retained multiplayer systems, packed content, campaign worlds, and the shortest route to a CTF prototype.",
    status: "Observed" as EvidenceLevel,
    icon: FlaskConical,
  },
  {
    href: "/docs/research/halo-simulation",
    title: "HaloSimulation_tag_release.dll",
    description:
      "Build fingerprint, factory ABI, shell object layout, interface tables, and the UE5 loader call path.",
    status: "Verified" as EvidenceLevel,
    icon: Binary,
  },
];

const evidenceLevels: Array<{ level: EvidenceLevel; meaning: string }> = [
  { level: "Verified", meaning: "Reproduced by an executable check or direct decompilation." },
  { level: "Observed", meaning: "Present in an artifact, but runtime reachability is not proven." },
  { level: "Hypothesis", meaning: "A testable interpretation of current evidence." },
  { level: "Unverified", meaning: "Proposed behavior that still needs a discriminating test." },
];

export default function DocsPage() {
  const notes = getDocNotes();

  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-10">
        <p className="mb-3 text-xs font-bold uppercase text-gold">MJOLNIR Research</p>
        <h1 className="text-3xl font-black sm:text-4xl">Technical documentation</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-text-muted">
          Curated findings for Halo Campaign Evolved&apos;s UE5 and Blam architecture. Claims are
          separated from hypotheses so each result can be checked and revised as the game changes.
        </p>
      </header>

      <section className="py-10" aria-labelledby="research-heading">
        <h2 id="research-heading" className="text-xl font-bold">
          Active research
        </h2>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
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
              <span className="mt-5 flex items-center gap-2 text-sm font-semibold text-gold">
                Read research <ArrowRight className="h-4 w-4" />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="border-t border-border py-10" aria-labelledby="notes-heading">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 id="notes-heading" className="text-xl font-bold">
            Research notes
          </h2>
          <Link href="/docs/notes" className="text-sm font-semibold text-gold hover:underline">
            View all
          </Link>
        </div>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-text-muted">
          Raw investigation logs rendered from the repository, including reproduction commands and
          superseded conclusions. The curated pages above summarize what these established.
        </p>
        <div className="mt-5 divide-y divide-border border-y border-border">
          {notes.map((note) => (
            <Link
              key={note.slug}
              href={`/docs/notes/${note.slug}`}
              className="group flex items-start gap-3 py-4"
            >
              <FileText className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
              <div className="min-w-0">
                <p className="font-semibold group-hover:text-gold">{note.title}</p>
                <p className="mt-1 line-clamp-2 text-sm leading-6 text-text-muted">
                  {note.summary}
                </p>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="border-t border-border py-10" aria-labelledby="evidence-heading">
        <h2 id="evidence-heading" className="text-xl font-bold">
          Evidence model
        </h2>
        <div className="mt-5 divide-y divide-border border-y border-border">
          {evidenceLevels.map(({ level, meaning }) => (
            <div key={level} className="grid gap-3 py-4 sm:grid-cols-[110px_1fr] sm:items-center">
              <EvidenceBadge level={level} />
              <p className="text-sm leading-6 text-text-muted">{meaning}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}