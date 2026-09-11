//! The simulation's own table of loaded tags, read without a scan.
//!
//! `HaloSimulation_tag_release.dll` keeps every loaded tag in one slotted table
//! it labels `tag instance`. Each 0x30-byte entry names the tag, its group, a
//! salt that makes the entry's handle unique across reloads, and the root
//! block descriptor — count plus two *encoded offsets* to the root element's
//! data and to its definition. So "what is loaded" and "where is this tag's
//! root" are one pointer-chase from two globals in the module, not a 13 GB
//! sweep of the process (`crate::census`). The sweep remains the fallback for
//! a build no [`Profile`] describes.
//!
//! An encoded offset packs a segment and a position: the top four bits index
//! a sixteen-slot table of segment bases, and the whole 32-bit value times four
//! is the byte offset from that base ([`Segments::resolve`]). That is the rule
//! `crate::derive_arena` was recovering per tag as `arena + 4 * words` — the
//! arena *is* the segment base, the nibble riding along in the product — made
//! exact and read from the module instead of inferred.
//!
//! Measured 2026-09-05 on build `2026.08.11.1121610.2 … CU4` in mission A30:
//! 7,055 entries, every one with a resolvable root, and the assault rifle's
//! root bytes matching the shipped tag at its scalar fields. Layout, addresses
//! and the console measurements around them: `docs/tag_table_and_string_ids.md`.

use std::collections::HashMap;
use std::io::Read;

use crate::{Error, Process, Result};

/// The module the table lives in.
pub const TAG_DLL: &str = "HaloSimulation_tag_release.dll";

/// Bytes read from another process. `Process` is the real one; tests use a
/// map of blocks.
pub trait Memory {
    fn read(&self, addr: u64, len: usize) -> Result<Vec<u8>>;

    fn u16(&self, addr: u64) -> Result<u16> {
        let b = self.read(addr, 2)?;
        Ok(u16::from_le_bytes(b[..2].try_into().unwrap()))
    }
    fn u32(&self, addr: u64) -> Result<u32> {
        let b = self.read(addr, 4)?;
        Ok(u32::from_le_bytes(b[..4].try_into().unwrap()))
    }
    fn u64(&self, addr: u64) -> Result<u64> {
        let b = self.read(addr, 8)?;
        Ok(u64::from_le_bytes(b[..8].try_into().unwrap()))
    }

    /// A NUL-terminated string at `addr`, at most `max` bytes. Reads shrink
    /// toward the string rather than failing when `addr + max` crosses into an
    /// unmapped page.
    fn cstr(&self, addr: u64, max: usize) -> Result<String> {
        let mut len = max;
        loop {
            match self.read(addr, len) {
                Ok(b) => {
                    let end = b.iter().position(|c| *c == 0).unwrap_or(b.len());
                    return Ok(String::from_utf8_lossy(&b[..end]).into_owned());
                }
                Err(e) if len <= 8 => return Err(e),
                Err(_) => len /= 4,
            }
        }
    }
}

impl Memory for Process {
    fn read(&self, addr: u64, len: usize) -> Result<Vec<u8>> {
        Process::read(self, addr, len)
    }
}

/// Where the globals sit in one build of the tag module, as RVAs.
///
/// A build is chosen by the SHA-256 of the module file — the image every RVA
/// is an offset into — and an unknown hash is refused rather than guessed at.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Profile {
    pub label: &'static str,
    /// Uppercase hex SHA-256 of `HaloSimulation_tag_release.dll`.
    pub dll_sha256: &'static str,
    /// Pointer to the `tag instance` table object.
    pub tag_table_pointer: u64,
    /// Sixteen u64 segment bases.
    pub segment_table: u64,
    /// String-id registry: pointer to the name-bytes storage.
    pub string_id_storage: u64,
    /// Bytes of storage in use.
    pub string_id_used: u64,
    /// Pointer to a per-id `char*` table.
    pub string_id_strings: u64,
    /// Registered names.
    pub string_id_count: u64,
    /// Pointer to the name → id hash table.
    pub string_id_map: u64,
    /// The engine's built-in ids, sixteen bytes each.
    pub string_id_builtin: u64,
}

/// Steam `2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4`, tag module
/// `C8C14440…3BF7` (`docs/build_lock.md`).
pub const CU4: Profile = Profile {
    label: "Steam CU4 2026.08.11.1121610.2",
    dll_sha256: "C8C144404ADF61A9DE821C996682A7E66ABADD7E530397D3BBDE31C123203BF7",
    tag_table_pointer: 0x0182_D1E8,
    segment_table: 0x02C2_CCC0,
    string_id_storage: 0x0135_7490,
    string_id_used: 0x0135_7498,
    string_id_strings: 0x0135_74A0,
    string_id_count: 0x0135_74A8,
    string_id_map: 0x0135_74C0,
    string_id_builtin: 0x0082_F0A0,
};

/// Every build this crate knows, newest first.
pub const PROFILES: &[Profile] = &[CU4];

