#!/usr/bin/env node
// Private PWR acceptance probe using the existing game bridge. It never installs
// files, changes a variant, launches a game, or adds/removes local players.
// Default: observe the current match. Explicit --host starts PWR PRIVATELY;
// --jump requests exit/deployment; --respawn kills the landed local test player
// once; --capture-a teleports that player to authored test flag pwr_capture_a.
// --expect-end requires the variant's replicated terminal phase (use a separate
// low-score TEST variant); it does not end the game or change rules itself.
// --screenshots saves one frame at seated, canopy, landed and terminal phase.
// --keyboard sends actual Space key presses for --jump/deploy instead of the
// native action export. --transports requires aircraft counts 0/2/0 in warmup,
// seated insertion, and active play after the aircraft cleanup grace period.
// Example (after installing a minplayers1/warmup5 TEST variant):
// node native/lobby/smoke-warfare.mjs --host --jump --respawn --capture-a --seconds=90
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { callTool } from '../../tools/mcp/game/game.mjs';

const args = new Set(process.argv.slice(2));
const option = (name, fallback) => [...args].find(x => x.startsWith(`${name}=`))?.slice(name.length + 1) ?? fallback;
const seconds = Number(option('--seconds', '150'));
if (!Number.isFinite(seconds) || seconds < 1 || seconds > 600) throw new Error('--seconds must be 1..600');
const out = path.resolve(option('--out', `out/pwr/smoke-${new Date().toISOString().replace(/[:.]/g, '-')}.jsonl`));
fs.mkdirSync(path.dirname(out), { recursive: true });
const content = r => (r.content ?? []).filter(c => c.type === 'text').map(c => c.text).join('\n');
const call = async (name, input) => {
  const r = await callTool(name, input);
  if (r.isError) throw new Error(`${name}: ${content(r)}`);
  return content(r);
};
const status = await call('game_status', {});
if (!/^process\s+running/m.test(status)) throw new Error('Game must already be running with the installed PWR build.');
const install = status.match(/^install\s+(.+)$/m)?.[1]?.trim();
if (!install) throw new Error('Could not identify the current game install.');
const bin = ['Win64', 'WinGDK'].find(x => fs.existsSync(path.join(install, 'Meteorite', 'Binaries', x, 'HaloCampaignEvolved.exe')));
const native = path.join(install, 'Meteorite', 'Binaries', bin, 'ue4ss', 'Mods', 'MJOLNIRLobby', 'native');
const luaString = text => `[==[${text.replaceAll('\\', '/')}]==]`;
const dll = luaString(path.join(native, 'mjolnir_lobby.dll'));
const state = luaString(path.join(native, 'warfare_state.txt'));
const read = `local f,e=package.loadlib(${dll},'mjolnir_warfare_pump'); assert(f,e); f(); local s=assert(io.open(${state},'rb')); print(s:read('a')); s:close()`;
const action = () => args.has('--keyboard')
  ? call('game_input', { method: 'sendinput', steps: [{ key: 'space', hold: 80 }] })
  : call('game_lua', { code: `local f,e=package.loadlib(${dll},'mjolnir_warfare_action'); assert(f,e); f()` });
