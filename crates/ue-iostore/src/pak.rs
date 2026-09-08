//! Read-only Unreal Engine 5 `.pak` archive reader.
//!
//! IoStore (`.ucas`/`.utoc`) holds the cooked packages, but a shipped title can
//! still put loose files in a sibling `.pak`. Campaign Evolved keeps its entire
//! Wwise audio bank there — roughly 6 GB the IoStore reader never sees.
//!
//! Scope matches the IoStore side: enumerate the directory index and read
//! individual files back into memory. The one thing written is the empty
//! archive a container triple needs to be discovered at all — see
//! [`write_stub`].
//!
//! Format reference: UE 5.5 `IPlatformFilePak.cpp` (`FPakInfo::Serialize`,
//! `FPakFile::DecodePakEntry`, `FPakFile::SaveIndex`).

use std::collections::BTreeMap;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use sha1::{Digest, Sha1};

use crate::{decompress, Error};

pub const PAK_MAGIC: u32 = 0x5A6F_12E1;

/// The pak format version the game ships: `PakFile_Version_Fnv64BugFix`,
/// the last one UE 5.5 writes.
pub const PAK_VERSION: u32 = 11;

/// Compression method slots recorded in the footer, 32 bytes each.
const MAX_METHODS: usize = 5;
/// GUID + encrypted flag + magic + version + index offset/size + hash + methods.
const FOOTER_SIZE: u64 = 16 + 1 + 4 + 4 + 8 + 8 + 20 + (32 * MAX_METHODS) as u64;

/// Offsets inside a compressed entry became entry-relative in this version.
const VER_RELATIVE_CHUNK_OFFSETS: u32 = 9;

/// One file stored in a `.pak`.
#[derive(Debug, Clone)]
pub struct PakEntry {
    /// Offset of the entry's inline header; the payload follows it.
    pub offset: u64,
    /// Stored size — compressed, when a method is set.
    pub size: u64,
    pub uncompressed_size: u64,
    /// Index into the archive's `compression_methods`; 0 means stored as-is.
    pub method_index: u8,
    pub encrypted: bool,
    pub block_size: u32,
    /// Compressed block extents, as `(start, end)` relative to `offset`.
    pub blocks: Vec<(u64, u64)>,
}

/// Size of the `FPakEntry` header written inline ahead of a payload.
///
/// Offset, Size, UncompressedSize, Hash and CompressionMethodIndex, then Flags
/// and CompressionBlockSize, then the block table when the entry is compressed.
fn header_size(method_index: u8, block_count: usize) -> u64 {
    let n = 8 + 8 + 8 + 20 + 4 + 1 + 4;
    if method_index != 0 {
        n + 16 * block_count as u64 + 4
    } else {
        n
    }
}

impl PakEntry {
    fn header_size(&self) -> u64 {
        header_size(self.method_index, self.blocks.len())
    }
}

/// A loaded `.pak` directory index.
#[derive(Debug)]
pub struct PakArchive {
    pub path: PathBuf,
    pub version: u32,
    /// Mount prefix every path in `files` hangs off, e.g.
    /// `../../../Meteorite/Content/WwiseAudio/`.
    pub mount_point: String,
    pub compression_methods: Vec<String>,
    /// Mount-relative path to entry, sorted so a directory is a contiguous run.
    pub files: BTreeMap<String, PakEntry>,
}

impl PakArchive {
    /// Full path including the mount point.
    pub fn full_path(&self, rel: &str) -> String {
        format!("{}{}", self.mount_point, rel)
    }
}

struct Cursor<'a> {
    buf: &'a [u8],
    pos: usize,
}

