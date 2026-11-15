// node --test tools/mcp/game/test_request_publish.mjs
// No game calls: deterministic file-reader contention and clock stand-ins.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { publishRequestFile } from './game.mjs';

const failure = code => Object.assign(new Error(code), { code });

function mailbox(errors, writeError = null) {
  const temporary = 'request.781.tmp', target = 'request.txt';
  const previous = Buffer.from('id 780\nold request');
  const files = new Map([[target, previous]]);
  const writes = [], renames = [], removals = [], waits = [];
  let clock = 0, published = 0;
  return {
    temporary, target, previous, files, writes, renames, removals, waits,
    get elapsed() { return clock; },
    get published() { return published; },
    operations: {
      async writeFile(file, payload) {
        writes.push([file, payload]);
        files.set(file, Buffer.from(payload));
        if (writeError) throw writeError;
      },
      async rename(from, to) {
        renames.push([from, to, Buffer.from(files.get(from))]);
        assert.equal(files.get(to), previous, 'The existing target must survive until successful replacement');
        const error = typeof errors === 'function' ? errors() : errors.shift();
        if (error) throw error;
        files.set(to, files.get(from));
        files.delete(from);
        published++;
      },
      async unlink(file) {
        assert.notEqual(file, target, 'The live target must never be deleted');
        removals.push(file);
        files.delete(file);
      },
      async wait(ms) { waits.push(ms); clock += ms; },
      now() { return clock; },
    },
  };
}

test('EPERM and EBUSY recover by renaming the same single encoded request', async () => {
  const box = mailbox([failure('EPERM'), failure('EBUSY')]);
  const encoded = Buffer.from('mjolnir-bridge 1\nid 781\nop lua\nbytes 8\n--\nprint(1)');
  await publishRequestFile(box.temporary, box.target, encoded, box.operations);
  assert.equal(box.writes.length, 1);
  assert.equal(box.writes[0][1], encoded);
  assert.equal(box.renames.length, 3);
  for (const [from, to, payload] of box.renames) {
    assert.equal(from, box.temporary);
    assert.equal(to, box.target);
    assert.deepEqual(payload, encoded);
  }
  assert.deepEqual(box.files.get(box.target), encoded);
  assert.equal(box.files.has(box.temporary), false);
  assert.equal(box.published, 1);
  assert.deepEqual(box.removals, []);
  assert.deepEqual(box.waits, [20, 20]);
});

test('a persistent reader lock fails within 500ms and cleans only the temporary request', async () => {
  const locked = failure('EPERM'), box = mailbox(() => locked);
  await assert.rejects(publishRequestFile(box.temporary, box.target, 'id 781\n', box.operations),
    error => error === locked);
  assert.ok(box.elapsed > 0 && box.elapsed <= 500);
  assert.ok(box.renames.length > 1 && box.renames.length <= 26);
  assert.ok(box.waits.every(ms => ms > 0 && ms <= 20));
  assert.equal(box.writes.length, 1);
  assert.equal(box.published, 0);
  assert.equal(box.files.get(box.target), box.previous);
  assert.equal(box.files.has(box.temporary), false);
  assert.deepEqual(box.removals, [box.temporary]);
});

test('non-transient rename errors propagate immediately without replacing the target', async () => {
  for (const code of ['EACCES', 'ENOENT', 'ENOSPC']) {
    const error = failure(code), box = mailbox([error]);
    await assert.rejects(publishRequestFile(box.temporary, box.target, 'id 781\n', box.operations),
      caught => caught === error);
    assert.equal(box.writes.length, 1);
    assert.equal(box.renames.length, 1);
    assert.deepEqual(box.waits, []);
    assert.equal(box.files.get(box.target), box.previous);
    assert.deepEqual(box.removals, [box.temporary]);
  }
});

test('a partial temporary write is cleaned and its original error propagates without a rename', async () => {
  const error = failure('ENOSPC'), box = mailbox([], error);
  await assert.rejects(publishRequestFile(box.temporary, box.target, 'id 781\n', box.operations),
    caught => caught === error);
  assert.equal(box.writes.length, 1);
  assert.deepEqual(box.renames, []);
  assert.deepEqual(box.waits, []);
  assert.equal(box.files.get(box.target), box.previous);
  assert.equal(box.files.has(box.temporary), false);
  assert.deepEqual(box.removals, [box.temporary]);
});
