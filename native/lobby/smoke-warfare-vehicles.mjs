#!/usr/bin/env node
// Explicit private-match vehicle acceptance. No hosting, installation, variant
// changes, vehicle creation/deletion, kills, or remote-player manipulation.
// Run AFTER insertion smoke: node native/lobby/smoke-warfare-vehicles.mjs --drive
// Optional: --screenshots --seconds=4 --team=red|blue --banshee-ascend
// --vehicle=hog|tank|banshee repeats only that vehicle after an earlier stopped
// run. It retains every occupancy/volume/health guard and records the subset.
// Does not explicitly exit the last vehicle; failure releases used keys and stops.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const METRES_PER_WU = 3.048;
const VEHICLES = [
  { kind: 'hog', tag: 'objects\\vehicles\\human\\warthog\\warthog', seat: 'warthog_d', minimumMetres: 1 },
  { kind: 'tank', tag: 'objects\\vehicles\\human\\scorpion\\scorpion', seat: 'scorpion_d', minimumMetres: 0.5 },
  { kind: 'banshee', tag: 'objects\\vehicles\\covenant\\banshee\\banshee', seat: 'banshee_d', minimumMetres: 1 },
];
const check = (condition, message) => { if (!condition) throw new Error(message); };
const finite3 = p => Array.isArray(p) && p.length === 3 && p.every(Number.isFinite);
const handle = text => /^0x[\da-f]{8}$/i.test(text) ? Number.parseInt(text.slice(2), 16) : null;
const dot = (a, b) => a.reduce((sum, n, i) => sum + n * b[i], 0);
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const metres = p => p.map(x => x * METRES_PER_WU);
const distance = (a, b) => Math.hypot(...a.map((x, i) => x - b[i]));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export function parseObjects(raw) {
  const objects = [];
  for (const line of raw.split(/\r?\n/)) {
    if (!/^\d+\t0x/i.test(line)) continue;
    const f = line.split('\t');
    const body = /^(\d+)% of (\d+)$/.exec(f[8]);
    const row = { index: Number(f[0]), handle: handle(f[1]), kind: f[2], group: f[3], tag: f[4]?.toLowerCase(),
      position: f.slice(5, 8).map(Number), healthPercent: body ? Number(body[1]) : null,
      maximumHealth: body ? Number(body[2]) : null, parent: f[10] === '-' ? null : handle(f[10]), player: f[11], yaw: Number(f[12]) };
    check(f.length === 15 && row.handle !== null && finite3(row.position) && Number.isFinite(row.yaw)
      && (f[10] === '-' || row.parent !== null), `Malformed live object row: ${line}`);
    check(!objects.some(o => o.handle === row.handle), 'Duplicate live object handle');
    objects.push(row);
  }
  check(/^\d+ of \d+ objects \(thread /m.test(raw) && objects.length > 0, 'No complete live object inventory');
  check(!/layout may have moved/.test(raw), 'Live object layout could not be verified');
  return objects;
}

export function parsePlayers(raw) {
  const players = [];
  for (const line of raw.split(/\r?\n/)) {
    if (!/^player \d+\t/.test(line)) continue;
    const f = line.split('\t');
    check(f.length === 8 && /^unit 0x[\da-f]{8}$/i.test(f[3]), `Player has no valid unit: ${line}`);
    players.push({ index: Number(f[0].slice(7)), handle: handle(f[1]), team: Number(f[2].slice(5)), unit: handle(f[3].slice(5)) });
  }
  const total = /^(\d+) player\(s\)$/m.exec(raw);
  check(total && Number(total[1]) === players.length, 'Incomplete live player inventory');
  return players;
}

export function parseSnapshot(raw) {
  raw = raw.replaceAll('\r\n', '\n');
  const start = raw.indexOf('warfare-state 3\n');
  check(start >= 0, 'No version-2 native snapshot');
  const result = { players: [], ordinals: {} };
  for (const line of raw.slice(start).split(/\r?\n/)) {
    const [key, ...v] = line.trim().split(/\s+/);
    if (key === 'instance') result.instance = v[0];
    else if (key === 'player') {
      const [index, team, stage, localUser, x, y, z, unit] = v.map(Number);
      result.players.push({ index, team, stage, localUser, position: [x, y, z], unit });
    } else if (key === 'ordinal') result.ordinals[Number(v[0])] = Number(v[1]);
    else if (v.length && v.every(n => /^-?\d+(?:\.\d+)?$/.test(n))) result[key] = v.length === 1 ? Number(v[0]) : v.map(Number);
  }
  return result;
}

export function guardSnapshot(s, previous) {
  check(s.ready === 1 && s.status === 2 && s.host === 1 && s.layout === 3 && s.phase === 2
    && s.globals?.length === 12 && s.globals[0] === 2 && s.globals[2] === 20570 && s.connected === 1
    && /^\d+$/.test(s.instance) && s.instance !== '0' && s.rate >= 10 && s.rate <= 240
    && Number.isInteger(s.tick) && Number.isSafeInteger(s.sampled_ms), 'Requires an active supported PWR/layout3 private host with one player');
  check(s.players.length === 1 && s.players[0].localUser === 0 && [0, 5].includes(s.players[0].stage),
    'Requires one landed local player, with no insertion/descent in progress');
  const p = s.players[0];
  check([0, 1].includes(p.team) && Number.isInteger(p.index) && p.index >= 0 && p.index < 16
    && Number.isInteger(p.unit) && p.unit > 65535 && p.unit < 0xffffffff && finite3(p.position)
    && s.ordinals[p.index] === 0, 'Invalid local player or sparse-slot HaloScript ordinal');
  if (previous) check(s.instance === previous.instance && s.tick > previous.tick && s.sampled_ms > previous.sampled_ms,
    'Native snapshot is stale, paused, or from a changed world');
  return p;
}

export function insideVolume(position, volume) {
  const { pos, forward, up, extents } = volume;
  check(finite3(pos) && finite3(forward) && finite3(up) && finite3(extents) && extents.every(x => x > 0)
    && Math.abs(dot(forward, forward) - 1) < 0.001 && Math.abs(dot(up, up) - 1) < 0.001
    && Math.abs(dot(forward, up)) < 0.001, 'Invalid probe-volume basis');
  const corner = [pos[0] / 304.8, -pos[1] / 304.8, pos[2] / 304.8];
  const offset = position.map((x, i) => x - corner[i]);
  return [forward, cross(up, forward), up].every((axis, i) => {
    const at = dot(offset, axis); return at >= 0 && at <= extents[i];
  });
}

export function guardOccupant(snapshot, livePlayers, objects, expectedVehicle = null) {
  const local = guardSnapshot(snapshot);
  check(livePlayers.length === 1 && livePlayers[0].index === local.index && livePlayers[0].unit === local.unit
    && livePlayers[0].team === local.team, 'Live player roster changed or disagrees with the native owner');
  const biped = objects.find(o => o.handle === local.unit);
  check(biped?.kind === 'biped' && biped.player === `player ${local.index}` && biped.healthPercent > 0,
    'Local player is missing, dead, or has unreadable health');
  check(biped.parent === expectedVehicle, 'Actual player parent does not match the expected vehicle');
  return biped;
}

export function guardVehicleVacant(vehicle, objects) {
  check(vehicle?.kind === 'vehicle' && vehicle.parent === null, 'Probe target must be a root vehicle');
  // Stock turrets are attached vehicle objects, not seated occupants. Follow
  // their descendants as well: a gunner seated in a child turret still makes
  // the whole vehicle unavailable for this sole-player acceptance probe.
  const descendants = new Set([vehicle.handle]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const object of objects) if (descendants.has(object.parent) && !descendants.has(object.handle)) {
      descendants.add(object.handle); changed = true;
    }
  }
  check(!objects.some(o => descendants.has(o.handle) && (o.kind === 'biped' || Boolean(o.player?.trim()))),
    'Probe vehicle is already occupied by a player or biped');
  return true;
}

