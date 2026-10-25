#!/usr/bin/env node
//
// The two-PC audio-role test: does each game give a player's own biped and
// first-person weapon the owner that makes their sounds "first person"?
// Background: docs/re/client_sound_roles.md. Nobody has to be at either PC,
// but someone listening at PC 2 tells us what the samples cannot.
//
// PC 1 is this machine (tools/mcp/game), PC 2 runs tools/remote/mjolnir-agent.ps1
// with the MJOLNIR bridge installed. Both games need MJOLNIRLobby, and PC 1
// native\join_in_progress.txt = 1 for the join-in-progress run.
//
//   node tools/remote/audio-roles-test.mjs [--before] [--map BGL] [--mode slayer]
//        [--seconds 60] [--actions 2] [--reload R] [--grenade G] [--no-actions]
//
//   --before    PC 2 joins the fireteam before PC 1 starts the map (the control
//               run); without it PC 2 joins the match in progress
//   --seconds   how long both probes sample after PC 2 has a biped
//   --actions   how many fire + reload + grenade rounds PC 2 performs while
//               sampling, each announced with a MARK line in both logs
//
// The run leaves <tmp>\mjolnir-audio-roles-<time>\ with pc1.log, pc2.log (the
// probes), both fireteam logs and a summary.txt: per sample, which pawn owns
// each player's biped on each machine.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { commands as pc2, autoState as pc2AutoFile } from "./remote.mjs";
import { callTool, bridgeCall, bridgeStatus, paths } from "../mcp/game/game.mjs";

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : fallback;
};
const BEFORE = args.includes("--before");
const MAP = flag("map", "BGL");
const MODE = flag("mode", "slayer");
const SECONDS = Number(flag("seconds", "60"));
const ACTIONS = args.includes("--no-actions") ? 0 : Number(flag("actions", "2"));
const RELOAD = flag("reload", "R");
const GRENADE = flag("grenade", "G");
const HERE = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const PROBE = fs.readFileSync(path.join(HERE, "audio-probe.lua"), "utf8");
const OUT = path.join(os.tmpdir(), `mjolnir-audio-roles-${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}`);

