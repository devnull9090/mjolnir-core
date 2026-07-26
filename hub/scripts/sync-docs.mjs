// Generates src/generated/docs.json from the repository docs/ directory.
//
// The hub renders research notes that are authored as Markdown outside the Next
// project. Reading them from the app would make Turbopack trace the whole
// repository into the server bundle, so the content is snapshotted here instead
// and imported as plain JSON. Run automatically by `pnpm dev` and `pnpm build`.

import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const hubDir = path.resolve(scriptDir, "..");
const docsDir = path.resolve(hubDir, "..", "docs");
const outFile = path.join(hubDir, "src", "generated", "docs.json");

const GITHUB_BLOB = "https://github.com/devnull9090/mjolnir-core/blob/main/docs";

/** Notes are rendered in this order. Anything else in docs/ is ignored. */
const ORDER = [
  "tag_data_pipeline.md",
  "tag_body_format.md",
  "halosimulation_tag_release.md",
  "multiplayer_investigation_notes.md",
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
    body: lines.slice(cursor).join("\n").trim(),
    meta,
    sourcePath: `${GITHUB_BLOB}/${fileName}`,
  };
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

await mkdir(path.dirname(outFile), { recursive: true });
await writeFile(
  outFile,
  `${JSON.stringify({ generator: "scripts/sync-docs.mjs", notes }, null, 2)}\n`,
  "utf8",
);

console.log(`sync-docs: wrote ${notes.length} note(s) to src/generated/docs.json`);
