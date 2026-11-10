// A bot that plays the local player (tools/bot/README.md): it walks the
// navmesh, fights at the skill its preset sets, dives out of the way, picks
// up better weapons, and keeps count of what it did.
//
//   node tools/bot/drive.mjs --navmesh <map.navmesh.json> [--skill regular]
//        [--set field=value ...] [--seconds 120] [--player 0] [--no-dive]
//        [--goto x,y,z] [--log]
//
// --skill is a preset of presets.mjs (recruit, regular, heroic, legendary);
// --set overrides one of its fields. --goto walks to a point (wu) instead of
// hunting: a route test. The last line printed is the run's tally as JSON.
//
// The navmesh comes from `mjolnir level navmesh` on the map's structure BSP.
// The game needs MJOLNIRBridge with mjolnir_test_input.dll (game_input's
// in-game route); nothing here touches the desktop's mouse or keyboard.
//
// Each tick (about 10 a second):
//   - world.mjs's latest read of the simulation (about two a second): the
//     bot's shield and body, every living enemy and where it faces, weapons
//     on the ground and in hand. A dead biped stays an object and an actor
//     far away is hidden, so the simulation picks the target;
//   - one game_lua call reads the camera, whether the reticle is locked on
//     an enemy (MyHUD.AimAssistInfo.FullyTargetedActor), and the target's
//     bone once its actor shows;
//   - brain.mjs decides the fight (aim wander, trigger, side-steps, melee,
//     grenades, dives, weapon swaps); this file walks routes, steers past
//     what stands in the way, and sends the keys. The view turns through the
//     input DLL's `glide`, spread over the frames, so it never snaps.
//
// A dive is the AI's own animation (`combat:rifle:dive_left` and the like in
// the Spartan's graph), played on the player's unit with the simulation's
// `custom_animation`; it moves the unit about 4 m.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bridgeCall, callTool, paths } from "../mcp/game/game.mjs";
import { parseAck } from "../mcp/game/in_game_input.mjs";
import {
  appliedSince, chooseTarget, chooseWeapon, fight, fitVelocity, M_PER_WU, newMemory, onBody, track, turnTo,
} from "./brain.mjs";
import { Navmesh } from "./navmesh.mjs";
import { KEYS, preset } from "./presets.mjs";
import { World } from "./world.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../..");
const WU = 304.8; // Unreal cm per world unit; Unreal y is the simulation's -y
const EYE = 0.62; // the camera above a standing biped's feet, wu
const DEG_PER_COUNT = 0.104; // one look count turns the view this far
const SPARTAN_GRAPH = "objects\\characters\\spartans\\spartans";

function args() {
  const a = { seconds: 120, skill: "regular", set: [], player: 0, log: false, dive: true, navmesh: null, goto: null };
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i].replace(/^--/, "");
    if (k === "log") a.log = true;
    else if (k === "no-dive") a.dive = false;
    else if (k === "set") a.set.push(argv[++i]);
    else a[k] = typeof a[k] === "number" ? Number(argv[++i]) : argv[++i];
  }
  if (!a.navmesh) throw new Error("--navmesh <file> is required (mjolnir level navmesh)");
  return a;
}

const toUE = (p) => [p[0] * WU, -p[1] * WU, p[2] * WU];
const toWU = (p) => [p[0] / WU, -p[1] / WU, p[2] / WU];
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// --- What the game shows ---------------------------------------------------

