#!/usr/bin/env node
//
// Several copies of the game on this PC, for multiplayer tests without PC 2.
//
//   node tools/remote/instances.mjs up <N> [-ResX=960 -ResY=540] [--separate]
//                                                    N copies signed in, in copy 1's lobby; then
//                                                    console 1 "mjolnir_auto host BGL slayer private"
//                                                    starts one match all N play (one simulation;
//                                                    --separate: each copy its own)
//   node tools/remote/instances.mjs players          each copy's world, UE players, Blam players
//   node tools/remote/instances.mjs down             stop every copy (never the Steam game)
//   node tools/remote/instances.mjs deploy <n>       this checkout's MJOLNIRLobby and MJOLNIRHud into copy n
//   node tools/remote/instances.mjs mirror <n>       build or refresh instance n's install (n >= 1);
//                                                    with MJ_OVERLAY=<dir>, that folder's files (laid
//                                                    out as the install) replace the copy's own
//   node tools/remote/instances.mjs launch <n>       start instance n (0 = the Steam install itself)
//   node tools/remote/instances.mjs menu <n>         sign in (no keys) and wait for the MULTIPLAYER main menu
//   node tools/remote/instances.mjs lua <n> <code>   Lua in instance n (or lua <n> @file.lua)
//   node tools/remote/instances.mjs console <n> <command>
//   node tools/remote/instances.mjs connection <n>   instance n's PlayFab lobby connection string
//   node tools/remote/instances.mjs join <n> <host>  instance n joins instance <host>'s lobby by its
//                                                    connection string (no hub listing)
//   node tools/remote/instances.mjs log <n> [lines]  the tail of instance n's MJOLNIRLobby fireteam.log
//
// Instance 0 is the Steam install. Instance n >= 1 is a mirror of it under
// %LOCALAPPDATA%\MJOLNIR\instances\<n>: every game file a hard link (no extra
// disk), and the ue4ss folder a real copy, so each instance has its own mods'
// state files, bridge channel and UE4SS.log. Each starts the exe directly with
// SteamAppId set (no Steam relaunch) and its own Saved folder
// (-saveddirsuffix), so settings and logs don't collide.
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { paths, setInstall, bridgeCall } from "../mcp/game/game.mjs";
import { SIGN_IN_LUA } from "./remote.mjs";

const STEAM_APP_ID = "2806050";
const ROOT = path.join(process.env.LOCALAPPDATA ?? "", "MJOLNIR", "instances");

/** Files under ue4ss that belong to one run, not to the install. */
const SKIP_UE4SS = [
  /\.dmp$/i,
  /^UE4SS\.log/i,
  /^MJOLNIR_FunctionDump\.txt$/i,
  /^MJOLNIR_TravelLog\.txt$/i,
  /^dti_trace.*\.csv$/i,
  /^mjolnir-bridge[\\/]/i,
  /[\\/]hub_reply_[^\\/]*\.txt$/i,
  /[\\/]last_match\.txt$/i,
  /[\\/]match_outbox\.txt$/i,
  /[\\/]discord_[^\\/]*\.txt$/i,
  /[\\/]listing\.txt$/i,
  /[\\/]auto_state\.txt$/i,
];

const STEAM_INSTALL = paths().install;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function installRoot(n) {
  if (!(n >= 0)) throw new Error(`no instance number: ${n}`);
  if (n === 0) return STEAM_INSTALL;
  return path.join(ROOT, String(n), "Halo Campaign Evolved");
}

/** Point game.mjs (bridge, paths) at instance n; its paths. */
function at(n) {
  setInstall(installRoot(n));
  return paths();
}

/** The lobby mod's native folder in instance n, as Lua wants it. */
function lobbyNative(n) {
  return path.join(at(n).mods, "MJOLNIRLobby", "native").split(path.sep).join("/");
}

async function lua(n, code, timeoutMs = 30_000) {
  at(n);
  const r = await bridgeCall("lua", code.startsWith("@") ? fs.readFileSync(code.slice(1), "utf8") : code, timeoutMs);
  return r.body.trim();
}

