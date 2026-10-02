import type { NodeView } from "./api";
import { fieldPath } from "./paths";

/** Types with no editable value of their own. */
export const NOT_EDITABLE = new Set([
  "data",
  "block",
  "struct",
  "array",
  "pageable resource",
  "api interop",
  // Structural fields the expert view shows: bytes, not values.
  "pad",
  "custom",
  "terminator X",
]);

/** Why a `runtime …` field is read-only. */
export const RUNTIME_NOTE = "Recomputed by the game when the tag loads";

/** Whether the inspector lets this field be edited. */
export function isEditable(node: NodeView): boolean {
  return !NOT_EDITABLE.has(node.type) && node.size > 0 && !node.runtime;
}

/**
 * The warning for a live change to a field the running game does not read:
 * it reads the runtime copies computed from it when the tag loaded. `null`
 * when the field feeds nothing.
 */
export function staleLiveNote(node: NodeView | null): string | null {
  if (!node || node.feeds.length === 0) return null;
  return (
    `the running game reads ${node.feeds.join(", ")}, computed from this ` +
    "when the tag loaded, so it will not change until the tag reloads " +
    "(restart the mission). The edit itself is recorded, and a rebuild or " +
    "test install carries it."
  );
}

/** The node a field path names, walking the tree the way paths are built. */
export function nodeAtPath(nodes: NodeView[], path: string, base = ""): NodeView | null {
  for (const n of nodes) {
    const here = fieldPath(base, n.name, n.kind);
    if (here === path) return n;
    if (path.startsWith(here) && (path[here.length] === "." || path[here.length] === "[")) {
      const found = nodeAtPath(n.children, path, here);
      if (found) return found;
    }
  }
  return null;
}

/** Types whose value lives in a trailing section, so changing one resizes the
 *  tag rather than overwriting bytes. Editable, but worth flagging. */
export const RESIZES = new Set(["string id", "tag reference"]);

/**
 * Keep the end of a long path rather than the start. A tag path's distinctive
 * part is its tail, so the usual trailing ellipsis hides exactly what you need.
 */
export function keepTail(text: string, max: number): string {
  return text.length <= max ? text : `…${text.slice(text.length - max)}`;
}

/**
 * The value as it should appear in an edit box: what the parser accepts, which
 * is not always what the display shows. An enum reads `large (3)` but is set by
 * name, and flags read `a | b (0x5)` but are set as `a | b`.
 */
export function editableText(node: NodeView): string {
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

/** Per-component labels Guerilla shows for multi-value fields. */
export const COMPONENT_LABELS: Record<string, string[]> = {
  "real point 2d": ["x", "y"],
  "real point 3d": ["x", "y", "z"],
  "point 2d": ["x", "y"],
  "real vector 2d": ["i", "j"],
  "real vector 3d": ["i", "j", "k"],
  "real euler angles 2d": ["y", "p"],
  "real euler angles 3d": ["y", "p", "r"],
  "real quaternion": ["i", "j", "k", "w"],
  "real plane 2d": ["i", "j", "d"],
  "real plane 3d": ["i", "j", "k", "d"],
  "real bounds": ["min", "max"],
  "real fraction bounds": ["min", "max"],
  "angle bounds": ["min", "max"],
  "short integer bounds": ["min", "max"],
  "rectangle 2d": ["t", "l", "b", "r"],
};

/** Split a `(a, b, c)` display value into its components. */
export function splitComponents(value: string): string[] {
  return value
    .replace(/^\(|\)$/g, "")
    .split(",")
    .map((s) => s.trim());
}

/**
 * A human name for one block element, the way Guerilla labels its element
 * dropdown: the element's own `name` field if the definition has one,
 * otherwise the tail of its first tag reference, otherwise its index.
 */
export function elementLabel(element: NodeView): string | null {
  const fields = element.children.filter((c) => c.kind === "field");
  const named = fields.find(
    (c) =>
      c.name === "name" &&
      (c.type === "string" || c.type === "long string" || c.type === "string id") &&
      c.value.replace(/^"|"$/g, "") !== "",
  );
  if (named) return named.value.replace(/^"|"$/g, "");

  const ref = fields.find((c) => c.reference && c.reference.path);
  if (ref?.reference) {
    const tail = ref.reference.path.split(/[\\/]/).pop();
    if (tail) return tail;
  }
  return null;
}
