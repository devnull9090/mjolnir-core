// Generates src/generated/docs.json and public/docs-search.json from the
// repository docs/ directory.
//
// The hub renders docs that are authored as Markdown outside the Next project.
// Reading them from the app would make Turbopack trace the whole repository
// into the server bundle, so the content is snapshotted here instead and
// imported as plain JSON. Run automatically by `pnpm dev` and `pnpm build`.
//
// What is published, and in which section, is docs/site.json. A Markdown file
// that is in no section and not under `repoOnly` stops the sync: for months the
// site published a third of docs/ because a new doc went unlisted quietly.

import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import GithubSlugger from "github-slugger";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const hubDir = path.resolve(scriptDir, "..");
const docsDir = path.resolve(hubDir, "..", "docs");
const imagesDir = path.join(docsDir, "images");
const outFile = path.join(hubDir, "src", "generated", "docs.json");
const searchFile = path.join(hubDir, "public", "docs-search.json");
const publicImagesDir = path.join(hubDir, "public", "docs-images");

const GITHUB_BLOB = "https://github.com/devnull9090/mjolnir-core/blob/main/docs";

/**
 * The most text one search chunk holds. A chunk is what a search result points
 * at and what the semantic index embeds, so it is kept near a screenful: a long
 * section is split at paragraph breaks, and every part keeps the section's
 * anchor.
 */
const MAX_CHUNK_CHARS = 1400;

/** The longest a header value may grow by taking in wrapped lines. */
const MAX_META_CHARS = 260;

function slugify(fileName) {
  return fileName.replace(/\.md$/i, "").replace(/_/g, "-").toLowerCase();
}

/**
 * Markdown emphasis, code ticks and links down to plain text, on one line.
 * Underscores inside a word stay (inlineText): `mjolnir_sounds` is a name.
 */
function toPlainText(value) {
  return inlineText(value).replace(/\*\*/g, "").replace(/\s+/g, " ").trim();
}

/**
 * Reads the `**Label:** value` block that every research note opens with.
 * Returns the parsed pairs and the index of the first line after the block.
 *
 * A label ends in a colon. A paragraph that merely opens in bold is prose,
 * and ends the block.
 *
 * A value wrapped over a few lines is one value: the lines after a label, up
 * to the next label or blank line, belong to it while it stays short. Read as
 * the end of the block, a wrapped line became the page's summary. A long one
 * is a paragraph and is left to the body.
 */
