import type { Metadata } from "next";
import Link from "next/link";
import { Braces, Database } from "lucide-react";
import { EvidenceBadge } from "../_components/EvidenceBadge";
import { getBuild, getTagGroups, getTotals } from "@/lib/tags";
import { TagSearch } from "./TagSearch";

const totals = getTotals();

export const metadata: Metadata = {
  title: "Halo Campaign Evolved tag definitions | MJOLNIR Docs",
  description:
    `Complete field-level reference for all ${totals.groups} Blam tag groups in Halo Campaign Evolved: ` +
    `${totals.fields.toLocaleString()} fields with names, types, byte offsets, and enum options, ` +
    "extracted from the shipped game data.",
  keywords: [
    "Halo Campaign Evolved",
    "Blam tag definitions",
    "tag reference",
    "Halo modding",
    "Guerilla",
    "tag editor",
  ],
  alternates: { canonical: "/docs/tags" },
};

export default function TagsIndexPage() {
  const groups = getTagGroups();
  const build = getBuild();

  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-9">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <EvidenceBadge level="Verified" />
          {build && <span className="text-xs text-text-dim">Build {build}</span>}
        </div>
        <div className="flex items-start gap-4">
          <Database className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div>
            <h1 className="break-words text-3xl font-black sm:text-4xl">Tag definitions</h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-text-muted">
              Every field of every Blam tag group in Halo Campaign Evolved, with the original
              names, types, byte offsets, and enum options. Extracted from the shipped game data,
              which carries its own definitions.
            </p>
          </div>
        </div>

        <dl className="mt-7 grid grid-cols-2 gap-px border border-border bg-border sm:grid-cols-4">
          {[
            ["Groups", totals.groups.toLocaleString()],
            ["Structs", totals.structs.toLocaleString()],
            ["Fields", totals.fields.toLocaleString()],
            ["Shipped tags", totals.tags.toLocaleString()],
          ].map(([label, value]) => (
            <div key={label} className="bg-background px-4 py-4">
              <dt className="text-xs uppercase text-text-dim">{label}</dt>
              <dd className="mt-1 font-mono text-lg text-gold">{value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <section className="py-9" aria-labelledby="search-heading">
        <h2 id="search-heading" className="sr-only">
          Search tag groups
        </h2>
        <TagSearch groups={groups} />
      </section>

      <section className="border-t border-border py-9" aria-labelledby="about-heading">
        <div className="flex items-center gap-3">
          <Braces className="h-5 w-5 text-gold" />
          <h2 id="about-heading" className="text-xl font-bold">
            Where this comes from
          </h2>
        </div>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          Halo Campaign Evolved ships self-describing tag files. Each one carries a layout section
          holding its own field names, type names, and enum option names, so this reference is
          generated mechanically from the game rather than reconstructed by hand. The extractor
          parses all 101 groups across all 12,290 shipped tags.
        </p>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          This is schema only. Field names, types, offsets, and option names are published; tag
          values are game content and are not.
        </p>
        <p className="mt-4 text-sm text-text-muted">
          Format details:{" "}
          <Link href="/docs/research/tag-format" className="text-gold hover:underline">
            Self-describing tag layout
          </Link>
          .
        </p>
      </section>
    </main>
  );
}
