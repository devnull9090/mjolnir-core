//! The engine's asset cache: a static-rooted, `FPackageId`-keyed map from a
//! loaded package to its live data buffer.
//!
//! This is the scan-free route to a tag's bytes. Reverse-engineered against
//! the shipped build and recorded in `docs/live_tag_locating.md`:
//!
//! ```text
//! .data global  ->  root struct T  ->  80-byte map records from T+0x40
//!   -> record head (+0x48) targets a node; window W = target - 0x10
//!   -> links at W+0x00 / W+0x10 target further nodes
//!   -> key hash at W+0x20 == FPackageId(package)
//!   -> flag at W+0x78 == 1 marks the chunk holding the live buffer
//!   -> descriptor at W+0x70: { ptr = payload base; u32; u32 = 1; u64 = 0; 00 01 }
//! ```
//!
//! A link targets an address 0x10 *into* the node struct (the embedded
//! link field, as intrusive lists do), so the node's window is read from
//! `link_target - 0x10`; the offsets above are within that window. The
//! descriptor slot the older probes were addressed by is `link_target + 0x60`.
//!
//! What it is and is not: the lookup is exact (every hit it returned agreed
//! with the byte-fingerprint census, none disagreed), but the map belongs to
//! the loader: it references a buffer while loading and lets go afterwards,
//! so in a settled mission it covers a fraction of the resident tags (37 of
//! 362 measured). It makes those instant and, during and just after a load,
//! likely many more; the census sweep remains the fallback for the rest.

use std::collections::{HashMap, HashSet, VecDeque};

use crate::{Process, Result};

const RECORDS_AT: u64 = 0x40;
const RECORD: u64 = 0x50;
const REC_SHARED: usize = 0x30;
const REC_HEAD: usize = 0x48;
/// Records examined for the root signature.
const PROBE_RECORDS: usize = 24;

const NODE_LINK_A: usize = 0x00;
const NODE_LINK_B: usize = 0x10;
const NODE_HASH: usize = 0x20;
const NODE_DESC: usize = 0x70;
const NODE_FLAG: usize = 0x78;
const NODE_SIZE: usize = 0x80;
/// A link (and a record head) targets the node's embedded link field; the
/// window the offsets above describe starts this far before it.
const NODE_WINDOW_BEFORE: u64 = 0x10;

fn u64_at(b: &[u8], o: usize) -> u64 {
    u64::from_le_bytes(b[o..o + 8].try_into().unwrap())
}
fn u32_at(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

/// The word real records carry at `+8` (`{Num = 0, Max = 4}` of an inline
/// array, by the look of it); not every record has it, but every root has
/// records that do.
const REC_TAG: u64 = 0x0000_0004_0000_0000;

/// Does a run of records look like a root's? Three structural checks —
/// the weakest alone (records sharing a heap pointer at `+0x30`) matches a
/// generic object-array pattern 21,000 times over in a live process:
///
/// 1. at least three of the first records agree on one heap pointer at
///    `+0x30` (a shared allocator or type object);
/// 2. at least one record carries the tag word at `+8`;
/// 3. at least one record has a heap pointer as its head at `+0x48`.
///
/// Deliberately nothing about the *nodes*: their links and heads change
/// as the loader works, and a signature that read them flapped between one
/// call and the next. A false positive here only costs a walk that finds
/// no valid nodes.
pub fn records_signature(records: &[u8]) -> bool {
    if records.len() < RECORD as usize * PROBE_RECORDS {
        return false;
    }
    let mut shared: HashMap<u64, usize> = HashMap::new();
    let mut tagged = false;
    let mut head = false;
    for i in 0..PROBE_RECORDS {
        let rec = i * RECORD as usize;
        let s = u64_at(records, rec + REC_SHARED);
        if heapish(s) {
            *shared.entry(s).or_default() += 1;
        }
        if u64_at(records, rec + 8) == REC_TAG {
            tagged = true;
        }
        if heapish(u64_at(records, rec + REC_HEAD)) {
            head = true;
        }
    }
    tagged && head && shared.values().copied().max().unwrap_or(0) >= 3
}

/// One node, decoded from its `NODE_SIZE` bytes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Node {
    pub link_a: u64,
    pub link_b: u64,
    pub hash: u64,
    pub descriptor: u64,
    pub flag: u64,
}

pub fn parse_node(bytes: &[u8]) -> Option<Node> {
    if bytes.len() < NODE_SIZE {
        return None;
    }
    Some(Node {
        link_a: u64_at(bytes, NODE_LINK_A),
        link_b: u64_at(bytes, NODE_LINK_B),
        hash: u64_at(bytes, NODE_HASH),
        descriptor: u64_at(bytes, NODE_DESC),
        flag: u64_at(bytes, NODE_FLAG),
    })
}

