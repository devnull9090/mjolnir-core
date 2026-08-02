/** Small formatting helpers shared by every hub surface. */

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MiB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KiB`;
  return `${n} B`;
}

export function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** ISO timestamp → "3 days ago", falling back to the date for old ones. */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const then = Date.parse(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
  if (Number.isNaN(then)) return iso.slice(0, 10);
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  return iso.slice(0, 10);
}

/** Truncated hash for display, with the full value meant for a title attr. */
export function shortHash(hash: string | null | undefined, chars = 16): string {
  if (!hash) return "";
  return hash.length <= chars ? hash : `${hash.slice(0, chars)}…`;
}

/**
 * Compare two dotted versions numerically, falling back to string order for
 * non-numeric parts. Enough for the semver the hub accepts (`x.y.z[-tag]`);
 * a released version sorts above the same version with a pre-release tag.
 */
export function compareVersions(a: string, b: string): number {
  const split = (v: string) => {
    const [core, tag] = v.split("-", 2);
    return { parts: core.split(".").map((p) => parseInt(p, 10) || 0), tag: tag ?? "" };
  };
  const va = split(a);
  const vb = split(b);
  const len = Math.max(va.parts.length, vb.parts.length);
  for (let i = 0; i < len; i++) {
    const d = (va.parts[i] ?? 0) - (vb.parts[i] ?? 0);
    if (d !== 0) return d < 0 ? -1 : 1;
  }
  if (va.tag === vb.tag) return 0;
  if (va.tag === "") return 1; // 1.0.0 > 1.0.0-beta.1
  if (vb.tag === "") return -1;
  return va.tag < vb.tag ? -1 : 1;
}

/** True when `candidate` is strictly newer than `installed`. */
export function isNewer(candidate: string, installed: string): boolean {
  return compareVersions(candidate, installed) > 0;
}
