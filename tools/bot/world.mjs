// What the simulation knows, read from outside the game with `mjolnir live
// objects` (about half a second a read, so about two reads a second): the
// bot's own biped with its shield and body, every other living biped with
// where it faces, the weapons lying on the ground and the ones the bot holds.
//
// Positions are world units; angles degrees (the simulation's yaw, counter-
// clockwise from +x seen from above, as its plan has y up).
import { execFile } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/** "100% of 70" -> 1; "-" or "" -> null. */
function fraction(text) {
  const m = /^(-?\d+(?:\.\d+)?)%/.exec(text ?? "");
  return m ? Number(m[1]) / 100 : null;
}

/** The last name of a tag path: `objects\weapons\pistol\magnum\magnum` -> magnum. */
const kindOf = (tag) => String(tag).split("\\").pop();

/** The rows of a `live objects --tsv` file as
 *  { me, enemies, ground, held }:
 *   me       { handle, pos, yaw, shield, body, alive } for player `player`
 *   enemies  [{ handle, pos, yaw, body }] every other living biped
 *   ground   [{ kind, pos }] weapons nothing holds
 *   held     [kind] weapons whose parent is `me`
 *  Columns (1-based): 2 handle, 4 group, 5 tag, 6-8 position, 9 body, 10
 *  shield, 11 parent, 12 "player N", 13 yaw. */
export function parseObjects(tsv, player = 0) {
  const rows = String(tsv).trim().split("\n").slice(1).map((line) => line.split("\t"));
  const pos = (f) => [Number(f[5]), Number(f[6]), Number(f[7])];
  let me = null;
  const enemies = [];
  for (const f of rows) {
    if (f[3] !== "bipd") continue;
    const body = fraction(f[8]);
    const owner = /player (\d+)/.exec(f[11] ?? "");
    if (owner && Number(owner[1]) === player) {
      me = { handle: f[1], pos: pos(f), yaw: Number(f[12]) || 0, shield: fraction(f[9]) ?? 0, body: body ?? 0,
        alive: (body ?? 0) > 0 };
    } else if ((body ?? 0) > 0) {
      enemies.push({ handle: f[1], pos: pos(f), yaw: Number(f[12]) || 0, body });
    }
  }
  const ground = [];
  const held = [];
  for (const f of rows) {
    if (f[3] !== "weap") continue;
    const parent = (f[10] ?? "").trim();
    if (me && parent === me.handle) held.push(kindOf(f[4]));
    else if ((parent === "" || parent === "-") && (Number(f[5]) !== 0 || Number(f[6]) !== 0)) {
      ground.push({ kind: kindOf(f[4]), pos: pos(f) });
    }
  }
  return { me, enemies, ground, held };
}

/** Reads the simulation over and over in the background; `now` is the latest
 *  parse with `at` (ms) and `seq`. */
export class World {
  constructor(exe, player = 0) {
    this.exe = exe;
    this.player = player;
    this.tsv = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "mjolnir-bot-")), "objects.tsv");
    this.now = { me: null, enemies: [], ground: [], held: [], at: 0, seq: 0 };
    this.running = false;
  }
  start() {
    this.running = true;
    const again = () => {
      if (!this.running) return;
      execFile(this.exe, ["live", "objects", "--tsv", this.tsv], () => {
        try {
          const parsed = parseObjects(fs.readFileSync(this.tsv, "utf8"), this.player);
          this.now = { ...parsed, at: Date.now(), seq: this.now.seq + 1 };
        } catch { /* the next read */ }
        setTimeout(again, 20);
      });
    };
    again();
  }
  stop() {
    this.running = false;
  }
}
