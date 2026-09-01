//! Reading UE's live object table (`GUObjectArray`) from the running game.
//!
//! Every `UObject` the engine has created is registered in one global array.
//! Reaching it turns "what is loaded right now" from a memory sweep into a
//! bounded read: resolve the array's address once per build, then walk it.
//!
//! Two globals are in play, both found the way UE4SS finds them — an
//! array-of-bytes match against the game's code, with the RIP-relative
//! displacement decoded at runtime rather than baked in (a baked displacement
//! rots at the next update; see `signatures/README.md`). This module resolves
//! `GUObjectArray` itself; turning an object's `FName` into text needs the name
//! pool, which is a second, harder global handled in [`names`].
//!
//! Layout is UE 5.5 (`5.5.4`, verified against the shipped build). The offsets
//! below are that ABI; a major engine bump is the thing most likely to move
//! them, which is why each is named and commented rather than a magic number.

use crate::{Process, Result};

/// The store into `GUObjectArray` that UE4SS keys on, from
/// `signatures/GUObjectArray.lua`. The `LEA` at `match + 0xB` loads the array's
/// address RIP-relative; [`resolve`] decodes it.
pub const GUOBJECTARRAY_SIG: &str =
    "45 84 C0 48 C7 41 10 00 00 00 00 48 8D 05 ? ? ? ? 4C 8B C9 48 89 01 B8 FF FF FF FF 89 41 08";

// --- UE 5.5 ABI offsets ------------------------------------------------------

/// `FUObjectArray::ObjObjects` — the chunked array sits past three int32s and a
/// padded bool.
const OBJOBJECTS: u64 = 0x10;
/// `FChunkedFixedUObjectArray::Objects` — pointer to the array of chunk base
/// pointers.
const CHUNKS_PTR: u64 = 0x00;
/// `FChunkedFixedUObjectArray::NumElements`.
const NUM_ELEMENTS: u64 = 0x14;
/// Objects per chunk. UE allocates `FUObjectItem`s in fixed 64K-element chunks.
const ELEMENTS_PER_CHUNK: u64 = 64 * 1024;
/// `sizeof(FUObjectItem)` — `{ UObject* Object; int32 Flags, ClusterRootIndex,
/// SerialNumber; }`, padded to 24.
const ITEM_SIZE: u64 = 0x18;
/// `UObjectBase::ClassPrivate`.
const CLASS: u64 = 0x10;
/// `UObjectBase::NamePrivate` (an `FName`: two int32s, comparison index then
/// number).
const NAME: u64 = 0x18;
/// `UObjectBase::OuterPrivate`.
const OUTER: u64 = 0x20;

/// One live object, as read straight from the table — addresses and `FName`
/// indices, before any name resolution.
#[derive(Debug, Clone, Copy)]
pub struct RawObject {
    pub index: u32,
    /// Address of the `UObjectBase`.
    pub object: u64,
    /// `ClassPrivate` — shared by every instance of a class, so it groups
    /// objects by type without resolving a single name.
    pub class: u64,
    /// `OuterPrivate` — the package/owner, for walking to the package name.
    pub outer: u64,
    /// `NamePrivate.ComparisonIndex`, an `FNameEntryId` into the name pool.
    pub name_id: u32,
    /// `NamePrivate.Number` — 0 means the bare name, N means `name_N-1`.
    pub name_number: u32,
}

/// Minimal little-endian readers over process memory.
fn read_u32(p: &Process, addr: u64) -> Result<u32> {
    let b = p.read(addr, 4)?;
    Ok(u32::from_le_bytes(b[..4].try_into().unwrap()))
}
fn read_u64(p: &Process, addr: u64) -> Result<u64> {
    let b = p.read(addr, 8)?;
    Ok(u64::from_le_bytes(b[..8].try_into().unwrap()))
}

/// Resolve `GUObjectArray`'s runtime address from the game image on disk plus
/// the module's load base.
///
/// The signature matches once in `.text`; the `LEA` it points at carries a
/// RIP-relative displacement to the array. Decoding that gives an RVA, which
/// is an address once the ASLR load base is added.
pub fn resolve(exe: &[u8], module_base: u64) -> Result<u64> {
    let (text_rva, text_off, code) = text_section(exe)?;
    let m = find_unique(code, GUOBJECTARRAY_SIG)?;
    // OnMatchFound: LEA at +0xB, disp32 at LEA+3, next instruction at LEA+7.
    let lea = m + 0xB;
    let disp_at = text_off + lea + 3;
    let disp = i32::from_le_bytes(exe[disp_at..disp_at + 4].try_into().unwrap());
    let next_rva = text_rva + (lea as u64) + 7;
    let target_rva = (next_rva as i64 + disp as i64) as u64;
    Ok(module_base + target_rva)
}

