// Generates the tag definition artifacts consumed by /docs/tags.
//
// The definition corpus is produced by `mjolnir defs` from an installed copy of
// the game and lives outside the Next project. Reading it from the app would
// make Turbopack trace the repository into the server bundle, so it is
// snapshotted here and imported as plain JSON, matching sync-docs.mjs.
//
// Three artifacts are written:
//   src/generated/tag-defs.json   full corpus, minified, used only at build time
//                                 to statically render one page per group
//   src/generated/tag-index.json  compact group summaries, imported directly
//   public/tag-search.json        field-name search terms, fetched on demand so
//                                 they never enter the page bundle
//
// Only schema is published: field names, types, offsets, and option names. Tag
// values are game content and are never emitted.

import { mkdir, readFile, writeFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const hubDir = path.resolve(scriptDir, "..");
const sourceFile = path.resolve(hubDir, "..", "defs", "hce", "tag-definitions.json");
const generatedDir = path.join(hubDir, "src", "generated");
const publicDir = path.join(hubDir, "public");
const defsFile = path.join(generatedDir, "tag-defs.json");
const indexFile = path.join(generatedDir, "tag-index.json");
const searchFile = path.join(publicDir, "tag-search.json");

/** Structural field types that carry no user-visible value. */
const HIDDEN_TYPES = new Set(["pad", "terminator X", "custom"]);

function slugify(name) {
  return name.replace(/_/g, "-").toLowerCase();
}

/** Distinct, human-meaningful field names for a group, for search. */
function searchTerms(group) {
  const seen = new Set();
  for (const struct of group.structs ?? []) {
    for (const field of struct.fields ?? []) {
      if (HIDDEN_TYPES.has(field.type)) continue;
      const name = (field.name ?? "").trim();
      if (name.length > 2) seen.add(name.toLowerCase());
    }
  }
  return [...seen];
}

async function main() {
  let raw;
  try {
    raw = await readFile(sourceFile, "utf8");
  } catch {
    console.warn(
      `[sync-tag-defs] ${path.relative(hubDir, sourceFile)} not found; ` +
        "skipping. Run `cargo run -p blam-cli -- defs` against an installed game to generate it."
    );
    await mkdir(generatedDir, { recursive: true });
    await mkdir(publicDir, { recursive: true });
    await writeFile(defsFile, JSON.stringify({ generator: "", build: "", groups: {} }));
    await writeFile(indexFile, JSON.stringify({ build: "", groups: [] }));
    await writeFile(searchFile, JSON.stringify({}));
    return;
  }

  const corpus = JSON.parse(raw);
  const names = Object.keys(corpus.groups ?? {}).sort();

  const summaries = [];
  const search = {};

  for (const name of names) {
    const g = corpus.groups[name];
    const structs = g.structs ?? [];
    const fields = structs.reduce((n, s) => n + (s.fields?.length ?? 0), 0);
    const visible = structs.reduce(
      (n, s) => n + (s.fields ?? []).filter((f) => !HIDDEN_TYPES.has(f.type)).length,
      0
    );
    const slug = slugify(name);

    summaries.push({
      slug,
      name,
      group: g.group,
      version: g.version,
      tagCount: g.tag_count ?? 0,
      structs: structs.length,
      fields,
      visible,
      size: structs[0]?.size ?? null,
    });
    search[slug] = searchTerms(g);
  }

  const index = {
    generator: corpus.generator ?? "",
    build: corpus.build ?? "",
    groups: summaries,
  };

  await mkdir(generatedDir, { recursive: true });
  await mkdir(publicDir, { recursive: true });
  await writeFile(defsFile, JSON.stringify(corpus));
  await writeFile(indexFile, JSON.stringify(index));
  await writeFile(searchFile, JSON.stringify(search));

  const [d, i, s] = await Promise.all([stat(defsFile), stat(indexFile), stat(searchFile)]);
  const kib = (n) => `${(n / 1024).toFixed(0)} KiB`;
  console.log(
    `[sync-tag-defs] ${summaries.length} groups -> ` +
      `tag-defs ${kib(d.size)} (build only), tag-index ${kib(i.size)}, ` +
      `tag-search ${kib(s.size)} (lazy)`
  );
}

await main();
