//! Cooked (zen) package structure: summary, name map, import and export maps,
//! and the byte range each export's serialized data occupies.
//!
//! Field offsets follow `FZenPackageSummary` as shipped by this game (UE 5.5,
//! no versioning block), the same layout `tools/iostore/zen_class.py` reads.
//! An export's data sits at `header_size + cooked_serial_offset` within the
//! package chunk: this cook's serial offsets are relative to the start of the
//! export data, verified by the first-serialized export sitting at offset 0
//! and exports tiling the chunk contiguously from there.

use std::collections::HashMap;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("package data ends early at {0:#x}")]
    Eof(usize),
    #[error("package name batch is malformed")]
    Names,
    #[error("export {index} spans {start:#x}..{end:#x}, outside the package of {len:#x} bytes")]
    ExportRange {
        index: usize,
        start: usize,
        end: usize,
        len: usize,
    },
}

/// A `FPackageObjectIndex`: a 62-bit id tagged with what it refers to.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ObjectIndex(pub u64);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ObjectRef {
    /// Index into this package's export map.
    Export(usize),
    /// A `/Script/...` object, resolvable through [`ScriptObjects`].
    Script(u64),
    /// An object in another package, through the import map.
    PackageImport(u64),
    Null,
}

impl ObjectIndex {
    pub const NULL: u64 = u64::MAX;

    pub fn classify(self) -> ObjectRef {
        if self.0 == Self::NULL {
            return ObjectRef::Null;
        }
        match self.0 >> 62 {
            0 => ObjectRef::Export((self.0 & ((1 << 62) - 1)) as usize),
            1 => ObjectRef::Script(self.0),
            2 => ObjectRef::PackageImport(self.0),
            _ => ObjectRef::Null,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Export {
    pub name: String,
    pub outer: ObjectIndex,
    pub class: ObjectIndex,
    pub super_: ObjectIndex,
    pub template: ObjectIndex,
    pub public_hash: u64,
    /// Offset in the original cooked layout; see the module docs for how it
    /// maps into the chunk.
    pub cooked_serial_offset: u64,
    pub serial_size: u64,
}

#[derive(Debug)]
pub struct Package {
    pub name: String,
    pub header_size: u32,
    pub cooked_header_size: u32,
    pub names: Vec<String>,
    pub imports: Vec<ObjectIndex>,
    pub exports: Vec<Export>,
    pub imported_package_names: Vec<String>,
}

impl Package {
    pub fn parse(data: &[u8]) -> Result<Package, Error> {
        let u32_at = |at: usize| -> Result<u32, Error> {
            data.get(at..at + 4)
                .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
                .ok_or(Error::Eof(at))
        };
        let u64_at = |at: usize| -> Result<u64, Error> {
            data.get(at..at + 8)
                .map(|b| u64::from_le_bytes(b.try_into().unwrap()))
                .ok_or(Error::Eof(at))
        };

        let header_size = u32_at(4)?;
        let name_index = u32_at(8)?;
        let name_number = u32_at(12)?;
        let cooked_header_size = u32_at(20)?;
        let import_map_off = u32_at(28)? as usize;
        let export_map_off = u32_at(32)? as usize;
        let export_bundle_off = u32_at(36)? as usize;
        let imported_pkg_names_off = u32_at(48)? as usize;

        let names = load_name_batch(data, 52).ok_or(Error::Names)?;
        let mapped = |index: u32, number: u32| -> String {
            let name = names
                .get((index & ((1 << 30) - 1)) as usize)
                .cloned()
                .unwrap_or_default();
            if number != 0 {
                format!("{name}_{}", number - 1)
            } else {
                name
            }
        };
        let name = mapped(name_index, name_number);

        let mut imports = Vec::new();
        let mut at = import_map_off;
        while at + 8 <= export_map_off {
            imports.push(ObjectIndex(u64_at(at)?));
            at += 8;
        }

        const EXPORT_ENTRY: usize = 72;
        let mut exports = Vec::new();
        let mut at = export_map_off;
        while at + EXPORT_ENTRY <= export_bundle_off {
            exports.push(Export {
                cooked_serial_offset: u64_at(at)?,
                serial_size: u64_at(at + 8)?,
                name: mapped(u32_at(at + 16)?, u32_at(at + 20)?),
                outer: ObjectIndex(u64_at(at + 24)?),
                class: ObjectIndex(u64_at(at + 32)?),
                super_: ObjectIndex(u64_at(at + 40)?),
                template: ObjectIndex(u64_at(at + 48)?),
                public_hash: u64_at(at + 56)?,
            });
            at += EXPORT_ENTRY;
        }

        let imported_package_names = if imported_pkg_names_off > 0
            && imported_pkg_names_off < header_size as usize
        {
            load_name_batch(data, imported_pkg_names_off).unwrap_or_default()
        } else {
            Vec::new()
        };

        Ok(Package {
            name,
            header_size,
            cooked_header_size,
            names,
            imports,
            exports,
            imported_package_names,
        })
    }

    /// The serialized bytes of one export within the package chunk.
    pub fn export_data<'a>(&self, data: &'a [u8], index: usize) -> Result<&'a [u8], Error> {
        let e = &self.exports[index];
        let start = self.header_size as usize + e.cooked_serial_offset as usize;
        let end = start + e.serial_size as usize;
        data.get(start..end).ok_or(Error::ExportRange {
            index,
            start,
            end,
            len: data.len(),
        })
    }
}

/// The global container's `/Script/...` object table: `FPackageObjectIndex`
/// to path, e.g. `/Script/Engine/StaticMesh`.
#[derive(Debug, Default)]
pub struct ScriptObjects {
    pub paths: HashMap<u64, String>,
}

impl ScriptObjects {
    /// Parse the `ScriptObjects` chunk of `global.utoc`.
    pub fn parse(data: &[u8]) -> Result<ScriptObjects, Error> {
        let (names, mut pos) = load_name_batch_at(data, 0).ok_or(Error::Names)?;
        let count = data
            .get(pos..pos + 4)
            .map(|b| i32::from_le_bytes(b.try_into().unwrap()))
            .ok_or(Error::Eof(pos))? as usize;
        pos += 4;

        struct Raw {
            name: String,
            outer: u64,
        }
        let mut raw: HashMap<u64, Raw> = HashMap::with_capacity(count);
        for _ in 0..count {
            let bytes = data.get(pos..pos + 32).ok_or(Error::Eof(pos))?;
            let name_index = u32::from_le_bytes(bytes[0..4].try_into().unwrap());
            let name_number = u32::from_le_bytes(bytes[4..8].try_into().unwrap());
            let global = u64::from_le_bytes(bytes[8..16].try_into().unwrap());
            let outer = u64::from_le_bytes(bytes[16..24].try_into().unwrap());
            pos += 32;
            let base = names
                .get((name_index & ((1 << 30) - 1)) as usize)
                .cloned()
                .unwrap_or_default();
            let name = if name_number != 0 {
                format!("{base}_{}", name_number - 1)
            } else {
                base
            };
            raw.insert(global, Raw { name, outer });
        }

        let mut paths: HashMap<u64, String> = HashMap::with_capacity(raw.len());
        // Recursive resolution with memoisation; outer chains are short.
        fn path_of(
            index: u64,
            raw: &HashMap<u64, Raw>,
            memo: &mut HashMap<u64, String>,
            depth: u32,
        ) -> String {
            if index == ObjectIndex::NULL || depth > 16 {
                return String::new();
            }
            if let Some(done) = memo.get(&index) {
                return done.clone();
            }
            let Some(entry) = raw.get(&index) else {
                return String::new();
            };
            let parent = path_of(entry.outer, raw, memo, depth + 1);
            let path = if parent.is_empty() {
                entry.name.clone()
            } else {
                format!("{parent}/{}", entry.name)
            };
            memo.insert(index, path.clone());
            path
        }
        let keys: Vec<u64> = raw.keys().copied().collect();
        for k in keys {
            let p = path_of(k, &raw, &mut paths, 0);
            paths.insert(k, p);
        }
        Ok(ScriptObjects { paths })
    }

