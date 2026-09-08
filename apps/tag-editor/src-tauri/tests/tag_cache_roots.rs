//! Every root of the tag cache, and the coverage they add up to.
//!
//! Two `.data` globals reach one ~44k-node component that resolves 35 of
//! 362 resident tags exactly (`tag_cache_lookup.rs`). The rest live in other
//! node regions — other instances of the root struct `T`. `T` has a strong
//! signature: its 80-byte map records from `+0x40` carry the word
//! `0x0000000400000000` at `+8`, so `+0x48`, `+0x98`, `+0xe8` all hold it.
//!
//! This enumerates every heap pointer in the image's writable sections whose
//! target carries that signature, walks each instance's records and chains,
//! and reports, per instance and in union: nodes, descriptor-holding nodes
//! (`+0x08 == 1`), known descriptors reached, and census-resident tags
//! resolved by `FPackageId` to their exact base. If the union reaches the
//! resident set, production can key on these `exe + offset` roots.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`,
//! `MJOLNIR_EXE`.

mod common;

use std::collections::{HashMap, HashSet, VecDeque};

use common::*;
use tag_editor_lib::catalog::Catalog;

const RECORDS_AT: u64 = 0x40;
const RECORD: u64 = 0x50;
const REC_HEAD: u64 = 0x48;
const REC_TAG: u64 = 0x0000_0004_0000_0000;
const SLOT_FROM_NODE: u64 = 0x60;

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

fn writable_sections(exe: &[u8]) -> Vec<(u64, u64)> {
    const WRITE: u32 = 0x8000_0000;
    let e_lfanew = u32::from_le_bytes(exe[0x3C..0x40].try_into().unwrap()) as usize;
    let coff = e_lfanew + 4;
    let n = u16::from_le_bytes(exe[coff + 2..coff + 4].try_into().unwrap()) as usize;
    let opt = u16::from_le_bytes(exe[coff + 16..coff + 18].try_into().unwrap()) as usize;
    let table = coff + 20 + opt;
    (0..n)
        .filter_map(|i| {
            let o = table + i * 40;
            let vsize = u32::from_le_bytes(exe[o + 8..o + 12].try_into().unwrap()) as u64;
            let vaddr = u32::from_le_bytes(exe[o + 12..o + 16].try_into().unwrap()) as u64;
            let chars = u32::from_le_bytes(exe[o + 36..o + 40].try_into().unwrap());
            (chars & WRITE != 0 && vsize > 0).then_some((vaddr, vsize))
        })
        .collect()
}

/// Is `addr` a `T`? Not every record carries the tag word (the first
/// signature missed even the known roots), but every record of every known
/// root holds the same pointer at `+0x30` — a shared allocator or type
/// object. `shared` is read from a known root at runtime; a `T` has it in at
/// least three of its first eight records.
const PROBE_RECORDS: usize = 24;

fn is_root(p: &blam_live::Process, addr: u64, shared: u64) -> bool {
    let Ok(w) = p.read(addr + RECORDS_AT, RECORD as usize * PROBE_RECORDS) else { return false };
    if w.len() < RECORD as usize * PROBE_RECORDS {
        return false;
    }
    (0..PROBE_RECORDS)
        .filter(|i| u64_at(&w, i * RECORD as usize + 0x30) == shared)
        .count()
        >= 3
}

/// The shared `+0x30` word of a known root: the most common heap value over
/// its first records. Record 0 is not always a plain record (root 1's array
/// effectively starts at +0x90), so the mode is taken rather than one slot.
fn shared_word(p: &blam_live::Process, root: u64) -> u64 {
    let w = p.read(root + RECORDS_AT, RECORD as usize * PROBE_RECORDS).expect("records");
    let mut hist: HashMap<u64, usize> = HashMap::new();
    for i in 0..PROBE_RECORDS {
        let v = u64_at(&w, i * RECORD as usize + 0x30);
        if heapish(v) {
            *hist.entry(v).or_default() += 1;
        }
    }
    hist.into_iter().max_by_key(|(_, n)| *n).map(|(v, _)| v).unwrap_or(0)
}

fn descriptor_base(p: &blam_live::Process, desc: u64) -> Option<u64> {
    if !heapish(desc) || desc % 32 != 0 {
        return None;
    }
    let r = p.read(desc, 32).ok()?;
    if r.len() < 32 {
        return None;
    }
    let ptr = u64_at(&r, 0);
    (u32_at(&r, 12) == 1 && u64_at(&r, 16) == 0 && r[0x18] == 0 && r[0x19] == 1 && heapish(ptr))
        .then_some(ptr)
}

