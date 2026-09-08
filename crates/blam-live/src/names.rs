//! Resolving an object's `FName` to text.
//!
//! Walking [`crate::objects`] gives every object's name as an `FNameEntryId` —
//! an index into UE's global name pool, not a string. Turning it into text
//! needs the pool's base address, which (unlike `GUObjectArray`) UE4SS ships no
//! signature for; it resolves names by calling into the engine, which an
//! external reader cannot do.
//!
//! So the base is found from the one function we *can* locate — the `FName`
//! constructor — by decoding the RIP-relative references in its first
//! instructions and testing each against a name whose text is already known.
//! A candidate that resolves that id back to its expected string is the pool.
//! No memory sweep, and self-validating: a wrong guess simply fails the check.
//!
//! Pool layout is UE 5.5's block allocator (`FNameEntryId` = `block << 16 |
//! offset`; entries live at `Blocks[block] + offset * 2`).

use crate::{Error, Process, Result};

/// `FName::FName`, from `signatures/FName_Constructor.lua`. Its opening
/// instructions reference the pool.
pub const FNAME_CONSTRUCTOR_SIG: &str = "48 89 5C 24 08 57 48 83 EC 30 41 8B F8 48 89 54 24 20 45 33 C0 48 8B D9 4C 8B CA 41 8B C8 48 85 D2 74 1E 0F B7 02";

/// Bits of an `FNameEntryId` that are the offset within a block.
const BLOCK_OFFSET_BITS: u32 = 16;
/// Bytes per offset unit — entries are 2-byte aligned.
const STRIDE: u64 = 2;
/// `FNamePool::Entries.Blocks` — past the lock and the two cursor int32s.
const BLOCKS: u64 = 0x10;

fn read_u16(p: &Process, addr: u64) -> Result<u16> {
    let b = p.read(addr, 2)?;
    Ok(u16::from_le_bytes(b[..2].try_into().unwrap()))
}
fn read_u64(p: &Process, addr: u64) -> Result<u64> {
    let b = p.read(addr, 8)?;
    Ok(u64::from_le_bytes(b[..8].try_into().unwrap()))
}

/// The name pool, once its base is known. Cheap to copy; holds no memory.
#[derive(Debug, Clone, Copy)]
pub struct NamePool {
    /// Address of the `FNamePool` global (`NamePoolData`).
    pub base: u64,
}

impl NamePool {
    /// Address of the `FNameEntry` an id points at.
    fn entry(&self, p: &Process, id: u32) -> Result<u64> {
        let block = (id >> BLOCK_OFFSET_BITS) as u64;
        let offset = (id & ((1 << BLOCK_OFFSET_BITS) - 1)) as u64;
        let block_base = read_u64(p, self.base + BLOCKS + block * 8)?;
        if block_base == 0 {
            return Err(Error::NotFound);
        }
        Ok(block_base + offset * STRIDE)
    }

