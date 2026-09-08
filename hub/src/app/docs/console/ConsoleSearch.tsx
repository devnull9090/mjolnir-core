"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import type { ConsoleFamilySummary } from "@/lib/console";

/** One row of public/console-search.json: name, family, anchor, compiled out, signature. */
type Row = [string, string, string, 0 | 1, string];

const MAX_RESULTS = 60;

export function ConsoleSearch({
  families,
  names,
  globals,
}: {
  families: ConsoleFamilySummary[];
  names: number;
  globals: number;
}) {
  const [query, setQuery] = useState("");
  const [hideStubs, setHideStubs] = useState(false);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [loading, setLoading] = useState(false);
  const requested = useRef(false);

  // The name index is ~190 KiB, so it is fetched once the visitor actually
  // searches rather than shipped with the page.
  useEffect(() => {
    if (!query || requested.current) return;
    requested.current = true;
    setLoading(true);
    fetch("/console-search.json")
      .then((r) => (r.ok ? r.json() : []))
      .then((data: Row[]) => setRows(data))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [query]);

  const titles = useMemo(() => {
    const map = new Map(families.map((f) => [f.slug, f.title]));
    map.set("globals", "Globals");
    return map;
  }, [families]);

  const results = useMemo<Row[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q || !rows) return [];
    const out: Row[] = [];
    for (const row of rows) {
      if (hideStubs && row[3] === 1) continue;
      if (row[0].toLowerCase().includes(q)) out.push(row);
    }
    // Names that start with the query rank above names that merely contain it;
    // live functions above compiled-out ones; then alphabetical.
    return out
      .sort((a, b) => {
        const as = a[0].toLowerCase().startsWith(q) ? 0 : 1;
        const bs = b[0].toLowerCase().startsWith(q) ? 0 : 1;
        return as - bs || a[3] - b[3] || a[0].localeCompare(b[0]);
      })
      .slice(0, MAX_RESULTS);
  }, [query, rows, hideStubs]);

  const hrefFor = (row: Row) =>
    row[1] === "globals"
      ? `/docs/console/globals#${row[2]}`
      : `/docs/console/${row[1]}#${row[2]}`;

  return (
    <div>
      <label htmlFor="console-search" className="sr-only">
        Search console functions and globals
      </label>
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-text-dim"
          aria-hidden
        />
        <input
          id="console-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${names.toLocaleString()} functions and ${globals} globals…`}
          className="w-full border border-border bg-surface py-3 pl-11 pr-4 text-sm outline-none placeholder:text-text-dim focus:border-gold"
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-text-dim" aria-live="polite">
          {loading
            ? "Loading name index…"
            : query
              ? results.length === MAX_RESULTS
                ? `First ${MAX_RESULTS} matches; narrow the search`
                : `${results.length} match${results.length === 1 ? "" : "es"}`
              : "Type part of a name: player_, teleport, cheat"}
        </p>
        <label className="flex items-center gap-2 text-xs text-text-muted">
          <input
            type="checkbox"
            checked={hideStubs}
            onChange={(e) => setHideStubs(e.target.checked)}
            className="accent-gold"
          />
          Only what works in this build
        </label>
      </div>

      {query && results.length > 0 && (
        <ul className="mt-5 divide-y divide-border border-y border-border">
          {results.map((row) => (
            <li key={`${row[1]}-${row[0]}`}>
              <Link
                href={hrefFor(row)}
                className="flex flex-col gap-1 py-3 transition-colors hover:bg-surface sm:flex-row sm:items-baseline sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-baseline gap-3">
                    <span className="font-mono text-sm text-gold">
                      {row[0]}
                    </span>
                    <span className="text-xs text-text-dim">
                      {titles.get(row[1]) ?? row[1]}
                    </span>
                    {row[3] === 1 && (
                      <span className="border border-border-bright bg-surface-raised px-1.5 py-0.5 text-[10px] font-bold uppercase text-text-muted">
                        {row[1] === "globals" ? "no storage" : "compiled out"}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 truncate font-mono text-xs text-text-muted">
                    {row[4]}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {query && !loading && rows && results.length === 0 && (
        <p className="py-8 text-center text-sm text-text-muted">
          No function or global matches {`"${query}"`}.
        </p>
      )}
    </div>
  );
}
