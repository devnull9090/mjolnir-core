//! The acceptance test: find a tag's buffer with no scan at all.
//!
//! The chain, fully known:
//!
//! ```text
//! .data global  →  root struct T  →  80-byte map records (+0x40, stride 0x50)
//!   → record head node (+0x48)  →  walk nodes via links (-0x70 / -0x60)
//!   → nodes whose key hash (-0x50) == FPackageId(tag)
//!   → the one holding a buffer descriptor (+0x00)  →  descriptor.ptr = base
//!   → field at base + file_offset
//! ```
//!
//! A first version kept one node per key and resolved 1 of 362 resident tags:
//! a package has **several** nodes — its chunks — sharing one package id,
//! and only the bulk-data node carries the descriptor. So this keeps every
//! node per key, validates each candidate by the descriptor's shape and by
//! its pointer, and reports which node fields distinguish the one that holds
//! the data, so production can select it without trying all of them.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`.

mod common;

use std::collections::{BTreeMap, HashMap, HashSet, VecDeque};

use common::*;
use tag_editor_lib::catalog::Catalog;

const ROOT_RVAS: [u64; 2] = [0xd3ec3a0, 0xd3ee678];
const RECORDS_AT: u64 = 0x40;
const RECORD: u64 = 0x50;
const REC_HEAD: u64 = 0x48;
/// A link points at a node start; the descriptor slot is `node + 0x60`.
const SLOT_FROM_NODE: u64 = 0x60;

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

/// One node, fields relative to its slot (`node + 0x60`).
#[derive(Clone, Copy)]
struct Node {
    node: u64,
    hash: u64,
    small: u32,     // -0x38
    c48: u64,       // -0x48
    c20: u64,       // -0x20
    key: u64,       // -0x08
    slot_val: u64,  // +0x00
    flag: u64,      // +0x08
}

fn walk_cache(p: &blam_live::Process, mbase: u64) -> (HashMap<u64, Vec<Node>>, usize) {
    let mut by_hash: HashMap<u64, Vec<Node>> = HashMap::new();
    let mut seen: HashSet<u64> = HashSet::new();
    let mut nodes = 0usize;
    for rva in ROOT_RVAS {
        let Ok(rb) = p.read(mbase + rva, 8) else { continue };
        let root = u64_at(&rb, 0);
        let Ok(tw) = p.read(root, 0x1000) else { continue };
        let mut rec = RECORDS_AT;
        while rec + RECORD <= tw.len() as u64 {
            let head = u64_at(&tw, (rec + REC_HEAD) as usize);
            let tagword = u64_at(&tw, (rec + 8) as usize);
            if tagword != 0x0000_0004_0000_0000 && head == 0 {
                break;
            }
            rec += RECORD;
            if !heapish(head) {
                continue;
            }
            let mut q: VecDeque<u64> = VecDeque::new();
            if seen.insert(head) {
                q.push_back(head);
            }
            while let Some(node) = q.pop_front() {
                let slot = node + SLOT_FROM_NODE;
                let Ok(w) = p.read(slot - 0x70, 0x80) else { continue };
                if w.len() < 0x80 {
                    continue;
                }
                nodes += 1;
                let n = Node {
                    node,
                    hash: u64_at(&w, 0x20),
                    small: u32_at(&w, 0x38),
                    c48: u64_at(&w, 0x28),
                    c20: u64_at(&w, 0x50),
                    key: u64_at(&w, 0x68),
                    slot_val: u64_at(&w, 0x70),
                    flag: u64_at(&w, 0x78),
                };
                if n.hash != 0 {
                    by_hash.entry(n.hash).or_default().push(n);
                }
                for l in [u64_at(&w, 0x00), u64_at(&w, 0x10)] {
                    if heapish(l) && seen.insert(l) {
                        q.push_back(l);
                    }
                }
            }
        }
    }
    (by_hash, nodes)
}