const started = Date.now();
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const say = (text) => {
  const s = Math.round((Date.now() - started) / 1000);
  const line = `[${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}] ${text}`;
  console.log(line);
  fs.mkdirSync(OUT, { recursive: true });
  fs.appendFileSync(path.join(OUT, "run.txt"), line + "\n");
};
async function waitFor(what, test, timeoutMs, everyMs = 1000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    let value;
    try {
      value = await test();
    } catch (error) {
      value = null;
      if (Date.now() > deadline) throw error;
    }
    if (value) return value;
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${what}`);
    await sleep(everyMs);
  }
}
function readState(text) {
  return Object.fromEntries(text.split(/\r?\n/).filter(Boolean).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]));
}

// --- The two sides -------------------------------------------------------------

const pc1File = (rel) => path.join(paths().mods, "MJOLNIRLobby", "native", rel);
const pc1ProbeLog = () => path.join(paths().ue4ss, "mjolnir-bridge", "audio-probe.log");

const pc1 = {
  name: "PC 1",
  async lua(code, timeout = 15000) {
    const r = await bridgeCall("lua", code, timeout);
    if (!r.ok) throw new Error(r.body);
    return r.body;
  },
  async auto(...words) {
    const file = pc1File("auto_state.txt");
    const before = fs.existsSync(file) ? readState(fs.readFileSync(file, "utf8")).at : "0";
    const r = await bridgeCall("console", `mjolnir_auto ${words.join(" ")}`.trim());
    if (!r.ok) throw new Error(r.body);
    // `host` answers only once the map travel has begun, 20-30 s later.
    return waitFor("PC 1's mjolnir_auto answer", () => {
      const state = fs.existsSync(file) ? readState(fs.readFileSync(file, "utf8")) : null;
      return state && state.at !== before ? state : null;
    }, 60000, 250);
  },
  async input(steps) {
    const r = await callTool("game_input", { steps });
    if (r.isError) throw new Error(r.content?.[0]?.text);
  },
  world() {
    return bridgeStatus()?.world ?? "";
  },
  log() {
    const file = pc1File("fireteam.log");
    return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
  },
  probeLog() {
    const file = pc1ProbeLog();
    return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
  },
  clearProbe() {
    const file = pc1ProbeLog();
    if (fs.existsSync(file)) fs.writeFileSync(file, "");
  },
};

const pc2Side = {
  name: "PC 2",
  lua: (code, timeout) => pc2.lua(code, timeout),
  async auto(...words) {
    return JSON.parse(await pc2.auto(...words));
  },
  async input(steps) {
    await pc2.input(JSON.stringify(steps));
  },
  async world() {
    return JSON.parse(await pc2.status()).bridge?.world ?? "";
  },
  log: () => pc2.get("ue4ss", "Mods/MJOLNIRLobby/native/fireteam.log"),
  probeLog: () => pc2.probe("dump"),
  clearProbe: () => pc2.probe("clear"),
};

// --- Steps -----------------------------------------------------------------------

async function signIn(side) {
  return waitFor(`${side.name} to sign in`, async () => {
    const state = await side.auto("state");
    if (state.signed_in === "1") return state;
    // Enter alone at the title screen; a click or Space here can start the campaign.
    say(`${side.name}: at the title screen; pressing Enter`);
    await side.input([{ key: "Enter" }]);
    await sleep(6000);
    return null;
  }, 120000, 2000);
}

async function loadProbe(side) {
  const answer = await side.lua(PROBE, 30000);
  if (!answer.includes("AudioProbe ready")) throw new Error(`${side.name}: the probe did not load: ${answer}`);
}

async function mark(text) {
  say(`MARK ${text}`);
  await Promise.all([
    pc1.lua(`AudioProbe.mark(${JSON.stringify(text)})`).catch(() => null),
    pc2Side.lua(`AudioProbe.mark(${JSON.stringify(text)})`).catch(() => null),
  ]);
}

/** Fire, reload and throw a grenade on one side, marking each in both logs. */
async function actions(side, round) {
  await mark(`${side.name} round ${round}: fire`);
  await side.input([{ mouse: "left", hold: 700 }]);
  await sleep(1500);
  await mark(`${side.name} round ${round}: reload (${RELOAD})`);
  await side.input([{ key: RELOAD }]);
  await sleep(4000);
  await mark(`${side.name} round ${round}: grenade (${GRENADE})`);
  await side.input([{ key: GRENADE }]);
  await sleep(4000);
}

// --- Summary ---------------------------------------------------------------------

/** One probe log into [{t, label, players: {index: name}, bipeds: [{name, player, owner, ownedByLocalPawn}], localPawn}]. */
function parseProbe(text) {
  const samples = [];
  // Lua writes the log in text mode, so the lines end in CRLF.
  for (const block of text.split(/\r?\n--\r?\n/)) {
    const lines = block.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (!lines.length) continue;
    const head = lines[0].match(/^t=(\d+) clock=([\d.]+) (?:label=(\S+)|MARK (.*))/);
    if (!head) continue;
    const sample = { t: Number(head[1]), label: head[3], mark: head[4], players: {}, bipeds: [], fps: [] };
    for (const line of lines.slice(1)) {
      let m;
      if ((m = line.match(/^PC \S+ player=(\S+) pawn=(\S+) /))) {
        sample.localPlayer = m[1];
        sample.localPawn = m[2];
      } else if (line.startsWith("PLAYERS ")) {
        for (const entry of line.slice(8).split(" ")) {
          const [, name, index, local] = entry.split(":");
          sample.players[index] = { name, local: local === "local" };
        }
      } else if ((m = line.match(/^BIPED (\S+) owner=(\S+) player=(-?\d+)/))) {
        const chain = m[2].split("<-");
        sample.bipeds.push({ name: m[1], owner: chain[1] ?? "-", player: Number(m[3]), ownedByLocalPawn: chain[1] === sample.localPawn });
      } else if ((m = line.match(/^FP (\S+) owner=(\S+)/))) {
        const chain = m[2].split("<-");
        sample.fps.push({ name: m[1], owner: chain[1] ?? "-", ownedByLocalPawn: chain[1] === sample.localPawn });
      }
    }
    samples.push(sample);
  }
  return samples;
}

function summarize(name, text) {
  const out = [`== ${name}`];
  for (const s of parseProbe(text)) {
    if (s.mark) {
      out.push(`  ${s.t} MARK ${s.mark}`);
      continue;
    }
    const localIndex = Object.entries(s.players).find(([, p]) => p.local)?.[0] ?? "?";
    const players = Object.entries(s.players).map(([i, p]) => `${i}=${p.name}${p.local ? "*" : ""}`).join(" ");
    const bipeds = s.bipeds
      .map((b) => `p${b.player}:${b.ownedByLocalPawn ? "LOCAL-PAWN" : b.owner}`)
      .join(" ");
    const fps = s.fps.map((f) => (f.ownedByLocalPawn ? "fp:LOCAL-PAWN" : `fp:${f.owner}`)).join(" ");
    out.push(`  ${s.t} me=${localIndex} players[${players}] bipeds[${bipeds}] ${fps}`);
  }
  return out.join("\n");
}

// --- Main ------------------------------------------------------------------------

async function main() {
  say(`audio roles: PC 1 hosts ${MAP} ${MODE}; PC 2 joins ${BEFORE ? "before the start" : "in progress"}; results in ${OUT}`);
  const [host, joiner] = await Promise.all([signIn(pc1), signIn(pc2Side)]);
  say(`signed in: PC 1 ${host.name} (${host.world}), PC 2 ${joiner.name} (${joiner.world})`);
  if (host.frontend !== "1") throw new Error("PC 1 is in a match; leave it first");
  if (joiner.frontend !== "1") throw new Error("PC 2 is in a match; leave it first");

  await Promise.all([loadProbe(pc1), loadProbe(pc2Side)]);
  pc1.clearProbe();
  await pc2Side.clearProbe();
  say("probes loaded on both");

  // A join waits for the joiner's own PlayFab lobby, made ~30 s after sign-in.
  const pc2LogMark0 = 0;
  await waitFor("PC 2's lobby", async () => {
    const lines = (await pc2Side.log()).slice(pc2LogMark0).split("\n");
    const at = lines.findLastIndex((l) => /lobby: (created|left)/.test(l));
    return at >= 0 && lines[at].includes("lobby: created") ? true : null;
  }, 90000, 2000);

  const pc1LogStart = pc1.log().length;
  const pc2LogStart = (await pc2Side.log()).length;

  if (BEFORE) {
    // The host lists its lobby, PC 2 joins the fireteam, then the host starts.
    const listed = await pc1.auto("public", "on");
    say(`PC 1: ${listed.result}`);
    await sleep(8000);
    const join = await pc2Side.auto("join", host.name);
    say(`PC 2: ${join.result}`);
    await waitFor("PC 2 in PC 1's fireteam", async () => {
      const state = await pc1.auto("state");
      return Number(state.players) >= 2 ? state : null;
    }, 90000, 3000);
    say("PC 1: fireteam of two");
    const hosting = await pc1.auto("host", MAP, MODE);
    say(`PC 1: ${hosting.result}`);
    if (!hosting.result?.startsWith("hosting")) throw new Error("PC 1 did not start hosting");
  } else {
    const hosting = await pc1.auto("host", MAP, MODE);
    say(`PC 1: ${hosting.result}`);
    if (!hosting.result?.startsWith("hosting")) throw new Error("PC 1 did not start hosting");
  }

  await sleep(10000);
  await waitFor("PC 1's match", () => {
    const beat = bridgeStatus();
    return beat && beat.world?.includes(`/${MAP}/`) && /MeteoritePawn/.test(beat.pawn ?? "") ? beat : null;
  }, 120000, 2000);
  say("PC 1: in the match");

  if (!BEFORE) {
    await sleep(15000);
    const join = await pc2Side.auto("join", host.name);
    say(`PC 2: ${join.result}`);
    const joined = await waitFor("PC 2's join", async () => {
      const s = await pc2AutoFile();
      return /^(joined|error)/.test(s?.result ?? "") ? s : null;
    }, 30000, 1000);
    say(`PC 2: ${joined.result}`);
    if (joined.result.startsWith("error")) throw new Error(joined.result);
    const injected = await waitFor("PC 1 to put the joiner in its game", () => {
      return pc1.log().slice(pc1LogStart).split("\n").find((l) => /inject: player \d+ .* created/.test(l)) ?? null;
    }, 90000, 1000);
    say(`PC 1: ${injected.trim()}`);
  }

  // Sample from the moment PC 2 reaches the map: the first seconds are the
  // interesting ones (its biped appears, its player index settles).
  await waitFor("PC 2 to reach the match", async () => (await pc2Side.world()).includes(`/${MAP}/`) || null, 180000, 2000);
  say(`PC 2: in the match; sampling ${SECONDS} s on both`);
  await Promise.all([
    pc1.lua(`print(AudioProbe.start("pc1", ${SECONDS}, 1000))`),
    pc2Side.lua(`print(AudioProbe.start("pc2", ${SECONDS}, 1000))`),
  ]);
  // Unlist once PC 2 is in (two players keep the engine's end-of-match test quiet).
  await pc1.auto("public", "off").then((s) => say(`PC 1: ${s.result}`), () => null);

  const spawned = await waitFor("PC 2's biped", async () => {
    const text = await pc2Side.probeLog();
    const last = parseProbe(text).filter((s) => !s.mark).at(-1);
    return last && last.bipeds.length >= 2 ? last : null;
  }, 90000, 3000);
  say(`PC 2: sees ${spawned.bipeds.length} bipeds; players ${JSON.stringify(spawned.players)}`);

  for (let round = 1; round <= ACTIONS; round++) {
    await actions(pc2Side, round);
    await actions(pc1, round);
  }
  const elapsed = (Date.now() - started) / 1000;
  const remaining = Math.max(0, SECONDS - 20 - (ACTIONS ? ACTIONS * 22 : 0));
  if (remaining > 0) {
    say(`waiting ${Math.round(remaining)} s for the probes to finish`);
    await sleep(remaining * 1000);
  }
  await sleep(3000);

  const pc1Text = pc1.probeLog();
  const pc2Text = await pc2Side.probeLog();
  fs.writeFileSync(path.join(OUT, "pc1.log"), pc1Text);
  fs.writeFileSync(path.join(OUT, "pc2.log"), pc2Text);
  fs.writeFileSync(path.join(OUT, "pc1-fireteam.log"), pc1.log().slice(pc1LogStart));
  fs.writeFileSync(path.join(OUT, "pc2-fireteam.log"), (await pc2Side.log()).slice(pc2LogStart));
  const summary = [summarize("PC 1 (host)", pc1Text), summarize("PC 2 (joiner)", pc2Text)].join("\n\n");
  fs.writeFileSync(path.join(OUT, "summary.txt"), summary + "\n");
  console.log("\n" + summary);
  say(`done in ${Math.round(elapsed)} s; files in ${OUT}`);
}

// `--summarize <probe log>`: read one log's samples, nothing else.
if (flag("summarize")) {
  console.log(summarize(flag("summarize"), fs.readFileSync(flag("summarize"), "utf8")));
  process.exit(0);
}

main().catch((error) => {
  say(`FAILED: ${error.message ?? error}`);
  process.exit(1);
});