/// The virtual address a signature matches at (the function start, for
/// signatures whose `OnMatchFound` returns the match unchanged).
pub fn match_va(exe: &[u8], module_base: u64, sig: &str) -> Result<u64> {
    let (text_rva, _, code) = text_section(exe)?;
    let m = find_unique(code, sig)?;
    Ok(module_base + text_rva + m as u64)
}

/// The array's base item-store and element count, read once.
#[derive(Debug, Clone, Copy)]
pub struct ObjectTable {
    /// Address of the chunk-pointer array (`Objects`).
    chunks: u64,
    pub num_elements: u32,
}

impl ObjectTable {
    /// Read the chunked-array header at a resolved `GUObjectArray` address.
    pub fn open(p: &Process, guobjectarray: u64) -> Result<ObjectTable> {
        let cfoa = guobjectarray + OBJOBJECTS;
        Ok(ObjectTable {
            chunks: read_u64(p, cfoa + CHUNKS_PTR)?,
            num_elements: read_u32(p, cfoa + NUM_ELEMENTS)?,
        })
    }

    /// Walk every live object, reading its class, outer and name `FName`.
    ///
    /// Reads chunk by chunk — one `read` per 64K-item chunk rather than per
    /// object — so the whole table is a few hundred reads, not a sweep. Null
    /// slots (destroyed objects) are skipped.
    pub fn walk(&self, p: &Process) -> Result<Vec<RawObject>> {
        let mut out = Vec::with_capacity(self.num_elements as usize);
        let total = self.num_elements as u64;
        let mut index = 0u64;
        while index < total {
            let chunk = index / ELEMENTS_PER_CHUNK;
            let chunk_ptr = read_u64(p, self.chunks + chunk * 8)?;
            if chunk_ptr == 0 {
                index = (chunk + 1) * ELEMENTS_PER_CHUNK;
                continue;
            }
            let count = (total - index).min(ELEMENTS_PER_CHUNK - index % ELEMENTS_PER_CHUNK);
            let start = index % ELEMENTS_PER_CHUNK;
            let buf = p.read(chunk_ptr + start * ITEM_SIZE, (count * ITEM_SIZE) as usize)?;
            for k in 0..count {
                let item = (k * ITEM_SIZE) as usize;
                if item + 8 > buf.len() {
                    break;
                }
                let object = u64::from_le_bytes(buf[item..item + 8].try_into().unwrap());
                if object == 0 {
                    continue;
                }
                // One read per surviving object for its header fields. The
                // class/name/outer sit within the first 0x28 bytes.
                let Ok(hdr) = p.read(object, 0x28) else {
                    continue;
                };
                if hdr.len() < 0x28 {
                    continue;
                }
                let rd64 = |o: u64| u64::from_le_bytes(hdr[o as usize..o as usize + 8].try_into().unwrap());
                let rd32 = |o: u64| u32::from_le_bytes(hdr[o as usize..o as usize + 4].try_into().unwrap());
                out.push(RawObject {
                    index: (index + k) as u32,
                    object,
                    class: rd64(CLASS),
                    outer: rd64(OUTER),
                    name_id: rd32(NAME),
                    name_number: rd32(NAME + 4),
                });
            }
            index += count;
        }
        Ok(out)
    }
}

/// Everything needed to read live object identities: the object table and the
/// name pool, both resolved from signatures. Cheap to hold; borrows nothing.
#[derive(Debug, Clone, Copy)]
pub struct Reader {
    pub module_base: u64,
    pub table: ObjectTable,
    pub pool: crate::names::NamePool,
}

impl Reader {
    /// Resolve `GUObjectArray` and the name pool from the game image.
    ///
    /// `exe` is the game executable's bytes on disk (for the static AOB scans);
    /// the addresses land in the running process via its module base. The pool
    /// bootstraps from `FName` id 0, which is `"None"` in every UE build — so
    /// this needs no prior knowledge of any name.
    pub fn attach(p: &Process, exe: &[u8]) -> Result<Reader> {
        let (module_base, _) = p.module(crate::GAME_EXE)?;
        let guobj = resolve(exe, module_base)?;
        let table = ObjectTable::open(p, guobj)?;
        let ctor = match_va(exe, module_base, crate::names::FNAME_CONSTRUCTOR_SIG)?;
        let pool = crate::names::find_pool(p, ctor, 0, "None")?;
        Ok(Reader {
            module_base,
            table,
            pool,
        })
    }

