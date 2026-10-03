#!/usr/bin/env node
//
// The two-PC join-in-progress test, with nobody at either PC.
//
// PC 1 is this machine (driven through tools/mcp/game, the MCP server's own
// code), PC 2 runs tools/remote/mjolnir-agent.ps1 (agent 2, for /input). Both
// games need MJOLNIRLobby with `mjolnir_auto` and the MJOLNIR bridge, and PC 1
// needs native\join_in_progress.txt = 1.
//
//   node tools/remote/jip-test.mjs [--restart] [--map BGL] [--mode slayer] [--wait 15]
//
//   --restart   close and start both games first (sign-in included)
//   --map/mode  what PC 1 hosts (an installed map's code and a game type)
//   --wait      seconds of match before PC 2 joins
//
// Steps: sign both in (Enter / click / Space until the main menu shows),
// PC 1 lists the game publicly and starts it, PC 2 joins it from the hub list
// once it is under way, then the test waits for PC 2 to fade in and for PC 1
// to give the joiner a biped (tools/remote/blam-players.py). Exit code 0 when
// the joiner spawned.

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { execFileSync } from "node:child_process";
import { commands as pc2, autoState as pc2AutoFile } from "./remote.mjs";
import { callTool, bridgeCall, bridgeStatus, paths } from "../mcp/game/game.mjs";

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : fallback;
};
const RESTART = args.includes("--restart");
const MAP = flag("map", "BGL");
const MODE = flag("mode", "slayer");
const JOIN_AFTER = Number(flag("wait", "15")) * 1000;

const HERE = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const started = Date.now();
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const say = (text) => {
  const s = Math.round((Date.now() - started) / 1000);
  console.log(`[${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}] ${text}`);
};

