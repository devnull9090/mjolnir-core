//! Building a small IoStore container to override chunks in a shipped one.
//!
//! The goal is narrow on purpose: hold a handful of chunks whose IDs already
//! exist in the game's containers, so the loader finds ours instead. It is not
//! a general cooker.
//!
//! What makes this tractable is that a chunk ID does not have to be *derived*.
//! It is twelve bytes read straight out of the shipped index, so an override
//! reuses them exactly and the hardest unknown disappears.
//!
//! The shape follows `pakchunk1-Windows`, the smallest shipped container, which
//! is a useful proof that several choices here are legal rather than guesses:
//! it stores its one chunk **uncompressed** (no compression methods at all), it
//! carries a 34-byte directory index describing only a root, and its
//! perfect-hash seed table is a single `-1`.
//!
//! See `docs/iostore_packaging.md`.

use crate::toc::{hash_chunk_id_with_seed, Block, ChunkId, ChunkOffset, Toc};

/// Blocks are stored 16-byte aligned in the `.ucas`; the reader reads the
/// padded length and trims, so the padding has to actually be there.
const ALIGN: usize = 16;

/// A chunk to put in the container: its ID, its bytes, and the metadata record
/// that goes with it.
pub struct Entry {
    pub id: ChunkId,
    pub data: Vec<u8>,
    /// The 24-byte metadata record. Carried over from the chunk being
    /// overridden, since its contents are not yet interpreted; see the
    /// packaging notes for why that is a candidate failure cause.
    pub meta: Vec<u8>,
}

/// A container ready to write: the index and the data blob.
pub struct Container {
    pub utoc: Vec<u8>,
    pub ucas: Vec<u8>,
}

/// The minimal directory index a container needs: mount point `/`, one root
/// directory with no name, and no files or strings.
///
/// Copied in shape from `pakchunk1-Windows`, which carries exactly this. The
/// override is found by chunk ID rather than by path, so there is nothing to
/// list.
fn empty_directory_index() -> Vec<u8> {
    let mut out = Vec::new();
    // FString "/" — length includes the terminator.
    out.extend_from_slice(&2i32.to_le_bytes());
    out.extend_from_slice(b"/\0");
    // One directory entry, every field "none".
    out.extend_from_slice(&1i32.to_le_bytes());
    for _ in 0..4 {
        out.extend_from_slice(&0xFFFF_FFFFu32.to_le_bytes());
    }
    out.extend_from_slice(&0i32.to_le_bytes()); // files
    out.extend_from_slice(&0i32.to_le_bytes()); // strings
    out
}

/// A single-directory index naming this container's files.
///
/// Shape copied from the UE 5.5-staged `pakchunk990-MJOLNIRWORLD` container:
/// the mount point is the directory itself, one nameless root entry points at
/// the file chain, and each file carries its chunk index as user data. Enough
/// for a container whose files all live in one directory, which a new tag
/// package's `.uasset`/`.ubulk` pair does.
///
/// `mount` is the full directory with trailing slash, e.g.
/// `../../../Meteorite/Content/Tags/.../_Generated_/`.
pub fn directory_index(mount: &str, files: &[(String, u32)]) -> Vec<u8> {
    let mut out = Vec::new();
    let put_string = |out: &mut Vec<u8>, s: &str| {
        out.extend_from_slice(&((s.len() + 1) as i32).to_le_bytes());
        out.extend_from_slice(s.as_bytes());
        out.push(0);
    };
    put_string(&mut out, mount);
    // One root directory: no name, no children, its files start at 0.
    out.extend_from_slice(&1i32.to_le_bytes());
    out.extend_from_slice(&0xFFFF_FFFFu32.to_le_bytes()); // name
    out.extend_from_slice(&0xFFFF_FFFFu32.to_le_bytes()); // first child
    out.extend_from_slice(&0xFFFF_FFFFu32.to_le_bytes()); // next sibling
    out.extend_from_slice(&(if files.is_empty() { u32::MAX } else { 0 }).to_le_bytes());
    // The file chain.
    out.extend_from_slice(&(files.len() as i32).to_le_bytes());
    for (i, (_, chunk_index)) in files.iter().enumerate() {
        out.extend_from_slice(&(i as u32).to_le_bytes()); // name = string i
        let next = if i + 1 < files.len() {
            (i + 1) as u32
        } else {
            u32::MAX
        };
        out.extend_from_slice(&next.to_le_bytes());
        out.extend_from_slice(&chunk_index.to_le_bytes());
    }
    out.extend_from_slice(&(files.len() as i32).to_le_bytes());
    for (name, _) in files {
        put_string(&mut out, name);
    }
    out
}

