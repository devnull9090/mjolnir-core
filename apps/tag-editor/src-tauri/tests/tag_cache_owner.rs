//! Mapping the descriptor-pointer arrays directly, then finding their owner.
//!
//! `tag_cache_nodes.rs` showed that the slots holding descriptor pointers are
//! not structured nodes: no identity field, and almost nothing external points
//! near them. They are elements of pointer *arrays* — and an owner points at
//! an array's **start**, which is nowhere near the ~4 % of elements the
//! census happens to know about. Searching around sparse hits could never
//! find it.
//!
//! So this maps each array outright: from a cluster of known slots, walk in
//! 8-byte steps while elements keep being descriptor pointers, to the true
//! start and end. If nearly every element is a shape-valid descriptor, the
//! array is a registry of loaded buffers. Then scan for pointers to the
//! start: a `TArray` header there reads `{Data*, Num, Max}` with `Num` equal
//! to the measured length — decisive — and the struct around it is the
//! manager. Repeat upward from the manager until a static holder appears.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`.

mod common;

use std::collections::{HashMap, HashSet};

use common::*;
use tag_editor_lib::catalog::Catalog;

/// Is `addr` a 32-byte buffer descriptor (`+0xC == 1`, `+0x10 == 0`) with a
/// heap-looking buffer pointer?
fn is_descriptor(p: &blam_live::Process, addr: u64) -> bool {
    if addr % 32 != 0 || !(0x1_0000_0000..0x8000_0000_0000).contains(&addr) {
        return false;
    }
    match p.read(addr, 32) {
        Ok(r) if r.len() == 32 => {
            let ptr = u64_at(&r, 0);
            u32_at(&r, 12) == 1
                && u64_at(&r, 16) == 0
                && (ptr == 0 || (0x1_0000_0000..0x8000_0000_0000).contains(&ptr))
        }
        _ => false,
    }
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn tag_cache_owner() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, msize) = p.module(blam_live::GAME_EXE).expect("module");
    let is_static = |a: u64| a >= mbase && a < mbase + msize;

    let resident = load_resident();
    let descs = descriptors(&p, &resident);
    let desc_set: HashSet<u64> = descs.iter().map(|(a, _)| *a).collect();
    let desc_addrs: Vec<u64> = desc_set.iter().copied().collect();
    let slots: Vec<u64> = range_scan(&p, &exact_ranges(&desc_addrs))
        .into_iter()
        .map(|(h, _)| h)
        .collect();
    eprintln!("{} descriptors, {} slots holding them", descs.len(), slots.len());

    // ---- Map each array. Cluster slots by 1 MB page; for each cluster walk
    // outward from its min/max in 8-byte steps while the element is a
    // descriptor pointer (allowing short gaps of nulls/other pointers).
    let mut by_page: HashMap<u64, Vec<u64>> = HashMap::new();
    for s in &slots {
        by_page.entry(s >> 20).or_default().push(*s);
    }
    let mut clusters: Vec<Vec<u64>> = by_page.into_values().filter(|v| v.len() >= 3).collect();
    clusters.sort_by_key(|v| std::cmp::Reverse(v.len()));

    struct Arr {
        start: u64,
        end: u64,
        elems: usize,
        descs: usize,
        ours: usize,
    }
    let mut arrays: Vec<Arr> = Vec::new();
    let mut desc_cache: HashMap<u64, bool> = HashMap::new();
    let mut check = |p: &blam_live::Process, v: u64| -> bool {
        *desc_cache.entry(v).or_insert_with(|| is_descriptor(p, v))
    };
    // Windows must stay inside one mapped region: a read that crosses into an
    // unmapped page comes back short and the walk would index past it.
    let regions = p.writable_regions().expect("regions");
    for cl in clusters.iter().take(6) {
        let (lo, hi) = (*cl.iter().min().unwrap(), *cl.iter().max().unwrap());
        let Some(reg) = regions.iter().find(|r| lo >= r.base && lo < r.base + r.size) else {
            continue;
        };
        let win_lo = lo.saturating_sub(0x80000).max(reg.base);
        let win_hi = (hi + 0x80000).min(reg.base + reg.size);
        let Ok(w) = p.read(win_lo, (win_hi - win_lo) as usize) else { continue };
        let w_end = win_lo + w.len() as u64;
        let at = |a: u64| (a - win_lo) as usize;
        let elem = |a: u64| -> u64 {
            if a < win_lo || a + 8 > w_end {
                return 0;
            }
            u64_at(&w, at(a))
        };
        let valid = |p: &blam_live::Process, a: u64, cache: &mut dyn FnMut(&blam_live::Process, u64) -> bool| -> bool {
            let v = elem(a);
            v != 0 && cache(p, v)
        };
        // Walk down from lo, up from hi; tolerate up to 8 consecutive misses.
        let mut start = lo;
        let mut miss = 0;
        while start >= win_lo + 8 && miss < 8 {
            let cand = start - 8;
            if valid(&p, cand, &mut check) {
                start = cand;
                miss = 0;
            } else {
                miss += 1;
                start = cand;
            }
        }
        start += 8 * miss as u64;
        let mut end = hi + 8;
        miss = 0;
        while end + 8 <= w_end && miss < 8 {
            if valid(&p, end, &mut check) {
                end += 8;
                miss = 0;
            } else {
                miss += 1;
                end += 8;
            }
        }
        end -= 8 * miss as u64;
        let elems = ((end - start) / 8) as usize;
        let mut nd = 0usize;
        let mut ours = 0usize;
        let mut a = start;
        while a < end {
            let v = elem(a);
            if v != 0 && check(&p, v) {
                nd += 1;
                if desc_set.contains(&v) {
                    ours += 1;
                }
            }
            a += 8;
        }
        eprintln!(
            "array {start:#x}..{end:#x}: {elems} elements, {nd} descriptor ptrs ({ours} ours), stride 8",
        );
        arrays.push(Arr { start, end, elems, descs: nd, ours });
    }
    assert!(!arrays.is_empty(), "no arrays mapped");

    // How many *distinct* descriptors do the arrays reference in total, and do
    // they overlap? A registry of every loaded buffer should sum to the
    // present-tag count or the resident count, not something random.
    let mut all_descs: HashSet<u64> = HashSet::new();
    for a in &arrays {
        let Ok(w) = p.read(a.start, (a.end - a.start) as usize) else { continue };
        for off in (0..w.len() - 7).step_by(8) {
            let v = u64_at(&w, off);
            if v != 0 && check(&p, v) {
                all_descs.insert(v);
            }
        }
    }
    eprintln!(
        "arrays reference {} distinct descriptors in total (census-resident: {}, present tags: ~9147)",
        all_descs.len(),
        descs.len()
    );

    // ---- Who points at each array's start (or a small header before it)?
    let mut targets: Vec<u64> = Vec::new();
    let mut tag_of: HashMap<u64, (usize, u64)> = HashMap::new(); // value -> (array idx, k)
    for (i, a) in arrays.iter().enumerate() {
        for k in (0..=0x40u64).step_by(8) {
            targets.push(a.start - k);
            tag_of.insert(a.start - k, (i, k));
        }
    }
    let owners = range_scan(&p, &exact_ranges(&targets));
    eprintln!("{} holders of an array start (or up to 0x40 before it)", owners.len());
    let mut manager_slots: Vec<u64> = Vec::new();
    for (h, v) in &owners {
        let (i, k) = tag_of[v];
        let a = &arrays[i];
        // TArray header? {Data*, int32 Num, int32 Max} right here.
        let hdr = p.read(*h, 16).unwrap_or_default();
        let (num, max) = if hdr.len() == 16 {
            (u32_at(&hdr, 8), u32_at(&hdr, 12))
        } else {
            (0, 0)
        };
        let tarray = k == 0 && num as usize == a.elems || (num as usize).abs_diff(a.elems) <= 2;
        eprintln!(
            "  holder {h:#x} -> array {i} start-{k:#x}{}{}  Num={num} Max={max} (measured {} elems)",
            if is_static(*h) { format!(" *** STATIC exe+{:#x}", h - mbase) } else { String::new() },
            if tarray { "  <-- TArray header matches" } else { "" },
            a.elems
        );
        if !is_static(*h) {
            manager_slots.push(*h);
        }
    }
    if owners.iter().any(|(h, _)| is_static(*h)) {
        eprintln!("ROOT: an array is held directly from static data (see above)");
        return;
    }

    // ---- Up from the manager: what points at the struct holding the array
    // header? Try starts up to 0x200 before each header slot; exclude the
    // arrays' own pages so element pointers cannot masquerade as owners.
    let mut excluded: HashSet<u64> = HashSet::new();
    for a in &arrays {
        for pg in (a.start >> 20)..=(a.end >> 20) {
            excluded.insert(pg);
        }
    }
    let mut level_targets = manager_slots;
    for level in 1..=4 {
        if level_targets.is_empty() {
            break;
        }
        for s in &level_targets {
            excluded.insert(s >> 20);
        }
        let mut tmap: HashMap<u64, u64> = HashMap::new();
        for s in &level_targets {
            for k in (0..=0x200u64).step_by(8) {
                tmap.insert(s - k, *s);
            }
        }
        let t: Vec<u64> = tmap.keys().copied().collect();
        let found: Vec<(u64, u64)> = range_scan(&p, &exact_ranges(&t))
            .into_iter()
            .filter(|(h, _)| !excluded.contains(&(h >> 20)))
            .collect();
        let statics: Vec<(u64, u64)> = found.iter().copied().filter(|(h, _)| is_static(*h)).collect();
        let mut next: Vec<u64> = found.iter().map(|(h, _)| *h).collect();
        next.sort_unstable();
        next.dedup();
        eprintln!(
            "manager level {level}: {} external holders ({} distinct), {} static",
            found.len(),
            next.len(),
            statics.len()
        );
        for (h, v) in statics.iter().take(10) {
            eprintln!(
                "  *** STATIC {h:#x} = exe+{:#x}  -> {v:#x} (struct start = slot-{:#x})",
                h - mbase,
                tmap[v] - v
            );
        }
        if !statics.is_empty() {
            eprintln!("ROOT FOUND at manager level {level}");
            break;
        }
        if next.len() > 500 {
            next.truncate(500);
        }
        level_targets = next;
    }
}