async function waitFor(what, test, timeoutMs, everyMs = 1000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    let value;
    try {
      value = await test();
    } catch {
      value = null;
    }
    if (value) return value;
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${what}`);
    await sleep(everyMs);
  }
}

const SIGN_IN = [{ key: "Enter" }, { wait: 1200 }, { click: [640, 360] }, { wait: 1200 }, { key: "Space" }];

// --- PC 1 (this machine) -----------------------------------------------------

const pc1File = (rel) => path.join(paths().mods, "MJOLNIRLobby", "native", rel);

function readState(text) {
  return Object.fromEntries(text.split(/\r?\n/).filter(Boolean).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]));
}

const pc1 = {
  name: "PC 1",
  async auto(...words) {
    const file = pc1File("auto_state.txt");
    const before = fs.existsSync(file) ? readState(fs.readFileSync(file, "utf8")).at : "0";
    const r = await bridgeCall("console", `mjolnir_auto ${words.join(" ")}`.trim());
    if (!r.ok) throw new Error(r.body);
    return waitFor("PC 1's mjolnir_auto answer", () => {
      const state = fs.existsSync(file) ? readState(fs.readFileSync(file, "utf8")) : null;
      return state && state.at !== before ? state : null;
    }, 10000, 250);
  },
  async input(steps) {
    const r = await callTool("game_input", { steps });
    if (r.isError) throw new Error(r.content?.[0]?.text);
  },
  async restart() {
    await callTool("game_quit", { force: true });
    await sleep(6000);
    const r = await callTool("game_launch", {});
    if (r.isError) throw new Error(r.content?.[0]?.text);
  },
  log() {
    const file = pc1File("fireteam.log");
    return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
  },
};

// --- PC 2 (the agent) ----------------------------------------------------------

const pc2Side = {
  name: "PC 2",
  async auto(...words) {
    return JSON.parse(await pc2.auto(...words));
  },
  async input(steps) {
    await pc2.input(JSON.stringify(steps));
  },
  async restart() {
    await pc2.quit("--force");
    await sleep(6000);
    await waitFor("PC 2's game to start", async () => JSON.parse(await pc2.launch()).ok || null, 60000, 3000);
    await waitFor("PC 2's bridge", async () => JSON.parse(await pc2.status()).bridge?.controller === "yes", 180000, 3000);
  },
  async log() {
    return pc2.get("ue4ss", "Mods/MJOLNIRLobby/native/fireteam.log");
  },
};

// --- Steps -------------------------------------------------------------------

async function signIn(side) {
  return waitFor(`${side.name} to sign in`, async () => {
    const state = await side.auto("state");
    if (state.signed_in === "1") return state;
    say(`${side.name}: at the title screen; pressing start`);
    await side.input(SIGN_IN);
    await sleep(4000);
    return null;
  }, 120000, 2000);
}

async function main() {
  say(`join in progress: PC 1 hosts ${MAP} ${MODE}, PC 2 joins ${JOIN_AFTER / 1000} s in`);
  if (RESTART) {
    say("restarting both games");
    await Promise.all([pc1.restart(), pc2Side.restart()]);
  }
  const [host, joiner] = await Promise.all([signIn(pc1), signIn(pc2Side)]);
  say(`signed in: PC 1 ${host.name} (${host.world}), PC 2 ${joiner.name} (${joiner.world})`);
  if (joiner.frontend !== "1") throw new Error("PC 2 is in a match; leave it first (or --restart)");

  const hosting = await pc1.auto("host", MAP, MODE);
  say(`PC 1: ${hosting.result}`);
  if (!hosting.result?.startsWith("hosting")) throw new Error("PC 1 did not start hosting");
  // While a map loads, ask the game nothing: polling mjolnir_auto through the
  // travel went with PC 1's game dying at map load (2026-10-03). The bridge's
  // heartbeat file says where it is without touching the game thread.
  await sleep(10000);
  await waitFor("PC 1's match", () => {
    const beat = bridgeStatus();
    return beat && beat.world?.includes(`/${MAP}/`) && /MeteoritePawn/.test(beat.pawn ?? "") ? beat : null;
  }, 120000, 2000);
  say(`PC 1: in the match; PC 2 joins in ${JOIN_AFTER / 1000} s`);
  await sleep(JOIN_AFTER);

  const pc1LogStart = pc1.log().length;
  const pc2LogStart = (await pc2Side.log()).length;
  const join = await pc2Side.auto("join", host.name);
  say(`PC 2: ${join.result}`);
  const joined = await waitFor("PC 2's join", async () => {
    const s = await pc2AutoFile();
    return /^(joined|error)/.test(s?.result ?? "") ? s : null;
  }, 30000, 1000);
  say(`PC 2: ${joined.result}`);
  if (joined.result.startsWith("error")) throw new Error(joined.result);

  const injected = await waitFor("PC 1 to put the joiner in its game", () => {
    const line = pc1.log().slice(pc1LogStart).split("\n").find((l) => /inject: player \d+ .* created/.test(l));
    return line ?? null;
  }, 90000, 1000);
  say(`PC 1: ${injected.trim()}`);
  const faded = await waitFor("PC 2 to fade in", async () => {
    const log = (await pc2Side.log()).slice(pc2LogStart);
    return log.split("\n").find((l) => l.includes("faded the joiner's view in")) ?? null;
  }, 120000, 2000);
  say(`PC 2: ${faded.trim()}`);

  const spawned = await waitFor("PC 1 to give the joiner a biped", () => {
    const out = JSON.parse(execFileSync("python", [path.join(HERE, "blam-players.py"), "--json"], { encoding: "utf8" }));
    const joinerPlayer = (out.players ?? []).find((p) => p.machine > 0 && p.flags & 0x8000);
    return joinerPlayer && joinerPlayer.unit !== -1 ? joinerPlayer : null;
  }, 60000, 2000);
  say(`PC 1: joiner player ${spawned.index} has a biped (flags ${spawned.flags.toString(16)})`);
  const beat = JSON.parse(await pc2.status()).bridge ?? {};
  say(`PC 2: ${beat.world}, ${beat.pawn}`);
  say("PASS: the joiner is in the match");
}

main().then(
  () => process.exit(0),
  (error) => {
    say(`FAIL: ${error.message ?? error}`);
    process.exit(1);
  }
);
