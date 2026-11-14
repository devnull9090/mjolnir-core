#!/usr/bin/env node
//
// Capture FlyCam shots from the running game, for before/after comparisons.
//
// Each shot is recalled with `mjolnir_camera go N` (FlyCam switches on with no
// blend and the jump is a camera cut), left to settle, and captured at full
// resolution without taking the desktop's focus. Run it once on one build of
// a map and once on another, then compare the folders with compare.py.
//
//   node tools/flycam/capture.mjs <out-dir> [--shots 1,2,5-8] [--settle 2500] [--hide-body]
//
// The shots come from the map's own file in the game's Saved folder
// (%LOCALAPPDATA%\Meteorite\Saved\MJOLNIR_FlyCam_shots_<MAP>.json, written by
// FlyCam). With no --shots, every shot in that file is captured. Images are
// named shot<NN>[_<name>].png. FlyCam is left on at the last shot.

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { callTool } from "../mcp/game/game.mjs";

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = args.indexOf(name);
  if (i < 0) return fallback;
  const value = args[i + 1];
  args.splice(i, 2);
  return value;
};
const has = (name) => {
  const i = args.indexOf(name);
  if (i >= 0) args.splice(i, 1);
  return i >= 0;
};

const settle = Number(flag("--settle", "2500"));
const shotList = flag("--shots", null);
const hideBody = has("--hide-body");
const map = flag("--map", null);
const outDir = args[0];
if (!outDir) {
  console.error("usage: capture.mjs <out-dir> [--shots 1,2,5-8] [--settle ms] [--hide-body] [--map CODE]");
  process.exit(2);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const text = (r) => (r.content ?? []).filter((c) => c.type === "text").map((c) => c.text).join("\n");
const consoleCommand = async (command) => {
  const r = await callTool("game_console", { command });
  if (r.isError) throw new Error(`${command}: ${text(r)}`);
};

function parseList(spec) {
  const out = [];
  for (const part of spec.split(",")) {
    const m = part.trim().match(/^(\d+)(?:-(\d+))?$/);
    if (!m) throw new Error(`bad --shots entry: ${part}`);
    for (let n = Number(m[1]); n <= Number(m[2] ?? m[1]); n++) out.push(n);
  }
  return out;
}

/** The map's shots file, read the same way FlyCam reads it. */
async function shotsFile() {
  let code = map;
  // FlyCam must read the same file this script does.
  if (code) await consoleCommand(`mjolnir_camera map ${code}`);
  if (!code) {
    await consoleCommand("mjolnir_camera map");
    await sleep(600);
    const log = text(await callTool("game_log", { lines: 30, filter: "FlyCam" }));
    const lines = log.split("\n").filter((l) => /\] Map: /.test(l));
    const m = lines.length ? lines[lines.length - 1].match(/\] Map: ([A-Za-z0-9_-]+)/) : null;
    if (!m) throw new Error("FlyCam did not report the map; pass --map CODE");
    code = m[1];
  }
  const file = path.join(process.env.LOCALAPPDATA ?? "", "Meteorite", "Saved", `MJOLNIR_FlyCam_shots_${code}.json`);
  if (!fs.existsSync(file)) throw new Error(`no shots saved for ${code} (${file})`);
  return { code, data: JSON.parse(fs.readFileSync(file, "utf8")) };
}

const { code, data } = await shotsFile();
const wanted = shotList ? parseList(shotList) : data.shots.map((s) => s.n);
fs.mkdirSync(outDir, { recursive: true });

if (hideBody) await consoleCommand("mjolnir_camera body hide");
const manifest = { map: code, captured: new Date().toISOString(), settle_ms: settle, shots: [] };
for (const n of wanted) {
  const shot = data.shots.find((s) => s.n === n);
  if (!shot) {
    console.log(`shot ${n}: not in ${code}'s file, skipped`);
    continue;
  }
  await consoleCommand(`mjolnir_camera go ${n}`);
  await sleep(settle);
  const r = await callTool("game_screenshot", { max_width: 7680 });
  const image = (r.content ?? []).find((c) => c.type === "image");
  if (r.isError || !image) throw new Error(`shot ${n}: ${text(r)}`);
  const name = `shot${String(n).padStart(2, "0")}${shot.name ? "_" + shot.name : ""}.png`;
  fs.writeFileSync(path.join(outDir, name), Buffer.from(image.data, "base64"));
  manifest.shots.push({ ...shot, file: name, capture: text(r) });
  console.log(`shot ${n}: ${name} (${text(r)})`);
}
fs.writeFileSync(path.join(outDir, "shots.json"), JSON.stringify(manifest, null, 2) + "\n");
console.log(`${manifest.shots.length} shots of ${code} in ${outDir}`);