async function menu(n) {
  const log = at(n).ue4ssLog;
  const ready = () => fs.existsSync(log) && fs.readFileSync(log, "utf8").includes("MULTIPLAYER is on the main menu");
  for (let i = 0; i < 12 && !ready(); i++) {
    // The title menu's own click event: no keys, so no window focus needed.
    await lua(n, SIGN_IN_LUA, 10_000).catch(() => null);
    for (let j = 0; j < 8 && !ready(); j++) await sleep(1000);
  }
  if (!ready()) throw new Error(`instance ${n}: no main menu`);
  return `instance ${n}: at the main menu`;
}

async function connection(n) {
  const dir = lobbyNative(n);
  const body = await lua(n,
    `local fn = package.loadlib([[${dir}/mjolnir_lobby.dll]], "mjolnir_lobby_connection") ` +
    `if fn then pcall(fn) end ` +
    `local f = io.open([[${dir}/lobby_connection.txt]], "rb") print(f and f:read("a") or "none no file") if f then f:close() end`);
  const conn = body.match(/^ok (\S+)/m)?.[1];
  if (!conn) throw new Error(`instance ${n}: no lobby connection string (${body.split(/\r?\n/)[0]})`);
  return conn;
}

async function join(n, host) {
  const conn = await connection(Number(host));
  const dir = lobbyNative(n);
  await lua(n,
    `local f = io.open([[${dir}/join_request.txt]], "wb") f:write([[${conn}]], "\\n") f:close() ` +
    `os.remove([[${dir}/join_reply.txt]]) ` +
    `print(pcall(package.loadlib([[${dir}/mjolnir_lobby.dll]], "mjolnir_join")))`);
  for (let i = 0; i < 50; i++) {
    const file = path.join(at(n).mods, "MJOLNIRLobby", "native", "join_reply.txt");
    if (fs.existsSync(file)) return `instance ${n} -> instance ${host}: ${fs.readFileSync(file, "utf8").trim()}`;
    await sleep(100);
  }
  throw new Error(`instance ${n}: the game did not take the join`);
}

function lobbyLog(n, lines = 40) {
  const file = path.join(at(n).mods, "MJOLNIRLobby", "native", "fireteam.log");
  const all = fs.readFileSync(file, "utf8").split(/\r?\n/);
  return all.slice(-Number(lines) - 1).join("\n");
}

function* walk(dir, rel = "") {
  for (const entry of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
    const r = path.join(rel, entry.name);
    if (entry.isDirectory()) yield* walk(dir, r);
    else if (entry.isFile()) yield r;
  }
}

function sameFile(a, b) {
  try {
    const sa = fs.statSync(a, { bigint: true });
    const sb = fs.statSync(b, { bigint: true });
    return sa.ino === sb.ino && sa.dev === sb.dev;
  } catch {
    return false;
  }
}

