#!/usr/bin/env node
//
// Drive a second PC's game through tools/remote/mjolnir-agent.ps1.
//
//   node tools/remote/remote.mjs status
//   node tools/remote/remote.mjs lua 'print(1 + 1)'        (or lua @file.lua)
//   node tools/remote/remote.mjs console 'stat fps'
//   node tools/remote/remote.mjs launch | quit [--force]
//   node tools/remote/remote.mjs get <root> <path> [local file]
//   node tools/remote/remote.mjs put <local file> <root> <path>
//   node tools/remote/remote.mjs ls <root> [path]
//        roots: ue4ss, saved, agent, paks (game closed to replace a container),
//        launcher (its config folder; agent 5)
//   node tools/remote/remote.mjs install-bridge
//   node tools/remote/remote.mjs deploy-lobby              the lobby's DLL and games.lua
//   node tools/remote/remote.mjs log [lines]               the tail of MJOLNIRLobby's fireteam.log
//   node tools/remote/remote.mjs crash                     the newest crash report's message and stack
//   node tools/remote/remote.mjs input '[{"key":"Enter"}]'  keys and clicks for the game window (agent 2)
//   node tools/remote/remote.mjs signin                    sign in at the title screen with no input
//   node tools/remote/remote.mjs auto state|host CODE mode|join [host]|public on|off
//                                                          MJOLNIRLobby's mjolnir_auto, and its answer
//   node tools/remote/remote.mjs probe load|start|snap|mark|stop|dump|clear
//                                                          the audio-role probe (tools/remote/audio-probe.lua)
//   node tools/remote/remote.mjs stage-agent               copy agent 2 into ue4ss/mjolnir-agent (once,
//                                                          through an agent 1; then run it from there)
//   node tools/remote/remote.mjs deploy-agent              replace this agent's files and restart it
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

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const AGENT_FILES = [
  [path.join(REPO, "tools", "remote", "mjolnir-agent.ps1"), "mjolnir-agent.ps1"],
  [path.join(REPO, "tools", "mcp", "game", "input.ps1"), "input.ps1"],
  [path.join(REPO, "tools", "mcp", "game", "capture.ps1"), "capture.ps1"],
  // The bridge mod beside the agent, so `install-bridge` has something to install.
  [path.join(REPO, "mods", "MJOLNIRBridge", "Scripts", "main.lua"), "MJOLNIRBridge/Scripts/main.lua"],
  [path.join(REPO, "mods", "MJOLNIRBridge", "mod.json"), "MJOLNIRBridge/mod.json"],
];
const PROBE_LUA = path.join(REPO, "tools", "remote", "audio-probe.lua");
export const SIGN_IN_LUA =
  'local t = FindFirstOf("WBP_TitleMenu_C") if t and t:IsValid() then ' +
  "t:BndEvt__WBP_TitleMenu_WBP_MeteoriteStandaloneButtonDefault_K2Node_ComponentBoundEvent_1_CommonButtonBaseClicked__DelegateSignature(nil) " +
  'print("clicked") else print("no title menu") end';
const PROBE_LOG = "mjolnir-bridge/audio-probe.log";

/** mjolnir_auto's answer file as an object, or null (reads the file only: safe while the game travels). */
export async function autoState() {
  try {
    const text = (await call("GET", "/file", { root: "ue4ss", path: "Mods/MJOLNIRLobby/native/auto_state.txt" })).toString("utf8");
    return Object.fromEntries(text.split(/\r?\n/).filter(Boolean).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]));
  } catch {
    return null;
  }
}