    /// The leaf name of a script object, e.g. `StaticMesh`.
    pub fn leaf(&self, index: ObjectIndex) -> Option<&str> {
        self.paths
            .get(&index.0)
            .map(|p| p.rsplit('/').next().unwrap_or(p))
    }
}

/// Parse an Unreal name batch at `pos`: count, byte size, hash version,
/// hashes, 2-byte headers, then string data.
pub fn load_name_batch(buf: &[u8], pos: usize) -> Option<Vec<String>> {
    load_name_batch_at(buf, pos).map(|(names, _)| names)
}

fn load_name_batch_at(buf: &[u8], mut pos: usize) -> Option<(Vec<String>, usize)> {
    let count = i32::from_le_bytes(buf.get(pos..pos + 4)?.try_into().ok()?) as usize;
    // An empty batch is the count alone: the shipped tag wrappers' imported
    // package names end at `header_size` four bytes after a zero count.
    if count == 0 {
        return Some((Vec::new(), pos + 4));
    }
    pos += 8;
    if count > 1_000_000 {
        return None;
    }
    pos += 8 + 8 * count;
    let mut headers = Vec::with_capacity(count);
    for _ in 0..count {
        let b0 = *buf.get(pos)?;
        let b1 = *buf.get(pos + 1)?;
        headers.push((b0 & 0x80 != 0, (((b0 & 0x7F) as usize) << 8) | b1 as usize));
        pos += 2;
    }
    let mut names = Vec::with_capacity(count);
    for (utf16, len) in headers {
        if utf16 {
            let raw = buf.get(pos..pos + len * 2)?;
            let units: Vec<u16> = raw
                .chunks_exact(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .collect();
            names.push(String::from_utf16_lossy(&units));
            pos += len * 2;
        } else {
            names.push(String::from_utf8_lossy(buf.get(pos..pos + len)?).into_owned());
            pos += len;
        }
    }
    Some((names, pos))
}
