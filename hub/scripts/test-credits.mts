// The credits list (src/lib/credits.ts) against what the tree actually uses.
//
//   pnpm test   (or: tsx scripts/test-credits.mts)
//
// Fails when:
// - an entry lacks a field every credit needs, or a link is not https;
// - a Creative Commons attribution entry does not say what we changed
//   (CC BY asks for that);
// - a content pack whose assets cook into our maps
//   (tools/level/foliage_bake.py COOKED) has no entry claiming its folder,
//   or an entry claims a folder nothing cooks from.

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { CREDIT_SECTIONS, allCredits } from "../src/lib/credits";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..", "..");
const failures: string[] = [];
const fail = (message: string) => failures.push(message);

const ids = new Set<string>();
for (const section of CREDIT_SECTIONS) {
  if (ids.has(section.id)) fail(`section id "${section.id}" is used twice`);
  ids.add(section.id);
  if (!section.entries.length) fail(`section "${section.id}" has no entries`);
}

const names = new Set<string>();
for (const credit of allCredits()) {
  const label = `"${credit.name}"`;
  if (names.has(credit.name)) fail(`${label} is listed twice`);
  names.add(credit.name);
  for (const field of ["name", "by", "url", "licence", "use"] as const) {
    if (!credit[field]?.trim()) fail(`${label} has no ${field}`);
  }
  for (const link of [credit.url, credit.licenceUrl, credit.derived?.url]) {
    if (link && !link.startsWith("https://")) fail(`${label}: ${link} is not an https link`);
  }
  if (/creative commons attribution|\bCC BY\b/i.test(credit.licence)) {
    if (!credit.licenceUrl) fail(`${label} is CC BY and needs a link to the licence`);
    if (!credit.changes?.trim()) fail(`${label} is CC BY and must state what we changed`);
  }
  for (const folder of credit.contentPaths ?? []) {
    if (!/^\/Game\/[^/]+\/$/.test(folder)) fail(`${label}: content path ${folder} must look like /Game/<Pack>/`);
  }
}

// The packs the foliage bake cooks for real: COOKED = ("/Game/A/", "/Game/B/")
const bake = readFileSync(path.join(repo, "tools", "level", "foliage_bake.py"), "utf8");
const tuple = /^COOKED\s*=\s*\(([^)]*)\)/m.exec(bake);
if (!tuple) {
  fail("could not find COOKED in tools/level/foliage_bake.py");
} else {
  const cooked = [...tuple[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  const claimed = new Set(allCredits().flatMap((c) => c.contentPaths ?? []));
  for (const folder of cooked) {
    if (!claimed.has(folder)) {
      fail(`${folder} cooks into our maps (foliage_bake.py COOKED) but no credit claims it in contentPaths`);
    }
  }
  for (const folder of claimed) {
    if (!cooked.includes(folder)) {
      fail(`a credit claims ${folder} but foliage_bake.py COOKED does not cook from it`);
    }
  }
}

if (failures.length) {
  console.error(`credits: ${failures.length} problem(s)`);
  for (const message of failures) console.error(`  - ${message}`);
  process.exit(1);
}
console.log(`credits: ${allCredits().length} entries in ${CREDIT_SECTIONS.length} sections, every cooked pack credited`);