function mirror(n) {
  if (!(n >= 1)) throw new Error("mirror needs an instance number of 1 or more (0 is the Steam install)");
  const src = paths().install;
  const dst = installRoot(n);
  const ue4ssRel = path.join("Meteorite", "Binaries", "Win64", "ue4ss");
  let linked = 0, copied = 0, kept = 0, skipped = 0;
  // An earlier overlay's files go first, so this mirror puts the install's
  // own back (a copied file of the same size and newer would be kept).
  const manifest = path.join(dst, ".mj_overlay.json");
  if (fs.existsSync(manifest)) {
    for (const rel of JSON.parse(fs.readFileSync(manifest, "utf8"))) {
      if (fs.existsSync(path.join(dst, rel))) fs.rmSync(path.join(dst, rel));
    }
    fs.rmSync(manifest);
  }
  for (const top of ["Engine", "Meteorite"]) {
    for (const rel of walk(src, top)) {
      const from = path.join(src, rel);
      const to = path.join(dst, rel);
      fs.mkdirSync(path.dirname(to), { recursive: true });
      if (rel.startsWith(ue4ssRel + path.sep)) {
        const inner = rel.slice(ue4ssRel.length + 1);
        if (SKIP_UE4SS.some((re) => re.test(inner))) { skipped++; continue; }
        // A real copy: mods rewrite their files in place, which through a
        // hard link would change instance 0's too.
        const a = fs.statSync(from);
        const b = fs.existsSync(to) ? fs.statSync(to) : null;
        if (b && b.size === a.size && b.mtimeMs >= a.mtimeMs) { kept++; continue; }
        fs.copyFileSync(from, to);
        copied++;
        continue;
      }
      if (sameFile(from, to)) { kept++; continue; }
      if (fs.existsSync(to)) fs.rmSync(to);
      fs.linkSync(from, to);
      linked++;
    }
  }
  fs.mkdirSync(path.join(dst, ue4ssRel, "mjolnir-bridge"), { recursive: true });
  // MJ_OVERLAY: a folder laid out as the install (Meteorite\Content\Paks\...,
  // Meteorite\Binaries\Win64\ue4ss\MJOLNIRMaps\<CODE>\level.json), copied over
  // this copy's files: a release candidate tried in the copies only. A copy,
  // never a write through the hard link, which would change the Steam
  // install's file too. The next mirror without it restores the copy.
  const overlay = process.env.MJ_OVERLAY;
  let overlaid = [];
  if (overlay) {
    for (const rel of walk(overlay)) {
      const to = path.join(dst, rel);
      fs.mkdirSync(path.dirname(to), { recursive: true });
      if (fs.existsSync(to)) fs.rmSync(to);
      fs.copyFileSync(path.join(overlay, rel), to);
      overlaid.push(rel);
    }
    fs.writeFileSync(manifest, JSON.stringify(overlaid, null, 1));
  }
  return `instance ${n}: ${dst}\n  ${linked} linked, ${copied} copied, ${kept} unchanged, ${skipped} run files left out` +
    (overlay ? `, ${overlaid.length} overlaid from ${overlay}` : "");
}

/**
 * The account's settings live in the cloud too, with a concurrency token that
 * each game keeps in Saved\Config\<account>\Halo*GameUserSettings.ini. A game
 * whose token differs from the cloud's signs in but never creates its
 * fireteam lobby (no hosting, no joining), and a game with no such files
 * uploads its settings and moves the cloud's token on, which strands every
 * other install, the Steam one included (seen 2026-11-07, fixed by giving it
 * the cloud's token). So each copy starts with the Steam install's two files,
 * content and token: no copy uploads, and the token stays the Steam game's.
 * The Steam install's files are read, never written.
 */
function shareCloudSettings(n) {
  const from = path.join(process.env.LOCALAPPDATA ?? "", "Meteorite", "Saved", "Config");
  const to = path.join(process.env.LOCALAPPDATA ?? "", "Meteorite", `Saved__mj${n}`, "Config");
  if (!(n >= 1) || !fs.existsSync(from)) return 0;
  let copied = 0;
  for (const user of fs.readdirSync(from, { withFileTypes: true })) {
    if (!user.isDirectory() || !/^\d+$/.test(user.name)) continue;
    for (const name of ["HaloLocalGameUserSettings.ini", "HaloGlobalGameUserSettings.ini"]) {
      const file = path.join(from, user.name, name);
      if (!fs.existsSync(file)) continue;
      fs.mkdirSync(path.join(to, user.name), { recursive: true });
      fs.copyFileSync(file, path.join(to, user.name, name));
      copied++;
    }
  }
  return copied;
}

/**
 * A copy's own display settings: windowed at the asked size and every
 * scalability group at its lowest, so four copies fit one GPU (a fourth at
 * the Steam game's settings died in D3D12 at startup, 2026-11-07). Written to
 * the copy's own Saved folder from the Steam game's file.
 */