/// Walk one root: key -> (descriptor, base) for every holder node
/// (`+0x08 == 1` with a shape-valid descriptor).
fn walk_root(
    p: &blam_live::Process,
    root: u64,
    seen: &mut HashSet<u64>,
) -> (usize, HashMap<u64, (u64, u64)>) {
    let mut holders: HashMap<u64, (u64, u64)> = HashMap::new();
    let mut nodes = 0usize;
    let Ok(tw) = p.read(root, 0x2000) else { return (0, holders) };
    let mut rec = RECORDS_AT;
    while rec + RECORD <= tw.len() as u64 {
        let head = u64_at(&tw, (rec + REC_HEAD) as usize);
        if u64_at(&tw, (rec + 8) as usize) != REC_TAG && head == 0 {
            break;
        }
        rec += RECORD;
        if !heapish(head) || !seen.insert(head) {
            continue;
        }
        let mut q: VecDeque<u64> = VecDeque::from([head]);
        while let Some(node) = q.pop_front() {
            let slot = node + SLOT_FROM_NODE;
            let Ok(w) = p.read(slot - 0x70, 0x80) else { continue };
            if w.len() < 0x80 {
                continue;
            }
            nodes += 1;
            let hash = u64_at(&w, 0x20);
            let flag = u64_at(&w, 0x78);
            if hash != 0 && flag == 1 {
                if let Some(base) = descriptor_base(p, u64_at(&w, 0x70)) {
                    holders.entry(hash).or_insert((u64_at(&w, 0x70), base));
                }
            }
            for l in [u64_at(&w, 0x00), u64_at(&w, 0x10)] {
                if heapish(l) && seen.insert(l) {
                    q.push_back(l);
                }
            }
        }
    }
    (nodes, holders)
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS, MJOLNIR_RESIDENT, MJOLNIR_EXE"]
fn tag_cache_roots() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let exe = std::fs::read(std::env::var("MJOLNIR_EXE").expect("set MJOLNIR_EXE")).unwrap();
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, _) = p.module(blam_live::GAME_EXE).expect("module");
    let resident = load_resident();
    let t = targets(&p);
    let known_desc: HashSet<u64> = t.descriptors.iter().map(|(a, _)| *a).collect();

    // The shared word, from the first known root (exe+0xd3ec3a0 on CU3).
    let known = u64_at(&p.read(mbase + 0xd3ec3a0, 8).expect("known root"), 0);
    let shared = shared_word(&p, known);
    eprintln!("shared record word from known root {known:#x}: {shared:#x}");
    assert!(is_root(&p, known, shared), "signature must accept the known root");

    // ---- Every static pointer whose target is a T.
    let t0 = std::time::Instant::now();
    let mut roots: Vec<(u64, u64)> = Vec::new(); // (static addr, T)
    let mut seen_t: HashSet<u64> = HashSet::new();
    for (rva, vsize) in writable_sections(&exe) {
        let start = mbase + rva;
        let mut at = 0u64;
        while at < vsize {
            let take = (4 * 1024 * 1024).min(vsize - at) as usize;
            if let Ok(w) = p.read(start + at, take) {
                for off in (0..w.len().saturating_sub(7)).step_by(8) {
                    let v = u64_at(&w, off);
                    if heapish(v) && seen_t.insert(v) && is_root(&p, v, shared) {
                        roots.push((start + at + off as u64, v));
                    }
                }
            }
            at += take as u64;
        }
    }
    eprintln!(
        "{} root structs found from static data in {:.1}s",
        roots.len(),
        t0.elapsed().as_secs_f32()
    );

    // ---- Walk each; union the holders.
    let mut seen_nodes: HashSet<u64> = HashSet::new();
    let mut union: HashMap<u64, (u64, u64)> = HashMap::new();
    let resident_ids: HashMap<u64, u64> = resident
        .iter()
        .filter_map(|(base, (i, _, _))| {
            catalog.entry(*i).map(|e| (package_id(&e.short, &e.group), *base))
        })
        .collect();
    for (sa, root) in &roots {
        let (nodes, holders) = walk_root(&p, *root, &mut seen_nodes);
        let known = holders.values().filter(|(d, _)| known_desc.contains(d)).count();
        let resolved = holders
            .iter()
            .filter(|(h, (_, b))| resident_ids.get(h) == Some(b))
            .count();
        eprintln!(
            "  exe+{:#x} -> T {root:#x}: {nodes:>6} nodes, {:>4} holders, {known:>3} known descriptors, {resolved:>3} resident tags resolved exactly",
            sa - mbase,
            holders.len()
        );
        for (h, v) in holders {
            union.entry(h).or_insert(v);
        }
    }

    // ---- Union coverage.
    let exact = resident_ids
        .iter()
        .filter(|(h, b)| union.get(h).map(|(_, ub)| ub) == Some(b))
        .count();
    let wrong = resident_ids
        .iter()
        .filter(|(h, b)| union.get(h).is_some_and(|(_, ub)| ub != *b))
        .count();
    let tags_in_cache = catalog
        .tags
        .iter()
        .filter(|e| union.contains_key(&package_id(&e.short, &e.group)))
        .count();
    let known_reached = union.values().filter(|(d, _)| known_desc.contains(d)).count();
    eprintln!(
        "UNION: {} holder nodes; {tags_in_cache} catalog tags have a loaded buffer per the cache; {known_reached}/{} known descriptors reached",
        union.len(),
        known_desc.len()
    );
    eprintln!(
        "ACCEPTANCE over {} census-resident tags: {exact} resolved exactly, {wrong} wrong, {} not in any root",
        resident.len(),
        resident.len() - exact - wrong
    );
    assert!(wrong == 0, "a cache lookup disagreed with the census");
}
