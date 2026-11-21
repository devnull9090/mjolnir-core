#!/usr/bin/env node
// Explicit, read-only private-match fleet retention. No movement, damage,
// teleport, hosting, configuration or vehicle creation/deletion commands.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parseSnapshot, guardSnapshot, parseObjects, parsePlayers, guardOccupant, guardVehicleVacant }
  from './smoke-warfare-vehicles.mjs';

const POLICY_SHA = 'dd3d8a4c49c21c49d6242e4b4b9882ae819caa84f77b14205515ea998cfec0cf';
const WU = 3.048;
const check = (ok, message) => { if (!ok) throw Error(message); };
const read = p => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''));
const sha = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const distance = (a, b) => Math.hypot(...a.map((n, i) => n-b[i]));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const origin = row => [row.new_pos_cm[0]/100, -row.new_pos_cm[1]/100, row.new_pos_cm[2]/100];

export function verifySeal(sealPath) {
  const seal = read(sealPath);
  check(seal.schema === 'pwr-native-qa-seal-v2' && seal.vehicle_spawn_policy?.policy_sha256 === POLICY_SHA,
    'Requires a fresh explicit-policy version-2 QA seal');
  check(Array.isArray(seal.critical) && seal.critical.length >= 4, 'Missing critical artifact records');
  for (const row of seal.critical) check(sha(row.path) === row.sha256, `Critical artifact changed: ${row.path}`);
  check(sha(seal.policy_path) === POLICY_SHA, 'Wrong or changed vehicle policy');
  check(seal.critical.some(r => path.resolve(r.path) === path.resolve(seal.installed_level))
    && seal.critical.some(r => path.resolve(r.path) === path.resolve(seal.policy_path)), 'Critical records omit installed metadata or policy');
  const policy = read(seal.policy_path), level = read(seal.installed_level);
  for (const row of policy.vehicles) {
    const placed = level.blam?.vehicles?.filter(v => v.name === row.name) ?? [];
    check(placed.length === 1 && JSON.stringify(placed[0].pos) === JSON.stringify(row.new_pos_cm)
      && placed[0].set['multiplayer data.spawn time'] === row.unchanged_spawn_seconds
      && placed[0].set['multiplayer data.abandonment time'] === row.unchanged_abandonment_seconds,
      `Installed vehicle does not match the sealed correction: ${row.name}`);
  }
  return { seal, policy, level };
}

export function sampleFleet(policy, objects, playerPosition, baseline = null) {
  check(policy.vehicles.length === 8, 'Expected eight corrected placements');
  const result = [];
  for (const row of policy.vehicles) {
    const spawn = origin(row);
    const tag = row.type === 'scorpion' ? 'objects\\vehicles\\human\\scorpion\\scorpion'
      : 'objects\\vehicles\\covenant\\banshee\\banshee';
    const nearby = objects.filter(o => o.kind === 'vehicle' && o.parent === null && o.tag === tag
      && Math.hypot(o.position[0]*WU-spawn[0], o.position[1]*WU-spawn[1]) < 4);
    check(nearby.length === 1, `Missing or ambiguous stationary vehicle: ${row.name}`);
    const vehicle = nearby[0], position = vehicle.position.map(n => n*WU);
    guardVehicleVacant(vehicle, objects);
    check(vehicle.healthPercent === 100, `Stationary vehicle lost health: ${row.name}`);
    const fromSpawn = distance(position, spawn), playerDistance = distance(playerPosition, position);
    check(fromSpawn < 1.3, `Settled origin lacks margin below the 1.524m abandonment threshold: ${row.name}`);
    check(playerDistance >= 60, `Player proximity could suppress abandonment: ${row.name}`);
    const first = baseline?.find(b => b.name === row.name);
    if (baseline) {
      check(first && first.handle === vehicle.handle, `Vehicle handle replaced during idle retention: ${row.name}`);
      check(distance(first.position_m, position) <= .5, `Stationary vehicle moved materially: ${row.name}`);
    }
    result.push({ name: row.name, handle: vehicle.handle, position_m: position, spawn_m: spawn,
      displacement_m: fromSpawn, player_distance_m: playerDistance, health: vehicle.healthPercent });
  }
  check(new Set(result.map(r => r.handle)).size === 8, 'One native object matched multiple spawn pads');
  return result;
}

export function retentionComplete(first, last, seconds = 180) {
  check(seconds >= 180 && seconds <= 300, 'Idle acceptance requires at least 180 seconds');
  check(first.rate === last.rate && first.instance === last.instance, 'Match timing or instance changed');
  const wall = (last.at_ms-first.at_ms)/1000;
  const simulation = (last.tick-first.tick)/first.rate;
  return { complete: wall >= seconds && simulation >= seconds, wall_seconds: wall, simulation_seconds: simulation };
}

