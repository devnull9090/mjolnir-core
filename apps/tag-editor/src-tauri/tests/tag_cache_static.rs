//! From the exe's static data down to the node regions.
//!
//! Every probe agrees the tag data cache is **native**: the descriptor
//! holders live in raw heap structures, not `UObject`s (`tag_cache_holders`),
//! so its root is a static global in the image's own writable sections — not
//! anything the object table can name. Upward walks never reached it because
//! node-to-node links drowned them; top-down from `UObject` singletons could
//! not, because the cache is not a `UObject`.
//!
//! So start from the true top. Read the image's writable sections (`.data`,
//! `.bss`), take every heap-looking pointer, and follow each one hop into a
//! small window. A struct in that window holding a pointer **into one of the
//! five known node regions** is a candidate manager; two hops from there,
//! count the slots and descriptors reached. Any survivor is, by construction,
//! `exe + offset` — the classic root — plus the field offsets to chase.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`,
//! `MJOLNIR_EXE`.

mod common;

use std::collections::{HashMap, HashSet};

use common::*;

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

/// Writable PE sections as `(name, rva, virtual size)`.
fn writable_sections(exe: &[u8]) -> Vec<(String, u64, u64)> {
    const WRITE: u32 = 0x8000_0000;
    let e_lfanew = u32::from_le_bytes(exe[0x3C..0x40].try_into().unwrap()) as usize;
    let coff = e_lfanew + 4;
    let n = u16::from_le_bytes(exe[coff + 2..coff + 4].try_into().unwrap()) as usize;
    let opt = u16::from_le_bytes(exe[coff + 16..coff + 18].try_into().unwrap()) as usize;
    let table = coff + 20 + opt;
    let mut out = Vec::new();
    for i in 0..n {
        let o = table + i * 40;
        let name = String::from_utf8_lossy(&exe[o..o + 8]).trim_end_matches('\0').to_string();
        let vsize = u32::from_le_bytes(exe[o + 8..o + 12].try_into().unwrap()) as u64;
        let vaddr = u32::from_le_bytes(exe[o + 12..o + 16].try_into().unwrap()) as u64;
        let chars = u32::from_le_bytes(exe[o + 36..o + 40].try_into().unwrap());
        if chars & WRITE != 0 && vsize > 0 {
            out.push((name, vaddr, vsize));
        }
    }
    out
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS, MJOLNIR_RESIDENT, MJOLNIR_EXE"]
fn tag_cache_static() {
    let exe = std::fs::read(std::env::var("MJOLNIR_EXE").expect("set MJOLNIR_EXE")).unwrap();
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, msize) = p.module(blam_live::GAME_EXE).expect("module");

    let t = targets(&p);
    let desc_set: HashSet<u64> = t.descriptors.iter().map(|(a, _)| *a).collect();
    let slot_set: HashSet<u64> = t.slots.iter().copied().collect();
    let node_pages = dense_pages(&t.slots, 2);
    let desc_pages = dense_pages(&t.descriptors.iter().map(|(a, _)| *a).collect::<Vec<_>>(), 2);
    eprintln!(
        "{} node pages, {} descriptor pages",
        node_pages.len(),
        desc_pages.len()
    );

    // ---- Static pointers: every heap-looking qword in the writable sections.
    let sections = writable_sections(&exe);
    let mut statics: Vec<(u64, u64)> = Vec::new(); // (static addr, value)
    for (name, rva, vsize) in &sections {
        let start = mbase + rva;
        let mut at = 0u64;
        let mut n = 0usize;
        while at < *vsize {
            let take = (4 * 1024 * 1024).min(vsize - at) as usize;
            if let Ok(w) = p.read(start + at, take) {
                for off in (0..w.len().saturating_sub(7)).step_by(8) {
                    let v = u64_at(&w, off);
                    if heapish(v) {
                        statics.push((start + at + off as u64, v));
                        n += 1;
                    }
                }
            }
            at += take as u64;
        }
        eprintln!("  section {name:<8} rva {rva:#x} size {} KB: {n} heap pointers", vsize >> 10);
    }
    let _ = msize;
    eprintln!("{} static heap pointers in total", statics.len());

    // ---- Hop 1: a 4 KB window at each pointer. Score by pointers into node
    // or descriptor pages, and by direct slot/descriptor hits.
    const HOP1: usize = 0x1000;
    struct Cand {
        static_addr: u64,
        value: u64,
        into_nodes: Vec<(usize, u64)>, // (field offset, target)
        into_descs: usize,
        direct: usize,
    }
    let mut cands: Vec<Cand> = Vec::new();
    let mut seen: HashSet<u64> = HashSet::new();
    for (sa, v) in &statics {
        if !seen.insert(*v) {
            continue;
        }
        let Ok(w) = p.read(*v, HOP1) else { continue };
        let mut into_nodes = Vec::new();
        let mut into_descs = 0usize;
        let mut direct = 0usize;
        for off in (0..w.len().saturating_sub(7)).step_by(8) {
            let x = u64_at(&w, off);
            if x == 0 {
                continue;
            }
            if slot_set.contains(&x) || desc_set.contains(&x) {
                direct += 1;
            }
            if node_pages.contains(&(x >> 20)) {
                into_nodes.push((off, x));
            } else if desc_pages.contains(&(x >> 20)) {
                into_descs += 1;
            }
        }
        if !into_nodes.is_empty() || direct > 0 {
            cands.push(Cand {
                static_addr: *sa,
                value: *v,
                into_nodes,
                into_descs,
                direct,
            });
        }
    }
    eprintln!(
        "{} static-reachable structs point into a node region or hold a slot/descriptor directly",
        cands.len()
    );

    // ---- Hop 2: from each node-region pointer, how many slots/descriptors
    // sit in a 64 KB window? Rank.
    const HOP2: usize = 0x10000;
    let mut ranked: Vec<(usize, usize, String)> = Vec::new();
    for c in &cands {
        let mut best = (0usize, 0usize, String::new());
        for (off, target) in c.into_nodes.iter().take(64) {
            let Ok(w) = p.read(*target, HOP2) else { continue };
            let mut s = 0usize;
            let mut d = 0usize;
            for io in (0..w.len().saturating_sub(7)).step_by(8) {
                let x = u64_at(&w, io);
                if slot_set.contains(&(target + io as u64)) {
                    s += 1;
                }
                if desc_set.contains(&x) {
                    d += 1;
                }
            }
            // A TArray header at this field? {Data=target, Num, Max}
            let hdr = p.read(c.value + *off as u64 + 8, 8).unwrap_or_default();
            let num = if hdr.len() == 8 { u32_at(&hdr, 0) } else { 0 };
            if s + d > best.0 + best.1 {
                best = (s, d, format!("field +{off:#x} -> {target:#x} (Num? {num})"));
            }
        }
        if best.0 + best.1 > 0 || c.direct > 0 {
            ranked.push((
                best.0 + best.1 + c.direct * 2,
                c.direct,
                format!(
                    "exe+{:#x} -> {:#x}: {} slots+descs via {}; {} direct; {} ptrs into node pages, {} into desc pages",
                    c.static_addr - mbase,
                    c.value,
                    best.0 + best.1,
                    best.2,
                    c.direct,
                    c.into_nodes.len(),
                    c.into_descs
                ),
            ));
        }
    }
    ranked.sort_by_key(|(score, _, _)| std::cmp::Reverse(*score));
    eprintln!("candidates from static data (best first):");
    for (_, _, line) in ranked.iter().take(20) {
        eprintln!("  {line}");
    }
    if ranked.is_empty() {
        // Fall back: report the static pointers whose hop-1 window merely
        // points into node pages, so the field can still be inspected.
        let mut weak: HashMap<u64, usize> = HashMap::new();
        for c in &cands {
            *weak.entry(c.static_addr).or_default() += c.into_nodes.len();
        }
        let mut w: Vec<_> = weak.into_iter().collect();
        w.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        eprintln!("no two-hop hits; static pointers whose target points into node pages:");
        for (sa, n) in w.iter().take(15) {
            eprintln!("  exe+{:#x}: {n} pointers into node pages", sa - mbase);
        }
    }
}