/// The payload base a 32-byte descriptor points at, if it has the shape
/// `{ptr; u32; u32 = 1; u64 = 0; 00 01 ...}` with a heap pointer.
pub fn descriptor_base(bytes: &[u8]) -> Option<u64> {
    if bytes.len() < 32 {
        return None;
    }
    let ptr = u64_at(bytes, 0);
    (u32_at(bytes, 12) == 1
        && u64_at(bytes, 16) == 0
        && bytes[0x18] == 0
        && bytes[0x19] == 1
        && heapish(ptr))
    .then_some(ptr)
}

/// A root: the `.data` slot (as an RVA, a property of the build) and the
/// struct it pointed at this launch.
#[derive(Debug, Clone, Copy)]
pub struct Root {
    pub static_rva: u64,
    pub addr: u64,
}

/// A live buffer the cache references.
#[derive(Debug, Clone, Copy)]
pub struct Holder {
    pub descriptor: u64,
    /// Payload byte 0: a field is at `base + file_offset`.
    pub base: u64,
}

/// The cache, walked: `FPackageId` -> holder.
#[derive(Debug, Default)]
pub struct Cache {
    pub roots: Vec<Root>,
    pub by_id: HashMap<u64, Holder>,
    pub nodes: usize,
}

/// Writable PE sections of the image as `(rva, virtual size)`.
fn writable_sections(exe: &[u8]) -> Vec<(u64, u64)> {
    const WRITE: u32 = 0x8000_0000;
    let Some(lfanew) = exe.get(0x3C..0x40) else {
        return Vec::new();
    };
    let e_lfanew = u32::from_le_bytes(lfanew.try_into().unwrap()) as usize;
    if exe.get(e_lfanew..e_lfanew + 4) != Some(b"PE\0\0") {
        return Vec::new();
    }
    let coff = e_lfanew + 4;
    let n = u16::from_le_bytes(exe[coff + 2..coff + 4].try_into().unwrap()) as usize;
    let opt = u16::from_le_bytes(exe[coff + 16..coff + 18].try_into().unwrap()) as usize;
    let table = coff + 20 + opt;
    (0..n)
        .filter_map(|i| {
            let o = table + i * 40;
            let vsize = u32::from_le_bytes(exe.get(o + 8..o + 12)?.try_into().unwrap()) as u64;
            let vaddr = u32::from_le_bytes(exe[o + 12..o + 16].try_into().unwrap()) as u64;
            let chars = u32::from_le_bytes(exe[o + 36..o + 40].try_into().unwrap());
            (chars & WRITE != 0 && vsize > 0).then_some((vaddr, vsize))
        })
        .collect()
}

/// Find every root from the image's static data: each heap pointer in a
/// writable section whose target carries the record signature. A few
/// seconds; the RVAs it returns are worth caching per build, and
/// [`roots_at`] revalidates cached ones in milliseconds.
pub fn find_roots(p: &Process, exe: &[u8], module_base: u64) -> Result<Vec<Root>> {
    let mut roots = Vec::new();
    let mut seen: HashSet<u64> = HashSet::new();
    for (rva, vsize) in writable_sections(exe) {
        let start = module_base + rva;
        let mut at = 0u64;
        while at < vsize {
            let take = (4 * 1024 * 1024).min(vsize - at) as usize;
            if let Ok(w) = p.read(start + at, take) {
                for off in (0..w.len().saturating_sub(7)).step_by(8) {
                    let v = u64_at(&w, off);
                    if !heapish(v) || !seen.insert(v) {
                        continue;
                    }
                    if let Ok(recs) = p.read(v + RECORDS_AT, RECORD as usize * PROBE_RECORDS) {
                        if records_signature(&recs) {
                            roots.push(Root {
                                static_rva: rva + at + off as u64,
                                addr: v,
                            });
                        }
                    }
                }
            }
            at += take as u64;
        }
    }
    // A static pointer into the *middle* of a root's record array passes
    // the signature too (it sees the same records). Keep the lowest address
    // of each such run: the struct start.
    roots.sort_by_key(|r| r.addr);
    let span = RECORDS_AT + RECORD * PROBE_RECORDS as u64;
    let mut kept: Vec<Root> = Vec::new();
    for r in roots {
        if kept.last().is_some_and(|k| r.addr < k.addr + span) {
            continue;
        }
        kept.push(r);
    }
    Ok(kept)
}

