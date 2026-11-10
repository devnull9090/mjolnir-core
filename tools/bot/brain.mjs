// The bot's decisions, as pure functions of what it perceives, what it
// remembers and its skill preset (presets.mjs): no game calls here, so every
// rule can be tested (test_brain.mjs). drive.mjs perceives, calls these and
// acts.
//
// Positions are world units unless a name says otherwise; angles degrees;
// times seconds on the caller's clock.
import { WEAPON_RANK } from "./presets.mjs";

export const M_PER_WU = 3.048;
const wrap = (deg) => ((deg + 540) % 360) - 180;
const dist2 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

/** What the bot remembers between ticks. */
export function newMemory() {
  return {
    targetHandle: null, seenAt: null, bone: "Head_M",
    noise: [0, 0], noiseFrom: [0, 0], noiseTo: [0, 0], noiseAt: -1e9,
    strafeDir: 0, strafeUntil: -1e9,
    burstAt: 0,
    lastDodge: -1e9, lastGrenade: -1e9, lastMelee: -1e9, lastSwap: -1e9,
    shield: 1, worldSeq: -1, hitAt: -1e9,
    firingSince: null, targetBodyAtFire: null,
    wasEngaged: false, lostAt: null,
    stats: { kills: 0, deaths: 0, dives: 0, grenades: 0, melees: 0, swaps: 0, pickups: 0 },
  };
}

/** A standard normal sample from a uniform rng (Box-Muller). */
function gaussian(rng) {
  const u = Math.max(rng(), 1e-12);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rng());
}

/** The enemy to go for: the nearest by `routeLength(enemy)` (wu), a wounded
 *  one weighing less by the preset's `finisher`. Null for none. */
export function chooseTarget(enemies, routeLength, skill) {
  let best = null;
  for (const e of enemies) {
    const length = routeLength(e);
    const score = length * (1 - skill.finisher * (1 - Math.min(1, e.body ?? 1)));
    if (!best || score < best.score) best = { enemy: e, score, length };
  }
  return best;
}

/** The weapon on the ground worth walking to: better than anything held,
 *  within the preset's reach by `routeLength(weapon)` (wu); the best, then
 *  the nearest. Null when none, or the preset does not look. */
export function chooseWeapon(ground, held, routeLength, skill) {
  if (!skill.seekWeapons) return null;
  const rank = (kind) => WEAPON_RANK[kind] ?? 1;
  const best = Math.max(0, ...held.map(rank));
  let pick = null;
  for (const w of ground) {
    if (rank(w.kind) <= best || held.includes(w.kind)) continue;
    const length = routeLength(w);
    if (length * M_PER_WU > skill.seekRange) continue;
    if (!pick || rank(w.kind) > rank(pick.weapon.kind)
      || (rank(w.kind) === rank(pick.weapon.kind) && length < pick.length)) pick = { weapon: w, length };
  }
  return pick;
}

/** Where the aim is off the bone right now (yaw, pitch, deg): it drifts from
 *  one random offset to the next every `aimWander` seconds. */
export function aimNoise(mem, skill, now, rng) {
  if (now - mem.noiseAt >= skill.aimWander) {
    mem.noiseFrom = mem.noise;
    mem.noiseTo = [gaussian(rng) * skill.aimError, gaussian(rng) * skill.aimError * 0.6];
    mem.noiseAt = now;
  }
  const k = Math.min(1, (now - mem.noiseAt) / Math.max(skill.aimWander, 1e-6));
  mem.noise = [0, 1].map((i) => mem.noiseFrom[i] + (mem.noiseTo[i] - mem.noiseFrom[i]) * k);
  return mem.noise;
}

/** Whether `enemy` (sim position and yaw) faces `me` within `within` deg. */
export function aimedAt(enemy, me, within) {
  const bearing = (Math.atan2(me[1] - enemy.pos[1], me[0] - enemy.pos[0]) * 180) / Math.PI;
  return Math.abs(wrap(bearing - enemy.yaw)) <= within;
}

/**
 * One tick of a fight.
 *   p    { now, dt, me: { pos, shield, body }, worldSeq,
 *          target: { handle, pos, yaw, body } | null,
 *          visible (the target's actor shows), locked (red reticle),
 *          onTarget (the aim is within the target's width of the bone),
 *          distance (m, plan), canDive: { left, right } }
 *   mem  newMemory()
 * Returns { engaged, fire, hold: { forward, back, left, right, crouch },
 *   taps: [key names], dive: "left" | "right" | null, bone, noise: [yaw, pitch],
 *   retreating }.
 */
