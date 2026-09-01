//! Finding the tag cache from the top instead of the bottom.
//!
//! Walking *up* from a buffer failed: descriptors are referenced from small
//! inline pointer buffers in assorted objects, with no identity field and no
//! owner chain to static memory (see `tag_cache_nodes.rs`, `tag_cache_owner.rs`).
//!
//! But the Blam runtime lives in `/Script/BlamSynchronization` — the same
//! module as the tag asset classes — so its manager is very likely a `UObject`
//! too, probably a subsystem singleton. A `UObject` is reachable **by class
//! name** through the object table the reader already walks in a second:
//! a root that needs no static address and no signature, and survives every
//! relaunch for free.
//!
//! So: list every `Blam*` class that is not a tag asset, and from each live
//! instance search *downward* — a bounded breadth-first walk over pointer
//! fields — for anything that reaches a known descriptor, a slot holding one,
//! or a buffer base. Whatever reaches many of them is the cache, and the path
//! of offsets that got there is the pointer chase.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`.

mod common;

use std::collections::{HashMap, HashSet, VecDeque};

use common::*;
use tag_editor_lib::{catalog::Catalog, present};

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn tag_cache_by_name() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (reader, _) = present::attach(&p, catalog.paks(), None).expect("reader");

    // ---- Targets: descriptors, the slots holding them, and buffer bases.
    let resident = load_resident();
    let descs = descriptors(&p, &resident);
    let desc_set: HashSet<u64> = descs.iter().map(|(a, _)| *a).collect();
    let desc_addrs: Vec<u64> = desc_set.iter().copied().collect();
    let slot_set: HashSet<u64> = range_scan(&p, &exact_ranges(&desc_addrs))
        .into_iter()
        .map(|(h, _)| h)
        .collect();
    let base_set: HashSet<u64> = resident.keys().copied().collect();
    eprintln!(
        "targets: {} descriptors, {} slots, {} bases",
        desc_set.len(),
        slot_set.len(),
        base_set.len()
    );

    // ---- Every non-tag-asset class whose name mentions Blam, with instances.
    let objects = reader.table.walk(&p).expect("walk");
    let mut class_name: HashMap<u64, String> = HashMap::new();
    let mut instances: HashMap<u64, Vec<u64>> = HashMap::new(); // class -> objects
    for o in &objects {
        let name = class_name
            .entry(o.class)
            .or_insert_with(|| reader.name_at(&p, o.class).unwrap_or_default());
        if !name.contains("Blam") || name.ends_with("TagDataAsset") {
            continue;
        }
        // Skip class default objects; we want live instances.
        if reader
            .pool
            .text(&p, o.name_id)
            .map(|n| n.starts_with("Default__"))
            .unwrap_or(true)
        {
            continue;
        }
        instances.entry(o.class).or_default().push(o.object);
    }
    let mut listing: Vec<(&String, usize)> = instances
        .iter()
        .map(|(c, v)| (&class_name[c], v.len()))
        .collect();
    listing.sort_by(|a, b| a.0.cmp(b.0));
    eprintln!("{} Blam classes with live non-CDO instances:", listing.len());
    for (n, c) in &listing {
        eprintln!("  {c:>5}  {n}");
    }

    // ---- Downward BFS from each candidate root. Prefer singletons: a cache
    // has one instance. Record, per root, how many targets it reaches and by
    // what offset path (first hit's path is enough to show the shape).
    const ROOT_WINDOW: usize = 0x4000;
    const CHILD_WINDOW: usize = 0x1000;
    const MAX_DEPTH: usize = 3;
    let fanout = [768usize, 96, 24];

    struct Reach {
        class: String,
        root: u64,
        descs: usize,
        slots: usize,
        bases: usize,
        first_path: String,
        visited: usize,
    }
    let mut results: Vec<Reach> = Vec::new();

    for (class, objs) in &instances {
        if objs.len() > 8 {
            continue; // not a manager
        }
        for &root in objs {
            let mut seen: HashSet<u64> = HashSet::new();
            let mut hit_d = HashSet::new();
            let mut hit_s = HashSet::new();
            let mut hit_b = HashSet::new();
            let mut first_path = String::new();
            // (address, depth, path so far)
            let mut q: VecDeque<(u64, usize, String)> = VecDeque::new();
            q.push_back((root, 0, String::from("root")));
            seen.insert(root);
            while let Some((addr, depth, path)) = q.pop_front() {
                let win = if depth == 0 { ROOT_WINDOW } else { CHILD_WINDOW };
                let Ok(w) = p.read(addr, win) else { continue };
                let mut spawned = 0usize;
                for off in (0..w.len().saturating_sub(7)).step_by(8) {
                    let v = u64_at(&w, off);
                    let here = addr + off as u64;
                    // The slot itself: this object holds a descriptor pointer.
                    if slot_set.contains(&here) {
                        hit_s.insert(here);
                    }
                    if v == 0 {
                        continue;
                    }
                    let mut noted = false;
                    if desc_set.contains(&v) {
                        hit_d.insert(v);
                        noted = true;
                    }
                    if base_set.contains(&v) {
                        hit_b.insert(v);
                        noted = true;
                    }
                    if noted && first_path.is_empty() {
                        first_path = format!("{path} +{off:#x}");
                    }
                    if depth < MAX_DEPTH && heapish(v) && spawned < fanout[depth] && seen.insert(v) {
                        spawned += 1;
                        q.push_back((v, depth + 1, format!("{path} +{off:#x} ->")));
                    }
                }
            }
            if !hit_d.is_empty() || !hit_s.is_empty() || !hit_b.is_empty() {
                results.push(Reach {
                    class: class_name[class].clone(),
                    root,
                    descs: hit_d.len(),
                    slots: hit_s.len(),
                    bases: hit_b.len(),
                    first_path,
                    visited: seen.len(),
                });
            }
        }
    }
    results.sort_by_key(|r| std::cmp::Reverse(r.descs + r.slots + r.bases));
    eprintln!("roots that reach a target within {MAX_DEPTH} hops:");
    for r in results.iter().take(15) {
        eprintln!(
            "  {} @ {:#x}: {} descriptors, {} slots, {} bases (visited {}); first via {}",
            r.class, r.root, r.descs, r.slots, r.bases, r.visited, r.first_path
        );
    }
    if results.is_empty() {
        eprintln!("no Blam object reaches a descriptor, slot or buffer within {MAX_DEPTH} hops");
    }
}
