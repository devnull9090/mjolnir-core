#!/usr/bin/env node
//
// This PC's game, from a shell, through the MCP server's own code
// (tools/mcp/game): the PC 1 half of what remote.mjs does for PC 2.
//
//   node tools/remote/pc1.mjs launch | quit | status
//   node tools/remote/pc1.mjs lua 'print(1)'      (or lua @file.lua)
//   node tools/remote/pc1.mjs console 'mjolnir_auto state'
//   node tools/remote/pc1.mjs input '[{"key":"Enter"}]'
//   node tools/remote/pc1.mjs menu                 sign in (no keys) and wait for the MULTIPLAYER main menu
import fs from "node:fs";
import process from "node:process";
import { callTool, paths } from "../mcp/game/game.mjs";
import { SIGN_IN_LUA } from "./remote.mjs";

const text = (r) => (r.content ?? []).map((c) => c.text).join("\n");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const commands = {
  launch: () => callTool("game_launch", { windowed: false, wait_seconds: 240 }),
  async quit() {
    const r = await callTool("game_quit", { force: true });
    // Wait for the process to be gone, so a launch right after starts afresh.
    for (let i = 0; i < 30; i++) {
      const st = text(await callTool("game_status", {}));
      if (st.includes("not running")) break;
      await sleep(1000);
    }
    return r;
  },
  status: () => callTool("game_status", {}),
  lua: (code, timeout) =>
    callTool("game_lua", { code: code.startsWith("@") ? fs.readFileSync(code.slice(1), "utf8") : code, timeout_ms: Number(timeout ?? 30000) }),
  console: (command) => callTool("game_console", { command }),
  input: (steps) => callTool("game_input", { steps: JSON.parse(steps) }),
  async menu() {
    const log = paths().ue4ssLog;
    const ready = () => fs.existsSync(log) && fs.readFileSync(log, "utf8").includes("MULTIPLAYER is on the main menu");
    for (let i = 0; i < 12 && !ready(); i++) {
      // The title menu's own click event: no keys, so no window focus needed.
      await callTool("game_lua", { code: SIGN_IN_LUA, timeout_ms: 10000 });
      for (let j = 0; j < 8 && !ready(); j++) await sleep(1000);
    }
    return { content: [{ type: "text", text: ready() ? "at the main menu" : "no main menu" }], isError: !ready() };
  },
};
const [name, ...args] = process.argv.slice(2);
if (!commands[name]) {
  console.error(`usage: pc1.mjs <${Object.keys(commands).join("|")}> ...`);
  process.exit(2);
}
const r = await commands[name](...args);
console.log(text(r));
process.exit(r.isError ? 1 : 0);
