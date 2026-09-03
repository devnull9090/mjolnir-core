//! Walking the tag cache from its static root, node by node.
//!
//! `tag_cache_decode.rs` established the shape. The root struct `T` holds an
//! array of 80-byte map records from `+0x40`, each with a head-node pointer
//! at `+0x48`. A node, relative to the slot that holds its descriptor, is:
//!
//! ```text
//! -0x70 link   -0x60 link   -0x50 u64 key hash   -0x48 0x02000000
//! -0x38 u32    -0x20 0x7fffffff   -0x18/-0x10 shared back-pointers
//! -0x08 key object*   +0x00 descriptor*   +0x08 1
//! ```
//!
//! This walks it: every record's chain via the two links (a bounded
//! traversal, no scan), collecting each node's hash, descriptor and key
//! object. It reports how many nodes there are, how many hold our known
//! descriptors, dumps `(hash, tag path)` pairs for offline hash-function
//! identification, and reads the key objects to see whether they carry the
//! tag's name in the clear. Either the hash or the key object closes the
//! chase: static → T → record → nodes → node for tag → descriptor → buffer.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`,
//! `MJOLNIR_NAMEINDEX`; writes `MJOLNIR_HASHES_OUT` if set.

mod common;

use std::collections::{HashMap, HashSet, VecDeque};

use common::*;
use tag_editor_lib::catalog::Catalog;

const ROOT_RVAS: [u64; 2] = [0xd3ec3a0, 0xd3ee678];
const RECORDS_AT: u64 = 0x40;
const RECORD: u64 = 0x50;
const REC_HEAD: u64 = 0x48;
const REC_COUNT: u64 = 0x18;

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

/// A node, addressed by its descriptor slot.
#[derive(Clone, Copy)]
struct Node {
    slot: u64,
    link_a: u64,
    link_b: u64,
    hash: u64,
    small: u32,
    key: u64,
    desc: u64,
    flag: u64,
}

