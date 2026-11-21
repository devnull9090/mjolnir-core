#!/usr/bin/env node
// Explicit private native terrain acceptance. Does not host, install, kill,
// spawn/remove objects, patch memory, or change variants. --probe is mandatory.
// node native/lobby/smoke-warfare-terrain.mjs --probe --plan=<plan.json> --walk
// --seams-only repeats calibration plus the four seams; it does not claim the
// omitted road/shore checks passed in this run.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parseObjects, parsePlayers, parseSnapshot, guardSnapshot, guardOccupant } from './smoke-warfare-vehicles.mjs';

const check = (condition, message) => { if (!condition) throw new Error(message); };
const finite3 = p => Array.isArray(p) && p.length === 3 && p.every(Number.isFinite);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const distance = (a, b) => Math.hypot(...a.map((x, i) => x - b[i]));
const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

export function guardPlan(plan, level, hash) {
  check(plan.schema === 'pwr-terrain-probe-v1' && plan.protocol === 20569 && plan.layout_revision === 3
    && plan.provenance?.compiled_boundaries_verified === true && /^[a-f0-9]{64}$/.test(plan.master_manifest_sha256)
    && level.warfare?.protocol === 20569 && level.warfare?.layout_revision === 3, 'Requires a compiled layout3 terrain probe plan');
  check(plan.probes?.length >= 8 && plan.probes.length <= 16 && plan.probes[0].kind === 'calibration', 'Invalid probe sequence');
  const flags = level.blam?.cutscene_flags ?? [];
  check(flags.filter(f => f.name === `terrain_probe_hash_${hash.slice(0, 12)}`).length === 1, 'Installed level has a different probe-plan stamp; rebake/reinstall required');
  const names = new Set();
  for (const p of plan.probes) {
    check(/^terrain_probe_[a-z0-9_]{1,17}$/.test(p.flag) && !names.has(p.flag) && finite3(p.position_m)
      && Number.isFinite(p.floor_m) && Number.isFinite(p.yaw) && p.max_residual_m > 0 && p.max_residual_m <= .75,
      'Invalid or duplicate probe flag');
    names.add(p.flag);
    const found = flags.filter(f => f.name === p.flag), expected = p.position_m.map((n, i) => n * (i === 1 ? -100 : 100));
    check(found.length === 1 && finite3(found[0].pos) && distance(found[0].pos, expected) < .01
      && Math.abs(found[0].yaw - p.yaw) < .001, `Installed flag differs from probe ${p.id}`);
    if (p.kind === 'seam') check(finite3(p.seam?.a_m) && finite3(p.seam?.b_m)
      && p.seam.instances?.length === 2 && p.seam.instances[0] !== p.seam.instances[1]
      && p.crossing_normal?.length === 2 && Math.abs(Math.hypot(...p.crossing_normal) - 1) < .0001
      && p.crossing_center_m?.length === 2 && p.crossing_center_m.every(Number.isFinite)
      && p.walk_duration_ms >= 500 && p.walk_duration_ms <= 2000
      && p.max_walk_metres > 0 && p.max_walk_metres <= 16, 'Invalid compiled seam crossing');
  }
  return plan;
}

export function motion(previous, current) {
  check(previous.instance === current.instance && current.tick > previous.tick && current.rate === previous.rate, 'Cannot measure motion across stale/changed simulation');
  const dt = (current.tick - previous.tick) / current.rate;
  check(dt > 0 && dt < 5, 'Native samples too far apart for a settling measurement');
  const velocity = current.players[0].position.map((v, i) => (v - previous.players[0].position[i]) / dt);
  return { dt, velocity_mps: velocity, speed_mps: Math.hypot(...velocity) };
}

export function settled(samples) {
  if (samples.length < 3) return false;
  const tail = samples.slice(-3), duration = (tail[2].tick - tail[0].tick) / tail[2].rate;
  return duration >= .7 && duration < 4 && tail.slice(1).every((s, i) => motion(tail[i], s).speed_mps < .08)
    && distance(tail[0].players[0].position, tail[2].players[0].position) < .04;
}

