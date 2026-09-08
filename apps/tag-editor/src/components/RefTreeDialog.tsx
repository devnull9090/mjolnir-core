import { useState } from "react";
import { useEditor } from "../stores/editor-store";
import { copyText } from "../lib/clipboard";
import type { RefNode } from "../lib/api";

/** The tree as indented text, one tag per line, for a report or a diff. */
export function refTreeText(node: RefNode, depth = 0): string {
  const pad = "  ".repeat(depth);
  const flag = node.cycle ? " (cycle)" : node.index === null ? " (missing)" : "";
  const more = node.truncated ? " …" : "";
  const line = `${pad}${node.path}.${node.group}${flag}${more}`;
  return [line, ...node.children.map((c) => refTreeText(c, depth + 1))].join("\n");
}

function countNodes(node: RefNode): number {
  return 1 + node.children.reduce((n, c) => n + countNodes(c), 0);
}

function Branch({ node, depth }: { node: RefNode; depth: number }) {
  const [open, setOpen] = useState(depth < 2);
  const openTab = useEditor((s) => s.openTab);
  const leaf = node.path.split(/[\\/]/).pop() ?? node.path;
  const has = node.children.length > 0;
  return (
    <li>
      <div className="flex items-baseline gap-1" style={{ paddingLeft: depth * 14 }}>
        <button
          type="button"
          className={`w-4 shrink-0 font-mono text-[10px] ${has ? "text-text-dim hover:text-text-primary" : "text-transparent"}`}
          onClick={() => setOpen(!open)}
          disabled={!has}
        >
          {has ? (open ? "▾" : "▸") : "·"}
        </button>
        <button
          type="button"
          disabled={node.index === null}
          className={`min-w-0 truncate font-mono text-xs ${
            node.index === null
              ? "cursor-default text-accent-red"
              : "text-text-primary hover:text-mjolnir-gold hover:underline"
          }`}
          title={
            node.index === null
              ? `${node.path} — not in this installation`
              : `${node.path}.${node.group} — open`
          }
          onClick={() => {
            if (node.index !== null) {
              void openTab("tag", node.index, `${leaf}.${node.group}`, {
                group: node.group,
                path: node.path,
              });
            }
          }}
        >
          {leaf}
        </button>
        <span className="shrink-0 font-mono text-[10px] text-text-dim">{node.group}</span>
        {node.cycle && (
          <span className="shrink-0 text-[10px] text-text-dim" title="Already on the path above">
            cycle
          </span>
        )}
        {node.truncated && (
          <span className="shrink-0 text-[10px] text-text-dim" title="Deeper references not shown">
            …
          </span>
        )}
        {has && !open && (
          <span className="shrink-0 font-mono text-[10px] text-text-dim">{node.children.length}</span>
        )}
      </div>
      {open && has && (
        <ul>
          {node.children.map((c, i) => (
            <Branch key={`${c.group}:${c.path}:${i}`} node={c} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * What a tag references, and what those reference, a few levels deep — the
 * graph behind a tag, walked from its body. Each row opens the tag; the
 * whole tree copies as indented text.
 */
export function RefTreeDialog() {
  const tree = useEditor((s) => s.refTree);
  const loading = useEditor((s) => s.refTreeLoading);
  const depth = useEditor((s) => s.refTreeDepth);
  const close = useEditor((s) => s.closeRefTree);
  const reload = useEditor((s) => s.loadRefTree);

  if (!tree && !loading) return null;

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
      <div className="mx-auto mt-[8vh] flex h-[80vh] w-[52rem] max-w-[94vw] flex-col border border-border-subtle bg-surface-card shadow-2xl">
        <div className="flex items-center gap-3 border-b border-border-subtle px-4 py-2">
          <h2 className="text-xs uppercase tracking-wider text-text-dim">References</h2>
          {tree && (
            <span className="min-w-0 truncate font-mono text-xs text-text-secondary">
              {tree.path}.{tree.group}
            </span>
          )}
          <label className="ml-auto flex items-center gap-1 text-[10px] text-text-dim">
            depth
            <select
              className="border border-border-subtle bg-surface-secondary px-1 py-0.5 font-mono text-[10px] text-text-primary"
              value={depth}
              onChange={(e) => void reload(Number(e.target.value))}
            >
              {[1, 2, 3, 4, 5, 6].map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="border border-border-subtle px-2 py-0.5 text-[10px] text-text-secondary hover:bg-surface-hover"
            disabled={!tree}
            onClick={() => tree && void copyText(refTreeText(tree))}
            title="Copy the whole tree as indented text"
          >
            copy
          </button>
          <button
            type="button"
            className="text-[10px] text-text-dim hover:text-text-secondary"
            onClick={close}
          >
            close
          </button>
        </div>
        {loading ? (
          <p className="px-4 py-6 text-xs text-text-dim">Walking references…</p>
        ) : tree ? (
          <>
            <div className="min-h-0 flex-1 overflow-auto py-2">
              <ul>
                <Branch node={tree} depth={0} />
              </ul>
            </div>
            <p className="border-t border-border-subtle px-4 py-1 text-[10px] text-text-dim">
              {countNodes(tree) - 1} reference{countNodes(tree) - 1 === 1 ? "" : "s"} to depth{" "}
              {depth}, from the bodies as this mod leaves them. At most 200 per tag and 4,000 in
              all; a red name is a reference this installation does not resolve.
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}