    /// Read the text of a name id. `Number` (the trailing `_N` UE appends) is
    /// the caller's to apply; this returns the bare entry text.
    ///
    /// Header layout is `{ bIsWide:1; LowercaseProbeHash:5; Len:10 }` — the
    /// UE 5.5 non-case-preserving form, confirmed against known names in
    /// [`tests::discover_name_pool`]. Wide (UTF-16) entries are rare for tag
    /// names; they are read as lossy UTF-16 for completeness.
    pub fn text(&self, p: &Process, id: u32) -> Result<String> {
        let entry = self.entry(p, id)?;
        let header = read_u16(p, entry)?;
        let is_wide = header & 1 != 0;
        let len = (header >> 6) as usize;
        if len == 0 || len > 1024 {
            return Err(Error::NotFound);
        }
        if is_wide {
            let bytes = p.read(entry + 2, len * 2)?;
            let units: Vec<u16> = bytes
                .chunks_exact(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .collect();
            Ok(String::from_utf16_lossy(&units))
        } else {
            let bytes = p.read(entry + 2, len)?;
            Ok(String::from_utf8_lossy(&bytes).into_owned())
        }
    }

    /// Confirm a candidate base actually decodes a known `(id, text)` pair —
    /// the test that turns a guessed pointer into the pool.
    fn validates(&self, p: &Process, id: u32, expect: &str) -> bool {
        matches!(self.text(p, id), Ok(t) if t == expect)
    }
}

/// Find the name pool by decoding RIP-relative references out of the `FName`
/// constructor and testing each against a known `(id, text)` pair.
///
/// `constructor` is the function's runtime address ([`crate::objects::match_va`]
/// on [`FNAME_CONSTRUCTOR_SIG`]). Returns the validated [`NamePool`].
pub fn find_pool(
    p: &Process,
    constructor: u64,
    known_id: u32,
    known_text: &str,
) -> Result<NamePool> {
    // The pool reference is a RIP-relative `lea`/`mov` — but often not in the
    // constructor itself; it computes the string length and then *calls* the
    // worker (or `GetNamePool`, a one-line `lea rax,[NamePoolData]; ret`) that
    // touches the pool. So collect RIP-relative targets from the constructor
    // *and* from the first instructions of every function it calls (one level).
    let mut candidates: Vec<u64> = Vec::new();
    let mut scan_at = vec![constructor];
    if let Ok(code) = p.read(constructor, 0x200) {
        for callee in call_targets(&code, constructor) {
            scan_at.push(callee);
        }
    }
    for func in scan_at {
        if let Ok(code) = p.read(func, 0x120) {
            candidates.extend(rip_targets(&code, func));
        }
    }

    for &c in &candidates {
        // The reference may be the pool itself, or a pointer to it.
        let direct = NamePool { base: c };
        if direct.validates(p, known_id, known_text) {
            return Ok(direct);
        }
        if let Ok(inner) = read_u64(p, c) {
            let indirect = NamePool { base: inner };
            if indirect.validates(p, known_id, known_text) {
                return Ok(indirect);
            }
        }
    }
    Err(Error::NotFound)
}

/// RIP-relative `lea`/`mov r64,[rip+disp32]` targets decoded from a code
/// window that starts at `origin`. REX.W (0x48/0x4C), opcode 0x8D/0x8B, modrm
/// mod=00 rm=101 (bytes 0x05/0x0D/…/0x3D).
fn rip_targets(code: &[u8], origin: u64) -> Vec<u64> {
    const MODRM_RIP: [u8; 8] = [0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D];
    let mut out = Vec::new();
    let mut i = 0usize;
    while i + 7 <= code.len() {
        if (code[i] == 0x48 || code[i] == 0x4C)
            && (code[i + 1] == 0x8D || code[i + 1] == 0x8B)
            && MODRM_RIP.contains(&code[i + 2])
        {
            let disp = i32::from_le_bytes(code[i + 3..i + 7].try_into().unwrap());
            let next = origin + i as u64 + 7;
            out.push((next as i64 + disp as i64) as u64);
            i += 7;
        } else {
            i += 1;
        }
    }
    out
}

/// `call rel32` (0xE8) targets decoded from a code window at `origin`.
fn call_targets(code: &[u8], origin: u64) -> Vec<u64> {
    let mut out = Vec::new();
    let mut i = 0usize;
    while i + 5 <= code.len() {
        if code[i] == 0xE8 {
            let rel = i32::from_le_bytes(code[i + 1..i + 5].try_into().unwrap());
            let next = origin + i as u64 + 5;
            out.push((next as i64 + rel as i64) as u64);
        }
        i += 1;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::objects;

    /// Find the name pool in the running game and read real names through it.
    /// Bootstraps from one bridge-supplied `(id, text)` pair, then resolves a
    /// batch of `(object addr -> name)` pairs end to end.
    ///
    /// Env: `MJOLNIR_EXE` (game exe), `MJOLNIR_NAMES` (`<hex addr>\t<name>`
    /// lines from the bridge). Ignored; needs the game running.
    #[test]
    #[ignore = "needs the game running; set MJOLNIR_EXE, MJOLNIR_NAMES"]
    fn discover_name_pool() {
        let exe = std::fs::read(std::env::var("MJOLNIR_EXE").expect("set MJOLNIR_EXE")).unwrap();
        let names_txt =
            std::fs::read_to_string(std::env::var("MJOLNIR_NAMES").expect("set MJOLNIR_NAMES"))
                .unwrap();

        let p = Process::attach().expect("game running");
        let (base, _) = p.module(crate::GAME_EXE).expect("module base");
        let guobj = objects::resolve(&exe, base).expect("resolve GUObjectArray");
        let table = objects::ObjectTable::open(&p, guobj).expect("open");
        let walked = table.walk(&p).expect("walk");

        // addr -> name_id, from the walk.
        let mut id_of: std::collections::HashMap<u64, u32> = std::collections::HashMap::new();
        for o in &walked {
            id_of.insert(o.object, o.name_id);
        }
        // (addr, name) from the bridge; join to (id, name).
        let mut pairs: Vec<(u64, u32, String)> = Vec::new();
        for line in names_txt.lines() {
            let Some((a, nm)) = line.split_once('\t') else { continue };
            let Ok(addr) = u64::from_str_radix(a.trim(), 16) else { continue };
            if let Some(&id) = id_of.get(&addr) {
                pairs.push((addr, id, nm.trim().to_string()));
            }
        }
        assert!(!pairs.is_empty(), "no bridge names joined to walked objects");
        eprintln!("{} (id,name) pairs joined", pairs.len());

        let ctor = objects::match_va(&exe, base, FNAME_CONSTRUCTOR_SIG).expect("FName ctor");
        eprintln!("FName::FName at {ctor:#x} (rva {:#x})", ctor - base);

        // Bootstrap from the first pair; the object name UE stores is the leaf
        // before any "-group", but GetFullName's last segment is the whole
        // object name — use it verbatim.
        let (_, id0, ref name0) = pairs[0];
        eprintln!("bootstrapping from id {id0} = {name0:?}");
        let pool = find_pool(&p, ctor, id0, name0).expect("find name pool");
        eprintln!("FNamePool at {:#x} (rva {:#x})", pool.base, pool.base - base);

        // Now resolve the whole batch and check against the bridge.
        let mut ok = 0usize;
        let mut bad = 0usize;
        for (_, id, expect) in &pairs {
            match pool.text(&p, *id) {
                Ok(t) if &t == expect => ok += 1,
                Ok(t) => {
                    if bad < 10 {
                        eprintln!("  MISMATCH id {id}: got {t:?} expected {expect:?}");
                    }
                    bad += 1;
                }
                Err(e) => {
                    if bad < 10 {
                        eprintln!("  ERR id {id}: {e}");
                    }
                    bad += 1;
                }
            }
        }
        eprintln!("resolved {ok}/{} names correctly ({bad} wrong)", pairs.len());
        assert!(ok * 10 >= pairs.len() * 9, "fewer than 90% of names resolved");
    }
}
