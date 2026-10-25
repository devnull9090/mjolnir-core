#!/usr/bin/env node
//
// Mirror this PC's installed MJOLNIR mod folders onto PC 2 through the agent,
// so both games run the same Lua and native code for a two-PC test.
//
//   node tools/remote/sync-mods.mjs MJOLNIRLobby MJOLNIRHud [...] [--max-mb 25] [--dry]
//
// Every file under <ue4ss>\Mods\<name> on this PC is PUT to the same path on
// PC 2, except the mods' own state and logs (*.log, auto_state.txt, the
// bridge's request/response/status files, agent-token.txt) and files over
// --max-mb, which are listed instead. The game on PC 2 should be closed: a Lua
// file read at start is only picked up at the next start anyway.
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { commands as pc2 } from "./remote.mjs";
import { paths } from "../mcp/game/game.mjs";

const args = process.argv.slice(2);
const names = args.filter((a) => !a.startsWith("--") && !/^\d+$/.test(a));
const maxMb = Number(args[args.indexOf("--max-mb") + 1] || 25);
const dry = args.includes("--dry");
if (!names.length) {
  console.error("usage: sync-mods.mjs <mod folder> [...] [--max-mb 25] [--dry]");
  process.exit(2);
}
const SKIP = /(\.log|\.old-\d+|auto_state\.txt|request\.txt|response\.txt|status\.txt|agent-token\.txt|life_cycle\.txt|hitches\.old\.log)$/i;

let sent = 0;
let bytes = 0;
for (const name of names) {
  const root = path.join(paths().mods, name);
  if (!fs.existsSync(root)) {
    console.error(`${name}: not installed here (${root})`);
    continue;
  }
  const files = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else files.push(full);
    }
  };
  walk(root);
  for (const file of files) {
    const rel = path.relative(paths().mods, file).split(path.sep).join("/");
    const size = fs.statSync(file).size;
    if (SKIP.test(file)) continue;
    if (size > maxMb * 1024 * 1024) {
      console.log(`skip (${(size / 1048576).toFixed(1)} MB): ${rel}`);
      continue;
    }
    if (dry) {
      console.log(`would send ${rel} (${size} bytes)`);
      continue;
    }
    const note = await pc2.put(file, "ue4ss", `Mods/${rel}`);
    sent++;
    bytes += size;
    if (sent % 10 === 0 || size > 1048576) console.log(note);
  }
  console.log(`${name}: ${files.length} files seen`);
}
console.log(`sent ${sent} files, ${(bytes / 1048576).toFixed(1)} MB`);
