//! The whole cooked (zen) package header, read and **written**.
//!
//! [`crate::zen::Package`] reads what a viewer needs. This is the complete
//! model: every section between the summary and the export data, as bytes the
//! game wrote them, so a package can be taken apart, changed, and put back
//! together — and, from nothing, built. The layout is `FZenPackageSummary` as
//! this game ships it (UE 5.5, no versioning block), measured against the
//! shipped tag wrappers; `mjolnir zen-roundtrip` re-serializes every one of
//! them and requires the bytes back.
//!
//! ```text
//! summary (52 bytes)
//!   u32 has_versioning_info (0)      u32 header_size
//!   u32 name index, u32 name number  u32 package_flags   u32 cooked_header_size
//!   i32 imported_public_export_hashes_offset   i32 import_map_offset
//!   i32 export_map_offset   i32 export_bundle_entries_offset
//!   i32 dependency_bundle_headers_offset   i32 dependency_bundle_entries_offset
//!   i32 imported_package_names_offset
//! name batch      count, string bytes, hash version, hashes, 2-byte headers, strings
//! u64 pad size, pad bytes            (aligns the map to 8)
//! u64 bulk map bytes, entries        32 bytes each
//! imported public export hashes      u64 each
//! import map                         u64 FPackageObjectIndex each
//! export map                         72 bytes each
//! export bundle entries              {u32 local export, u32 command} each
//! dependency bundle headers          {i32 first entry, 4 × u32 counts} each
//! dependency bundle entries          i32 FPackageIndex each
//! imported package names             name batch; an empty one is the 4-byte count alone
//! = header_size
//! export data                        each export's serial bytes, tiled
//! u32 PACKAGE_FILE_TAG               c1 83 2a 9e
//! ```

use std::fmt;

/// `PACKAGE_FILE_TAG`, the four bytes after the last export.
pub const PACKAGE_FILE_TAG: [u8; 4] = [0xc1, 0x83, 0x2a, 0x9e];
/// `FNAME_HASH_ALGORITHM_ID`, the hash version every shipped name batch carries.
pub const NAME_HASH_VERSION: u64 = 0xC164_0000;
pub const EXPORT_ENTRY: usize = 72;
pub const BULK_ENTRY: usize = 32;
pub const SUMMARY: usize = 52;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("package data ends early at {0:#x}")]
    Eof(usize),
    #[error("{0}")]
    Layout(&'static str),
    #[error("{section} has a size of {size} bytes, not a whole number of {unit}-byte entries")]
    Ragged {
        section: &'static str,
        size: usize,
        unit: usize,
    },
}

/// A name batch: the strings plus the hashes the cooker stored beside them.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct NameBatch {
    pub hash_version: u64,
    pub names: Vec<String>,
    /// One per name. Kept as read so a round trip is exact; [`name_hash`]
    /// derives them for a batch built from scratch.
    pub hashes: Vec<u64>,
}

/// `FBulkDataMapEntry`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BulkEntry {
    pub serial_offset: i64,
    pub duplicate_serial_offset: i64,
    pub serial_size: i64,
    pub flags: u32,
    pub cooked_index: u32,
}

/// `FExportMapEntry`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExportEntry {
    pub cooked_serial_offset: u64,
    pub cooked_serial_size: u64,
    pub name_index: u32,
    pub name_number: u32,
    pub outer: u64,
    pub class: u64,
    pub super_: u64,
    pub template: u64,
    pub public_export_hash: u64,
    pub object_flags: u32,
    pub filter_flags: u32,
}