function parseMetaBlock(lines, start) {
  const meta = [];
  let index = start;
  let wrapped = false;
  /** The value has reached its length: the rest of its paragraph is passed over. */
  let full = false;
  for (; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (!line) {
      wrapped = false;
      continue;
    }
    const match = line.match(/^\*\*([^*]+?)(?::\*\*|\*\*\s*:)\s*(.+)$/);
    if (match) {
      meta.push({ label: match[1].replace(/:$/, "").trim(), value: toPlainText(match[2]) });
      wrapped = true;
      full = false;
    } else if (wrapped && !/^(#|>|---|```|[-*+] |\d+[.)] |\|)/.test(line)) {
      // Still the label's paragraph, so still not the page's summary.
      const last = meta[meta.length - 1];
      const joined = `${last.value} ${toPlainText(line)}`;
      if (!full && joined.length <= MAX_META_CHARS) {
        last.value = joined;
      } else if (!full) {
        full = true;
        last.value = `${last.value} …`;
      }
    } else {
      break;
    }
  }
  return { meta, next: index };
}

/** The first paragraph from `start` on, as one line of plain text. */
function firstParagraph(lines, start) {
  let text = "";
  let out = [];
  for (let i = start; i <= lines.length && !text; i += 1) {
    const line = (lines[i] ?? "").trim();
    // Headings, rules, quotes, tables and fences are not prose; each also ends a paragraph.
    const prose = line && !/^(#|---|```|>|\|)/.test(line);
    if (prose) {
      out.push(line.replace(/^(?:[-*+]|\d+[.)])\s+/, ""));
      continue;
    }
    // A paragraph that is only an image has no words: keep looking.
    text = toPlainText(out.join(" "));
    out = [];
  }
  if (text.length <= 280) return text;
  const cut = text.slice(0, 280);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(" "), 200))}…`;
}

function parseNote(fileName, raw, section) {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");

  let cursor = 0;
  let title = fileName;
  while (cursor < lines.length && !lines[cursor].trim()) cursor += 1;
  if (lines[cursor]?.startsWith("# ")) {
    title = lines[cursor].slice(2).trim();
    cursor += 1;
  }

  const { meta, next } = parseMetaBlock(lines, cursor);

  const summary = firstParagraph(lines, next);

  return {
    slug: slugify(fileName),
    title,
    summary,
    section,
    // The page renders its own H1, so the body starts after it.
    body: rewriteImages(lines.slice(cursor).join("\n").trim()),
    meta,
    sourcePath: `${GITHUB_BLOB}/${fileName}`,
  };
}

/**
 * Point image references at the copies served from `public/`.
 *
 * The Markdown is authored to render on GitHub too, where `images/x.jpg` is
 * relative to the file. The hub serves the same files from a fixed route, so
 * the prefix is swapped here rather than making the source worse for one of
 * the two readers.
 */
function rewriteImages(body) {
  return body.replace(/(!\[[^\]]*\]\()images\//g, "$1/docs-images/");
}

// ── Search chunks ────────────────────────────────────────────────────────

/**
 * Raw HTML tags out of a run of text, repeated until there is nothing left to
 * take: one pass over `<scr<b>ipt>` joins what is on either side of the tag it
 * removes into a new one. What comes out is only ever shown as text (a search
 * snippet, a summary) or made into a heading's anchor, never written into a
 * page as HTML, but a string that is said to have no tags should have none.
 */
function stripTags(text) {
  let before;
  let after = text;
  do {
    before = after;
    after = before.replace(/<\/?[a-zA-Z][^>]*>/g, "");
  } while (after !== before);
  return after;
}

/**
 * Inline Markdown down to the text a reader sees. Unlike toPlainText this
 * keeps underscores inside words: `mjolnir_auto` and `cheat_all_weapons` are
 * what people search for.
 */
function inlineText(value) {
  // A code span is literal: `_P` is not emphasis and `TArray<FName>` is not a tag.
  return value
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\[[^\]]*\]/g, "$1")
    .split(/(`+[^`]*`+)/)
    .map((piece, index) =>
      index % 2 === 1
        ? piece.replace(/^`+|`+$/g, "")
        : stripTags(piece.replace(/<(https?:[^>]+)>/g, "$1"))
            .replace(/\*\*([^*]+)\*\*/g, "$1")
            .replace(/(^|[^\w*])\*([^*\s][^*]*)\*(?!\w)/g, "$1$2")
            .replace(/(^|[^\w])_([^_\s][^_]*)_(?!\w)/g, "$1$2")
            .replace(/\\([\\`*_{}[\]()#+\-.!|<>~])/g, "$1"),
    )
    .join("");
}

/** A block of Markdown lines as one line of searchable text. */
function blockText(lines) {
  const out = [];
  for (const raw of lines) {
    let line = raw;
    // A table's rule row carries nothing; its cells read fine as a sentence.
    if (/^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(line)) continue;
    line = line
      .replace(/^\s{0,3}>+\s?/, "")
      .replace(/^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?/, "")
      .replace(/\|/g, " ");
    out.push(line);
  }
  // Joined before the inline pass: emphasis often runs over a line break.
  return inlineText(out.join(" ")).replace(/\*\*/g, "").replace(/\s+/g, " ").trim();
}

/** Splits text over the chunk size at a sentence or word end. */
function hardSplit(text) {
  const parts = [];
  let rest = text;
  while (rest.length > MAX_CHUNK_CHARS) {
    const window = rest.slice(0, MAX_CHUNK_CHARS);
    let cut = Math.max(window.lastIndexOf(". "), window.lastIndexOf("; "));
    if (cut < MAX_CHUNK_CHARS / 2) cut = window.lastIndexOf(" ");
    if (cut < MAX_CHUNK_CHARS / 2) cut = MAX_CHUNK_CHARS - 1;
    parts.push(rest.slice(0, cut + 1).trim());
    rest = rest.slice(cut + 1).trim();
  }
  if (rest) parts.push(rest);
  return parts;
}

/**
 * A doc's body as search chunks: one per heading's own text, split when long.
 *
 * `anchor` is the id rehype-slug gives the heading when the page renders
 * (Markdown.tsx), so a result opens at the section: same slugger, fed every
 * heading of the body in order, which is what makes a repeated heading's
 * `-1` suffix agree.
 */
function chunkBody(body) {
  const slugger = new GithubSlugger();
  /** Open headings, outermost first. */
  const trail = [];
  const chunks = [];
  let anchor = "";
  let paragraphs = [];
  let paragraph = [];
  let fence = null;

  const endParagraph = () => {
    if (paragraph.length === 0) return;
    const text = blockText(paragraph);
    if (text) paragraphs.push(text);
    paragraph = [];
  };
  const endSection = () => {
    endParagraph();
    const heading = trail.map((entry) => entry.text).join(" › ");
    let text = "";
    const emit = () => {
      if (text) chunks.push({ anchor, heading, text });
      text = "";
    };
    for (const piece of paragraphs.flatMap(hardSplit)) {
      if (text && text.length + 1 + piece.length > MAX_CHUNK_CHARS) emit();
      text = text ? `${text} ${piece}` : piece;
    }
    emit();
    paragraphs = [];
  };

  for (const line of body.split("\n")) {
    const fenced = line.match(/^\s{0,3}(`{3,}|~{3,})/);
    if (fenced) {
      if (!fence) {
        endParagraph();
        fence = fenced[1][0];
      } else if (fenced[1][0] === fence) {
        endParagraph();
        fence = null;
      }
      continue;
    }
    if (fence) {
      paragraph.push(line);
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/);
    if (heading) {
      endSection();
      const level = heading[1].length;
      const text = inlineText(heading[2]).trim();
      anchor = slugger.slug(text);
      while (trail.length > 0 && trail[trail.length - 1].level >= level) trail.pop();
      trail.push({ level, text });
      continue;
    }
    if (!line.trim()) {
      endParagraph();
      continue;
    }
    paragraph.push(line);
  }
  endSection();
  return chunks;
}

