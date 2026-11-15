import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseObjects, parsePlayers, parseSnapshot, guardSnapshot, guardOccupant, guardVehicleVacant, insideVolume, main } from './smoke-warfare-vehicles.mjs';

const unit = 0xe2b70039, vehicle = 0xe2870018;
const source = `warfare-state 2
ready 1
status 2
host 1
instance 18446744073709550000
tick 100
sampled_ms 50000
layout 3
phase 2
rate 30
connected 1
globals 2 100 20569 3 1 0 0 0 0 0 0 0
player 7 0 5 0 -760 0 36 ${unit}
ordinal 7 0
`;
const playerText = 'player 7\t0xE2110007\tteam 0\tunit 0xE2B70039\tobjects\\characters\\masterchief\\masterchief\t0.00\t0.00\t0.00\r\n1 player(s)\r\n';
const objectRow = (index, datum, kind, parent = '-', player = '') => [index, datum, kind, kind === 'biped' ? 'bipd' : 'vehi', 'objects\\example', 1, 2, 3, '100% of 45', '100% of 70', parent, player, 0, '0x1234', 'team 0/0'].join('\t');
const inventory = (parent = '-') => `${objectRow(57, '0xE2B70039', 'biped', parent, 'player 7')}\r\n${objectRow(24, '0xE2870018', 'vehicle')}\r\n2 of 2 objects (thread 123, object array 2 of 2048 slots)\r\n`;

test('explicit opt-in is checked before importing or calling the game bridge', async () => {
  await assert.rejects(main([]), /No game calls made.*--drive/);
  await assert.rejects(main(['--drive', '--vehicle=pelican']), /--vehicle must be hog, tank or banshee/);
});

test('sparse player slot7 uses native ordinal0 and salted parent, including Windows lines', () => {
  const snapshot = parseSnapshot(source.replaceAll('\n', '\r\n'));
  const players = parsePlayers(playerText), objects = parseObjects(inventory());
  assert.equal(snapshot.instance, '18446744073709550000');
  assert.equal(guardSnapshot(snapshot).index, 7);
  assert.equal(guardOccupant(snapshot, players, objects).handle, unit);
  assert.equal(guardOccupant(snapshot, players, parseObjects(inventory('0xE2870018')), vehicle).parent, vehicle);
  assert.throws(() => guardOccupant(snapshot, players, objects, vehicle), /parent/);
  assert.throws(() => guardOccupant(snapshot, [{ ...players[0], unit: unit + 65536 }], objects), /roster/);
});

test('stale, changed, remote, precombat or old-layout snapshots cannot authorize input', () => {
  const snapshot = parseSnapshot(source);
  assert.throws(() => guardSnapshot(snapshot, snapshot), /stale/);
  guardSnapshot({ ...snapshot, tick: 101, sampled_ms: 50033 }, snapshot);
  for (const patch of [{ instance: '5' }, { tick: 99 }, { sampled_ms: 49999 }])
    assert.throws(() => guardSnapshot({ ...snapshot, ...patch }, snapshot), /stale/);
  for (const patch of [{ phase: 1 }, { host: 0 }, { connected: 2 }, { layout: 2 }])
    assert.throws(() => guardSnapshot({ ...snapshot, ...patch }));
  assert.throws(() => guardSnapshot({ ...snapshot, players: [{ ...snapshot.players[0], localUser: -1 }] }), /local/);
  assert.throws(() => guardSnapshot({ ...snapshot, ordinals: { 7: 7 } }), /ordinal/);
  assert.throws(() => parsePlayers(playerText.replace('unit 0xE2B70039', 'no unit')));
  assert.throws(() => parseObjects(inventory().replace('0xE2870018', '0xbroken')));
});

test('probe volume uses installed UE corner and Blam basis/extents, excluding neighbors', () => {
  const volume = { pos: [-76500, 500, 3300], forward: [1, 0, 0], up: [0, 0, 1], extents: [1000 / 304.8, 1000 / 304.8, 900 / 304.8] };
  assert.equal(insideVolume([-760 / 3.048, 0, 36 / 3.048], volume), true);
  assert.equal(insideVolume([-745 / 3.048, 0, 36 / 3.048], volume), false);
  assert.equal(insideVolume([-760 / 3.048, 0, 46 / 3.048], volume), false);
  assert.throws(() => insideVolume([0, 0, 0], { ...volume, forward: [2, 0, 0] }), /basis/);
});

test('attached stock turrets are not occupants, but their bipeds and players are', () => {
  const root = { handle: vehicle, kind: 'vehicle', parent: null, player: '' };
  const turret = { handle: vehicle + 1, kind: 'vehicle', parent: vehicle, player: '' };
  const weapon = { handle: vehicle + 2, kind: 'weapon', parent: turret.handle, player: '' };
  const soldier = { handle: unit, kind: 'biped', parent: turret.handle, player: '' };
  assert.equal(guardVehicleVacant(root, [root, turret, weapon]), true);
  assert.throws(() => guardVehicleVacant(root, [root, turret, soldier]), /occupied/);
  assert.throws(() => guardVehicleVacant(root, [root, { ...soldier, parent: vehicle, player: 'player 7' }]), /occupied/);
  assert.throws(() => guardVehicleVacant(root, [root, { ...turret, player: 'player 7' }]), /occupied/);
  assert.throws(() => guardVehicleVacant(turret, [root, turret]), /root vehicle/);
});