function seedUserSettings(n, extra) {
  const from = path.join(process.env.LOCALAPPDATA ?? "", "Meteorite", "Saved", "Config", "Windows", "GameUserSettings.ini");
  const dir = path.join(process.env.LOCALAPPDATA ?? "", "Meteorite", `Saved__mj${n}`, "Config", "Windows");
  if (!(n >= 1) || !fs.existsSync(from)) return;
  const size = (flag, fallback) => Number(extra.find((a) => a.startsWith(flag))?.slice(flag.length) ?? fallback);
  const width = size("-ResX=", 1280), height = size("-ResY=", 720);
  const text = fs.readFileSync(from, "utf8")
    .replace(/^(sg\.(?!ResolutionQuality)\w+)=.*$/gm, "$1=0")
    .replace(/^((?:Last)?(?:Preferred|Confirmed)?FullscreenMode|FullscreenMode)=.*$/gm, "$1=2")
    .replace(/^((?:LastUserConfirmed)?ResolutionSizeX)=.*$/gm, `$1=${width}`)
    .replace(/^((?:LastUserConfirmed)?ResolutionSizeY)=.*$/gm, `$1=${height}`);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "GameUserSettings.ini"), text);
}

function launch(n, extra = []) {
  const root = installRoot(n);
  if (n >= 1) {
    shareCloudSettings(n);
    seedUserSettings(n, extra);
  }
  const win64 = path.join(root, "Meteorite", "Binaries", "Win64");
  const exe = path.join(win64, "HaloCampaignEvolved.exe");
  if (!fs.existsSync(exe)) throw new Error(`no instance ${n} at ${root}: run mirror ${n} first`);
  // The copies' simulations join one another (MJOLNIR_SIM_JOIN=1: each copy
  // gets its own machine identity, docs/multi_instance.md). --separate leaves
  // that out: every copy then follows the host's match in its own simulation.
  const separate = extra.includes("--separate");
  const args = [`-saveddirsuffix=_mj${n}`, ...extra.filter((a) => a !== "--separate" && a !== "--sim-join")];
  const env = { ...process.env, SteamAppId: STEAM_APP_ID, SteamGameId: STEAM_APP_ID, MJOLNIR_INSTANCE: String(n) };
  if (separate) delete env.MJOLNIR_SIM_JOIN;
  else env.MJOLNIR_SIM_JOIN = "1";
  const child = spawn(exe, args, { cwd: win64, detached: true, stdio: "ignore", env });
  child.unref();
  return `instance ${n}: started pid ${child.pid} (${args.join(" ")})`;
}

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..", "..");

/** This checkout's built lobby DLL into copy n (the copies' join code lives there). */
/**
 * This checkout's MJOLNIRLobby into copy n: its built DLL (the copies' join
 * code lives there) and its scripts and mod.json, so a lobby change can be
 * tried on the copies before it ships, and its MJOLNIRHud scripts. The
 * Steam install keeps its own.
 */
function deploy(n) {
  const from = path.join(REPO, "mods", "MJOLNIRLobby");
  const dll = path.join(from, "native", "mjolnir_lobby.dll");
  if (!fs.existsSync(dll)) throw new Error(`${dll} is not built: run native/lobby/build.ps1`);
  const to = path.join(installRoot(n), "Meteorite", "Binaries", "Win64", "ue4ss", "Mods", "MJOLNIRLobby");
  fs.copyFileSync(dll, path.join(to, "native", "mjolnir_lobby.dll"));
  let scripts = 0;
  for (const name of fs.readdirSync(path.join(from, "Scripts"))) {
    if (!name.endsWith(".lua")) continue;
    fs.copyFileSync(path.join(from, "Scripts", name), path.join(to, "Scripts", name));
    scripts++;
  }
  fs.copyFileSync(path.join(from, "mod.json"), path.join(to, "mod.json"));
  // The HUD too: most of what a multiplayer test looks at is drawn by it.
  const hudFrom = path.join(REPO, "mods", "MJOLNIRHud");
  const hudTo = path.join(path.dirname(to), "MJOLNIRHud");
  let hud = 0;
  for (const name of fs.readdirSync(path.join(hudFrom, "Scripts"))) {
    if (!name.endsWith(".lua")) continue;
    fs.copyFileSync(path.join(hudFrom, "Scripts", name), path.join(hudTo, "Scripts", name));
    hud++;
  }
  fs.copyFileSync(path.join(hudFrom, "mod.json"), path.join(hudTo, "mod.json"));
  // The map registry, when this checkout has built one (native/map_registry/
  // build.ps1): it stages each match's variant where the copy's simulation
  // reads it, which a registry from before 2026-11-07 does not.
  const registry = path.join(REPO, "mods", "MJOLNIRLevelLoader", "native", "mjolnir_map_registry.dll");
  let staged = "";
  if (fs.existsSync(registry)) {
    fs.copyFileSync(registry, path.join(path.dirname(to), "MJOLNIRLevelLoader", "native", "mjolnir_map_registry.dll"));
    staged = ", map registry DLL";
  }
  return `instance ${n}: MJOLNIRLobby (DLL, ${scripts} scripts), MJOLNIRHud (${hud} scripts)${staged} from this checkout`;
}