// ── Manifest ─────────────────────────────────────────────────────────────

const site = JSON.parse(await readFile(path.join(docsDir, "site.json"), "utf8"));
const present = new Set(
  (await readdir(docsDir)).filter((name) => name.toLowerCase().endsWith(".md")),
);

const problems = [];
const placed = new Map();
for (const section of site.sections) {
  for (const name of section.docs) {
    if (placed.has(name)) problems.push(`${name} is in both "${placed.get(name)}" and "${section.id}"`);
    placed.set(name, section.id);
    if (!present.has(name)) problems.push(`${name} (section "${section.id}") is not in docs/`);
  }
}
for (const name of Object.keys(site.repoOnly)) {
  if (placed.has(name)) problems.push(`${name} is in section "${placed.get(name)}" and under repoOnly`);
  if (!present.has(name)) problems.push(`${name} (repoOnly) is not in docs/`);
}
for (const name of [...present].sort()) {
  if (!placed.has(name) && !(name in site.repoOnly)) {
    problems.push(
      `${name} is in no section of docs/site.json: add it to one to publish it, or to repoOnly to keep it off the site`,
    );
  }
}
if (problems.length > 0) {
  console.error(`sync-docs: docs/site.json does not match docs/:\n  ${problems.join("\n  ")}`);
  process.exit(1);
}

// ── Docs ─────────────────────────────────────────────────────────────────

const notes = [];
const guides = [];
const sections = [];
/** Search index rows: [slug, "g" | "n", title, section title]. */
const searchDocs = [];
/** Search index rows: [doc index, heading anchor, heading trail, text]. */
const searchChunks = [];

for (const section of site.sections) {
  const kind = section.kind === "guide" ? "guide" : "note";
  const slugs = [];
  for (const name of section.docs) {
    const note = parseNote(name, await readFile(path.join(docsDir, name), "utf8"), section.id);
    (kind === "guide" ? guides : notes).push(note);
    slugs.push(note.slug);

    const docIndex = searchDocs.length;
    searchDocs.push([note.slug, kind === "guide" ? "g" : "n", note.title, section.title]);
    for (const chunk of chunkBody(note.body)) {
      searchChunks.push([docIndex, chunk.anchor, chunk.heading, chunk.text]);
    }
  }
  sections.push({ id: section.id, kind, title: section.title, blurb: section.blurb, slugs });
}

// Preserve nested paths: images/forge/example.png is served at
// /docs-images/forge/example.png. Sort each directory for reproducible traversal,
// and ignore symlinks so only files inside the source image tree are copied.
async function collectImages(relativeDir = "") {
  let entries;
  try {
    entries = await readdir(path.join(imagesDir, relativeDir), { withFileTypes: true });
  } catch (error) {
    if (relativeDir === "" && error.code === "ENOENT") {
      console.warn("sync-docs: no docs/images directory");
      return [];
    }
    throw error;
  }
  entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  const images = [];
  for (const entry of entries) {
    const relativePath = path.join(relativeDir, entry.name);
    if (entry.isDirectory()) {
      images.push(...await collectImages(relativePath));
    } else if (entry.isFile() && /\.(png|jpe?g|gif|webp|svg)$/i.test(entry.name)) {
      images.push(relativePath);
    }
  }
  return images;
}

// Screenshots live beside the Markdown so the files render on GitHub; the hub
// needs them under public/ to serve them.
const images = await collectImages();
for (const name of images) {
  const destination = path.join(publicImagesDir, name);
  await mkdir(path.dirname(destination), { recursive: true });
  await copyFile(path.join(imagesDir, name), destination);
}

await mkdir(path.dirname(outFile), { recursive: true });
await writeFile(
  outFile,
  `${JSON.stringify({ generator: "scripts/sync-docs.mjs", sections, notes, guides }, null, 2)}\n`,
  "utf8",
);

// The search index is fetched by the browser on first search and read by the
// Worker when it fills the semantic index, so it is one compact line. `build`
// names this exact content: the semantic index records the build it holds.
const content = JSON.stringify({ docs: searchDocs, chunks: searchChunks });
const build = createHash("sha256").update(content).digest("hex").slice(0, 16);
await writeFile(
  searchFile,
  `${JSON.stringify({ build, docs: searchDocs, chunks: searchChunks })}\n`,
  "utf8",
);

console.log(
  `sync-docs: wrote ${notes.length} note(s), ${guides.length} guide(s), ` +
    `${searchChunks.length} search chunk(s) and copied ${images.length} image(s)`,
);