const hs = async line => {
  const script = luaString(path.join(native, 'script.txt'));
  const body = luaString(`${Date.now()}\n${line}\n`);
  return call('game_lua', { code: `local f=assert(io.open(${script},'wb')); f:write(${body}); f:close(); local run,e=package.loadlib(${dll},'mjolnir_sim_script'); assert(run,e); run()` });
};
const parse = raw => {
  const start = raw.indexOf('warfare-state 3');
  if (start < 0) throw new Error(`No warfare snapshot in bridge reply: ${raw.slice(0, 300)}`);
  const snapshot = { players: [], ordinals: {}, raw: raw.slice(start) };
  for (const line of snapshot.raw.split(/\r?\n/)) {
    const [key, ...values] = line.trim().split(/\s+/);
    if (key === 'player') {
      const [index, team, stage, localUser, x, y, z, unit] = values.map(Number);
      snapshot.players.push({ index, team, stage, localUser, x, y, z, unit });
    } else if (key === 'ordinal') snapshot.ordinals[Number(values[0])] = Number(values[1]);
    else if (key === 'instance') snapshot.instance = values[0];
    else if (values.length && values.every(v => /^-?\d+(\.\d+)?$/.test(v)))
      snapshot[key] = values.length === 1 ? Number(values[0]) : values.map(Number);
  }
  return snapshot;
};
const record = data => fs.appendFileSync(out, `${JSON.stringify({ at: new Date().toISOString(), ...data })}\n`);
const transportCounts = {};
const transports = (stage, snapshot) => {
  if (!args.has('--transports') || stage in transportCounts) return;
  try {
    const cli = fileURLToPath(new URL('../../target/release/mjolnir.exe', import.meta.url));
    const output = execFileSync(cli, ['live', 'objects', '--filter', 'pwr_pelican'],
      { encoding: 'utf8', timeout: 15000, windowsHide: true });
    const count = output.split(/\r?\n/).filter(line => /^\d+\t0x[\da-f]+\tvehicle\t/i.test(line)).length;
    transportCounts[stage] = count;
    record({ event: 'transports', stage, count, tick: snapshot.tick, instance: snapshot.instance, output });
    console.log(`transports ${stage}: ${count}`);
  } catch (e) {
    transportCounts[stage] = -1;
    record({ event: 'transports_failed', stage, error: String(e) });
  }
};
const screenshotStages = new Set();
const screenshot = async (stage, snapshot) => {
  if (!args.has('--screenshots') || screenshotStages.has(stage)) return;
  screenshotStages.add(stage);
  try {
    const result = await callTool('game_screenshot', { foreground: true, max_width: 1280 });
    if (result.isError) throw new Error(content(result));
    const frame = result.content?.find(c => c.type === 'image' && c.mimeType === 'image/png' && c.data);
    if (!frame) throw new Error('Screenshot returned no PNG image');
    const file = `${out.replace(/\.[^./\\]+$/, '')}-${stage}.png`;
    fs.writeFileSync(file, Buffer.from(frame.data, 'base64'));
    record({ event: 'screenshot', stage, tick: snapshot.tick, instance: snapshot.instance, file, note: content(result) });
    console.log(`screenshot ${stage}: ${file}`);
  } catch (e) { record({ event: 'screenshot_failed', stage, error: String(e) }); }
};
record({ event: 'start', args: [...args], install });
const autoFile = path.join(native, 'auto_state.txt');
const stamp = () => { try { return fs.statSync(autoFile, { bigint: true }).mtimeNs; } catch { return 0n; } };
const auto = async command => {
  const before = stamp();
  await call('game_console', { command: `mjolnir_auto ${command}` });
  const end = Date.now() + 5000;
  while (Date.now() < end) {
    if (stamp() !== before) {
      try {
        const fields = Object.fromEntries(fs.readFileSync(autoFile, 'utf8').trim().split(/\r?\n/)
          .map(line => { const at = line.indexOf('='); return [line.slice(0, at), line.slice(at + 1)]; }));
        if (fields.at && fields.signed_in !== undefined) { record({ event: 'auto_ack', command, fields }); return fields; }
      } catch { /* A concurrently written reply will be complete on the next poll. */ }
    }
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error(`No fresh Lobby auto_state acknowledgement for ${command}`);
};
if (args.has('--host')) {
  const deadline = Date.now() + 45000;
  let ready = false;
  while (Date.now() < deadline) {
    const fields = await auto('state');
    if (fields.signed_in === '1' && Number(fields.players) >= 1) {
      if (fields.frontend !== '1') throw new Error('Return to the main menu before using --host.');
      ready = true; break;
    }
    await new Promise(r => setTimeout(r, 500));
  }
  if (!ready) throw new Error('Title-screen sign-in did not finish within 45 seconds.');
  const fields = await auto('host PWR warfare private');
  if (fields.result !== 'hosting PWR warfare private') throw new Error(`Private host failed: ${fields.result ?? 'no result'}`);
}
let jumped = 0, deployed = false, killed = 0, captured = false, last = '', lastUnit = 0;
let sawReady = false, sawSeated = false, sawCanopy = false, sawLanded = false, sawRespawn = false, sawScore = false, sawEnd = false;
let sawKeyboardExit = false;
const until = Date.now() + seconds * 1000;
while (Date.now() < until) {
  let s;
  try { s = parse(await call('game_lua', { code: read, timeout_ms: 5000 })); }
  catch (e) { record({ event: 'unavailable', error: String(e) }); await new Promise(r => setTimeout(r, 1000)); continue; }
  record({ event: 'snapshot', ...s });
  const local = s.players.find(p => p.localUser === 0);
  const summary = `ready=${s.ready} status=${s.status} phase=${s.phase} tick=${s.tick} score=${s.score} local=${local?.stage} xyz=${local ? `${local.x},${local.y},${local.z}` : 'none'}`;
  if (summary !== last) { console.log(summary); last = summary; }
  if (s.ready === 1 && s.status === 2 && s.layout === 3 && s.globals?.[2] === 20570) {
    sawReady = true;
    if (local?.stage === 2) sawSeated = true;
    if (local?.stage === 4) sawCanopy = true;
    if (local?.stage === 5) sawLanded = true;
    if (s.score?.some(x => x > 0)) sawScore = true;
    if (s.phase === 3) sawEnd = true;
    // Native automatic exit begins at90% of insertion duration. An earlier
    // detached drop proves the Space key path rather than automatic fallback.
    if (args.has('--keyboard') && jumped && s.phase === 1 && s.elapsed_ticks < 0.85 * s.insertion_seconds * s.rate
        && (local?.stage === 3 || local?.stage === 4)) sawKeyboardExit = true;
    if (s.phase === 0) transports('warmup', s);
    if (s.phase === 1 && local?.stage === 2) transports('insertion', s);
    if (s.phase === 2 && s.elapsed_ticks >= 6 * s.rate) transports('cleanup', s);
    const stage = s.phase === 3 ? 'end' : ({ 2: 'seated', 4: 'canopy', 5: 'landed' })[local?.stage];
    if (stage) await screenshot(stage, s);
    if (args.has('--jump') && !jumped && local?.stage === 2 && s.phase === 1 && s.elapsed_ticks >= s.rate * 5) {
      const response = await action(); jumped = Date.now(); record({ event: 'jump_requested', keyboard: args.has('--keyboard'), response });
    } else if (jumped && !deployed && local?.stage === 3 && Date.now() - jumped >= 700) {
      const response = await action(); deployed = true; record({ event: 'deploy_requested', keyboard: args.has('--keyboard'), response });
    }
    if (args.has('--respawn') && !killed && local?.stage === 5 && s.phase === 2) {
      const rank = s.ordinals[local.index]; if (!Number.isInteger(rank) || rank < 0) throw new Error('Missing verified HaloScript player rank');
      lastUnit = local.unit; await hs(`(unit_kill (player_get ${rank}))`);
      killed = Date.now(); record({ event: 'respawn_requested', player: local.index, oldUnit: lastUnit });
    } else if (killed && local && local.unit !== lastUnit && local.stage === 0) sawRespawn = true;
    if (args.has('--capture-a') && !captured && local && s.phase === 2
        && (args.has('--respawn') ? sawRespawn : local.stage === 5)) {
      const rank = s.ordinals[local.index]; if (!Number.isInteger(rank) || rank < 0) throw new Error('Missing verified HaloScript player rank');
      await hs(`(object_teleport (player_get ${rank}) pwr_capture_a)`);
      captured = true; record({ event: 'capture_a_requested', player: local.index });
    }
  }
  await new Promise(r => setTimeout(r, 500));
}
const sawTransports = transportCounts.warmup === 0 && transportCounts.insertion === 2 && transportCounts.cleanup === 0;
const result = { sawReady, sawSeated, sawCanopy, sawLanded, sawRespawn, sawScore, sawEnd,
  ...(args.has('--keyboard') ? { sawKeyboardExit } : {}),
  ...(args.has('--transports') ? { sawTransports, transportCounts } : {}) };
record({ event: 'result', ...result }); console.log(JSON.stringify({ out, ...result }, null, 2));
if (!sawReady || (args.has('--jump') && !(sawSeated && sawCanopy && sawLanded))
    || (args.has('--respawn') && !sawRespawn) || (args.has('--capture-a') && !sawScore)
    || (args.has('--expect-end') && !sawEnd)
    || (args.has('--keyboard') && args.has('--jump') && !sawKeyboardExit)
    || (args.has('--transports') && !sawTransports)) process.exitCode = 1;
