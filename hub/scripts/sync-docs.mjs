// Generates src/generated/docs.json from the repository docs/ directory.
//
// The hub renders research notes that are authored as Markdown outside the Next
// project. Reading them from the app would make Turbopack trace the whole
// repository into the server bundle, so the content is snapshotted here instead
// and imported as plain JSON. Run automatically by `pnpm dev` and `pnpm build`.

import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const hubDir = path.resolve(scriptDir, "..");
const docsDir = path.resolve(hubDir, "..", "docs");
const imagesDir = path.join(docsDir, "images");
const outFile = path.join(hubDir, "src", "generated", "docs.json");
const publicImagesDir = path.join(hubDir, "public", "docs-images");

const GITHUB_BLOB = "https://github.com/devnull9090/mjolnir-core/blob/main/docs";

/** Notes are rendered in this order. Anything else in docs/ is ignored. */
const ORDER = [
  "build_lock.md",
  "game_update_pipeline.md",
  "tag_data_pipeline.md",
  "tag_body_format.md",
  "iostore_packaging.md",
  "ue_texture_format.md",
  "wwise_audio_format.md",
  "halosimulation_tag_release.md",
  "multiplayer_investigation_notes.md",
  "coop_player_cap.md",
  "mjolnir_format.md",
  "hub_architecture.md",
  "mod_authoring_design.md",
  "mod_signing_design.md",
  "contributing_code_mods.md",
  "security_advisory_arrayref.md",
];

/**
 * Guides are task-shaped: follow them start to finish and you have done the
 * thing. Notes are the working history behind them, superseded turns included.
 */
const GUIDES = [
  "getting_started.md",
  "making_your_first_mod.md",
  "tag_editing_guide.md",
  "texture_swapping.md",
  "game_automation.md",
];

function slugify(fileName) {
  return fileName.replace(/\.md$/i, "").replace(/_/g, "-").toLowerCase();
}

/** Strips Markdown emphasis, code ticks, and links down to plain text. */
function toPlainText(value) {
  return value
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[*_`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Reads the `**Label:** value` block that every research note opens with.
 * Returns the parsed pairs and the index of the first line after the block.
 */
function parseMetaBlock(lines, start) {
  const meta = [];
  let index = start;
  for (; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (!line) continue;
    const match = line.match(/^\*\*([^*]+?)\*\*\s*:?\s*(.+)$/);
    if (!match) break;
    meta.push({ label: match[1].replace(/:$/, "").trim(), value: toPlainText(match[2]) });
  }
  return { meta, next: index };
}

function parseNote(fileName, raw) {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");

  let cursor = 0;
  let title = fileName;
  while (cursor < lines.length && !lines[cursor].trim()) cursor += 1;
  if (lines[cursor]?.startsWith("# ")) {
    title = lines[cursor].slice(2).trim();
    cursor += 1;
  }

  const { meta, next } = parseMetaBlock(lines, cursor);

  let summary = "";
  for (let i = next; i < lines.length; i += 1) {
    const line = lines[i].trim();
    if (!line || line.startsWith("#") || line.startsWith("---") || line.startsWith(">")) continue;
    summary = toPlainText(line);
    break;
  }

  return {
    slug: slugify(fileName),
    title,
    summary,
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

const present = new Set(
  (await readdir(docsDir)).filter((name) => name.toLowerCase().endsWith(".md")),
);
const missing = ORDER.filter((name) => !present.has(name));
if (missing.length > 0) {
  console.warn(`sync-docs: skipping missing note(s): ${missing.join(", ")}`);
}

const notes = [];
for (const name of ORDER.filter((name) => present.has(name))) {
  notes.push(parseNote(name, await readFile(path.join(docsDir, name), "utf8")));
}

const missingGuides = GUIDES.filter((name) => !present.has(name));
if (missingGuides.length > 0) {
  console.warn(`sync-docs: skipping missing guide(s): ${missingGuides.join(", ")}`);
}

// A doc in neither list is never published, and any `[…](that.md)` link from a
// doc that *is* published resolves to a 404. That is how three format notes went
// missing for months, so say so rather than ignoring it quietly.
const listed = new Set([...ORDER, ...GUIDES]);
const unlisted = [...present].filter((name) => !listed.has(name)).sort();
if (unlisted.length > 0) {
  console.warn(
    `sync-docs: ${unlisted.length} doc(s) in neither ORDER nor GUIDES, so not published: ` +
      `${unlisted.join(", ")}. Add them to a list, or accept that links to them 404.`,
  );
}
const guides = [];
for (const name of GUIDES.filter((name) => present.has(name))) {
  guides.push(parseNote(name, await readFile(path.join(docsDir, name), "utf8")));
}

// Screenshots live beside the Markdown so the files render on GitHub; the hub
// needs them under public/ to serve them.
let images = [];
try {
  images = (await readdir(imagesDir)).filter((name) => /\.(png|jpe?g|gif|webp|svg)$/i.test(name));
} catch {
  console.warn("sync-docs: no docs/images directory");
}
if (images.length > 0) {
  await mkdir(publicImagesDir, { recursive: true });
  for (const name of images) {
    await copyFile(path.join(imagesDir, name), path.join(publicImagesDir, name));
  }
}

await mkdir(path.dirname(outFile), { recursive: true });
await writeFile(
  outFile,
  `${JSON.stringify({ generator: "scripts/sync-docs.mjs", notes, guides }, null, 2)}\n`,
  "utf8",
);

console.log(
  `sync-docs: wrote ${notes.length} note(s), ${guides.length} guide(s) and copied ${images.length} image(s)`,
);
