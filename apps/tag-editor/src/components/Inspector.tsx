import { useEffect, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { useEditor } from "../stores/editor-store";
import type { NodeView } from "../lib/api";

/** Blocks larger than this stay collapsed until asked for. */
const AUTO_EXPAND_ELEMENTS = 8;

/** Types with no editable value of their own. */
const NOT_EDITABLE = new Set([
  "data",
  "block",
  "struct",
  "array",
  "pageable resource",
  "api interop",
]);

/** Types whose value lives in a trailing section, so changing one resizes the
 *  tag rather than overwriting bytes. Editable, but worth flagging. */
const RESIZES = new Set(["string id", "tag reference"]);

function typeColor(type: string): string {
  if (type === "block") return "text-accent-blue";
  if (type === "tag reference") return "text-mjolnir-gold";
  if (type.endsWith("enum") || type.endsWith("flags")) return "text-accent-green";
  return "text-text-dim";
}

/**
 * Keep the end of a long path rather than the start. A tag path's distinctive
 * part is its tail, so the usual trailing ellipsis hides exactly what you need.
 */
function keepTail(text: string, max: number): string {
  return text.length <= max ? text : `…${text.slice(text.length - max)}`;
}

/**
 * The value as it should appear in an edit box: what the parser accepts, which
 * is not always what the display shows. An enum reads `large (3)` but is set by
 * name, and flags read `a | b (0x5)` but are set as `a | b`.
 */
function editableText(node: NodeView): string {
  if (node.type === "tag reference") {
    return node.reference && node.reference.path
      ? `${node.reference.group}:${node.reference.path}`
      : "none";
  }
  if (node.type === "string id") return node.value.replace(/^"|"$/g, "");
  if (node.type.endsWith("enum")) return node.selected[0] ?? node.value;
  if (node.type.endsWith("flags")) {
    return node.selected.length > 0 ? node.selected.join(" | ") : "none";
  }
  if (node.type === "string" || node.type === "long string") {
    return node.value.replace(/^"|"$/g, "");
  }
  return node.value.replace(/^\(|\)$/g, "");
}

/** A leaf field: name, value, and the type it was decoded as. */
function Leaf({ node, path }: { node: NodeView; path: string }) {
  const setField = useEditor((s) => s.setField);
  const revertField = useEditor((s) => s.revertField);
  const edited = useEditor((s) => s.tag?.edited ?? []);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [failed, setFailed] = useState<string | null>(null);

  const isEdited = edited.includes(path);
  const canEdit = !NOT_EDITABLE.has(node.type) && node.size > 0;
  const empty = node.value === "";
  const shown =
    node.reference && node.reference.path
      ? `${keepTail(node.reference.path, 52)} (${node.reference.group})`
      : node.value;

  async function commit() {
    setEditing(false);
    if (draft === editableText(node)) return;
    const ok = await setField(path, draft);
    setFailed(ok ? null : "rejected");
  }

  return (
    <div
      className={`flex items-baseline gap-3 py-0.5 ${
        isEdited ? "bg-mjolnir-gold/10" : ""
      }`}
    >
      <span className="w-14 shrink-0 text-right font-mono text-[10px] text-text-dim">
        {node.offset}
      </span>
      <span className="min-w-0 flex-1 truncate text-sm" title={path}>
        {isEdited && <span className="mr-1 text-mjolnir-gold">●</span>}
        {node.name || <em className="text-text-dim">unnamed</em>}
      </span>

      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => void commit()}
          onKeyDown={(e) => {
            if (e.key === "Enter") void commit();
            if (e.key === "Escape") setEditing(false);
          }}
          className="min-w-0 flex-1 border border-mjolnir-gold bg-surface-card px-1 text-right font-mono text-xs outline-none"
        />
      ) : (
        <button
          type="button"
          disabled={!canEdit}
          onClick={() => {
            setDraft(editableText(node));
            setFailed(null);
            setEditing(true);
          }}
          title={
            !canEdit
              ? `${node.value}\n\n${node.type} values are not editable`
              : node.type === "tag reference"
                ? `${node.value}\n\nClick to edit. Written as group:path, or none. Resizes the tag.`
                : RESIZES.has(node.type)
                  ? `${node.value}\n\nClick to edit as plain text. Resizes the tag.`
                  : `${node.value}\n\nClick to edit`
          }
          className={`min-w-0 flex-1 truncate text-right font-mono text-xs ${
            failed
              ? "text-accent-red"
              : isEdited
                ? "text-mjolnir-gold"
                : empty
                  ? "text-text-dim"
                  : "text-text-primary"
          } ${canEdit ? "hover:underline" : "cursor-default"}`}
        >
          {empty ? "—" : shown}
        </button>
      )}

      {isEdited && !editing && (
        <button
          type="button"
          onClick={() => void revertField(path)}
          title="Revert this field"
          className="shrink-0 font-mono text-[10px] text-text-dim hover:text-text-primary"
        >
          undo
        </button>
      )}
      <span className={`w-36 shrink-0 font-mono text-[10px] ${typeColor(node.type)}`}>
        {node.type}
      </span>
    </div>
  );
}

