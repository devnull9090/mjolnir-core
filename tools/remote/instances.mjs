#!/usr/bin/env node
//
// Several copies of the game on this PC, for multiplayer tests without PC 2.
//
//   node tools/remote/instances.mjs mirror <n>       build or refresh instance n's install (n >= 1)
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
  return `instance ${n}: ${dst}\n  ${linked} linked, ${copied} copied, ${kept} unchanged, ${skipped} run files left out`;
}

function launch(n, extra = []) {
  const root = installRoot(n);
  const win64 = path.join(root, "Meteorite", "Binaries", "Win64");
  const exe = path.join(win64, "HaloCampaignEvolved.exe");
  if (!fs.existsSync(exe)) throw new Error(`no instance ${n} at ${root}: run mirror ${n} first`);
  const args = [`-saveddirsuffix=_mj${n}`, ...extra];
  const child = spawn(exe, args, {
    cwd: win64,
    detached: true,
    stdio: "ignore",
    env: { ...process.env, SteamAppId: STEAM_APP_ID, SteamGameId: STEAM_APP_ID, MJOLNIR_INSTANCE: String(n) },
  });
  child.unref();
  return `instance ${n}: started pid ${child.pid} (${args.join(" ")})`;
}

const commands = {
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
