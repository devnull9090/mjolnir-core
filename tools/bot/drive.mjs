// A test bot that plays the local player: it walks the navmesh to the closest
// living enemy, turns smoothly, and fires while the reticle is locked on.
//
//   node tools/bot/drive.mjs --navmesh <map.navmesh.json> [--seconds 120]
//        [--bone Head_M] [--engage 30] [--stop 6] [--goto x,y,z] [--log]
//
// --goto walks to a point (wu) instead of hunting: a route test.
//
// The navmesh comes from `mjolnir level navmesh` on the map's structure BSP.
// The game needs MJOLNIRBridge with mjolnir_test_input.dll (game_input's
// in-game route); nothing here touches the desktop's mouse or keyboard.
//
// Each tick (about 10 a second):
//   - the simulation's bipeds (`mjolnir live objects`, refreshed in the
//     background every second) give where every enemy is and who is alive:
//     an actor far away is hidden, and a dead biped stays an object;
//   - one game_lua call reads the camera, whether the reticle is locked on
//     an enemy (MyHUD.AimAssistInfo.FullyTargetedActor), and, when the
//     target's actor is showing, the bone to aim at;
//   - the target is the enemy closest by route; the view turns toward the
//     route's next corner, or the bone once engaged, through the input DLL's
//     `glide` (spread over the frames, so it never snaps); W stays down while
//     walking, Shift too on a straight stretch (sprint); fire is held while
//     the reticle is locked.
//
// Obstacles: what stands on the ground (trees, rocks) is collision the AI
// pathfinding does not see; the navmesh export marks the areas it stands in
// as blocked, so routes go around, and lists its sides as walls, which the
// driver steers past close in.
import { execFile } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bridgeCall, callTool, paths } from "../mcp/game/game.mjs";
import { parseAck } from "../mcp/game/in_game_input.mjs";
import { Navmesh } from "./navmesh.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../..");
const WU = 304.8; // Unreal cm per world unit; Unreal y is the simulation's -y
const EYE = 0.62; // the camera above a standing biped's feet, wu
const DEG_PER_COUNT = 0.104; // one look count turns the view this far

function args() {
  const a = { seconds: 120, bone: "Head_M", engage: 30, stop: 6, log: false, navmesh: null, goto: null };
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i].replace(/^--/, "");
    if (k === "log") a.log = true;
    else a[k] = typeof a[k] === "number" ? Number(argv[++i]) : argv[++i];
  }
  if (!a.navmesh) throw new Error("--navmesh <file> is required (mjolnir level navmesh)");
  return a;
}

const toUE = (p) => [p[0] * WU, -p[1] * WU, p[2] * WU];
const toWU = (p) => [p[0] / WU, -p[1] / WU, p[2] / WU];
const wrap = (deg) => ((deg + 540) % 360) - 180;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// --- The simulation's bipeds, in the background -------------------------

class Enemies {
  constructor() {
    this.list = []; // { pos: [x, y, z] wu }
    this.tsv = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "mjolnir-bot-")), "bipd.tsv");
    this.busy = false;
    this.exe = path.join(REPO, "target", "debug", "mjolnir.exe");
  }
  refresh() {
    if (this.busy) return;
    this.busy = true;
    execFile(this.exe, ["live", "objects", "--group", "bipd", "--tsv", this.tsv], () => {
      this.busy = false;
      try {
        // Columns: 6-8 position, 9 body vitality ("100% of 105"), 12 "player N"
        // for a player's own biped.
        this.list = fs.readFileSync(this.tsv, "utf8").trim().split("\n").slice(1)
          .map((line) => line.split("\t"))
          .filter((f) => !/player/.test(f[11] ?? "") && /^[1-9][0-9]*%/.test(f[8] ?? ""))
          .map((f) => ({ pos: [Number(f[5]), Number(f[6]), Number(f[7])] }));
      } catch { /* the next refresh */ }
    });
  }
}

// --- What the game shows ---------------------------------------------------