/// `FDependencyBundleHeader`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct DependencyBundleHeader {
    pub first_entry_index: i32,
    /// `create_before_create, serialize_before_create, create_before_serialize,
    /// serialize_before_serialize`.
    pub counts: [u32; 4],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ZenPackage {
    pub has_versioning_info: u32,
    pub name_index: u32,
    pub name_number: u32,
    pub package_flags: u32,
    pub cooked_header_size: u32,
    pub names: NameBatch,
    /// The bytes between the name batch and the bulk-data map, after the
    /// `pad size` word. Zeros in every shipped package; kept as read.
    pub pad: Vec<u8>,
    pub bulk: Vec<BulkEntry>,
    pub imported_public_export_hashes: Vec<u64>,
    pub import_map: Vec<u64>,
    pub export_map: Vec<ExportEntry>,
    pub export_bundle_entries: Vec<(u32, u32)>,
    pub dependency_bundle_headers: Vec<DependencyBundleHeader>,
    pub dependency_bundle_entries: Vec<i32>,
    /// `FZenPackageImportedPackageNamesContainer`: a name batch followed by
    /// one `FName` number per name (all zero in every shipped tag wrapper).
    pub imported_package_names: NameBatch,
    pub imported_package_name_numbers: Vec<u32>,
    /// Everything after the header up to the trailer: the exports' serial
    /// bytes, tiled in export-map order.
    pub export_data: Vec<u8>,
    /// Whether the package ended with [`PACKAGE_FILE_TAG`]. Every shipped
    /// package does.
    pub trailer: bool,
}

struct Reader<'a> {
    b: &'a [u8],
    at: usize,
}

impl<'a> Reader<'a> {
    fn u32(&mut self) -> Result<u32, Error> {
        let v = self
            .b
            .get(self.at..self.at + 4)
            .map(|s| u32::from_le_bytes(s.try_into().unwrap()))
            .ok_or(Error::Eof(self.at))?;
        self.at += 4;
        Ok(v)
    }
    fn u64(&mut self) -> Result<u64, Error> {
        let v = self
            .b
            .get(self.at..self.at + 8)
            .map(|s| u64::from_le_bytes(s.try_into().unwrap()))
            .ok_or(Error::Eof(self.at))?;
        self.at += 8;
        Ok(v)
    }
    fn bytes(&mut self, n: usize) -> Result<&'a [u8], Error> {
        let s = self
            .b
            .get(self.at..self.at + n)
            .ok_or(Error::Eof(self.at))?;
        self.at += n;
        Ok(s)
    }
}

impl NameBatch {
    fn read(r: &mut Reader<'_>) -> Result<NameBatch, Error> {
        let count = r.u32()? as usize;
        if count == 0 {
            return Ok(NameBatch::default());
        }
        if count > 1_000_000 {
            return Err(Error::Layout("implausible name count"));
        }
        let _string_bytes = r.u32()?;
        let hash_version = r.u64()?;
        let mut hashes = Vec::with_capacity(count);
        for _ in 0..count {
            hashes.push(r.u64()?);
        }
        let mut headers = Vec::with_capacity(count);
        for _ in 0..count {
            let h = r.bytes(2)?;
            headers.push((
                h[0] & 0x80 != 0,
                (((h[0] & 0x7F) as usize) << 8) | h[1] as usize,
            ));
        }
        let mut names = Vec::with_capacity(count);
        for (utf16, len) in headers {
            if utf16 {
                let raw = r.bytes(len * 2)?;
                let units: Vec<u16> = raw
                    .chunks_exact(2)
                    .map(|c| u16::from_le_bytes([c[0], c[1]]))
                    .collect();
                names.push(String::from_utf16_lossy(&units));
            } else {
                names.push(String::from_utf8_lossy(r.bytes(len)?).into_owned());
            }
        }
        Ok(NameBatch {
            hash_version,
            names,
            hashes,
        })
    }

    fn write(&self, out: &mut Vec<u8>) {
        out.extend_from_slice(&(self.names.len() as u32).to_le_bytes());
        if self.names.is_empty() {
            return;
        }
        let encoded: Vec<(bool, Vec<u8>)> = self
            .names
            .iter()
            .map(|n| {
                if n.is_ascii() {
                    (false, n.as_bytes().to_vec())
                } else {
                    (
                        true,
                        n.encode_utf16().flat_map(|u| u.to_le_bytes()).collect(),
                    )
                }
            })
            .collect();
        let string_bytes: usize = encoded.iter().map(|(_, b)| b.len()).sum();
        out.extend_from_slice(&(string_bytes as u32).to_le_bytes());
        out.extend_from_slice(&self.hash_version.to_le_bytes());
        for h in &self.hashes {
            out.extend_from_slice(&h.to_le_bytes());
        }
        for (utf16, b) in &encoded {
            let len = if *utf16 { b.len() / 2 } else { b.len() };
            out.push(((*utf16 as u8) << 7) | ((len >> 8) as u8 & 0x7F));
            out.push((len & 0xFF) as u8);
        }
        for (_, b) in &encoded {
            out.extend_from_slice(b);
        }
    }