/// The perfect-hash tables for a set of chunk IDs, plus the entry order they
/// imply.
///
/// The reader finds a chunk in two hops: `hash(0, id) % seed_count` picks a
/// seed, and the seed picks the entry slot — directly when negative
/// (`-seed - 1`), by rehash (`hash(seed, id) % entry_count`) when positive.
/// The consequence that makes this a *placement* problem rather than just a
/// table to emit: the TOC's per-chunk arrays must be ordered so each chunk
/// sits at the slot its seed sends the reader to.
///
/// The earlier version of this packer missed that. It wrote seed `-i - 1`
/// into table slot `i` in input order, which only agrees with the reader's
/// seed choice when there is one chunk — the reason multi-chunk containers
/// silently exposed a single chunk (`docs/iostore_packaging.md`).
struct PerfectHash {
    /// One signed seed per table slot; zero means no chunk hashes there.
    seeds: Vec<i32>,
    /// Slots findable only by scanning, for buckets no seed could place.
    overflow: Vec<u32>,
    /// `entry_at_slot[slot]` is the caller's entry index stored at that slot.
    entry_at_slot: Vec<usize>,
}

impl PerfectHash {
    /// How many seeds to try for one bucket before shunting it to the
    /// overflow list. Buckets average two chunks, so real searches end within
    /// a handful of iterations; the cap only bounds pathological inputs.
    const SEED_LIMIT: i32 = 1 << 20;

    /// How many table sizes `generate` tries before accepting a spill.
    const SIZE_LIMIT: usize = 64;

    /// Build the tables, growing the seed table until nothing has to spill.
    ///
    /// The engine's writer sizes the seed table at half the chunk count, and
    /// that is where this starts, so output stays comparable to shipped
    /// containers. It is not always *sufficient*, which is the bug this loop
    /// exists for: the rehash hop is `hash(seed, id) % n`, and modulo a power
    /// of two that sees only the hash's low bits — where FNV's multiply barely
    /// diffuses. Mod 2 the seed cancels out of the expression altogether, so
    /// two IDs agreeing there are inseparable by *any* seed and the bucket
    /// search cannot succeed however long it runs. At n = 2 and n = 4 that is
    /// common enough to hit an ordinary three-tag mod.
    ///
    /// Growing the seed table is the way out, and it is free: the reader takes
    /// the count from the header, and a bucket holding a single chunk is
    /// stored as a direct index that never rehashes at all. Splitting an
    /// inseparable pair into separate buckets sidesteps the dead bits
    /// entirely.
    ///
    /// Spilling is not a benign fallback. No shipped container uses the
    /// overflow list — 28 scanned, every one `without_hash = 0` — and a mod
    /// container that relied on it was not read by the game at all, silently
    /// reverting to shipped tags.
    fn generate(ids: &[ChunkId]) -> PerfectHash {
        let first = (ids.len() / 2).max(1);
        let mut spilled: Option<PerfectHash> = None;
        for seed_count in first..first + Self::SIZE_LIMIT {
            let attempt = PerfectHash::with_seed_count(ids, seed_count);
            if attempt.overflow.is_empty() {
                return attempt;
            }
            spilled.get_or_insert(attempt);
        }
        // Genuinely unplaceable; duplicate IDs are what reaches here. Keep the
        // engine-shaped table and leave them to the reader's scan.
        spilled.expect("at least one table size is tried")
    }

