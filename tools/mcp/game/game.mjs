//
// MJOLNIR game control
//
// Exposes the running game as a set of tools: launch it, run console commands,
// evaluate Lua inside it, send input, and take screenshots. The point is that
// an experiment which used to be "load the game, alt-tab, type this, read that
// off the screen, tell me what it said" becomes something that can be done
// without a person in the loop for every step.
//
// Three transports, because no single one reaches everything:
//
//   the bridge mod   in-process Lua and console commands, over files in
//                    ue4ss/mjolnir-bridge (see mods/MJOLNIRBridge)
//   capture.ps1      screenshots of the game window
//   input.ps1        keyboard and mouse, for menus the console cannot reach
//
// Prefer the bridge. A value read by reflection is exact; a value read off a
// screenshot is a guess about pixels.
//
// This module is the tools themselves. `server.mjs` serves them over MCP and
// `cli.mjs` runs them from a shell; both are thin, so anything either one can
// do, the other can too.

import { spawn, execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const execFileAsync = promisify(execFile);

// Steam's own appmanifest, and apps/launcher, agree on this. The store page id
// in the README is a different app.
const STEAM_APP_ID = "2806050";
const EXE_NAME = "HaloCampaignEvolved.exe";
const PROCESS_NAME = "HaloCampaignEvolved";

const HERE = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const CAPTURE_SCRIPT = path.join(HERE, "capture.ps1");
const INPUT_SCRIPT = path.join(HERE, "input.ps1");
const SCRATCH = path.join(HERE, ".captures");

const log = (...args) => console.error("[mjolnir-game]", ...args);

// ─────────────────────────────────────────────────────────────────────────────
// Where the game lives
// ─────────────────────────────────────────────────────────────────────────────

/** Steam library roots, from the library index Steam maintains for itself. */
function steamLibraries() {
  const roots = [
    "C:\\Program Files (x86)\\Steam",
    "C:\\Program Files\\Steam",
    path.join(process.env.LOCALAPPDATA ?? "", "Steam"),
  ];
  const found = new Set();
  for (const root of roots) {
    if (!root) continue;
    if (fs.existsSync(path.join(root, "steamapps"))) found.add(root);
    const index = path.join(root, "steamapps", "libraryfolders.vdf");
    if (!fs.existsSync(index)) continue;
    try {
      const text = fs.readFileSync(index, "utf8");
      for (const match of text.matchAll(/"path"\s+"([^"]+)"/g)) {
        found.add(match[1].replace(/\\\\/g, "\\"));
      }
    } catch (error) {
      log("could not read", index, String(error));
    }
  }
  return [...found];
}

function findInstall() {
  const candidates = [];
  if (process.env.MJOLNIR_GAME_DIR) candidates.push(process.env.MJOLNIR_GAME_DIR);
  for (const library of steamLibraries()) {
    candidates.push(path.join(library, "steamapps", "common", "Halo Campaign Evolved"));
  }
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, "Meteorite", "Binaries", "Win64", EXE_NAME))) {
      return candidate;
    }
  }
  return null;
}

const INSTALL = findInstall();

