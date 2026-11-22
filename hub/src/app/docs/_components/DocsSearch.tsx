"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { BookOpen, CornerDownLeft, Database, FileText, Search, Sparkles, Terminal } from "lucide-react";
import { DocsIndex, snippet, type DocHit, type SearchIndexFile, type SnippetPart } from "@/lib/docs-search";

/**
 * One search over everything under /docs: the guides and notes, the hand-made
 * pages, the tag definitions and the console functions.
 *
 * The docs are searched in the browser (src/lib/docs-search.ts) from an index
 * fetched the first time the palette opens, so results follow each keystroke.
 * A question, as opposed to a name, is also sent to /api/v1/docs/search, which
 * finds sections by meaning; those hits are merged in when they arrive. When
 * that endpoint has no index behind it (local dev, or an outage) it says so and
 * the palette carries on with keywords alone.
 *
 * Mounted once by the docs layout. Anything can open it with `openDocsSearch()`.
 */

const OPEN_EVENT = "mjolnir:docs-search";

export function openDocsSearch() {
  window.dispatchEvent(new Event(OPEN_EVENT));
}

export type SearchPage = { href: string; title: string; description: string };
export type SearchTagGroup = { slug: string; name: string; group: string };

/** One row of public/console-search.json: name, family, anchor, compiled out, signature. */
type ConsoleRow = [string, string, string, 0 | 1, string];
type TagTerms = Record<string, string[]>;

/** One hit of GET /api/v1/docs/search. */
type SemanticHit = { key: string; relevance: number };

type Scope = "all" | "docs" | "tags" | "console";
const SCOPES: Array<{ id: Scope; label: string }> = [
  { id: "all", label: "All" },
  { id: "docs", label: "Docs" },
  { id: "tags", label: "Tags" },
  { id: "console", label: "Console" },
];

type Result = {
  id: string;
  href: string;
  kind: "guide" | "note" | "page" | "tag" | "console";
  title: string;
  /** Where the result lives: the doc and section, or the reference it is from. */
  context: string;
  body?: SnippetPart[];
  mono?: boolean;
  semanticOnly?: boolean;
};
type Group = { label: string; results: Result[] };

const ICONS = { guide: BookOpen, note: FileText, page: FileText, tag: Database, console: Terminal };

/** A question worth asking the semantic index: several words, not one name. */
function isQuestion(query: string): boolean {
  return query.length >= 8 && /\S\s+\S/.test(query);
}

