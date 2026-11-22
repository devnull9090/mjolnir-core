// Checks the docs keyword search (src/lib/docs-search.ts) against the index
// sync-docs.mjs wrote, so it runs after `pnpm sync`.
//
// The queries are ones a reader types: a feature by name, an identifier, a
// word cut short, a typo. Each names the doc that has to come back near the
// top; a ranking change that loses one fails here rather than on the site.

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  DocsIndex,
  highlight,
  indexTerms,
  queryTerms,
  snippet,
  type SearchIndexFile,
} from "../src/lib/docs-search";

const hubDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const file = JSON.parse(
  readFileSync(path.join(hubDir, "public", "docs-search.json"), "utf8"),
) as SearchIndexFile;

let failed = 0;
function check(name: string, ok: boolean, detail = "") {
  if (ok) return;
  failed += 1;
  console.error(`FAIL ${name}${detail ? `: ${detail}` : ""}`);
}

const started = performance.now();
const index = new DocsIndex(file);
const built = performance.now() - started;

const slugsFor = (query: string, limit = 5) =>
  index.search(query, limit).map((hit) => file.docs[file.chunks[hit.chunk][0]][0]);

/** [query, the doc that must be in the first `within` results, within] */
const expectations: Array<[string, string, number]> = [
  ["sound mixer", "sound-mixer", 1],
  ["texture swap", "texture-swapping", 3],
  ["forge pack authoring", "forge-pack-authoring", 3],
  ["game pass", "game-pass", 3],
  ["crash report", "crash-reports", 3],
  ["discord rich presence", "discord-presence", 1],
  ["kill feed", "multiplayer-hud", 3],
  ["container numbers load order", "chunk-numbering", 3],
  // An identifier, whole and by its parts.
  ["mjolnir_auto", "game-automation", 5],
  // A word cut short, as it is while typing.
  ["mixe", "sound-mixer", 3],
  // A typo.
  ["vehicel", "custom-vehicles", 8],
  // Words that say nothing do not sink the ones that do.
  ["how do I install a map while the game is running", "live-map-install", 3],
];
for (const [query, slug, within] of expectations) {
  const slugs = slugsFor(query, within);
  check(`"${query}" finds ${slug}`, slugs.includes(slug), `got ${slugs.join(", ") || "nothing"}`);
}

check("no query, no results", index.search("   ").length === 0);
check("nonsense finds nothing", index.search("zzqqxxyyww").length === 0);

// No doc crowds out the rest of a result list.
{
  const perDoc = new Map<number, number>();
  for (const hit of index.search("forge", 12)) {
    const doc = file.chunks[hit.chunk][0];
    perDoc.set(doc, (perDoc.get(doc) ?? 0) + 1);
  }
  check("at most three chunks of one doc", Math.max(...perDoc.values()) <= 3);
}

// Every chunk has a key that leads back to it: the semantic index stores keys.
{
  let wrong = 0;
  for (let chunk = 0; chunk < file.chunks.length; chunk += 1) {
    if (index.chunkOfKey(index.keyOf(chunk)) !== chunk) wrong += 1;
  }
  check("chunk keys round-trip", wrong === 0, `${wrong} do not`);
}

// Fusing: a chunk both searches found leads, one only meaning found is kept and marked.
{
  const lexical = index.search("sound mixer", 6);
  const other = index.keyOf(index.search("crash report", 1)[0].chunk);
  const fused = index.fuse(
    lexical,
    [
      { key: index.keyOf(lexical[2].chunk), relevance: 0.9 },
      { key: other, relevance: 0.8 },
      { key: "gone#x#0", relevance: 0.9 },
    ],
    8,
  );
  check("fused: found by both leads", fused[0].chunk === lexical[2].chunk);
  const extra = fused.find((hit) => index.keyOf(hit.chunk) === other);
  check("fused: semantic-only hit kept and marked", extra?.semanticOnly === true);
  check("fused: a key this build lacks is dropped", fused.length === lexical.length + 1);
  // What only meaning found, and found weakly, is not shown; it does not reorder the keywords either.
  const weak = index.fuse(lexical, [{ key: other, relevance: 0.15 }], 8);
  check(
    "fused: a weak semantic-only hit is left out",
    weak.length === lexical.length && weak.every((hit, at) => hit.chunk === lexical[at].chunk),
  );
}

check(
  "identifier indexed whole and by parts",
  ["cheat_all_weapons", "cheat", "all", "weapons"].every((term) =>
    indexTerms("cheat_all_weapons").includes(term),
  ),
);
check("camel case splits", indexTerms("MJOLNIRLobby").includes("lobby"));
check("stopwords dropped", queryTerms("how do I host a game").join(" ") === "host game");
check("a query of only stopwords keeps them", queryTerms("how to").length === 2);

{
  const parts = highlight("cheat_all_weapons in the rain", ["weapons", "in"]);
  const hits = parts.filter((part) => part.hit).map((part) => part.text);
  check("highlight marks parts of identifiers, not insides of words", hits.join("|") === "weapons|in");
  const cut = snippet(`${"word ".repeat(100)}needle ${"word ".repeat(100)}`, ["needle"]);
  check("snippet centres on the match", cut.some((part) => part.hit && part.text === "needle"));
  check(
    "snippet is short",
    cut.reduce((sum, part) => sum + part.text.length, 0) < 260,
  );
}

if (failed > 0) {
  console.error(`docs search: ${failed} check(s) failed`);
  process.exit(1);
}
console.log(
  `docs search: ok (${file.docs.length} docs, ${file.chunks.length} chunks, index built in ${built.toFixed(0)} ms)`,
);
