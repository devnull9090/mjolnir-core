/**
 * Who is asking, as far as a release's launcher requirements go.
 *
 * A release can need something of the launcher that installs it (its
 * `requires`, measured at scan and publish). Launchers after 0.23 say what
 * they support in two headers; launchers up to 0.23 send no User-Agent and no
 * headers of their own at all, which is what identifies them. Everyone else
 * (browsers, the website, tools) sees every release as it is.
 */

/** Sent by every current launcher, with its version as the value. */
export const LAUNCHER_HEADER = "X-MJOLNIR-Launcher";
/** The launcher's features, comma-separated. */
export const FEATURES_HEADER = "X-MJOLNIR-Features";

/** The launcher renames each container's shader library to a chunk number of
 *  its own (launcher PR #386), so content cooked under any number loads, and
 *  two mods cooked under one number both draw. */
export const LOCAL_CHUNK_NUMBERS = "local-chunk-numbers";

/** Responses that differ by client say so, so no cache hands one client's
 *  answer to another. */
export const CLIENT_VARY = `User-Agent, ${LAUNCHER_HEADER}, ${FEATURES_HEADER}`;

/** What a launcher too old for a release is told, as the release's status
 *  (it prints "Release is <status>, not published") and as the download's error. */
export const UPDATE_LAUNCHER =
  "for a newer MJOLNIR launcher: update the launcher from mjolnircore.com/download";

export interface Client {
  kind: "launcher" | "legacy" | "other";
  features: ReadonlySet<string>;
}

/** Anyone not a launcher: sees everything. The default for server-side callers. */
export const OTHER_CLIENT: Client = { kind: "other", features: new Set() };

export function clientOf(headers: { get(name: string): string | null }): Client {
  if (headers.get(LAUNCHER_HEADER) !== null) {
    const features = (headers.get(FEATURES_HEADER) ?? "")
      .split(",")
      .map((f) => f.trim())
      .filter(Boolean);
    return { kind: "launcher", features: new Set(features) };
  }
  if (!headers.get("user-agent")?.trim()) return { kind: "legacy", features: new Set() };
  return OTHER_CLIENT;
}

/** Whether the client can install a release that requires these features. */
export function compatible(client: Client, requires: readonly string[]): boolean {
  return client.kind === "other" || requires.every((f) => client.features.has(f));
}

/** The client's features as one JSON array for SQL's json_each, or null when
 *  every release suits it. */
export function featuresJson(client: Client): string | null {
  return client.kind === "other" ? null : JSON.stringify([...client.features]);
}

/** A `mod_releases.requires` value: a JSON array, NULL for none. */
export function parseRequires(raw: unknown): string[] {
  if (typeof raw !== "string" || !raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((f): f is string => typeof f === "string") : [];
  } catch {
    return [];
  }
}

/** SQL true when release `alias` needs nothing beyond the features bound at
 *  `param` (a featuresJson value; NULL suits every release). */
export function compatibleSql(alias: string, param: string): string {
  return `(${param} IS NULL OR NOT EXISTS (
    SELECT 1 FROM json_each(COALESCE(${alias}.requires, '[]')) req
    WHERE req.value NOT IN (SELECT value FROM json_each(${param}))))`;
}
