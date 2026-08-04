//! Writing a `.utoc` container index.
//!
//! [`crate::load_container`] parses a TOC into what a *reader* needs, which
//! throws away anything a reader does not use — the directory index becomes a
//! flat path map, the perfect-hash tables are skipped entirely. That is the
//! right shape for reading and the wrong shape for writing.
//!
//! This models the file itself: every field the format defines, in order, plus
//! the regions that are not yet interpreted kept verbatim so nothing is lost.
//! [`Toc::write`] rebuilds the bytes from those fields.
//!
//! The check that matters is that parsing a shipped container and writing it
//! straight back reproduces it byte for byte. That is not trivially true here:
//! the typed fields are re-encoded from their values, so a wrong width, a wrong
//! byte order, or a misplaced field shows up as a difference. Run it with
//! `mjolnir toc-roundtrip`.
//!
//! See `docs/iostore_packaging.md`.

use std::path::Path;

use crate::{Error, TOC_MAGIC, VER_PERFECT_HASH, VER_PERFECT_HASH_WITH_OVERFLOW};

/// One chunk's identity: which package, which part of it, and what kind.
///
/// On disk this is twelve bytes — and it mixes byte orders, which is the sort
/// of thing a round-trip catches and an eyeball does not. The package ID is
/// little-endian, the chunk index is **big**-endian, then a pad byte, then the
/// type.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChunkId {
    pub id: u64,
    pub index: u16,
    pub pad: u8,
    pub kind: u8,
}

impl ChunkId {
    fn read(b: &[u8]) -> ChunkId {
        ChunkId {
            id: u64::from_le_bytes(b[0..8].try_into().unwrap()),
            index: u16::from_be_bytes(b[8..10].try_into().unwrap()),
            pad: b[10],
            kind: b[11],
        }
    }

    /// The twelve bytes as they sit in the file — the form the perfect hash
    /// is computed over.
    pub fn bytes(&self) -> [u8; 12] {
        let mut out = [0u8; 12];
        out[0..8].copy_from_slice(&self.id.to_le_bytes());
        out[8..10].copy_from_slice(&self.index.to_be_bytes());
        out[10] = self.pad;
        out[11] = self.kind;
        out
    }

    fn write(&self, out: &mut Vec<u8>) {
        out.extend_from_slice(&self.bytes());
    }
}

/// The hash the engine uses for the perfect-hash tables: FNV-1a's prime over
/// the twelve raw ID bytes, but multiply-then-xor, seeded either by the FNV
/// offset basis (seed 0) or by the seed itself.
///
/// Two details pinned down empirically against `pakchunk0`'s engine-written
/// tables (all 122,804 chunks resolve; truncating either one resolves ~0):
/// the modulo downstream is taken on the **full 64-bit hash**, and the seed
/// is sign-extended from its signed 32-bit table slot. Only non-negative
/// seeds are ever hashed in practice — negative table entries mean "direct
/// index" and are never passed here — but the extension is kept faithful
/// anyway.
pub fn hash_chunk_id_with_seed(seed: i32, id: &ChunkId) -> u64 {
    let mut hash: u64 = if seed != 0 {
        seed as i64 as u64
    } else {
        0xcbf2_9ce4_8422_2325
    };
    for b in id.bytes() {
        hash = hash.wrapping_mul(0x0000_0100_0000_01B3) ^ b as u64;
    }
    hash
}

/// Where a chunk's data sits in the `.ucas`. Both are five-byte big-endian.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChunkOffset {
    pub offset: u64,
    pub length: u64,
}

/// Write `v` as `n` big-endian bytes.
fn put_be(out: &mut Vec<u8>, v: u64, n: usize) {
    for i in (0..n).rev() {
        out.push((v >> (8 * i)) as u8);
    }
}

/// Write `v` as `n` little-endian bytes.
fn put_le(out: &mut Vec<u8>, v: u64, n: usize) {
    for i in 0..n {
        out.push((v >> (8 * i)) as u8);
    }
}

fn get_be(b: &[u8]) -> u64 {
    b.iter().fold(0u64, |v, byte| (v << 8) | *byte as u64)
}