    /// How many bytes this batch serializes to.
    pub fn serialized_len(&self) -> usize {
        let mut out = Vec::new();
        self.write(&mut out);
        out.len()
    }

    /// A batch built from scratch: hashes derived by [`name_hash`].
    pub fn from_names(names: Vec<String>) -> NameBatch {
        let hashes = names.iter().map(|n| name_hash(n)).collect();
        NameBatch {
            hash_version: NAME_HASH_VERSION,
            names,
            hashes,
        }
    }

    /// The index of `name`, adding it if absent.
    pub fn intern(&mut self, name: &str) -> u32 {
        if let Some(i) = self.names.iter().position(|n| n == name) {
            return i as u32;
        }
        self.names.push(name.to_string());
        self.hashes.push(name_hash(name));
        (self.names.len() - 1) as u32
    }
}

/// The hash stored beside a name-batch entry: CityHash64 of the name
/// lowercased, over its bytes as stored (UTF-8 for ASCII names, UTF-16LE
/// otherwise). Verified against every shipped tag wrapper by
/// `mjolnir zen-roundtrip --hashes`.
pub fn name_hash(name: &str) -> u64 {
    let lower = name.to_lowercase();
    if name.is_ascii() {
        ue_iostore::city::city_hash64(lower.as_bytes())
    } else {
        let bytes: Vec<u8> = lower.encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
        ue_iostore::city::city_hash64(&bytes)
    }
}

/// CityHash64 of a string lowercased and encoded UTF-16LE — the form behind
/// package ids, public export hashes and script-import indices.
pub fn utf16_lower_hash(s: &str) -> u64 {
    let bytes: Vec<u8> = s
        .to_lowercase()
        .encode_utf16()
        .flat_map(|u| u.to_le_bytes())
        .collect();
    ue_iostore::city::city_hash64(&bytes)
}

/// An export's `public_export_hash`: the hash of its object (leaf) name.
pub fn public_export_hash(object_name: &str) -> u64 {
    utf16_lower_hash(object_name)
}

/// The `FPackageObjectIndex` of a `/Script/...` object, e.g.
/// `/Script/BlamSynchronization.BlamBipedTagDataAsset` or its
/// `Default__` CDO: `:` and `.` become `/`, the path is lowercased, hashed as
/// UTF-16LE, the top two bits cleared and the `ScriptImport` type set.
pub fn script_import_index(object_path: &str) -> u64 {
    let path: String = object_path
        .chars()
        .map(|c| if c == ':' || c == '.' { '/' } else { c })
        .collect();
    (utf16_lower_hash(&path) & !(3u64 << 62)) | (1u64 << 62)
}