async function fetchJson<T>(url: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(url);
    return response.ok ? ((await response.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function DocsSearch({
  pages,
  tagGroups,
  consoleFamilies,
  suggestions,
}: {
  pages: SearchPage[];
  tagGroups: SearchTagGroup[];
  consoleFamilies: Record<string, string>;
  /** Shown before anything is typed. */
  suggestions: SearchPage[];
}) {
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<Scope>("all");
  const [active, setActive] = useState(0);
  const [index, setIndex] = useState<DocsIndex | null>(null);
  const [tagTerms, setTagTerms] = useState<TagTerms | null>(null);
  const [consoleRows, setConsoleRows] = useState<ConsoleRow[] | null>(null);
  /** The semantic hits for one query: chunk keys, each with its relevance. */
  const [semantic, setSemantic] = useState<{ query: string; hits: SemanticHit[] } | null>(null);
  /** Unknown until the endpoint answers once; "off" stops the asking. */
  const [meaning, setMeaning] = useState<"unknown" | "on" | "off">("unknown");
  const loading = useRef(false);

  // The indexes are ~0.5 MB compressed together, so they are fetched when the
  // palette first opens rather than shipped with every docs page.
  const load = useCallback(() => {
    if (loading.current) return;
    loading.current = true;
    void fetchJson<SearchIndexFile | null>("/docs-search.json", null).then((file) => {
      if (file) setIndex(new DocsIndex(file));
      else loading.current = false;
    });
    void fetchJson<TagTerms>("/tag-search.json", {}).then(setTagTerms);
    void fetchJson<ConsoleRow[]>("/console-search.json", []).then(setConsoleRows);
  }, []);

  const open = useCallback(() => {
    load();
    if (!dialog.current?.open) dialog.current?.showModal();
    input.current?.focus();
    input.current?.select();
  }, [load]);
  const close = useCallback(() => dialog.current?.close(), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing =
        event.target instanceof HTMLElement &&
        (event.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName));
      const chord = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
      if (chord || (event.key === "/" && !typing)) {
        event.preventDefault();
        open();
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, open);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, open);
    };
  }, [open]);

  const trimmed = query.trim();

  // Ask for meaning once the typing pauses. A reply for a query that has
  // since changed is dropped by the abort.
  useEffect(() => {
    if (!index || meaning === "off" || !isQuestion(trimmed)) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/v1/docs/search?q=${encodeURIComponent(trimmed)}`, {
          signal: controller.signal,
        });
        const data = response.ok
          ? ((await response.json()) as { semantic?: boolean; hits?: SemanticHit[] })
          : null;
        if (!data?.semantic) {
          setMeaning("off");
          return;
        }
        setMeaning("on");
        setSemantic({ query: trimmed, hits: data.hits ?? [] });
      } catch {
        // Aborted because the query changed, or the request failed: keywords
        // still answer, and a failure stops the asking for this visit.
        if (!controller.signal.aborted) setMeaning("off");
      }
    }, 350);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [index, meaning, trimmed]);

  const groups = useMemo<Group[]>(() => {
    if (!trimmed) return [];
    const q = trimmed.toLowerCase();
    /** The query as an identifier: "ai place" finds `ai_place`. */
    const id = q.replace(/\s+/g, "_");
    const words = q.split(/\s+/);
    const out: Group[] = [];

    if (scope === "all" || scope === "docs") {
      const results: Result[] = [];
      if (index) {
        const lexical = index.search(trimmed, 30);
        const hits: DocHit[] =
          semantic?.query === trimmed ? index.fuse(lexical, semantic.hits, 10) : lexical.slice(0, 10);
        for (const hit of hits) {
          const [doc, anchor, heading, text] = index.file.chunks[hit.chunk];
          const [slug, kind, title, section] = index.file.docs[doc];
          const trail = heading.split(" › ");
          results.push({
            id: `doc-${hit.chunk}`,
            href: `/docs/${kind === "g" ? "guides" : "notes"}/${slug}${anchor ? `#${anchor}` : ""}`,
            kind: kind === "g" ? "guide" : "note",
            title: heading ? trail[trail.length - 1] : title,
            context: [section, title, ...trail.slice(0, -1)].filter(Boolean).join(" › "),
            body: snippet(text, hit.terms),
            semanticOnly: hit.semanticOnly,
          });
        }
      }
      for (const page of pages) {
        const haystack = `${page.title} ${page.description}`.toLowerCase();
        if (words.every((word) => haystack.includes(word))) {
          results.push({
            id: `page-${page.href}`,
            href: page.href,
            kind: "page",
            title: page.title,
            context: "Documentation",
            body: [{ text: page.description, hit: false }],
          });
        }
      }
      if (results.length > 0) out.push({ label: "Guides and notes", results });
    }

    if (scope === "all" || scope === "tags") {
      const matches: Array<{ group: SearchTagGroup; rank: number; fields: string[] }> = [];
      for (const group of tagGroups) {
        const name = group.name.toLowerCase();
        const named = name.includes(q) || name.includes(id) || group.group.toLowerCase() === q;
        const fields = (tagTerms?.[group.slug] ?? []).filter((field) => field.includes(q));
        if (!named && fields.length === 0) continue;
        const rank = name === q || name === id ? 0 : named ? 1 : 2;
        matches.push({ group, rank, fields });
      }
      matches.sort((a, b) => a.rank - b.rank || b.fields.length - a.fields.length);
      const results = matches.slice(0, scope === "tags" ? 20 : 5).map<Result>(({ group, fields }) => ({
        id: `tag-${group.slug}`,
        href: `/docs/tags/${group.slug}`,
        kind: "tag",
        title: group.name,
        context: `Tag group ${group.group}`,
        body:
          fields.length > 0
            ? [{ text: `${fields.length === 1 ? "Field" : "Fields"}: ${fields.slice(0, 5).join(", ")}${fields.length > 5 ? ", …" : ""}`, hit: false }]
            : undefined,
        mono: true,
      }));
      if (results.length > 0) out.push({ label: "Tag definitions", results });
    }

    if ((scope === "all" || scope === "console") && consoleRows) {
      const matches = consoleRows.filter((row) => {
        const name = row[0].toLowerCase();
        return name.includes(q) || name.includes(id);
      });
      const starts = (row: ConsoleRow) => {
        const name = row[0].toLowerCase();
        return name === q || name === id ? 0 : name.startsWith(q) || name.startsWith(id) ? 1 : 2;
      };
      matches.sort((a, b) => starts(a) - starts(b) || a[3] - b[3] || a[0].localeCompare(b[0]));
      const results = matches.slice(0, scope === "console" ? 30 : 6).map<Result>((row) => ({
        id: `console-${row[1]}-${row[2]}`,
        href: row[1] === "globals" ? `/docs/console/globals#${row[2]}` : `/docs/console/${row[1]}#${row[2]}`,
        kind: "console",
        title: row[0],
        context: `Console › ${consoleFamilies[row[1]] ?? "Globals"}${row[3] === 1 ? " · compiled out" : ""}`,
        body: row[4] ? [{ text: row[4], hit: false }] : undefined,
        mono: true,
      }));
      // A query that is a function's exact name wants the function first.
      const exact = matches.length > 0 && starts(matches[0]) === 0;
      if (results.length > 0) {
        const group = { label: "Console", results };
        if (exact) out.unshift(group);
        else out.push(group);
      }
    }
    return out;
  }, [trimmed, scope, index, semantic, pages, tagGroups, tagTerms, consoleRows, consoleFamilies]);

  const flat = useMemo(() => groups.flatMap((group) => group.results), [groups]);
  const current = flat[Math.min(active, flat.length - 1)];

  useEffect(() => {
    if (!current) return;
    list.current?.querySelector(`[data-result="${CSS.escape(current.id)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [current]);

  const go = (href: string) => {
    close();
    router.push(href);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (flat.length === 0) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((Math.min(active, flat.length - 1) + step + flat.length) % flat.length);
    } else if (event.key === "Enter" && current) {
      event.preventDefault();
      go(current.href);
    }
  };

  const ready = index !== null;
  const asked = semantic?.query === trimmed;

  return (
    <dialog
      ref={dialog}
      aria-label="Search the documentation"
      onClick={(event) => {
        // The dialog element itself is the backdrop; its content sits inside.
        if (event.target === dialog.current) close();
      }}
      className="m-0 mx-auto mt-[9vh] w-[min(46rem,calc(100vw-1.5rem))] max-w-none rounded-xl border border-border-bright bg-surface p-0 text-foreground shadow-2xl backdrop:bg-black/70 backdrop:backdrop-blur-sm"
    >
      <div className="flex max-h-[78vh] flex-col" onKeyDown={onKeyDown}>
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Search className="h-5 w-5 shrink-0 text-text-dim" aria-hidden />
          <input
            ref={input}
            type="search"
            role="combobox"
            aria-expanded={flat.length > 0}
            aria-controls="docs-search-results"
            aria-activedescendant={current ? `result-${current.id}` : undefined}
            aria-label="Search the documentation"
            autoComplete="off"
            spellCheck={false}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            placeholder="Search guides, notes, tags and console functions"
            className="min-w-0 flex-1 bg-transparent py-4 text-base text-foreground placeholder:text-text-dim focus:outline-none [&::-webkit-search-cancel-button]:hidden"
          />
          <button
            type="button"
            onClick={close}
            className="shrink-0 rounded border border-border px-2 py-1 font-mono text-[11px] text-text-dim hover:text-foreground"
          >
            Esc
          </button>
        </div>

        <div className="flex gap-1.5 overflow-x-auto border-b border-border px-4 py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="tablist" aria-label="Search in">
          {SCOPES.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={scope === id}
              onClick={() => {
                setScope(id);
                setActive(0);
                input.current?.focus();
              }}
              className={`shrink-0 rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${
                scope === id ? "bg-gold/15 text-gold" : "text-text-muted hover:text-foreground"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div ref={list} id="docs-search-results" role="listbox" aria-label="Results" className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2">
          {!trimmed && (
            <div className="p-2">
              <p className="px-2 pb-2 text-xs font-bold uppercase text-text-dim">Start here</p>
              {suggestions.map((page) => (
                <button
                  key={page.href}
                  type="button"
                  onClick={() => go(page.href)}
                  className="flex w-full items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-hover"
                >
                  <BookOpen className="mt-0.5 h-4 w-4 shrink-0 text-gold" aria-hidden />
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold">{page.title}</span>
                    <span className="mt-0.5 line-clamp-1 block text-xs text-text-muted">{page.description}</span>
                  </span>
                </button>
              ))}
            </div>
          )}

          {trimmed && !ready && <p className="px-4 py-8 text-center text-sm text-text-muted">Loading the index…</p>}

          {trimmed && ready && flat.length === 0 && (
            <p className="px-4 py-8 text-center text-sm text-text-muted">
              Nothing matches <span className="font-mono text-foreground">{trimmed}</span>.
              {scope !== "all" && " Try All."}
            </p>
          )}

          {groups.map((group) => (
            <div key={group.label} role="group" aria-label={group.label} className="pb-2">
              <p className="px-3 pb-1 pt-2 text-xs font-bold uppercase text-text-dim">{group.label}</p>
              {group.results.map((result) => {
                const Icon = ICONS[result.kind];
                const selected = result === current;
                return (
                  <a
                    key={result.id}
                    id={`result-${result.id}`}
                    data-result={result.id}
                    role="option"
                    aria-selected={selected}
                    href={result.href}
                    onClick={(event) => {
                      // A modified click opens a tab; a plain one stays in the app.
                      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
                      event.preventDefault();
                      go(result.href);
                    }}
                    onMouseMove={() => {
                      const at = flat.indexOf(result);
                      if (at !== active) setActive(at);
                    }}
                    className={`flex items-start gap-3 rounded-lg px-3 py-2.5 ${selected ? "bg-surface-hover" : ""}`}
                  >
                    <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${selected ? "text-gold" : "text-text-dim"}`} aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-x-2">
                        <span className={`break-words text-sm font-semibold ${result.mono ? "font-mono" : ""}`}>
                          {result.title}
                        </span>
                        {result.semanticOnly && (
                          <span className="inline-flex items-center gap-1 rounded border border-accent-blue/30 px-1.5 text-[10px] font-semibold uppercase text-accent-blue">
                            <Sparkles className="h-3 w-3" aria-hidden />
                            By meaning
                          </span>
                        )}
                      </span>
                      <span className="mt-0.5 block truncate text-xs text-text-dim">{result.context}</span>
                      {result.body && (
                        <span className={`mt-1 line-clamp-2 block break-words text-xs leading-5 text-text-muted ${result.mono ? "font-mono" : ""}`}>
                          {result.body.map((part, at) =>
                            part.hit ? (
                              <mark key={at} className="rounded-sm bg-gold/20 px-0.5 text-foreground">
                                {part.text}
                              </mark>
                            ) : (
                              <span key={at}>{part.text}</span>
                            ),
                          )}
                        </span>
                      )}
                    </span>
                    {selected && <CornerDownLeft className="mt-0.5 h-4 w-4 shrink-0 text-text-dim" aria-hidden />}
                  </a>
                );
              })}
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t border-border px-4 py-2 text-[11px] text-text-dim">
          <span>
            <kbd className="font-mono">↑</kbd> <kbd className="font-mono">↓</kbd> to move,{" "}
            <kbd className="font-mono">Enter</kbd> to open
          </span>
          <span aria-live="polite">
            {meaning === "on" && asked
              ? "Matched by keyword and by meaning"
              : meaning === "on"
                ? "Ask a question to also search by meaning"
                : "Keyword search"}
          </span>
        </div>
      </div>
    </dialog>
  );
}

/** A button that opens the palette. `hero` is the large field on the docs landing page. */
export function DocsSearchButton({ variant = "sidebar" }: { variant?: "sidebar" | "hero" | "pill" }) {
  if (variant === "pill") {
    return (
      <button
        type="button"
        onClick={openDocsSearch}
        className="flex shrink-0 items-center gap-1.5 rounded-lg border border-gold/40 px-3 py-2 text-xs font-semibold text-gold"
      >
        <Search className="h-3.5 w-3.5" aria-hidden />
        Search
      </button>
    );
  }
  const hero = variant === "hero";
  return (
    <button
      type="button"
      onClick={openDocsSearch}
      className={`group flex w-full items-center gap-3 border border-border bg-surface text-left text-text-muted transition-colors hover:border-gold/40 hover:text-foreground ${
        hero ? "rounded-xl px-5 py-4 text-base" : "rounded-lg px-3 py-2 text-sm"
      }`}
    >
      <Search className={`shrink-0 ${hero ? "h-5 w-5 text-gold" : "h-4 w-4"}`} aria-hidden />
      <span className="min-w-0 flex-1 truncate">
        {hero ? "Search guides, notes, tags and console functions" : "Search docs"}
      </span>
      <kbd className="shrink-0 rounded border border-border px-1.5 py-0.5 font-mono text-[11px] text-text-dim">
        Ctrl K
      </kbd>
    </button>
  );
}