/** Running copies: [{pid, n}] by exe path (n 0 = the Steam install). */
async function running() {
  const { execFileSync } = await import("node:child_process");
  const out = execFileSync("powershell", ["-NoProfile", "-Command",
    "Get-Process HaloCampaignEvolved -ErrorAction SilentlyContinue | ForEach-Object { \"$($_.Id)`t$($_.Path)\" }; exit 0"],
  { encoding: "utf8" });
  return out.split(/\r?\n/).filter(Boolean).map((line) => {
    const [pid, exe] = line.split("\t");
    const m = exe.match(/instances[\\/](\d+)[\\/]/i);
    return { pid: Number(pid), n: m ? Number(m[1]) : 0 };
  });
}

/**
 * The copies' Party endpoint ids (the lobby DLL's peer table reads them to
 * tell same-account joiners apart). A copy that has gone leaves its file, and
 * the next network reuses its ids, so they go before every start and stop:
 * by name, one file per copy number.
 */
function clearEndpointFiles() {
  const dir = path.join(ROOT, "endpoints");
  for (let n = 1; n <= 16; n++) {
    const file = path.join(dir, `${n}.txt`);
    if (fs.existsSync(file)) fs.rmSync(file);
  }
}

async function waitForBridge(n, seconds = 240) {
  at(n);
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    try {
      await bridgeCall("ping", "", 3_000);
      return;
    } catch { await sleep(2000); }
  }
  throw new Error(`instance ${n}: the bridge did not answer within ${seconds}s`);
}

async function waitForLobby(n, seconds = 180) {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    try { return await connection(n); } catch { await sleep(5000); }
  }
  throw new Error(`instance ${n}: no fireteam lobby within ${seconds}s`);
}

// Host or client by the game state's authority: the first player controller
// found can be a stale one from the world before (a host read as "client"
// after a post-game travel).
const PLAYERS_LUA =
  'local pc = FindFirstOf("PlayerController") local w = pc:GetWorld() local n, host = 0, false ' +
  "pcall(function() n = #w.GameState.PlayerArray end) " +
  "pcall(function() host = w.GameState:HasAuthority() end) " +
  'print(w:GetFName():ToString() .. " players " .. n .. (host and " host" or " client"))';

/**
 * Copies 1..count up, signed in, in one lobby: 1 hosts (its menu world made
 * a listen server, which a same-account join never triggers), the rest join
 * it by connection string.
 */