impl ZenPackage {
    pub fn parse(data: &[u8]) -> Result<ZenPackage, Error> {
        let mut r = Reader { b: data, at: 0 };
        let has_versioning_info = r.u32()?;
        let header_size = r.u32()? as usize;
        let name_index = r.u32()?;
        let name_number = r.u32()?;
        let package_flags = r.u32()?;
        let cooked_header_size = r.u32()?;
        let ipeh_off = r.u32()? as usize;
        let import_off = r.u32()? as usize;
        let export_off = r.u32()? as usize;
        let bundle_off = r.u32()? as usize;
        let dep_headers_off = r.u32()? as usize;
        let dep_entries_off = r.u32()? as usize;
        let names_off = r.u32()? as usize;
        if has_versioning_info != 0 {
            return Err(Error::Layout(
                "packages with a versioning block are not modelled",
            ));
        }
        let names = NameBatch::read(&mut r)?;
        let pad_size = r.u64()? as usize;
        let pad = r.bytes(pad_size)?.to_vec();
        let bulk_bytes = r.u64()? as usize;
        if bulk_bytes % BULK_ENTRY != 0 {
            return Err(Error::Ragged {
                section: "bulk data map",
                size: bulk_bytes,
                unit: BULK_ENTRY,
            });
        }
        let mut bulk = Vec::with_capacity(bulk_bytes / BULK_ENTRY);
        for _ in 0..bulk_bytes / BULK_ENTRY {
            bulk.push(BulkEntry {
                serial_offset: r.u64()? as i64,
                duplicate_serial_offset: r.u64()? as i64,
                serial_size: r.u64()? as i64,
                flags: r.u32()?,
                cooked_index: r.u32()?,
            });
        }
        if r.at != ipeh_off {
            return Err(Error::Layout(
                "the bulk-data map does not end where the imported public export hashes begin",
            ));
        }
        let section =
            |name: &'static str, from: usize, to: usize, unit: usize| -> Result<usize, Error> {
                let size = to
                    .checked_sub(from)
                    .ok_or(Error::Layout("section offsets run backwards"))?;
                if size % unit != 0 {
                    return Err(Error::Ragged {
                        section: name,
                        size,
                        unit,
                    });
                }
                Ok(size / unit)
            };
        let mut imported_public_export_hashes = Vec::new();
        for _ in 0..section("imported public export hashes", ipeh_off, import_off, 8)? {
            imported_public_export_hashes.push(r.u64()?);
        }
        let mut import_map = Vec::new();
        for _ in 0..section("import map", import_off, export_off, 8)? {
            import_map.push(r.u64()?);
        }
        let mut export_map = Vec::new();
        for _ in 0..section("export map", export_off, bundle_off, EXPORT_ENTRY)? {
            export_map.push(ExportEntry {
                cooked_serial_offset: r.u64()?,
                cooked_serial_size: r.u64()?,
                name_index: r.u32()?,
                name_number: r.u32()?,
                outer: r.u64()?,
                class: r.u64()?,
                super_: r.u64()?,
                template: r.u64()?,
                public_export_hash: r.u64()?,
                object_flags: r.u32()?,
                filter_flags: r.u32()?,
            });
        }
        let mut export_bundle_entries = Vec::new();
        for _ in 0..section("export bundle entries", bundle_off, dep_headers_off, 8)? {
            export_bundle_entries.push((r.u32()?, r.u32()?));
        }
        let mut dependency_bundle_headers = Vec::new();
        for _ in 0..section(
            "dependency bundle headers",
            dep_headers_off,
            dep_entries_off,
            20,
        )? {
            dependency_bundle_headers.push(DependencyBundleHeader {
                first_entry_index: r.u32()? as i32,
                counts: [r.u32()?, r.u32()?, r.u32()?, r.u32()?],
            });
        }
        let mut dependency_bundle_entries = Vec::new();
        for _ in 0..section("dependency bundle entries", dep_entries_off, names_off, 4)? {
            dependency_bundle_entries.push(r.u32()? as i32);
        }
        let imported_package_names = NameBatch::read(&mut r)?;
        let mut imported_package_name_numbers =
            Vec::with_capacity(imported_package_names.names.len());
        for _ in 0..imported_package_names.names.len() {
            imported_package_name_numbers.push(r.u32()?);
        }
        if r.at != header_size {
            return Err(Error::Layout(
                "the imported package names do not end at the declared header size",
            ));
        }
        let rest = data.get(header_size..).ok_or(Error::Eof(header_size))?;
        let trailer = rest.len() >= 4 && rest[rest.len() - 4..] == PACKAGE_FILE_TAG;
        let export_data = if trailer {
            rest[..rest.len() - 4].to_vec()
        } else {
            rest.to_vec()
        };
        Ok(ZenPackage {
            has_versioning_info,
            name_index,
            name_number,
            package_flags,
            cooked_header_size,
            names,
            pad,
            bulk,
            imported_public_export_hashes,
            import_map,
            export_map,
            export_bundle_entries,
            dependency_bundle_headers,
            dependency_bundle_entries,
            imported_package_names,
            imported_package_name_numbers,
            export_data,
            trailer,
        })
    }

    /// Serialize. Every offset in the summary is recomputed from the content;
    /// `cooked_header_size`, `package_flags` and the export map's serial
    /// offsets and sizes are written as held — callers that change the export
    /// data update those themselves ([`ZenPackage::set_export_data`]).
    pub fn write(&self) -> Vec<u8> {
        let mut out = vec![0u8; SUMMARY];
        self.names.write(&mut out);
        out.extend_from_slice(&(self.pad.len() as u64).to_le_bytes());
        out.extend_from_slice(&self.pad);
        out.extend_from_slice(&((self.bulk.len() * BULK_ENTRY) as u64).to_le_bytes());
        for b in &self.bulk {
            out.extend_from_slice(&b.serial_offset.to_le_bytes());
            out.extend_from_slice(&b.duplicate_serial_offset.to_le_bytes());
            out.extend_from_slice(&b.serial_size.to_le_bytes());
            out.extend_from_slice(&b.flags.to_le_bytes());
            out.extend_from_slice(&b.cooked_index.to_le_bytes());
        }
        let ipeh_off = out.len() as u32;
        for h in &self.imported_public_export_hashes {
            out.extend_from_slice(&h.to_le_bytes());
        }
        let import_off = out.len() as u32;
        for i in &self.import_map {
            out.extend_from_slice(&i.to_le_bytes());
        }
        let export_off = out.len() as u32;
        for e in &self.export_map {
            out.extend_from_slice(&e.cooked_serial_offset.to_le_bytes());
            out.extend_from_slice(&e.cooked_serial_size.to_le_bytes());
            out.extend_from_slice(&e.name_index.to_le_bytes());
            out.extend_from_slice(&e.name_number.to_le_bytes());
            out.extend_from_slice(&e.outer.to_le_bytes());
            out.extend_from_slice(&e.class.to_le_bytes());
            out.extend_from_slice(&e.super_.to_le_bytes());
            out.extend_from_slice(&e.template.to_le_bytes());
            out.extend_from_slice(&e.public_export_hash.to_le_bytes());
            out.extend_from_slice(&e.object_flags.to_le_bytes());
            out.extend_from_slice(&e.filter_flags.to_le_bytes());
        }
        let bundle_off = out.len() as u32;
        for (local, command) in &self.export_bundle_entries {
            out.extend_from_slice(&local.to_le_bytes());
            out.extend_from_slice(&command.to_le_bytes());
        }
        let dep_headers_off = out.len() as u32;
        for h in &self.dependency_bundle_headers {
            out.extend_from_slice(&h.first_entry_index.to_le_bytes());
            for c in h.counts {
                out.extend_from_slice(&c.to_le_bytes());
            }
        }
        let dep_entries_off = out.len() as u32;
        for e in &self.dependency_bundle_entries {
            out.extend_from_slice(&e.to_le_bytes());
        }
        let names_off = out.len() as u32;
        self.imported_package_names.write(&mut out);
        for n in &self.imported_package_name_numbers {
            out.extend_from_slice(&n.to_le_bytes());
        }
        let header_size = out.len() as u32;

        let put = |out: &mut Vec<u8>, at: usize, v: u32| {
            out[at..at + 4].copy_from_slice(&v.to_le_bytes())
        };
        put(&mut out, 0, self.has_versioning_info);
        put(&mut out, 4, header_size);
        put(&mut out, 8, self.name_index);
        put(&mut out, 12, self.name_number);
        put(&mut out, 16, self.package_flags);
        put(&mut out, 20, self.cooked_header_size);
        put(&mut out, 24, ipeh_off);
        put(&mut out, 28, import_off);
        put(&mut out, 32, export_off);
        put(&mut out, 36, bundle_off);
        put(&mut out, 40, dep_headers_off);
        put(&mut out, 44, dep_entries_off);
        put(&mut out, 48, names_off);

        out.extend_from_slice(&self.export_data);
        if self.trailer {
            out.extend_from_slice(&PACKAGE_FILE_TAG);
        }
        out
    }

    /// The package's own name.
    pub fn name(&self) -> String {
        self.mapped_name(self.name_index, self.name_number)
    }

    pub fn mapped_name(&self, index: u32, number: u32) -> String {
        let base = self
            .names
            .names
            .get((index & ((1 << 30) - 1)) as usize)
            .cloned()
            .unwrap_or_default();
        if number != 0 {
            format!("{base}_{}", number - 1)
        } else {
            base
        }
    }

    /// The serial bytes of one export.
    pub fn export_bytes(&self, index: usize) -> Option<&[u8]> {
        let e = self.export_map.get(index)?;
        self.export_data.get(
            e.cooked_serial_offset as usize
                ..(e.cooked_serial_offset + e.cooked_serial_size) as usize,
        )
    }

    /// Replace the export data of a single-export package and keep the export
    /// map's size in step.
    pub fn set_export_data(&mut self, data: Vec<u8>) -> Result<(), Error> {
        if self.export_map.len() != 1 {
            return Err(Error::Layout("set_export_data expects exactly one export"));
        }
        self.export_map[0].cooked_serial_offset = 0;
        self.export_map[0].cooked_serial_size = data.len() as u64;
        self.export_data = data;
        Ok(())
    }
}