fn read_node(p: &blam_live::Process, slot: u64) -> Option<Node> {
    let w = p.read(slot - 0x70, 0x80).ok()?;
    if w.len() < 0x80 {
        return None;
    }
    Some(Node {
        slot,
        link_a: u64_at(&w, 0x00),
        link_b: u64_at(&w, 0x10),
        hash: u64_at(&w, 0x20),
        small: u32_at(&w, 0x38),
        key: u64_at(&w, 0x68),
        desc: u64_at(&w, 0x70),
        flag: u64_at(&w, 0x78),
    })
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS, MJOLNIR_RESIDENT, MJOLNIR_NAMEINDEX"]
fn tag_cache_walk() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, _) = p.module(blam_live::GAME_EXE).expect("module");

    let t = targets(&p);
    let desc_of: HashMap<u64, usize> = t.descriptors.iter().copied().collect();
    let slot_set: HashSet<u64> = t.slots.iter().copied().collect();

    // ---- 1. Where a link points within a node: the offset `k` such that
    // `link + k` is a known slot, across all known slots' links.
    let mut k_hist: HashMap<i64, usize> = HashMap::new();
    for s in &t.slots {
        let Some(n) = read_node(&p, *s) else { continue };
        for l in [n.link_a, n.link_b] {
            if !heapish(l) {
                continue;
            }
            for s2 in &t.slots {
                let d = *s2 as i64 - l as i64;
                if d.abs() <= 0x100 {
                    *k_hist.entry(d).or_default() += 1;
                }
            }
        }
    }
    let mut kv: Vec<_> = k_hist.into_iter().collect();
    kv.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    eprintln!("link target -> slot offset k: {:?}", &kv[..kv.len().min(5)]);
    let k = kv.first().map(|(k, _)| *k).unwrap_or(0x70);
    eprintln!("using k = {k:#x} (a link points at node start; slot = node + k)");

    let mut all_pairs: Vec<(u64, usize, String)> = Vec::new(); // (hash, tag, path)
    let mut total_nodes = 0usize;
    let mut total_with_desc = 0usize;
    let mut total_known = 0usize;

    for rva in ROOT_RVAS {
        let root = u64_at(&p.read(mbase + rva, 8).unwrap(), 0);
        eprintln!("========== exe+{rva:#x} -> T @ {root:#x}");
        let tw = p.read(root, 0x1000).expect("T");
        // ---- 2. Records: walk while the shape holds (head heapish or 0 and
        // the shared word pattern at +0x08).
        let mut rec = RECORDS_AT;
        let mut records = 0usize;
        while rec + RECORD <= tw.len() as u64 {
            let head = u64_at(&tw, (rec + REC_HEAD) as usize);
            let count = u32_at(&tw, (rec + REC_COUNT) as usize);
            let tagword = u64_at(&tw, (rec + 8) as usize);
            if tagword != 0x0000_0004_0000_0000 && head == 0 {
                break;
            }
            records += 1;
            if heapish(head) {
                // ---- 3. Traverse from the head.
                let start_slot = (head as i64 + k) as u64;
                let mut seen: HashSet<u64> = HashSet::new();
                let mut q: VecDeque<u64> = VecDeque::new();
                q.push_back(start_slot);
                seen.insert(start_slot);
                let mut nodes: Vec<Node> = Vec::new();
                while let Some(s) = q.pop_front() {
                    if nodes.len() >= 50_000 {
                        break;
                    }
                    let Some(n) = read_node(&p, s) else { continue };
                    nodes.push(n);
                    for l in [n.link_a, n.link_b] {
                        if heapish(l) {
                            let ns = (l as i64 + k) as u64;
                            if seen.insert(ns) {
                                q.push_back(ns);
                            }
                        }
                    }
                }
                let with_desc = nodes.iter().filter(|n| heapish(n.desc)).count();
                let known = nodes.iter().filter(|n| desc_of.contains_key(&n.desc)).count();
                let known_slots = nodes.iter().filter(|n| slot_set.contains(&n.slot)).count();
                eprintln!(
                    "  record {records:>2} @ T+{rec:#x}: count {count:>6}, head {head:#x}: walked {} nodes, {with_desc} with a pointer at +0, {known} known descriptors, {known_slots} known slots",
                    nodes.len()
                );
                total_nodes += nodes.len();
                total_with_desc += with_desc;
                total_known += known;
                for n in &nodes {
                    if let Some(i) = desc_of.get(&n.desc) {
                        let path = catalog
                            .entry(*i)
                            .map(|e| format!("{}-{}", e.short, e.group))
                            .unwrap_or_default();
                        all_pairs.push((n.hash, *i, path));
                    }
                }
            } else if count > 0 {
                eprintln!("  record {records:>2} @ T+{rec:#x}: count {count:>6}, no head");
            }
            rec += RECORD;
        }
        eprintln!("  {records} records");
    }
    eprintln!(
        "TOTAL: {total_nodes} nodes walked, {total_with_desc} with a +0 pointer, {total_known} of our {} known descriptors reached",
        desc_of.len()
    );

    // ---- 4. Pairs for offline hash identification.
    all_pairs.sort();
    all_pairs.dedup();
    eprintln!("{} (hash, tag) pairs", all_pairs.len());
    for (h, i, path) in all_pairs.iter().take(6) {
        eprintln!("  {h:016x}  {i:5}  {path}");
    }
    if let Ok(out) = std::env::var("MJOLNIR_HASHES_OUT") {
        let rows: Vec<serde_json::Value> = all_pairs
            .iter()
            .map(|(h, i, path)| serde_json::json!({ "hash": format!("{h:016x}"), "tag": i, "path": path }))
            .collect();
        std::fs::write(&out, serde_json::to_string_pretty(&rows).unwrap()).unwrap();
        eprintln!("  wrote {out}");
    }

    // ---- 5. The key object: what does slot-0x08 point at? Read 0x80 and
    // look for the tag's path as UTF-16 or UTF-8, an FName, or pointers.
    let mut shown = 0usize;
    for s in &t.slots {
        if shown >= 3 {
            break;
        }
        let Some(n) = read_node(&p, *s) else { continue };
        let Some(i) = desc_of.get(&n.desc) else { continue };
        let path = catalog.entry(*i).map(|e| e.short.to_ascii_lowercase()).unwrap_or_default();
        if !heapish(n.key) {
            continue;
        }
        let Ok(kw) = p.read(n.key, 0x80) else { continue };
        let utf16: String = kw
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]))
            .take_while(|u| *u != 0)
            .map(|u| char::from_u32(u as u32).unwrap_or('?'))
            .collect();
        let ascii: String = kw.iter().take_while(|b| **b != 0).map(|b| *b as char).collect();
        let leaf = path.rsplit('/').next().unwrap_or("");
        eprintln!(
            "  key object of tag {i} @ {:#x}: utf16 {:?} ascii {:?}  (tag leaf {leaf:?}; hash {:016x}, small {}, flag {})",
            n.key,
            &utf16[..utf16.len().min(40)],
            &ascii[..ascii.len().min(40)],
            n.hash,
            n.small,
            n.flag
        );
        for off in (0..0x40usize).step_by(8) {
            let v = u64_at(&kw, off);
            if v != 0 {
                eprintln!("      +{off:#04x}: {v:016x}{}", if heapish(v) { "  heap" } else { "" });
            }
        }
        shown += 1;
    }
}
