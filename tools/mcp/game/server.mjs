#!/usr/bin/env node
//
// MCP transport for the game tools in game.mjs.
//
// Newline-delimited JSON-RPC on stdio, which is what the MCP stdio transport
// is. stdout carries protocol traffic only -- a stray console.log here shows up
// as a parse error at the other end, so diagnostics go to stderr.

import { TOOLS, callTool, INSTALL, log } from "./game.mjs";

const SERVER_NAME = "mjolnir-game";
const SERVER_VERSION = "0.1.0";
const DEFAULT_PROTOCOL = "2025-06-18";

function send(message) {
  process.stdout.write(JSON.stringify(message) + "\n");
}

async function handle(request) {
  const { method, params } = request;

  if (method === "initialize") {
    return {
      protocolVersion: params?.protocolVersion ?? DEFAULT_PROTOCOL,
      capabilities: { tools: {} },
      serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
    };
  }
  if (method === "ping") return {};
  if (method === "tools/list") {
    return {
      tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
    };
  }
  if (method === "tools/call") {
    return await callTool(params?.name, params?.arguments ?? {});
  }

  const error = new Error(`unknown method: ${method}`);
  error.code = -32601;
  throw error;
}

let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let newline;
  while ((newline = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, newline).trim();
    buffer = buffer.slice(newline + 1);
    if (!line) continue;

    let request;
    try {
      request = JSON.parse(line);
    } catch (error) {
      log("dropped unparseable line:", String(error));
      continue;
    }

    handle(request).then(
      (result) => {
        if (request.id !== undefined) send({ jsonrpc: "2.0", id: request.id, result });
      },
      (error) => {
        if (request.id === undefined) return;   // a notification has nowhere to fail to
        send({
          jsonrpc: "2.0",
          id: request.id,
          error: { code: error.code ?? -32603, message: String(error.message ?? error) },
        });
      }
    );
  }
});

log(INSTALL ? `install: ${INSTALL}` : "install not found; set MJOLNIR_GAME_DIR");
