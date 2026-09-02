// Fails if the committed sync artifacts differ from what the sync scripts
// generate. Run after `npm run sync` — see the `sync:check` script.
//
// The artifacts are snapshots of files that live outside the Next project
// (docs/, defs/, changelog/), so nothing in the hub notices when the source moves and the
// snapshot does not. `pnpm build` regenerates them, which means a stale commit
// still builds and deploys correctly, and the only symptom is a site missing
// content nobody thinks to look for.
//
// Two questions, because one command does not answer both: `git diff` for
// content that changed, `git ls-files --others` for a new note or screenshot,
// which lands as an untracked file a diff never sees. `git status` would cover
// both, but reports these files as modified on a Windows checkout with
// core.autocrlf=true — the sync scripts write LF, and status compares against
// the CRLF the checkout would produce.

import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hubDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** Everything the sync scripts write, relative to hub/. */
const OUTPUTS = [
  "src/generated/docs.json",
  "src/generated/tag-defs.json",
  "src/generated/tag-index.json",
  "src/generated/changelog.json",
  "src/generated/blog.json",
  "public/tag-search.json",
  "public/docs-images",
];

function git(...args) {
  return execFileSync("git", [...args, "--", ...OUTPUTS], { cwd: hubDir, encoding: "utf8" })
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

const changed = git("diff", "HEAD", "--name-only");
const added = git("ls-files", "--others", "--exclude-standard");
const drifted = [...changed, ...added];

if (drifted.length > 0) {
  console.error("Generated docs and tag artifacts are out of date:\n");
  for (const file of drifted) console.error(`  ${file}`);
  console.error("\nRun `pnpm sync` in hub/ and commit the result.");
  process.exit(1);
}

console.log("sync artifacts are up to date");
