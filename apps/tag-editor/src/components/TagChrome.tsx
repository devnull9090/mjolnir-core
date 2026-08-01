import { useEffect, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { useEditor } from "../stores/editor-store";

/** Links longer than this start collapsed, so a scenario's hundreds of
 *  imports do not take over the inspector. */
const LINKS_COLLAPSED_OVER = 24;

/** Chips for the packages this tag imports; openable ones open in a tab. */
function LinkedAssets() {
  const links = useEditor((s) => s.tagLinks);
  const openTab = useEditor((s) => s.openTab);
  const [showAll, setShowAll] = useState(false);
  const [open, setOpen] = useState<boolean | null>(null);

  if (links.length === 0) return null;
  const openable = links.filter((l) => l.index !== null);
  const rest = links.filter((l) => l.index === null);
  const shown = showAll ? links : openable;
  const expanded = open ?? links.length <= LINKS_COLLAPSED_OVER;

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen(!expanded)}
        className="font-mono text-[10px] uppercase tracking-wider text-text-dim hover:text-text-secondary"
        title={expanded ? "Collapse the linked packages" : "Show the linked packages"}
      >
        {expanded ? "▾" : "▸"} linked · {openable.length} openable
        {rest.length > 0 ? ` · ${rest.length} unreal` : ""}
      </button>
      {expanded && (
        <div className="mt-1 flex max-h-28 flex-wrap content-start items-center gap-1.5 overflow-y-auto pr-1">
          {shown.map((l) => (
            <button
              key={l.package}
              type="button"
              disabled={l.index === null}
              title={
                l.index === null
                  ? `${l.package}\n\nAn Unreal ${l.label.startsWith("BP_") ? "Blueprint" : "asset"}; the editor cannot open this kind yet.`
                  : l.package
              }
              onClick={() => {
                if (l.index !== null) {
                  void openTab(l.kind === "texture" ? "texture" : "tag", l.index, l.label);
                }
              }}
              className={`border px-1.5 py-0.5 font-mono text-[10px] ${
                l.index === null
                  ? "cursor-default border-border-subtle/60 text-text-dim"
                  : l.kind === "texture"
                    ? "border-accent-blue/40 text-accent-blue hover:bg-accent-blue/10"
                    : "border-mjolnir-gold/40 text-mjolnir-gold hover:bg-mjolnir-gold/10"
              }`}
            >
              {l.label}
            </button>
          ))}
          {rest.length > 0 && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="font-mono text-[10px] text-text-dim hover:text-text-secondary"
            >
              {showAll ? "hide unreal" : `+${rest.length} unreal`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** Header shared by both inspector views: identity, vitals, view toggle. */
export function TagHeader() {
  const { tag, viewMode } = useEditor();
  const setViewMode = useEditor((s) => s.setViewMode);

  if (!tag) return null;
  const other = viewMode === "form" ? "tree" : "form";

  return (
    <header className="sticky top-0 z-10 border-b border-border-subtle bg-surface-primary px-6 py-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="font-mono text-lg text-mjolnir-gold">{tag.group}</h1>
        <span className="font-mono text-xs text-text-dim">{tag.four_cc}</span>
        <span className="font-mono text-xs text-text-dim">v{tag.version}</span>
        <button
          type="button"
          onClick={() => setViewMode(other)}
          title={
            other === "form"
              ? "Guerilla-style form: section bars, element dropdowns, typed controls"
              : "Flat tree of every field with offsets and types"
          }
          className="ml-auto border border-border-subtle px-2 py-0.5 text-[11px] text-text-secondary hover:bg-surface-hover"
        >
          {other === "form" ? "Form view" : "Tree view"}
        </button>
        <span
          className={`font-mono text-[11px] ${
            tag.data_exact ? "text-accent-green" : "text-text-dim"
          }`}
          title={
            tag.data_exact
              ? "The value walk consumed the data payload exactly."
              : "The values shown may be incomplete."
          }
        >
          {tag.data_exact ? "values exact" : "values partial"}
        </span>
      </div>
      <p className="mt-1 truncate font-mono text-[11px] text-text-secondary">{tag.path}</p>
      <p className="mt-1 font-mono text-[11px] text-text-dim">
        {tag.chunk_size.toLocaleString()} bytes · {tag.data_size.toLocaleString()} bytes of data ·{" "}
        {tag.node_count.toLocaleString()} fields
      </p>
      <LinkedAssets />
    </header>
  );
}

/** Pending edits, and the only way they leave the editor. */
export function EditBar() {
  const { tag, lastEdit, editError } = useEditor();
  const revertTag = useEditor((s) => s.revertTag);
  const exportTag = useEditor((s) => s.exportTag);
  const [wrote, setWrote] = useState<string | null>(null);

  useEffect(() => setWrote(null), [tag?.path]);

  if (!tag) return null;
  const count = tag.edited.length;
  if (count === 0 && !editError) return null;

  async function onExport() {
    if (!tag) return;
    const name = tag.path.split("/").pop() ?? "tag.ubulk";
    const dest = await save({ defaultPath: name });
    if (!dest) return;
    const written = await exportTag(dest);
    if (written !== null) setWrote(`${written.toLocaleString()} bytes to ${dest}`);
  }

  return (
    <div className="border-b border-mjolnir-gold/40 bg-mjolnir-gold/5 px-6 py-2">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className="text-mjolnir-gold">
          {count} unsaved edit{count === 1 ? "" : "s"}
        </span>
        <button
          type="button"
          onClick={() => void onExport()}
          disabled={count === 0}
          className="border border-mjolnir-gold/60 px-2 py-0.5 text-mjolnir-gold hover:bg-mjolnir-gold/10 disabled:opacity-40"
        >
          Export patched tag…
        </button>
        <button
          type="button"
          onClick={() => void revertTag()}
          disabled={count === 0}
          className="border border-border-subtle px-2 py-0.5 text-text-secondary hover:bg-surface-hover disabled:opacity-40"
        >
          Revert all
        </button>
        <span className="ml-auto font-mono text-[10px] text-text-dim">
          The game&rsquo;s containers are read-only; edits export to a file.
        </span>
      </div>
      {lastEdit && (
        <p className="mt-1 font-mono text-[10px] text-text-secondary">
          {lastEdit.path}: {lastEdit.before} → {lastEdit.after} ({lastEdit.changed_bytes}{" "}
          byte{lastEdit.changed_bytes === 1 ? "" : "s"} changed)
        </p>
      )}
      {editError && (
        <p className="mt-1 font-mono text-[10px] text-accent-red">{editError}</p>
      )}
      {wrote && <p className="mt-1 font-mono text-[10px] text-accent-green">Wrote {wrote}</p>}
    </div>
  );
}
