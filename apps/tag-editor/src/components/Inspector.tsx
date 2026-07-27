import { useState } from "react";
import { useEditor } from "../stores/editor-store";
import type { NodeView } from "../lib/api";

/** Blocks larger than this stay collapsed until asked for. */
const AUTO_EXPAND_ELEMENTS = 8;

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

/** A leaf field: name, value, and the type it was decoded as. */
function Leaf({ node }: { node: NodeView }) {
  const empty = node.value === "";
  const shown =
    node.reference && node.reference.path
      ? `${keepTail(node.reference.path, 52)} (${node.reference.group})`
      : node.value;
  return (
    <div className="flex items-baseline gap-3 py-0.5">
      <span className="w-14 shrink-0 text-right font-mono text-[10px] text-text-dim">
        {node.offset}
      </span>
      <span className="min-w-0 flex-1 truncate text-sm" title={node.name}>
        {node.name || <em className="text-text-dim">unnamed</em>}
      </span>
      <span
        className={`min-w-0 flex-1 truncate text-right font-mono text-xs ${
          empty ? "text-text-dim" : "text-text-primary"
        }`}
        title={node.value}
      >
        {empty ? "—" : shown}
      </span>
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

function Node({ node, depth }: { node: NodeView; depth: number }) {
  // Structs are part of the shape rather than a list, so they open by default.
  // Blocks and arrays open only when short enough not to bury what follows.
  const [open, setOpen] = useState(
    node.kind === "struct" ||
      (node.kind === "element" && depth < 3) ||
      node.children.length <= AUTO_EXPAND_ELEMENTS,
  );

  if (node.kind === "field") {
    return <Leaf node={node} />;
  }

  return (
    <div>
      <Branch node={node} open={open} onToggle={() => setOpen((v) => !v)} />
      {open && node.children.length > 0 && (
        <div className="ml-4 border-l border-border-subtle/60 pl-2">
          {node.children.map((child, i) => (
            <Node key={`${child.name}-${i}`} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
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
          tag.fields.map((node, i) => <Node key={`${node.name}-${i}`} node={node} depth={0} />)
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