export const commands = {
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
  async input(steps) {
    const result = await json("POST", "/input", {}, steps);
    if (!result.ok) throw new Error(result.error ?? result.output ?? "input failed");
    return result.output || "sent";
  },
  /** Run `mjolnir_auto ...` in the game and wait for its answer (a newer `at`). */
  async auto(...words) {
    const before = (await autoState())?.at ?? "0";
    await bridge("console", `mjolnir_auto ${words.join(" ")}`.trim());
    for (let i = 0; i < 40; i++) {
      await sleep(250);
      const state = await autoState();
      if (state && state.at !== before) return JSON.stringify(state);
    }
    throw new Error("mjolnir_auto did not answer (is MJOLNIRLobby loaded?)");
  },
  /**
   * The audio-role probe (tools/remote/audio-probe.lua) in PC 2's game:
   *   probe load                      define AudioProbe in the bridge's sandbox
   *   probe start [label] [seconds]   one sample a second (default 60 s)
   *   probe snap [label]              one sample, printed
   *   probe mark <text>               a marker line in the log
   *   probe stop
   *   probe dump [local file]         the log so far (ue4ss/mjolnir-bridge/audio-probe.log)
   *   probe clear                     empty the log
   */
  async probe(verb = "snap", ...rest) {
    const loaded = async () => {
      const ok = await bridge("lua", "print(AudioProbe and 'yes' or 'no')");
      if (!ok.includes("yes")) await bridge("lua", fs.readFileSync(PROBE_LUA, "utf8"));
    };
    switch (verb) {
      case "load":
        return bridge("lua", fs.readFileSync(PROBE_LUA, "utf8"));
      case "start":
        await loaded();
        return bridge("lua", `print(AudioProbe.start(${JSON.stringify(rest[0] ?? "run")}, ${Number(rest[1] ?? 60)}, 1000))`);
      case "snap":
        await loaded();
        return bridge("lua", `AudioProbe.snapshot(${JSON.stringify(rest[0] ?? "snapshot")}, true)`, 30000);
      case "mark":
        await loaded();
        return bridge("lua", `AudioProbe.mark(${JSON.stringify(rest.join(" "))})`);
      case "stop":
        return bridge("lua", "if AudioProbe then AudioProbe.stop() end print('stopped')");
      case "dump": {
        const bytes = await call("GET", "/file", { root: "ue4ss", path: PROBE_LOG });
        if (!rest[0]) return bytes.toString("utf8");
        fs.writeFileSync(rest[0], bytes);
        return `${rest[0]}: ${bytes.length} bytes`;
      }
      case "clear":
        return JSON.stringify(await json("PUT", "/file", { root: "ue4ss", path: PROBE_LOG }, ""));
      default:
        throw new Error(`probe: unknown verb '${verb}' (load, start, snap, mark, stop, dump, clear)`);
    }
  },
  /**
   * Sign in at the title screen with no input: the title menu's own click
   * event (docs/multiplayer_servers.md). Keys need the game window in the
   * foreground, which Windows refuses while PC 2's desktop is locked.
   * Waits for MJOLNIRLobby's "MULTIPLAYER is on the main menu".
   */
  async signin() {
    const ready = async () => (await call("GET", "/file", { root: "ue4ss", path: "UE4SS.log" })).toString("utf8").includes("MULTIPLAYER is on the main menu");
    for (let i = 0; i < 40; i++) {
      if (await ready()) return "at the main menu";
      await bridge("lua", SIGN_IN_LUA).catch(() => null);
      await sleep(3000);
    }
    throw new Error("PC 2 did not reach the main menu");
  },
  /** The game window as a PNG (agent 4). */
  async shot(local = "pc2.png", max = "1280") {
    const bytes = await call("GET", "/screenshot", { max });
    fs.writeFileSync(local, bytes);
    return `${local}: ${bytes.length} bytes`;
  },
  async "stage-agent"() {
    const out = [];
    for (const [local, name] of AGENT_FILES) out.push(await put(local, "ue4ss", `mjolnir-agent/${name}`));
    const tokenFile = path.join(os.tmpdir(), "mjolnir-agent-token.txt");
    fs.writeFileSync(tokenFile, config().token);
    out.push(await put(tokenFile, "ue4ss", "mjolnir-agent/agent-token.txt"));
    fs.unlinkSync(tokenFile);
    return out.join("\n");
  },
  async "deploy-agent"() {
    const out = [];
    for (const [local, name] of AGENT_FILES) out.push(await put(local, "agent", name));
    out.push(JSON.stringify(await json("POST", "/restart-agent")));
    await sleep(4000);
    out.push(JSON.stringify(await json("GET", "/status")));
    return out.join("\n");
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

// Run as a command unless imported (tools/remote/jip-test.mjs).
if (path.resolve(process.argv[1] ?? "") === path.resolve(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"))) {
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
}
