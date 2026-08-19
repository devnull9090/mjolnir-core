// Generates src/generated/blog.json from the repository blog/ directory.
//
// Same shape and same reasoning as sync-changelog.mjs: posts are authored as
// Markdown outside the Next project, and reading them from the app would make
// Turbopack trace the whole repository into the server bundle. They are
// snapshotted here and imported as plain JSON. Run automatically by `pnpm dev`
// and `pnpm build`.
//
// A malformed post fails the build rather than warning, for the changelog's
// reason: a post is public writing, and half of one is worse than a loud
// failure at the point someone can still fix it.

import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const hubDir = path.resolve(scriptDir, "..");
const blogDir = path.resolve(hubDir, "..", "blog");
const outFile = path.join(hubDir, "src", "generated", "blog.json");

const GITHUB_BLOB = "https://github.com/devnull9090/mjolnir-core/blob/main/blog";

/** Hard ceiling on `**Summary:**` — it is a meta description and an RSS body. */
const SUMMARY_MAX = 300;

function fail(message) {
  console.error(`sync-blog: ${message}`);
  process.exit(1);
}

/** Strips Markdown emphasis, code ticks and links down to plain text. */
function toPlainText(value) {
  return value
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[*_`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * One post: `YYYY-MM-DD-slug.md`, an `# Title`, then a `**Label:** value` meta
 * block in the research-note style. The date lives in the filename so a
 * directory listing reads as a timeline, and in no second place that could
 * disagree with it.
 */
async function parsePost(fileName) {
  const match = fileName.match(/^(\d{4}-\d{2}-\d{2})-([a-z0-9-]+)\.md$/);
  if (!match) {
    fail(`${fileName}: file name must be YYYY-MM-DD-slug.md (lowercase, hyphens)`);
  }
  const [, date, slug] = match;

  const raw = await readFile(path.join(blogDir, fileName), "utf8");
  const lines = raw.split(/\r?\n/);

  let index = 0;
  while (index < lines.length && lines[index].trim() === "") index += 1;
  const title = lines[index]?.match(/^#\s+(.+?)\s*$/);
  if (!title) fail(`${fileName}: must open with an # Title heading`);
  index += 1;

  const meta = {};
  for (; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (line === "") {
      if (Object.keys(meta).length > 0) break;
      continue;
    }
    const pair = line.match(/^\*\*([^:*]+):\*\*\s*(.+)$/);
    if (!pair) break;
    meta[pair[1].trim().toLowerCase()] = pair[2].trim();
  }

  if (!meta.summary) fail(`${fileName}: missing **Summary:** line`);
  const summary = toPlainText(meta.summary);
  if (summary.length > SUMMARY_MAX) {
    fail(`${fileName}: summary is ${summary.length} chars; keep it under ${SUMMARY_MAX}`);
  }

  const body = lines.slice(index).join("\n").trim();
  if (!body) fail(`${fileName}: post has no body`);

  return {
    slug,
    date,
    title: toPlainText(title[1]),
    author: meta.author ? toPlainText(meta.author) : "MJOLNIR Core",
    summary,
    tags: meta.tags
      ? meta.tags.split(",").map((t) => t.trim()).filter(Boolean)
      : [],
    body,
    sourceUrl: `${GITHUB_BLOB}/${fileName}`,
  };
}

async function main() {
  let fileNames;
  try {
    fileNames = (await readdir(blogDir)).filter(
      (f) => f.endsWith(".md") && f.toLowerCase() !== "readme.md",
    );
  } catch {
    fail(`cannot read ${blogDir}`);
  }

  const posts = await Promise.all(fileNames.map(parsePost));
  // Newest first; same-day posts tie-break by slug so the order is stable.
  posts.sort((a, b) => b.date.localeCompare(a.date) || a.slug.localeCompare(b.slug));

  const seen = new Set();
  for (const post of posts) {
    if (seen.has(post.slug)) fail(`duplicate slug "${post.slug}"`);
    seen.add(post.slug);
  }

  await mkdir(path.dirname(outFile), { recursive: true });
  await writeFile(outFile, `${JSON.stringify({ posts }, null, 2)}\n`);
  console.log(`sync-blog: wrote ${posts.length} post(s) to ${path.relative(hubDir, outFile)}`);
}

await main();