// One call a tick. MJ_BOT keeps the controller and the biped actors between
// calls; the actors are found again every 3 s (FindAllOf costs ~20 ms).
function perceive(bone, target, reach = 600) {
  const t = target ? `{${toUE(target).map((v) => v.toFixed(1)).join(",")}}` : "nil";
  return `
local TARGET = ${t}
MJ_BOT = MJ_BOT or {}
local B = MJ_BOT
if not (B.pc and B.pc:IsValid()) then
    B.pc = nil
    for _, c in ipairs(FindAllOf("BP_MeteoritePlayerController_C") or {}) do
        if c:IsValid() and c:IsLocalController() and c.PlayerCameraManager:IsValid() then B.pc = c end
    end
end
local pc = B.pc
if not pc then return "none" end
local cam = pc.PlayerCameraManager
local at, rot = cam:GetCameraLocation(), cam:GetCameraRotation()
local locked = 0
pcall(function()
    local info = pc.MyHUD.AimAssistInfo
    local a = info.FullyTargetedActor
    if a and a:IsValid() and not info.AutoAimFlags.bFriendly then locked = 1 end
end)
local aim = "-"
if TARGET then
    if os.clock() - (B.listed or -100) > 3 then
        B.actors = FindAllOf("BP_SpartansBipedActor_C") or {}
        B.listed = os.clock()
    end
    -- The showing actor nearest where the target was last known, and not
    -- this player's own (under the camera).
    local best, bestD
    for _, b in ipairs(B.actors) do
        local ok, l = pcall(function() return b:K2_GetActorLocation() end)
        if ok and b:IsValid() and not b.bHidden then
            local d = math.sqrt((l.X - TARGET[1]) ^ 2 + (l.Y - TARGET[2]) ^ 2)
            local own = math.sqrt((l.X - at.X) ^ 2 + (l.Y - at.Y) ^ 2) < 120
            if d < ${reach} and not own and (not bestD or d < bestD) then best, bestD = b, d end
        end
    end
    if best then
        local mesh = best:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.SkeletalMeshComponent"))[1]
        if type(mesh) ~= "userdata" or not mesh.GetFName then mesh = mesh:get() end
        local p = mesh:GetSocketLocation(FName("${bone}"))
        aim = string.format("%.1f,%.1f,%.1f", p.X, p.Y, p.Z)
    end
end
return string.format("%.1f %.1f %.1f %.3f %.3f %d %s", at.X, at.Y, at.Z, rot.Yaw, rot.Pitch, locked, aim)`;
}

// A walker's half width plus room to spare, wu.
const CLEAR = 0.7 / 3.048;

/** Heading (deg, plan) from p toward q, bent past the collision standing in
 *  the way (the navmesh's walls: trees, rocks) within `ahead` wu. The
 *  obstacle is every wall side within a walker's reach of the line around
 *  the first one hit; it is passed on the side that turns less, its
 *  outermost point cleared by CLEAR. */
export function steer(mesh, p, q, z, ahead = 4) {
  const straight = (Math.atan2(q[1] - p[1], q[0] - p[0]) * 180) / Math.PI;
  const length = Math.hypot(q[0] - p[0], q[1] - p[1]);
  if (length < 1e-6) return { heading: straight, around: false };
  const ux = (q[0] - p[0]) / length;
  const uy = (q[1] - p[1]) / length;
  const reach = Math.min(ahead, length);
  const end = [p[0] + ux * reach, p[1] + uy * reach];
  const hits = mesh.wallsAlong(p, end, z, CLEAR);
  if (!hits.length) return { heading: straight, around: false };
  const first = Math.min(...hits.map((h) => h.along));
  // The obstacle: the sides near the first hit, with what stands beside them.
  const near = mesh.wallsAlong(p, [p[0] + ux * (first + 1.5), p[1] + uy * (first + 1.5)], z, CLEAR * 4)
    .filter((h) => h.along <= first + 1.0);
  let left = null;
  let right = null;
  for (const h of near) {
    for (const pt of [h.wall.a, h.wall.b]) {
      const along = (pt[0] - p[0]) * ux + (pt[1] - p[1]) * uy;
      if (along <= 0) continue;
      const side = (pt[1] - p[1]) * ux - (pt[0] - p[0]) * uy; // + left of the line
      const angleLeft = Math.atan2(side + CLEAR, along);
      const angleRight = Math.atan2(side - CLEAR, along);
      if (left === null || angleLeft > left) left = angleLeft;
      if (right === null || angleRight < right) right = angleRight;
    }
  }
  if (left === null) return { heading: straight, around: false };
  // Turn left by `left` or right by `-right`, whichever is less.
  const turn = left < -right ? left : right;
  return { heading: straight + (turn * 180) / Math.PI, around: true };
}

function parseView(body) {
  const line = String(body).trim().split("\n").pop().replace(/^= /, "");
  const f = line.split(" ");
  if (f.length < 7) return null;
  const n = f.slice(0, 6).map(Number);
  return {
    camera: [n[0], n[1], n[2]], yaw: n[3], pitch: n[4], locked: n[5] === 1,
    bone: f[6] === "-" ? null : f[6].split(",").map(Number),
  };
}

