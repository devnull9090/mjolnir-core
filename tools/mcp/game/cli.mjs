#!/usr/bin/env node
//
// Shell access to the same tools the MCP server serves.
//
// Two reasons this exists rather than being MCP-only. An MCP server is only
// reachable from a client that has loaded it, which makes it awkward to test
// and impossible to use from a script. And when something does not work, being
// able to run one tool by hand and read the raw output is the difference
// between debugging the game and debugging the transport.
//
//   node tools/mcp/game/cli.mjs status
//   node tools/mcp/game/cli.mjs launch
//   node tools/mcp/game/cli.mjs lua "print(mj.name(mj.pawn()))"
//   node tools/mcp/game/cli.mjs lua --timeout=60000 < scan.lua
//   node tools/mcp/game/cli.mjs console "stat fps"
//   node tools/mcp/game/cli.mjs travel a30
//   node tools/mcp/game/cli.mjs shot out.png
//   node tools/mcp/game/cli.mjs input '[{"key":"Enter"}]'
//   node tools/mcp/game/cli.mjs log 40
//
// Anything not listed is passed straight through: `cli.mjs game_lua '{"code":"..."}'`.

import fs from "node:fs";
import process from "node:process";
import { TOOLS, callTool } from "./game.mjs";

const argv = process.argv.slice(2);

// A scan worth writing is usually longer than a comfortable command line, and
// slower than the default timeout, so both have to be reachable from a shell.
const timeoutFlag = argv.findIndex((argument) => argument.startsWith("--timeout="));
const timeout = timeoutFlag >= 0 ? Number(argv.splice(timeoutFlag, 1)[0].split("=")[1]) : undefined;

const [command, ...rest] = argv;
const stdin = process.stdin.isTTY ? "" : fs.readFileSync(0, "utf8");

/** Map the friendly forms above onto a tool name and its arguments. */
function resolve(name, args) {
  switch (name) {
    case "status":  return ["game_status", {}];
    case "launch":  return ["game_launch", args[0] ? JSON.parse(args[0]) : {}];
    case "quit":    return ["game_quit", {}];
    case "lua":     return ["game_lua", { code: args.join(" ") || stdin, timeout_ms: timeout }];
    case "console": return ["game_console", { command: args.join(" ") }];
    case "travel":  return ["game_travel", { map: args[0] }];
    case "shot":
    case "screenshot": return ["game_screenshot", {}];
    case "input":   return ["game_input", { steps: JSON.parse(args[0]) }];
    case "log":     return ["game_log", { lines: Number(args[0]) || 60, filter: args[1] }];
    default:        return [name, args[0] ? JSON.parse(args[0]) : {}];
  }
}

if (!command || command === "--help" || command === "-h") {
  console.log("tools:\n" + TOOLS.map((tool) => `  ${tool.name}`).join("\n"));
  console.log("\nshorthands: status launch quit lua console travel shot input log");
  process.exit(0);
}

const [tool, args] = resolve(command, rest);
const result = await callTool(tool, args);

// An image has nowhere to go in a terminal, so write it out and say where.
let exitCode = result.isError ? 1 : 0;
for (const part of result.content ?? []) {
  if (part.type === "text") {
    console.log(part.text);
  } else if (part.type === "image") {
    const out = (command === "shot" || command === "screenshot") && rest[0] ? rest[0] : "shot.png";
    fs.writeFileSync(out, Buffer.from(part.data, "base64"));
    console.log(`image written to ${out}`);
  }
}
process.exit(exitCode);
