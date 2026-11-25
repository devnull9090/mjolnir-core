// node --test tools/mcp/game/test_pipe_call.mjs
// The bridge's pipe client (pipeCall in game.mjs) against a real local
// server: a named pipe on Windows, a Unix socket elsewhere. No game.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { pipeCall } from './game.mjs';

let serial = 0;
function address() {
  serial++;
  return process.platform === 'win32'
    ? `\\\\.\\pipe\\mjolnir-bridge-test-${process.pid}-${serial}`
    : path.join(os.tmpdir(), `mjolnir-bridge-test-${process.pid}-${serial}.sock`);
}

function message(headers, body) {
  const payload = Buffer.from(body, 'utf8');
  const head = ['mjolnir-bridge 1', ...Object.entries(headers).map(([k, v]) => `${k} ${v}`),
    `bytes ${payload.length}`, '--', ''].join('\n');
  return Buffer.concat([Buffer.from(head, 'utf8'), payload]);
}

/** A one-shot server: `answer(requestText, socket)` decides what happens. */
async function serve(answer) {
  const where = address();
  const server = net.createServer((socket) => {
    let text = '';
    socket.on('data', (chunk) => {
      text += chunk.toString('utf8');
      if (text.includes('\n--\n')) answer(text, socket);
    });
  });
  await new Promise((resolve) => server.listen(where, resolve));
  return { where, close: () => new Promise((resolve) => server.close(resolve)) };
}

test('an answer comes back whole, even in pieces', async () => {
  const server = await serve((text, socket) => {
    assert.match(text, /\nid 7\n/);
    assert.match(text, /\nop lua\n/);
    const reply = message({ id: 7, ok: 1 }, 'hello ünïcode');
    socket.write(reply.subarray(0, 10));
    setTimeout(() => socket.end(reply.subarray(10)), 20);
  });
  const answer = await pipeCall(server.where, message({ id: 7, op: 'lua' }, 'print(1)'), 7, 2000);
  assert.deepEqual(answer, { ok: true, body: 'hello ünïcode' });
  await server.close();
});

test('no pipe: null, so the caller uses the files and nothing ran', async () => {
  const answer = await pipeCall(address(), message({ id: 1, op: 'ping' }, ''), 1, 2000);
  assert.equal(answer, null);
});

test('closed mid-call: an error, never a second try', async () => {
  const server = await serve((_text, socket) => socket.destroy());
  await assert.rejects(pipeCall(server.where, message({ id: 2, op: 'lua' }, 'x'), 2, 2000),
    /closed its pipe|failed mid-call/);
  await server.close();
});

test('an answer to another request is refused', async () => {
  const server = await serve((_text, socket) => socket.end(message({ id: 99, ok: 1 }, 'not yours')));
  await assert.rejects(pipeCall(server.where, message({ id: 3, op: 'lua' }, 'x'), 3, 2000), /request 99/);
  await server.close();
});
