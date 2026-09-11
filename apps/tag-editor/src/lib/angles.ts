/**
 * Angles as the user prefers them. The tag stores radians and every path into
 * the backend — edits, recipes, TSV — speaks radians; only what the inspector
 * shows and what the user types is converted, here, at the edge.
 */
export const ANGLE_TYPES: ReadonlySet<string> = new Set([
  "angle",
  "angle bounds",
  "real euler angles 2d",
  "real euler angles 3d",
]);

export function isAngleType(type: string): boolean {
  return ANGLE_TYPES.has(type);
}

const NUMBER = /-?\d+(?:\.\d+)?(?:e[-+]?\d+)?/gi;

/** Six decimals, trailing zeroes trimmed — the same shape the backend prints. */
function fmt(n: number): string {
  if (n === 0) return "0";
  const s = n.toFixed(6);
  return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
}

function mapNumbers(text: string, f: (n: number) => number): string {
  return text.replace(NUMBER, (m) => {
    const n = Number(m);
    return Number.isFinite(n) ? fmt(f(n)) : m;
  });
}

/** `(0.5236, 1.0472)` in radians → the same text in degrees. */
export function radiansToDegreesText(text: string): string {
  return mapNumbers(text, (n) => (n * 180) / Math.PI);
}

/** What the user typed in degrees → the radians the tag stores. */
export function degreesToRadiansText(text: string): string {
  return mapNumbers(text, (n) => (n * Math.PI) / 180);
}