fn get_le(b: &[u8]) -> u64 {
    b.iter()
        .enumerate()
        .fold(0u64, |v, (i, byte)| v | (*byte as u64) << (8 * i))
}

/// One compression block. Offset is little-endian over five bytes; the two
/// sizes are little-endian over three each.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Block {
    pub offset: u64,
    pub compressed_size: u32,
    pub uncompressed_size: u32,
    pub method_index: u8,
}

/// A parsed `.utoc`, faithful enough to write back.
#[derive(Debug, Clone)]
pub struct Toc {
    pub version: u8,
    /// Bytes 17..20, undocumented here and preserved as they were.
    pub reserved0: [u8; 3],
    pub header_size: u32,
    pub block_entry_size: u32,
    pub method_name_length: u32,
    pub compression_block_size: u32,
    pub partition_count: u32,
    pub container_id: u64,
    pub encryption_guid: [u8; 16],
    pub flags: u8,
    /// Bytes 81..84.
    pub reserved1: [u8; 3],
    /// Perfect-hash seed count, at byte 84.
    pub perfect_hash_seed_count: u32,
    pub partition_size: u64,
    /// Chunks with no perfect-hash slot, at byte 96.
    pub chunks_without_perfect_hash: u32,
    /// Everything from byte 100 to `header_size`, kept verbatim.
    pub header_tail: Vec<u8>,

    pub chunk_ids: Vec<ChunkId>,
    pub chunk_offsets: Vec<ChunkOffset>,
    /// Perfect-hash seeds and the overflow list, not interpreted.
    pub perfect_hash: Vec<u8>,
    pub blocks: Vec<Block>,
    /// Compression method names, without the implicit "None" at index 0.
    pub methods: Vec<String>,
    /// The signature block, when the container is signed.
    pub signature: Vec<u8>,
    /// The directory index, not interpreted here.
    pub directory_index: Vec<u8>,
    /// One metadata record per chunk, `CHUNK_META` bytes each.
    ///
    /// Measured as exactly 24 bytes per entry on every shipped container, from
    /// the single-chunk ones up to `pakchunk0` with 122,800. For version 8 that
    /// is consistent with a 20-byte `IoHash` plus flags; the contents are not
    /// interpreted here, only kept per chunk so a container with a different
    /// number of chunks gets the right number of records.
    pub chunk_meta: Vec<u8>,
    /// Anything after the last known region. Empty on every shipped container.
    pub trailing: Vec<u8>,
}

/// Bytes of metadata carried per chunk, after the directory index.
pub const CHUNK_META: usize = 24;

impl Toc {
    pub fn read(path: impl AsRef<Path>) -> Result<Toc, Error> {
        Toc::parse(&std::fs::read(path.as_ref())?)
    }