// The bridge renames its request into place; while the game still has the
// last one open Windows refuses (EPERM), so a call is tried again briefly.
async function lua(code) {
  for (let attempt = 0; ; attempt++) {
    try {
      return await bridgeCall("lua", code);
    } catch (error) {
      if (error.code !== "EPERM" || attempt >= 40) throw error;
      await new Promise((r) => setTimeout(r, 5));
    }
  }
}

// --- Input -------------------------------------------------------------------

class Hands {
  constructor() {
    this.keys = new Map(); // vk -> down
    this.fire = false;
  }
  // One script a tick: held keys that changed, taps, the trigger, the glide.
  async send(want) {
    const lines = [];
    for (const [vk, down] of want.keys) {
      if ((this.keys.get(vk) ?? false) !== down) {
        lines.push(`key ${vk} ${down ? 1 : 0}`);
        this.keys.set(vk, down);
      }
    }
    // A press that ends between two reads is still delivered once.
    for (const vk of want.taps ?? []) {
      if (!this.keys.get(vk)) lines.push(`key ${vk} 1`, `key ${vk} 0`);
    }
    if (want.fire !== this.fire) {
      lines.push(`button 1 ${want.fire ? 1 : 0}`);
      this.fire = want.fire;
    }
    lines.push(`glide ${Math.round(want.look[0])} ${Math.round(want.look[1])} ${want.glideMs}`);
    await this.script(lines);
  }
  async script(lines) {
    const { bridge } = paths();
    const ack = path.join(bridge, "input_ack.txt");
    const id = Date.now() % 1_000_000_000;
    fs.rmSync(ack, { force: true });
    const temporary = path.join(bridge, `input_cmd.${id}.tmp`);
    fs.writeFileSync(temporary, [`id ${id}`, ...lines, ""].join("\n"));
    for (let attempt = 0; ; attempt++) {
      try {
        fs.renameSync(temporary, path.join(bridge, "input_cmd.txt"));
        break;
      } catch (error) {
        if (error.code !== "EPERM" || attempt >= 40) throw error;
        await new Promise((r) => setTimeout(r, 5));
      }
    }
    const deadline = Date.now() + 1000;
    while (Date.now() < deadline) {
      const reply = fs.existsSync(ack) ? parseAck(fs.readFileSync(ack, "utf8"), id) : null;
      if (reply) {
        if (!reply.ok) throw new Error(`input: ${reply.error}`);
        return;
      }
      await new Promise((r) => setTimeout(r, 3));
    }
  }
  async release() {
    this.keys.clear();
    this.fire = false;
    await this.script(["release"]);
  }
}

/** The AI's dive, on this player's unit. Not waited for. */
function dive(side, player) {
  const command = `blam (custom_animation (unit (list_get (players) ${player})) ${SPARTAN_GRAPH} "combat:rifle:dive_${side}" true)`;
  callTool("game_console", { command }).catch(() => {});
}

// --- The loop ----------------------------------------------------------------

