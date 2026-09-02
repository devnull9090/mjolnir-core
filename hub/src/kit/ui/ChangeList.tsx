/**
 * "What this mod does" — the transparency section of a mod page.
 *
 * Every content mod is a set of tag edits, and the archive declares them
 * (changes.json), so the page can show the actual shipped → modded values
 * instead of asking players to trust a description. Two levels of truth are
 * kept visibly distinct: the change list is the *author's declaration*,
 * while the chunk count comes from the scanner reading the uploaded
 * containers — a release declaring one tweak while overriding hundreds of
 * chunks looks exactly as odd as it is.
 *
 * This file is deliberately hook-free so the website can render it in a
 * Server Component with data straight from D1; the client-side fetching
 * wrapper lives in ReleaseChangesPanel.tsx.
 */
import type { DeclaredChanges, ReleaseChanges } from "../types";

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** One-line scope summary: "8 field edits across 3 tags · 2 textures". */
export function changesSummary(changes: DeclaredChanges): string {
  const fields = changes.tags.reduce((n, t) => n + t.fields.length, 0);
  const parts: string[] = [];
  if (fields > 0) {
    parts.push(`${plural(fields, "field edit")} across ${plural(changes.tags.length, "tag")}`);
  }
  if (changes.textures.length > 0) parts.push(plural(changes.textures.length, "texture"));
  if (changes.scripts.length > 0) parts.push(plural(changes.scripts.length, "script"));
  return parts.join(" · ") || "no declared edits";
}

export function ChangeList({
  data,
  emptyText = "This release was exported before mods declared their changes, so there is no change list to show. The archive was still scanned: it holds only inert game data.",
}: {
  data: ReleaseChanges;
  emptyText?: string;
}) {
  const { changes, chunk_count } = data;

  if (!changes) {
    return (
      <div className="text-sm text-[var(--mj-text-dim)]">
        <p>{emptyText}</p>
        <p className="mt-1">
          It overrides <span className="text-[var(--mj-text-muted)]">{plural(chunk_count, "game-data chunk")}</span>.
        </p>
      </div>
    );
  }

  // A couple of tags reads fine expanded; dozens is a wall of text, so big
  // change lists start collapsed and each row carries enough to scan by.
  const openByDefault = changes.tags.length <= 3;

  return (
    <div className="space-y-2">
      <p className="text-sm text-[var(--mj-text-muted)] mb-3">
        {changesSummary(changes)}
        <span className="text-[var(--mj-text-dim)]">
          {" "}
          · overrides {plural(chunk_count, "game-data chunk")}
        </span>
      </p>

      {changes.tags.map((t) => (
        <details
          key={`${t.group}/${t.tag}`}
          open={openByDefault}
          className="group rounded-lg border border-[var(--mj-border)]"
        >
          <summary className="flex items-center gap-2 min-w-0 px-3 py-2 cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden">
            <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase bg-[var(--mj-surface-hover)] text-[var(--mj-text-dim)]">
              {t.group}
            </span>
            {/* The path's tail is the tag's identity; the full path lives in
                the expanded body, where it has room to wrap. */}
            <span className="font-mono text-xs text-[var(--mj-text)] truncate" title={t.tag}>
              {t.tag.split("/").pop()}
            </span>
            <span className="ml-auto shrink-0 text-[11px] text-[var(--mj-text-dim)]">
              {plural(t.fields.length, "edit")}
            </span>
            <svg
              viewBox="0 0 16 16"
              aria-hidden
              className="shrink-0 w-3 h-3 text-[var(--mj-text-dim)] transition-transform group-open:rotate-90"
            >
              <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </summary>
          <div className="px-3 pb-3">
            <p className="font-mono text-[11px] text-[var(--mj-text-dim)] break-all mb-2">
              {t.tag}
            </p>
            <ul className="space-y-1 text-xs">
              {t.fields.map((f, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                  <span className="font-mono text-[var(--mj-text-muted)] break-all min-w-0">
                    {f.field}
                  </span>
                  {/* flex-wrap + ml-auto: short values sit right of the field
                      name; long ones (flag lists) drop to their own wrapped
                      line instead of forcing the page wide. */}
                  <span className="ml-auto min-w-0 max-w-full text-right break-words">
                    {f.before != null && (
                      <>
                        <span className="text-[var(--mj-text-dim)] line-through">{f.before}</span>
                        <span className="text-[var(--mj-text-dim)]"> → </span>
                      </>
                    )}
                    <span className="font-semibold text-[var(--mj-text)]">{f.value}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </details>
      ))}

      {changes.textures.length > 0 && (
        <div className="rounded-lg border border-[var(--mj-border)] p-3">
          <p className="text-[10px] font-bold uppercase text-[var(--mj-text-dim)] mb-2">
            Replaced textures
          </p>
          <ul className="space-y-0.5">
            {changes.textures.map((tx) => (
              <li key={tx.path} className="font-mono text-xs text-[var(--mj-text-muted)] break-all">
                {tx.path}
              </li>
            ))}
          </ul>
        </div>
      )}

      {changes.scripts.length > 0 && (
        <div className="rounded-lg border border-[var(--mj-border)] p-3">
          <p className="text-[10px] font-bold uppercase text-[var(--mj-text-dim)] mb-2">
            Replaced scripts
          </p>
          <ul className="space-y-0.5">
            {changes.scripts.map((s) => (
              <li
                key={`${s.group}/${s.tag}`}
                className="font-mono text-xs text-[var(--mj-text-muted)] break-all"
              >
                {s.tag}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[11px] text-[var(--mj-text-dim)]">
        Declared by the author&apos;s tag editor at export and stored when the archive was
        scanned. The scan verifies the archive holds only inert game data; the chunk count is
        measured from the uploaded containers themselves.
      </p>
    </div>
  );
}