function paths() {
  if (!INSTALL) {
    throw new Error(
      "Halo Campaign Evolved was not found. Set MJOLNIR_GAME_DIR to the folder " +
        "that contains Meteorite\\Binaries\\Win64\\" + EXE_NAME + "."
    );
  }
  const win64 = path.join(INSTALL, "Meteorite", "Binaries", "Win64");
  const ue4ss = path.join(win64, "ue4ss");
  // Anything the game writes goes under LOCALAPPDATA, not the install -- the
  // install lives in Program Files and is not writable by the game.
  const saved = path.join(process.env.LOCALAPPDATA ?? "", "Meteorite", "Saved");
  return {
    install: INSTALL,
    exe: path.join(win64, EXE_NAME),
    win64,
    ue4ss,
    mods: path.join(ue4ss, "Mods"),
    modsTxt: path.join(ue4ss, "Mods", "mods.txt"),
    bridgeMod: path.join(ue4ss, "Mods", "MJOLNIRBridge", "Scripts", "main.lua"),
    bridge: path.join(ue4ss, "mjolnir-bridge"),
    ue4ssLog: path.join(ue4ss, "UE4SS.log"),
    saved,
    userSettings: path.join(saved, "Config", "Windows", "GameUserSettings.ini"),
    screenshots: path.join(saved, "Screenshots", "WindowsClient"),
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Display mode
// ─────────────────────────────────────────────────────────────────────────────

// UE's EWindowMode, as GameUserSettings.ini stores it.
const WINDOW_MODES = { fullscreen: 0, borderless: 1, windowed: 2 };

/**
 * Force a display mode by editing GameUserSettings.ini.
 *
 * The alternative is `-windowed -ResX=...` on the command line, but Steam's
 * rungameid URL is not a reliable way to pass arguments and launching the exe
 * directly sidesteps Steam's DRM. The ini is the one lever that works whatever
 * route the game starts by.
 *
 * The original is copied aside once, on the first change, so the user's own
 * settings survive however many times this runs.
 */
function setDisplayMode(mode, width, height) {
  const file = paths().userSettings;
  if (!fs.existsSync(file)) throw new Error(`no GameUserSettings.ini at ${file} — run the game once first.`);

  const backup = file + ".mjolnir-backup";
  if (!fs.existsSync(backup)) fs.copyFileSync(file, backup);

  const value = WINDOW_MODES[mode];
  if (value === undefined) throw new Error(`unknown display mode '${mode}'`);

  const replacements = {
    FullscreenMode: value,
    PreferredFullscreenMode: value,
    LastConfirmedFullscreenMode: value,
  };
  if (width && height) {
    Object.assign(replacements, {
      ResolutionSizeX: width,
      ResolutionSizeY: height,
      LastUserConfirmedResolutionSizeX: width,
      LastUserConfirmedResolutionSizeY: height,
    });
  }

  let text = fs.readFileSync(file, "utf8");
  const changed = [];
  for (const [key, replacement] of Object.entries(replacements)) {
    const pattern = new RegExp(`^${key}=.*$`, "m");
    if (pattern.test(text)) {
      text = text.replace(pattern, `${key}=${replacement}`);
      changed.push(`${key}=${replacement}`);
    }
  }
  fs.writeFileSync(file, text);
  return { file, backup, changed };
}

function restoreDisplayMode() {
  const file = paths().userSettings;
  const backup = file + ".mjolnir-backup";
  if (!fs.existsSync(backup)) throw new Error("nothing to restore: no backup was ever taken.");
  fs.copyFileSync(backup, file);
  return { file, backup };
}

// ─────────────────────────────────────────────────────────────────────────────
// Bridge protocol — the mirror of mods/MJOLNIRBridge/Scripts/main.lua
// ─────────────────────────────────────────────────────────────────────────────

function encodeMessage(headers, body) {
  const payload = Buffer.from(body ?? "", "utf8");
  const head = ["mjolnir-bridge 1"];
  for (const [key, value] of Object.entries(headers)) head.push(`${key} ${value}`);
  head.push(`bytes ${payload.length}`, "--", "");
  return Buffer.concat([Buffer.from(head.join("\n"), "utf8"), payload]);
}

/** Decode a message, or null if the writer has not finished writing it. */
function decodeMessage(buffer) {
  if (!buffer) return null;
  const separator = buffer.indexOf("\n--\n");
  if (separator < 0) return null;
  const headers = {};
  for (const line of buffer.subarray(0, separator).toString("utf8").split("\n")) {
    const match = line.match(/^(\S+)\s*(.*)$/);
    if (match) headers[match[1]] = match[2];
  }
  const body = buffer.subarray(separator + 4);
  const want = Number(headers.bytes ?? 0);
  if (body.length < want) return null;
  return { headers, body: body.subarray(0, want).toString("utf8") };
}

function readMessage(file) {
  try {
    return decodeMessage(fs.readFileSync(file));
  } catch {
    return null;   // missing, or being rewritten right now
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

let nextId = Date.now() % 1_000_000;

/** Read the heartbeat the mod writes about once a second. */
function bridgeStatus() {
  const message = readMessage(paths().bridge + path.sep + "status.txt");
  if (!message) return null;
  const fields = {};
  for (const line of message.body.split("\n")) {
    const match = line.match(/^(\S+)\s+(.*)$/);
    if (match) fields[match[1]] = match[2];
  }
  return fields;
}

async function bridgeCall(op, body, timeoutMs = 15_000) {
  const { bridge } = paths();
  fs.mkdirSync(bridge, { recursive: true });

  const requestFile = path.join(bridge, "request.txt");
  const responseFile = path.join(bridge, "response.txt");
  const id = ++nextId;

  try { fs.unlinkSync(responseFile); } catch { /* first call of the session */ }

  const temporary = path.join(bridge, `request.${id}.tmp`);
  fs.writeFileSync(temporary, encodeMessage({ id, op }, body));
  fs.renameSync(temporary, requestFile);

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const message = readMessage(responseFile);
    if (message && Number(message.headers.id) === id) {
      return { ok: message.headers.ok === "1", body: message.body };
    }
    await sleep(50);
  }

  const status = bridgeStatus();
  const age = status ? Math.round(Date.now() / 1000 - Number(status.now)) : null;
  throw new Error(
    `the bridge did not answer within ${timeoutMs} ms. ` +
      (status
        ? `Its last heartbeat was ${age}s ago (world ${status.world}). ` +
          "A game thread busy loading a level can outlast the timeout; retry with a larger one."
        : "It has never written a heartbeat, so the mod is probably not loaded — " +
          "run scripts/install-bridge.ps1 and restart the game.")
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Process control
// ─────────────────────────────────────────────────────────────────────────────

async function gameProcess() {
  try {
    const { stdout } = await execFileAsync("tasklist", [
      "/FI", `IMAGENAME eq ${EXE_NAME}`, "/NH", "/FO", "CSV",
    ]);
    const match = stdout.match(/^"([^"]+)","(\d+)"/m);
    return match ? { name: match[1], pid: Number(match[2]) } : null;
  } catch {
    return null;
  }
}

async function powershell(script, args) {
  const { stdout, stderr } = await execFileAsync(
    "powershell",
    ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script, ...args],
    { maxBuffer: 64 * 1024 * 1024 }
  );
  const line = stdout.trim().split("\n").filter(Boolean).pop();
  try {
    return JSON.parse(line);
  } catch {
    throw new Error(`${path.basename(script)} returned unparseable output: ${stdout.trim()}\n${stderr.trim()}`);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tools
// ─────────────────────────────────────────────────────────────────────────────

// Verified CU3 root world packages, same list the multiplayer mod carries.
const MAPS = {
  a15: "/Game/Levels/Halo1/Solo/A15/A15",
  a30: "/Game/Levels/Halo1/Solo/A30/A30",
  a50: "/Game/Levels/Halo1/Solo/A50/A50",
  b30: "/Game/Levels/Halo1/Solo/B30/B30",
  b40: "/Game/Levels/Halo1/Solo/B40/B40",
  c10: "/Game/Levels/Halo1/Solo/C10/C10",
  c20: "/Game/Levels/Halo1/Solo/C20/C20",
  c45: "/Game/Levels/Halo1/Solo/C45/C45",
  d20: "/Game/Levels/Halo1/Solo/D20/D20",
  d40: "/Game/Levels/Halo1/Solo/D40/D40",
  e10: "/Game/Levels/Halo1/Solo/Extra/E10/E10",
  e20: "/Game/Levels/Halo1/Solo/Extra/E20/E20",
  e30: "/Game/Levels/Halo1/Solo/Extra/E30/E30",
};

const text = (body) => ({ content: [{ type: "text", text: body }] });

export const TOOLS = [];
const define = (tool) => TOOLS.push(tool);

define({
  name: "game_status",
  description:
    "Where the game is installed, whether it is running, and whether the in-game bridge is answering. " +
    "Start here: every other tool depends on some part of this being true.",
  inputSchema: { type: "object", properties: {} },
  async run() {
    const p = paths();
    const running = await gameProcess();
    const status = bridgeStatus();
    const lines = [
      `install      ${p.install}`,
      `process      ${running ? `running, pid ${running.pid}` : "not running"}`,
      `bridge mod   ${fs.existsSync(p.bridgeMod) ? "installed" : "NOT INSTALLED — run scripts/install-bridge.ps1"}`,
    ];

    if (status) {
      const now = Math.floor(Date.now() / 1000);
      lines.push(
        `heartbeat    ${now - Number(status.now)}s ago`,
        `game thread  ${Number(status.now) - Number(status.refreshed)}s behind the poll thread`,
        `controller   ${status.controller}`,
        `world        ${status.world}`,
        `pawn         ${status.pawn}`
      );
    } else {
      lines.push("heartbeat    none — the bridge has not run in this install");
    }

    if (running) {
      try {
        const ping = await bridgeCall("ping", "", 5_000);
        lines.push("", "ping:", ping.body);
      } catch (error) {
        lines.push("", `ping failed: ${error.message}`);
      }
    }
    return text(lines.join("\n"));
  },
});

define({
  name: "game_launch",
  description:
    "Start the game and wait until the in-game bridge answers. Launches windowed by default, " +
    "because exclusive fullscreen cannot be screenshotted.",
  inputSchema: {
    type: "object",
    properties: {
      windowed: { type: "boolean", description: "Windowed mode (default true)." },
      width: { type: "number", description: "Window width, default 1280." },
      height: { type: "number", description: "Window height, default 720." },
      wait_seconds: { type: "number", description: "How long to wait for the bridge, default 180." },
      via: { type: "string", enum: ["steam", "exe"], description: "Launch route, default steam." },
    },
  },
  async run(args) {
    const p = paths();
    const existing = await gameProcess();
    if (existing) return text(`already running, pid ${existing.pid}. Use game_quit first to restart it.`);

    const notes = [];
    const windowed = args.windowed !== false;
    if (windowed) {
      const display = setDisplayMode("windowed", args.width ?? 1280, args.height ?? 720);
      notes.push(`display: ${display.changed.join(" ")} (original saved to ${path.basename(display.backup)})`);
    }

    const via = args.via ?? "steam";
    if (via === "steam") {
      spawn("cmd", ["/c", "start", "", `steam://rungameid/${STEAM_APP_ID}`], {
        detached: true,
        stdio: "ignore",
      }).unref();
    } else {
      spawn(p.exe, [], { cwd: p.win64, detached: true, stdio: "ignore" }).unref();
    }

    const waitSeconds = args.wait_seconds ?? 240;
    const deadline = Date.now() + waitSeconds * 1000;
    let seen = null;
    while (Date.now() < deadline) {
      await sleep(2000);
      seen ??= await gameProcess();
      if (seen) {
        try {
          const ping = await bridgeCall("ping", "", 3_000);
          notes.push(`launched via ${via}, pid ${seen.pid}, bridge answering.`, "", ping.body);
          return text(notes.join("\n"));
        } catch { /* mods load a few seconds after the process appears */ }
      }
    }

    notes.push(
      seen
        ? `the process started (pid ${seen.pid}) but the bridge did not answer within ${waitSeconds}s. ` +
            `Check ${p.ue4ssLog} — UE4SS may not have injected, or MJOLNIRBridge may not be enabled in mods.txt.`
        : `no ${EXE_NAME} process appeared within ${waitSeconds}s. Steam may be showing a prompt, ` +
            "or the app id may be wrong."
    );
    return text(notes.join("\n"));
  },
});

define({
  name: "game_display",
  description:
    "Set the game's window mode, or put the user's own settings back. Windowed is what screenshots need: " +
    "borderless and exclusive fullscreen both take over the display. Takes effect on the next launch.",
  inputSchema: {
    type: "object",
    properties: {
      mode: {
        type: "string",
        enum: ["windowed", "borderless", "fullscreen", "restore"],
        description: "'restore' puts back the settings as they were before the first change.",
      },
      width: { type: "number" },
      height: { type: "number" },
    },
    required: ["mode"],
  },
  async run(args) {
    if (args.mode === "restore") {
      const { file } = restoreDisplayMode();
      return text(`restored ${file} from the backup.`);
    }
    const result = setDisplayMode(args.mode, args.width, args.height);
    return text(
      `${result.file}\n${result.changed.join("\n")}\n\n` +
        `original saved to ${path.basename(result.backup)}; takes effect on the next launch.`
    );
  },
});

define({
  name: "game_quit",
  description: "Close the game.",
  inputSchema: {
    type: "object",
    properties: { force: { type: "boolean", description: "Kill rather than asking it to close." } },
  },
  async run(args) {
    const running = await gameProcess();
    if (!running) return text("not running.");
    const flags = ["/PID", String(running.pid)];
    if (args.force) flags.push("/F");
    await execFileAsync("taskkill", flags).catch(() => execFileAsync("taskkill", [...flags, "/F"]));
    return text(`closed pid ${running.pid}.`);
  },
});

define({
  name: "game_console",
  description:
    "Run a UE console command through the local PlayerController — 'stat fps', 'open <level>', cheats. " +
    "Needs a live PlayerController, so it fails at the main menu.",
  inputSchema: {
    type: "object",
    properties: { command: { type: "string", description: "The command, without a leading tilde." } },
    required: ["command"],
  },
  async run(args) {
    const result = await bridgeCall("console", args.command);
    return { content: [{ type: "text", text: result.body }], isError: !result.ok };
  },
});

define({
  name: "game_lua",
  description:
    "Evaluate Lua on the game thread and return what it printed. This is the precise way to read game " +
    "state — ammo, health, tag properties — because it reads the objects rather than the screen. " +
    "Helpers: mj.pc(), mj.pawn(), mj.world(), mj.find(class), mj.props(obj), mj.name(obj), mj.console(cmd). " +
    "UE4SS reflection is available: FindAllOf, StaticFindObject, FName. The sandbox persists between calls, " +
    "so a helper defined once stays defined.",
  inputSchema: {
    type: "object",
    properties: {
      code: { type: "string", description: "Lua source. Use print() for output; a returned value is shown too." },
      timeout_ms: { type: "number", description: "Default 15000. Raise it if a level is loading." },
    },
    required: ["code"],
  },
  async run(args) {
    const result = await bridgeCall("lua", args.code, args.timeout_ms ?? 15_000);
    return { content: [{ type: "text", text: result.body || "(no output)" }], isError: !result.ok };
  },
});

define({
  name: "game_travel",
  description:
    "Load a level with `open`. Takes a short key (a30, b30, ...) or a full /Game/... package path. " +
    "WARNING: doing this from the frontend menu crashes the game — verified 2026-07-27, access violation " +
    "a couple of minutes into the load. `open` skips the mission setup the campaign flow performs, so use " +
    "game_input to start a mission through the menus and keep this for level-to-level travel once in game.",
  inputSchema: {
    type: "object",
    properties: {
      map: { type: "string", description: "Short key or full package path." },
      listen: { type: "boolean", description: "Append ?listen to host." },
      wait: { type: "boolean", description: "Wait for a PlayerController to exist afterwards (default true)." },
      force: { type: "boolean", description: "Travel from the frontend anyway, knowing it has crashed before." },
    },
    required: ["map"],
  },
  async run(args) {
    const status = bridgeStatus();
    if (status?.world?.includes("Frontend") && !args.force) {
      return {
        content: [{
          type: "text",
          text: "refusing to `open` from the frontend menu: that crashed the game on 2026-07-27. " +
            "Start a mission through the menus with game_input first. Pass force:true to try anyway.",
        }],
        isError: true,
      };
    }

    const key = args.map.toLowerCase();
    let url = MAPS[key] ?? (args.map.startsWith("/") ? args.map : null);
    if (!url) {
      return {
        content: [{ type: "text", text: `unknown map '${args.map}'. Known keys: ${Object.keys(MAPS).join(", ")}` }],
        isError: true,
      };
    }
    if (args.listen) url += "?listen";

    const result = await bridgeCall("console", `open ${url}`);
    if (!result.ok) return { content: [{ type: "text", text: result.body }], isError: true };
    if (args.wait === false) return text(result.body);

    // A travel tears down the world and builds a new one; the game thread is
    // unresponsive throughout, so poll the heartbeat rather than the bridge.
    const deadline = Date.now() + 180_000;
    await sleep(3000);
    while (Date.now() < deadline) {
      const status = bridgeStatus();
      if (status && status.controller === "yes" && status.world.toLowerCase().includes(key)) {
        return text(`${result.body}\n\narrived: world ${status.world}, pawn ${status.pawn}`);
      }
      await sleep(2000);
    }
    return text(`${result.body}\n\nstill loading after 180s; check game_status.`);
  },
});

define({
  name: "game_screenshot",
  description:
    "Photograph the game window. Use it to see what is on screen — menus, HUD, whether a weapon looks right. " +
    "For numbers, prefer game_lua: reflection is exact where pixels are not.",
  inputSchema: {
    type: "object",
    properties: {
      max_width: {
        type: "number",
        description:
          "Downscale to this width, default 800. Cost scales with area, so doubling the width " +
          "quadruples the tokens; raise it only when reading small text off the HUD.",
      },
      foreground: { type: "boolean", description: "Force the focus-stealing capture path." },
    },
  },
  async run(args) {
    const running = await gameProcess();
    if (!running) return { content: [{ type: "text", text: "the game is not running." }], isError: true };

    fs.mkdirSync(SCRATCH, { recursive: true });
    const file = path.join(SCRATCH, `shot-${Date.now()}.png`);
    const flags = ["-ProcessName", PROCESS_NAME, "-OutFile", file, "-MaxWidth", String(args.max_width ?? 800)];
    if (args.foreground) flags.push("-ForceForeground");

    const result = await powershell(CAPTURE_SCRIPT, flags);
    if (!result.ok) return { content: [{ type: "text", text: `capture failed: ${result.error}` }], isError: true };

    const note = `${result.method}, ${result.source} -> ${result.width}x${result.height}` +
      (result.blank ? " — the frame came back blank, which usually means exclusive fullscreen; relaunch windowed" : "");
    return {
      content: [
        { type: "text", text: note },
        { type: "image", data: fs.readFileSync(result.path).toString("base64"), mimeType: "image/png" },
      ],
    };
  },
});

define({
  name: "game_input",
  description:
    "Send keyboard and mouse input to the game window, for menus and movement the console cannot reach. " +
    "Steals focus while it runs. Steps: {key:'Enter'}, {key:'W',hold:800}, {key:'Shift',down:true}, " +
    "{mouse:'left',hold:60}, {move:[dx,dy]}, {wait:500}.",
  inputSchema: {
    type: "object",
    properties: {
      steps: {
        type: "array",
        description: "Ordered input steps.",
        items: { type: "object" },
      },
      gap_ms: { type: "number", description: "Pause between steps, default 60." },
    },
    required: ["steps"],
  },
  async run(args) {
    const running = await gameProcess();
    if (!running) return { content: [{ type: "text", text: "the game is not running." }], isError: true };
    const flags = ["-ProcessName", PROCESS_NAME, "-Steps", JSON.stringify(args.steps)];
    if (args.gap_ms !== undefined) flags.push("-GapMs", String(args.gap_ms));
    const result = await powershell(INPUT_SCRIPT, flags);
    if (!result.ok) return { content: [{ type: "text", text: `input failed: ${result.error}` }], isError: true };
    return text(
      (result.focused ? "" : "warning: the game window did not take focus, so the input may have gone elsewhere.\n") +
        result.steps.join("\n")
    );
  },
});

define({
  name: "game_log",
  description: "Tail UE4SS.log — mod load failures, Lua errors, and anything a mod printed.",
  inputSchema: {
    type: "object",
    properties: {
      lines: { type: "number", description: "How many lines from the end, default 60." },
      filter: { type: "string", description: "Only lines containing this substring." },
    },
  },
  async run(args) {
    const file = paths().ue4ssLog;
    if (!fs.existsSync(file)) return { content: [{ type: "text", text: `no log at ${file}` }], isError: true };
    let lines = fs.readFileSync(file, "utf8").split(/\r?\n/);
    if (args.filter) lines = lines.filter((line) => line.includes(args.filter));
    return text(lines.slice(-(args.lines ?? 60)).join("\n") || "(nothing matched)");
  },
});

/** Run a tool by name. Errors come back as a result, not a throw. */
export async function callTool(name, args = {}) {
  const tool = TOOLS.find((candidate) => candidate.name === name);
  if (!tool) {
    return {
      content: [{ type: "text", text: `unknown tool '${name}'. Known: ${TOOLS.map((t) => t.name).join(", ")}` }],
      isError: true,
    };
  }
  try {
    return await tool.run(args);
  } catch (error) {
    // A failed call is a result to read and react to, not a stack trace.
    return { content: [{ type: "text", text: String(error.message ?? error) }], isError: true };
  }
}

export { INSTALL, paths, bridgeCall, bridgeStatus, gameProcess, log };
