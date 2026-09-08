import { useMemo, useState } from "react";
import { useEditor } from "../stores/editor-store";
import { copyText } from "../lib/clipboard";

/**
 * Two tags side by side, field by field: what differs, with the values on
 * each side. Either two tags of one group, or a tag as shipped against the
 * tag as this mod leaves it. Blocks are materialised to 64 elements; past
 * that only their counts are compared, which the footnote says.
 */
export function DiffDialog() {
  const diff = useEditor((s) => s.diff);
  const loading = useEditor((s) => s.diffLoading);
  const close = useEditor((s) => s.closeDiff);
  const [filter, setFilter] = useState("");

  const rows = useMemo(() => {
    if (!diff) return [];
    const q = filter.trim().toLowerCase();
    return q ? diff.fields.filter((f) => f.path.toLowerCase().includes(q)) : diff.fields;
  }, [diff, filter]);

  if (!diff && !loading) return null;

  const asText = () =>
    diff
      ? [
          `A: ${diff.a}`,
          `B: ${diff.b}`,
          "",
          ...diff.fields.map((f) => `${f.path}\t${f.a ?? "—"}\t${f.b ?? "—"}`),
        ].join("\n")
      : "";

  return (
    <div
      className="fixed inset-0 z-40 bg-black/50"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") close();
      }}
    >
      <div className="mx-auto mt-[8vh] flex h-[80vh] w-[60rem] max-w-[94vw] flex-col border border-border-subtle bg-surface-card shadow-2xl">
        <div className="flex items-baseline gap-3 border-b border-border-subtle px-4 py-2">
          <h2 className="text-xs uppercase tracking-wider text-text-dim">Diff</h2>
          {diff && (
            <span className="min-w-0 truncate font-mono text-xs text-text-secondary">
              <span className="text-mjolnir-gold">A</span> {diff.a}
              <span className="mx-2 text-text-dim">·</span>
              <span className="text-mjolnir-gold">B</span> {diff.b}
            </span>
          )}
          <button
            type="button"
            className="ml-auto text-[10px] text-text-dim hover:text-text-secondary"
            onClick={close}
          >
            close
          </button>
        </div>

        {loading ? (
          <p className="px-4 py-6 text-xs text-text-dim">Comparing…</p>
        ) : diff?.error ? (
          <p className="px-4 py-6 font-mono text-xs text-accent-red">{diff.error}</p>
        ) : diff ? (
          <>
            <div className="flex items-center gap-3 border-b border-border-subtle px-4 py-2">
              <input
                type="search"
                autoFocus
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter by field path…"
                className="w-72 border border-border-subtle bg-surface-secondary px-2 py-1 font-mono text-xs outline-none placeholder:text-text-dim focus:border-mjolnir-gold"
              />
              <span className="font-mono text-[10px] text-text-dim">
                {diff.fields.length} differ · {diff.same} same
                {filter && ` · ${rows.length} shown`}
              </span>
              <button
                type="button"
                className="ml-auto border border-border-subtle px-2 py-0.5 text-[10px] text-text-secondary hover:bg-surface-hover"
                onClick={() => void copyText(asText())}
                title="Copy every difference as tab-separated text"
              >
                copy
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              {rows.length === 0 ? (
                <p className="px-4 py-6 text-xs text-text-dim">
                  {diff.fields.length === 0
                    ? "Every materialised field agrees."
                    : "No differing field matches the filter."}
                </p>
              ) : (
                <table className="w-full border-collapse font-mono text-[11px]">
                  <thead className="sticky top-0 bg-surface-card text-[10px] uppercase tracking-wider text-text-dim">
                    <tr>
                      <th className="px-4 py-1 text-left font-normal">field</th>
                      <th className="px-2 py-1 text-left font-normal">A</th>
                      <th className="px-2 py-1 text-left font-normal">B</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((f) => (
                      <tr key={f.path} className="border-t border-border-subtle/40 align-top">
                        <td className="max-w-[24rem] break-all px-4 py-1 text-text-secondary">
                          {f.path}
                        </td>
                        <td
                          className={`max-w-[16rem] break-all px-2 py-1 ${
                            f.a === null ? "text-text-dim" : "text-text-primary"
                          }`}
                        >
                          {f.a ?? "—"}
                        </td>
                        <td
                          className={`max-w-[16rem] break-all px-2 py-1 ${
                            f.b === null ? "text-text-dim" : "text-mjolnir-gold"
                          }`}
                        >
                          {f.b ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <p className="border-t border-border-subtle px-4 py-1 text-[10px] text-text-dim">
              Blocks are compared element by element up to 64 elements, then by count. A field
              on one side only means the block sizes differ there.
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}