async function up(count, ...extra) {
  count = Number(count);
  if (!(count >= 2 && count <= 8)) throw new Error("up takes 2 to 8 copies");
  const lines = [];
  const already = new Set((await running()).map((r) => r.n));
  if (already.size === 0) clearEndpointFiles();
  for (let n = 1; n <= count; n++) {
    if (already.has(n)) { lines.push(`instance ${n}: already running`); continue; }
    // Refreshed every start: a copy made before a mods update kept the old
    // mods (copies 1 and 2 ran MJOLNIRLobby 0.22.0 after the install had
    // 0.23.0, 2026-11-07). About a second; only changed files are copied.
    lines.push(mirror(n));
    lines.push(deploy(n));
    const window = extra.some((a) => a.startsWith("-Res") || a === "-windowed") ? [] : ["-windowed", "-ResX=1280", "-ResY=720"];
    lines.push(launch(n, [...window, ...extra]));
    // One copy's startup (asset load, shader cache) at a time: four at once
    // crashed one in D3D12.
    await waitForBridge(n);
  }
  for (let n = 1; n <= count; n++) await waitForBridge(n);
  for (let n = 1; n <= count; n++) lines.push(await menu(n));
  for (let n = 1; n <= count; n++) {
    await waitForLobby(n);
    lines.push(`instance ${n}: fireteam lobby up`);
  }
  at(1);
  await bridgeCall("console", "open /Game/Levels/UI/Frontend/Frontend?listen");
  await sleep(12_000);
  await waitForLobby(1);
  lines.push("instance 1: hosting (menu world listening)");
  for (let n = 2; n <= count; n++) {
    lines.push(await join(n, 1));
    await sleep(15_000);
  }
  lines.push(await lua(1, PLAYERS_LUA));
  return lines.join("\n");
}

async function down() {
  const copies = (await running()).filter((r) => r.n >= 1);
  for (const { pid } of copies) process.kill(pid);
  // Gone before this returns: `down; up` launched copy 1 while the old one
  // was still exiting, and the new one quit at once (2026-11-07).
  const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
  for (let i = 0; i < 30 && copies.some((c) => alive(c.pid)); i++) await sleep(500);
  // Even then a copy launched at once quit with no log (twice, 2026-11-07);
  // one launched a few seconds later started.
  if (copies.length) await sleep(5000);
  clearEndpointFiles();
  return copies.length ? `stopped ${copies.map((c) => `instance ${c.n} (pid ${c.pid})`).join(", ")}` : "no copies running";
}

/** Each running copy's world and player count (UE), and its Blam players and machines. */
async function players() {
  const lines = [];
  for (const { pid, n } of await running()) {
    let ue = "?";
    try { ue = await lua(n, PLAYERS_LUA, 10_000); } catch (error) { ue = String(error.message); }
    const { execFileSync } = await import("node:child_process");
    let blam = "?";
    try {
      const out = JSON.parse(execFileSync("python", [path.join(REPO, "tools", "remote", "blam-players.py"), "--json", "--pid", String(pid)], { encoding: "utf8" }));
      const machines = new Set(out.players.map((p) => p.machine)).size;
      blam = `blam players ${out.players.length} on ${machines} machine(s)`;
    } catch { /* not in a game */ }
    lines.push(`instance ${n} (pid ${pid}): ${ue}; ${blam}`);
  }
  return lines.join("\n");
}

const commands = {
  up: (count, ...extra) => up(count, ...extra),
  down: () => down(),
  players: () => players(),
  deploy: (n) => deploy(Number(n)),
  mirror: (n) => mirror(Number(n)),
  launch: (n, ...extra) => launch(Number(n), extra),
  menu: (n) => menu(Number(n)),
  lua: (n, code, timeout) => lua(Number(n), code, Number(timeout ?? 30_000)),
  console: async (n, ...words) => {
    at(Number(n));
    return (await bridgeCall("console", words.join(" "))).body.trim();
  },
  connection: (n) => connection(Number(n)),
  join: (n, host) => join(Number(n), Number(host)),
  log: (n, lines) => lobbyLog(Number(n), lines),
};
const [name, ...args] = process.argv.slice(2);
if (!commands[name]) {
  console.error(`usage: instances.mjs <${Object.keys(commands).join("|")}> ...`);
  process.exit(2);
}
try {
  console.log(await commands[name](...args));
} catch (error) {
  console.error(String(error?.message ?? error));
  process.exit(1);
}
