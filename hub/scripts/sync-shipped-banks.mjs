// Generates src/generated/shipped-banks.json from defs/hce/shipped_banks.json.
//
// The scan refuses a map pack that carries one of these ids, and reading the
// list from outside the Next project would make Turbopack trace the repository
// into the server bundle, so it is snapshotted here like the other defs. The
// launcher compiles the same file in. `pak_banks` regenerates it after a game
// update (docs/game_update_pipeline.md).

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hubDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.resolve(hubDir, "..", "defs", "hce", "shipped_banks.json");
const outFile = path.join(hubDir, "src", "generated", "shipped-banks.json");

const ids = JSON.parse(await readFile(source, "utf8"));
if (!Array.isArray(ids) || ids.length === 0 || !ids.every(Number.isInteger)) {
  throw new Error(`${source} is not a list of bank ids`);
}
await mkdir(path.dirname(outFile), { recursive: true });
await writeFile(outFile, `${JSON.stringify(ids)}\n`);
console.log(`shipped-banks.json: ${ids.length} ids`);
