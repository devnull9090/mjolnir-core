//! Read-only Unreal Engine 5 IoStore (`.utoc` / `.ucas`) container reader.
//!
//! A Rust port of `tools/iostore/iostore.py`. Scope is deliberately narrow:
//! enumerate a container's directory index and read individual chunks back into
//! memory. It is not a bulk asset ripper and never writes game content to disk.
//!
//! Format reference: UE 5.5 `IoStore.cpp` / `IoDirectoryIndex.h`.

use std::collections::HashMap;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

pub mod oodle;
pub mod pack;
pub mod toc;

pub const TOC_MAGIC: &[u8; 16] = b"-==--==--==--==-";

// EIoStoreTocVersion
pub const VER_DIRECTORY_INDEX: u8 = 2;
pub const VER_PERFECT_HASH: u8 = 4;
pub const VER_PERFECT_HASH_WITH_OVERFLOW: u8 = 5;
pub const VER_REPLACE_CHUNK_HASH_WITH_IO_HASH: u8 = 8;

// EIoContainerFlags
pub const FLAG_COMPRESSED: u8 = 1 << 0;
pub const FLAG_ENCRYPTED: u8 = 1 << 1;
pub const FLAG_SIGNED: u8 = 1 << 2;
pub const FLAG_INDEXED: u8 = 1 << 3;
pub const FLAG_ON_DEMAND: u8 = 1 << 4;

const NONE_INDEX: u32 = 0xFFFF_FFFF;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("not an IoStore TOC (bad magic)")]
    BadMagic,
    #[error("TOC version {0} predates the directory index")]
    VersionTooOld(u8),
    #[error("directory index is encrypted; no key supplied")]
    Encrypted,
    #[error("unexpected end of buffer (wanted {wanted}, have {have})")]
    Truncated { wanted: usize, have: usize },
    #[error("unsupported compression method {0:?}")]
    UnsupportedCompression(String),
    #[error("Oodle decode failed: {0}")]
    OodlePure(String),
    #[error("Oodle decompress returned {got}, expected {want}")]
    OodleDecompress { got: i64, want: usize },
    #[error("zlib decompress failed: {0}")]
    Zlib(String),
}

pub fn chunk_type_name(v: u8) -> &'static str {
    match v {
        0 => "Invalid",
        1 => "ExportBundleData",
        2 => "BulkData",
        3 => "OptionalBulkData",
        4 => "MemoryMappedBulkData",
        5 => "ScriptObjects",
        6 => "ContainerHeader",
        7 => "ExternalFile",
        8 => "ShaderCodeLibrary",
        9 => "ShaderCode",
        10 => "PackageStoreEntry",
        11 => "DerivedData",
        12 => "EditorDerivedData",
        13 => "PackageResource",
        _ => "Unknown",
    }
}

#[derive(Debug, Clone, Copy)]
pub struct ChunkEntry {
    pub index: usize,
    pub chunk_id: u64,
    pub chunk_index: u16,
    pub chunk_type: u8,
    pub offset: u64,
    pub length: u64,
}

impl ChunkEntry {
    pub fn type_name(&self) -> &'static str {
        chunk_type_name(self.chunk_type)
    }
}

#[derive(Debug, Clone, Copy)]
pub struct CompressedBlock {
    pub offset: u64,
    pub compressed_size: u32,
    pub uncompressed_size: u32,
    pub method_index: u8,
}

#[derive(Debug)]
pub struct Container {
    pub utoc_path: PathBuf,
    pub version: u8,
    pub container_id: u64,
    pub flags: u8,
    pub compression_block_size: u64,
    pub partition_size: u64,
    pub partition_count: u32,
    pub compression_methods: Vec<String>,
    pub chunks: Vec<ChunkEntry>,
    pub blocks: Vec<CompressedBlock>,
    pub mount_point: String,
    /// Directory-index path (relative to `mount_point`) to chunk index.
    pub files: HashMap<String, usize>,
}

impl Container {
    pub fn indexed(&self) -> bool {
        self.flags & FLAG_INDEXED != 0
    }
    pub fn encrypted(&self) -> bool {
        self.flags & FLAG_ENCRYPTED != 0
    }
    /// Full path including the container's mount point.
    pub fn full_path(&self, rel: &str) -> String {
        if self.mount_point.is_empty() {
            rel.to_string()
        } else {
            format!("{}{}", self.mount_point, rel)
        }
    }
}