/// `PKG_FilterEditorOnly | PKG_UnversionedProperties | PKG_Cooked`.
pub const PACKAGE_FLAGS: u32 = 0x8000_2200;
/// The above plus `PKG_CookGenerated`: the five level-resident groups.
pub const PACKAGE_FLAGS_GENERATED: u32 = 0x8800_2200;
/// `RF_Public | RF_Standalone | RF_Transactional`.
pub const OBJECT_FLAGS: u32 = 0xb;
/// `RF_Public` alone, on the generated groups.
pub const OBJECT_FLAGS_GENERATED: u32 = 0x1;
/// The one bulk-data flag word every tag payload carries.
pub const BULK_FLAGS: u32 = 66_817;
/// The module every tag wrapper class lives in.
pub const BLAM_MODULE: &str = "/Script/BlamSynchronization";

/// The groups whose tags are cooked with the level (`_Generated_`), and carry
/// `PKG_CookGenerated` and bare `RF_Public`.
pub const GENERATED_GROUPS: [&str; 5] = [
    "scenario",
    "scenario_structure_bsp",
    "scenario_structure_lighting_info",
    "structure_design",
    "structure_seams",
];

/// `Blam<Pascal(group)>TagDataAsset`: `frame_event_list` →
/// `BlamFrameEventListTagDataAsset`. Holds for every shipped group.
pub fn wrapper_class(group: &str) -> String {
    let pascal: String = group
        .split('_')
        .map(|part| {
            let mut c = part.chars();
            match c.next() {
                Some(f) => f.to_ascii_uppercase().to_string() + c.as_str(),
                None => String::new(),
            }
        })
        .collect();
    format!("Blam{pascal}TagDataAsset")
}