export function fight(p, mem, skill, rng) {
  const out = {
    engaged: false, fire: false, hold: { forward: false, back: false, left: false, right: false, crouch: false },
    taps: [], dive: null, bone: mem.bone, noise: [0, 0], retreating: false,
  };
  const t = p.target;

  // A hit: the shield fell between two reads of the simulation.
  if (p.worldSeq !== mem.worldSeq) {
    if (p.me.shield < mem.shield - 0.02) mem.hitAt = p.now;
    mem.shield = p.me.shield;
    mem.worldSeq = p.worldSeq;
  }

  // A new target is noticed, then reacted to.
  if (!t || !p.visible) {
    if (!t || t.handle !== mem.targetHandle) mem.seenAt = null;
    // A fight is over once nothing has been in view for a moment.
    if (mem.lostAt === null) mem.lostAt = p.now;
    if (mem.wasEngaged && p.now - mem.lostAt >= 1.5) {
      out.taps.push("reload"); // top up between fights
      mem.wasEngaged = false;
    }
    mem.firingSince = null;
    mem.targetHandle = t ? t.handle : null;
    return out;
  }
  mem.lostAt = null;
  if (t.handle !== mem.targetHandle || mem.seenAt === null) {
    mem.targetHandle = t.handle;
    mem.seenAt = p.now;
    mem.bone = rng() < skill.headshots ? "Head_M" : "Chest_M";
    out.bone = mem.bone;
    mem.firingSince = null;
  }
  if (p.distance > skill.engage) return out;
  out.engaged = true;
  mem.wasEngaged = true;
  const reacted = p.now - mem.seenAt >= skill.reaction;
  out.noise = aimNoise(mem, skill, p.now, rng);

  // Trigger, in bursts: on the red reticle, or with the aim on the target's
  // body (the reticle only reddens inside the weapon's auto-aim range).
  const [on, off] = skill.burst;
  const phase = (p.now - mem.burstAt) % (on + off || 1);
  out.fire = reacted && (p.locked || p.onTarget === true) && (off <= 0 || phase < on);

  // Out of ammunition, or the wrong tool: on target and nothing happens.
  if (out.fire) {
    if (mem.firingSince === null) {
      mem.firingSince = p.now;
      mem.targetBodyAtFire = t.body;
    } else if (t.body < mem.targetBodyAtFire - 0.01) {
      mem.firingSince = p.now;
      mem.targetBodyAtFire = t.body;
    } else if (p.now - mem.firingSince >= skill.swapAfter && p.now - mem.lastSwap >= skill.swapAfter) {
      out.taps.push("swap");
      mem.lastSwap = p.now;
      mem.firingSince = p.now;
      mem.stats.swaps++;
    }
  } else if (!p.locked && !p.onTarget) {
    mem.firingSince = null;
  }

  // Feet.
  out.retreating = p.me.shield < skill.retreat;
  if (out.retreating) out.hold.back = true;
  else if (p.distance > skill.hold) out.hold.forward = true;
  else if (p.distance < 3 && skill.melee <= 0) out.hold.back = true;
  if (skill.strafe > 0 || out.retreating) {
    if (p.now >= mem.strafeUntil) {
      const [lo, hi] = skill.strafeEvery;
      mem.strafeUntil = p.now + lo + rng() * (hi - lo);
      const moving = out.retreating || rng() < skill.strafe;
      mem.strafeDir = moving ? (mem.strafeDir === 1 ? -1 : mem.strafeDir === -1 ? 1 : rng() < 0.5 ? -1 : 1) : 0;
    }
    if (mem.strafeDir < 0) out.hold.left = true;
    if (mem.strafeDir > 0) out.hold.right = true;
  }
  if (rng() < skill.crouch * p.dt) out.hold.crouch = true;
  if (rng() < skill.jump * p.dt) out.taps.push("jump");

  // Hands.
  if (skill.melee > 0 && p.distance <= skill.melee && p.now - mem.lastMelee >= 0.9) {
    out.taps.push("melee");
    mem.lastMelee = p.now;
    mem.stats.melees++;
  }
  const [near, far] = skill.grenadeRange;
  if (reacted && p.distance >= near && p.distance <= far && p.now - mem.lastGrenade >= skill.grenadeEvery) {
    out.taps.push("grenade");
    mem.lastGrenade = p.now;
    mem.stats.grenades++;
  }

  // Out of the way: when a hit lands, or when the enemy has it lined up.
  if (p.now - mem.lastDodge >= skill.dodgeCooldown) {
    const hit = p.now - mem.hitAt < 0.25 && rng() < skill.dodgeOnHit;
    const lined = aimedAt(t, p.me.pos, skill.dodgeAimed) && rng() < skill.dodgeAware * p.dt;
    if (hit || lined) {
      const options = ["left", "right"].filter((side) => p.canDive?.[side] !== false);
      if (options.length) {
        out.dive = options[Math.floor(rng() * options.length)];
        mem.lastDodge = p.now;
        mem.hitAt = -1e9;
        mem.stats.dives++;
      }
    }
  }
  return out;
}

/** Whether an aim `error` (yaw, pitch, deg) off a bone `distance` m away is
 *  still on a body `halfWidth` m wide. */
export function onBody(error, distance, halfWidth = 0.28) {
  const cone = (Math.atan2(halfWidth, Math.max(distance, 0.5)) * 180) / Math.PI;
  return Math.abs(error[0]) <= cone && Math.abs(error[1]) <= cone * 1.4;
}

/** The angles to turn (yaw, pitch, deg) from a camera (UE cm, UE yaw/pitch)
 *  to a point (UE cm), plus `offset` (deg). */
export function turnTo(camera, yaw, pitch, point, offset = [0, 0]) {
  const d = [point[0] - camera[0], point[1] - camera[1], point[2] - camera[2]];
  return [
    wrap((Math.atan2(d[1], d[0]) * 180) / Math.PI - yaw) + offset[0],
    (Math.atan2(d[2], Math.hypot(d[0], d[1])) * 180) / Math.PI - pitch + offset[1],
  ];
}

export { dist2, wrap };