    pub fn parse(blob: &[u8]) -> Result<Toc, Error> {
        if blob.len() < 144 || &blob[..16] != TOC_MAGIC {
            return Err(Error::BadMagic);
        }
        let u32_at = |o: usize| u32::from_le_bytes(blob[o..o + 4].try_into().unwrap());
        let u64_at = |o: usize| u64::from_le_bytes(blob[o..o + 8].try_into().unwrap());

        let version = blob[16];
        let header_size = u32_at(20);
        let entry_count = u32_at(24) as usize;
        let block_count = u32_at(28) as usize;
        let block_entry_size = u32_at(32);
        let method_count = u32_at(36) as usize;
        let method_name_length = u32_at(40);
        let dir_index_size = u32_at(48) as usize;
        let seed_count = u32_at(84) as usize;
        let without_hash = u32_at(96) as usize;

        let mut pos = header_size as usize;
        let take = |pos: &mut usize, n: usize| -> Vec<u8> {
            let end = (*pos + n).min(blob.len());
            let v = blob[(*pos).min(blob.len())..end].to_vec();
            *pos = end;
            v
        };

        let ids_raw = take(&mut pos, 12 * entry_count);
        let chunk_ids: Vec<ChunkId> = ids_raw.chunks_exact(12).map(ChunkId::read).collect();

        let offs_raw = take(&mut pos, 10 * entry_count);
        let chunk_offsets: Vec<ChunkOffset> = offs_raw
            .chunks_exact(10)
            .map(|r| ChunkOffset {
                offset: get_be(&r[0..5]),
                length: get_be(&r[5..10]),
            })
            .collect();

        let mut hash_len = 0;
        if version >= VER_PERFECT_HASH {
            hash_len += 4 * seed_count;
        }
        if version >= VER_PERFECT_HASH_WITH_OVERFLOW {
            hash_len += 4 * without_hash;
        }
        let perfect_hash = take(&mut pos, hash_len);

        let blocks_raw = take(&mut pos, block_entry_size as usize * block_count);
        let blocks: Vec<Block> = blocks_raw
            .chunks_exact(block_entry_size as usize)
            .map(|r| Block {
                offset: get_le(&r[0..5]),
                compressed_size: get_le(&r[5..8]) as u32,
                uncompressed_size: get_le(&r[8..11]) as u32,
                method_index: r[11],
            })
            .collect();

        let methods_raw = take(&mut pos, method_name_length as usize * method_count);
        let methods: Vec<String> = methods_raw
            .chunks_exact(method_name_length.max(1) as usize)
            .map(|r| {
                let end = r.iter().position(|b| *b == 0).unwrap_or(r.len());
                String::from_utf8_lossy(&r[..end]).into_owned()
            })
            .collect();

        let mut signature = Vec::new();
        if blob[80] & crate::FLAG_SIGNED != 0 {
            let n = i32::from_le_bytes(blob[pos..pos + 4].try_into().unwrap()) as usize;
            signature = take(&mut pos, 4 + n * 2 + n * block_count);
        }

        let directory_index = take(&mut pos, dir_index_size);
        let chunk_meta = take(&mut pos, CHUNK_META * entry_count);
        let trailing = blob[pos.min(blob.len())..].to_vec();

        Ok(Toc {
            version,
            reserved0: blob[17..20].try_into().unwrap(),
            header_size,
            block_entry_size,
            method_name_length,
            compression_block_size: u32_at(44),
            partition_count: u32_at(52),
            container_id: u64_at(56),
            encryption_guid: blob[64..80].try_into().unwrap(),
            flags: blob[80],
            reserved1: blob[81..84].try_into().unwrap(),
            perfect_hash_seed_count: seed_count as u32,
            partition_size: u64_at(88),
            chunks_without_perfect_hash: without_hash as u32,
            header_tail: blob[100..header_size as usize].to_vec(),
            chunk_ids,
            chunk_offsets,
            perfect_hash,
            blocks,
            methods,
            signature,
            directory_index,
            chunk_meta,
            trailing,
        })
    }

