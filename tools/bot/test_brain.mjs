// node --test tools/bot/test_brain.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  aimedAt, aimNoise, appliedSince, chooseTarget, chooseWeapon, fight, fitVelocity, newMemory, onBody, track, turnTo,
} from "./brain.mjs";
import { PRESETS, preset } from "./presets.mjs";
import { parseObjects } from "./world.mjs";

// A repeatable rng (mulberry32).
function seeded(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const enemy = (over = {}) => ({ handle: "0xE1", pos: [10, 0, 0], yaw: 180, body: 1, ...over });
const percept = (over = {}) => ({
  now: 0, dt: 0.1, worldSeq: 1, me: { pos: [0, 0, 0], shield: 1, body: 1 }, target: enemy(), visible: true,
  locked: true, distance: 10, canDive: { left: true, right: true }, ...over,
});

test("presets: every one has every setting, and skill rises through them", () => {
  const keys = Object.keys(PRESETS.regular).sort();
  for (const p of Object.values(PRESETS)) assert.deepEqual(Object.keys(p).sort(), keys);
  const order = ["recruit", "regular", "heroic", "legendary"].map((n) => PRESETS[n]);
  for (let i = 1; i < order.length; i++) {
    assert.ok(order[i].reaction < order[i - 1].reaction);
    assert.ok(order[i].aimError < order[i - 1].aimError);
    assert.ok(order[i].turnRate > order[i - 1].turnRate);
    assert.ok(order[i].dodgeOnHit >= order[i - 1].dodgeOnHit);
  }
});

test("presets: overrides by name, and a bad one is refused", () => {
  const p = preset("heroic", ["aimError=0.5", "sprint=false", "burst=0.2,0.4"]);
  assert.equal(p.aimError, 0.5);
  assert.equal(p.sprint, false);
  assert.deepEqual(p.burst, [0.2, 0.4]);
  assert.equal(PRESETS.heroic.aimError, 0.8, "the preset itself is untouched");
  assert.throws(() => preset("heroic", ["aimErorr=1"]), /no setting/);
  assert.throws(() => preset("godlike"), /no skill/);
  assert.throws(() => preset("heroic", ["aimError=lots"]), /bad value/);
});

test("fight: nothing happens before the reaction time, then it fires on the red reticle", () => {
  const skill = preset("regular", { burst: "1,0", grenadeEvery: Infinity });
  const mem = newMemory();
  const rng = seeded(1);
  assert.equal(fight(percept({ now: 0 }), mem, skill, rng).fire, false);
  assert.equal(fight(percept({ now: 0.3 }), mem, skill, rng).fire, false);
  assert.equal(fight(percept({ now: 0.45 }), mem, skill, rng).fire, true);
  assert.equal(fight(percept({ now: 0.5, locked: false }), mem, skill, rng).fire, false, "not off the reticle");
});

test("fight: past the reticle's range it fires with the aim on the body", () => {
  const skill = preset("regular", { burst: "1,0", grenadeEvery: Infinity });
  const mem = newMemory();
  fight(percept({ now: 0, locked: false }), mem, skill, seeded(1));
  assert.equal(fight(percept({ now: 1, locked: false, onTarget: false }), mem, skill, seeded(1)).fire, false);
  assert.equal(fight(percept({ now: 1.1, locked: false, onTarget: true }), mem, skill, seeded(1)).fire, true);
  // A body 0.28 m either side: 1 degree off is on it at 10 m, not at 40 m.
  assert.equal(onBody([1, 0], 10), true);
  assert.equal(onBody([1, 0], 40), false);
  assert.equal(onBody([0.2, 0.3], 40), true);
});

test("fight: a target out of sight or out of range is not engaged", () => {
  const skill = preset("regular");
  assert.equal(fight(percept({ visible: false }), newMemory(), skill, seeded(1)).engaged, false);
  assert.equal(fight(percept({ distance: 80 }), newMemory(), skill, seeded(1)).engaged, false);
  assert.equal(fight(percept({ target: null }), newMemory(), skill, seeded(1)).engaged, false);
});

test("fight: a recruit stands still; a legendary never does", () => {
  const still = fight(percept({ now: 5 }), newMemory(), preset("recruit"), seeded(3));
  assert.deepEqual([still.hold.left, still.hold.right], [false, false]);
  const mem = newMemory();
  const rng = seeded(3);
  let moved = 0;
  for (let i = 0; i < 50; i++) {
    const f = fight(percept({ now: i * 0.1 }), mem, preset("legendary"), rng);
    if (f.hold.left || f.hold.right) moved++;
  }
  assert.equal(moved, 50);
});

test("fight: a hit makes a legendary dive, once per cooldown, to a side with room", () => {
  const skill = preset("legendary", { dodgeOnHit: 1, dodgeAware: 0 });
  const mem = newMemory();
  const rng = seeded(7);
  fight(percept({ now: 0, worldSeq: 1 }), mem, skill, rng);
  const hit = fight(percept({ now: 0.5, worldSeq: 2, me: { pos: [0, 0, 0], shield: 0.6, body: 1 },
    canDive: { left: false, right: true } }), mem, skill, rng);
  assert.equal(hit.dive, "right");
  const again = fight(percept({ now: 0.6, worldSeq: 3, me: { pos: [0, 0, 0], shield: 0.3, body: 1 } }), mem, skill, rng);
  assert.equal(again.dive, null, "inside the cooldown");
  const later = fight(percept({ now: 4, worldSeq: 4, me: { pos: [0, 0, 0], shield: 0.1, body: 1 } }), mem, skill, rng);
  assert.ok(later.dive, "after it");
  assert.equal(mem.stats.dives, 2);
  // A recruit takes it.
  const r = newMemory();
  fight(percept({ now: 0, worldSeq: 1 }), r, preset("recruit"), seeded(7));
  assert.equal(fight(percept({ now: 0.5, worldSeq: 2, me: { pos: [0, 0, 0], shield: 0.5, body: 1 } }), r,
    preset("recruit"), seeded(7)).dive, null);
});

test("fight: no room either side, no dive", () => {
  const skill = preset("legendary", { dodgeOnHit: 1 });
  const mem = newMemory();
  fight(percept({ now: 0, worldSeq: 1 }), mem, skill, seeded(2));
  const f = fight(percept({ now: 0.5, worldSeq: 2, me: { pos: [0, 0, 0], shield: 0.5, body: 1 },
    canDive: { left: false, right: false } }), mem, skill, seeded(2));
  assert.equal(f.dive, null);
});

test("fight: low shields back off; melee inside its range; grenades in theirs", () => {
  const skill = preset("heroic", { grenadeEvery: 5 });
  const low = fight(percept({ now: 1, me: { pos: [0, 0, 0], shield: 0.1, body: 1 } }), newMemory(), skill, seeded(1));
  assert.equal(low.retreating, true);
  assert.equal(low.hold.back, true);
  const close = fight(percept({ now: 1, distance: 1.5 }), newMemory(), skill, seeded(1));
  assert.ok(close.taps.includes("melee"));
  assert.ok(!close.taps.includes("grenade"), "too close for a grenade");
  const mem = newMemory();
  fight(percept({ now: 0 }), mem, skill, seeded(1));
  const mid = fight(percept({ now: 1, distance: 12 }), mem, skill, seeded(1));
  assert.ok(mid.taps.includes("grenade"));
  assert.ok(!fight(percept({ now: 2, distance: 12 }), mem, skill, seeded(1)).taps.includes("grenade"), "cooldown");
});

test("fight: on target with no damage for long enough, it swaps weapons", () => {
  const skill = preset("regular", { burst: "1,0", swapAfter: 2, grenadeEvery: Infinity });
  const mem = newMemory();
  const rng = seeded(1);
  let swapped = null;
  for (let i = 0; i <= 40 && swapped === null; i++) {
    if (fight(percept({ now: i * 0.1 }), mem, skill, rng).taps.includes("swap")) swapped = i * 0.1;
  }
  assert.ok(swapped !== null && swapped >= 2.4 && swapped <= 2.7, `swapped at ${swapped}`);
  // Damage landing keeps the weapon.
  const m2 = newMemory();
  for (let i = 0; i <= 40; i++) {
    const f = fight(percept({ now: i * 0.1, target: enemy({ body: 1 - i * 0.02 }) }), m2, skill, seeded(1));
    assert.ok(!f.taps.includes("swap"));
  }
});

test("fight: leaving a fight reloads once", () => {
  const skill = preset("regular");
  const mem = newMemory();
  fight(percept({ now: 0 }), mem, skill, seeded(1));
  assert.deepEqual(fight(percept({ now: 1, visible: false }), mem, skill, seeded(1)).taps, [], "lost for a moment");
  assert.deepEqual(fight(percept({ now: 2.6, visible: false }), mem, skill, seeded(1)).taps, ["reload"]);
  assert.deepEqual(fight(percept({ now: 2.7, visible: false }), mem, skill, seeded(1)).taps, []);
});

test("aim noise stays near its preset's error and moves smoothly", () => {
  for (const [name, limit] of [["recruit", 3.5], ["legendary", 0.15]]) {
    const skill = preset(name);
    const mem = newMemory();
    const rng = seeded(9);
    let sum = 0;
    let lastYaw = 0;
    let jump = 0;
    const n = 2000;
    for (let i = 0; i < n; i++) {
      const [yaw] = aimNoise(mem, skill, i * 0.05, rng);
      sum += yaw * yaw;
      jump = Math.max(jump, Math.abs(yaw - lastYaw));
      lastYaw = yaw;
    }
    const rms = Math.sqrt(sum / n);
    assert.ok(rms > limit * 0.4 && rms < limit * 1.1, `${name} rms ${rms}`);
    assert.ok(jump < limit * 2.5, `${name} jump ${jump}`);
  }
});

test("aimedAt: facing the bot, or not", () => {
  assert.equal(aimedAt({ pos: [10, 0, 0], yaw: 180 }, [0, 0, 0], 12), true);
  assert.equal(aimedAt({ pos: [10, 0, 0], yaw: 150 }, [0, 0, 0], 12), false);
  assert.equal(aimedAt({ pos: [0, 10, 0], yaw: -90 }, [0, 0, 0], 12), true);
});

test("chooseTarget: the nearest, unless a finisher sees a wounded one", () => {
  const near = enemy({ handle: "a", pos: [5, 0, 0], body: 1 });
  const hurt = enemy({ handle: "b", pos: [7, 0, 0], body: 0.2 });
  const len = (e) => e.pos[0];
  assert.equal(chooseTarget([near, hurt], len, preset("recruit")).enemy.handle, "a");
  assert.equal(chooseTarget([near, hurt], len, preset("legendary")).enemy.handle, "b");
  assert.equal(chooseTarget([], len, preset("regular")), null);
});

test("chooseWeapon: the best one in reach that beats what is held", () => {
  const ground = [
    { kind: "magnum", pos: [2, 0, 0] }, { kind: "sniper_rifle", pos: [6, 0, 0] },
    { kind: "rocket_launcher", pos: [500, 0, 0] }, { kind: "plasma_pistol", pos: [1, 0, 0] },
  ];
  const len = (w) => w.pos[0];
  assert.equal(chooseWeapon(ground, ["assault_rifle"], len, preset("regular")).weapon.kind, "sniper_rifle");
  assert.equal(chooseWeapon(ground, ["assault_rifle", "sniper_rifle"], len, preset("regular")), null);
  assert.equal(chooseWeapon(ground, ["assault_rifle"], len, preset("recruit")), null, "a recruit does not look");
});

test("turnTo: angles from the camera to a point, with an offset", () => {
  const [yaw, pitch] = turnTo([0, 0, 0], 0, 0, [100, 100, 0]);
  assert.ok(Math.abs(yaw - 45) < 1e-9 && Math.abs(pitch) < 1e-9);
  assert.ok(Math.abs(turnTo([0, 0, 0], 170, 0, [-100, -10, 0])[0] - 15.71) < 0.01, "across the seam");
  assert.deepEqual(turnTo([0, 0, 0], 0, 0, [100, 0, 0], [2, -1]), [2, -1]);
});

test("world: the simulation's rows become the bot, enemies, and weapons", () => {
  const tsv = [
    "index\thandle\ttype\tgroup\ttag\tx\ty\tz\tbody\tshield\tparent\towner\tyaw\taddress\tteam",
    "24\t0xE4F10018\tbiped\tbipd\tobjects\\characters\\spartans\\spartans\t90.09\t-157.35\t0.12\t100% of 105\t-\t-\t\t58.9\t0x1\tteam 3/-1",
    "25\t0xE4F10019\tbiped\tbipd\tobjects\\characters\\spartans\\spartans\t80\t-150\t0.1\t0% of 105\t-\t-\t\t10\t0x2\tteam 3/-1",
    "142\t0xE4DC008E\tbiped\tbipd\tobjects\\characters\\spartans\\spartans\t43.43\t-75.90\t1.70\t100% of 45\t40% of 70\t-\tplayer 0\t-60.0\t0x3\tteam -1/0",
    "30\t0xE2000030\tweapon\tweap\tobjects\\weapons\\pistol\\magnum\\magnum\t0\t0\t0\t-\t-\t0xE4DC008E\t\t0\t0x4\t",
    "31\t0xE2000031\tweapon\tweap\tobjects\\weapons\\rifle\\sniper_rifle\\sniper_rifle\t43.19\t-82.23\t1.74\t-\t-\t-\t\t0\t0x5\t",
    "32\t0xE2000032\tweapon\tweap\tobjects\\vehicles\\human\\warthog\\weapons\\warthog_chaingun\\weapon\\warthog_chaingun\t0\t0\t0\t-\t-\t0xE2700001\t\t0\t0x6\t",
  ].join("\n");
  const w = parseObjects(tsv, 0);
  assert.equal(w.me.handle, "0xE4DC008E");
  assert.equal(w.me.shield, 0.4);
  assert.equal(w.me.alive, true);
  assert.equal(w.enemies.length, 1, "the dead one is not an enemy");
  assert.equal(w.enemies[0].yaw, 58.9);
  assert.deepEqual(w.held, ["magnum"]);
  assert.deepEqual(w.ground, [{ kind: "sniper_rifle", pos: [43.19, -82.23, 1.74] }]);
});

test("fitVelocity: a steady runner's speed, through a noisy reading", () => {
  const samples = [];
  for (let i = 0; i < 5; i++) samples.push({ t: i * 0.1, pos: [i * 0.1 * 600, 100, 0] }); // 600 cm/s along x
  const v = fitVelocity(samples);
  assert.ok(Math.abs(v[0] - 600) < 1e-6 && Math.abs(v[1]) < 1e-6);
  // One reading 40 cm out: two-point differences would say 1000 or 200.
  samples[4].pos = [4 * 60 + 40, 100, 0];
  assert.ok(Math.abs(fitVelocity(samples)[0] - 600) < 90, `fit ${fitVelocity(samples)[0]}`);
  assert.deepEqual(fitVelocity([{ t: 0, pos: [1, 2, 3] }]), [0, 0, 0]);
  assert.deepEqual(fitVelocity([{ t: 1, pos: [1, 2, 3] }, { t: 1, pos: [9, 9, 9] }]), [0, 0, 0]);
});

test("track: keeps the last half second", () => {
  const samples = [];
  for (let i = 0; i < 20; i++) track(samples, i * 0.1, [i, 0, 0]);
  assert.ok(samples.length >= 4 && samples.length <= 6);
  assert.equal(samples[samples.length - 1].pos[0], 19);
});

test("appliedSince: the part of a turn a stale reading has not seen", () => {
  const glide = { amount: 12, at: 1.0, span: 0.12 };
  assert.ok(Math.abs(appliedSince(glide, 1.0, 1.12) - 12) < 1e-9, "all of it");
  assert.ok(Math.abs(appliedSince(glide, 1.06, 1.12) - 6) < 1e-9, "the second half");
  assert.ok(Math.abs(appliedSince(glide, 1.06, 1.09) - 3) < 1e-9, "a slice");
  assert.equal(appliedSince(glide, 1.2, 1.3), 0, "already over");
  assert.equal(appliedSince(null, 0, 1), 0);
});

test("presets: only the skilled lock on", () => {
  assert.equal(PRESETS.recruit.lockOn, 0);
  assert.equal(PRESETS.regular.lockOn, 0);
  assert.ok(PRESETS.heroic.lockOn > 0 && PRESETS.legendary.lockOn > PRESETS.heroic.lockOn);
});