export async function main(argv = process.argv.slice(2)) {
  check(argv.includes('--observe'), 'No game calls made. Explicit --observe required.');
  check(argv.every(v => v === '--observe' || /^--(?:seal|out|seconds)=/.test(v)), 'Unknown option');
  const option = name => argv.find(v => v.startsWith(`--${name}=`))?.slice(name.length+3);
  const sealPath = option('seal'), output = option('out'), seconds = Number(option('seconds') ?? '180');
  check(sealPath && output && !fs.existsSync(output), 'Explicit --seal and new --out paths are required');
  check(Number.isInteger(seconds) && seconds >= 180 && seconds <= 300, '--seconds must be 180..300');
  const { seal, policy } = verifySeal(sealPath);
  const ue4ss = path.dirname(path.dirname(path.dirname(seal.installed_level)));
  const native = path.join(ue4ss, 'Mods/MJOLNIRLobby/native');
  const luaString = s => `[==[${s.replaceAll('\\','/')}]==]`;
  const readState = `local f=assert(package.loadlib(${luaString(path.join(native,'mjolnir_lobby.dll'))},'mjolnir_warfare_pump')); f(); local s=assert(io.open(${luaString(path.join(native,'warfare_state.txt'))},'rb'));print(s:read('a'));s:close()`;
  const { callTool } = await import('../../tools/mcp/game/game.mjs');
  const text = r => (r.content ?? []).filter(c => c.type === 'text').map(c => c.text).join('\n');
  const call = async (name, args) => { const r = await callTool(name, args); check(!r.isError, text(r)); return text(r); };
  const status = await call('game_status', {});
  const pid = status.match(/^process\s+running, pid (\d+)$/m)?.[1];
  check(pid, 'Game must already be running');
  const statusInstall = status.match(/^install\s+(.+)$/m)?.[1]?.trim();
  check(statusInstall && path.resolve(ue4ss).startsWith(path.resolve(statusInstall)+path.sep), 'Seal belongs to another game install');
  const cli = fileURLToPath(new URL('../../target/release/mjolnir.exe', import.meta.url));
  const live = name => execFileSync(cli, ['live','--pid',pid,name], {encoding:'utf8',timeout:15000,windowsHide:true});
  fs.mkdirSync(path.dirname(path.resolve(output)), {recursive:true});
  const descriptor = fs.openSync(output,'wx');
  const record = row => fs.writeSync(descriptor, JSON.stringify({at:new Date().toISOString(),...row})+'\n');
  let previous, first, fleet, bodyHandle, lastSampleAt;
  try {
    record({event:'start', pid, seal: path.resolve(sealPath), seal_sha256: sha(sealPath), seconds,
      policy_sha256:POLICY_SHA, read_only:true, proximity_exclusion_m:60});
    const autoPath = path.join(native,'auto_state.txt');
    const oldStamp = fs.existsSync(autoPath) ? fs.statSync(autoPath).mtimeMs : 0;
    await call('game_console',{command:'mjolnir_auto state'});
    const requested = Date.now();
    while ((!fs.existsSync(autoPath) || fs.statSync(autoPath).mtimeMs === oldStamp) && Date.now()-requested < 5000) await sleep(50);
    check(fs.existsSync(autoPath) && fs.statSync(autoPath).mtimeMs !== oldStamp, 'Missing fresh private-session acknowledgement');
    const fields = Object.fromEntries(fs.readFileSync(autoPath,'utf8').trim().split(/\r?\n/).map(s => {const at=s.indexOf('=');return[s.slice(0,at),s.slice(at+1)];}));
    check(fields.signed_in === '1' && fields.frontend === '0' && fields.public === '0' && fields.players === '1'
      && Math.abs(Date.now()/1000-Number(fields.at)) < 3, 'Requires fresh private solo session');
    record({event:'private_guard',fields});
    const deadline = Date.now()+(seconds+60)*1000;
    while (Date.now() < deadline) {
      const started = Date.now();
      const snapshot = parseSnapshot(await call('game_lua',{code:readState,timeout_ms:5000}));
      const local = guardSnapshot(snapshot,previous);
      const players = parsePlayers(live('players')), objects = parseObjects(live('objects'));
      const body = guardOccupant(snapshot,players,objects);
      check(body.healthPercent === 100 && (bodyHandle === undefined || body.handle === bodyHandle), 'Player health or unit changed');
      check(Date.now()-started < 2500, 'Native inventory too slow for a bounded idle sample');
      const stamp = Date.now();
      check(lastSampleAt === undefined || stamp-lastSampleAt <= 3500, 'Idle sampling gap exceeds 3.5 seconds');
      const current = sampleFleet(policy,objects,local.position,fleet);
      const clock = {at_ms:stamp,tick:snapshot.tick,rate:snapshot.rate,instance:snapshot.instance};
      if (!first) {first=clock;fleet=current;bodyHandle=body.handle;}
      const timing = retentionComplete(first,clock,seconds);
      record({event:'idle_sample',...clock,unit:body.handle,player_position_m:local.position,vehicles:current,...timing});
      previous=snapshot;lastSampleAt=stamp;
      if (timing.complete) {
        verifySeal(sealPath);
        record({event:'complete',success:true,retained_same_handles:8,...timing});
        console.log(JSON.stringify({success:true,out:output,retained_same_handles:8,...timing}));
        return;
      }
      await sleep(Math.max(0,2000-(Date.now()-started)));
    }
    throw Error('Could not observe the full required wall and simulation duration before timeout');
  } catch (error) {
    record({event:'aborted',error:String(error)});throw error;
  } finally {fs.closeSync(descriptor);}
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  main().catch(error => {console.error(error.message);process.exitCode=1;});
