import { useEffect, useState } from "react";
import { useEditor } from "../stores/editor-store";
import type { NodeView } from "../lib/api";
import { TagHeader, EditBar } from "./TagChrome";
import {
  COMPONENT_LABELS,
  NOT_EDITABLE,
  editableText,
  elementLabel,
  splitComponents,
} from "../lib/fields";

function canEdit(node: NodeView): boolean {
  return !NOT_EDITABLE.has(node.type) && node.size > 0;
}

const INPUT =
  "border border-border-subtle bg-surface-card px-2 py-1 font-mono text-xs " +
  "text-text-primary outline-none focus:border-mjolnir-gold " +
  "disabled:text-text-dim disabled:bg-surface-secondary";
const EDITED = "border-mjolnir-gold/50 bg-mjolnir-gold/10";

/** One text box that commits on Enter or blur and reverts on Escape. */
function FText({
  value,
  disabled,
  edited,
  wide,
  onCommit,
}: {
  value: string;
  disabled?: boolean;
  edited?: boolean;
  wide?: boolean;
  onCommit: (text: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  // A re-read after an edit replaces the node; follow the new value.
  useEffect(() => setDraft(value), [value]);

  return (
    <input
      className={`${INPUT} ${edited ? EDITED : ""} ${wide ? "w-80" : "w-32"}`}
      value={draft}
      disabled={disabled}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (draft !== value) onCommit(draft);
      }}
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === "Return") && draft !== value) {
          onCommit(draft);
        }
        if (e.key === "Escape") setDraft(value);
      }}
    />
  );
}