/** Header line for anything that expands. */
function Branch({
  node,
  open,
  onToggle,
}: {
  node: NodeView;
  open: boolean;
  onToggle: () => void;
}) {
  // `count` is what the tag holds; `children` may be fewer, because a tag like
  // scenario_structure_bsp has millions of elements and building them all costs
  // gigabytes. Report the real number and flag when the list is partial.
  const total = node.count ?? node.children.length;
  const shown = node.children.length;
  const partial = shown < total;
  const label =
    node.kind === "block"
      ? `${total} element${total === 1 ? "" : "s"}${
          node.max_count !== null ? ` of ${node.max_count}` : ""
        }${partial ? ` · first ${shown} shown` : ""}`
      : node.kind === "array"
        ? `array of ${total}${partial ? ` · first ${shown} shown` : ""}`
        : node.type;

  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-baseline gap-3 py-0.5 text-left hover:bg-surface-secondary/40"
    >
      <span className="w-14 shrink-0 text-right font-mono text-[10px] text-text-dim">
        {node.offset}
      </span>
      <span className="w-3 shrink-0 font-mono text-[10px] text-text-dim">
        {node.children.length > 0 ? (open ? "▾" : "▸") : " "}
      </span>
      <span className="min-w-0 flex-1 truncate text-sm">
        {node.name || <em className="text-text-dim">unnamed</em>}
      </span>
      <span className="shrink-0 font-mono text-[10px] text-text-dim">{label}</span>
      {node.block && (
        <span className="hidden shrink-0 font-mono text-[10px] text-text-dim md:inline">
          {node.block}
        </span>
      )}
    </button>
  );
}

/** Join a parent path with a child, matching what `mjolnir set --field` takes. */
function childPath(parent: string, node: NodeView): string {
  if (node.kind === "element") return `${parent}${node.name}`;
  return parent ? `${parent}.${node.name}` : node.name;
}

function Node({ node, depth, path }: { node: NodeView; depth: number; path: string }) {
  // Structs are part of the shape rather than a list, so they open by default.
  // Blocks and arrays open only when short enough not to bury what follows.
  const [open, setOpen] = useState(
    node.kind === "struct" ||
      (node.kind === "element" && depth < 3) ||
      node.children.length <= AUTO_EXPAND_ELEMENTS,
  );

  if (node.kind === "field") {
    return <Leaf node={node} path={path} />;
  }

  return (
    <div>
      <Branch node={node} open={open} onToggle={() => setOpen((v) => !v)} />
      {open && node.children.length > 0 && (
        <div className="ml-4 border-l border-border-subtle/60 pl-2">
          {node.children.map((child, i) => (
            <Node
              key={`${child.name}-${i}`}
              node={child}
              depth={depth + 1}
              path={childPath(path, child)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Pending edits, and the only way they leave the editor. */
function EditBar() {
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

/** Guerilla-style value inspector for the selected tag. */
export function Inspector() {
  const { tag, tagLoading, selectedTag } = useEditor();

  if (tagLoading) {
    return <Centered>Reading tag…</Centered>;
  }
  if (!tag) {
    return (
      <Centered>
        {selectedTag === null ? "Select a tag to inspect." : "Nothing to show."}
      </Centered>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <header className="sticky top-0 z-10 border-b border-border-subtle bg-surface-primary px-6 py-4">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="font-mono text-lg text-mjolnir-gold">{tag.group}</h1>
          <span className="font-mono text-xs text-text-dim">{tag.four_cc}</span>
          <span className="font-mono text-xs text-text-dim">v{tag.version}</span>
          <span
            className={`ml-auto font-mono text-[11px] ${
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
      </header>

      <EditBar />

      <div className="px-6 py-4">
        {tag.error ? (
          <div className="border border-accent-red/40 bg-accent-red/5 px-4 py-3">
            <p className="text-sm text-text-primary">This tag&rsquo;s values could not be read.</p>
            <p className="mt-1 font-mono text-[11px] text-text-secondary">{tag.error}</p>
            <p className="mt-2 text-xs text-text-dim">
              The definition is still complete; only the values are affected.
            </p>
          </div>
        ) : tag.fields.length === 0 ? (
          <p className="text-xs text-text-dim">This tag has no user-visible fields.</p>
        ) : (
          tag.fields.map((node, i) => (
            <Node key={`${node.name}-${i}`} node={node} depth={0} path={node.name} />
          ))
        )}
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-dim">
      {children}
    </div>
  );
}