export function crossedSeam(probe, before, after) {
  const a = probe.seam.a_m, b = probe.seam.b_m, normal = probe.crossing_normal, c = probe.crossing_center_m;
  const side = p => (p[0] - c[0]) * normal[0] + (p[1] - c[1]) * normal[1];
  const s0 = side(before), s1 = side(after);
  if (!(s0 < -.5 && s1 > .5)) return false;
  const t = -s0 / (s1 - s0), point = before.map((n, i) => n + (after[i] - n) * t);
  const e = [b[0] - a[0], b[1] - a[1]], len2 = e[0] ** 2 + e[1] ** 2;
  const u = ((point[0] - a[0]) * e[0] + (point[1] - a[1]) * e[1]) / len2;
  return u > .05 && u < .95 && distance(before.slice(0, 2), after.slice(0, 2)) <= probe.max_walk_metres;
}

export function floorResult(probe, position, expectedFloor, offset) {
  check(Number.isFinite(expectedFloor) && Number.isFinite(offset), 'Invalid floor/calibration sample');
  const residual = position[2] - offset - expectedFloor;
  return { expected_floor_m: expectedFloor, origin_above_floor_m: offset,
    measured_floor_m: position[2] - offset, residual_m: residual,
    tolerance_m: probe.max_residual_m, pass: Math.abs(residual) <= probe.max_residual_m };
}

export function movementForYaw(normal, actualYaw) {
  check(normal?.length === 2 && normal.every(Number.isFinite) && Number.isFinite(actualYaw)
    && Math.abs(Math.hypot(...normal) - 1) < .0001, 'Invalid movement basis');
  const yaw = actualYaw * Math.PI / 180, forward = [Math.cos(yaw), Math.sin(yaw)], left = [-forward[1], forward[0]];
  const choices = [
    { key: 'w', traversal: 'forward', direction: forward },
    { key: 's', traversal: 'backward', direction: forward.map(v => -v) },
    { key: 'a', traversal: 'left_strafe', direction: left },
    { key: 'd', traversal: 'right_strafe', direction: left.map(v => -v) },
  ].map(c => ({ ...c, alignment: c.direction[0] * normal[0] + c.direction[1] * normal[1] }));
  const selected = choices.sort((a, b) => b.alignment - a.alignment)[0];
  check(selected.alignment >= Math.cos(15 * Math.PI / 180), 'Player facing is not aligned with a bounded keyboard crossing axis');
  return selected;
}

export function verifyDirectedStep(probe, before, after, maximumMetres) {
  const delta = [after[0] - before[0], after[1] - before[1]], moved = Math.hypot(...delta);
  const progress = delta[0] * probe.crossing_normal[0] + delta[1] * probe.crossing_normal[1];
  const alignment = moved > 0 ? progress / moved : 0;
  check(moved >= .05 && moved <= maximumMetres && alignment >= Math.cos(20 * Math.PI / 180),
    `Observed keyboard motion did not follow the crossing: moved=${moved.toFixed(3)}m, alignment=${alignment.toFixed(3)}`);
  return { delta_m: delta, moved_m: moved, crossing_progress_m: progress, alignment };
}

