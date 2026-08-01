import { useState } from "react";
import { useEditor } from "../stores/editor-store";
import type { NodeView } from "../lib/api";
import { NOT_EDITABLE, RESIZES, editableText, keepTail } from "../lib/fields";
import { TagHeader, EditBar } from "./TagChrome";

/** Blocks larger than this stay collapsed until asked for. */
const AUTO_EXPAND_ELEMENTS = 8;

function typeColor(type: string): string {
  if (type === "block") return "text-accent-blue";
  if (type === "tag reference") return "text-mjolnir-gold";
  if (type.endsWith("enum") || type.endsWith("flags")) return "text-accent-green";
  return "text-text-dim";
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

/** Flat-tree value inspector for the selected tag. */
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
      <TagHeader />
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
