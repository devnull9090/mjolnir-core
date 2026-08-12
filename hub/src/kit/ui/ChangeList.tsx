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

  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--mj-text-muted)]">
        {changesSummary(changes)}
        <span className="text-[var(--mj-text-dim)]">
          {" "}
          · overrides {plural(chunk_count, "game-data chunk")}
        </span>
      </p>

      {changes.tags.map((t) => (
        <div key={`${t.group}/${t.tag}`} className="rounded-lg border border-[var(--mj-border)] p-3">
          <div className="flex items-center gap-2 mb-2 min-w-0">
            <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase bg-[var(--mj-surface-hover)] text-[var(--mj-text-dim)]">
              {t.group}
            </span>
            <span className="font-mono text-xs text-[var(--mj-text)] truncate" title={t.tag}>
              {t.tag}
            </span>
          </div>
          <table className="w-full text-xs">
            <tbody>
              {t.fields.map((f, i) => (
                <tr key={i} className="align-top">
                  <td className="py-0.5 pr-3 font-mono text-[var(--mj-text-muted)] break-all">
                    {f.field}
                  </td>
                  <td className="py-0.5 text-right whitespace-nowrap">
                    {f.before != null && (
                      <>
                        <span className="text-[var(--mj-text-dim)] line-through">{f.before}</span>
                        <span className="text-[var(--mj-text-dim)]"> → </span>
                      </>
                    )}
                    <span className="font-semibold text-[var(--mj-text)]">{f.value}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