/// One anchor into the tag module's code: an instruction shape that refers
/// to a global through a RIP-relative displacement, with the displacement
/// wildcarded (`signatures/README.md`: never bake a displacement into a
/// pattern). The instruction is `disp_at + 4` bytes long, so the global's RVA
/// is `instruction RVA + disp_at + 4 + disp`.
#[derive(Debug, Clone, Copy)]
pub struct Anchor {
    pub name: &'static str,
    pub pattern: &'static str,
    /// Byte offset of the disp32 within the match.
    pub disp_at: usize,
}

/// The four anchors that recover every profile RVA from the module on disk,
/// chosen on CU4 (`2026.08.11.1121610.2`) for shapes that say what the code
/// does rather than where it is: each matched exactly once.
pub const ANCHORS: [Anchor; 4] = [
    // The table's constructor storing the new object into the global, then
    // setting its +0x31 flag: `mov [rip+d], rbx; mov byte [rbx+0x31], 1;
    // mov rcx, rbx`.
    Anchor {
        name: "tag table pointer",
        pattern: "48 89 1D ? ? ? ? C6 43 31 01 48 8B CB",
        disp_at: 3,
    },
    // The encoded-offset decode itself: `lea r14, [rip+d]` (the segment
    // table), then `movsxd rax, edx; lea rcx, [r8+rax*4]; shr r8, 0x1c` —
    // words times four, and the top nibble as the segment.
    Anchor {
        name: "segment table",
        pattern: "4C 8D 35 ? ? ? ? 48 63 C2 49 8D 0C 80 49 C1 E8 1C",
        disp_at: 3,
    },
    // The registry's constructor storing the name storage pointer, then
    // sizing the hash table: 0xFF800 buckets and 0x7FC00 entries at most —
    // the header numbers the live read sees. The other five registry
    // globals sit at fixed offsets from this one.
    Anchor {
        name: "string-id storage",
        pattern: "48 89 05 ? ? ? ? BA 00 F8 0F 00 41 B8 00 FC 07 00",
        disp_at: 3,
    },
    // A builtin-id lookup: `lea rax, [rip+d]; mov eax, [rax+rdi*8]`.
    Anchor {
        name: "string-id builtins",
        pattern: "48 8D 05 ? ? ? ? 8B 04 F8 89 44 24 70 EB 20",
        disp_at: 3,
    },
];

/// Offsets of the registry globals from the storage pointer, measured on CU4
/// (`storage 0x01357490 … map 0x013574C0`).
const REGISTRY_USED: u64 = 0x8;
const REGISTRY_STRINGS: u64 = 0x10;
const REGISTRY_COUNT: u64 = 0x18;
const REGISTRY_MAP: u64 = 0x30;

/// Resolve one anchor in the module image: the RVA it refers to.
pub fn resolve_anchor(image: &[u8], anchor: &Anchor) -> Result<u64> {
    let (text_rva, text_off, code) = crate::objects::text_section(image)?;
    let m = crate::objects::find_unique(code, anchor.pattern)?;
    let disp_off = text_off + m + anchor.disp_at;
    let disp = i32::from_le_bytes(image[disp_off..disp_off + 4].try_into().unwrap());
    let next_rva = text_rva + m as u64 + anchor.disp_at as u64 + 4;
    Ok((next_rva as i64 + disp as i64) as u64)
}

/// Derive a profile from the module image on disk when no measured profile
/// matches its hash: every anchor must match exactly once, and every RVA must
/// lie inside the image. The result is leaked so it can live as long as a
/// measured profile does — one per process lifetime.
pub fn derive_profile(image: &[u8], dll_sha256: &str) -> Result<&'static Profile> {
    let mut rvas = [0u64; 4];
    for (i, anchor) in ANCHORS.iter().enumerate() {
        rvas[i] = resolve_anchor(image, anchor).map_err(|e| Error::Layout {
            what: "tag module signatures",
            detail: format!("{}: {e}", anchor.name),
        })?;
    }
    let storage = rvas[2];
    let profile = Profile {
        label: Box::leak(format!("signature-derived {}", &dll_sha256[..8]).into_boxed_str()),
        dll_sha256: Box::leak(dll_sha256.to_string().into_boxed_str()),
        tag_table_pointer: rvas[0],
        segment_table: rvas[1],
        string_id_storage: storage,
        string_id_used: storage + REGISTRY_USED,
        string_id_strings: storage + REGISTRY_STRINGS,
        string_id_count: storage + REGISTRY_COUNT,
        string_id_map: storage + REGISTRY_MAP,
        string_id_builtin: rvas[3],
    };
    if profile.rvas().iter().any(|rva| *rva >= image.len() as u64 + 0x10000) {
        return Err(Error::Layout {
            what: "tag module signatures",
            detail: "a derived RVA lies past the image".into(),
        });
    }
    Ok(Box::leak(Box::new(profile)))
}

/// The profile for a tag module, by its file hash.
pub fn profile_for(dll_sha256: &str) -> Option<&'static Profile> {
    PROFILES
        .iter()
        .find(|p| p.dll_sha256.eq_ignore_ascii_case(dll_sha256))
}

