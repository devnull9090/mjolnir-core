import generated from "@/generated/docs.json";

/**
 * The docs are authored as Markdown in the repository `docs/` directory.
 * `scripts/sync-docs.mjs` snapshots them into `src/generated/docs.json` before
 * every build, so nothing here touches the filesystem. Reading the Markdown
 * directly from the app would make Turbopack trace the whole repository into
 * the server bundle.
 */

export type DocNote = {
  slug: string;
  title: string;
  summary: string;
  /** The id of the section of docs/site.json this doc is published under. */
  section: string;
  /** Body with the leading H1 removed, since the page renders its own header. */
  body: string;
  meta: Array<{ label: string; value: string }>;
  sourcePath: string;
};

/**
 * A group of docs on one subject, in reading order. Sections and what is in
 * them are docs/site.json; a guide section is served under /docs/guides and
 * every other under /docs/notes.
 */
export type DocSection = {
  id: string;
  kind: "guide" | "note";
  title: string;
  blurb: string;
  docs: DocNote[];
};

const bySlug = new Map<string, DocNote>(
  [...generated.guides, ...generated.notes].map((doc) => [doc.slug, doc]),
);

export function getDocSections(): DocSection[] {
  return generated.sections.map((section) => ({
    id: section.id,
    kind: section.kind === "guide" ? "guide" : "note",
    title: section.title,
    blurb: section.blurb,
    docs: section.slugs.map((slug) => bySlug.get(slug)).filter((doc) => doc !== undefined),
  }));
}

export function getDocSection(id: string): DocSection | null {
  return getDocSections().find((section) => section.id === id) ?? null;
}

/** Where a doc is served. */
export function docHref(section: Pick<DocSection, "kind">, doc: Pick<DocNote, "slug">): string {
  return `/docs/${section.kind === "guide" ? "guides" : "notes"}/${doc.slug}`;
}

export function slugify(fileName: string): string {
  return fileName.replace(/\.md$/i, "").replace(/_/g, "-").toLowerCase();
}

export function getDocNotes(): DocNote[] {
  return generated.notes;
}

export function getDocNote(slug: string): DocNote | null {
  return generated.notes.find((note) => note.slug === slug) ?? null;
}

/**
 * Guides are task-shaped: follow one start to finish and you have done the
 * thing. Notes are the working history behind them. Same Markdown pipeline,
 * different promise to the reader.
 */
export function getGuides(): DocNote[] {
  return generated.guides;
}

export function getGuide(slug: string): DocNote | null {
  return generated.guides.find((guide) => guide.slug === slug) ?? null;
}