async function main() {
  const a = args();
  const skill = preset(a.skill, a.set);
  const mesh = Navmesh.load(fs.readFileSync(a.navmesh, "utf8"));
  const world = new World(path.join(REPO, "target", "debug", "mjolnir.exe"), a.player);
  world.start();
  // The input worker: game_input starts it once (its first call waits ~3 s).
  await callTool("game_input", { steps: [{ wait: 1 }] });
  const hands = new Hands();
  const mem = newMemory();
  const rng = Math.random;
  const say = (...m) => a.log && console.log(new Date().toISOString().slice(11, 23), ...m);
  say(`skill ${skill.name}; navmesh: ${mesh.sectors.length} areas, ${mesh.sectors.filter((x) => x.blocked).length} blocked, ${mesh.walls.length} wall sides`);

  let feet = null;
  let last = { at: Date.now(), pos: null };
  let unstickUntil = 0;
  let crouchUntil = 0;
  let dead = false;
  let lastFire = { at: -1e9, handle: null };
  let aimed = { handle: null, samples: [], velocity: [0, 0, 0] };
  const eye = { samples: [], velocity: [0, 0, 0] };
  let glide = { yaw: null, pitch: null };
  let seen = { handle: null, at: 0, pos: null };
  let foughtAt = -1e9;
  let going = { key: null, since: 0 };
  const givenUp = new Set();
  let heldBefore = null;
  let seq = -1;
  const started = Date.now();
  const end = started + a.seconds * 1000;
  let tick = Date.now();

  const routeLength = (from, to) => {
    const r = mesh.route(from, to);
    if (!r) return Math.hypot(to[0] - from[0], to[1] - from[1]) * 3; // off the mesh: a last resort
    let length = 0;
    let at = from;
    for (const p of r.points) {
      length += Math.hypot(p[0] - at[0], p[1] - at[1]);
      at = p;
    }
    return length;
  };

  // The end of the match. MJOLNIRHud writes the results the moment a match
  // ends, seconds before it takes everyone back to the lobby; the level's
  // actors are freed on the way, and a call on one of the handles the Lua
  // keeps crashed the game (2026-11-10). So the bot stops at the results.
  const results = path.join(paths().bridge, "..", "Mods", "MJOLNIRHud", "last_match.txt");
  const resultsAt = () => {
    try { return fs.statSync(results).mtimeMs; } catch { return 0; }
  };
  const resultsBefore = resultsAt();

  try {
    while (Date.now() < end) {
      const t0 = Date.now();
      if (resultsAt() !== resultsBefore) {
        say("the match is over: stopping");
        break;
      }
      const now = (t0 - started) / 1000;
      const dt = Math.min(0.3, (t0 - tick) / 1000);
      tick = t0;
      const w = world.now;

      // The tally: a death once per life; a kill when the enemy just fired on is gone.
      if (w.seq !== seq) {
        seq = w.seq;
        const alive = Boolean(w.me && w.me.alive);
        if (!alive && !dead && w.me) mem.stats.deaths++;
        dead = !alive && Boolean(w.me);
        if (lastFire.handle && now - lastFire.at < 3 && !w.enemies.some((e) => e.handle === lastFire.handle)) {
          mem.stats.kills++;
          say(`kill ${mem.stats.kills}`);
          lastFire = { at: -1e9, handle: null };
        }
        if (heldBefore && alive) {
          for (const kind of w.held) if (!heldBefore.includes(kind)) { mem.stats.pickups++; say(`picked up ${kind}`); }
        }
        if (alive) heldBefore = w.held;
      }

      // Who and what, from where the last tick saw this player.
      let target = null;
      let weapon = null;
      if (a.goto) {
        const g = String(a.goto).split(",").map(Number);
        // No height given: the floor there is about this player's own.
        target = { handle: "goto", pos: [g[0], g[1], Number.isFinite(g[2]) ? g[2] : feet ? feet[2] : 0], yaw: 0, body: 1 };
      } else if (feet) {
        const pick = chooseTarget(w.enemies, (e) => routeLength(feet, e.pos), skill);
        if (pick) target = pick.enemy;
        if (now - foughtAt > 4) { // not in, or just out of, a fight
          const key = (g) => `${g.kind}@${g.pos[0].toFixed(1)},${g.pos[1].toFixed(1)}`;
          const found = chooseWeapon(w.ground.filter((g) => !givenUp.has(key(g))), w.held,
            (g) => routeLength(feet, g.pos), skill);
          if (found) {
            weapon = found.weapon;
            // One it cannot get (out of reach, or hands full): 10 s, then never again.
            if (going.key !== key(weapon)) going = { key: key(weapon), since: now };
            else if (now - going.since > 10) {
              givenUp.add(going.key);
              say(`gave up on ${going.key}`);
              weapon = null;
            }
          }
        }
      }

      // The simulation's read is up to half a second old, and a runner covers
      // metres in that: look for the target where it was last seen.
      const fresh = target && seen.handle === target.handle && t0 - seen.at < 1500;
      const reply = await lua(perceive(mem.bone, target ? (fresh ? seen.pos : target.pos) : null, fresh ? 400 : 700));
      // When the game read its camera: just before the reply came back.
      const readAt = Date.now() - 15;
      const view = parseView(reply.body);
      if (!view || dead) {
        if (hands.keys.size || hands.fire) await hands.release();
        say(dead ? "dead" : `no view: ${String(reply.body).slice(0, 80)}`);
        await new Promise((r) => setTimeout(r, 300));
        continue;
      }
      const me = toWU(view.camera);
      const before = feet;
      feet = [me[0], me[1], me[2] - EYE];
      // This player's own motion (UE cm/s): the view swings as it side-steps.
      eye.velocity = fitVelocity(track(eye.samples, readAt / 1000, view.camera));
      const speed = before && dt > 0 ? (Math.hypot(feet[0] - before[0], feet[1] - before[1]) * WU) / 100 / dt : 0; // m/s

      // The target's bone, and how it is moving (for the lead).
      // Its actor shows: where it is, and (a line fitted through its last
      // half second) how it is moving.
      const showing = Boolean(!a.goto && target && view.bone);
      if (showing) {
        if (aimed.handle !== target.handle) aimed = { handle: target.handle, samples: [], velocity: [0, 0, 0] };
        aimed.velocity = fitVelocity(track(aimed.samples, readAt / 1000, view.bone));
        seen = { handle: target.handle, at: t0, pos: toWU(view.bone) };
      }
      // Visible: showing, with nothing solid between the eye and the bone.
      const visible = showing && mesh.sight(me, toWU(view.bone));
      const targetAt = visible ? toWU(view.bone) : target ? target.pos : null;
      const distance = targetAt ? Math.hypot(targetAt[0] - feet[0], targetAt[1] - feet[1]) * M_PER_WU : Infinity;

      // Room to dive: nothing standing within a dive's length to that side.
      const forward = [Math.cos((view.yaw * Math.PI) / 180), -Math.sin((view.yaw * Math.PI) / 180)]; // plan, wu
      const leftward = [-forward[1], forward[0]];
      const room = (sign) => !mesh.firstWall(feet, [feet[0] + leftward[0] * 1.6 * sign, feet[1] + leftward[1] * 1.6 * sign], feet[2], CLEAR);
      // The aim point: the bone, led by how it and this player are moving.
      const aimPoint = visible
        ? [0, 1, 2].map((i) => view.bone[i] + (aimed.velocity[i] - eye.velocity[i]) * skill.lead)
        : null;
      const offBone = visible ? turnTo(view.camera, view.yaw, view.pitch, view.bone) : [180, 180];
      const f = fight({
        now, dt, worldSeq: w.seq, onTarget: visible && onBody(offBone, distance), me: { pos: feet, shield: w.me ? w.me.shield : 1, body: w.me ? w.me.body : 1 },
        target: a.goto ? null : target, visible, locked: view.locked, distance,
        canDive: { left: room(1), right: room(-1) },
      }, mem, skill, rng);

      // Where to look, and where to walk.
      let look = null;
      let around = false;
      let walking = false;
      let using = false;
      const toward = (point) => {
        let r = mesh.route(feet, point);
        if (!r) {
          // Nowhere this player can walk to (a roof, a ledge): the nearest
          // ground it can reach, never a straight line at a wall.
          const near = mesh.reachableNear(feet, point);
          if (!near || Math.hypot(near[0] - feet[0], near[1] - feet[1]) < 0.5) return null;
          point = near;
          r = mesh.route(feet, point);
        }
        let next = point;
        if (r && r.points.length) {
          next = r.points[0];
          if (Math.hypot(next[0] - feet[0], next[1] - feet[1]) < 0.4 && r.points[1]) next = r.points[1];
        }
        const way = steer(mesh, feet, next, feet[2]);
        around = way.around;
        const far = Math.max(1, Math.hypot(next[0] - feet[0], next[1] - feet[1]));
        const h = (way.heading * Math.PI) / 180;
        return toUE([feet[0] + Math.cos(h) * far, feet[1] + Math.sin(h) * far, next[2] + EYE]);
      };
      let mode = "idle";
      if (f.engaged) {
        mode = f.retreating ? "retreat" : "engage";
        look = aimPoint;
      } else if (weapon) {
        mode = "weapon";
        const gap = Math.hypot(weapon.pos[0] - feet[0], weapon.pos[1] - feet[1]);
        look = toward(weapon.pos);
        walking = gap > 0.25 && look !== null;
        using = gap < 1.0; // hold the pick-up key over it
      } else if (target) {
        mode = "hunt";
        look = toward(target.pos);
        walking = look !== null;
        // Nowhere nearer to walk: face it and wait for it to show.
        if (!look) look = toUE([target.pos[0], target.pos[1], target.pos[2] + EYE]);
      }
      let [dyaw, dpitch] = look ? turnTo(view.camera, view.yaw, view.pitch, look, f.engaged ? f.noise : [0, 0]) : [0, 0];
      if (!f.engaged) dpitch = clamp(dpitch, -20, 20);
      // Turn at a limited rate, spread over the next ticks: smooth, and a
      // newer tick takes over what is left.
      // The camera was read a moment ago, and the last turn has gone on
      // since: that part is already done, and asking for it again is what
      // swung the aim past the target.
      const sendAt = Date.now();
      dyaw -= appliedSince(glide.yaw, readAt / 1000, sendAt / 1000);
      dpitch -= appliedSince(glide.pitch, readAt / 1000, sendAt / 1000);
      // Close enough, a skilled aim sticks to the bone: no rate limit, one
      // frame's glide.
      const locking = f.engaged && skill.lockOn > 0 && Math.hypot(dyaw, dpitch) <= skill.lockOn;
      const rate = locking ? Infinity : f.engaged ? skill.turnRate : 200; // deg/s
      const span = locking ? 0.05 : f.engaged ? 0.12 : 0.25; // s: tight on a target, easy on a route
      const turnYaw = locking ? dyaw : clamp(dyaw, -rate * span, rate * span);
      const turnPitch = locking ? dpitch : clamp(dpitch, -rate * span, rate * span);
      glide = {
        yaw: { amount: turnYaw, at: sendAt / 1000, span },
        pitch: { amount: turnPitch, at: sendAt / 1000, span },
      };

      // Stuck walking: whatever is ahead is not walkable after all (a wall the
      // navmesh missed, a vehicle). The ground there is blocked for the rest
      // of the run, so the next route goes another way, and the bot backs
      // out with a jump and a step aside.
      if (walking && last.pos && t0 - last.at > 1500) {
        if (Math.hypot(feet[0] - last.pos[0], feet[1] - last.pos[1]) < 0.3) {
          unstickUntil = t0 + 600;
          const blocked = mesh.block([feet[0] + forward[0] * 0.8, feet[1] + forward[1] * 0.8], 0.6);
          say(`stuck: ${blocked} area(s) ahead blocked; backing out`);
        }
        last = { at: t0, pos: feet };
      } else if (!last.pos || !walking) {
        last = { at: t0, pos: feet };
      }
      const unsticking = t0 < unstickUntil;
      if (f.hold.crouch) crouchUntil = t0 + 350;
      if (f.dive && a.dive) {
        dive(f.dive, a.player);
        say(`dive ${f.dive}`);
      }
      if (f.fire) lastFire = { at: now, handle: target.handle };
      if (f.engaged) foughtAt = now;

      const straight = Math.abs(dyaw) < 60;
      await hands.send({
        keys: [
          [KEYS.forward, !unsticking && ((walking && straight) || f.hold.forward)],
          [KEYS.back, f.hold.back || unsticking],
          [KEYS.left, f.hold.left],
          [KEYS.right, f.hold.right || unsticking],
          // Sprint on a straight stretch; not while turning hard or fighting.
          [KEYS.sprint, skill.sprint && walking && !f.engaged && Math.abs(dyaw) < 20],
          [KEYS.jump, unsticking],
          [KEYS.crouch, t0 < crouchUntil],
          [KEYS.use, using],
        ],
        taps: f.taps.map((name) => KEYS[name]),
        fire: f.fire,
        look: [turnYaw / DEG_PER_COUNT, -turnPitch / DEG_PER_COUNT],
        glideMs: Math.round(span * 1000),
      });
      say(mode, Number.isFinite(distance) ? `${distance.toFixed(1)} m` : "-",
        `yaw ${dyaw.toFixed(1)} pitch ${dpitch.toFixed(1)}`, view.locked ? "LOCKED" : "", f.fire ? "FIRE" : "",
        f.taps.join("+"), around ? "AROUND" : "",
        visible ? `off ${offBone[0].toFixed(1)}` : showing ? "NO-SIGHT" : "", locking ? "LOCK" : "", `shield ${(w.me ? w.me.shield : 1).toFixed(2)}`,
        `${speed.toFixed(1)} m/s`, `at ${feet[0].toFixed(2)},${feet[1].toFixed(2)}`, `${Date.now() - t0} ms`);
      // About 10 a second.
      const wait = 100 - (Date.now() - t0);
      if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    }
  } finally {
    world.stop();
    // Nothing kept in the game's Lua outlives the run.
    await lua("MJ_BOT = nil return 1").catch(() => {});
    await hands.release().catch(() => {});
    console.log(JSON.stringify({ skill: skill.name, seconds: Math.round((Date.now() - started) / 1000), ...mem.stats }));
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
