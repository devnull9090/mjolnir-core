//! Decoding the per-tag node above the buffer descriptor, and escaping the
//! pool to its owner.
//!
//! `tag_cache_root.rs` showed why a naive upward walk fails: the nodes that
//! hold descriptor pointers also point at *each other*, so scanning for "who
//! points at a node" chases siblings forever and never leaves the pool. This
//! probe does two things instead.
//!
//! 1. **Read the node.** Dump the memory around each descriptor slot and test
//!    every field against what could identify the tag — its `FName` id, its
//!    package's `FName` id, its class pointer, its catalog index — to find the
//!    key the engine indexes by, and the node's own layout.
//! 2. **Escape the pool.** Scan for pointers to candidate node starts
//!    (`slot - k` for each plausible `k`), and keep only holders *outside*
//!    the pages the nodes live in. External holders are the container; the
//!    `k` that yields a clean one (about one holder per node, in one dense
//!    region) is the node's true start. Then repeat upward with the same
//!    exclusion until a holder is in the image's static data.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`.

mod common;

use std::collections::{HashMap, HashSet};

use common::*;
use tag_editor_lib::catalog::Catalog;

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn tag_cache_nodes() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, msize) = p.module(blam_live::GAME_EXE).expect("module");
    let is_static = |a: u64| a >= mbase && a < mbase + msize;

    let resident = load_resident();
    let tags = tag_objects(&p, &catalog);
    eprintln!("{} resident, {} tag objects", resident.len(), tags.len());

    // Level 0/1 as established: descriptors, then the nodes holding them.
    let descs = descriptors(&p, &resident);
    let desc_index: HashMap<u64, usize> = descs.iter().copied().collect();
    let desc_addrs: Vec<u64> = descs.iter().map(|(a, _)| *a).collect();
    let l1 = range_scan(&p, &exact_ranges(&desc_addrs));
    // (slot address holding the descriptor ptr, catalog index)
    let nodes: Vec<(u64, usize)> = l1.iter().map(|(h, d)| (*h, desc_index[d])).collect();
    eprintln!("{} descriptors, {} node slots", descs.len(), nodes.len());

    // ---- 1. Stride: slot address modulo candidate strides. A contiguous or
    // pool-allocated container of fixed-size elements makes one residue
    // dominate for its stride.
    for stride in [16u64, 24, 32, 48, 64, 80, 96] {
        let mut h: HashMap<u64, usize> = HashMap::new();
        for (s, _) in &nodes {
            *h.entry(s % stride).or_default() += 1;
        }
        let mut v: Vec<_> = h.into_iter().collect();
        v.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        eprintln!(
            "  mod {stride:>2}: top residues {:?} ({} distinct)",
            &v[..v.len().min(3)],
            v.len()
        );
    }

    // ---- 2. Identity: which field near the slot equals something that
    // names the tag? Offsets are relative to the descriptor slot.
    let mut hits_name: HashMap<i64, usize> = HashMap::new();
    let mut hits_pkg: HashMap<i64, usize> = HashMap::new();
    let mut hits_idx: HashMap<i64, usize> = HashMap::new();
    let mut hits_class: HashMap<i64, usize> = HashMap::new();
    let mut hits_uobj: HashMap<i64, usize> = HashMap::new();
    let mut checked = 0usize;
    const BEFORE: usize = 0x100;
    const AFTER: usize = 0x100;
    for (slot, idx) in &nodes {
        let Some(t) = tags.get(idx) else { continue };
        let Ok(w) = p.read(slot - BEFORE as u64, BEFORE + AFTER) else { continue };
        checked += 1;
        for off in (0..w.len() - 3).step_by(4) {
            let rel = off as i64 - BEFORE as i64;
            let v = u32_at(&w, off);
            if v == t.name_id && v != 0 {
                *hits_name.entry(rel).or_default() += 1;
            }
            if v == t.package_name_id && v != 0 {
                *hits_pkg.entry(rel).or_default() += 1;
            }
            if v as usize == *idx {
                *hits_idx.entry(rel).or_default() += 1;
            }
        }
        for off in (0..w.len() - 7).step_by(8) {
            let rel = off as i64 - BEFORE as i64;
            let v = u64_at(&w, off);
            if v == t.class {
                *hits_class.entry(rel).or_default() += 1;
            }
            if v == t.uobject {
                *hits_uobj.entry(rel).or_default() += 1;
            }
        }
    }
    let top = |m: &HashMap<i64, usize>| {
        let mut v: Vec<_> = m.iter().map(|(k, n)| (*k, *n)).collect();
        v.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        v.truncate(4);
        v
    };
    eprintln!("identity fields near the slot ({checked} nodes checked; offset rel. to slot -> count):");
    eprintln!("  object FName id : {:?}", top(&hits_name));
    eprintln!("  package FName id: {:?}", top(&hits_pkg));
    eprintln!("  catalog index   : {:?}", top(&hits_idx));
    eprintln!("  class pointer   : {:?}", top(&hits_class));
    eprintln!("  UObject pointer : {:?}", top(&hits_uobj));

    // ---- 3. Raw dump of four nodes, annotated.
    let node_pages = dense_pages(&nodes.iter().map(|(s, _)| *s).collect::<Vec<_>>(), 3);
    let desc_set: HashSet<u64> = desc_addrs.iter().copied().collect();
    for (slot, idx) in nodes.iter().take(4) {
        let t = tags.get(idx);
        let short = catalog.entry(*idx).map(|e| e.short.as_str()).unwrap_or("?");
        eprintln!("node slot {slot:#x} — tag {idx} {short}");
        let Ok(w) = p.read(slot - 0x40, 0x90) else { continue };
        for off in (0..w.len() - 7).step_by(8) {
            let v = u64_at(&w, off);
            let rel = off as i64 - 0x40;
            let note = if v == 0 {
                String::new()
            } else if desc_set.contains(&v) {
                " <- descriptor".into()
            } else if node_pages.contains(&(v >> 20)) {
                " (sibling: same pool)".into()
            } else if is_static(v) {
                format!(" (STATIC exe+{:#x})", v - mbase)
            } else if t.is_some_and(|t| t.uobject == v) {
                " (UObject!)".into()
            } else if t.is_some_and(|t| t.class == v) {
                " (class)".into()
            } else if (0x1_0000_0000..0x8000_0000_0000).contains(&v) {
                " (heap ptr)".into()
            } else {
                let lo = (v & 0xffff_ffff) as u32;
                let hi = (v >> 32) as u32;
                format!(" (u32 {lo} | {hi})")
            };
            eprintln!("    {rel:+#05x}: {v:016x}{note}");
        }
    }

    // ---- 4. Escape the pool: pointers to `slot - k`, holders outside node
    // pages only. The right `k` shows as one clean external container.
    let ks: Vec<u64> = (0..=0x58).step_by(8).collect();
    let mut target_of: HashMap<u64, (u64, u64)> = HashMap::new(); // value -> (k, slot)
    for (slot, _) in &nodes {
        for &k in &ks {
            target_of.insert(slot - k, (k, *slot));
        }
    }
    let targets: Vec<u64> = target_of.keys().copied().collect();
    let up = range_scan(&p, &exact_ranges(&targets));
    let mut per_k: HashMap<u64, Vec<(u64, u64)>> = HashMap::new(); // k -> (holder, slot)
    for (h, v) in &up {
        if node_pages.contains(&(h >> 20)) {
            continue; // a sibling, not an owner
        }
        let (k, slot) = target_of[v];
        per_k.entry(k).or_default().push((*h, slot));
    }
    eprintln!("external holders of slot-k (node pages excluded):");
    let mut best: Option<(u64, Vec<(u64, u64)>)> = None;
    for &k in &ks {
        let Some(list) = per_k.get(&k) else { continue };
        let covered: HashSet<u64> = list.iter().map(|(_, s)| *s).collect();
        let pages = dense_pages(&list.iter().map(|(h, _)| *h).collect::<Vec<_>>(), 2);
        let statics = list.iter().filter(|(h, _)| is_static(*h)).count();
        eprintln!(
            "  k={k:#04x}: {} holders, {} nodes covered, {} dense pages, {statics} static",
            list.len(),
            covered.len(),
            pages.len()
        );
        // Prefer high coverage with few holders per node (a real container
        // references each node about once).
        let score = covered.len() as f64 - (list.len() as f64 - covered.len() as f64) * 0.5;
        if best.as_ref().is_none_or(|(_, b)| {
            let bc: HashSet<u64> = b.iter().map(|(_, s)| *s).collect();
            score > bc.len() as f64 - (b.len() as f64 - bc.len() as f64) * 0.5
        }) {
            best = Some((k, list.clone()));
        }
    }
    let Some((k, owner_slots)) = best else {
        eprintln!("no external holders for any k — the nodes are only referenced from within their pool");
        return;
    };
    let mut owners: Vec<u64> = owner_slots.iter().map(|(h, _)| *h).collect();
    owners.sort_unstable();
    owners.dedup();
    eprintln!(
        "best k={k:#04x}: {} external holder slots, span {:#x}..{:#x}",
        owners.len(),
        owners[0],
        owners[owners.len() - 1]
    );
    let mut stride_h: HashMap<u64, usize> = HashMap::new();
    for w in owners.windows(2) {
        *stride_h.entry(w[1] - w[0]).or_default() += 1;
    }
    let mut sv: Vec<_> = stride_h.into_iter().collect();
    sv.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    eprintln!("  gaps between consecutive owner slots: {:?}", &sv[..sv.len().min(6)]);
    for h in owners.iter().filter(|h| is_static(**h)) {
        eprintln!("  *** STATIC owner slot {h:#x} = exe+{:#x}", h - mbase);
    }

    // ---- 5. Keep going up with the same exclusion, until static.
    let mut level_targets = owners.clone();
    let mut excluded = node_pages.clone();
    for level in 3..=6 {
        let pages = dense_pages(&level_targets, 1);
        excluded.extend(pages.iter());
        // Owners are slots inside some struct; try starts up to 0x80 before.
        let mut tmap: HashMap<u64, u64> = HashMap::new();
        for s in &level_targets {
            for k in (0..=0x80u64).step_by(8) {
                tmap.insert(s - k, *s);
            }
        }
        let t: Vec<u64> = tmap.keys().copied().collect();
        let found = range_scan(&p, &exact_ranges(&t));
        let ext: Vec<(u64, u64)> = found
            .into_iter()
            .filter(|(h, _)| !excluded.contains(&(h >> 20)))
            .collect();
        let statics: Vec<u64> = ext.iter().map(|(h, _)| *h).filter(|h| is_static(*h)).collect();
        let mut hs: Vec<u64> = ext.iter().map(|(h, _)| *h).collect();
        hs.sort_unstable();
        hs.dedup();
        eprintln!(
            "level {level}: {} external holders ({} distinct slots), {} static",
            ext.len(),
            hs.len(),
            statics.len()
        );
        for s in &statics {
            eprintln!("  *** STATIC {s:#x} = exe+{:#x}", s - mbase);
        }
        if !statics.is_empty() || hs.is_empty() {
            break;
        }
        if hs.len() > 2000 {
            hs.truncate(2000);
        }
        level_targets = hs;
    }
}