// ---------------------------------------------------------------- byte reader

struct Reader<'a> {
    buf: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    fn new(buf: &'a [u8]) -> Self {
        Self { buf, pos: 0 }
    }

    fn take(&mut self, n: usize) -> Result<&'a [u8], Error> {
        let end = self.pos.checked_add(n).ok_or(Error::Truncated {
            wanted: n,
            have: self.buf.len().saturating_sub(self.pos),
        })?;
        if end > self.buf.len() {
            return Err(Error::Truncated {
                wanted: n,
                have: self.buf.len() - self.pos,
            });
        }
        let out = &self.buf[self.pos..end];
        self.pos = end;
        Ok(out)
    }

    fn i32(&mut self) -> Result<i32, Error> {
        Ok(i32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }

    /// Unreal `FString`: negative length means UTF-16, positive means UTF-8.
    fn fstring(&mut self) -> Result<String, Error> {
        let len = self.i32()?;
        if len == 0 {
            return Ok(String::new());
        }
        if len < 0 {
            let raw = self.take((-len as usize) * 2)?;
            let units: Vec<u16> = raw
                .chunks_exact(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .collect();
            Ok(String::from_utf16_lossy(&units)
                .trim_end_matches('\0')
                .to_string())
        } else {
            let raw = self.take(len as usize)?;
            Ok(String::from_utf8_lossy(raw)
                .trim_end_matches('\0')
                .to_string())
        }
    }
}

fn u64_le(b: &[u8]) -> u64 {
    let mut v = 0u64;
    for (i, byte) in b.iter().enumerate() {
        v |= (*byte as u64) << (8 * i);
    }
    v
}

fn u64_be(b: &[u8]) -> u64 {
    let mut v = 0u64;
    for byte in b {
        v = (v << 8) | *byte as u64;
    }
    v
}

// -------------------------------------------------------------- header + load

struct TocHeader {
    version: u8,
    header_size: usize,
    entry_count: usize,
    block_count: usize,
    block_entry_size: usize,
    method_count: usize,
    method_length: usize,
    block_size: u64,
    dir_index_size: usize,
    partition_count: u32,
    container_id: u64,
    flags: u8,
    perfect_hash_seed_count: usize,
    partition_size: u64,
    chunks_without_perfect_hash: usize,
}

fn read_header(blob: &[u8]) -> Result<TocHeader, Error> {
    if blob.len() < 100 || &blob[..16] != TOC_MAGIC {
        return Err(Error::BadMagic);
    }
    let u32_at = |off: usize| u32::from_le_bytes(blob[off..off + 4].try_into().unwrap());
    let u64_at = |off: usize| u64::from_le_bytes(blob[off..off + 8].try_into().unwrap());

    Ok(TocHeader {
        version: blob[16],
        header_size: u32_at(20) as usize,
        entry_count: u32_at(24) as usize,
        block_count: u32_at(28) as usize,
        block_entry_size: u32_at(32) as usize,
        method_count: u32_at(36) as usize,
        method_length: u32_at(40) as usize,
        block_size: u32_at(44) as u64,
        dir_index_size: u32_at(48) as usize,
        partition_count: u32_at(52),
        container_id: u64_at(56),
        flags: blob[80],
        perfect_hash_seed_count: u32_at(84) as usize,
        partition_size: u64_at(88),
        chunks_without_perfect_hash: u32_at(96) as usize,
    })
}

fn parse_directory_index(blob: &[u8]) -> Result<(String, HashMap<String, usize>), Error> {
    let mut r = Reader::new(blob);
    let mount_point = r.fstring()?;

    let dir_count = r.i32()? as usize;
    let mut dirs = Vec::with_capacity(dir_count);
    for _ in 0..dir_count {
        let raw = r.take(16)?;
        dirs.push((
            u32::from_le_bytes(raw[0..4].try_into().unwrap()),
            u32::from_le_bytes(raw[4..8].try_into().unwrap()),
            u32::from_le_bytes(raw[8..12].try_into().unwrap()),
            u32::from_le_bytes(raw[12..16].try_into().unwrap()),
        ));
    }

    let file_count = r.i32()? as usize;
    let mut files = Vec::with_capacity(file_count);
    for _ in 0..file_count {
        let raw = r.take(12)?;
        files.push((
            u32::from_le_bytes(raw[0..4].try_into().unwrap()),
            u32::from_le_bytes(raw[4..8].try_into().unwrap()),
            u32::from_le_bytes(raw[8..12].try_into().unwrap()),
        ));
    }

    let string_count = r.i32()? as usize;
    let mut strings = Vec::with_capacity(string_count);
    for _ in 0..string_count {
        strings.push(r.fstring()?);
    }

    let mut result = HashMap::new();
    if dirs.is_empty() {
        return Ok((mount_point, result));
    }

    // Iterative walk of the sibling/child tree, mirroring the Python reader.
    let mut stack: Vec<(u32, String)> = vec![(0, String::new())];
    while let Some((dir_index, prefix)) = stack.pop() {
        let (name_idx, first_child, next_sibling, first_file) = dirs[dir_index as usize];
        let path = if name_idx != NONE_INDEX {
            format!("{}{}/", prefix, strings[name_idx as usize])
        } else {
            prefix.clone()
        };

        let mut file_index = first_file;
        while file_index != NONE_INDEX {
            let (f_name, f_next, f_user) = files[file_index as usize];
            if f_name != NONE_INDEX {
                result.insert(
                    format!("{}{}", path, strings[f_name as usize]),
                    f_user as usize,
                );
            }
            file_index = f_next;
        }

        if next_sibling != NONE_INDEX {
            stack.push((next_sibling, prefix));
        }
        if first_child != NONE_INDEX {
            stack.push((first_child, path));
        }
    }

    Ok((mount_point, result))
}

/// Parse a `.utoc` container index.
pub fn load_container(utoc_path: impl AsRef<Path>) -> Result<Container, Error> {
    let utoc_path = utoc_path.as_ref().to_path_buf();
    let blob = std::fs::read(&utoc_path)?;
    let h = read_header(&blob)?;

    if h.version < VER_DIRECTORY_INDEX {
        return Err(Error::VersionTooOld(h.version));
    }

    let mut pos = h.header_size;

    let chunk_ids = &blob[pos..pos + 12 * h.entry_count];
    pos += 12 * h.entry_count;

    let offsets = &blob[pos..pos + 10 * h.entry_count];
    pos += 10 * h.entry_count;

    if h.version >= VER_PERFECT_HASH {
        pos += 4 * h.perfect_hash_seed_count;
    }
    if h.version >= VER_PERFECT_HASH_WITH_OVERFLOW {
        pos += 4 * h.chunks_without_perfect_hash;
    }

    let mut blocks = Vec::with_capacity(h.block_count);
    for i in 0..h.block_count {
        let raw = &blob[pos + i * h.block_entry_size..pos + i * h.block_entry_size + 12];
        blocks.push(CompressedBlock {
            offset: u64_le(&raw[0..5]),
            compressed_size: u64_le(&raw[5..8]) as u32,
            uncompressed_size: u64_le(&raw[8..11]) as u32,
            method_index: raw[11],
        });
    }
    pos += h.block_entry_size * h.block_count;

    let mut methods = vec!["None".to_string()];
    for i in 0..h.method_count {
        let raw = &blob[pos + i * h.method_length..pos + (i + 1) * h.method_length];
        let end = raw.iter().position(|b| *b == 0).unwrap_or(raw.len());
        methods.push(String::from_utf8_lossy(&raw[..end]).to_string());
    }
    pos += h.method_length * h.method_count;

    if h.flags & FLAG_SIGNED != 0 {
        let hash_size = i32::from_le_bytes(blob[pos..pos + 4].try_into().unwrap()) as usize;
        pos += 4 + hash_size * 2 + hash_size * h.block_count;
    }

    let mut mount_point = String::new();
    let mut files = HashMap::new();
    if h.dir_index_size > 0 && h.flags & FLAG_INDEXED != 0 {
        if h.flags & FLAG_ENCRYPTED != 0 {
            return Err(Error::Encrypted);
        }
        let (mp, f) = parse_directory_index(&blob[pos..pos + h.dir_index_size])?;
        mount_point = mp;
        files = f;
    }

    let mut chunks = Vec::with_capacity(h.entry_count);
    for i in 0..h.entry_count {
        let cid = &chunk_ids[i * 12..(i + 1) * 12];
        let raw = &offsets[i * 10..(i + 1) * 10];
        chunks.push(ChunkEntry {
            index: i,
            chunk_id: u64::from_le_bytes(cid[0..8].try_into().unwrap()),
            chunk_index: u16::from_be_bytes(cid[8..10].try_into().unwrap()),
            chunk_type: cid[11],
            offset: u64_be(&raw[0..5]),
            length: u64_be(&raw[5..10]),
        });
    }

    Ok(Container {
        utoc_path,
        version: h.version,
        container_id: h.container_id,
        flags: h.flags,
        compression_block_size: h.block_size,
        partition_size: h.partition_size,
        partition_count: h.partition_count,
        compression_methods: methods,
        chunks,
        blocks,
        mount_point,
        files,
    })
}

fn decompress(
    method: &str,
    src: &[u8],
    out_size: usize,
    oodle_roots: &[PathBuf],
) -> Result<Vec<u8>, Error> {
    match method.to_ascii_lowercase().as_str() {
        "none" | "" => Ok(src[..out_size.min(src.len())].to_vec()),
        "zlib" => {
            use flate2::read::ZlibDecoder;
            let mut out = Vec::with_capacity(out_size);
            ZlibDecoder::new(src)
                .read_to_end(&mut out)
                .map_err(|e| Error::Zlib(e.to_string()))?;
            Ok(out)
        }
        "oodle" => oodle::decompress(src, out_size, oodle_roots),
        other => Err(Error::UnsupportedCompression(other.to_string())),
    }
}

/// Read one chunk back into memory, decompressing only the blocks needed.
///
/// `max_bytes` caps the read so header inspection does not pay for a full
/// multi-megabyte payload.
pub fn read_chunk(
    container: &Container,
    chunk: &ChunkEntry,
    max_bytes: Option<usize>,
    oodle_roots: &[PathBuf],
) -> Result<Vec<u8>, Error> {
    let block_size = container.compression_block_size;
    let first = (chunk.offset / block_size) as usize;
    let wanted = match max_bytes {
        Some(m) => (chunk.length as usize).min(m),
        None => chunk.length as usize,
    };
    if wanted == 0 {
        return Ok(Vec::new());
    }
    let last = ((chunk.offset + wanted as u64 - 1) / block_size) as usize;

    let base = container.utoc_path.with_extension("");
    let mut handles: HashMap<u64, File> = HashMap::new();
    let mut out: Vec<u8> = Vec::with_capacity(wanted + block_size as usize);

    for i in first..=last {
        let block = &container.blocks[i];
        let (partition, local_offset) = if container.partition_size > 0 {
            (
                block.offset / container.partition_size,
                block.offset % container.partition_size,
            )
        } else {
            (0, block.offset)
        };

        if !handles.contains_key(&partition) {
            let name = if partition == 0 {
                format!("{}.ucas", base.display())
            } else {
                format!("{}_s{}.ucas", base.display(), partition)
            };
            handles.insert(partition, File::open(name)?);
        }
        let fh = handles.get_mut(&partition).unwrap();
        fh.seek(SeekFrom::Start(local_offset))?;

        // Blocks are stored 16-byte aligned; read the padded size then trim.
        let aligned = ((block.compressed_size + 15) & !15) as usize;
        let mut raw = vec![0u8; aligned];
        fh.read_exact(&mut raw)?;
        raw.truncate(block.compressed_size as usize);

        let method = &container.compression_methods[block.method_index as usize];
        out.extend_from_slice(&decompress(
            method,
            &raw,
            block.uncompressed_size as usize,
            oodle_roots,
        )?);
    }

    let start = (chunk.offset - first as u64 * block_size) as usize;
    let end = (start + wanted).min(out.len());
    Ok(out[start..end].to_vec())
}

/// Load every `.utoc` in a directory, skipping containers that fail to parse.
pub fn load_all(paks_dir: impl AsRef<Path>) -> Result<Vec<Container>, Error> {
    let mut paths: Vec<PathBuf> = std::fs::read_dir(paks_dir)?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("utoc"))
        .collect();
    paths.sort();
    Ok(paths.iter().filter_map(|p| load_container(p).ok()).collect())
}
