//! One MCC Halo 2 cache file, decompressed, with its tag index, tag names and
//! string ids.
//!
//! MCC stores a Halo 2 map as its 0x380-byte header followed by zlib chunks,
//! each inflating to at most 0x40000 bytes, with the chunk table (u32
//! compressed size, u32 file offset per chunk) at the offset the header gives
//! at 0x310 and the chunk count at 0x314. The decompressed image is the header
//! and the chunks back to back, as long as the header's size field at 0x08 says;
//! every offset the header and the tags record is an offset into that image.
//!
//! Tag data sits at the end of the image, behind the tag index: an address `a`
//! is at image offset `a - base + index_offset`, where `base` is the header's
//! virtual base at 0x2D0 (0x3200000 for a scenario map, 0 for `shared.map`
//! and `mainmenu.map`). A scenario map holds only its own tags; an index entry
//! whose address is 0 or -1 lives in `shared.map` (weapons, vehicles, the
//! multiplayer item collections' targets) and is found there by name, never by
//! address: `mainmenu.map` also starts at 0 and the two ranges overlap.
//! Header offsets verified on lockout.map, coagulation.map, shared.map and
//! mainmenu.map (2026-10-21); see docs/h2_cache_format.md.

use std::collections::HashMap;
use std::io::Read;
use std::path::{Path, PathBuf};

use crate::Error;

