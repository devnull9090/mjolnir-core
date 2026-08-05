// Fails unless a release tag has a changelog entry to ship with it.
//
//   node scripts/check-changelog.mjs launcher-v0.5.4
//
// Every release workflow runs this before it builds anything. A release is the
// one moment the whole audience is looking, and it is also the moment nobody
// wants to stop and write prose — so the entry is required at the gate rather
// than requested in a checklist. The workflows then read the same file back for
// the GitHub release body and the Discord announcement, which means writing one
// is not extra work: it is the only way to get release notes at all.
//
// Prints the entry's title and summary as workflow outputs so a caller does not
// have to parse the Markdown a second time.

import { appendFileSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const changelogDir = path.join(repoRoot, "changelog");

const tag = process.argv[2];
if (!tag) {
  console.error("usage: node scripts/check-changelog.mjs <tag>   e.g. launcher-v0.5.4");
  process.exit(2);
}

const { products } = JSON.parse(readFileSync(path.join(changelogDir, "products.json"), "utf8"));

// Longest prefix first, so a product whose prefix is a prefix of another's
// cannot swallow the match.
const product = [...products]
  .sort((a, b) => b.tagPrefix.length - a.tagPrefix.length)
  .find((p) => tag.startsWith(p.tagPrefix));

if (!product) {
  console.error(
    `No product in changelog/products.json releases under the tag "${tag}".\n` +
      `Known prefixes: ${products.map((p) => p.tagPrefix).join(", ")}`,
  );
  process.exit(1);
}

const version = tag.slice(product.tagPrefix.length);
const relative = `changelog/${product.id}/${version}.md`;
const entryPath = path.join(changelogDir, product.id, `${version}.md`);

let raw;
try {
  raw = readFileSync(entryPath, "utf8");
} catch {
  console.error(
    `${product.name} ${version} has no changelog entry.\n\n` +
      `Create ${relative} before tagging. It is what the release notes, the\n` +
      `Discord announcement, mjolnircore.com/changelog and the launcher's\n` +
      `"What's new" modal all read. See changelog/README.md for the format.`,
  );
  process.exit(1);
}

const lines = raw.replace(/\r\n/g, "\n").split("\n");
let cursor = 0;
while (cursor < lines.length && !lines[cursor].trim()) cursor += 1;

if (!lines[cursor]?.startsWith("# ")) {
  console.error(`${relative} must open with a '# Title' line. See changelog/README.md.`);
  process.exit(1);
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

const problems = [];
if (!meta.date) problems.push("no '**Date:**' line");
else if (!/^\d{4}-\d{2}-\d{2}$/.test(meta.date)) problems.push(`'**Date:** ${meta.date}' is not YYYY-MM-DD`);
if (!meta.summary) problems.push("no '**Summary:**' line");
// Matches the ceiling in hub/scripts/sync-changelog.mjs, so a summary that
// would fail the site build fails here first — at the tag, where it is still
// one commit to fix rather than a broken release.
else if (meta.summary.length > 200) {
  problems.push(
    `the '**Summary:**' is ${meta.summary.length} characters; the limit is 200. ` +
      "It is the meta description and the launcher's opening line — aim for one sentence under 160.",
  );
}

const body = lines.slice(cursor).join("\n").trim();
if (!body) problems.push("no body below the summary");

if (problems.length > 0) {
  console.error(`${relative} is incomplete:\n`);
  for (const problem of problems) console.error(`  - ${problem}`);
  console.error("\nSee changelog/README.md for the format.");
  process.exit(1);
}

console.log(`${relative}\n  ${title}\n  ${meta.summary}`);

// Consumed by the release workflows for the GitHub release body and the Discord
// embed. Multi-line values need the delimiter form.
if (process.env.GITHUB_OUTPUT) {
  appendFileSync(
    process.env.GITHUB_OUTPUT,
    `entry_path=${relative}\n` +
      `product=${product.id}\n` +
      `product_name=${product.name}\n` +
      `version=${version}\n` +
      `title=${title}\n` +
      `summary=${meta.summary}\n` +
      `url=https://mjolnircore.com/changelog/${product.id}/${version}\n` +
      `body<<CHANGELOG_BODY_EOF\n${body}\nCHANGELOG_BODY_EOF\n`,
  );
}
