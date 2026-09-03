//! Decoding the tag cache from its static roots.
//!
//! `tag_cache_static.rs` found two `.data` globals (`exe+0xd3ec3a0`,
//! `exe+0xd3ee678`) each pointing at an instance of one struct type whose
//! field `+0x808` points into a node region — the containers of the slots
//! that hold buffer descriptors. This decodes that chain end to end:
//!
//! 1. the root struct `T` (layout around `+0x808`: is it a hash map, a
//!    sparse array, a plain array?);
//! 2. the node container: extent, element stride, and each node's fields;
//! 3. the node's **identity** — tested against keys unavailable to earlier
//!    probes: the runtime tag index (name-table position) and the name
//!    table's own `FString` data pointers, besides FNames and `UObject`s.
//!
//! If a node names its tag, the chase closes: static → T → nodes → node by
//! tag → descriptor → buffer, and the sweep can retire.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`,
//! `MJOLNIR_NAMEINDEX`.

mod common;

use std::collections::{BTreeMap, HashMap, HashSet};

use common::*;
use tag_editor_lib::{catalog::Catalog, present};

const ROOT_RVAS: [u64; 2] = [0xd3ec3a0, 0xd3ee678];
const NODE_FIELD: u64 = 0x808;

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS, MJOLNIR_RESIDENT, MJOLNIR_NAMEINDEX"]
fn tag_cache_decode() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, msize) = p.module(blam_live::GAME_EXE).expect("module");
    let (reader, _) = present::attach(&p, catalog.paks(), None).expect("reader");
    let is_static = |a: u64| a >= mbase && a < mbase + msize;

    let t = targets(&p);
    let desc_of: HashMap<u64, usize> = t.descriptors.iter().copied().collect();
    let slot_set: HashSet<u64> = t.slots.iter().copied().collect();
    let resident = load_resident();
    let base_of: HashMap<u64, usize> = resident.iter().map(|(b, (i, _, _))| (*b, *i)).collect();
    let tags = tag_objects(&p, &catalog);

    // Runtime tag index and the name table's FString data pointers.
    let ni: Vec<serde_json::Value> = serde_json::from_str(
        &std::fs::read_to_string(std::env::var("MJOLNIR_NAMEINDEX").unwrap()).unwrap(),
    )
    .unwrap();
    let mut pos_of: HashMap<usize, usize> = HashMap::new();
    for (pos, row) in ni.iter().enumerate() {
        if let Some(i) = row["tag"].as_u64() {
            pos_of.insert(i as usize, pos);
        }
    }
    let objects = reader.table.walk(&p).expect("walk");
    let subsystem = objects
        .iter()
        .find(|o| {
            reader.name_at(&p, o.class).ok().as_deref()
                == Some("BlamCookedTagReferencesEngineSubsystem")
                && !reader.pool.text(&p, o.name_id).map(|n| n.starts_with("Default__")).unwrap_or(true)
        })
        .map(|o| o.object)
        .expect("subsystem");
    let sh = p.read(subsystem, 0x60).unwrap();
    let names_data = u64_at(&sh, 0x30);
    let names_num = u32_at(&sh, 0x38) as usize;
    let names = p.read(names_data, names_num * 16).unwrap();
    // tag index -> its FString's TCHAR* in the name table
    let mut str_ptr_of: HashMap<usize, u64> = HashMap::new();
    let mut tag_of_str_ptr: HashMap<u64, usize> = HashMap::new();
    for pos in 0..names_num {
        if let Some(i) = ni[pos]["tag"].as_u64() {
            let sp = u64_at(&names, pos * 16);
            str_ptr_of.insert(i as usize, sp);
            tag_of_str_ptr.insert(sp, i as usize);
        }
    }
    // slot -> tag (via the descriptor it holds)
    let mut tag_of_slot: HashMap<u64, usize> = HashMap::new();
    for s in &t.slots {
        if let Ok(b) = p.read(*s, 8) {
            if let Some(i) = desc_of.get(&u64_at(&b, 0)) {
                tag_of_slot.insert(*s, *i);
            }
        }
    }

    for rva in ROOT_RVAS {
        let root_slot = mbase + rva;
        let Ok(rb) = p.read(root_slot, 8) else { continue };
        let root = u64_at(&rb, 0);
        eprintln!("========== root exe+{rva:#x} -> T @ {root:#x}");

        // ---- 1. T around the node field.
        let Ok(tw) = p.read(root, 0x900) else { continue };
        eprintln!("T fields +0x7c0..+0x880 (and any pointer into a node page anywhere in T):");
        let node_pages = dense_pages(&t.slots, 2);
        for off in (0x7c0..0x880usize).step_by(8) {
            let v = u64_at(&tw, off);
            let note = if v == 0 {
                String::new()
            } else if is_static(v) {
                format!("  static exe+{:#x}", v - mbase)
            } else if node_pages.contains(&(v >> 20)) {
                "  -> NODE PAGE".into()
            } else if heapish(v) {
                "  heap".into()
            } else {
                format!("  u32 {} | {}", v & 0xffff_ffff, v >> 32)
            };
            eprintln!("    +{off:#05x}: {v:016x}{note}");
        }
        let node_ptrs: Vec<(usize, u64)> = (0..tw.len() - 7)
            .step_by(8)
            .map(|o| (o, u64_at(&tw, o)))
            .filter(|(_, v)| node_pages.contains(&(v >> 20)))
            .collect();
        eprintln!("  pointers into node pages anywhere in T: {:x?}", node_ptrs);

        // ---- 2. The node container: where the known slots sit relative to
        // the +0x808 target, and the stride between them.
        let container = u64_at(&tw, NODE_FIELD as usize);
        if !heapish(container) {
            eprintln!("  +0x808 is not a pointer here");
            continue;
        }
        let mut rel: Vec<(u64, usize)> = t
            .slots
            .iter()
            .filter(|s| s.abs_diff(container) < 0x200000)
            .filter_map(|s| tag_of_slot.get(s).map(|i| (*s, *i)))
            .collect();
        rel.sort_unstable();
        eprintln!(
            "  container {container:#x}: {} known slots within 2 MB, offsets {:x?}",
            rel.len(),
            rel.iter().map(|(s, _)| *s as i64 - container as i64).take(12).collect::<Vec<_>>()
        );
        let mut gaps: BTreeMap<u64, usize> = BTreeMap::new();
        for w in rel.windows(2) {
            *gaps.entry(w[1].0 - w[0].0).or_default() += 1;
        }
        let mut g: Vec<_> = gaps.into_iter().collect();
        g.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        eprintln!("  gaps between consecutive known slots: {:?}", &g[..g.len().min(8)]);

        // ---- 3. Node identity. For each known slot, read a window around
        // it and test every field against every key we have for its tag.
        let mut hits: HashMap<(&str, i64), usize> = HashMap::new();
        let mut checked = 0usize;
        for (s, i) in &rel {
            let Some(tg) = tags.get(i) else { continue };
            checked += 1;
            let pos = pos_of.get(i).copied();
            let sp = str_ptr_of.get(i).copied();
            let Ok(w) = p.read(s - 0x80, 0x100) else { continue };
            for off in (0..w.len() - 3).step_by(4) {
                let r = off as i64 - 0x80;
                let v = u32_at(&w, off);
                if v == 0 {
                    continue;
                }
                if Some(v as usize) == pos {
                    *hits.entry(("tag index (u32)", r)).or_default() += 1;
                }
                if v == tg.name_id {
                    *hits.entry(("object FName", r)).or_default() += 1;
                }
                if v == tg.package_name_id {
                    *hits.entry(("package FName", r)).or_default() += 1;
                }
                if v as usize == *i {
                    *hits.entry(("catalog index", r)).or_default() += 1;
                }
            }
            for off in (0..w.len() - 7).step_by(8) {
                let r = off as i64 - 0x80;
                let v = u64_at(&w, off);
                if v == 0 {
                    continue;
                }
                if Some(v) == sp {
                    *hits.entry(("name-table TCHAR*", r)).or_default() += 1;
                }
                if pos.is_some_and(|pp| v == names_data + (pp as u64) * 16) {
                    *hits.entry(("name-table element*", r)).or_default() += 1;
                }
                if v == tg.uobject {
                    *hits.entry(("UObject*", r)).or_default() += 1;
                }
                if v == tg.class {
                    *hits.entry(("class*", r)).or_default() += 1;
                }
                if base_of.get(&v) == Some(i) {
                    *hits.entry(("buffer base", r)).or_default() += 1;
                }
                if desc_of.get(&v) == Some(i) {
                    *hits.entry(("descriptor", r)).or_default() += 1;
                }
                if slot_set.contains(&v) && v != *s {
                    *hits.entry(("other slot (link)", r)).or_default() += 1;
                }
            }
        }
        let mut hv: Vec<_> = hits.into_iter().collect();
        hv.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        eprintln!("  node identity, {checked} nodes checked (key, offset rel. to slot) -> count:");
        for ((k, r), n) in hv.iter().take(16) {
            eprintln!("    {n:>3}  {k:<20} @ {r:+#x}");
        }

        // ---- 4. Two nodes raw, annotated, 0x80 before to 0x40 after the slot.
        for (s, i) in rel.iter().take(2) {
            let short = catalog.entry(*i).map(|e| e.short.as_str()).unwrap_or("?");
            eprintln!("  node for tag {i} ({short}), slot {s:#x}:");
            let Ok(w) = p.read(s - 0x80, 0xc0) else { continue };
            for off in (0..w.len() - 7).step_by(8) {
                let v = u64_at(&w, off);
                let r = off as i64 - 0x80;
                let note = if v == 0 {
                    String::new()
                } else if desc_of.contains_key(&v) {
                    "  <- DESCRIPTOR".into()
                } else if slot_set.contains(&v) {
                    "  (link to another slot)".into()
                } else if tag_of_str_ptr.contains_key(&v) {
                    format!("  <- name-table string of tag {}", tag_of_str_ptr[&v])
                } else if is_static(v) {
                    format!("  static exe+{:#x}", v - mbase)
                } else if node_pages.contains(&(v >> 20)) {
                    "  -> node page".into()
                } else if heapish(v) {
                    "  heap".into()
                } else {
                    format!("  u32 {} | {}", v & 0xffff_ffff, v >> 32)
                };
                eprintln!("    {r:+#05x}: {v:016x}{note}");
            }
        }
    }
}
