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

use crate::toc::{Block, ChunkId, ChunkOffset, Toc};

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

/// Build an override container.
///
/// `template` supplies the format-level settings — version, header size, block
/// size, partitioning — so the result matches the containers it sits beside
/// rather than inventing values. Its chunks are not used.
pub fn build(template: &Toc, container_id: u64, entries: &[Entry]) -> Container {
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
        let mut meta = entry.meta.clone();
        meta.resize(crate::toc::CHUNK_META, 0);
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

    // One seed per chunk. A negative seed means "the entry is at index
    // -seed - 1", which is how the shipped one-chunk containers are written.
    let mut perfect_hash = Vec::with_capacity(4 * entries.len());
    for i in 0..entries.len() {
        perfect_hash.extend_from_slice(&(-(i as i32) - 1).to_le_bytes());
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
        perfect_hash_seed_count: entries.len() as u32,
        partition_size: template.partition_size,
        chunks_without_perfect_hash: 0,
        header_tail: template.header_tail.clone(),
        chunk_ids,
        chunk_offsets,
        perfect_hash,
        blocks,
        // No compression methods: every block is stored as-is.
        methods: Vec::new(),
        signature: Vec::new(),
        directory_index: empty_directory_index(),
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
        // size, so a chunk starting mid-block would read the wrong data.
        assert_eq!(toc.chunk_offsets[0].offset, 0);
        assert_eq!(toc.chunk_offsets[1].offset, 64);
    }

    #[test]
    fn seeds_point_directly_at_each_entry() {
        let built = build(
            &template(),
            0,
            &[
                Entry {
                    id: id(1),
                    data: vec![0; 4],
                    meta: vec![0; 24],
                },
                Entry {
                    id: id(2),
                    data: vec![0; 4],
                    meta: vec![0; 24],
                },
            ],
        );
        let toc = Toc::parse(&built.utoc).unwrap();
        assert_eq!(toc.perfect_hash_seed_count, 2);
        let seeds: Vec<i32> = toc
            .perfect_hash
            .chunks_exact(4)
            .map(|c| i32::from_le_bytes(c.try_into().unwrap()))
            .collect();
        assert_eq!(seeds, vec![-1, -2], "-seed - 1 is the entry index");
    }
}
