"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import type { TagGroupSummary } from "@/lib/tags";

/** Field-name terms per group slug, fetched on first use. */
type SearchTerms = Record<string, string[]>;

type Match = {
  group: TagGroupSummary;
  /** Field names that matched, capped for display. */
  fields: string[];
};

export function TagSearch({ groups }: { groups: TagGroupSummary[] }) {
  const [query, setQuery] = useState("");
  const [terms, setTerms] = useState<SearchTerms | null>(null);
  const [loading, setLoading] = useState(false);
  const requested = useRef(false);

  // The field-name index is ~180 KiB, so it is fetched only once the visitor
  // actually searches rather than shipped with the page.
  useEffect(() => {
    if (!query || requested.current) return;
    requested.current = true;
    setLoading(true);
    fetch("/tag-search.json")
      .then((r) => (r.ok ? r.json() : {}))
      .then((data: SearchTerms) => setTerms(data))
      .catch(() => setTerms({}))
      .finally(() => setLoading(false));
  }, [query]);

  const results = useMemo<Match[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q) return groups.map((group) => ({ group, fields: [] }));

    const out: Match[] = [];
    for (const group of groups) {
      const nameHit =
        group.name.toLowerCase().includes(q) || group.group.toLowerCase().includes(q);
      const fields = (terms?.[group.slug] ?? []).filter((t) => t.includes(q));
      if (nameHit || fields.length > 0) {
        out.push({ group, fields: fields.slice(0, 6) });
      }
    }
    // Groups matching by name rank above groups matching only by field.
    return out.sort((a, b) => {
      const an = a.group.name.toLowerCase().includes(q) ? 0 : 1;
      const bn = b.group.name.toLowerCase().includes(q) ? 0 : 1;
      return an - bn || b.group.visible - a.group.visible;
    });
  }, [query, groups, terms]);

  return (
    <div>
      <label htmlFor="tag-search" className="sr-only">
        Search tag groups and field names
      </label>
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-text-dim"
          aria-hidden
        />
        <input
          id="tag-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search 101 groups and 11,216 field names…"
          className="w-full border border-border bg-surface py-3 pl-11 pr-4 text-sm outline-none placeholder:text-text-dim focus:border-gold"
        />
      </div>

      <p className="mt-3 text-xs text-text-dim" aria-live="polite">
        {loading
          ? "Loading field index…"
          : query
            ? `${results.length} group${results.length === 1 ? "" : "s"} match`
            : `${groups.length} groups`}
      </p>

      <ul className="mt-5 divide-y divide-border border-y border-border">
        {results.map(({ group, fields }) => (
          <li key={group.slug}>
            <Link
              href={`/docs/tags/${group.slug}`}
              className="flex flex-col gap-2 py-4 transition-colors hover:bg-surface sm:flex-row sm:items-baseline sm:justify-between"
            >
              <div className="min-w-0">
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-sm text-gold">{group.group}</span>
                  <span className="truncate text-sm font-semibold">{group.name}</span>
                </div>
                {fields.length > 0 && (
                  <p className="mt-1 truncate text-xs text-text-dim">
                    {fields.join(" · ")}
                  </p>
                )}
              </div>
              <div className="shrink-0 font-mono text-xs text-text-muted">
                {group.visible} fields · {group.tagCount} tags
              </div>
            </Link>
          </li>
        ))}
      </ul>

      {query && results.length === 0 && !loading && (
        <p className="py-8 text-center text-sm text-text-muted">
          No group or field matches {`"${query}"`}.
        </p>
      )}
    </div>
  );
}
