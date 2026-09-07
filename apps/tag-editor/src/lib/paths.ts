/**
 * Field paths as the backend reads them: segments joined with `.`, elements as
 * `[i]`, and a backslash escaping a dot or bracket that is part of a field's
 * own name (`v\\.i`, `message anchor v\\[0,1\\]`). Every path the UI sends
 * is built here, so a name that happens to contain a separator still resolves.
 */
export function escapeSegment(name: string): string {
  return name.replace(/[.[\]\\]/g, (c) => `\\${c}`);
}

/** `base.name`, or just the name at the root. Element names (`[3]`) attach
 *  directly to their block. */
export function fieldPath(base: string, name: string, kind?: string): string {
  if (kind === "element") return `${base}${name}`;
  const segment = escapeSegment(name);
  return base ? `${base}.${segment}` : segment;
}
