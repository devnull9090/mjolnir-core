import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Boxes, Hash } from "lucide-react";
import { EvidenceBadge } from "../../_components/EvidenceBadge";
import {
  getBuild,
  getTagGroup,
  getTagGroups,
  getTagGroupSummary,
  isHiddenType,
  type TagField,
} from "@/lib/tags";

type Params = { group: string };

export function generateStaticParams(): Params[] {
  return getTagGroups().map((g) => ({ group: g.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { group: slug } = await params;
  const summary = getTagGroupSummary(slug);
  if (!summary) return { title: "Unknown tag group | MJOLNIR Docs" };

  const title = `${summary.name} (${summary.group}) tag definition | MJOLNIR Docs`;
  const description =
    `Field reference for the Halo Campaign Evolved ${summary.name} tag group (${summary.group}): ` +
    `${summary.visible} fields across ${summary.structs} structs, with types, byte offsets, and ` +
    `enum options. ${summary.tagCount} tags of this group ship in the game.`;

  return {
    title,
    description,
    keywords: [
      `${summary.name} tag`,
      summary.group,
      "Halo Campaign Evolved",
      "Blam tag definition",
      "Halo modding",
    ],
    alternates: { canonical: `/docs/tags/${slug}` },
    openGraph: { title, description, type: "article" },
  };
}

function fieldTypeLabel(field: TagField) {
  if (field.type === "array" && field.array_count) {
    return `array [${field.array_count}]`;
  }
  return field.type;
}

export default async function TagGroupPage({ params }: { params: Promise<Params> }) {
  const { group: slug } = await params;
  const summary = getTagGroupSummary(slug);
  const def = getTagGroup(slug);
  if (!summary || !def) notFound();

  const build = getBuild();

  // Structs whose fields are all padding or terminators carry nothing worth
  // rendering, and large groups have many of them.
  const structs = def.structs
    .map((struct, index) => ({
      struct,
      index,
      visible: struct.fields.filter((f) => !isHiddenType(f.type)),
    }))
    .filter((s) => s.visible.length > 0 || s.index === 0);

  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-9">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <EvidenceBadge level="Verified" />
          <Link href="/docs/tags" className="text-xs text-gold hover:underline">
            All tag definitions
          </Link>
          {build && <span className="text-xs text-text-dim">Build {build}</span>}
        </div>
        <div className="flex items-start gap-4">
          <Hash className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div className="min-w-0">
            <h1 className="break-words text-3xl font-black sm:text-4xl">{summary.name}</h1>
            <p className="mt-2 font-mono text-sm text-gold">{summary.group}</p>
          </div>
        </div>

        <dl className="mt-7 grid grid-cols-2 gap-px border border-border bg-border sm:grid-cols-3 lg:grid-cols-5">
          {[
            ["Fields", summary.visible.toLocaleString()],
            ["Structs", summary.structs.toLocaleString()],
            ["Shipped tags", summary.tagCount.toLocaleString()],
            ["Root size", summary.size !== null ? `${summary.size} B` : "—"],
            ["Version", String(summary.version)],
          ].map(([label, value]) => (
            <div key={label} className="bg-background px-4 py-4">
              <dt className="text-xs uppercase text-text-dim">{label}</dt>
              <dd className="mt-1 font-mono text-base text-gold">{value}</dd>
            </div>
          ))}
        </dl>
      </header>

      {structs.length > 1 && (
        <nav className="border-b border-border py-7" aria-labelledby="toc-heading">
          <h2 id="toc-heading" className="text-xs font-bold uppercase text-text-dim">
            {structs.length} structs
          </h2>
          <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-2">
            {structs.map(({ struct, index }) => (
              <li key={`toc-${index}`}>
                <a
                  href={`#struct-${index}`}
                  className="break-all font-mono text-xs text-text-muted hover:text-gold"
                >
                  {struct.name || `struct ${index}`}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      )}

      {structs.map(({ struct, index: structIndex, visible }) => {
        return (
          <section
            key={`${struct.name}-${structIndex}`}
            id={`struct-${structIndex}`}
            className="scroll-mt-24 border-b border-border py-9"
            aria-labelledby={`struct-${structIndex}-heading`}
          >
            <div className="flex flex-wrap items-baseline gap-3">
              <Boxes className="h-5 w-5 shrink-0 text-gold" aria-hidden />
              <h2
                id={`struct-${structIndex}-heading`}
                className="break-all font-mono text-lg font-bold"
              >
                {struct.name || `struct ${structIndex}`}
              </h2>
              {structIndex === 0 && (
                <span className="border border-gold/40 bg-gold/10 px-2 py-0.5 text-[11px] font-bold uppercase text-gold">
                  Root
                </span>
              )}
              <span className="font-mono text-xs text-text-dim">
                {visible.length} fields
                {struct.size !== undefined && ` · ${struct.size} B`}
              </span>
            </div>

            {visible.length === 0 ? (
              <p className="mt-4 text-sm text-text-muted">No user-visible fields.</p>
            ) : (
              <div className="mt-5 overflow-x-auto border border-border">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="bg-surface text-xs uppercase text-text-dim">
                    <tr>
                      <th className="px-4 py-3 text-right">Offset</th>
                      <th className="px-4 py-3 text-right">Size</th>
                      <th className="px-4 py-3">Field</th>
                      <th className="px-4 py-3">Type</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {visible.map((field, i) => (
                      <tr key={`${field.name}-${i}`} className="align-top">
                        <td className="px-4 py-3 text-right font-mono text-text-dim">
                          {field.offset !== undefined ? field.offset : "—"}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-text-dim">
                          {field.size !== undefined ? field.size : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-medium">
                            {field.name || <em className="text-text-dim">unnamed</em>}
                          </span>
                          {field.block && (
                            <span className="mt-1 block text-xs text-text-dim">
                              block {field.block.name} · max {field.block.max_count}
                            </span>
                          )}
                          {field.options && field.options.length > 0 && (
                            <ul className="mt-2 flex flex-wrap gap-1.5">
                              {field.options.map((option, oi) => (
                                <li
                                  key={`${option}-${oi}`}
                                  className="border border-border bg-surface px-1.5 py-0.5 font-mono text-[11px] text-text-muted"
                                >
                                  {option}
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-gold">
                          {fieldTypeLabel(field)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        );
      })}

      <section className="py-9">
        <p className="text-sm leading-6 text-text-muted">
          Generated from the shipped game data, which carries its own tag definitions. Schema only:
          field names, types, offsets, and option names are published; tag values are not. See{" "}
          <Link href="/docs/research/tag-format" className="text-gold hover:underline">
            Self-describing tag layout
          </Link>{" "}
          for how this is extracted.
        </p>
      </section>
    </main>
  );
}