export async function main(argv = process.argv.slice(2)) {
  const args = new Set(argv);
  const option = (name, fallback) => argv.find(x => x.startsWith(`${name}=`))?.slice(name.length + 1) ?? fallback;
  check(args.has('--drive'), 'No game calls made. Explicit --drive is required for this private vehicle test.');
  check(argv.every(x => ['--drive', '--screenshots', '--banshee-ascend'].includes(x)
    || /^--(?:seconds|team|out|vehicle)=/.test(x)), 'Unknown option');
  const seconds = Number(option('--seconds', '4'));
  check(Number.isInteger(seconds) && seconds >= 3 && seconds <= 5, '--seconds must be an integer from 3 to 5');
  const requestedTeam = option('--team', 'local');
  check(['local', 'red', 'blue'].includes(requestedTeam), '--team must be red or blue');
  const requestedVehicle = option('--vehicle', 'all');
  check(['all', ...VEHICLES.map(v => v.kind)].includes(requestedVehicle), '--vehicle must be hog, tank or banshee');
  const selectedVehicles = VEHICLES.filter(v => requestedVehicle === 'all' || v.kind === requestedVehicle);
  const out = path.resolve(option('--out', `out/pwr/vehicles-${new Date().toISOString().replace(/[:.]/g, '-')}.jsonl`));
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const record = value => fs.appendFileSync(out, `${JSON.stringify({ at: new Date().toISOString(), ...value })}\n`);
  const { callTool } = await import('../../tools/mcp/game/game.mjs');
  const text = r => (r.content ?? []).filter(c => c.type === 'text').map(c => c.text).join('\n');
  const call = async (name, input) => {
    const response = await callTool(name, input);
    check(!response.isError, `${name}: ${text(response)}`); return text(response);
  };
  const status = await call('game_status', {});
  const pid = status.match(/^process\s+running, pid (\d+)$/m)?.[1];
  check(pid, 'The game must already be running');
  const install = status.match(/^install\s+(.+)$/m)?.[1]?.trim();
  check(install, 'Could not identify the current game install');
  const bin = ['Win64', 'WinGDK'].find(x => fs.existsSync(path.join(install, 'Meteorite', 'Binaries', x, 'HaloCampaignEvolved.exe')));
  check(bin, 'Could not identify game binary directory');
  const ue4ss = path.join(install, 'Meteorite', 'Binaries', bin, 'ue4ss');
  const native = path.join(ue4ss, 'Mods', 'MJOLNIRLobby', 'native');
  const levelPath = path.join(ue4ss, 'MJOLNIRMaps', 'PWR', 'level.json');
  const level = JSON.parse(fs.readFileSync(levelPath, 'utf8'));
  check(level.warfare?.protocol === 20569 && level.warfare?.layout_revision === 3, 'Installed level metadata is not PWR layout3');
  const luaString = value => `[==[${value.replaceAll('\\', '/')}]==]`;
  const dll = luaString(path.join(native, 'mjolnir_lobby.dll'));
  const state = luaString(path.join(native, 'warfare_state.txt'));
  const read = `local f,e=package.loadlib(${dll},'mjolnir_warfare_pump'); assert(f,e); f(); local s=assert(io.open(${state},'rb')); print(s:read('a')); s:close()`;
  let lastSnapshot, unit, instance, inputStarted = false;
  const snapshot = async () => {
    const s = parseSnapshot(await call('game_lua', { code: read, timeout_ms: 5000 }));
    const p = guardSnapshot(s, lastSnapshot);
    if (unit !== undefined) check(p.unit === unit && s.instance === instance, 'Player died/respawned or world changed; refusing further actions');
    lastSnapshot = s; record({ event: 'snapshot', ...s }); return s;
  };
  const cli = fileURLToPath(new URL('../../target/release/mjolnir.exe', import.meta.url));
  const inventory = s => {
    const started = Date.now();
    const live = name => execFileSync(cli, ['live', '--pid', pid, name], { encoding: 'utf8', timeout: 15000, windowsHide: true });
    const players = parsePlayers(live('players')), objects = parseObjects(live('objects'));
    check(Date.now() - started < 2500, 'Live inventory took too long to authorize a movement action');
    record({ event: 'inventory', tick: s.tick, players, objects: objects.filter(o => o.kind === 'vehicle' || o.kind === 'biped') });
    return { players, objects };
  };
  const privateState = async () => {
    const file = path.join(native, 'auto_state.txt');
    const stamp = () => { try { return fs.statSync(file, { bigint: true }).mtimeNs; } catch { return 0n; } };
    const before = stamp(), requested = Date.now();
    await call('game_console', { command: 'mjolnir_auto state' });
    while (Date.now() - requested < 5000) {
      if (stamp() !== before) {
        const fields = Object.fromEntries(fs.readFileSync(file, 'utf8').trim().split(/\r?\n/).map(line => {
          const split = line.indexOf('='); return [line.slice(0, split), line.slice(split + 1)];
        }));
        if (fields.at && fields.public !== undefined) {
          check(fields.signed_in === '1' && fields.frontend === '0' && fields.public === '0' && fields.players === '1'
            && Math.abs(Date.now() / 1000 - Number(fields.at)) < 3, 'Requires a fresh private in-game session with one player');
          record({ event: 'private_guard', fields }); return;
        }
      }
      await sleep(100);
    }
    throw new Error('No fresh private-session acknowledgement');
  };
  const hs = async line => {
    check(line.length < 255, 'HaloScript command is too long');
    const script = luaString(path.join(native, 'script.txt')), body = luaString(`${Date.now()}\n${line}\n`);
    await call('game_lua', { code: `local f=assert(io.open(${script},'wb')); f:write(${body}); f:close(); local run,e=package.loadlib(${dll},'mjolnir_sim_script'); assert(run,e); run()` });
    record({ event: 'hs_requested', line }); await sleep(350);
  };
  const picture = async name => {
    if (!args.has('--screenshots')) return;
    const response = await callTool('game_screenshot', { foreground: true, max_width: 1280 });
    check(!response.isError, `Screenshot failed: ${text(response)}`);
    const frame = response.content?.find(c => c.type === 'image' && c.mimeType === 'image/png' && c.data);
    check(frame, 'Screenshot returned no PNG');
    const file = `${out.replace(/\.[^./\\]+$/, '')}-${name}.png`;
    fs.writeFileSync(file, Buffer.from(frame.data, 'base64')); record({ event: 'screenshot', file, note: text(response) });
  };
  try {
    record({ event: 'start', args: argv, install, pid, levelPath, selected_vehicles: selectedVehicles.map(v => v.kind) });
    await privateState();
    await snapshot(); await sleep(600);
    let s = await snapshot(), inv = inventory(s);
    const local = guardSnapshot(s), initial = guardOccupant(s, inv.players, inv.objects);
    unit = initial.handle; instance = s.instance;
    const team = requestedTeam === 'local' ? (local.team === 0 ? 'red' : 'blue') : requestedTeam;
    const rank = s.ordinals[local.index];
    for (let n = 0; n < selectedVehicles.length; n++) {
      const spec = selectedVehicles[n], volumeName = `pwr_probe_${spec.kind}_${team}`;
      await privateState(); s = await snapshot(); inv = inventory(s);
      guardOccupant(s, inv.players, inv.objects);
      const volumes = level.blam?.trigger_volumes?.filter(v => v.name === volumeName) ?? [];
      check(volumes.length === 1, `Expected one installed ${volumeName} probe volume`);
      const candidates = inv.objects.filter(o => o.kind === 'vehicle' && o.parent === null && insideVolume(o.position, volumes[0]));
      check(candidates.length === 1 && candidates[0].tag === spec.tag && candidates[0].healthPercent > 0,
        `Probe ${volumeName} does not contain exactly one healthy expected vehicle`);
      const vehicle = candidates[0];
      guardVehicleVacant(vehicle, inv.objects);
      // HS list_get uses the actual multiplayer copy, not its scenario name.
      const objects = `(volume_return_objects_by_type ${volumeName} 2)`;
      // HS does not implicitly downcast list_get's object to a vehicle.
      // The real engine compiler rejects the uncast expression even inside
      // an unexecuted branch; explicit vehicle() was verified in private QA.
      await hs(`(if (= (list_count ${objects}) 1) (unit_enter_vehicle_immediate (player_get ${rank}) (vehicle (list_get ${objects} 0)) "${spec.seat}"))`);
      s = await snapshot(); inv = inventory(s);
      const seated = guardOccupant(s, inv.players, inv.objects, vehicle.handle);
      const origin = inv.objects.find(o => o.handle === vehicle.handle);
      check(origin?.tag === spec.tag && origin.healthPercent > 0, 'Selected vehicle disappeared or changed type');
      record({ event: 'boarded', kind: spec.kind, vehicle: origin, player: seated });
      await picture(`${spec.kind}-seated`);
      for (let second = 0; second < seconds; second++) {
        await privateState(); s = await snapshot(); inv = inventory(s);
        guardOccupant(s, inv.players, inv.objects, vehicle.handle);
        const steps = spec.kind === 'banshee' && args.has('--banshee-ascend')
          ? [{ key: 'space', down: true }, { key: 'w', hold: 1000 }, { key: 'space', up: true }]
          : [{ key: 'w', hold: 1000 }];
        inputStarted = true;
        const response = await call('game_input', { method: 'sendinput', gap_ms: 0, steps });
        check(!/warning:|did not take focus/i.test(response), 'SendInput did not acquire the game window');
        record({ event: 'drive_input', kind: spec.kind, second, response });
      }
      await sleep(300); s = await snapshot(); inv = inventory(s);
      const afterPlayer = guardOccupant(s, inv.players, inv.objects, vehicle.handle);
      const after = inv.objects.find(o => o.handle === vehicle.handle);
      check(after?.tag === spec.tag && after.healthPercent > 0, 'Vehicle lost or destroyed during drive');
      const moved = distance(origin.position, after.position) * METRES_PER_WU;
      const deltaMetres = after.position.map((x, i) => (x - origin.position[i]) * METRES_PER_WU);
      record({ event: 'drive_result', kind: spec.kind, movedMetres: moved, deltaMetres,
        beforeMetres: metres(origin.position), afterMetres: metres(after.position), before: origin, after, player: afterPlayer });
      check(moved >= spec.minimumMetres, `${spec.kind} did not move the minimum ${spec.minimumMetres}m under input`);
      check(afterPlayer.healthPercent >= seated.healthPercent - 5 && after.healthPercent >= origin.healthPercent - 5,
        `${spec.kind} driving caused material player/vehicle damage`);
      if (spec.kind === 'banshee' && args.has('--banshee-ascend')) check(deltaMetres[2] > 0.5, 'Requested Banshee ascent was not observed');
      await picture(`${spec.kind}-moved`);
      console.log(`${spec.kind}: moved ${moved.toFixed(2)}m; player health ${afterPlayer.healthPercent}%`);
      if (n + 1 < selectedVehicles.length) {
        await privateState(); await snapshot();
        await hs(`(objects_detach (unit_get_vehicle (player_get ${rank})) (player_get ${rank}))`);
        s = await snapshot(); inv = inventory(s); guardOccupant(s, inv.players, inv.objects);
        await hs(`(object_teleport (player_get ${rank}) pwr_${local.team === 0 ? 'red' : 'blue'}_home)`);
        s = await snapshot(); inv = inventory(s); guardOccupant(s, inv.players, inv.objects);
      }
    }
    record({ event: 'complete', success: true, completed_vehicles: selectedVehicles.map(v => v.kind),
      note: 'Selected vehicles moved with verified player occupancy; match continues. Omitted vehicles were not checked in this run.' });
    console.log(JSON.stringify({ out, success: true }, null, 2));
  } catch (error) {
    record({ event: 'aborted', error: String(error) }); throw error;
  } finally {
    if (inputStarted) {
      try { await call('game_input', { method: 'sendinput', gap_ms: 0, steps: [
        { key: 'w', up: true }, ...(args.has('--banshee-ascend') ? [{ key: 'space', up: true }] : []),
      ] }); }
      catch (error) { record({ event: 'release_failed', error: String(error) }); }
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
