// Turns game_input steps into a script for the test input DLL
// (native/test_input/mjolnir_test_input.c), which drives the player from inside
// the game: no OS input, no focus change.
//
// Keys are Windows virtual keys, which is what the simulation's key state is
// indexed by. A plain Shift, Ctrl or Alt is the left one: the simulation tracks
// the two sides apart and has no entry for the generic codes.

const VK = {
  escape: 27, backspace: 8, tab: 9, enter: 13, space: 32, capslock: 20,
  pause: 19, scrolllock: 145, numlock: 144,
  shift: 160, lshift: 160, rshift: 161, ctrl: 162, lctrl: 162, rctrl: 163,
  alt: 164, lalt: 164, ralt: 165, lwin: 91, rwin: 92, menu: 93,
  pageup: 33, pagedown: 34, end: 35, home: 36, left: 37, up: 38, right: 39, down: 40,
  insert: 45, delete: 46,
  numstar: 106, numplus: 107, numminus: 109, numdot: 110, numslash: 111,
  semicolon: 186, equals: 187, comma: 188, minus: 189, period: 190, slash: 191,
  grave: 192, tilde: 192, lbracket: 219, backslash: 220, rbracket: 221, apostrophe: 222,
};
for (let i = 0; i < 10; i++) {
  VK[String(i)] = 48 + i;
  VK[`num${i}`] = 96 + i;
}
for (let i = 0; i < 26; i++) VK[String.fromCharCode(97 + i)] = 65 + i;
for (let i = 1; i <= 12; i++) VK[`f${i}`] = 111 + i;

const BUTTON = { left: 1, middle: 2, right: 4, thumb1: 8, thumb2: 16 };

const DEFAULT_HOLD_MS = 40;

function lookup(table, name, what) {
  const code = table[String(name).toLowerCase()];
  if (code === undefined) throw new Error(`unknown ${what} '${name}'`);
  return code;
}

// A press, a hold, or one half of either, for `<word> <code> <1|0>` lines.
function pressLines(word, code, step, lines, done, label) {
  if (step.down) {
    lines.push(`${word} ${code} 1`);
    done.push(`down ${label}`);
  } else if (step.up) {
    lines.push(`${word} ${code} 0`);
    done.push(`up ${label}`);
  } else {
    const hold = step.hold ? Number(step.hold) : DEFAULT_HOLD_MS;
    lines.push(`${word} ${code} 1`, `wait ${hold}`, `${word} ${code} 0`);
    done.push(`press ${label} ${hold}ms`);
    return hold;
  }
  return 0;
}

// The script for a step list, what it will do, and how long it takes to run.
export function toScript(steps, gapMs = 60) {
  const lines = [];
  const done = [];
  let duration = 0;
  for (const step of steps) {
    if (step.wait) {
      lines.push(`wait ${Number(step.wait)}`);
      done.push(`wait ${step.wait}ms`);
      duration += Number(step.wait);
      continue;
    }
    if (step.click) {
      throw new Error(
        "click needs the desktop cursor, so it cannot run in the game; pass method:'sendinput' for screens that need it"
      );
    }
    if (step.move) {
      const [dx, dy] = step.move.map((n) => Math.trunc(Number(n)));
      if (!Number.isFinite(dx) || !Number.isFinite(dy)) throw new Error(`bad move ${JSON.stringify(step.move)}`);
      lines.push(`look ${dx} ${dy}`);
      done.push(`move ${dx},${dy}`);
    } else if (step.mouse) {
      duration += pressLines("button", lookup(BUTTON, step.mouse, "mouse button"), step, lines, done, `mouse ${step.mouse}`);
    } else if (step.key) {
      duration += pressLines("key", lookup(VK, step.key, "key"), step, lines, done, step.key);
    } else if (step.release) {
      lines.push("release");
      done.push("release everything");
    } else {
      throw new Error(`step has none of key/mouse/move/release/wait: ${JSON.stringify(step)}`);
    }
    lines.push(`wait ${gapMs}`);
    duration += gapMs;
  }
  return { lines, done, duration };
}

// `id 12 ok reads 900 delivered 40`, or `id 12 error why`; null if not this id.
export function parseAck(text, id) {
  const line = text.trim();
  const ok = line.match(/^id (-?\d+) ok reads (\d+) delivered (\d+)$/);
  if (ok) {
    return Number(ok[1]) === id ? { ok: true, reads: Number(ok[2]), delivered: Number(ok[3]) } : null;
  }
  const failed = line.match(/^id (-?\d+) error (.*)$/);
  if (failed) return Number(failed[1]) === id ? { ok: false, error: failed[2] } : null;
  return null;
}
