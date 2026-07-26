import generated from "@/generated/docs.json";

/**
 * Research notes are authored as Markdown in the repository `docs/` directory.
 * `scripts/sync-docs.mjs` snapshots them into `src/generated/docs.json` before
 * every build, so nothing here touches the filesystem. Reading the Markdown
 * directly from the app would make Turbopack trace the whole repository into
 * the server bundle.
 */

export type DocNote = {
  slug: string;
  title: string;
  summary: string;
  /** Body with the leading H1 removed, since the page renders its own header. */
  body: string;
  meta: Array<{ label: string; value: string }>;
  sourcePath: string;
};

export function slugify(fileName: string): string {
  return fileName.replace(/\.md$/i, "").replace(/_/g, "-").toLowerCase();
}

export function getDocNotes(): DocNote[] {
  return generated.notes;
}

export function getDocNote(slug: string): DocNote | null {
  return generated.notes.find((note) => note.slug === slug) ?? null;
}