/** A field row: fixed-width label column, then the control its type calls for. */
function FField({ node, path }: { node: NodeView; path: string }) {
  const setField = useEditor((s) => s.setField);
  const revertField = useEditor((s) => s.revertField);
  const followReference = useEditor((s) => s.followReference);
  const edited = useEditor((s) => s.tag?.edited ?? []);

  const isEdited = edited.includes(path);
  const editable = canEdit(node);
  const commit = (text: string) => void setField(path, text);

  let control: React.ReactNode;

  if (node.type.endsWith("flags")) {
    control = (
      <div className="min-w-64 max-w-96 border border-border-subtle bg-surface-card px-3 py-2">
        {node.options.map((opt, bit) => {
          const on = node.selected.includes(opt);
          return (
            <label
              key={bit}
              className={`flex items-center gap-2 py-0.5 text-xs ${
                editable ? "cursor-pointer text-text-primary" : "text-text-dim"
              }`}
            >
              <input
                type="checkbox"
                className="accent-(--color-mjolnir-gold)"
                checked={on}
                disabled={!editable}
                onChange={() => {
                  const next = on
                    ? node.selected.filter((s) => s !== opt)
                    : [...node.selected, opt];
                  commit(next.length > 0 ? next.join(" | ") : "none");
                }}
              />
              <span>{opt}</span>
            </label>
          );
        })}
        {node.options.length === 0 && (
          <span className="text-xs text-text-dim">no flags defined</span>
        )}
      </div>
    );
  } else if (node.type.endsWith("enum")) {
    const current = node.selected[0] ?? node.value;
    const known = node.options.includes(current);
    control = (
      <select
        className={`${INPUT} w-64 ${isEdited ? EDITED : ""}`}
        value={current}
        disabled={!editable}
        onChange={(e) => commit(e.target.value)}
      >
        {!known && <option value={current}>{current}</option>}
        {node.options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  } else if (node.type === "tag reference") {
    const has = node.reference !== null && node.reference.path !== "";
    control = (
      <span className="flex min-w-0 flex-1 items-center gap-2">
        <FText
          value={editableText(node)}
          edited={isEdited}
          wide
          disabled={!editable}
          onCommit={commit}
        />
        <button
          type="button"
          className="border border-border-subtle px-2 py-1 text-xs text-text-secondary hover:bg-surface-hover hover:text-mjolnir-gold disabled:opacity-40"
          disabled={!has}
          title={has ? "Open the referenced tag" : "No tag referenced"}
          onClick={() => {
            if (node.reference) {
              void followReference(node.reference.group, node.reference.path);
            }
          }}
        >
          Open
        </button>
        {has && (
          <span className="font-mono text-[10px] text-text-dim">
            {node.reference?.group}
          </span>
        )}
      </span>
    );
  } else if (COMPONENT_LABELS[node.type] && node.value.includes(",")) {
    const labels = COMPONENT_LABELS[node.type];
    const parts = splitComponents(node.value);
    control = (
      <span className="flex flex-wrap items-center gap-3">
        {parts.map((part, i) => (
          <span key={i} className="flex items-center gap-1.5">
            <span className="font-mono text-[10px] text-text-dim">
              {labels[i] ?? i}
            </span>
            <FText
              value={part}
              edited={isEdited}
              disabled={!editable}
              onCommit={(text) => {
                const next = [...parts];
                next[i] = text;
                commit(next.join(", "));
              }}
            />
          </span>
        ))}
      </span>
    );
  } else if (node.type === "data") {
    control = (
      <span className="py-1 font-mono text-xs text-text-dim">
        {node.value || "data"}
      </span>
    );
  } else if (node.type.includes("color") && node.value.startsWith("#")) {
    control = (
      <span className="flex items-center gap-2">
        <span
          className="inline-block h-5 w-9 border border-border-subtle"
          style={{ background: node.value.slice(0, 7) }}
        />
        <FText
          value={node.value}
          edited={isEdited}
          disabled={!editable}
          onCommit={commit}
        />
      </span>
    );
  } else {
    const wide =
      node.type === "string" || node.type === "long string" || node.type === "string id";
    control = (
      <FText
        value={editableText(node)}
        edited={isEdited}
        disabled={!editable}
        wide={wide}
        onCommit={commit}
      />
    );
  }

  return (
    <div className="flex items-start gap-3 py-1">
      <span
        className={`w-44 shrink-0 truncate pt-1 text-sm ${
          editable ? "text-text-secondary" : "text-text-dim"
        }`}
        title={`${node.type} · ${node.size} bytes @ ${node.offset}`}
      >
        {isEdited && <span className="mr-1 text-mjolnir-gold">●</span>}
        {node.name || <em>unnamed</em>}
      </span>
      {control}
      {isEdited && (
        <button
          type="button"
          className="pt-1 font-mono text-[10px] text-text-dim hover:text-text-primary"
          title="Revert this field"
          onClick={() => void revertField(path)}
        >
          undo
        </button>
      )}
    </div>
  );
}

/**
 * A block, struct or array, Guerilla-style: a section bar with a collapse
 * toggle, and for blocks and arrays an element dropdown on the bar itself.
 * The fields below always belong to the one element the dropdown picks.
 */
function FSection({ node, path, depth }: { node: NodeView; path: string; depth: number }) {
  const [open, setOpen] = useState(depth < 1 || node.kind === "struct");
  const [element, setElement] = useState(0);

  const isStruct = node.kind === "struct";
  const elements = isStruct ? [] : node.children;
  const total = node.count ?? elements.length;
  const index = Math.min(element, Math.max(elements.length - 1, 0));
  const current = elements[index];

  const inner = isStruct ? node.children : (current?.children ?? []);
  const innerBase = isStruct ? path : `${path}[${index}]`;

  return (
    <div className="mt-3">
      <div className="flex h-8 items-center gap-2 border border-border-subtle bg-surface-secondary pl-1 pr-2">
        <button
          type="button"
          className="w-5 shrink-0 font-mono text-xs text-text-dim hover:text-text-primary"
          onClick={() => setOpen((v) => !v)}
          title={open ? "Collapse" : "Expand"}
        >
          {open ? "▾" : "▸"}
        </button>
        <span className="truncate text-xs font-semibold uppercase tracking-wider text-text-primary">
          {node.name || node.block || "block"}
        </span>
        {!isStruct && (
          <>
            <span className="shrink-0 font-mono text-[10px] text-text-dim">
              {total}
              {node.max_count !== null ? ` of ${node.max_count}` : ""}
            </span>
            <select
              className={`${INPUT} ml-auto w-80 max-w-[50%] py-0.5`}
              disabled={elements.length === 0}
              value={index}
              onChange={(e) => setElement(Number(e.target.value))}
            >
              {elements.length === 0 && <option>none</option>}
              {elements.map((el, i) => {
                const label = elementLabel(el);
                return (
                  <option key={i} value={i}>
                    {label ? `${i} · ${label}` : `${i}`}
                  </option>
                );
              })}
              {elements.length < total && (
                <option disabled>… {total - elements.length} more not loaded</option>
              )}
            </select>
          </>
        )}
      </div>

      {open && inner.length > 0 && (
        <div className="ml-2.5 border-l border-border-subtle py-1.5 pl-4">
          {inner.map((child, i) => (
            <FNode
              key={`${child.name}-${i}`}
              node={child}
              depth={depth + 1}
              path={
                child.kind === "element"
                  ? `${innerBase}${child.name}`
                  : `${innerBase}.${child.name}`
              }
            />
          ))}
        </div>
      )}
      {open && inner.length === 0 && !isStruct && (
        <div className="ml-2.5 border-l border-border-subtle py-1.5 pl-4 text-xs text-text-dim">
          no elements
        </div>
      )}
    </div>
  );
}

function FNode({ node, path, depth }: { node: NodeView; path: string; depth: number }) {
  if (node.kind === "field") return <FField node={node} path={path} />;
  return <FSection node={node} path={path} depth={depth} />;
}

/** The Guerilla-format inspector: section bars and typed controls. */
export function FormInspector() {
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

      <div className="px-6 py-3">
        {tag.error ? (
          <div className="border border-accent-red/40 bg-accent-red/5 px-4 py-3">
            <p className="text-sm text-text-primary">This tag&rsquo;s values could not be read.</p>
            <p className="mt-1 font-mono text-[11px] text-text-secondary">{tag.error}</p>
          </div>
        ) : tag.fields.length === 0 ? (
          <p className="text-xs text-text-dim">This tag has no user-visible fields.</p>
        ) : (
          tag.fields.map((node, i) => (
            <FNode key={`${node.name}-${i}`} node={node} depth={0} path={node.name} />
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