    fn with_seed_count(ids: &[ChunkId], seed_count: usize) -> PerfectHash {
        let n = ids.len();
        let mut buckets: Vec<Vec<usize>> = vec![Vec::new(); seed_count];
        for (e, id) in ids.iter().enumerate() {
            buckets[(hash_chunk_id_with_seed(0, id) % seed_count as u64) as usize].push(e);
        }

        // Big buckets first, while free slots are plentiful.
        let mut order: Vec<usize> = (0..seed_count).collect();
        order.sort_by_key(|&b| std::cmp::Reverse(buckets[b].len()));

        let mut seeds = vec![0i32; seed_count];
        let mut entry_at_slot = vec![usize::MAX; n];
        let mut taken = vec![false; n];
        let mut singles: Vec<usize> = Vec::new();
        let mut spill: Vec<usize> = Vec::new();

        for &b in &order {
            let bucket = &buckets[b];
            match bucket.len() {
                0 => break, // sorted descending: the rest are empty too
                1 => singles.push(b),
                _ => {
                    // Identical IDs hash identically under every seed, so no
                    // search can separate them. Recognise that up front rather
                    // than burning the seed limit: `generate` calls this once
                    // per table size, and duplicates spill at every one.
                    let duplicated = (1..bucket.len())
                        .any(|i| bucket[..i].iter().any(|&e| ids[e] == ids[bucket[i]]));
                    let seed = if duplicated {
                        None
                    } else {
                        (1..=Self::SEED_LIMIT).find(|&seed| {
                            let mut slots = Vec::with_capacity(bucket.len());
                            bucket.iter().all(|&e| {
                                let s =
                                    (hash_chunk_id_with_seed(seed, &ids[e]) % n as u64) as usize;
                                let free = !taken[s] && !slots.contains(&s);
                                slots.push(s);
                                free
                            })
                        })
                    };
                    match seed {
                        Some(seed) => {
                            seeds[b] = seed;
                            for &e in bucket {
                                let s =
                                    (hash_chunk_id_with_seed(seed, &ids[e]) % n as u64) as usize;
                                taken[s] = true;
                                entry_at_slot[s] = e;
                            }
                        }
                        None => spill.extend_from_slice(bucket),
                    }
                }
            }
        }

        // Chunks alone in their bucket don't need a search: park each in the
        // next free slot and store the slot in the seed directly.
        let mut free = (0..n).filter(|&s| !taken[s]);
        for b in singles {
            let s = free.next().expect("as many free slots as chunks");
            entry_at_slot[s] = buckets[b][0];
            seeds[b] = -(s as i32) - 1;
        }

        // Unplaceable chunks still occupy slots; the reader finds them by
        // scanning the overflow list.
        let mut overflow = Vec::with_capacity(spill.len());
        for e in spill {
            let s = free.next().expect("as many free slots as chunks");
            entry_at_slot[s] = e;
            overflow.push(s as u32);
        }

        PerfectHash {
            seeds,
            overflow,
            entry_at_slot,
        }
    }
}

/// Build an override container.
///
/// `template` supplies the format-level settings — version, header size, block
/// size, partitioning — so the result matches the containers it sits beside
/// rather than inventing values. Its chunks are not used.
pub fn build(template: &Toc, container_id: u64, entries: &[Entry]) -> Container {
    build_indexed(template, container_id, entries, None)
}