impl<'a> Cursor<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], Error> {
        let end = self.pos.checked_add(n).ok_or(Error::Truncated {
            wanted: n,
            have: self.buf.len().saturating_sub(self.pos),
        })?;
        // `pos` can start past the end: the location comes from the index and
        // is not trusted to be in range.
        if end > self.buf.len() {
            return Err(Error::Truncated {
                wanted: n,
                have: self.buf.len().saturating_sub(self.pos),
            });
        }
        let out = &self.buf[self.pos..end];
        self.pos = end;
        Ok(out)
    }

    fn u32(&mut self) -> Result<u32, Error> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }

    fn i32(&mut self) -> Result<i32, Error> {
        Ok(i32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }

    fn u64(&mut self) -> Result<u64, Error> {
        Ok(u64::from_le_bytes(self.take(8)?.try_into().unwrap()))
    }

    /// Unreal `FString`: negative length means UTF-16, positive means UTF-8.
    /// Both include a trailing NUL in the count.
    fn fstring(&mut self) -> Result<String, Error> {
        let len = self.i32()?;
        if len == 0 {
            return Ok(String::new());
        }
        if len < 0 {
            let units: Vec<u16> = self
                .take((-len as usize) * 2)?
                .chunks_exact(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .collect();
            Ok(String::from_utf16_lossy(&units)
                .trim_end_matches('\0')
                .to_string())
        } else {
            Ok(String::from_utf8_lossy(self.take(len as usize)?)
                .trim_end_matches('\0')
                .to_string())
        }
    }
}

/// Decode one entry from the packed `EncodedPakEntries` blob.
///
/// The leading bitfield says which fields were narrowed to 32 bits, so the
/// record length varies per entry.
fn decode_entry(buf: &[u8], at: usize, version: u32) -> Result<PakEntry, Error> {
    let mut c = Cursor { buf, pos: at };
    // Bit 31 offset is 32-bit safe, 30 uncompressed size, 29 size,
    // bits 28-23 compression method, 22 encrypted, 21-6 block count,
    // bits 5-0 block size in 2 KiB units.
    let flags = c.u32()?;
    let method_index = ((flags >> 23) & 0x3F) as u8;

    let offset = if flags & (1 << 31) != 0 {
        c.u32()? as u64
    } else {
        c.u64()?
    };
    let uncompressed_size = if flags & (1 << 30) != 0 {
        c.u32()? as u64
    } else {
        c.u64()?
    };
    // Only a compressed entry stores a separate stored size.
    let size = if method_index != 0 {
        if flags & (1 << 29) != 0 {
            c.u32()? as u64
        } else {
            c.u64()?
        }
    } else {
        uncompressed_size
    };

    let encrypted = flags & (1 << 22) != 0;
    let block_count = ((flags >> 6) & 0xFFFF) as usize;
    let block_size = if block_count > 0 {
        // A payload under one block records no size; it is its own block.
        if uncompressed_size < 65536 {
            uncompressed_size as u32
        } else {
            (flags & 0x3F) << 11
        }
    } else {
        0
    };

    let mut entry = PakEntry {
        offset,
        size,
        uncompressed_size,
        method_index,
        encrypted,
        block_size,
        blocks: Vec::with_capacity(block_count),
    };

    // Offsets are entry-relative from v9 on, absolute before that.
    let base = if version >= VER_RELATIVE_CHUNK_OFFSETS {
        0
    } else {
        offset
    };

    let payload = base + header_size(method_index, block_count);
    if block_count == 1 && !encrypted {
        // A lone unencrypted block is implied by the header and payload sizes.
        entry.blocks.push((payload, payload + size));
    } else if block_count > 0 {
        // Encrypted payloads pad each block up to the AES block size.
        let align = if encrypted { 16 } else { 1 };
        let mut at = payload;
        for _ in 0..block_count {
            let len = c.u32()? as u64;
            entry.blocks.push((at, at + len));
            at += len.div_ceil(align) * align;
        }
    }

    Ok(entry)
}

/// Read a `.pak` footer and directory index.
pub fn load_pak(path: impl AsRef<Path>) -> Result<PakArchive, Error> {
    let path = path.as_ref().to_path_buf();
    let mut fh = File::open(&path)?;
    let file_size = fh.metadata()?.len();
    if file_size < FOOTER_SIZE {
        return Err(Error::BadMagic);
    }

    fh.seek(SeekFrom::Start(file_size - FOOTER_SIZE))?;
    let mut footer = vec![0u8; FOOTER_SIZE as usize];
    fh.read_exact(&mut footer)?;
    let mut c = Cursor {
        buf: &footer,
        pos: 16, // skip the encryption key GUID
    };
    let encrypted_index = c.take(1)?[0] != 0;
    if c.u32()? != PAK_MAGIC {
        return Err(Error::BadMagic);
    }
    let version = c.u32()?;
    let index_offset = c.u64()?;
    let index_size = c.u64()?;
    c.take(20)?; // index hash
    if encrypted_index {
        return Err(Error::Encrypted);
    }

    let mut compression_methods = vec!["None".to_string()];
    for _ in 0..MAX_METHODS {
        let raw = c.take(32)?;
        let name = String::from_utf8_lossy(raw)
            .trim_end_matches('\0')
            .to_string();
        if !name.is_empty() {
            compression_methods.push(name);
        }
    }

    if index_offset + index_size > file_size {
        return Err(Error::Truncated {
            wanted: index_size as usize,
            have: file_size.saturating_sub(index_offset) as usize,
        });
    }
    fh.seek(SeekFrom::Start(index_offset))?;
    let mut index = vec![0u8; index_size as usize];
    fh.read_exact(&mut index)?;

    let mut c = Cursor {
        buf: &index,
        pos: 0,
    };
    let mount_point = c.fstring()?;
    let _num_entries = c.i32()?;
    let _path_hash_seed = c.u64()?;
    if c.i32()? != 0 {
        // Path hash index: offset, size, hash. The directory index covers the
        // same files by name, so this one is skipped.
        c.take(8 + 8 + 20)?;
    }
    if c.i32()? == 0 {
        // Without it there are only hashed paths, and no names to show.
        return Err(Error::UnsupportedCompression(
            "pak has no full directory index".to_string(),
        ));
    }
    let dir_offset = c.u64()?;
    let dir_size = c.u64()?;
    c.take(20)?; // directory index hash

    let encoded_len = c.u32()? as usize;
    let encoded = c.take(encoded_len)?.to_vec();

    if dir_offset + dir_size > file_size {
        return Err(Error::Truncated {
            wanted: dir_size as usize,
            have: file_size.saturating_sub(dir_offset) as usize,
        });
    }
    fh.seek(SeekFrom::Start(dir_offset))?;
    let mut dir = vec![0u8; dir_size as usize];
    fh.read_exact(&mut dir)?;

    let mut d = Cursor {
        buf: &dir,
        pos: 0,
    };
    let mut files = BTreeMap::new();
    let dir_count = d.u32()?;
    for _ in 0..dir_count {
        let dir_name = d.fstring()?;
        let file_count = d.u32()?;
        for _ in 0..file_count {
            let file_name = d.fstring()?;
            // FPakEntryLocation: >= 0 is a byte offset into the encoded blob,
            // negative indexes the unencoded list, i32::MIN means deleted.
            let location = d.i32()?;
            if location < 0 {
                continue;
            }
            let Ok(entry) = decode_entry(&encoded, location as usize, version) else {
                continue;
            };
            files.insert(format!("{dir_name}{file_name}"), entry);
        }
    }

    Ok(PakArchive {
        path,
        version,
        mount_point,
        compression_methods,
        files,
    })
}

/// Read one file back into memory, decompressing only the blocks needed.
///
/// `max_bytes` caps the read so header inspection does not pay for a full
/// multi-megabyte payload.
pub fn read_file(
    pak: &PakArchive,
    entry: &PakEntry,
    max_bytes: Option<usize>,
    oodle_roots: &[PathBuf],
) -> Result<Vec<u8>, Error> {
    if entry.encrypted {
        return Err(Error::Encrypted);
    }
    let wanted = match max_bytes {
        Some(m) => (entry.uncompressed_size as usize).min(m),
        None => entry.uncompressed_size as usize,
    };
    if wanted == 0 {
        return Ok(Vec::new());
    }

    let mut fh = File::open(&pak.path)?;

    // Stored as-is: the payload sits straight after the inline header.
    if entry.method_index == 0 || entry.blocks.is_empty() {
        fh.seek(SeekFrom::Start(entry.offset + entry.header_size()))?;
        let mut out = vec![0u8; wanted];
        fh.read_exact(&mut out)?;
        return Ok(out);
    }

    let method = pak
        .compression_methods
        .get(entry.method_index as usize)
        .ok_or_else(|| Error::UnsupportedCompression(format!("method {}", entry.method_index)))?;

    let mut out: Vec<u8> = Vec::with_capacity(wanted);
    for (start, end) in &entry.blocks {
        if out.len() >= wanted {
            break;
        }
        let mut raw = vec![0u8; (end - start) as usize];
        fh.seek(SeekFrom::Start(entry.offset + start))?;
        fh.read_exact(&mut raw)?;
        // The tail block is short whenever the payload is not a whole multiple.
        let remaining = entry.uncompressed_size as usize - out.len();
        let block_out = (entry.block_size as usize).min(remaining);
        out.extend_from_slice(&decompress(method, &raw, block_out, oodle_roots)?);
    }
    out.truncate(wanted);
    Ok(out)
}

/// Load every `.pak` in a directory, skipping archives that fail to parse.
///
/// An empty or index-less pak is normal in a shipped build; those are dropped
/// rather than failing the whole load.
pub fn load_all(paks_dir: impl AsRef<Path>) -> Result<Vec<PakArchive>, Error> {
    let mut paths: Vec<PathBuf> = std::fs::read_dir(paks_dir)?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("pak"))
        .collect();
    paths.sort();
    Ok(paths
        .iter()
        .filter_map(|p| load_pak(p).ok())
        .filter(|p| !p.files.is_empty())
        .collect())
}

