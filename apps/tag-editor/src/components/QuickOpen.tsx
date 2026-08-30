import { useCallback, useEffect, useRef, useState } from "react";
import { api, type TagSummary } from "../lib/api";
import { tagLabel, useEditor, type RecentTag } from "../stores/editor-store";

const DEBOUNCE_MS = 150;
const MAX_SHOWN = 50;

/**
 * Client-side ranking over the server's (capped) substring matches: an exact
 * file-name match first, then name-starts-with, then anything containing the
 * query — shorter paths before longer within each band, so `ar` finds the
 * assault rifle before an armory prop.
 */
function rank(rows: TagSummary[], q: string): TagSummary[] {
  const want = q.trim().toLowerCase();
  const score = (t: TagSummary) => {
    const short = t.short.toLowerCase();
    const tail = short.split("/").pop() ?? short;
    if (tail === want) return 0;
    if (tail.startsWith(want)) return 1;
    if (tail.includes(want)) return 2;
    return 3;
  };
  return [...rows]
    .sort(
      (a, b) =>
        score(a) - score(b) ||
        a.short.length - b.short.length ||
        a.short.localeCompare(b.short),
    )
    .slice(0, MAX_SHOWN);
}

/** Ctrl+P: type a name, arrow to a row, Enter opens it. Empty query shows
 *  recently opened tags instead of nothing. */
export function QuickOpen() {
  const open = useEditor((s) => s.quickOpen);
  const setOpen = useEditor((s) => s.setQuickOpen);
  const openTab = useEditor((s) => s.openTab);
  const openRecent = useEditor((s) => s.openRecent);
  const recents = useEditor((s) => s.recents);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<TagSummary[]>([]);
  const [sel, setSel] = useState(0);

  // A fresh palette every time it comes up.
  useEffect(() => {
    if (open) {
      setQuery("");
      setRows([]);
      setSel(0);
      // Focus after the overlay paints.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (!open || query.trim() === "") {
      setRows([]);
      setSel(0);
      return;
    }
    const q = query;
    const t = window.setTimeout(() => {
      api
        .searchTags(q.trim().toLowerCase())
        .then((r) => {
          // Answers can land out of order; only the current query counts.
          if (inputRef.current?.value === q) {
            setRows(rank(r, q));
            setSel(0);
          }
        })
        .catch(() => {});
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [open, query]);

  const showingRecents = query.trim() === "";
  const count = showingRecents ? recents.length : rows.length;

  const choose = useCallback(
    (at: number) => {
      setOpen(false);
      if (showingRecents) {
        const r = recents[at];
        if (r) void openRecent(r);
      } else {
        const t = rows[at];
        if (t) void openTab("tag", t.index, tagLabel(t));
      }
    },
    [showingRecents, recents, rows, openRecent, openTab, setOpen],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-40 bg-black/50"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div className="mx-auto mt-[15vh] w-[36rem] max-w-[90vw] border border-border-subtle bg-surface-card shadow-2xl">
        <input
          ref={inputRef}
          className="w-full border-b border-border-subtle bg-transparent px-3 py-2 font-mono text-sm text-text-primary outline-none placeholder:text-text-dim"
          placeholder="Open a tag by name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              setOpen(false);
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              setSel((s) => Math.min(s + 1, Math.max(0, count - 1)));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setSel((s) => Math.max(s - 1, 0));
            } else if (e.key === "Enter" && count > 0) {
              e.preventDefault();
              choose(sel);
            }
          }}
        />
        <div className="max-h-[50vh] overflow-y-auto py-1">
          {showingRecents && recents.length > 0 && (
            <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-text-dim">
              recent
            </div>
          )}
          {showingRecents
            ? recents.map((r: RecentTag, i: number) => (
                <Row
                  key={`${r.group}:${r.short}`}
                  label={r.label}
                  detail={r.short}
                  group={r.group}
                  selected={i === sel}
                  onPick={() => choose(i)}
                  onHover={() => setSel(i)}
                />
              ))
            : rows.map((t, i) => (
                <Row
                  key={t.index}
                  label={tagLabel(t)}
                  detail={t.short}
                  group={t.group}
                  selected={i === sel}
                  onPick={() => choose(i)}
                  onHover={() => setSel(i)}
                />
              ))}
          {count === 0 && (
            <div className="px-3 py-2 text-xs text-text-dim">
              {showingRecents
                ? "Nothing opened yet — type to search every tag."
                : "No tag matches."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({
  label,
  detail,
  group,
  selected,
  onPick,
  onHover,
}: {
  label: string;
  detail: string;
  group: string;
  selected: boolean;
  onPick: () => void;
  onHover: () => void;
}) {
  return (
    <button
      type="button"
      className={`flex w-full cursor-pointer items-baseline gap-2 px-3 py-1 text-left ${
        selected ? "bg-surface-hover" : ""
      }`}
      onPointerMove={onHover}
      onClick={onPick}
    >
      <span className="shrink-0 font-mono text-xs text-text-primary">{label}</span>
      <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-text-dim">
        {detail}
      </span>
      <span className="shrink-0 font-mono text-[10px] text-mjolnir-gold-dim">{group}</span>
    </button>
  );
}