/// [`build`], optionally naming files in a real directory index.
///
/// `index` is a mount directory plus (file name, input entry index) pairs; the
/// entry indices are remapped to final hash-slot order automatically.
pub fn build_indexed(
    template: &Toc,
    container_id: u64,
    entries: &[Entry],
    index: Option<(&str, &[(String, usize)])>,
) -> Container {
    let block_size = template.compression_block_size as usize;

    let mut ucas: Vec<u8> = Vec::new();
    let mut blocks: Vec<Block> = Vec::new();
    let mut chunk_ids: Vec<ChunkId> = Vec::new();
    let mut chunk_offsets: Vec<ChunkOffset> = Vec::new();
    let mut chunk_meta: Vec<u8> = Vec::new();

    // Chunk offsets address an uncompressed stream, and the block index for a
    // chunk is its offset divided by the block size. Starting every chunk on a
    // block boundary keeps that mapping exact.
    let mut uncompressed_cursor = 0u64;

    for entry in entries {
        chunk_ids.push(entry.id);
        // The meta record is BLAKE3-160 of the uncompressed chunk data plus a
        // flags byte (1 = compressed; our blocks never are). The game verifies
        // it at least when it reads a ContainerHeader chunk at mount — a
        // copied-from-donor hash was exactly why a mod container's own header
        // was ignored. The caller's meta is disregarded on purpose.
        let _ = &entry.meta;
        let mut meta = [0u8; crate::toc::CHUNK_META];
        let hash = blake3::hash(&entry.data);
        meta[..20].copy_from_slice(&hash.as_bytes()[..20]);
        chunk_meta.extend_from_slice(&meta);
        chunk_offsets.push(ChunkOffset {
            offset: uncompressed_cursor,
            length: entry.data.len() as u64,
        });

        for piece in entry.data.chunks(block_size) {
            blocks.push(Block {
                offset: ucas.len() as u64,
                compressed_size: piece.len() as u32,
                uncompressed_size: piece.len() as u32,
                // Index 0 is the implicit "None"; the container declares no
                // compression methods at all.
                method_index: 0,
            });
            ucas.extend_from_slice(piece);
            let pad = (ALIGN - ucas.len() % ALIGN) % ALIGN;
            ucas.resize(ucas.len() + pad, 0);
        }

        // Round the stream cursor up to a whole number of blocks.
        let used = entry.data.len().div_ceil(block_size).max(1) * block_size;
        uncompressed_cursor += used as u64;
    }

    // Build the perfect-hash tables and reorder every per-chunk array to
    // match: the entry index *is* the hash slot, so the arrays cannot stay in
    // input order once more than one chunk is present.
    let hash = PerfectHash::generate(&chunk_ids);
    // Where each input entry landed, for the directory index's chunk refs.
    let mut slot_of_entry = vec![0u32; entries.len()];
    for (slot, &e) in hash.entry_at_slot.iter().enumerate() {
        slot_of_entry[e] = slot as u32;
    }
    let chunk_ids: Vec<ChunkId> = hash.entry_at_slot.iter().map(|&e| chunk_ids[e]).collect();
    let chunk_offsets: Vec<ChunkOffset> = hash
        .entry_at_slot
        .iter()
        .map(|&e| chunk_offsets[e])
        .collect();
    let chunk_meta: Vec<u8> = hash
        .entry_at_slot
        .iter()
        .flat_map(|&e| {
            chunk_meta[e * crate::toc::CHUNK_META..(e + 1) * crate::toc::CHUNK_META].to_vec()
        })
        .collect();

    let mut perfect_hash = Vec::with_capacity(4 * (hash.seeds.len() + hash.overflow.len()));
    for s in &hash.seeds {
        perfect_hash.extend_from_slice(&s.to_le_bytes());
    }
    for o in &hash.overflow {
        perfect_hash.extend_from_slice(&o.to_le_bytes());
    }

    let toc = Toc {
        version: template.version,
        reserved0: template.reserved0,
        header_size: template.header_size,
        block_entry_size: template.block_entry_size,
        method_name_length: template.method_name_length,
        compression_block_size: template.compression_block_size,
        partition_count: 1,
        container_id,
        encryption_guid: [0; 16],
        flags: crate::FLAG_INDEXED,
        reserved1: template.reserved1,
        perfect_hash_seed_count: hash.seeds.len() as u32,
        partition_size: template.partition_size,
        chunks_without_perfect_hash: hash.overflow.len() as u32,
        header_tail: template.header_tail.clone(),
        chunk_ids,
        chunk_offsets,
        perfect_hash,
        blocks,
        // No compression methods: every block is stored as-is.
        methods: Vec::new(),
        signature: Vec::new(),
        directory_index: match index {
            Some((mount, files)) => {
                let mapped: Vec<(String, u32)> = files
                    .iter()
                    .map(|(name, entry)| (name.clone(), slot_of_entry[*entry]))
                    .collect();
                directory_index(mount, &mapped)
            }
            None => empty_directory_index(),
        },
        chunk_meta,
        trailing: Vec::new(),
    };

    Container {
        utoc: toc.write(),
        ucas,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn template() -> Toc {
        Toc {
            version: 8,
            reserved0: [0; 3],
            header_size: 144,
            block_entry_size: 12,
            method_name_length: 32,
            compression_block_size: 65536,
            partition_count: 1,
            container_id: 0,
            encryption_guid: [0; 16],
            flags: crate::FLAG_INDEXED,
            reserved1: [0; 3],
            perfect_hash_seed_count: 0,
            partition_size: u64::MAX,
            chunks_without_perfect_hash: 0,
            header_tail: vec![0; 44],
            chunk_ids: Vec::new(),
            chunk_offsets: Vec::new(),
            perfect_hash: Vec::new(),
            blocks: Vec::new(),
            methods: Vec::new(),
            signature: Vec::new(),
            directory_index: Vec::new(),
            chunk_meta: Vec::new(),
            trailing: Vec::new(),
        }
    }

    fn id(n: u64) -> ChunkId {
        ChunkId {
            id: n,
            index: 0,
            pad: 0,
            kind: 2,
        }
    }

    #[test]
    fn the_index_it_writes_parses_back() {
        let built = build(
            &template(),
            0x1234,
            &[Entry {
                id: id(7),
                data: vec![0xAB; 100],
                meta: vec![0; 24],
            }],
        );
        let toc = Toc::parse(&built.utoc).expect("must parse");
        assert_eq!(toc.chunk_ids.len(), 1);
        assert_eq!(toc.chunk_ids[0], id(7));
        assert_eq!(toc.chunk_offsets[0].length, 100);
        assert_eq!(toc.container_id, 0x1234);
        assert_eq!(toc.blocks.len(), 1);
        assert_eq!(toc.blocks[0].uncompressed_size, 100);
        assert_eq!(toc.blocks[0].method_index, 0);
    }

    #[test]
    fn block_data_is_sixteen_byte_aligned() {
        // The reader reads each block padded up to 16 bytes, so the padding has
        // to exist or the last block runs off the end of the file.
        let built = build(
            &template(),
            0,
            &[Entry {
                id: id(1),
                data: vec![1u8; 100],
                meta: vec![0; 24],
            }],
        );
        assert_eq!(built.ucas.len(), 112, "100 bytes padded to a 16-byte bound");
        assert_eq!(&built.ucas[..100], &[1u8; 100]);
        assert!(built.ucas[100..].iter().all(|b| *b == 0));
    }

    #[test]
    fn a_chunk_larger_than_one_block_splits() {
        let mut t = template();
        t.compression_block_size = 64;
        let built = build(
            &t,
            0,
            &[Entry {
                id: id(1),
                data: vec![9u8; 200],
                meta: vec![0; 24],
            }],
        );
        let toc = Toc::parse(&built.utoc).unwrap();
        assert_eq!(toc.blocks.len(), 4, "200 bytes over 64-byte blocks");
        assert_eq!(toc.blocks[3].uncompressed_size, 8);
        assert_eq!(toc.chunk_offsets[0].length, 200);
    }

    #[test]
    fn each_chunk_starts_on_a_block_boundary() {
        let mut t = template();
        t.compression_block_size = 64;
        let built = build(
            &t,
            0,
            &[
                Entry {
                    id: id(1),
                    data: vec![1u8; 10],
                    meta: vec![0; 24],
                },
                Entry {
                    id: id(2),
                    data: vec![2u8; 10],
                    meta: vec![0; 24],
                },
            ],
        );
        let toc = Toc::parse(&built.utoc).unwrap();
        // The reader finds a chunk's blocks by dividing its offset by the block
        // size, so a chunk starting mid-block would read the wrong data. The
        // perfect hash decides which chunk sits at which slot, so assert on
        // the set of offsets rather than their order.
        let mut offsets: Vec<u64> = toc.chunk_offsets.iter().map(|o| o.offset).collect();
        offsets.sort_unstable();
        assert_eq!(offsets, vec![0, 64]);
    }

    /// Read a chunk's bytes back out of a built container, resolving it the
    /// way the engine would.
    fn read_back(toc: &Toc, ucas: &[u8], cid: ChunkId) -> Option<Vec<u8>> {
        let slot = toc.find_chunk(&cid)?;
        assert_eq!(
            toc.chunk_ids[slot], cid,
            "slot must hold the chunk asked for"
        );
        let off = toc.chunk_offsets[slot];
        let bs = toc.compression_block_size as usize;
        let mut out = Vec::new();
        let mut block = off.offset as usize / bs;
        let mut remaining = off.length as usize;
        while remaining > 0 {
            let b = &toc.blocks[block];
            let take = remaining.min(b.uncompressed_size as usize);
            out.extend_from_slice(&ucas[b.offset as usize..b.offset as usize + take]);
            remaining -= take;
            block += 1;
        }
        Some(out)
    }

    #[test]
    fn a_single_chunk_container_matches_the_shipped_shape() {
        // pakchunk1-Windows carries exactly this: one seed, and it is -1.
        let built = build(
            &template(),
            0,
            &[Entry {
                id: id(7),
                data: vec![3u8; 8],
                meta: vec![0; 24],
            }],
        );
        let toc = Toc::parse(&built.utoc).unwrap();
        assert_eq!(toc.perfect_hash_seed_count, 1);
        assert_eq!(toc.perfect_hash_seeds(), vec![-1]);
        assert_eq!(toc.chunks_without_perfect_hash, 0);
        assert_eq!(toc.find_chunk(&id(7)), Some(0));
    }

    #[test]
    fn every_chunk_in_a_multi_chunk_container_resolves() {
        // The old writer emitted seeds the reader's hash never selects, so a
        // multi-chunk container silently exposed one chunk. Resolve every
        // chunk through the reader's own algorithm and check its bytes.
        let mut t = template();
        t.compression_block_size = 64;

        // Powers of two are in here on purpose: the rehash modulo degenerates
        // there, and 2 and 4 are the sizes an ordinary mod actually has.
        for n in [2usize, 3, 4, 7, 8, 16, 25, 32, 200] {
            let entries: Vec<Entry> = (0..n)
                .map(|i| Entry {
                    // Vary every field that feeds the hash, and size chunks
                    // across block boundaries.
                    id: ChunkId {
                        id: 0x1000 + 37 * i as u64,
                        index: (i % 5) as u16,
                        pad: 0,
                        kind: if i % 3 == 0 { 1 } else { 2 },
                    },
                    data: vec![i as u8; 40 + (i % 4) * 64],
                    meta: vec![0; 24],
                })
                .collect();

            let built = build(&t, 0xC0FFEE, &entries);
            let toc = Toc::parse(&built.utoc).unwrap();
            assert_eq!(toc.chunk_ids.len(), n);
            // The table starts at the engine's half-count and only grows when
            // a size cannot place every chunk.
            assert!(toc.perfect_hash_seed_count as usize >= (n / 2).max(1));
            assert_eq!(
                toc.chunks_without_perfect_hash, 0,
                "distinct IDs must all get a hash slot at n = {n}; the overflow \
                 list is not read by the game"
            );

            for e in &entries {
                toc.find_chunk_by_hash(&e.id)
                    .unwrap_or_else(|| panic!("chunk {:?} of {n} must resolve by hash", e.id));
                let data = read_back(&toc, &built.ucas, e.id)
                    .unwrap_or_else(|| panic!("chunk {:?} of {n} must resolve", e.id));
                assert_eq!(data, e.data, "chunk {:?} of {n} must round-trip", e.id);
            }
        }
    }

    #[test]
    fn the_four_tag_mod_that_spilled_every_chunk_now_places_them() {
        // Real IDs, from a mod editing the spartans biped, both fall-damage
        // effects and globals. At four entries every one of them landed in the
        // overflow list and none resolved, so the game read no edit at all and
        // the mod appeared to do nothing.
        //
        // These four are also a genuine worst case: they pair up under the
        // mod-2 invariant the rehash cannot see past, two to each value.
        let entries: Vec<Entry> = [
            0x8da5_079f_be94_7049u64,
            0x98d9_2e76_d077_0f80,
            0xe4f5_53b7_d393_5d5c,
            0x78be_a50c_1f97_0461,
        ]
        .iter()
        .map(|&pkg| Entry {
            id: ChunkId {
                id: pkg,
                index: 0,
                pad: 0,
                kind: 2,
            },
            data: vec![0xAB; 32],
            meta: vec![0; 24],
        })
        .collect();

        let built = build(&template(), 0, &entries);
        let toc = Toc::parse(&built.utoc).unwrap();
        assert_eq!(
            toc.chunks_without_perfect_hash, 0,
            "every chunk must get a hash slot"
        );
        for e in &entries {
            assert!(
                toc.find_chunk_by_hash(&e.id).is_some(),
                "chunk {:?} must resolve without the overflow scan",
                e.id
            );
        }
    }

    #[test]
    fn metadata_records_follow_their_chunks_through_the_permutation() {
        // Meta is computed from each chunk's data (BLAKE3-160 + flags), so
        // distinct data makes each record recognisable.
        let entries: Vec<Entry> = (0..8u8)
            .map(|i| Entry {
                id: id(100 + i as u64),
                data: vec![i; 4],
                meta: Vec::new(),
            })
            .collect();
        let built = build(&template(), 0, &entries);
        let toc = Toc::parse(&built.utoc).unwrap();
        for e in &entries {
            let slot = toc.find_chunk(&e.id).expect("resolves");
            let mut want = [0u8; crate::toc::CHUNK_META];
            want[..20].copy_from_slice(&blake3::hash(&e.data).as_bytes()[..20]);
            assert_eq!(
                toc.meta(slot).unwrap(),
                &want[..],
                "meta must be the chunk's own hash, at the chunk's slot"
            );
        }
    }

    #[test]
    fn duplicate_ids_fall_back_to_the_overflow_list() {
        // Two entries with the same ID can never both get a perfect-hash
        // slot. They must not wedge the seed search; they land in the
        // overflow list and the scan finds the first.
        let built = build(
            &template(),
            0,
            &[
                Entry {
                    id: id(5),
                    data: vec![1; 4],
                    meta: vec![0; 24],
                },
                Entry {
                    id: id(5),
                    data: vec![2; 4],
                    meta: vec![0; 24],
                },
            ],
        );
        let toc = Toc::parse(&built.utoc).unwrap();
        assert_eq!(toc.chunks_without_perfect_hash, 2);
        let slot = toc.find_chunk(&id(5)).expect("still findable");
        assert_eq!(toc.chunk_ids[slot], id(5));
    }
}
