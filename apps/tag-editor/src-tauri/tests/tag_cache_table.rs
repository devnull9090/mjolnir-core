//! Is there a Blam tag-instance table holding buffer bases by tag index?
//!
//! The static-rooted map resolves ~10 % of resident tags exactly: it is a
//! loader-side cache that lets go of a buffer once loading is done, while
//! the buffer lives on. Something in the Blam simulation must still be able
//! to find every live tag's data — classic Halo did it with a tag-instance
//! table, one fixed-size entry per tag holding the data pointer.
//!
//! The earlier position fit tested the *bases* against the runtime tag
//! index, which could never fit (bases are allocations). This tests the
//! **slots that hold a base**: the level-0 pointer scan found 262 of them
//! and only 167 were descriptors; the rest, if they sit at a fixed stride by
//! tag index, are that table. A `T`-independent, `FPackageId`-independent
//! route: `table[index] → base`.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`,
//! `MJOLNIR_NAMEINDEX`.

mod common;

use std::collections::{BTreeMap, HashMap, HashSet};

use common::*;
use tag_editor_lib::catalog::Catalog;

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS, MJOLNIR_RESIDENT, MJOLNIR_NAMEINDEX"]
fn tag_cache_table() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, msize) = p.module(blam_live::GAME_EXE).expect("module");
    let is_static = |a: u64| a >= mbase && a < mbase + msize;

    let resident = load_resident();
    let t = targets(&p);
    let desc_set: HashSet<u64> = t.descriptors.iter().map(|(a, _)| *a).collect();
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

    // ---- Every slot holding a resident base that is NOT a descriptor.
    let bases: Vec<u64> = resident.keys().copied().collect();
    let holders = range_scan(&p, &exact_ranges(&bases));
    let mut others: Vec<(u64, usize, u64)> = Vec::new(); // (slot, catalog idx, base)
    for (h, v) in &holders {
        if desc_set.contains(h) {
            continue;
        }
        others.push((*h, resident[v].0, *v));
    }
    eprintln!(
        "{} holders of a resident base; {} are not descriptors",
        holders.len(),
        others.len()
    );
    let mut align: HashMap<u64, usize> = HashMap::new();
    for (h, _, _) in &others {
        *align.entry(h % 32).or_default() += 1;
    }
    eprintln!("  non-descriptor holder mod 32: {align:?}");
    let statics = others.iter().filter(|(h, _, _)| is_static(*h)).count();
    eprintln!("  in static data: {statics}");

    // ---- Fit slot address against runtime tag index and catalog index,
    // per region.
    for (label, key): (&str, &dyn Fn(usize) -> Option<usize>) in [
        ("runtime tag index", &|i| pos_of.get(&i).copied()),
        ("catalog index", &|i| Some(i)),
    ] {
        let pts: Vec<(u64, usize)> = others
            .iter()
            .filter_map(|(h, i, _)| key(*i).map(|k| (*h, k)))
            .collect();
        let mut by_page: BTreeMap<u64, Vec<(u64, usize)>> = BTreeMap::new();
        for pt in &pts {
            by_page.entry(pt.0 >> 20).or_default().push(*pt);
        }
        eprintln!("fit vs {label}: {} points in {} regions", pts.len(), by_page.len());
        for (pg, v) in &by_page {
            if v.len() < 3 {
                continue;
            }
            let mut strides: HashMap<i64, usize> = HashMap::new();
            for i in 0..v.len() {
                for j in i + 1..v.len() {
                    let dp = v[j].1 as i64 - v[i].1 as i64;
                    if dp == 0 {
                        continue;
                    }
                    let da = v[j].0 as i64 - v[i].0 as i64;
                    if da % dp == 0 {
                        let e = da / dp;
                        if e != 0 && e.abs() <= 4096 {
                            *strides.entry(e).or_default() += 1;
                        }
                    }
                }
            }
            let mut top: Vec<_> = strides.into_iter().collect();
            top.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
            if let Some((e, n)) = top.first().copied() {
                let mut bases_h: HashMap<i64, usize> = HashMap::new();
                for (a, k) in v {
                    *bases_h.entry(*a as i64 - *k as i64 * e).or_default() += 1;
                }
                let (b, nb) = bases_h.into_iter().max_by_key(|(_, n)| *n).unwrap();
                eprintln!(
                    "  region {:#x}xxxxx: {} pts; stride {e} agreed by {n} pairs; base {b:#x} by {nb}/{}",
                    pg,
                    v.len(),
                    v.len()
                );
            }
        }
    }

    // ---- Context of a few non-descriptor holders: what structure are they in?
    for (h, i, base) in others.iter().take(5) {
        let short = catalog.entry(*i).map(|e| e.short.as_str()).unwrap_or("?");
        eprintln!("holder {h:#x} -> base {base:#x} (tag {i} {short}):");
        let Ok(w) = p.read(h - 0x40, 0xa0) else { continue };
        for off in (0..w.len() - 7).step_by(8) {
            let v = u64_at(&w, off);
            let r = off as i64 - 0x40;
            let note = if v == *base {
                " <- BASE".into()
            } else if v == 0 {
                String::new()
            } else if is_static(v) {
                format!("  static exe+{:#x}", v - mbase)
            } else if (0x1_0000_0000..0x8000_0000_0000).contains(&v) {
                "  heap".into()
            } else {
                format!("  u32 {} | {}", v & 0xffff_ffff, v >> 32)
            };
            eprintln!("    {r:+#05x}: {v:016x}{note}");
        }
    }
}
