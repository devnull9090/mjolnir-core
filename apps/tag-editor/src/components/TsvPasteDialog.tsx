import { useEffect, useRef, useState } from "react";
import { useEditor } from "../stores/editor-store";

/**
 * Paste tab-separated rows into a block: the header names the fields (the
 * same paths "Copy Block as TSV" writes), every following row becomes one new
 * element. Empty cells leave the field at its default. Reading the system
 * clipboard needs a permission the webview may not grant, so the text goes
 * through a textarea the user pastes into.
 */
export function TsvPasteDialog() {
  const target = useEditor((s) => s.tsvPaste);
  const close = useEditor((s) => s.closeTsvPaste);
  const paste = useEditor((s) => s.pasteBlockTsv);
  const [text, setText] = useState("");
  const [replace, setReplace] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const areaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!target) return;
    setText("");
    setReplace(false);
    setError(null);
    setBusy(false);
    const t = window.setTimeout(() => areaRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [target]);

  if (!target) return null;

  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  const rows = Math.max(lines.length - 1, 0);
  const columns = lines[0]?.split("\t").length ?? 0;

  const submit = async () => {
    if (busy || rows === 0) return;
    setBusy(true);
    const problem = await paste(text, replace);
    setBusy(false);
    if (problem) setError(problem);
  };

  return (
    <div
      className="fixed inset-0 z-40 bg-black/50"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <form
        className="mx-auto mt-[12vh] flex w-[44rem] max-w-[92vw] flex-col gap-3 border border-border-subtle bg-surface-card p-4 shadow-2xl"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            close();
          }
        }}
      >
        <div className="flex items-baseline gap-2">
          <h2 className="text-xs uppercase tracking-wider text-text-dim">Paste TSV into</h2>
          <span className="min-w-0 truncate font-mono text-xs text-text-secondary">{target.label}</span>
        </div>

        <textarea
          ref={areaRef}
          className="h-56 w-full resize-y border border-border-subtle bg-surface-secondary p-2 font-mono text-[11px] text-text-primary outline-none placeholder:text-text-dim focus:border-mjolnir-gold"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"field a\tfield b\n1\t2\n3\t4"}
          spellCheck={false}
        />
        <p className="font-mono text-[10px] text-text-dim">
          {lines.length === 0
            ? "Paste rows from a spreadsheet or from Copy Block as TSV. The first row names the fields."
            : `${columns} column${columns === 1 ? "" : "s"}, ${rows} row${rows === 1 ? "" : "s"} → ${rows} new element${rows === 1 ? "" : "s"}`}
        </p>

        <label className="flex items-center gap-2 text-[11px] text-text-secondary">
          <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
          Replace the block's elements rather than appending to them
        </label>

        {error && (
          <p className="border border-accent-red/40 bg-accent-red/5 px-3 py-2 font-mono text-[11px] text-accent-red">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="border border-border-subtle px-3 py-1 text-xs text-text-secondary hover:bg-surface-hover"
            onClick={close}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy || rows === 0}
            className="border border-mjolnir-gold/60 px-3 py-1 text-xs text-mjolnir-gold hover:bg-mjolnir-gold/10 disabled:opacity-40"
          >
            {busy ? "Pasting…" : replace ? `Replace with ${rows}` : `Append ${rows}`}
          </button>
        </div>
      </form>
    </div>
  );
}
