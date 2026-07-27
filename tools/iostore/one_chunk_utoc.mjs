// Rewrite the override .utoc to hold ONLY the bulk-data chunk.
//
// With a single entry the perfect hash cannot collide -- hash % 1 is always 0,
// and the one seed points at the one entry -- so if the loader still ignores
// our payload, that is not a hash problem.
//
// Layout comes from decoding the 302-byte original; see docs/iostore_packaging.md.
import fs from "node:fs";

const src = process.argv[2];
const out = process.argv[3];
const b = fs.readFileSync(src);

const HEADER = 144;
const entryCount = b.readUInt32LE(24);
const blockCount = b.readUInt32LE(28);
const dirSize = b.readUInt32LE(48);
const seedCount = b.readUInt32LE(84);
console.log(`source: ${entryCount} entries, ${blockCount} blocks, ${seedCount} seeds, dir ${dirSize}`);

// Region starts, in the order the format lays them out.
const ids = HEADER;
const offsets = ids + 12 * entryCount;
const seeds = offsets + 10 * entryCount;
const blocks = seeds + 4 * seedCount;
const dir = blocks + 12 * blockCount;
const meta = dir + dirSize;
console.log(`regions: ids@${ids} offsets@${offsets} seeds@${seeds} blocks@${blocks} dir@${dir} meta@${meta} end@${meta + 24 * entryCount} (file ${b.length})`);

// Which entry is the bulk chunk? Byte 11 of a chunk ID is its type.
let bulk = -1;
for (let i = 0; i < entryCount; i++) {
  const type = b[ids + i * 12 + 11];
  console.log(`  entry ${i}: type ${type}`);
  if (type === 2) bulk = i;
}
if (bulk < 0) throw new Error("no type-2 chunk in this container");
console.log(`keeping entry ${bulk}`);

// The chunk's logical offset must become 0 so it maps to block 0.
const offset = Buffer.from(b.subarray(offsets + bulk * 10, offsets + (bulk + 1) * 10));
offset.fill(0, 0, 5);   // 5-byte big-endian offset -> 0

// And its block must point at where that chunk actually sits in the .ucas.
const blockIndex = Number(b.readUIntBE(offsets + bulk * 10, 5) / 65536);
const block = Buffer.from(b.subarray(blocks + blockIndex * 12, blocks + (blockIndex + 1) * 12));

const header = Buffer.from(b.subarray(0, HEADER));
header.writeUInt32LE(1, 24);   // entry count
header.writeUInt32LE(1, 28);   // compressed block count
header.writeUInt32LE(1, 84);   // perfect-hash seed count

const seed = Buffer.alloc(4);
seed.writeInt32LE(-1, 0);      // negative seed: "the entry is at index -seed - 1"

const result = Buffer.concat([
  header,
  b.subarray(ids + bulk * 12, ids + (bulk + 1) * 12),
  offset,
  seed,
  block,
  b.subarray(dir, dir + dirSize),
  b.subarray(meta + bulk * 24, meta + (bulk + 1) * 24),
]);

fs.writeFileSync(out, result);
console.log(`wrote ${out}, ${result.length} bytes (was ${b.length})`);
console.log(`  block -> .ucas offset ${block.readUIntLE(0, 5)}, size ${block.readUIntLE(5, 3)}`);