/// Uppercase hex SHA-256 of a file, streamed — the module is 14 MB.
pub fn sha256_file(path: &std::path::Path) -> std::io::Result<String> {
    use sha2::Digest;
    let mut file = std::fs::File::open(path)?;
    let mut hasher = sha2::Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hasher
        .finalize()
        .iter()
        .map(|b| format!("{b:02X}"))
        .collect())
}

/// Attach to the tag module of a running game: find it, hash it, pick the
/// profile.
pub fn attach(process: &Process) -> Result<Attached> {
    let module = process.module_info(TAG_DLL)?;
    let sha = sha256_file(&module.path).map_err(|source| Error::Read {
        addr: 0,
        len: 0,
        source,
    })?;
    // A measured profile first; otherwise the anchors, read off the module
    // file — the same image the process mapped.
    let profile = match profile_for(&sha) {
        Some(p) => p,
        None => {
            let image = std::fs::read(&module.path).map_err(|source| Error::Read {
                addr: 0,
                len: 0,
                source,
            })?;
            derive_profile(&image, &sha).map_err(|_| Error::UnknownBuild(sha.clone()))?
        }
    };
    if profile.rvas().iter().any(|rva| *rva >= module.size) {
        return Err(Error::Layout {
            what: "tag module",
            detail: format!(
                "a profile RVA lies past the module's {:#x} bytes",
                module.size
            ),
        });
    }
    Ok(Attached {
        base: module.base,
        profile,
    })
}

/// A tag module with a known profile.
#[derive(Debug, Clone, Copy)]
pub struct Attached {
    /// Load base of the tag module.
    pub base: u64,
    pub profile: &'static Profile,
}

impl Profile {
    /// Every RVA the profile carries, in field order.
    pub fn rvas(&self) -> [u64; 8] {
        [
            self.tag_table_pointer,
            self.segment_table,
            self.string_id_storage,
            self.string_id_used,
            self.string_id_strings,
            self.string_id_count,
            self.string_id_map,
            self.string_id_builtin,
        ]
    }
}

/// The sixteen segment bases an encoded offset can point into.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Segments {
    pub bases: [u64; 16],
}

/// An offset the engine stores in place of a pointer: `segment << 28 | words`.
pub const NULL_OFFSET: u32 = u32::MAX;

impl Segments {
    pub fn read(m: &impl Memory, dll_base: u64, profile: &Profile) -> Result<Segments> {
        let b = m.read(dll_base + profile.segment_table, 16 * 8)?;
        let mut bases = [0u64; 16];
        for (i, base) in bases.iter_mut().enumerate() {
            *base = u64::from_le_bytes(b[i * 8..i * 8 + 8].try_into().unwrap());
        }
        Ok(Segments { bases })
    }

    /// Segment index and byte offset of an encoded value, or `None` for the
    /// engine's null.
    pub fn split(enc: u32) -> Option<(usize, u64)> {
        if enc == NULL_OFFSET {
            return None;
        }
        Some(((enc >> 28) as usize, u64::from(enc) * 4))
    }

    /// The address an encoded offset names, or `None` when it is null or its
    /// segment is not mapped.
    pub fn resolve(&self, enc: u32) -> Option<u64> {
        let (segment, offset) = Self::split(enc)?;
        let base = self.bases[segment];
        if base == 0 {
            return None;
        }
        base.checked_add(offset)
    }

    /// The encoded form of an address: the inverse of [`Segments::resolve`].
    ///
    /// The segment nibble is part of the number that gets multiplied, so a
    /// segment's addressable window is `base + 4·(nibble << 28)` upward and
    /// each address encodes in at most one segment — the candidate is checked
    /// by re-resolving it. Returns `None` for an unaligned address or one no
    /// segment covers.
    pub fn encode(&self, addr: u64) -> Option<u32> {
        for (i, base) in self.bases.iter().enumerate() {
            if *base == 0 || addr < *base {
                continue;
            }
            let offset = addr - base;
            if offset % 4 != 0 || offset / 4 > u64::from(u32::MAX) {
                continue;
            }
            let enc = (offset / 4) as u32;
            if (enc >> 28) as usize == i && enc != NULL_OFFSET {
                return Some(enc);
            }
        }
        None
    }

    /// The `arena` value `crate::field_address` expects for a block header
    /// whose offset word is `enc`: the base that makes `arena + 4 * enc` land
    /// on the elements. Because the nibble rides along in the multiplication,
    /// that is the segment base itself — which is what `crate::derive_arena`
    /// has been recovering per tag. Lets the header-walking code stay as it is.
    pub fn arena_for(&self, enc: u32) -> Option<u64> {
        let (segment, _) = Self::split(enc)?;
        let base = self.bases[segment];
        (base != 0).then_some(base)
    }
}

/// A block descriptor as the engine rewrites it: count, then encoded offsets
/// to the elements and to their definition. The root element of a tag is a
/// block of one.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Descriptor {
    pub count: u32,
    pub data: u32,
    pub definition: u32,
}