    /// The `FName` text of any object address (its `NamePrivate`).
    pub fn name_at(&self, p: &Process, object: u64) -> Result<String> {
        let id = read_u32(p, object + NAME)?;
        self.pool.text(p, id)
    }

    /// An object's own name and its outer's (package's) name. The package name
    /// is the full cooked path, e.g. `/Game/Tags/objects/.../engineer-biped`.
    pub fn identity(&self, p: &Process, o: &RawObject) -> Result<(String, String)> {
        let name = self.pool.text(p, o.name_id)?;
        let outer = if o.outer != 0 {
            self.name_at(p, o.outer).unwrap_or_default()
        } else {
            String::new()
        };
        Ok((name, outer))
    }
}

// --- PE parsing (minimal, enough to scan .text) ------------------------------

/// `(text RVA, text file offset, text bytes)` for AOB scanning.
fn text_section(exe: &[u8]) -> Result<(u64, usize, &[u8])> {
    let bad = || crate::Error::TooSmall(exe.len());
    let e_lfanew = u32::from_le_bytes(exe.get(0x3C..0x40).ok_or_else(bad)?.try_into().unwrap()) as usize;
    if exe.get(e_lfanew..e_lfanew + 4) != Some(b"PE\0\0") {
        return Err(bad());
    }
    let coff = e_lfanew + 4;
    let n_sections = u16::from_le_bytes(exe[coff + 2..coff + 4].try_into().unwrap()) as usize;
    let opt_size = u16::from_le_bytes(exe[coff + 16..coff + 18].try_into().unwrap()) as usize;
    let table = coff + 20 + opt_size;
    for i in 0..n_sections {
        let o = table + i * 40;
        let name = &exe[o..o + 8];
        if name.starts_with(b".text\0") {
            let vaddr = u32::from_le_bytes(exe[o + 12..o + 16].try_into().unwrap()) as u64;
            let rsize = u32::from_le_bytes(exe[o + 16..o + 20].try_into().unwrap()) as usize;
            let raddr = u32::from_le_bytes(exe[o + 20..o + 24].try_into().unwrap()) as usize;
            return Ok((vaddr, raddr, &exe[raddr..raddr + rsize]));
        }
    }
    Err(bad())
}