    /// Serialise back to `.utoc` bytes.
    ///
    /// Counts are taken from the collections rather than carried over, so a
    /// caller that adds a chunk does not have to remember to update the header.
    pub fn write(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(self.header_size as usize);
        out.extend_from_slice(TOC_MAGIC);
        out.push(self.version);
        out.extend_from_slice(&self.reserved0);
        out.extend_from_slice(&self.header_size.to_le_bytes());
        out.extend_from_slice(&(self.chunk_ids.len() as u32).to_le_bytes());
        out.extend_from_slice(&(self.blocks.len() as u32).to_le_bytes());
        out.extend_from_slice(&self.block_entry_size.to_le_bytes());
        out.extend_from_slice(&(self.methods.len() as u32).to_le_bytes());
        out.extend_from_slice(&self.method_name_length.to_le_bytes());
        out.extend_from_slice(&self.compression_block_size.to_le_bytes());
        out.extend_from_slice(&(self.directory_index.len() as u32).to_le_bytes());
        out.extend_from_slice(&self.partition_count.to_le_bytes());
        out.extend_from_slice(&self.container_id.to_le_bytes());
        out.extend_from_slice(&self.encryption_guid);
        out.push(self.flags);
        out.extend_from_slice(&self.reserved1);
        out.extend_from_slice(&self.perfect_hash_seed_count.to_le_bytes());
        out.extend_from_slice(&self.partition_size.to_le_bytes());
        out.extend_from_slice(&self.chunks_without_perfect_hash.to_le_bytes());
        out.extend_from_slice(&self.header_tail);
        debug_assert_eq!(out.len(), self.header_size as usize);

        for id in &self.chunk_ids {
            id.write(&mut out);
        }
        for o in &self.chunk_offsets {
            put_be(&mut out, o.offset, 5);
            put_be(&mut out, o.length, 5);
        }
        out.extend_from_slice(&self.perfect_hash);

        for b in &self.blocks {
            put_le(&mut out, b.offset, 5);
            put_le(&mut out, b.compressed_size as u64, 3);
            put_le(&mut out, b.uncompressed_size as u64, 3);
            out.push(b.method_index);
            // Any bytes past the twelve this format defines.
            out.resize(
                out.len() + self.block_entry_size.saturating_sub(12) as usize,
                0,
            );
        }

        for m in &self.methods {
            let mut name = vec![0u8; self.method_name_length as usize];
            let n = m.len().min(name.len());
            name[..n].copy_from_slice(&m.as_bytes()[..n]);
            out.extend_from_slice(&name);
        }

        out.extend_from_slice(&self.signature);
        out.extend_from_slice(&self.directory_index);
        out.extend_from_slice(&self.chunk_meta);
        out.extend_from_slice(&self.trailing);
        out
    }

    /// The metadata record for chunk `i`, if present.
    pub fn meta(&self, i: usize) -> Option<&[u8]> {
        self.chunk_meta.get(i * CHUNK_META..(i + 1) * CHUNK_META)
    }

    /// The perfect-hash seed table, when the TOC carries one.
    pub fn perfect_hash_seeds(&self) -> Vec<i32> {
        self.perfect_hash
            .get(..4 * self.perfect_hash_seed_count as usize)
            .unwrap_or(&[])
            .chunks_exact(4)
            .map(|c| i32::from_le_bytes(c.try_into().unwrap()))
            .collect()
    }

    /// The overflow list: entry indices findable only by scanning, because no
    /// perfect-hash seed places them.
    pub fn overflow_indices(&self) -> Vec<u32> {
        if self.version < VER_PERFECT_HASH_WITH_OVERFLOW {
            return Vec::new();
        }
        let start = 4 * self.perfect_hash_seed_count as usize;
        let len = 4 * self.chunks_without_perfect_hash as usize;
        self.perfect_hash
            .get(start..start + len)
            .unwrap_or(&[])
            .chunks_exact(4)
            .map(|c| u32::from_le_bytes(c.try_into().unwrap()))
            .collect()
    }

    /// Resolve through the perfect-hash tables alone, with no overflow scan.
    ///
    /// Seed-table slot is `hash(0, id) % seed_count`. A zero seed means no
    /// chunk hashed there; a negative seed is the entry index directly,
    /// `-seed - 1`, used for buckets holding one chunk; a positive seed
    /// rehashes, `hash(seed, id) % entry_count`. Either way the ID at the
    /// resulting slot must match.
    ///
    /// This is what anything checking a container it just *wrote* should use.
    /// `find_chunk` additionally scans the overflow list, which makes it a
    /// more forgiving oracle than the game: no shipped container populates
    /// that list, and a mod container that relied on it was not read at all in
    /// game while resolving perfectly here. A packer bug shipped through
    /// exactly that gap.
    ///
    /// `None` for a pre-perfect-hash container, which has no tables to consult.
    pub fn find_chunk_by_hash(&self, id: &ChunkId) -> Option<usize> {
        let n = self.chunk_ids.len();
        let seeds = self.perfect_hash_seeds();
        if n == 0 || self.version < VER_PERFECT_HASH || seeds.is_empty() {
            return None;
        }
        let seed = seeds[(hash_chunk_id_with_seed(0, id) % seeds.len() as u64) as usize];
        if seed == 0 {
            return None;
        }
        let slot = if seed < 0 {
            (-(seed as i64) - 1) as usize
        } else {
            (hash_chunk_id_with_seed(seed, id) % n as u64) as usize
        };
        (slot < n && self.chunk_ids[slot] == *id).then_some(slot)
    }

