// Skill presets for the bot (tools/bot/README.md). A preset is every number
// the brain reads; nothing about skill is hard-coded elsewhere. Use one by
// name (`--skill heroic`), and override any field (`--set aimError=0.5`).
//
// Times are seconds unless named Ms, angles degrees, distances metres.

export const KEYS = {
  // Windows virtual keys, as the simulation's key state is indexed. These are
  // the game's bindings on the test PC (HaloGlobalGameUserSettings.ini,
  // CustomInputMappingKBM); change them here if the bindings change.
  forward: 87, back: 83, left: 65, right: 68, // W S A D
  jump: 32, crouch: 162, sprint: 160, // Space, Left Ctrl, Left Shift
  melee: 70, grenade: 67, reload: 82, swap: 49, use: 69, // F C R 1 E
};

const base = {
  // --- Seeing and aiming ---
  reaction: 0.4,       // from a target coming into view to the first aimed shot
  turnRate: 220,       // how fast the view may turn onto a target, deg/s
  aimError: 1.8,       // how far the aim wanders off the bone (one sigma), deg
  aimWander: 0.4,      // how often the wander picks a new offset
  lead: 0.05,          // how far ahead of a moving target to aim, s of its motion
  headshots: 0.35,     // the share of targets aimed at the head (else the chest)
  engage: 30,          // a showing target this close is fought, m
  hold: 8,             // stops closing in at this range, m
  // --- Trigger ---
  burst: [0.9, 0.3],   // fire this long, rest this long; [1, 0] holds the trigger
  // --- Moving in a fight ---
  strafe: 0.5,         // the share of the fight spent side-stepping
  strafeEvery: [0.8, 1.6], // a side-step lasts between these
  crouch: 0.05,        // crouch taps a second
  jump: 0.03,          // jumps a second
  sprint: true,        // sprint on a straight stretch when not fighting
  // --- Getting out of the way ---
  dodgeOnHit: 0.15,    // chance to dive when a hit lands
  dodgeAware: 0,       // dives a second while an enemy aims at it
  dodgeAimed: 12,      // "aims at it": the enemy faces within this of the bot, deg
  dodgeCooldown: 8,    // between dives
  retreat: 0.15,       // backs off below this shield fraction
  // --- Weapons ---
  melee: 2.2,          // melees inside this range, m (0: never)
  grenadeEvery: 20,    // seconds between grenades (Infinity: never)
  grenadeRange: [6, 20],
  seekWeapons: true,   // walks to a better weapon when no fight is on
  seekRange: 25,       // how far it will go for one, m of route
  swapAfter: 3.5,      // firing on target this long with no damage: next weapon
  // --- Choosing a target ---
  finisher: 0,         // 0..1: how much a wounded enemy outweighs a nearer one
};

export const PRESETS = {
  // Stands and shoots in bursts, misses a lot, never dodges.
  recruit: {
    ...base, reaction: 0.75, turnRate: 140, aimError: 3.5, aimWander: 0.55, lead: 0, headshots: 0.1,
    engage: 22, burst: [0.5, 0.7], strafe: 0, crouch: 0, jump: 0, sprint: false,
    dodgeOnHit: 0, dodgeAware: 0, retreat: 0, grenadeEvery: Infinity, seekWeapons: false,
  },
  regular: { ...base },
  // Strafes hard, aims for the head, dives when shot, throws grenades.
  heroic: {
    ...base, reaction: 0.22, turnRate: 320, aimError: 0.8, aimWander: 0.3, lead: 0.1, headshots: 0.65,
    engage: 40, burst: [1, 0], strafe: 0.85, strafeEvery: [0.5, 1.1], crouch: 0.15, jump: 0.08,
    dodgeOnHit: 0.5, dodgeAware: 0.25, dodgeCooldown: 5, retreat: 0.3, grenadeEvery: 10, seekRange: 40,
    finisher: 0.3,
  },
  // Near-instant, near-perfect, never still: dives the moment it is aimed at.
  legendary: {
    ...base, reaction: 0.08, turnRate: 540, aimError: 0.15, aimWander: 0.2, lead: 0.15, headshots: 0.95,
    engage: 60, hold: 10, burst: [1, 0], strafe: 1, strafeEvery: [0.3, 0.8], crouch: 0.3, jump: 0.12,
    dodgeOnHit: 0.9, dodgeAware: 0.8, dodgeAimed: 18, dodgeCooldown: 2.5, retreat: 0.4,
    grenadeEvery: 6, seekRange: 60, swapAfter: 2.5, finisher: 0.6,
  },
};

/** How much better a weapon is than nothing, by the tail of its tag path.
 *  Higher is taken first; a weapon not listed is worth 1. */
export const WEAPON_RANK = {
  rocket_launcher: 10, sniper_rifle: 9, fuel_rod_gun: 8, shotgun: 7, magnum: 6, plasma_rifle: 5,
  needler: 4, assault_rifle: 3, plasma_pistol: 2, flamethrower: 2,
};

/** Preset `name` with `overrides` ({ field: value } or ["field=value", ...]). */
export function preset(name = "regular", overrides = {}) {
  const found = PRESETS[name];
  if (!found) throw new Error(`no skill '${name}' (${Object.keys(PRESETS).join(", ")})`);
  const out = { ...found, name };
  const pairs = Array.isArray(overrides)
    ? overrides.map((o) => String(o).split("="))
    : Object.entries(overrides);
  for (const [key, raw] of pairs) {
    if (!(key in base)) throw new Error(`no setting '${key}' (${Object.keys(base).join(", ")})`);
    const now = out[key];
    if (Array.isArray(now)) out[key] = String(raw).split(",").map(Number);
    else if (typeof now === "boolean") out[key] = raw === true || raw === "true" || raw === "1";
    else out[key] = Number(raw);
    const bad = Array.isArray(out[key]) ? out[key].some(Number.isNaN) : Number.isNaN(out[key]);
    if (bad) throw new Error(`bad value for '${key}': ${raw}`);
  }
  return out;
}