/// The legacy header size the cooker records for a wrapper with no imports
/// and no properties: exact for all 3,563 such shipped tags. A wrapper with
/// imports carries legacy import names the zen header does not, so its value
/// cannot be derived here; the game has not been seen to read it.
pub fn bare_cooked_header_size(package_path: &str, object_name: &str, class: &str) -> u32 {
    (617 + 2 * package_path.len() + object_name.len() + 2 * class.len()) as u32
}

/// The export body of a wrapper whose class adds no property: the constant
/// frame around one fragment that skips the three base properties.
pub const BARE_EXPORT_BODY: [u8; 10] = [0, 0, 0, 0, 0x03, 0x01, 0, 0, 0, 0];

impl ZenPackage {
    /// A tag wrapper built from nothing but the group, the package path and
    /// the payload length — the shape of every shipped tag whose class adds no
    /// property (47 of the 101 shipped groups). `mjolnir zen-roundtrip
    /// --rebuild` requires this to reproduce each such shipped wrapper byte
    /// for byte.
    pub fn bare_tag(group: &str, package_path: &str, ubulk_len: u64) -> ZenPackage {
        let object_name = package_path
            .rsplit('/')
            .next()
            .unwrap_or(package_path)
            .to_string();
        let class = wrapper_class(group);
        let class_index = script_import_index(&format!("{BLAM_MODULE}.{class}"));
        let cdo_index = script_import_index(&format!("{BLAM_MODULE}.Default__{class}"));
        let module_index = script_import_index(BLAM_MODULE);
        let generated = GENERATED_GROUPS.contains(&group);
        let names = NameBatch::from_names(vec![object_name.clone(), package_path.to_string()]);

        // The bulk map is aligned to 8 after the name batch and the pad word.
        let mut probe = vec![0u8; SUMMARY];
        names.write(&mut probe);
        let pad_len = (8 - (probe.len() + 8) % 8) % 8;

        ZenPackage {
            has_versioning_info: 0,
            name_index: 1,
            name_number: 0,
            package_flags: if generated {
                PACKAGE_FLAGS_GENERATED
            } else {
                PACKAGE_FLAGS
            },
            cooked_header_size: bare_cooked_header_size(package_path, &object_name, &class),
            names,
            pad: vec![0; pad_len],
            bulk: vec![BulkEntry {
                serial_offset: 0,
                duplicate_serial_offset: -1,
                serial_size: ubulk_len as i64,
                flags: BULK_FLAGS,
                cooked_index: 0,
            }],
            imported_public_export_hashes: Vec::new(),
            import_map: vec![cdo_index, class_index, module_index],
            export_map: vec![ExportEntry {
                cooked_serial_offset: 0,
                cooked_serial_size: BARE_EXPORT_BODY.len() as u64,
                name_index: 0,
                name_number: 0,
                outer: u64::MAX,
                class: class_index,
                super_: u64::MAX,
                template: cdo_index,
                public_export_hash: public_export_hash(&object_name),
                object_flags: if generated {
                    OBJECT_FLAGS_GENERATED
                } else {
                    OBJECT_FLAGS
                },
                filter_flags: 0,
            }],
            export_bundle_entries: vec![(0, 0), (0, 1)],
            dependency_bundle_headers: vec![DependencyBundleHeader::default()],
            dependency_bundle_entries: Vec::new(),
            imported_package_names: NameBatch::default(),
            imported_package_name_numbers: Vec::new(),
            export_data: BARE_EXPORT_BODY.to_vec(),
            trailer: true,
        }
    }