/// Reattach to cached root RVAs, keeping only those whose target still
/// carries the signature: a game update moves them, and this notices.
pub fn roots_at(p: &Process, module_base: u64, rvas: &[u64]) -> Vec<Root> {
    rvas.iter()
        .filter_map(|rva| {
            let addr = u64_at(&p.read(module_base + rva, 8).ok()?, 0);
            let recs = p.read(addr + RECORDS_AT, RECORD as usize * PROBE_RECORDS).ok()?;
            records_signature(&recs).then_some(Root {
                static_rva: *rva,
                addr,
            })
        })
        .collect()
}

/// Walk every root's records and node chains, keeping each holder node's
/// buffer by package id. Bounded by the graph; the largest component
/// measured was 1.28M nodes in about five seconds.
pub fn walk(p: &Process, roots: &[Root]) -> Cache {
    let mut cache = Cache {
        roots: roots.to_vec(),
        ..Default::default()
    };
    let mut seen: HashSet<u64> = HashSet::new();
    for root in roots {
        let Ok(tw) = p.read(root.addr, 0x2000) else {
            continue;
        };
        let mut rec = RECORDS_AT as usize;
        while rec + RECORD as usize <= tw.len() {
            let head = u64_at(&tw, rec + REC_HEAD);
            rec += RECORD as usize;
            if !heapish(head) || !seen.insert(head) {
                continue;
            }
            let mut q: VecDeque<u64> = VecDeque::from([head]);
            while let Some(node) = q.pop_front() {
                let Ok(w) = p.read(node.wrapping_sub(NODE_WINDOW_BEFORE), NODE_SIZE) else {
                    continue;
                };
                let Some(n) = parse_node(&w) else {
                    continue;
                };
                cache.nodes += 1;
                if n.hash != 0 && n.flag == 1 && heapish(n.descriptor) {
                    if let Ok(d) = p.read(n.descriptor, 32) {
                        if let Some(base) = descriptor_base(&d) {
                            cache.by_id.entry(n.hash).or_insert(Holder {
                                descriptor: n.descriptor,
                                base,
                            });
                        }
                    }
                }
                for l in [n.link_a, n.link_b] {
                    if heapish(l) && seen.insert(l) {
                        q.push_back(l);
                    }
                }
            }
        }
    }
    cache
}

impl Cache {
    /// The live buffer for a package id, if the loader still references it.
    pub fn lookup(&self, package_id: u64) -> Option<Holder> {
        self.by_id.get(&package_id).copied()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn put64(b: &mut [u8], o: usize, v: u64) {
        b[o..o + 8].copy_from_slice(&v.to_le_bytes());
    }

    #[test]
    fn records_signature_needs_shared_pointer_tag_word_and_head() {
        let mut recs = vec![0u8; RECORD as usize * PROBE_RECORDS];
        assert!(!records_signature(&recs), "all zeros is not a root");
        for i in [0usize, 5, 9] {
            put64(&mut recs, i * RECORD as usize + REC_SHARED, 0x1a5b34c6700);
        }
        put64(&mut recs, 5 * RECORD as usize + REC_HEAD, 0x1aaec93cde0);
        assert!(!records_signature(&recs), "shared pointer and head alone are not enough");
        put64(&mut recs, 7 * RECORD as usize + 8, REC_TAG);
        assert!(records_signature(&recs));
        put64(&mut recs, 9 * RECORD as usize + REC_SHARED, 0);
        assert!(!records_signature(&recs), "two agreeing records are not enough");
    }

    #[test]
    fn descriptor_shape_is_checked_exactly() {
        let mut d = vec![0u8; 32];
        put64(&mut d, 0, 0x1a5f5280040);
        d[12] = 1;
        d[0x19] = 1;
        assert_eq!(descriptor_base(&d), Some(0x1a5f5280040));
        d[0x19] = 0;
        assert_eq!(descriptor_base(&d), None, "the 00 01 tail is part of the shape");
        d[0x19] = 1;
        put64(&mut d, 16, 7);
        assert_eq!(descriptor_base(&d), None, "+0x10 must be zero");
    }

    #[test]
    fn node_fields_sit_where_the_probes_found_them() {
        let mut n = vec![0u8; NODE_SIZE];
        put64(&mut n, NODE_HASH, 0x2fc1a2f8efc6ef72);
        put64(&mut n, NODE_DESC, 0x1a5c9e042e0);
        put64(&mut n, NODE_FLAG, 1);
        let node = parse_node(&n).unwrap();
        assert_eq!(node.hash, 0x2fc1a2f8efc6ef72);
        assert_eq!(node.descriptor, 0x1a5c9e042e0);
        assert_eq!(node.flag, 1);
    }
}
