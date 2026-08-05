// Generates src/generated/changelog.json from the repository changelog/ directory.
//
// Same shape and same reasoning as sync-docs.mjs: the entries are authored as
// Markdown outside the Next project, and reading them from the app would make
// Turbopack trace the whole repository into the server bundle. They are
// snapshotted here and imported as plain JSON. Run automatically by `pnpm dev`
// and `pnpm build`.
//
// Unlike sync-docs, a malformed entry fails the build rather than warning. A
// changelog entry is a release's public record and it is also what the launcher
// shows after an update; half of one is worse than a loud failure at the point
// someone can still fix it.

import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const hubDir = path.resolve(scriptDir, "..");
const changelogDir = path.resolve(hubDir, "..", "changelog");
const outFile = path.join(hubDir, "src", "generated", "changelog.json");

const GITHUB_BLOB = "https://github.com/devnull9090/mjolnir-core/blob/main/changelog";
const GITHUB_RELEASE = "https://github.com/devnull9090/mjolnir-core/releases/tag";

/** Hard ceiling on `**Summary:**`. See the check in parseEntry for why. */
const SUMMARY_MAX = 200;

/** `0.1.10` sorts above `0.1.9`, which a string comparison gets backwards. */
function compareVersions(a, b) {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function fail(message) {
  console.error(`sync-changelog: ${message}`);
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
 * Pulls the `### Heading` + bullet structure out of the body.
 *
 * The hub renders the Markdown itself, but the launcher's modal and the Discord
 * embed want the shape rather than the prose — "3 fixes, 1 security note" is a
 * different rendering job from a page. Parsing it once here keeps every consumer
 * off the Markdown.
 */
function parseSections(body) {
  const sections = [];
  let current = null;
  /** The bullet being accumulated, since entries wrap theirs across lines. */
  let pending = null;

  const flush = () => {
    if (pending !== null && current) current.items.push(toPlainText(pending));
    pending = null;
  };

  for (const line of body.split("\n")) {
    const heading = line.match(/^#{2,4}\s+(.+?)\s*$/);
    if (heading) {
      flush();
      current = { heading: toPlainText(heading[1]), items: [] };
      sections.push(current);
      continue;
    }

    // Top-level bullets only: a nested one is a detail of the line above it,
    // and lifting it out of that context makes it read as a separate change.
    const bullet = line.match(/^[-*]\s+(.+?)\s*$/);
    if (bullet) {
      flush();
      if (current) pending = bullet[1];
      continue;
    }

    // A wrapped bullet continues on an indented line. A blank line ends it:
    // what follows is a second paragraph, and these items are a summary.
    if (pending !== null) {
      if (/^\s+\S/.test(line) && !/^\s+[-*]\s/.test(line)) pending += ` ${line.trim()}`;
      else flush();
    }
  }

  flush();
  return sections.filter((s) => s.items.length > 0);
}

function parseEntry(product, version, fileName, raw) {
  const where = `changelog/${product.id}/${fileName}`;
  const lines = raw.replace(/\r\n/g, "\n").split("\n");

  let cursor = 0;
  while (cursor < lines.length && !lines[cursor].trim()) cursor += 1;
  if (!lines[cursor]?.startsWith("# ")) {
    fail(`${where} must open with a '# Title' line. See changelog/README.md.`);
  }
  const title = lines[cursor].slice(2).trim();
  cursor += 1;

  const meta = {};
  for (; cursor < lines.length; cursor += 1) {
    const line = lines[cursor].trim();
    if (!line) continue;
    const match = line.match(/^\*\*([^*]+?)\*\*\s*:?\s*(.+)$/);
    if (!match) break;
    meta[match[1].replace(/:$/, "").trim().toLowerCase()] = match[2].trim();
  }

  if (!meta.date) fail(`${where} has no '**Date:**' line.`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(meta.date)) {
    fail(`${where} has '**Date:** ${meta.date}', which is not YYYY-MM-DD.`);
  }
  if (!meta.summary) fail(`${where} has no '**Summary:**' line.`);
  // The summary is the page's meta description and the feed entry. Search
  // engines truncate somewhere around 160 characters, so aim below that; the
  // hard stop is here to catch a whole paragraph pasted into the field, which
  // would be truncated into nonsense everywhere it is shown.
  if (meta.summary.length > SUMMARY_MAX) {
    fail(
      `${where} has a ${meta.summary.length}-character '**Summary:**'; the limit is ${SUMMARY_MAX}. ` +
        `It is the meta description and the launcher's opening line — aim for one sentence under 160.`,
    );
  }

  const body = lines.slice(cursor).join("\n").trim();

  return {
    product: product.id,
    productName: product.name,
    version,
    tag: `${product.tagPrefix}${version}`,
    title,
    date: meta.date,
    summary: toPlainText(meta.summary),
    // The page renders its own H1 and its own date, so the body starts after
    // the meta block.
    body,
    sections: parseSections(body),
    path: `/changelog/${product.id}/${version}`,
    sourcePath: `${GITHUB_BLOB}/${product.id}/${fileName}`,
    releaseUrl: `${GITHUB_RELEASE}/${product.tagPrefix}${version}`,
  };
}

const registry = JSON.parse(await readFile(path.join(changelogDir, "products.json"), "utf8"));
const products = registry.products;

const releases = [];
for (const product of products) {
  const dir = path.join(changelogDir, product.id);
  let files;
  try {
    files = (await readdir(dir)).filter((name) => name.toLowerCase().endsWith(".md"));
  } catch {
    fail(`changelog/${product.id}/ does not exist, but products.json lists it.`);
  }

  for (const fileName of files) {
    const version = fileName.replace(/\.md$/i, "");
    if (!/^\d+\.\d+\.\d+$/.test(version)) {
      fail(
        `changelog/${product.id}/${fileName} is not named <major>.<minor>.<patch>.md. ` +
          `The version comes from the filename, so it cannot be spelled differently here ` +
          `than in the tag.`,
      );
    }
    releases.push(parseEntry(product, version, fileName, await readFile(path.join(dir, fileName), "utf8")));
  }
}

// Newest first. Same-day releases fall back to product then version so the
// order is stable across machines — the files carry a date, not a timestamp.
releases.sort(
  (a, b) =>
    b.date.localeCompare(a.date) ||
    a.product.localeCompare(b.product) ||
    compareVersions(b.version, a.version),
);

await mkdir(path.dirname(outFile), { recursive: true });
await writeFile(
  outFile,
  `${JSON.stringify(
    {
      generator: "scripts/sync-changelog.mjs",
      products: products.map(({ id, name, tagPrefix, blurb, docsUrl }) => ({
        id,
        name,
        tagPrefix,
        blurb,
        docsUrl,
      })),
      releases,
    },
    null,
    2,
  )}\n`,
  "utf8",
);

console.log(
  `sync-changelog: wrote ${releases.length} release(s) across ${products.length} product(s)`,
);