/// Find the one offset in `code` matching an AOB like `"48 8D ? ? C3"`, where
/// `?` is a wildcard byte. Errors if the pattern matches zero or many places —
/// the only count UE4SS resolves deterministically.
fn find_unique(code: &[u8], sig: &str) -> Result<usize> {
    let pat: Vec<Option<u8>> = sig
        .split_whitespace()
        .map(|t| if t.contains('?') { None } else { u8::from_str_radix(t, 16).ok() })
        .collect();
    let n = pat.len();
    let mut hit = None;
    let mut count = 0usize;
    for start in 0..=code.len().saturating_sub(n) {
        if pat
            .iter()
            .enumerate()
            .all(|(j, b)| b.is_none_or(|want| code[start + j] == want))
        {
            count += 1;
            if hit.is_none() {
                hit = Some(start);
            }
            if count > 1 {
                break;
            }
        }
    }
    match (hit, count) {
        (Some(m), 1) => Ok(m),
        _ => Err(crate::Error::Unverified {
            candidates: count,
            best: count as f32,
            need: 1.0,
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn aob_matches_exactly_one_place() {
        let mut code = vec![0u8; 256];
        code[100..104].copy_from_slice(&[0x48, 0x8d, 0x05, 0xAA]);
        assert_eq!(find_unique(&code, "48 8D 05 ?").unwrap(), 100);
    }

    #[test]
    fn aob_rejects_zero_and_many() {
        let code = vec![0x90u8; 64];
        assert!(find_unique(&code, "48 8D 05").is_err());
        assert!(find_unique(&code, "90 90").is_err());
    }

    /// Resolve and walk GUObjectArray in the running game, grouping objects by
    /// class pointer. Verifies the resolution and the UE 5.5 offsets without
    /// needing name resolution: a healthy table has hundreds of thousands of
    /// elements, and the biggest class groups should be recognisable engine
    /// types. Env: `MJOLNIR_EXE` (path to the game exe).
    ///
    /// Ignored by default; needs the game running. Run with
    /// `--ignored --nocapture`.
    #[test]
    #[ignore = "needs the game running; set MJOLNIR_EXE"]
    fn walk_live_object_table() {
        use std::collections::HashMap;

        let exe_path = std::env::var("MJOLNIR_EXE").expect("set MJOLNIR_EXE");
        let exe = std::fs::read(&exe_path).expect("read exe");
        let process = Process::attach().expect("game running");
        let (base, size) = process.module(crate::GAME_EXE).expect("module base");
        eprintln!("module {} at {base:#x} ({} MiB)", crate::GAME_EXE, size >> 20);

        let guobj = resolve(&exe, base).expect("resolve GUObjectArray");
        eprintln!("GUObjectArray at {guobj:#x} (rva {:#x})", guobj - base);

        let table = ObjectTable::open(&process, guobj).expect("open table");
        eprintln!("num_elements = {}", table.num_elements);
        assert!(
            (10_000..5_000_000).contains(&table.num_elements),
            "element count {} is not a sane object table — offsets are probably wrong",
            table.num_elements
        );

        let objects = table.walk(&process).expect("walk");
        eprintln!("walked {} live objects", objects.len());
        assert!(objects.len() > 1000, "too few live objects");

        // Group by class pointer; the class is itself a UObject whose own name
        // we cannot resolve yet, but the counts prove the walk is coherent.
        let mut by_class: HashMap<u64, usize> = HashMap::new();
        for o in &objects {
            *by_class.entry(o.class).or_default() += 1;
        }
        let mut ranked: Vec<(u64, usize)> = by_class.into_iter().collect();
        ranked.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        eprintln!("{} distinct classes; top 10 by instance count:", ranked.len());
        for (cls, n) in ranked.iter().take(10) {
            eprintln!("  class {cls:#x}: {n} instances");
        }

        // End to end via Reader: the "None"@0 bootstrap (no oracle), then
        // list loaded tag assets by class-name suffix, with package paths.
        let exe2 = std::fs::read(&exe_path).unwrap();
        let reader = Reader::attach(&process, &exe2).expect("reader attaches");
        eprintln!(
            "pool bootstrapped from None@0; FNamePool rva {:#x}",
            reader.pool.base - base
        );

        // Resolve each distinct class name once (cache), keep *TagDataAsset.
        let mut class_name: HashMap<u64, String> = HashMap::new();
        for o in &objects {
            class_name.entry(o.class).or_insert_with(|| {
                reader.name_at(&process, o.class).unwrap_or_default()
            });
        }
        let tag_classes: std::collections::HashSet<u64> = class_name
            .iter()
            .filter(|(_, n)| n.ends_with("TagDataAsset"))
            .map(|(c, _)| *c)
            .collect();
        eprintln!("{} tag-asset classes among {} classes", tag_classes.len(), class_name.len());

        let mut all_tag_objs = 0usize;
        let mut game_tags = 0usize;
        let mut cdo = 0usize;
        let mut shown = 0usize;
        for o in &objects {
            if !tag_classes.contains(&o.class) {
                continue;
            }
            all_tag_objs += 1;
            let (name, pkg) = reader.identity(&process, o).unwrap_or_default();
            if name.starts_with("Default__") {
                cdo += 1;
                continue;
            }
            // Real cooked tags live under /Game/Tags/. Anything else is a CDO,
            // an archetype, or an engine-script object of the same class.
            if pkg.starts_with("/Game/Tags/") {
                game_tags += 1;
                if shown < 10 {
                    eprintln!("  {} :: {name}  pkg {pkg}", class_name[&o.class]);
                    shown += 1;
                }
            }
        }
        eprintln!(
            "tag-asset objects: {all_tag_objs} total, {cdo} CDOs, {game_tags} under /Game/Tags/"
        );
        eprintln!("(census found 369 with resident data — compare)");

        // Cross-check hook: if MJOLNIR_KNOWN_OBJ is set to a UObject address
        // (from the game bridge), report its class and how many peers share it.
        if let Ok(known) = std::env::var("MJOLNIR_KNOWN_OBJ") {
            let addr = u64::from_str_radix(known.trim_start_matches("0x"), 16).unwrap();
            let hit = objects.iter().find(|o| o.object == addr);
            match hit {
                Some(o) => {
                    let peers = objects.iter().filter(|x| x.class == o.class).count();
                    eprintln!(
                        "known object {addr:#x}: found in table (index {}), class {:#x}, {peers} peers, name_id {} num {}",
                        o.index, o.class, o.name_id, o.name_number
                    );
                }
                None => eprintln!("known object {addr:#x}: NOT found in the walked table"),
            }
        }
    }
}