fn push_i32(out: &mut Vec<u8>, v: i32) {
    out.extend_from_slice(&v.to_le_bytes());
}

fn push_u64(out: &mut Vec<u8>, v: u64) {
    out.extend_from_slice(&v.to_le_bytes());
}

fn sha1_of(bytes: &[u8]) -> [u8; 20] {
    let mut h = Sha1::new();
    h.update(bytes);
    h.finalize().into()
}

/// Size of the primary index [`write_stub`] emits; the secondary indexes and
/// the footer's `IndexSize` all refer to it.
const STUB_INDEX_SIZE: u64 = 106;

/// An empty version-11 archive: the `.pak` a `.utoc`/`.ucas` pair must have
/// beside it to be mounted at all.
///
/// The game discovers containers by their `.pak` sibling, then reads the
/// IoStore pair; the archive itself may hold nothing. Every shipped stub is
/// this exact shape — 339 bytes, mount point `/`, zero entries, an empty
/// path-hash index and an empty full directory index — differing only in the
/// path-hash seed and the footer's hash of the primary index. The seed is
/// meaningless with no entries to hash, so any value serves; callers pass
/// something stable per container so a rebuild is byte-identical.
///
/// Layout, in `FPakFile::SaveIndex` order:
///
/// ```text
/// primary index (106 bytes, at offset 0)
///   FString mount point "/"            i32 2, '/', NUL
///   NumEntries                          i32 0
///   PathHashSeed                        u64
///   bReaderHasPathHashIndex             u32 1
///   PathHashIndexOffset / Size / Hash   i64 106, i64 8, 20 bytes
///   bReaderHasFullDirectoryIndex        u32 1
///   FullDirectoryIndexOffset/Size/Hash  i64 114, i64 4, 20 bytes
///   EncodedPakEntries                   TArray<u8>, count 0
///   FilesNum                            i32 0
/// path hash index (8 bytes): empty TMap, empty pruned directory index
/// full directory index (4 bytes): empty TMap
/// FPakInfo footer (221 bytes)
///   EncryptionKeyGuid 16 zero bytes, bEncryptedIndex 0, Magic, Version 11,
///   IndexOffset 0, IndexSize 106, IndexHash, 5 x 32-byte compression names
/// ```
pub fn write_stub(path_hash_seed: u64) -> Vec<u8> {
    let path_hash_index = [0u8; 8];
    let full_directory_index = [0u8; 4];

    let mut index = Vec::with_capacity(STUB_INDEX_SIZE as usize);
    push_i32(&mut index, 2);
    index.extend_from_slice(&[b'/', 0]);
    push_i32(&mut index, 0);
    push_u64(&mut index, path_hash_seed);
    // The two secondary indexes follow the primary one directly.
    push_i32(&mut index, 1);
    push_u64(&mut index, STUB_INDEX_SIZE);
    push_u64(&mut index, path_hash_index.len() as u64);
    index.extend_from_slice(&sha1_of(&path_hash_index));
    push_i32(&mut index, 1);
    push_u64(&mut index, STUB_INDEX_SIZE + path_hash_index.len() as u64);
    push_u64(&mut index, full_directory_index.len() as u64);
    index.extend_from_slice(&sha1_of(&full_directory_index));
    push_i32(&mut index, 0);
    push_i32(&mut index, 0);
    debug_assert_eq!(index.len() as u64, STUB_INDEX_SIZE);

    let mut out = index.clone();
    out.extend_from_slice(&path_hash_index);
    out.extend_from_slice(&full_directory_index);

    // FPakInfo.
    out.extend_from_slice(&[0u8; 16]);
    out.push(0);
    out.extend_from_slice(&PAK_MAGIC.to_le_bytes());
    out.extend_from_slice(&PAK_VERSION.to_le_bytes());
    push_u64(&mut out, 0);
    push_u64(&mut out, STUB_INDEX_SIZE);
    out.extend_from_slice(&sha1_of(&index));
    out.extend_from_slice(&[0u8; 32 * MAX_METHODS]);
    out
}