    /// Find a chunk's entry index the way the engine's reader does: the
    /// perfect hash first, then the overflow list.
    pub fn find_chunk(&self, id: &ChunkId) -> Option<usize> {
        let n = self.chunk_ids.len();
        if n == 0 {
            return None;
        }

        if self.version >= VER_PERFECT_HASH && !self.perfect_hash_seeds().is_empty() {
            if let Some(slot) = self.find_chunk_by_hash(id) {
                return Some(slot);
            }
            return self
                .overflow_indices()
                .into_iter()
                .map(|i| i as usize)
                .find(|&i| i < n && self.chunk_ids[i] == *id);
        }

        // Pre-perfect-hash containers: nothing to consult but the array.
        self.chunk_ids.iter().position(|c| c == id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_chunk_id_keeps_its_mixed_byte_order() {
        // Package ID little-endian, chunk index big-endian, then pad and type.
        let raw = [0x01, 0, 0, 0, 0, 0, 0, 0, 0x00, 0x07, 0xAB, 0x02];
        let id = ChunkId::read(&raw);
        assert_eq!(id.id, 1);
        assert_eq!(id.index, 7);
        assert_eq!(id.pad, 0xAB);
        assert_eq!(id.kind, 2);

        let mut out = Vec::new();
        id.write(&mut out);
        assert_eq!(out, raw, "writing must undo reading exactly");
    }

    #[test]
    fn five_byte_offsets_round_trip() {
        let mut out = Vec::new();
        put_be(&mut out, 0x01_02_03_04_05, 5);
        assert_eq!(out, [1, 2, 3, 4, 5]);
        assert_eq!(get_be(&out), 0x01_02_03_04_05);

        let mut out = Vec::new();
        put_le(&mut out, 0x01_02_03_04_05, 5);
        assert_eq!(out, [5, 4, 3, 2, 1]);
        assert_eq!(get_le(&out), 0x01_02_03_04_05);
    }

    #[test]
    fn a_short_or_wrong_blob_is_rejected() {
        assert!(matches!(Toc::parse(&[0u8; 200]), Err(Error::BadMagic)));
        assert!(matches!(Toc::parse(&[]), Err(Error::BadMagic)));
    }

    /// Resolve every chunk of every shipped container through [`Toc::find_chunk`].
    ///
    /// This is the ground truth for [`hash_chunk_id_with_seed`]: the seed
    /// tables in the shipped TOCs were written by the engine, so if our hash
    /// disagreed with the engine's on any of pakchunk0's 122,800 IDs, some
    /// lookup here would miss its slot. Ignored by default because it needs
    /// an installed game; point `MJOLNIR_PAKS` at the `Paks` directory and
    /// run with `--ignored`.
    #[test]
    #[ignore = "needs an installed game; set MJOLNIR_PAKS"]
    fn every_shipped_chunk_resolves_through_the_perfect_hash() {
        let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
        let mut containers = 0usize;
        let mut chunks = 0usize;
        for entry in std::fs::read_dir(&paks).expect("readable Paks dir") {
            let path = entry.unwrap().path();
            if path.extension().is_none_or(|e| e != "utoc") {
                continue;
            }
            let toc = Toc::read(&path).expect("shipped TOC parses");
            for (i, id) in toc.chunk_ids.iter().enumerate() {
                let found = toc.find_chunk(id);
                // Duplicate IDs cannot occur in one container, so every
                // chunk must come back as exactly its own slot.
                assert_eq!(
                    found,
                    Some(i),
                    "{}: chunk {:?} at slot {i} resolved to {:?}",
                    path.display(),
                    id,
                    found
                );
            }
            containers += 1;
            chunks += toc.chunk_ids.len();
        }
        assert!(containers > 0, "no .utoc files under {paks}");
        eprintln!("resolved {chunks} chunks across {containers} containers");
    }
}