/// The buffer base a candidate slot value leads to, if it is a shape-valid
/// descriptor (`+0xC == 1`, `+0x10 == 0`, `+0x18 == 00 01`) with a heap ptr.
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

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn tag_cache_lookup() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, _) = p.module(blam_live::GAME_EXE).expect("module");
    let resident = load_resident();

    let t0 = std::time::Instant::now();
    let (by_hash, nodes) = walk_cache(&p, mbase);
    eprintln!(
        "walked {nodes} nodes in {:.2}s; {} distinct keys",
        t0.elapsed().as_secs_f32(),
        by_hash.len()
    );
    let mut per_key: BTreeMap<usize, usize> = BTreeMap::new();
    for v in by_hash.values() {
        *per_key.entry(v.len()).or_default() += 1;
    }
    eprintln!("nodes per key: {per_key:?}");

    // ---- Every catalog tag: does some node under its id hold a valid
    // descriptor? That set is the cache's own answer to "resident".
    let mut tags_with_node = 0usize;
    let mut tags_with_desc = 0usize;
    for e in &catalog.tags {
        if let Some(ns) = by_hash.get(&package_id(&e.short, &e.group)) {
            tags_with_node += 1;
            if ns.iter().any(|n| descriptor_base(&p, n.slot_val).is_some()) {
                tags_with_desc += 1;
            }
        }
    }
    eprintln!(
        "{tags_with_node} of {} catalog tags have a node; {tags_with_desc} have a node holding a valid descriptor (census-resident: {})",
        catalog.tags.len(),
        resident.len()
    );

    // ---- Acceptance: each census-resident tag, id -> nodes -> the one whose
    // descriptor's pointer equals the census base.
    let mut exact = 0usize;
    let mut has_desc_but_wrong = 0usize;
    let mut no_desc = 0usize;
    let mut missing = 0usize;
    // Which node fields mark the descriptor-holding node vs its siblings?
    let mut holder_fields: HashMap<&str, HashMap<u64, usize>> = HashMap::new();
    let mut sibling_fields: HashMap<&str, HashMap<u64, usize>> = HashMap::new();
    let mut examples = 0usize;
    for (base, (i, _, _)) in &resident {
        let Some(e) = catalog.entry(*i) else { continue };
        let id = package_id(&e.short, &e.group);
        let Some(ns) = by_hash.get(&id) else {
            missing += 1;
            continue;
        };
        let mut found = false;
        let mut any_desc = false;
        for n in ns {
            match descriptor_base(&p, n.slot_val) {
                Some(b) if b == *base => {
                    found = true;
                    for (name, v) in [("small", n.small as u64), ("c48", n.c48), ("c20", n.c20), ("flag", n.flag), ("key_nonnull", (n.key != 0) as u64)] {
                        *holder_fields.entry(name).or_default().entry(v).or_default() += 1;
                    }
                }
                Some(_) => any_desc = true,
                None => {
                    for (name, v) in [("small", n.small as u64), ("c48", n.c48), ("c20", n.c20), ("flag", n.flag), ("key_nonnull", (n.key != 0) as u64)] {
                        *sibling_fields.entry(name).or_default().entry(v).or_default() += 1;
                    }
                }
            }
        }
        if found {
            exact += 1;
            if examples < 4 {
                eprintln!(
                    "  OK  {id:016x} {} nodes -> base {base:#x}  {}",
                    ns.len(),
                    e.short
                );
                examples += 1;
            }
        } else if any_desc {
            has_desc_but_wrong += 1;
        } else {
            no_desc += 1;
        }
    }
    eprintln!(
        "ACCEPTANCE over {} census-resident tags: {exact} resolved to the census base with no scan; {has_desc_but_wrong} had a descriptor with another base; {no_desc} had nodes but no descriptor; {missing} no node",
        resident.len()
    );
    let top = |m: &HashMap<u64, usize>| {
        let mut v: Vec<_> = m.iter().map(|(k, n)| (*k, *n)).collect();
        v.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        v.truncate(4);
        v.iter().map(|(k, n)| format!("{k:#x}x{n}")).collect::<Vec<_>>().join(" ")
    };
    eprintln!("node fields — descriptor-holding node vs sibling nodes of the same package:");
    for name in ["small", "c48", "c20", "flag", "key_nonnull"] {
        eprintln!(
            "  {name:<12} holder: {}   siblings: {}",
            holder_fields.get(name).map(top).unwrap_or_default(),
            sibling_fields.get(name).map(top).unwrap_or_default()
        );
    }
    assert!(exact > 0, "no resident tag resolved through the cache");
}
