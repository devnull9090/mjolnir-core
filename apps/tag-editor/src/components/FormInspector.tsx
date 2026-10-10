import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { degreesToRadiansText, isAngleType, radiansToDegreesText } from "../lib/angles";
import { fieldPath } from "../lib/paths";
import { refKey, useEditor } from "../stores/editor-store";
import type { NodeView } from "../lib/api";
import { useTabUi } from "../lib/tab-ui";
import { scheduleSaveSession } from "../lib/session";
import { copyText } from "../lib/clipboard";
import { showContextMenu, type MenuItem } from "./ContextMenu";
import { RefPreview } from "./RefPreview";
import { TagHeader, EditBar } from "./TagChrome";
import {
  COMPONENT_LABELS,
  RUNTIME_NOTE,
  editableText,
  elementLabel,
  isEditable,
  splitComponents,
} from "../lib/fields";

const INPUT =
  "border border-border-subtle bg-surface-card px-2 py-1 font-mono text-xs " +
  "text-text-primary outline-none focus:border-mjolnir-gold " +
  "disabled:text-text-dim disabled:bg-surface-secondary";
const EDITED = "border-mjolnir-gold/50 bg-mjolnir-gold/10";
const INVALID = "border-accent-red/60 bg-accent-red/5";

/** One text box that commits on Enter or blur and reverts on Escape. */
function FText({
  value,
  disabled,
  edited,
  invalid,
  wide,
  onCommit,
}: {
  value: string;
  disabled?: boolean;
  edited?: boolean;
  /** Red tint for a value that is well-formed but points at nothing. */
  invalid?: boolean;
  wide?: boolean;
  onCommit: (text: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  // A re-read after an edit replaces the node; follow the new value.
  useEffect(() => setDraft(value), [value]);

  return (
    <input
      className={`${INPUT} ${edited ? EDITED : ""} ${invalid ? INVALID : ""} ${wide ? "w-80" : "w-32"}`}
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
/**
 * The field lists enclosing a field, outermost (the tag's root) first. A block
 * index names its target block by definition, and the nearest enclosing list
 * holding a block of that definition is the one it indexes.
 */
type Scopes = NodeView[][];

/** The block a block index points into: the nearest enclosing block of its
 *  target definition, or null when none is in view. */
function indexTarget(scopes: Scopes, definition: string): NodeView | null {
  for (let i = scopes.length - 1; i >= 0; i--) {
    const hit = scopes[i].find((n) => n.kind === "block" && n.block === definition);
    if (hit) return hit;
  }
  return null;
}

/** Targets up to this long get a dropdown; longer ones keep the text box. */
const INDEX_OPTION_LIMIT = 512;

/** `#2` → 2, `none` → -1, `none (-5)` → -5. */
function indexOf(value: string): number {
  if (value.startsWith("#")) return Number.parseInt(value.slice(1), 10);
  const raw = /\((-?\d+)\)/.exec(value);
  return raw ? Number.parseInt(raw[1], 10) : -1;
}

/** `character_palette_block` → `character palette`. */
function blockTitle(definition: string): string {
  return definition.replace(/_block$/, "").replace(/_/g, " ");
}

/**
 * A block index as a choice among the elements it can point at, named the
 * way the block's own dropdown names them ("2 · crewman"). A target that is
 * not in view, too long, or read only in part keeps the text box, with the
 * current element's name beside it when that element was read.
 */
function FBlockIndex({
  node,
  scopes,
  edited,
  editable,
  onCommit,
}: {
  node: NodeView;
  scopes: Scopes;
  edited: boolean;
  editable: boolean;
  onCommit: (text: string) => void;
}) {
  const definition = node.index_target!;
  const target = indexTarget(scopes, definition);
  const current = indexOf(node.value);
  const title = `Indexes the ${blockTitle(definition)} block`;
  const total = target ? (target.count ?? target.children.length) : 0;
  const first = target?.first ?? 0;
  const labelOf = (i: number) => {
    const el = target && i >= first ? target.children[i - first] : undefined;
    return el ? elementLabel(el) : null;
  };
  const complete =
    target !== null &&
    first === 0 &&
    target.children.length >= total &&
    total <= INDEX_OPTION_LIMIT;

  if (!complete) {
    const label = current >= 0 ? labelOf(current) : null;
    return (
      <span className="flex items-center gap-2" title={title}>
        <FText value={editableText(node)} edited={edited} disabled={!editable} onCommit={onCommit} />
        <span className="font-mono text-[10px] text-text-dim">
          {label ? `${label} · ` : ""}
          {blockTitle(definition)}
        </span>
      </span>
    );
  }
  return (
    <span className="flex items-center gap-2" title={title}>
      <select
        className={`${INPUT} w-64 ${edited ? EDITED : ""} ${current >= total ? INVALID : ""}`}
        value={String(current)}
        disabled={!editable}
        onChange={(e) => onCommit(e.target.value === "-1" ? "none" : e.target.value)}
      >
        <option value="-1">none</option>
        {current < -1 && <option value={String(current)}>none ({current})</option>}
        {current >= total && (
          <option value={String(current)}>#{current} · past the end</option>
        )}
        {Array.from({ length: total }, (_, i) => {
          const label = labelOf(i);
          return (
            <option key={i} value={String(i)}>
              {label ? `${i} · ${label}` : `${i}`}
            </option>
          );
        })}
      </select>
      <span className="font-mono text-[10px] text-text-dim">{blockTitle(definition)}</span>
    </span>
  );
}

function FField({ node, path, scopes }: { node: NodeView; path: string; scopes: Scopes }) {
  const setField = useEditor((s) => s.setField);
  const revertField = useEditor((s) => s.revertField);
  const followReference = useEditor((s) => s.followReference);
  const edited = useEditor((s) => s.tag?.edited ?? []);
  const refHit = useEditor((s) =>
    node.reference && node.reference.path !== ""
      ? s.refStatus[refKey(node.reference.group, node.reference.path)]
      : undefined,
  );

  const isEdited = edited.includes(path);
  const editable = isEditable(node);
  // Angles convert at the edge: shown in degrees when asked, stored in radians.
  const degreesOn = useEditor((s) => s.degrees);
  const angular = degreesOn && isAngleType(node.type);
  const shownNode = angular ? { ...node, value: radiansToDegreesText(node.value) } : node;
  const commit = (text: string) =>
    void setField(path, angular ? degreesToRadiansText(text) : text);

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
  } else if (node.index_target) {
    control = (
      <FBlockIndex
        node={node}
        scopes={scopes}
        edited={isEdited}
        editable={editable}
        onCommit={commit}
      />
    );
  } else if (node.type === "tag reference") {
    const has = node.reference !== null && node.reference.path !== "";
    // null is a resolved answer of "nowhere"; undefined means the batched
    // resolve has not landed yet, and casts no aspersions either way.
    const broken = has && refHit === null;
    control = (
      <span className="flex min-w-0 flex-1 items-center gap-2">
        <FText
          value={editableText(node)}
          edited={isEdited}
          invalid={broken}
          wide
          disabled={!editable}
          onCommit={commit}
        />
        <button
          type="button"
          className="border border-border-subtle px-2 py-1 text-xs text-text-secondary hover:bg-surface-hover hover:text-mjolnir-gold disabled:opacity-40"
          disabled={!has || broken}
          title={
            broken
              ? "This reference does not exist in this installation"
              : has
                ? "Open the referenced tag"
                : "No tag referenced"
          }
          onClick={() => {
            if (node.reference) {
              void followReference(node.reference.group, node.reference.path);
            }
          }}
        >
          Open
        </button>
        {has && node.reference && <RefPreview reference={node.reference} />}
      </span>
    );
  } else if (COMPONENT_LABELS[node.type] && shownNode.value.includes(",")) {
    const labels = COMPONENT_LABELS[node.type];
    const parts = splitComponents(shownNode.value);
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
        value={editableText(shownNode)}
        edited={isEdited}
        disabled={!editable}
        wide={wide}
        onCommit={commit}
      />
    );
  }

  return (
    <div
      className="flex items-start gap-3 py-1"
      onContextMenu={(e) => {
        // Text controls keep the native cut/copy/paste menu.
        if ((e.target as HTMLElement).closest("input, select, textarea")) return;
        showContextMenu(e, [
          {
            label: "Revert Field",
            action: () => void revertField(path),
            disabled: !isEdited,
          },
          { label: "Copy Field Path", action: () => void copyText(path) },
        ]);
      }}
    >
      <span
        className={`w-44 shrink-0 truncate pt-1 text-sm ${
          editable ? "text-text-secondary" : "text-text-dim"
        }`}
        title={
          `${node.type} · ${node.size} bytes @ ${node.offset}` +
          (node.runtime ? `

${RUNTIME_NOTE}, so an edit here would be overwritten.` : "") +
          (node.feeds.length > 0
            ? `

The game computes ${node.feeds.join(", ")} from this when the tag loads.`
            : "")
        }
      >
        {isEdited && <span className="mr-1 text-mjolnir-gold">●</span>}
        {node.name || <em>unnamed</em>}
        {angular && (
          <span className="ml-1 font-mono text-[10px] text-text-dim" title="Shown in degrees; the tag stores radians">
            °
          </span>
        )}
      </span>
      {control}
      {node.runtime && (
        <span className="pt-1.5 text-[10px] italic text-text-dim">{RUNTIME_NOTE}</span>
      )}
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
const BAR_BUTTON =
  "shrink-0 border border-border-subtle px-1.5 py-0.5 font-mono text-[10px] " +
  "text-text-secondary hover:bg-surface-hover hover:text-mjolnir-gold disabled:opacity-40";

/** Blocks up to this long list every element in the dropdown; a longer one
 *  (a BSP's millions) lists the page read and offers a go-to box. */
const OPTION_LIMIT = 4096;

/** The element indices a block's dropdown offers. */
function elementChoices(total: number, first: number, read: number, selected: number): number[] {
  if (total <= OPTION_LIMIT) return Array.from({ length: total }, (_, i) => i);
  const page = Array.from({ length: read }, (_, i) => first + i);
  // The selection is shown even before the page holding it arrives.
  if (total > 0 && (selected < first || selected >= first + read)) page.unshift(selected);
  return page;
}

function FSection({
  node,
  path,
  depth,
  scopes,
}: {
  node: NodeView;
  path: string;
  depth: number;
  scopes: Scopes;
}) {
  // Expansion and the element pick initialise from the tab's remembered state
  // and write through to it, so leaving and returning to the tab lands on the
  // same view. The component itself remounts per activation.
  const ui = useTabUi();
  const [open, setOpenState] = useState(() => ui?.open[path] ?? (depth < 1 || node.kind === "struct"));
  const [element, setElementState] = useState(() => ui?.element[path] ?? 0);
  const setOpen = (v: boolean) => {
    setOpenState(v);
    if (ui) {
      ui.open[path] = v;
      scheduleSaveSession();
    }
  };
  const setElement = (i: number) => {
    setElementState(i);
    if (ui) {
      ui.element[path] = i;
      scheduleSaveSession();
    }
  };
  const editElements = useEditor((s) => s.editElements);
  const revertField = useEditor((s) => s.revertField);
  const edited = useEditor((s) => s.tag?.edited ?? []);
  const copyElement = useEditor((s) => s.copyElement);
  const pasteElement = useEditor((s) => s.pasteElement);
  const copyBlockTsv = useEditor((s) => s.copyBlockTsv);
  const openTsvPaste = useEditor((s) => s.openTsvPaste);
  const clipboard = useEditor((s) => s.elementClipboard);
  const refreshTag = useEditor((s) => s.refreshTag);

  const isStruct = node.kind === "struct";
  // Only a block can gain or lose elements; an array's count is fixed by the
  // definition.
  const isBlock = node.kind === "block";
  // A long block is read one page at a time: `children` are elements
  // `first`… of `total`, the page holding the selected element.
  const elements = isStruct ? [] : node.children;
  const first = node.first ?? 0;
  const total = node.count ?? elements.length;
  const index = Math.min(element, Math.max(total - 1, 0));
  const current = index >= first ? elements[index - first] : undefined;
  const hasOps = isBlock && edited.includes(path);
  const atMax = node.max_count !== null && total >= node.max_count;

  // The selection sits outside the page read: read again, and the read pages
  // to it. Once per selection, so a read that still cannot reach it (the
  // tag's node budget ran out) does not loop.
  const requested = useRef<number | null>(null);
  useEffect(() => {
    if (isStruct || total === 0 || current) {
      requested.current = null;
      return;
    }
    if (requested.current === index) return;
    requested.current = index;
    void refreshTag();
  }, [isStruct, total, current, index, refreshTag]);

  const inner = isStruct ? node.children : (current?.children ?? []);
  const innerScopes = [...scopes, inner];
  const innerBase = isStruct ? path : `${path}[${index}]`;

  const add = async () => {
    if (await editElements(path, "add")) {
      setElement(total);
      setOpen(true);
    }
  };
  const duplicate = async () => {
    if (await editElements(path, "duplicate", index)) {
      setElement(index + 1);
      setOpen(true);
    }
  };
  // A fresh element in front of the selected one, which stays selected.
  const insert = async () => {
    if (await editElements(path, "insert", total === 0 ? 0 : index)) {
      setOpen(true);
    }
  };
  // The clipboard only fits a block of the same definition.
  const canPaste = clipboard !== null && clipboard.block === (node.block ?? "");
  const pasteTitle =
    clipboard === null
      ? "Nothing copied yet — copy an element first"
      : canPaste
        ? `Paste ${clipboard.source} after the selected element`
        : `The clipboard holds a ${clipboard.block} element; this block holds ${node.block ?? "another kind"}`;
  const paste = async () => {
    const at = total === 0 ? null : index + 1;
    if (await pasteElement(path, at)) {
      setElement(at ?? 0);
      setOpen(true);
    }
  };
  const label = node.name || node.block || "block";

  const barMenu = (e: React.MouseEvent) => {
    // A right-click on the element dropdown keeps the control's own behavior.
    if ((e.target as HTMLElement).closest("input, select, textarea")) return;
    const items: MenuItem[] = [];
    if (isBlock) {
      items.push(
        {
          label: "Add Element",
          action: () => void add(),
          disabled: atMax,
          title: atMax ? `This block allows at most ${node.max_count} elements` : undefined,
        },
        {
          label: "Duplicate Element",
          action: () => void duplicate(),
          disabled: !current || atMax,
        },
        {
          label: "Insert Element Before",
          action: () => void insert(),
          disabled: atMax,
        },
        {
          label: "Delete Element",
          action: () => void editElements(path, "remove", index),
          disabled: !current,
          danger: true,
        },
        "separator",
        {
          label: "Copy Element",
          action: () => void copyElement(path, index),
          disabled: !current,
        },
        {
          label: "Paste Element After",
          action: () => void paste(),
          disabled: !canPaste || atMax,
          title: pasteTitle,
        },
        "separator",
        {
          label: "Copy Block as TSV",
          action: () => void copyBlockTsv(path),
          disabled: total === 0,
          title: "One row per element, one column per field; nested blocks are left out",
        },
        {
          label: "Paste TSV into Block…",
          action: () => openTsvPaste(path, label),
          title: "Rows become new elements; the header names the fields",
        },
        "separator",
        {
          label: "Revert Block",
          action: () => void revertField(path),
          disabled: !hasOps,
          title: "Revert this section's element changes, and every edit inside its elements",
        },
      );
    }
    items.push({ label: "Copy Field Path", action: () => void copyText(path) });
    showContextMenu(e, items);
  };

  return (
    <div className="mt-3">
      <div
        className="flex h-8 items-center gap-2 border border-border-subtle bg-surface-secondary pl-1 pr-2"
        onContextMenu={barMenu}
      >
        <button
          type="button"
          className="w-5 shrink-0 font-mono text-xs text-text-dim hover:text-text-primary"
          onClick={() => setOpen(!open)}
          title={open ? "Collapse" : "Expand"}
        >
          {open ? "▾" : "▸"}
        </button>
        <span className="truncate text-xs font-semibold uppercase tracking-wider text-text-primary">
          {hasOps && <span className="mr-1 text-mjolnir-gold">●</span>}
          {node.name || node.block || "block"}
        </span>
        {!isStruct && (
          <>
            <span className="shrink-0 font-mono text-[10px] text-text-dim">
              {total}
              {node.max_count !== null ? ` of ${node.max_count}` : ""}
            </span>
            {total > OPTION_LIMIT && (
              <span className="ml-auto flex shrink-0 items-center gap-1" title={`Go to element 0–${total - 1}`}>
                <span className="font-mono text-[10px] text-text-dim">go to</span>
                <FText
                  value={String(index)}
                  onCommit={(text) => {
                    const n = Number.parseInt(text, 10);
                    if (Number.isInteger(n)) setElement(Math.min(Math.max(n, 0), total - 1));
                  }}
                />
              </span>
            )}
            <select
              className={`${INPUT} ${total > OPTION_LIMIT ? "" : "ml-auto"} w-80 max-w-[50%] py-0.5`}
              disabled={total === 0}
              value={index}
              onChange={(e) => setElement(Number(e.target.value))}
            >
              {total === 0 && <option>none</option>}
              {elementChoices(total, first, elements.length, index).map((i) => {
                const el = i >= first ? elements[i - first] : undefined;
                const label = el ? elementLabel(el) : null;
                return (
                  <option key={i} value={i}>
                    {label ? `${i} · ${label}` : `${i}`}
                  </option>
                );
              })}
            </select>
            {isBlock && (
              <>
                <button
                  type="button"
                  className={BAR_BUTTON}
                  disabled={atMax}
                  title={
                    atMax
                      ? `This block allows at most ${node.max_count} elements`
                      : "Add a new element"
                  }
                  onClick={() => void add()}
                >
                  add
                </button>
                <button
                  type="button"
                  className={BAR_BUTTON}
                  disabled={atMax}
                  title="Insert a new element before the selected one"
                  onClick={() => void insert()}
                >
                  ins
                </button>
                <button
                  type="button"
                  className={BAR_BUTTON}
                  disabled={!current || atMax}
                  title="Duplicate the selected element"
                  onClick={() => void duplicate()}
                >
                  dup
                </button>
                <button
                  type="button"
                  className={BAR_BUTTON}
                  disabled={!current}
                  title="Delete the selected element"
                  onClick={() => void editElements(path, "remove", index)}
                >
                  del
                </button>
                <button
                  type="button"
                  className={BAR_BUTTON}
                  disabled={!current}
                  title="Copy the selected element, to paste into a block of the same kind — here or in another tag"
                  onClick={() => void copyElement(path, index)}
                >
                  copy
                </button>
                <button
                  type="button"
                  className={BAR_BUTTON}
                  disabled={!canPaste || atMax}
                  title={pasteTitle}
                  onClick={() => void paste()}
                >
                  paste
                </button>
                {hasOps && (
                  <button
                    type="button"
                    className="shrink-0 font-mono text-[10px] text-text-dim hover:text-text-primary"
                    title="Revert this section's element changes, and every edit inside its elements"
                    onClick={() => void revertField(path)}
                  >
                    undo
                  </button>
                )}
              </>
            )}
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
              path={fieldPath(innerBase, child.name, child.kind)}
              scopes={innerScopes}
            />
          ))}
        </div>
      )}
      {open && inner.length === 0 && !isStruct && (
        <div className="ml-2.5 border-l border-border-subtle py-1.5 pl-4 text-xs text-text-dim">
          {total === 0 ? "no elements" : current ? "no fields" : `reading element ${index}…`}
        </div>
      )}
    </div>
  );
}

function FNode({
  node,
  path,
  depth,
  scopes,
}: {
  node: NodeView;
  path: string;
  depth: number;
  scopes: Scopes;
}) {
  if (node.kind === "field") return <FField node={node} path={path} scopes={scopes} />;
  return <FSection node={node} path={path} depth={depth} scopes={scopes} />;
}

/** The Guerilla-format inspector: section bars and typed controls. */
export function FormInspector() {
  const { tag, tagLoading, selectedTag } = useEditor();
  const ui = useTabUi();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const restored = useRef(false);

  // The container exists only once the tag has loaded, so restoration waits
  // for its first appearance rather than for mount; by then the sections have
  // initialised from the same remembered state, so heights are final.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!restored.current && el && ui) {
      restored.current = true;
      el.scrollTop = ui.scroll.form ?? 0;
    }
  });

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
    <div
      ref={scrollRef}
      className="min-h-0 flex-1 overflow-y-auto"
      onScroll={(e) => {
        if (ui) {
          ui.scroll.form = e.currentTarget.scrollTop;
          scheduleSaveSession();
        }
      }}
    >
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
            <FNode
              key={`${node.name}-${i}`}
              node={node}
              depth={0}
              path={fieldPath("", node.name)}
              scopes={[tag.fields]}
            />
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
