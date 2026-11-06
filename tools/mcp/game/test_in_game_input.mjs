// node --test tools/mcp/game/test_in_game_input.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { parseAck, toScript } from "./in_game_input.mjs";

test("a held key goes down, waits and comes up", () => {
  const { lines, duration } = toScript([{ key: "W", hold: 800 }], 60);
  assert.deepEqual(lines, ["key 87 1", "wait 800", "key 87 0", "wait 60"]);
  assert.equal(duration, 860);
});

test("down and up are separate halves", () => {
  const { lines } = toScript([{ key: "Shift", down: true }, { key: "Shift", up: true }], 0);
  assert.deepEqual(lines, ["key 160 1", "wait 0", "key 160 0", "wait 0"]);
});

test("mouse buttons, look and release", () => {
  const { lines } = toScript(
    [{ mouse: "left", hold: 60 }, { mouse: "right", down: true }, { move: [120, -40] }, { release: true }, { wait: 500 }],
    0
  );
  assert.deepEqual(lines, [
    "button 1 1", "wait 60", "button 1 0", "wait 0",
    "button 4 1", "wait 0",
    "look 120 -40", "wait 0",
    "release", "wait 0",
    "wait 500",
  ]);
});

test("keys are the virtual keys the simulation indexes by", () => {
  const code = (key) => Number(toScript([{ key, down: true }], 0).lines[0].split(" ")[1]);
  assert.equal(code("E"), 69);
  assert.equal(code("5"), 53);
  assert.equal(code("F1"), 112);
  assert.equal(code("Enter"), 13);
  assert.equal(code("num0"), 96);
  assert.equal(code("up"), 38);
});

test("click and unknown names are refused, never guessed", () => {
  assert.throws(() => toScript([{ click: [1, 2] }]), /sendinput/);
  assert.throws(() => toScript([{ key: "nope" }]), /unknown key/);
  assert.throws(() => toScript([{ mouse: "nope" }]), /unknown mouse button/);
  assert.throws(() => toScript([{ hold: 5 }]), /step has none/);
});

test("an ack answers only its own id", () => {
  assert.deepEqual(parseAck("id 3 ok reads 90 delivered 4\n", 3), { ok: true, reads: 90, delivered: 4 });
  assert.equal(parseAck("id 2 ok reads 90 delivered 4\n", 3), null);
  assert.deepEqual(parseAck("id 3 error bad line: x\n", 3), { ok: false, error: "bad line: x" });
  assert.equal(parseAck("", 3), null);
});