/// One entry of the table.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LiveTag {
    /// Slot in the table.
    pub index: u32,
    /// The engine's per-slot reuse counter (Blam calls it the salt): a
    /// reloaded tag in the same slot gets a new one, so a stale handle
    /// never resolves.
    pub generation: u16,
    /// Tag group four-CC as the file spells it (`weap`).
    pub group: [u8; 4],
    /// Tag path as the engine spells it: backslashes, no extension,
    /// `objects\weapons\rifle\assault_rifle\assault_rifle`.
    pub name: String,
    /// Where that path's bytes are. A resolved tag reference points here.
    pub name_address: u64,
    pub root: Descriptor,
}

impl LiveTag {
    /// The value a tag reference holds in the resident copy: `generation << 16 | index`.
    pub fn handle(&self) -> u32 {
        (self.generation as u32) << 16 | self.index
    }

    pub fn group_str(&self) -> String {
        self.group
            .iter()
            .map(|c| {
                if c.is_ascii_graphic() {
                    *c as char
                } else {
                    '?'
                }
            })
            .collect()
    }

    /// The sixteen bytes a resolved tag reference to this tag holds.
    ///
    /// The loader rewrites a reference field in place: the group four-CC and
    /// the path length stay as the file spells them, the second word becomes
    /// an encoded offset to the tag's own path string — the very bytes this
    /// entry names — and the last word becomes the handle, where the file
    /// carries `0xFFFFFFFF`. Measured on CU4, `docs/tag_table_and_string_ids.md`.
    ///
    /// `None` when the path string is not in an addressable segment.
    pub fn reference_bytes(&self, segments: &Segments) -> Option<[u8; REFERENCE_SIZE]> {
        let enc = segments.encode(self.name_address)?;
        let mut out = [0u8; REFERENCE_SIZE];
        out[0..4].copy_from_slice(&u32::from_be_bytes(self.group).to_le_bytes());
        out[4..8].copy_from_slice(&enc.to_le_bytes());
        out[8..12].copy_from_slice(&(self.name.len() as u32).to_le_bytes());
        out[12..16].copy_from_slice(&self.handle().to_le_bytes());
        Some(out)
    }

    /// Where the root element's bytes are.
    pub fn root_address(&self, segments: &Segments) -> Option<u64> {
        if self.root.count != 1 {
            return None;
        }
        segments.resolve(self.root.data)
    }
}

/// Layout of the table object, as measured: a 32-byte label, then the array
/// bookkeeping.
const ELEMENT_SIZE: u64 = 0x20;
const MAXIMUM: u64 = 0x2c;
const HIGH_WATER: u64 = 0x44;
const USED: u64 = 0x48;
const ENTRIES: u64 = 0x50;
const BITSET: u64 = 0x58;
const HEADER_LEN: usize = 0x60;
/// Per entry.
const ENTRY_SIZE: usize = 0x30;
const ENTRY_GROUP: usize = 0x04;
const ENTRY_NAME: usize = 0x10;
const ENTRY_ROOT: usize = 0x18;
/// The most tags a table may declare before its layout is disbelieved.
const MAX_TAGS: u32 = 0x1_0000;
/// A tag reference field, inline and resident alike.
pub const REFERENCE_SIZE: usize = 16;
/// Longest tag path read.
const MAX_NAME: usize = 1024;

/// The table object, read once.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TagTable {
    pub address: u64,
    pub maximum: u32,
    pub high_water: u32,
    pub used: u32,
    entries: u64,
    bitset: u64,
}

impl TagTable {
    /// Read the table's header. `Err(NoMission)` when the pointer is null —
    /// the table is only built once a mission is loading.
    pub fn open(m: &impl Memory, dll_base: u64, profile: &Profile) -> Result<TagTable> {
        let address = m.u64(dll_base + profile.tag_table_pointer)?;
        if address == 0 {
            return Err(Error::NoMission);
        }
        let h = m.read(address, HEADER_LEN)?;
        let at32 = |o: u64| u32::from_le_bytes(h[o as usize..o as usize + 4].try_into().unwrap());
        let at64 = |o: u64| u64::from_le_bytes(h[o as usize..o as usize + 8].try_into().unwrap());
        let element_size = at32(ELEMENT_SIZE);
        let maximum = at32(MAXIMUM);
        let high_water = at32(HIGH_WATER);
        let used = at32(USED);
        let entries = at64(ENTRIES);
        let bitset = at64(BITSET);
        if element_size as usize != ENTRY_SIZE
            || maximum > MAX_TAGS
            || high_water > maximum
            || used > high_water
            || entries == 0
            || bitset == 0
        {
            return Err(Error::Layout {
                what: "tag table",
                detail: format!(
                    "element size {element_size:#x}, maximum {maximum}, high water {high_water}, \
                     used {used}, entries {entries:#x}, bitset {bitset:#x}"
                ),
            });
        }
        Ok(TagTable {
            address,
            maximum,
            high_water,
            used,
            entries,
            bitset,
        })
    }