pub(crate) fn u16_at(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes([b[o], b[o + 1]])
}
pub(crate) fn i16_at(b: &[u8], o: usize) -> i16 {
    i16::from_le_bytes([b[o], b[o + 1]])
}
pub(crate) fn u32_at(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
pub(crate) fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

/// A tag group four-character code as the index stores it (little-endian
/// u32, so `b"psbs"` on disk is `sbsp`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Group(pub u32);

impl Group {
    pub const fn new(s: &[u8; 4]) -> Group {
        Group(u32::from_be_bytes(*s))
    }
    pub fn name(self) -> String {
        String::from_utf8_lossy(&self.0.to_be_bytes()).trim_end().to_string()
    }
}

/// One tag index entry.
#[derive(Debug, Clone)]
pub struct TagEntry {
    pub group: Group,
    pub datum: u32,
    /// The tag's address, or `None` when its data lives in another file.
    pub address: Option<u32>,
    pub size: u32,
    pub name: String,
}

/// The header fields a reader needs (offsets in the decompressed image).
#[derive(Debug, Clone)]
pub struct Header {
    pub file_size: u32,
    pub index_offset: u32,
    pub tag_buffer_size: u32,
    pub name_count: u32,
    pub names_offset: u32,
    pub name_index_offset: u32,
    pub string_count: u32,
    pub strings_offset: u32,
    pub string_index_offset: u32,
    pub name: String,
    pub scenario: String,
    pub virtual_base: u32,
    pub index_size: u32,
    pub meta_size: u32,
}

/// A decompressed MCC Halo 2 cache file.
pub struct CacheFile {
    pub path: PathBuf,
    pub data: Vec<u8>,
    pub header: Header,
    pub tags: Vec<TagEntry>,
    by_name: HashMap<(Group, String), usize>,
}

const HEADER_SIZE: usize = 0x380;

/// Inflate an MCC Halo 2 map into its image.
pub fn decompress(file: &[u8]) -> Result<Vec<u8>, Error> {
    if file.len() < HEADER_SIZE || &file[0..4] != b"daeh" {
        return Err(Error::Format("not a cache file".into()));
    }
    let size = u32_at(file, 0x08) as usize;
    if size <= file.len() {
        // Already a plain image (a map some tool saved decompressed).
        return Ok(file.to_vec());
    }
    let table = u32_at(file, 0x310) as usize;
    let count = u32_at(file, 0x314) as usize;
    if table + count * 8 > file.len() {
        return Err(Error::Format(format!("chunk table at {table:#x} ({count} chunks) is past the end of the file")));
    }
    // The header's size is trusted only as far as the chunks bear it out
    // (a chunk inflates to at most 0x40000 bytes).
    let mut image = Vec::with_capacity(size.min(HEADER_SIZE + count * 0x40000));
    image.extend_from_slice(&file[..HEADER_SIZE]);
    for i in 0..count {
        let len = u32_at(file, table + i * 8) as usize;
        let at = u32_at(file, table + i * 8 + 4) as usize;
        let chunk = file
            .get(at..at + len)
            .ok_or_else(|| Error::Format(format!("chunk {i} at {at:#x} runs past the end of the file")))?;
        flate2::read::ZlibDecoder::new(chunk)
            .read_to_end(&mut image)
            .map_err(|e| Error::Format(format!("chunk {i}: {e}")))?;
    }
    if image.len() != size {
        return Err(Error::Format(format!("decompressed {} bytes, the header says {size}", image.len())));
    }
    Ok(image)
}

fn cstr(b: &[u8], o: usize) -> String {
    let s = b.get(o.min(b.len())..).unwrap_or(&[]);
    let n = s.iter().position(|&c| c == 0).unwrap_or(s.len());
    String::from_utf8_lossy(&s[..n]).into_owned()
}

impl CacheFile {
    pub fn open(path: &Path) -> Result<CacheFile, Error> {
        let file = std::fs::read(path).map_err(|e| Error::Io(path.to_path_buf(), e))?;
        let data = decompress(&file)?;
        CacheFile::from_image(path.to_path_buf(), data)
    }

    pub fn from_image(path: PathBuf, data: Vec<u8>) -> Result<CacheFile, Error> {
        let d = &data;
        let header = Header {
            file_size: u32_at(d, 0x08),
            index_offset: u32_at(d, 0x10),
            tag_buffer_size: u32_at(d, 0x14),
            name_count: u32_at(d, 0x20),
            names_offset: u32_at(d, 0x24),
            name_index_offset: u32_at(d, 0x2C),
            string_count: u32_at(d, 0x30),
            strings_offset: u32_at(d, 0x34),
            string_index_offset: u32_at(d, 0x3C),
            name: cstr(d, 0xB0),
            scenario: cstr(d, 0xD0),
            virtual_base: u32_at(d, 0x2D0),
            index_size: u32_at(d, 0x2D4),
            meta_size: u32_at(d, 0x2D8),
        };
        let idx = header.index_offset as usize;
        if idx + 0x20 > d.len() || u32_at(d, idx + 0x1C) != u32::from_le_bytes(*b"sgat") {
            return Err(Error::Format(format!("no tag index ('tags') at {idx:#x}")));
        }
        let tags_at = idx + u32_at(d, idx + 8) as usize;
        let count = u32_at(d, idx + 0x18) as usize;
        if count.checked_mul(16).and_then(|n| n.checked_add(tags_at)).map_or(true, |end| end > d.len()) {
            return Err(Error::Format(format!("tag table at {tags_at:#x} ({count} tags) runs past the image")));
        }
        let names = header.name_index_offset as usize;
        let name_count = (header.name_count as usize).min(count);
        if name_count.checked_mul(4).and_then(|n| n.checked_add(names)).map_or(true, |end| end > d.len()) {
            return Err(Error::Format(format!("tag name table at {names:#x} runs past the image")));
        }
        let strings = header.string_index_offset as usize;
        if (header.string_count as usize).checked_mul(4).and_then(|n| n.checked_add(strings)).map_or(true, |end| end > d.len()) {
            return Err(Error::Format(format!("string id table at {strings:#x} runs past the image")));
        }
        let mut tags = Vec::with_capacity(count);
        let mut by_name = HashMap::new();
        for i in 0..count {
            let e = tags_at + i * 16;
            let group = Group(u32_at(d, e));
            let datum = u32_at(d, e + 4);
            let address = u32_at(d, e + 8);
            let size = u32_at(d, e + 12);
            let name = if i < name_count {
                let rel = u32_at(d, names + i * 4);
                if rel == u32::MAX {
                    String::new()
                } else {
                    cstr(d, header.names_offset as usize + rel as usize)
                }
            } else {
                String::new()
            };
            let address = (address != 0 && address != u32::MAX).then_some(address);
            if address.is_some() && !name.is_empty() {
                by_name.entry((group, name.clone())).or_insert(i);
            }
            tags.push(TagEntry { group, datum, address, size, name });
        }
        Ok(CacheFile { path, data, header, tags, by_name })
    }

    /// The image offset of an address in this file's tag data, if it is one.
    pub fn offset(&self, address: u32) -> Option<usize> {
        let h = &self.header;
        let start = h.virtual_base.checked_add(h.index_size)?;
        let end = start.checked_add(h.meta_size)?;
        (start..end)
            .contains(&address)
            .then(|| (address - h.virtual_base + h.index_offset) as usize)
    }

    /// The index entry a datum names (the low 16 bits are the index).
    pub fn entry(&self, datum: u32) -> Option<&TagEntry> {
        if datum == u32::MAX {
            return None;
        }
        self.tags.get((datum & 0xFFFF) as usize)
    }

    /// The index position of a tag whose data is in this file.
    pub fn find(&self, group: Group, name: &str) -> Option<usize> {
        self.by_name.get(&(group, name.to_string())).copied()
    }

    /// A string id's text. The low 24 bits index the string table (the top
    /// byte is the string's length).
    pub fn string(&self, id: u32) -> &str {
        let i = (id & 0xFF_FFFF) as usize;
        if id == 0 || i >= self.header.string_count as usize {
            return "";
        }
        let rel = u32_at(&self.data, self.header.string_index_offset as usize + i * 4) as usize;
        let at = (self.header.strings_offset as usize + rel).min(self.data.len());
        let s = &self.data[at..];
        let n = s.iter().position(|&c| c == 0).unwrap_or(s.len());
        std::str::from_utf8(&s[..n]).unwrap_or("")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    /// A two-chunk file inflates to header + chunks, as long as the header says.
    #[test]
    fn chunks_inflate_behind_the_header() {
        let body: Vec<u8> = (0..0x50000u32).map(|i| (i % 251) as u8).collect();
        let mut file = vec![0u8; HEADER_SIZE];
        file[0..4].copy_from_slice(b"daeh");
        let total = (HEADER_SIZE + body.len()) as u32;
        file[8..12].copy_from_slice(&total.to_le_bytes());
        let mut table = Vec::new();
        for part in body.chunks(0x40000) {
            let mut z = flate2::write::ZlibEncoder::new(Vec::new(), flate2::Compression::default());
            z.write_all(part).unwrap();
            let c = z.finish().unwrap();
            table.push((c.len() as u32, file.len() as u32));
            file.extend_from_slice(&c);
        }
        let at = file.len() as u32;
        for (len, off) in &table {
            file.extend_from_slice(&len.to_le_bytes());
            file.extend_from_slice(&off.to_le_bytes());
        }
        file[0x310..0x314].copy_from_slice(&at.to_le_bytes());
        file[0x314..0x318].copy_from_slice(&(table.len() as u32).to_le_bytes());
        assert!(file.len() < total as usize, "the test file must be compressed");
        let image = decompress(&file).unwrap();
        assert_eq!(&image[HEADER_SIZE..], &body[..]);
    }

    #[test]
    fn group_codes_read_as_the_index_stores_them() {
        assert_eq!(Group::new(b"sbsp").0, u32::from_le_bytes(*b"psbs"));
        assert_eq!(Group::new(b"sky ").name(), "sky");
    }
}