    /// Whether this wrapper has the bare shape [`ZenPackage::bare_tag`]
    /// produces: no imports, no properties, one export.
    pub fn is_bare(&self) -> bool {
        self.names.names.len() == 2
            && self.import_map.len() == 3
            && self.imported_public_export_hashes.is_empty()
            && self.export_map.len() == 1
            && self.export_data == BARE_EXPORT_BODY
    }
}

impl fmt::Display for ZenPackage {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        writeln!(
            f,
            "{}  flags {:#010x}  cooked header {}",
            self.name(),
            self.package_flags,
            self.cooked_header_size
        )?;
        writeln!(
            f,
            "  names {}  bulk {}  imports {}  exports {}  imported packages {}",
            self.names.names.len(),
            self.bulk.len(),
            self.import_map.len(),
            self.export_map.len(),
            self.imported_package_names.names.len()
        )?;
        for (i, e) in self.export_map.iter().enumerate() {
            writeln!(
                f,
                "  export {i}: {} {} bytes  flags {:#x}  class {:#018x}",
                self.mapped_name(e.name_index, e.name_number),
                e.cooked_serial_size,
                e.object_flags,
                e.class
            )?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The marine collision model's wrapper as shipped on CU4: 374 bytes,
    /// decoded by hand in the module docs' terms.
    fn marine_collision_model() -> Vec<u8> {
        let hex = concat!(
            "000000006801000001000000000000000022008031030000e0000000e0000000",
            "f8000000400100005001000064010000640100000200000051000000000064c1",
            "00000000d8ab2fdc12af0997ffa8c3b7bfd217df0016003b6d6172696e652d63",
            "6f6c6c6973696f6e5f6d6f64656c2f47616d652f546167732f6f626a65637473",
            "2f636861726163746572732f6d6172696e652f6d6172696e652d636f6c6c6973",
            "696f6e5f6d6f64656c0700000000000000000000000000002000000000000000",
            "0000000000000000fffffffffffffffffb200200000000000105010000000000",
            "8daf020b664d144f6f2075a51cce864542d3d9f3cd5b4d420000000000000000",
            "0a000000000000000000000000000000ffffffffffffffff6f2075a51cce8645",
            "ffffffffffffffff8daf020b664d144f7a43e226e05fe4240b00000000000000",
            "0000000000000000000000000100000000000000000000000000000000000000",
            "000000000000000000000000030100000000c1832a9e"
        );
        let hex: String = hex.chars().filter(|c| !c.is_whitespace()).collect();
        (0..hex.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
            .collect()
    }

    #[test]
    fn the_hand_decoded_wrapper_round_trips() {
        let bytes = marine_collision_model();
        assert_eq!(bytes.len(), 374);
        let p = ZenPackage::parse(&bytes).unwrap();
        assert_eq!(
            p.name(),
            "/Game/Tags/objects/characters/marine/marine-collision_model"
        );
        assert_eq!(p.names.names[0], "marine-collision_model");
        assert_eq!(p.package_flags, 0x8000_2200);
        assert_eq!(p.cooked_header_size, 817);
        assert_eq!(p.bulk.len(), 1);
        assert_eq!(p.bulk[0].serial_size, 139_515);
        assert_eq!(p.bulk[0].flags, 66_817);
        assert_eq!(p.bulk[0].duplicate_serial_offset, -1);
        assert_eq!(p.import_map.len(), 3);
        assert_eq!(p.export_map.len(), 1);
        assert_eq!(p.export_map[0].object_flags, 0xb);
        assert_eq!(
            p.export_map[0].template, p.import_map[0],
            "slot 0 is the CDO"
        );
        assert_eq!(
            p.export_map[0].class, p.import_map[1],
            "slot 1 is the class"
        );
        assert_eq!(p.export_bundle_entries, vec![(0, 0), (0, 1)]);
        assert_eq!(p.dependency_bundle_headers.len(), 1);
        assert!(p.dependency_bundle_entries.is_empty());
        assert!(p.imported_package_names.names.is_empty());
        assert_eq!(p.export_data, [0, 0, 0, 0, 0x03, 0x01, 0, 0, 0, 0]);
        assert!(p.trailer);
        assert_eq!(p.write(), bytes);
    }

    #[test]
    fn the_hashes_follow_the_derivations() {
        let p = ZenPackage::parse(&marine_collision_model()).unwrap();
        for (name, hash) in p.names.names.iter().zip(&p.names.hashes) {
            assert_eq!(name_hash(name), *hash, "{name}");
        }
        assert_eq!(
            public_export_hash("marine-collision_model"),
            p.export_map[0].public_export_hash
        );
        assert_eq!(
            script_import_index("/Script/BlamSynchronization.BlamCollisionModelTagDataAsset"),
            p.export_map[0].class
        );
        assert_eq!(
            script_import_index(
                "/Script/BlamSynchronization.Default__BlamCollisionModelTagDataAsset"
            ),
            p.export_map[0].template
        );
        assert_eq!(
            script_import_index("/Script/BlamSynchronization"),
            p.import_map[2]
        );
    }

    #[test]
    fn a_bare_tag_is_built_from_scratch_byte_for_byte() {
        let shipped = marine_collision_model();
        let built = ZenPackage::bare_tag(
            "collision_model",
            "/Game/Tags/objects/characters/marine/marine-collision_model",
            139_515,
        );
        assert!(built.is_bare());
        assert_eq!(built.write(), shipped);
        // A new name, a new identity — nothing else changes shape.
        let renamed = ZenPackage::bare_tag(
            "collision_model",
            "/Game/Tags/objects/characters/marinf/marinf-collision_model",
            139_515,
        );
        assert_ne!(renamed.write(), shipped);
        assert_eq!(renamed.write().len(), shipped.len());
        assert_eq!(renamed.names.names[0], "marinf-collision_model");
        assert_eq!(
            renamed.export_map[0].public_export_hash,
            public_export_hash("marinf-collision_model")
        );
    }

    #[test]
    fn a_rebuilt_export_keeps_the_map_in_step() {
        let mut p = ZenPackage::parse(&marine_collision_model()).unwrap();
        p.set_export_data(vec![0; 14]).unwrap();
        let again = ZenPackage::parse(&p.write()).unwrap();
        assert_eq!(again.export_map[0].cooked_serial_size, 14);
        assert_eq!(again.export_bytes(0).unwrap().len(), 14);
    }
}