    /// Every live entry, in slot order.
    pub fn walk(&self, m: &impl Memory) -> Result<Vec<LiveTag>> {
        let high = self.high_water as usize;
        if high == 0 {
            return Ok(Vec::new());
        }
        let bits = m.read(self.bitset, high.div_ceil(8))?;
        let blob = m.read(self.entries, high * ENTRY_SIZE)?;
        let mut tags = Vec::with_capacity(self.used as usize);
        for i in 0..high {
            if bits[i / 8] & (1 << (i % 8)) == 0 {
                continue;
            }
            let e = &blob[i * ENTRY_SIZE..(i + 1) * ENTRY_SIZE];
            tags.push(decode_entry(m, i as u32, e)?);
        }
        Ok(tags)
    }

    /// One slot, read fresh. `None` when the slot is free or past the high
    /// water mark.
    ///
    /// A walked table is a photograph: `tag_reload_force` and a level change
    /// both re-slot tags, and a stale handle written into a live reference
    /// would point at whatever took the slot. Re-reading the one entry a
    /// write is about to name costs a single 0x30-byte read.
    pub fn entry(&self, m: &impl Memory, index: u32) -> Result<Option<LiveTag>> {
        if index >= self.high_water {
            return Ok(None);
        }
        let byte = m.read(self.bitset + u64::from(index) / 8, 1)?;
        if byte[0] & (1 << (index % 8)) == 0 {
            return Ok(None);
        }
        let e = m.read(self.entries + u64::from(index) * ENTRY_SIZE as u64, ENTRY_SIZE)?;
        Ok(Some(decode_entry(m, index, &e)?))
    }
}

/// One 0x30-byte entry as a [`LiveTag`].
fn decode_entry(m: &impl Memory, index: u32, e: &[u8]) -> Result<LiveTag> {
    let u32_at = |o: usize| u32::from_le_bytes(e[o..o + 4].try_into().unwrap());
    let name_address = u64::from_le_bytes(e[ENTRY_NAME..ENTRY_NAME + 8].try_into().unwrap());
    let name = if name_address == 0 {
        String::new()
    } else {
        m.cstr(name_address, MAX_NAME)?
    };
    Ok(LiveTag {
        index,
        generation: u16::from_le_bytes(e[0..2].try_into().unwrap()),
        group: u32_at(ENTRY_GROUP).to_be_bytes(),
        name,
        name_address,
        root: Descriptor {
            count: u32_at(ENTRY_ROOT),
            data: u32_at(ENTRY_ROOT + 4),
            definition: u32_at(ENTRY_ROOT + 8),
        },
    })
}

/// The engine's spelling of a tag path: lowercase, backslashes, no leading
/// separator, no `tags/` prefix, no extension.
pub fn normalize_path(path: &str) -> String {
    let mut p = path.trim().replace('/', "\\").to_ascii_lowercase();
    loop {
        if let Some(rest) = p.strip_prefix("..\\") {
            p = rest.to_string();
        } else if let Some(rest) = p.strip_prefix('\\') {
            p = rest.to_string();
        } else {
            break;
        }
    }
    for prefix in [
        "meteorite\\content\\tags\\",
        "content\\tags\\",
        "game\\tags\\",
        "tags\\",
    ] {
        if let Some(rest) = p.strip_prefix(prefix) {
            p = rest.to_string();
        }
    }
    if let Some(dot) = p.rfind('.') {
        if !p[dot..].contains('\\') {
            p.truncate(dot);
        }
    }
    p
}

/// The engine's spelling of the tag a container entry holds:
/// `../../../Meteorite/Content/Tags/objects/weapons/Rifle/assault_rifle/assault_rifle-weapon.ubulk`
/// → `objects\weapons\rifle\assault_rifle\assault_rifle`. The group rides on the
/// leaf after its last hyphen; tag names may contain hyphens, group names do
/// not.
pub fn from_ubulk_path(path: &str) -> String {
    let mut p = normalize_path(path);
    let leaf_start = p.rfind('\\').map(|i| i + 1).unwrap_or(0);
    if let Some(dash) = p[leaf_start..].rfind('-') {
        p.truncate(leaf_start + dash);
    }
    p
}

/// A walked table indexed for lookup by `(group, path)`.
pub struct LiveTags {
    pub tags: Vec<LiveTag>,
    by_key: HashMap<([u8; 4], String), usize>,
}

impl LiveTags {
    pub fn new(tags: Vec<LiveTag>) -> LiveTags {
        let by_key = tags
            .iter()
            .enumerate()
            .map(|(i, t)| ((t.group, t.name.to_ascii_lowercase()), i))
            .collect();
        LiveTags { tags, by_key }
    }

    /// The entry for a tag, given its group four-CC and any spelling of its
    /// path.
    pub fn find(&self, group: [u8; 4], path: &str) -> Option<&LiveTag> {
        self.by_key
            .get(&(group, normalize_path(path)))
            .map(|i| &self.tags[*i])
    }

    /// The entry a handle names, if the generation still matches.
    pub fn by_handle(&self, handle: u32) -> Option<&LiveTag> {
        let index = handle & 0xFFFF;
        self.tags
            .iter()
            .find(|t| t.index == index && t.handle() == handle)
    }

    pub fn len(&self) -> usize {
        self.tags.len()
    }

    pub fn is_empty(&self) -> bool {
        self.tags.is_empty()
    }
}

#[cfg(test)]
pub(crate) mod testing {
    use super::*;
    use std::collections::BTreeMap;