// One call a tick. MJ_BOT keeps the controller and the biped actors between
// calls; the actors are found again every 3 s (FindAllOf costs ~20 ms).
function perceive(bone, target) {
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
    for _, b in ipairs(B.actors) do
        local ok, l = pcall(function() return b:K2_GetActorLocation() end)
        if ok and b:IsValid() and not b.bHidden
            and math.sqrt((l.X - TARGET[1]) ^ 2 + (l.Y - TARGET[2]) ^ 2) < 150 then
            local mesh = b:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.SkeletalMeshComponent"))[1]
            if type(mesh) ~= "userdata" or not mesh.GetFName then mesh = mesh:get() end
            local p = mesh:GetSocketLocation(FName("${bone}"))
            aim = string.format("%.1f,%.1f,%.1f", p.X, p.Y, p.Z)
            break
        end
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
  // One script a tick: key and button changes, then the glide.
  async send(want) {
    const lines = [];
    for (const [vk, down] of want.keys) {
      if ((this.keys.get(vk) ?? false) !== down) {
        lines.push(`key ${vk} ${down ? 1 : 0}`);
        this.keys.set(vk, down);
      }
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
    await this.script(["release"]);
  }
}

// --- The brain ---------------------------------------------------------------

const VK_W = 87;
const VK_SPACE = 32;
const VK_D = 68;
const VK_SHIFT = 160; // left Shift: the simulation tracks the two sides apart

async function main() {
  const a = args();
  const mesh = Navmesh.load(fs.readFileSync(a.navmesh, "utf8"));
  const enemies = new Enemies();
  enemies.refresh();
  const refresher = setInterval(() => enemies.refresh(), 1000);
  // The input worker: game_input starts it once (its first call waits ~3 s).
  await callTool("game_input", { steps: [{ wait: 1 }] });
  const hands = new Hands();
  const say = (...m) => a.log && console.log(new Date().toISOString().slice(11, 23), ...m);
  say(`navmesh: ${mesh.sectors.length} areas, ${mesh.sectors.filter((x) => x.blocked).length} blocked, ${mesh.walls.length} wall sides`);

  let feet = null;
  let last = { at: Date.now(), pos: null };
  let unstickUntil = 0;
  const end = Date.now() + a.seconds * 1000;
  let tick = Date.now();
  try {
    while (Date.now() < end) {
      const t0 = Date.now();
      const dt = Math.min(0.3, (t0 - tick) / 1000);
      tick = t0;

      // Who: the living enemy closest by route (a straight line can be a
      // wall), from where the last tick saw this player.
      let target = null;
      if (a.goto) {
        const g = String(a.goto).split(",").map(Number);
        // No height given: the floor there is about this player's own.
        target = { pos: [g[0], g[1], Number.isFinite(g[2]) ? g[2] : feet ? feet[2] : 0], length: 0 };
      } else if (feet) {
        for (const e of enemies.list) {
          const r = mesh.route(feet, e.pos);
          const length = r
            ? r.points.reduce((sum, p, i) => sum + Math.hypot(p[0] - (i ? r.points[i - 1][0] : feet[0]),
              p[1] - (i ? r.points[i - 1][1] : feet[1])), 0)
            : Math.hypot(e.pos[0] - feet[0], e.pos[1] - feet[1]) * 3; // off the mesh: a last resort
          if (!target || length < target.length) target = { pos: e.pos, length, route: r };
        }
      }
      const reply = await lua(perceive(a.bone, target ? target.pos : null));
      const view = parseView(reply.body);
      if (!view) {
        say("no view:", String(reply.body).slice(0, 80));
        await new Promise((r) => setTimeout(r, 300));
        continue;
      }
      const me = toWU(view.camera);
      const before = feet;
      feet = [me[0], me[1], me[2] - EYE];
      const speed = before && dt > 0 ? (Math.hypot(feet[0] - before[0], feet[1] - before[1]) * WU) / 100 / dt : 0; // m/s
      const route = target ? mesh.route(feet, target.pos) : null;
      const dist = target ? Math.hypot(target.pos[0] - feet[0], target.pos[1] - feet[1]) * WU / 100 : Infinity; // m
      const engaged = Boolean(!a.goto && target && view.bone && dist < a.engage);

      // Where to look.
      let look;
      let around = false;
      if (engaged) {
        look = view.bone;
      } else if (route && route.points.length) {
        // The next corner a little way ahead, at eye height.
        let next = route.points[0];
        if (Math.hypot(next[0] - feet[0], next[1] - feet[1]) < 0.4 && route.points[1]) next = route.points[1];
        const way = steer(mesh, feet, next, feet[2]);
        around = way.around;
        const far = Math.hypot(next[0] - feet[0], next[1] - feet[1]);
        const h = (way.heading * Math.PI) / 180;
        look = toUE([feet[0] + Math.cos(h) * far, feet[1] + Math.sin(h) * far, next[2] + EYE]);
      } else if (target) {
        // Off the mesh: straight at it, still past what stands in the way.
        const way = steer(mesh, feet, target.pos, feet[2]);
        around = way.around;
        const far = Math.hypot(target.pos[0] - feet[0], target.pos[1] - feet[1]);
        const h = (way.heading * Math.PI) / 180;
        look = toUE([feet[0] + Math.cos(h) * far, feet[1] + Math.sin(h) * far, target.pos[2] + EYE]);
      }
      let dyaw = 0;
      let dpitch = 0;
      if (look) {
        const d = [look[0] - view.camera[0], look[1] - view.camera[1], look[2] - view.camera[2]];
        dyaw = wrap((Math.atan2(d[1], d[0]) * 180) / Math.PI - view.yaw);
        dpitch = (Math.atan2(d[2], Math.hypot(d[0], d[1])) * 180) / Math.PI - view.pitch;
        if (!engaged) dpitch = clamp(dpitch, -20, 20);
      }
      // Turn at a limited rate, spread over the next ticks: smooth, and a
      // newer tick takes over what is left.
      const rate = engaged ? 360 : 200; // deg/s
      const span = engaged ? 0.12 : 0.25; // s: tight on a target, easy on a route
      const turnYaw = clamp(dyaw, -rate * span, rate * span);
      const turnPitch = clamp(dpitch, -rate * span, rate * span);

      // Walk unless engaged and close; stuck walking means a jump and a step aside.
      const walking = Boolean(target) && !(engaged && dist < a.stop);
      if (walking && last.pos && t0 - last.at > 1500) {
        if (Math.hypot(feet[0] - last.pos[0], feet[1] - last.pos[1]) < 0.3) {
          unstickUntil = t0 + 500;
          say("stuck: jump and step aside");
        }
        last = { at: t0, pos: feet };
      } else if (!last.pos || !walking) {
        last = { at: t0, pos: feet };
      }
      const unsticking = t0 < unstickUntil;

      await hands.send({
        keys: [
          [VK_W, walking && Math.abs(dyaw) < 60],
          // Sprint on a straight stretch; not while turning hard or fighting.
          [VK_SHIFT, walking && !engaged && Math.abs(dyaw) < 20],
          [VK_SPACE, unsticking],
          [VK_D, unsticking],
        ],
        fire: view.locked, // red reticle: an enemy is under it
        look: [turnYaw / DEG_PER_COUNT, -turnPitch / DEG_PER_COUNT],
        glideMs: Math.round(span * 1000),
      });
      say(engaged ? "engage" : walking ? "walk" : "idle", target ? `${dist.toFixed(1)} m` : "-",
        `yaw ${dyaw.toFixed(1)} pitch ${dpitch.toFixed(1)}`, view.locked ? "LOCKED" : "",
        route ? `${route.points.length} corners` : "no route", around ? "AROUND" : "", `${speed.toFixed(1)} m/s`, `at ${feet[0].toFixed(2)},${feet[1].toFixed(2)}`, `${Date.now() - t0} ms`, `dt ${dt.toFixed(2)}`);
      // About 10 a second.
      const wait = 100 - (Date.now() - t0);
      if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    }
  } finally {
    clearInterval(refresher);
    await hands.release();
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