/// The stub for a container, seeded from its name so a rebuild reproduces the
/// same bytes. The shipped stubs carry 32-bit seeds; this does too.
pub fn stub_for(container_name: &str) -> Vec<u8> {
    let hash = blake3::hash(container_name.as_bytes());
    let seed = u32::from_le_bytes(hash.as_bytes()[..4].try_into().unwrap());
    write_stub(seed as u64)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Build one `EncodedPakEntries` record.
    fn encoded(flags: u32, fields: &[u32]) -> Vec<u8> {
        let mut v = flags.to_le_bytes().to_vec();
        for f in fields {
            v.extend_from_slice(&f.to_le_bytes());
        }
        v
    }

    const OFFSET_32: u32 = 1 << 31;
    const UNCOMPRESSED_32: u32 = 1 << 30;
    const SIZE_32: u32 = 1 << 29;

    #[test]
    fn stored_entry_reuses_the_uncompressed_size() {
        // No compression method, no blocks: size mirrors uncompressed size and
        // no separate size field is present in the record.
        let buf = encoded(OFFSET_32 | UNCOMPRESSED_32, &[1024, 4096]);
        let e = decode_entry(&buf, 0, 11).unwrap();
        assert_eq!(e.offset, 1024);
        assert_eq!(e.uncompressed_size, 4096);
        assert_eq!(e.size, 4096);
        assert_eq!(e.method_index, 0);
        assert!(e.blocks.is_empty());
        // A stored payload sits right after the short (block-less) header.
        assert_eq!(e.header_size(), 53);
    }

    #[test]
    fn wide_fields_are_read_as_64_bit() {
        let mut v = 0u32.to_le_bytes().to_vec();
        v.extend_from_slice(&(1u64 << 33).to_le_bytes());
        v.extend_from_slice(&(1u64 << 32).to_le_bytes());
        let e = decode_entry(&v, 0, 11).unwrap();
        assert_eq!(e.offset, 1 << 33);
        assert_eq!(e.uncompressed_size, 1 << 32);
    }

    #[test]
    fn a_lone_block_is_derived_from_the_header_and_size() {
        // One Oodle block, unencrypted: the extent is implied, not stored.
        let flags = OFFSET_32 | UNCOMPRESSED_32 | SIZE_32 | (1 << 23) | (1 << 6);
        let buf = encoded(flags, &[4096, 200_000, 90_000]);
        let e = decode_entry(&buf, 0, 11).unwrap();
        assert_eq!(e.method_index, 1);
        assert_eq!(e.size, 90_000);
        // Offsets are entry-relative from v9, so the block starts at the header.
        let head = header_size(1, 1);
        assert_eq!(e.blocks, vec![(head, head + 90_000)]);
    }

    #[test]
    fn multi_block_extents_accumulate_from_stored_lengths() {
        let flags = OFFSET_32 | UNCOMPRESSED_32 | SIZE_32 | (1 << 23) | (3 << 6) | 32;
        let buf = encoded(flags, &[0, 200_000, 90_000, 40_000, 30_000, 20_000]);
        let e = decode_entry(&buf, 0, 11).unwrap();
        let head = header_size(1, 3);
        assert_eq!(
            e.blocks,
            vec![
                (head, head + 40_000),
                (head + 40_000, head + 70_000),
                (head + 70_000, head + 90_000),
            ]
        );
        // Bits 0-5 carry the block size in 2 KiB units.
        assert_eq!(e.block_size, 32 << 11);
    }

    #[test]
    fn a_payload_under_one_block_reports_its_own_size() {
        let flags = OFFSET_32 | UNCOMPRESSED_32 | SIZE_32 | (1 << 23) | (1 << 6) | 32;
        let buf = encoded(flags, &[0, 40_000, 10_000]);
        let e = decode_entry(&buf, 0, 11).unwrap();
        assert_eq!(e.block_size, 40_000);
    }

    #[test]
    fn absolute_offsets_are_used_before_version_nine() {
        let flags = OFFSET_32 | UNCOMPRESSED_32 | SIZE_32 | (1 << 23) | (1 << 6);
        let buf = encoded(flags, &[4096, 200_000, 90_000]);
        let e = decode_entry(&buf, 0, 8).unwrap();
        assert_eq!(e.blocks[0].0, 4096 + header_size(1, 1));
    }

    #[test]
    fn encrypted_blocks_pad_to_the_aes_block_size() {
        let flags =
            OFFSET_32 | UNCOMPRESSED_32 | SIZE_32 | (1 << 23) | (1 << 22) | (2 << 6) | 32;
        let buf = encoded(flags, &[0, 200_000, 90_000, 100, 200]);
        let e = decode_entry(&buf, 0, 11).unwrap();
        assert!(e.encrypted);
        let head = header_size(1, 2);
        // 100 rounds up to 112 before the next block starts.
        assert_eq!(e.blocks, vec![(head, head + 100), (head + 112, head + 312)]);
    }

    #[test]
    fn a_truncated_record_is_an_error_not_a_panic() {
        let buf = encoded(0, &[1]);
        assert!(decode_entry(&buf, 0, 11).is_err());
        assert!(decode_entry(&buf, 999, 11).is_err());
    }

    #[test]
    fn the_stub_has_the_shipped_shape() {
        let stub = write_stub(0xcc13_a9dd);
        assert_eq!(stub.len(), 339);
        assert_eq!(&stub[..6], &[2, 0, 0, 0, b'/', 0]);
        assert_eq!(&stub[10..18], &0xcc13_a9ddu64.to_le_bytes());
        assert_eq!(
            u32::from_le_bytes(stub[0x87..0x8b].try_into().unwrap()),
            PAK_MAGIC
        );
        assert_eq!(
            u32::from_le_bytes(stub[0x8b..0x8f].try_into().unwrap()),
            PAK_VERSION
        );
        assert_eq!(
            u64::from_le_bytes(stub[0x97..0x9f].try_into().unwrap()),
            106
        );
        // SHA-1 of eight and of four zero bytes, as the shipped stubs carry.
        assert_eq!(
            stub[0x26..0x3a].to_vec(),
            hex("05fe405753166f125559e7c9ac558654f107c7e9")
        );
        assert_eq!(
            stub[0x4e..0x62].to_vec(),
            hex("9069ca78e7450a285173431b3e52c5c25299e473")
        );
        // Only the seed and the footer hash vary between stubs.
        let other = write_stub(1);
        let differ: Vec<usize> = (0..339).filter(|&i| stub[i] != other[i]).collect();
        assert!(!differ.is_empty());
        assert!(differ
            .iter()
            .all(|&i| (10..14).contains(&i) || (159..179).contains(&i)));
    }

    #[test]
    fn the_stub_reads_back_as_an_empty_archive() {
        let dir = std::env::temp_dir().join(format!("mjolnir-stub-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("stub.pak");
        std::fs::write(&path, stub_for("pakchunk999-test_P")).unwrap();
        let pak = load_pak(&path).unwrap();
        assert_eq!(pak.mount_point, "/");
        assert!(pak.files.is_empty());
        assert_eq!(pak.version, PAK_VERSION);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn stubs_are_stable_per_name_and_distinct_across_names() {
        assert_eq!(stub_for("a_P"), stub_for("a_P"));
        assert_ne!(stub_for("a_P"), stub_for("b_P"));
    }

    /// Against the real thing, when an installation is at hand: the shipped
    /// stub's own seed must reproduce it byte for byte.
    #[test]
    fn matches_a_shipped_stub_when_available() {
        let Ok(paks) = std::env::var("HCE_PAKS") else {
            return;
        };
        let path = Path::new(&paks).join("pakchunk115-Windows.pak");
        let Ok(shipped) = std::fs::read(&path) else {
            return;
        };
        let seed = u64::from_le_bytes(shipped[10..18].try_into().unwrap());
        assert_eq!(write_stub(seed), shipped);
    }

    fn hex(s: &str) -> Vec<u8> {
        (0..s.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap())
            .collect()
    }
}