    /// Process memory as a handful of blocks; a read must fall inside one.
    #[derive(Default)]
    pub struct Mock(pub BTreeMap<u64, Vec<u8>>);

    impl Mock {
        pub fn put(&mut self, addr: u64, bytes: &[u8]) {
            self.0.insert(addr, bytes.to_vec());
        }
        pub fn put_u64(&mut self, addr: u64, v: u64) {
            self.put(addr, &v.to_le_bytes());
        }
    }

    impl Memory for Mock {
        fn read(&self, addr: u64, len: usize) -> Result<Vec<u8>> {
            for (base, block) in self.0.range(..=addr).rev() {
                let off = (addr - base) as usize;
                if off + len <= block.len() {
                    return Ok(block[off..off + len].to_vec());
                }
                break;
            }
            Err(Error::Read {
                addr,
                len,
                source: std::io::Error::from(std::io::ErrorKind::InvalidInput),
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::testing::Mock;
    use super::*;

    const DLL: u64 = 0x7FF0_0000_0000;
    const TABLE: u64 = 0x2000_0000;
    const ENTRIES_AT: u64 = 0x2000_1000;
    const BITSET_AT: u64 = 0x2000_0F00;
    const NAMES_AT: u64 = 0x3000_0000;
    const SEG1: u64 = 0x2380_0000_0000;

    fn table_header(high: u32, used: u32) -> Vec<u8> {
        let mut h = vec![0u8; HEADER_LEN];
        h[..12].copy_from_slice(b"tag instance");
        h[0x20..0x24].copy_from_slice(&(ENTRY_SIZE as u32).to_le_bytes());
        h[0x2c..0x30].copy_from_slice(&32767u32.to_le_bytes());
        h[0x44..0x48].copy_from_slice(&high.to_le_bytes());
        h[0x48..0x4c].copy_from_slice(&used.to_le_bytes());
        h[0x50..0x58].copy_from_slice(&ENTRIES_AT.to_le_bytes());
        h[0x58..0x60].copy_from_slice(&BITSET_AT.to_le_bytes());
        h
    }

    fn entry(generation: u16, group: &[u8; 4], name_ptr: u64, data: u32) -> Vec<u8> {
        let mut e = vec![0u8; ENTRY_SIZE];
        e[0..2].copy_from_slice(&generation.to_le_bytes());
        e[4..8].copy_from_slice(&u32::from_be_bytes(*group).to_le_bytes());
        e[0x10..0x18].copy_from_slice(&name_ptr.to_le_bytes());
        e[0x18..0x1c].copy_from_slice(&1u32.to_le_bytes());
        e[0x1c..0x20].copy_from_slice(&data.to_le_bytes());
        e[0x20..0x24].copy_from_slice(&0xE123_4567u32.to_le_bytes());
        e
    }

    fn game() -> Mock {
        let mut m = Mock::default();
        m.put_u64(DLL + CU4.tag_table_pointer, TABLE);
        let mut segs = vec![0u8; 16 * 8];
        segs[8..16].copy_from_slice(&SEG1.to_le_bytes());
        m.put(DLL + CU4.segment_table, &segs);
        m.put(TABLE, &table_header(3, 2));
        // Slots 0 and 2 live, slot 1 free.
        m.put(BITSET_AT, &[0b101]);
        let mut blob = Vec::new();
        blob.extend(entry(0xE174, b"matg", NAMES_AT, 0x1000_0010));
        blob.extend(entry(0, b"xxxx", 0, NULL_OFFSET));
        blob.extend(entry(0xE24A, b"weap", NAMES_AT + 0x20, 0x1000_0020));
        m.put(ENTRIES_AT, &blob);
        let mut names = vec![0u8; 0x80];
        names[..16].copy_from_slice(b"globals\\globals\0");
        let weap = b"objects\\weapons\\rifle\\assault_rifle\\assault_rifle\0";
        names[0x20..0x20 + weap.len()].copy_from_slice(weap);
        m.put(NAMES_AT, &names);
        m
    }

    /// The path of the installed tag module, from `HCE_PAKS`.
    fn installed_tag_dll() -> Option<std::path::PathBuf> {
        let paks = std::env::var("HCE_PAKS").ok()?;
        let path = std::path::Path::new(&paks)
            .parent()?
            .parent()?
            .parent()?
            .join("Binaries")
            .join("Win64")
            .join(TAG_DLL);
        path.exists().then_some(path)
    }

    /// Against the installed game: the four anchors match once each in the
    /// CU4 module and reproduce every measured RVA — the derived profile is
    /// the measured one.
    #[test]
    fn anchors_reproduce_the_measured_profile() {
        let Some(path) = installed_tag_dll() else {
            return;
        };
        let image = std::fs::read(&path).unwrap();
        let sha = sha256_file(&path).unwrap();
        let derived = derive_profile(&image, &sha).unwrap();
        if sha.eq_ignore_ascii_case(CU4.dll_sha256) {
            assert_eq!(derived.rvas(), CU4.rvas());
        } else {
            eprintln!("module {sha} is not CU4; derived {derived:#x?}");
            assert!(derived.rvas().iter().all(|r| *r > 0));
        }
    }

    #[test]
    fn an_anchor_decodes_its_displacement() {
        // A minimal PE with one .text section holding the anchor bytes.
        let mut image = vec![0u8; 0x400 + 64];
        image[0x3C..0x40].copy_from_slice(&0x80u32.to_le_bytes());
        image[0x80..0x84].copy_from_slice(b"PE\0\0");
        image[0x86..0x88].copy_from_slice(&1u16.to_le_bytes()); // one section
        image[0x94..0x96].copy_from_slice(&0u16.to_le_bytes()); // no optional header
        let table = 0x80 + 4 + 20;
        image[table..table + 8].copy_from_slice(b".text\0\0\0");
        image[table + 12..table + 16].copy_from_slice(&0x1000u32.to_le_bytes()); // rva
        image[table + 16..table + 20].copy_from_slice(&64u32.to_le_bytes()); // raw size
        image[table + 20..table + 24].copy_from_slice(&0x400u32.to_le_bytes()); // raw offset
        // `mov [rip+disp], rbx` at text+8, next instruction at text+15; the
        // global at rva 0x2000 => disp = 0x2000 - (0x1000 + 15).
        let code = 0x400 + 8;
        image[code..code + 3].copy_from_slice(&[0x48, 0x89, 0x1D]);
        let disp = (0x2000i64 - (0x1000 + 15)) as i32;
        image[code + 3..code + 7].copy_from_slice(&disp.to_le_bytes());
        image[code + 7..code + 14].copy_from_slice(&[0xC6, 0x43, 0x31, 0x01, 0x48, 0x8B, 0xCB]);
        assert_eq!(resolve_anchor(&image, &ANCHORS[0]).unwrap(), 0x2000);
        // The other anchors are absent: no profile.
        assert!(derive_profile(&image, "0000000000000000").is_err());
    }

    #[test]
    fn split_and_resolve_follow_the_engine_encoding() {
        assert_eq!(Segments::split(0xa123_4567), Some((10, 0x2_848d_159c)));
        assert_eq!(Segments::split(0xebd8_5054), Some((14, 0x3_af61_4150)));
        assert_eq!(Segments::split(NULL_OFFSET), None);
        let mut bases = [0u64; 16];
        bases[14] = 0x7ffb_4000_0000;
        let s = Segments { bases };
        assert_eq!(s.resolve(0xebd8_5054), Some(0x7ffe_ef61_4150));
        assert_eq!(s.resolve(0xa123_4567), None, "segment 10 is not mapped");
        // arena_for makes the old `arena + 4 * words` rule land on the same byte.
        let arena = s.arena_for(0xebd8_5054).unwrap();
        assert_eq!(arena + 4 * 0xebd8_5054u64, 0x7ffe_ef61_4150);
    }

    #[test]
    fn walk_reads_live_slots_and_skips_free_ones() {
        let m = game();
        let table = TagTable::open(&m, DLL, &CU4).unwrap();
        assert_eq!((table.high_water, table.used), (3, 2));
        let tags = table.walk(&m).unwrap();
        assert_eq!(tags.len(), 2);
        assert_eq!(tags[0].group_str(), "matg");
        assert_eq!(tags[0].name, "globals\\globals");
        assert_eq!(tags[0].handle(), 0xE174_0000);
        assert_eq!(tags[1].index, 2);
        assert_eq!(tags[1].handle(), 0xE24A_0002);
        let segs = Segments::read(&m, DLL, &CU4).unwrap();
        assert_eq!(tags[1].root_address(&segs), Some(SEG1 + 0x1000_0020 * 4));
    }

    /// `encode` is `resolve` backwards: the nibble rides along in the
    /// multiplication, so each address belongs to at most one segment, and an
    /// address outside every segment's window has no encoding.
    #[test]
    fn encode_inverts_resolve() {
        let mut bases = [0u64; 16];
        bases[1] = 0x1ffe_51f0_0000;
        bases[14] = 0x7ffb_4000_0000;
        let s = Segments { bases };
        for enc in [0x113e_cb98u32, 0x1000_0000, 0xebd8_5054] {
            let addr = s.resolve(enc).unwrap();
            assert_eq!(s.encode(addr), Some(enc), "{enc:#x}");
        }
        // Below segment 1's window (the nibble puts it a gigabyte up) and
        // unaligned addresses have no encoding.
        assert_eq!(s.encode(bases[1]), None);
        assert_eq!(s.encode(s.resolve(0x113e_cb98).unwrap() + 1), None);
        assert_eq!(s.encode(0), None);
    }

    /// The resident form of a reference: group and length as the file spells
    /// them, an encoded offset to the tag's own path, and the handle.
    #[test]
    fn a_reference_resolves_to_the_engine_sixteen_bytes() {
        let m = game();
        let segs = Segments::read(&m, DLL, &CU4).unwrap();
        let tags = LiveTags::new(TagTable::open(&m, DLL, &CU4).unwrap().walk(&m).unwrap());
        let weap = tags.find(*b"weap", "objects/weapons/rifle/assault_rifle/assault_rifle").unwrap();
        // The mock's names sit outside any segment window, so encoding fails
        // rather than inventing an offset.
        assert_eq!(weap.reference_bytes(&segs), None);

        // Put the path inside segment 1 and it encodes.
        let mut m = game();
        let name_at = SEG1 + 0x1000_0000 * 4;
        let mut names = vec![0u8; 0x80];
        let path = b"objects\\weapons\\rifle\\assault_rifle\\assault_rifle";
        names[..path.len()].copy_from_slice(path);
        m.put(name_at, &names);
        let mut e = entry(0xE24A, b"weap", name_at, 0x1000_0020);
        e[0..2].copy_from_slice(&0xE24Au16.to_le_bytes());
        let mut blob = Vec::new();
        blob.extend(entry(0xE174, b"matg", NAMES_AT, 0x1000_0010));
        blob.extend(entry(0, b"xxxx", 0, NULL_OFFSET));
        blob.extend(e);
        m.put(ENTRIES_AT, &blob);
        let table = TagTable::open(&m, DLL, &CU4).unwrap();
        let tags = LiveTags::new(table.walk(&m).unwrap());
        let weap = tags.find(*b"weap", "objects\\weapons\\rifle\\assault_rifle\\assault_rifle").unwrap();
        let bytes = weap.reference_bytes(&segs).unwrap();
        assert_eq!(&bytes[0..4], b"paew", "the four-CC is stored reversed");
        assert_eq!(u32::from_le_bytes(bytes[4..8].try_into().unwrap()), 0x1000_0000);
        assert_eq!(u32::from_le_bytes(bytes[8..12].try_into().unwrap()), 49);
        assert_eq!(u32::from_le_bytes(bytes[12..16].try_into().unwrap()), 0xE24A_0002);

        // One slot, read fresh, says the same thing; a free slot says nothing.
        let fresh = table.entry(&m, 2).unwrap().unwrap();
        assert_eq!(fresh.reference_bytes(&segs), Some(bytes));
        assert!(table.entry(&m, 1).unwrap().is_none());
        assert!(table.entry(&m, 99).unwrap().is_none());
    }

    #[test]
    fn lookup_accepts_every_spelling_of_a_path() {
        let m = game();
        let tags = LiveTags::new(TagTable::open(&m, DLL, &CU4).unwrap().walk(&m).unwrap());
        for spelling in [
            "objects\\weapons\\rifle\\assault_rifle\\assault_rifle",
            "objects/weapons/rifle/assault_rifle/assault_rifle.weapon",
            "/Game/Tags/Objects/Weapons/Rifle/Assault_Rifle/assault_rifle.weapon",
            "tags\\objects\\weapons\\rifle\\assault_rifle\\assault_rifle",
        ] {
            let t = tags
                .find(*b"weap", spelling)
                .unwrap_or_else(|| panic!("{spelling}"));
            assert_eq!(t.index, 2);
        }
        assert!(tags
            .find(
                *b"bipd",
                "objects\\weapons\\rifle\\assault_rifle\\assault_rifle"
            )
            .is_none());
        assert_eq!(tags.by_handle(0xE24A_0002).map(|t| t.index), Some(2));
        assert!(
            tags.by_handle(0xE24B_0002).is_none(),
            "a stale generation is not the same tag"
        );
    }

    #[test]
    fn container_paths_become_engine_paths() {
        assert_eq!(
            from_ubulk_path(
                "../../../Meteorite/Content/Tags/objects/weapons/Rifle/assault_rifle/assault_rifle-weapon.ubulk"
            ),
            "objects\\weapons\\rifle\\assault_rifle\\assault_rifle"
        );
        assert_eq!(
            from_ubulk_path("Meteorite/Content/Tags/sound/x/FOL_MC-Gear-sound.ubulk"),
            "sound\\x\\fol_mc-gear",
            "only the last hyphen is the group separator"
        );
    }

    #[test]
    fn an_empty_pointer_means_no_mission() {
        let mut m = game();
        m.put_u64(DLL + CU4.tag_table_pointer, 0);
        assert!(matches!(
            TagTable::open(&m, DLL, &CU4),
            Err(Error::NoMission)
        ));
    }

    #[test]
    fn a_foreign_layout_is_refused() {
        let mut m = game();
        let mut h = table_header(3, 2);
        h[0x20..0x24].copy_from_slice(&0x40u32.to_le_bytes());
        m.put(TABLE, &h);
        assert!(matches!(
            TagTable::open(&m, DLL, &CU4),
            Err(Error::Layout {
                what: "tag table",
                ..
            })
        ));
    }

    #[test]
    fn profiles_are_unique_and_upper_hex() {
        for p in PROFILES {
            assert_eq!(p.dll_sha256.len(), 64);
            assert!(p
                .dll_sha256
                .chars()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_lowercase()));
        }
        let mut seen = std::collections::HashSet::new();
        assert!(PROFILES.iter().all(|p| seen.insert(p.dll_sha256)));
        assert!(profile_for(&CU4.dll_sha256.to_ascii_lowercase()).is_some());
        assert!(profile_for("00").is_none());
    }
}