export async function main(argv = process.argv.slice(2)) {
  const args = new Set(argv), opt = (key, fallback) => argv.find(x => x.startsWith(`${key}=`))?.slice(key.length + 1) ?? fallback;
  check(args.has('--probe'), 'No game calls made. Explicit --probe is required for this private native terrain test.');
  check(argv.every(x => ['--probe', '--walk', '--screenshots', '--seams-only'].includes(x) || /^--(?:plan|out)=/.test(x)), 'Unknown option');
  check(opt('--plan'), '--plan=<compiled probe plan> is required');
  const planPath = path.resolve(opt('--plan')), plan = JSON.parse(fs.readFileSync(planPath, 'utf8')), planHash = sha(planPath);
  const selectedProbes = args.has('--seams-only') ? plan.probes.filter(p => ['calibration', 'seam'].includes(p.kind)) : plan.probes;
  check(sha(plan.master_path) === plan.master_manifest_sha256, 'Runtime master changed since probe preparation');
  check(sha(plan.provenance.receipt_path) === plan.provenance.receipt_sha256, 'Compiled collision receipt changed');
  const receipt = JSON.parse(fs.readFileSync(plan.provenance.receipt_path, 'utf8'));
  check(receipt.output_sha256 === plan.provenance.compiled_tag_sha256 && sha(receipt.output) === receipt.output_sha256,
    'Compiled collision tag changed since probe preparation');
  const out = path.resolve(opt('--out', `out/pwr/terrain-${new Date().toISOString().replace(/[:.]/g, '-')}.jsonl`));
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const record = data => fs.appendFileSync(out, `${JSON.stringify({ at: new Date().toISOString(), ...data })}\n`);
  const { callTool } = await import('../../tools/mcp/game/game.mjs');
  const text = r => (r.content ?? []).filter(c => c.type === 'text').map(c => c.text).join('\n');
  const call = async (name, input) => {
    const r = await callTool(name, input); check(!r.isError, `${name}: ${text(r)}`); return text(r);
  };
  const status = await call('game_status', {}), pid = status.match(/^process\s+running, pid (\d+)$/m)?.[1];
  const install = status.match(/^install\s+(.+)$/m)?.[1]?.trim();
  check(pid && install, 'The game must already be running in the private layout3 match');
  const bin = ['Win64', 'WinGDK'].find(x => fs.existsSync(path.join(install, 'Meteorite', 'Binaries', x, 'HaloCampaignEvolved.exe')));
  check(bin, 'Could not identify game binary directory');
  const ue4ss = path.join(install, 'Meteorite', 'Binaries', bin, 'ue4ss');
  const native = path.join(ue4ss, 'Mods', 'MJOLNIRLobby', 'native');
  const levelPath = path.join(ue4ss, 'MJOLNIRMaps', 'PWR', 'level.json');
  guardPlan(plan, JSON.parse(fs.readFileSync(levelPath, 'utf8')), planHash);
  const luaString = value => { check(!value.includes(']==]'), 'Invalid Lua literal'); return `[==[${value.replaceAll('\\', '/')}]==]`; };
  const dll = luaString(path.join(native, 'mjolnir_lobby.dll')), state = luaString(path.join(native, 'warfare_state.txt'));
  const read = `local f,e=package.loadlib(${dll},'mjolnir_warfare_pump'); assert(f,e); f(); local s=assert(io.open(${state},'rb')); print(s:read('a')); s:close()`;
  const cli = fileURLToPath(new URL('../../target/release/mjolnir.exe', import.meta.url));
  const sampler = fileURLToPath(new URL('./prepare_terrain_probe.py', import.meta.url));
  let previous, unit, instance, minimumHealth, inputStarted = false;
  const snapshot = async () => {
    const s = parseSnapshot(await call('game_lua', { code: read, timeout_ms: 5000 }));
    const p = guardSnapshot(s, previous);
    if (unit !== undefined) check(unit === p.unit && instance === s.instance, 'Player died/respawned or match changed; stopping');
    previous = s; record({ event: 'native_snapshot', ...s }); return s;
  };
  const body = s => {
    const started = Date.now();
    const live = name => execFileSync(cli, ['live', '--pid', pid, name], { encoding: 'utf8', timeout: 15000, windowsHide: true });
    const b = guardOccupant(s, parsePlayers(live('players')), parseObjects(live('objects')));
    check(Date.now() - started < 2500, 'Live inventory too old to authorize movement');
    if (minimumHealth !== undefined) check(b.healthPercent >= minimumHealth, 'Player took damage during terrain probe');
    if (minimumHealth !== undefined) minimumHealth = Math.max(minimumHealth, b.healthPercent);
    record({ event: 'body', tick: s.tick, body: b, contact: 'not exposed by CLI' }); return b;
  };
  const privateState = async () => {
    const file = path.join(native, 'auto_state.txt');
    const stamp = () => { try { return fs.statSync(file, { bigint: true }).mtimeNs; } catch { return 0n; } };
    const before = stamp(), requested = Date.now();
    await call('game_console', { command: 'mjolnir_auto state' });
    while (Date.now() - requested < 5000) {
      if (stamp() !== before) {
        const f = Object.fromEntries(fs.readFileSync(file, 'utf8').trim().split(/\r?\n/).map(line => {
          const n = line.indexOf('='); return [line.slice(0, n), line.slice(n + 1)];
        }));
        if (f.at && f.public !== undefined) {
          check(f.signed_in === '1' && f.frontend === '0' && f.public === '0' && f.players === '1'
            && Math.abs(Date.now() / 1000 - Number(f.at)) < 3, 'Requires a fresh private sole-player match');
          record({ event: 'private_guard', fields: f }); return;
        }
      }
      await sleep(100);
    }
    throw new Error('No fresh private-session acknowledgement');
  };
  const teleport = async (probe, rank) => {
    const line = `(object_teleport (player_get ${rank}) ${probe.flag})`;
    const script = luaString(path.join(native, 'script.txt')), content = luaString(`${Date.now()}\n${line}\n`);
    await call('game_lua', { code: `local f=assert(io.open(${script},'wb')); f:write(${content}); f:close(); local run,e=package.loadlib(${dll},'mjolnir_sim_script'); assert(run,e); run()` });
    record({ event: 'teleport_requested', id: probe.id, line }); await sleep(250);
  };
  const floor = (probe, position) => {
    if (probe.surface === 'base_plaza') {
      check(distance(position.slice(0, 2), probe.position_m.slice(0, 2)) < 2, 'Player left known calibration/base support');
      return probe.floor_m;
    }
    const r = execFileSync('python', [sampler, 'sample', planPath, String(position[0]), String(position[1])],
      { encoding: 'utf8', timeout: 10000, windowsHide: true });
    return JSON.parse(r).floor_m;
  };
  const settle = async (probe, walking = false) => {
    const samples = [], start = Date.now();
    while (Date.now() - start < 8000) {
      await sleep(350); const s = await snapshot(), p = s.players[0].position;
      check(p[2] > probe.floor_m - 2 && distance(p.slice(0, 2), probe.position_m.slice(0, 2)) < (walking ? 16 : 2),
        `Probe ${probe.id}: missed destination, fell below support or left its bounded region`);
      if (samples.length) record({ event: 'measured_motion', id: probe.id, tick: s.tick, ...motion(samples.at(-1), s) });
      samples.push(s);
      if (settled(samples)) { body(s); return s; }
    }
    throw new Error(`Probe ${probe.id}: no stable native landing within 8 seconds`);
  };
  const picture = async name => {
    if (!args.has('--screenshots')) return;
    const r = await callTool('game_screenshot', { foreground: true, max_width: 1280 });
    const frame = r.content?.find(c => c.type === 'image' && c.mimeType === 'image/png' && c.data);
    check(!r.isError && frame, 'Screenshot failed');
    const file = `${out.replace(/\.[^./\\]+$/, '')}-${name}.png`;
    fs.writeFileSync(file, Buffer.from(frame.data, 'base64')); record({ event: 'screenshot', file });
  };
  try {
    record({ event: 'start', planPath, planHash, master: plan.master_manifest_sha256, provenance: plan.provenance, pid, install, args: argv,
      selected_probes: selectedProbes.map(p => p.id) });
    await privateState(); await snapshot(); await sleep(500);
    const initial = await snapshot(), b = body(initial);
    unit = b.handle; instance = initial.instance; minimumHealth = b.healthPercent;
    const rank = initial.ordinals[initial.players[0].index];
    let offset;
    for (const probe of selectedProbes) {
      await privateState(); const before = await snapshot(); body(before);
      await teleport(probe, rank);
      let s = await settle(probe), position = s.players[0].position, expected = floor(probe, position);
      if (probe.kind === 'calibration') {
        offset = position[2] - expected;
        check(offset >= -.1 && offset <= .5, 'Calibration origin offset is inconsistent with the known flat apron');
        record({ event: 'calibration', id: probe.id, offset_m: offset, expected_floor_m: expected, position });
      }
      const result = floorResult(probe, position, expected, offset);
      record({ event: 'settled_floor', id: probe.id, position, contact_inferred: true, ...result });
      check(result.pass, `${probe.id}: native floor residual ${result.residual_m.toFixed(3)}m exceeds ${result.tolerance_m}m`);
      if (probe.kind === 'seam' && args.has('--walk')) {
        const begin = position, seated = body(s);
        const movement = movementForYaw(probe.crossing_normal, seated.yaw);
        record({ event: 'crossing_axis', id: probe.id, actual_yaw: seated.yaw,
          flag_unreal_yaw: probe.yaw, ...movement });
        // A short pulse verifies the actual native motion before the remaining
        // bounded traversal. Body/camera disagreement, FlyCam, a blocked route
        // or a reversed input axis cannot produce a claimed pass.
        for (let elapsed = 0; elapsed < probe.walk_duration_ms;) {
          const milliseconds = elapsed === 0 ? 150 : Math.min(450, probe.walk_duration_ms - elapsed);
          await privateState(); s = await snapshot(); body(s);
          const stepStart = s.players[0].position;
          inputStarted = true;
          const response = await call('game_input', { method: 'sendinput', gap_ms: 0, steps: [{ key: movement.key, hold: milliseconds }] });
          check(!/warning:|did not take focus/i.test(response), 'SendInput failed to acquire game focus');
          await sleep(150); s = await snapshot(); body(s);
          const observation = verifyDirectedStep(probe, stepStart, s.players[0].position, elapsed === 0 ? 2.5 : 6);
          check(distance(begin.slice(0, 2), s.players[0].position.slice(0, 2)) <= probe.max_walk_metres,
            'Crossing exceeded its bounded movement distance');
          record({ event: elapsed === 0 ? 'verification_pulse' : 'walk_input', id: probe.id,
            milliseconds, key: movement.key, traversal: movement.traversal, ...observation });
          elapsed += milliseconds;
        }
        s = await settle(probe, true); position = s.players[0].position;
        const result = floorResult(probe, position, floor(probe, position), offset);
        const crossed = crossedSeam(probe, begin, position);
        record({ event: 'seam_walk_result', id: probe.id, before: begin, after: position, crossed,
          instances: probe.seam.instances, key: movement.key, traversal: movement.traversal,
          contact_inferred: true, ...result });
        check(crossed && result.pass, `Probe ${probe.id}: actual finite seam crossing/floor acceptance failed`);
      }
      await picture(probe.id);
      console.log(`${probe.id}: settled floor residual ${result.residual_m.toFixed(3)}m`);
    }
    record({ event: 'complete', success: true, walked: args.has('--walk'), completed_probes: selectedProbes.map(p => p.id),
      note: 'Player left at final probe; match continues. Omitted probes were not checked in this run.' });
    console.log(JSON.stringify({ out, success: true, probes: selectedProbes.length, walked: args.has('--walk') }));
  } catch (error) {
    record({ event: 'aborted', error: String(error) }); throw error;
  } finally {
    if (inputStarted) try { await call('game_input', { method: 'sendinput', gap_ms: 0, steps: ['w', 's', 'a', 'd'].map(key => ({ key, up: true })) }); }
    catch (error) { record({ event: 'release_failed', error: String(error) }); }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
