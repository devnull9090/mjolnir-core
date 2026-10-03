#!/usr/bin/env node
//
// Drive a second PC's game through tools/remote/mjolnir-agent.ps1.
//
//   node tools/remote/remote.mjs status
//   node tools/remote/remote.mjs lua 'print(1 + 1)'        (or lua @file.lua)
//   node tools/remote/remote.mjs console 'stat fps'
//   node tools/remote/remote.mjs launch | quit [--force]
//   node tools/remote/remote.mjs get <ue4ss|saved> <path> [local file]
//   node tools/remote/remote.mjs put <local file> <ue4ss|saved> <path>
//   node tools/remote/remote.mjs ls <ue4ss|saved> [path]
//   node tools/remote/remote.mjs install-bridge
//   node tools/remote/remote.mjs deploy-lobby              the lobby's DLL and games.lua
//   node tools/remote/remote.mjs log [lines]               the tail of MJOLNIRLobby's fireteam.log
//   node tools/remote/remote.mjs crash                     the newest crash report's message and stack
//
// The agent's address and token come from MJOLNIR_REMOTE / MJOLNIR_REMOTE_TOKEN,
// or from %USERPROFILE%\.mjolnir-remote.json: {"url": "http://host:47820", "token": "..."}.
// Kept out of the repository: the token lets its holder run Lua in that game.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..", "..");

function config() {
  let url = process.env.MJOLNIR_REMOTE;
  let token = process.env.MJOLNIR_REMOTE_TOKEN;
  const file = path.join(os.homedir(), ".mjolnir-remote.json");
  if ((!url || !token) && fs.existsSync(file)) {
    const saved = JSON.parse(fs.readFileSync(file, "utf8"));
    url ??= saved.url;
    token ??= saved.token;
  }
  if (!url || !token) throw new Error(`no agent configured: set MJOLNIR_REMOTE and MJOLNIR_REMOTE_TOKEN, or write ${file}`);
  return { url: url.replace(/\/$/, ""), token };
}

async function call(method, endpoint, query = {}, body) {
  const { url, token } = config();
  const search = new URLSearchParams(query).toString();
  const response = await fetch(`${url}${endpoint}${search ? "?" + search : ""}`, {
    method,
    headers: { "X-Mjolnir-Token": token },
    body,
  });
  const bytes = Buffer.from(await response.arrayBuffer());
  if (!response.ok) throw new Error(`${response.status}: ${bytes.toString("utf8")}`);
  return bytes;
}

const json = async (...args) => JSON.parse((await call(...args)).toString("utf8"));

async function bridge(op, body, timeout) {
  const result = await json("POST", "/bridge", { op, timeout: timeout ?? 15000 }, body);
  if (!result.ok) throw new Error(result.body);
  return result.body;
}

async function put(local, root, remote) {
  const result = await json("PUT", "/file", { root, path: remote }, fs.readFileSync(local));
  return `${remote}: ${result.note} (${result.bytes} bytes)`;
}

const commands = {
  async status() {
    return JSON.stringify(await json("GET", "/status"), null, 1);
  },
  async lua(code, timeout) {
    if (code?.startsWith("@")) code = fs.readFileSync(code.slice(1), "utf8");
    return bridge("lua", code, timeout && Number(timeout));
  },
  async console(command) {
    return bridge("console", command);
  },
  async launch() {
    return JSON.stringify(await json("POST", "/launch"));
  },
  async quit(flag) {
    return JSON.stringify(await json("POST", "/quit", flag === "--force" ? { force: "1" } : {}));
  },
  async get(root, remote, local) {
    const bytes = await call("GET", "/file", { root, path: remote });
    if (!local) return bytes.toString("utf8");
    fs.writeFileSync(local, bytes);
    return `${local}: ${bytes.length} bytes`;
  },
  put,
  async ls(root, remote = "") {
    const { items } = await json("GET", "/list", { root, path: remote });
    return items.map((i) => `${i.modified}  ${i.dir ? "<dir>" : String(i.size).padStart(10)}  ${i.name}`).join("\n");
  },
  async "install-bridge"() {
    return JSON.stringify(await json("POST", "/install-bridge"));
  },
  async "deploy-lobby"() {
    const lobby = path.join(REPO, "mods", "MJOLNIRLobby");
    return [
      await put(path.join(lobby, "native", "mjolnir_lobby.dll"), "ue4ss", "Mods/MJOLNIRLobby/native/mjolnir_lobby.dll"),
      await put(path.join(lobby, "Scripts", "games.lua"), "ue4ss", "Mods/MJOLNIRLobby/Scripts/games.lua"),
    ].join("\n");
  },
  async log(lines = "80") {
    const text = (await call("GET", "/file", { root: "ue4ss", path: "Mods/MJOLNIRLobby/native/fireteam.log" })).toString("utf8");
    return text.split("\n").filter((l) => !/ (search |lobby |create (search |lobby ))?property /.test(l)).slice(-Number(lines)).join("\n");
  },
  async crash() {
    const { items } = await json("GET", "/list", { root: "saved", path: "Crashes" });
    const newest = items.find((i) => i.dir);
    if (!newest) return "no crash reports";
    const xml = (await call("GET", "/file", { root: "saved", path: `Crashes/${newest.name}/CrashContext.runtime-xml` })).toString("utf8");
    const message = xml.match(/<ErrorMessage>([\s\S]*?)<\/ErrorMessage>/)?.[1] ?? "?";
    const stack = xml.match(/<PCallStack>([\s\S]*?)<\/PCallStack>/)?.[1]?.trim() ?? "";
    return `${newest.name} (${newest.modified})\n${message}\n${stack}`;
  },
};

const [name, ...args] = process.argv.slice(2);
if (!commands[name]) {
  console.error(`usage: remote.mjs <${Object.keys(commands).join("|")}> ...`);
  process.exit(2);
}
commands[name](...args).then(
  (out) => console.log(out),
  (error) => {
    console.error(String(error.message ?? error));
    process.exit(1);
  }
);
