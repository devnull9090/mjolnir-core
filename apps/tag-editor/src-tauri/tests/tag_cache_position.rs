//! Is anything laid out by runtime tag position?
//!
//! The name index (`BlamCookedTagReferencesEngineSubsystem+0x30`) maps every
//! one of its 10,201 positions to a catalog tag, so each descriptor and slot
//! now has a **runtime position**. A parallel table of element size `E` at
//! base `B` would put tag `pos`'s slot at `B + pos·E + k`; across the known
//! slots the pairwise `Δslot / Δpos` ratios then agree on `E`, and
//! `slot − pos·E` on `B`. No scanning — pure arithmetic on cached data.
//!
//! Also decoded here: the subsystem's 13-element `+0x40` array (thirteen
//! loaded containers, plausibly each owning a per-container table), and a
//! header scan restricted to the two informative counts (10,201 and 9,147)
//! with a real pointer as `Data`, printed in full.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`,
//! and `MJOLNIR_NAMEINDEX` (from `tag_cache_parallel.rs`).

mod common;

use std::collections::{BTreeMap, HashMap, HashSet};

use common::*;
use tag_editor_lib::{catalog::Catalog, present};

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

/// For `(address, position)` pairs, the stride most pairs agree on and the
/// base it implies, tested per 1 MB region so separate tables do not mix.
fn fit(label: &str, pts: &[(u64, usize)]) {
    let mut by_page: BTreeMap<u64, Vec<(u64, usize)>> = BTreeMap::new();
    for pt in pts {
        by_page.entry(pt.0 >> 20).or_default().push(*pt);
    }
    eprintln!("{label}: {} points in {} regions", pts.len(), by_page.len());
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
        let pairs = v.len() * (v.len() - 1) / 2;
        let mut top: Vec<_> = strides.into_iter().collect();
        top.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        let best = top.first().copied();
        let base = best.map(|(e, _)| {
            let mut bases: HashMap<i64, usize> = HashMap::new();
            for (a, p) in v {
                *bases.entry(*a as i64 - *p as i64 * e).or_default() += 1;
            }
            bases.into_iter().max_by_key(|(_, n)| *n).unwrap()
        });
        eprintln!(
            "  region {:#x}xxxxx: {} pts, {pairs} pairs; top strides {:?}{}",
            pg,
            v.len(),
            &top[..top.len().min(3)],
            base.map(|(b, n)| format!("; base {b:#x} agreed by {n}/{}", v.len())).unwrap_or_default()
        );
    }
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS, MJOLNIR_RESIDENT, MJOLNIR_NAMEINDEX"]
fn tag_cache_position() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, msize) = p.module(blam_live::GAME_EXE).expect("module");
    let (reader, _) = present::attach(&p, catalog.paks(), None).expect("reader");

    // Catalog index -> runtime position.
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

    let t = targets(&p);
    let desc_of: HashMap<u64, usize> = t.descriptors.iter().copied().collect();
    let resident = load_resident();

    // ---- 1. Position fits: descriptors, the slots holding them, bases.
    let desc_pts: Vec<(u64, usize)> = t
        .descriptors
        .iter()
        .filter_map(|(a, i)| pos_of.get(i).map(|p| (*a, *p)))
        .collect();
    let mut slot_pts: Vec<(u64, usize)> = Vec::new();
    for s in &t.slots {
        let Ok(b) = p.read(*s, 8) else { continue };
        let d = u64_at(&b, 0);
        if let Some(i) = desc_of.get(&d) {
            if let Some(pos) = pos_of.get(i) {
                slot_pts.push((*s, *pos));
            }
        }
    }
    let base_pts: Vec<(u64, usize)> = resident
        .iter()
        .filter_map(|(b, (i, _, _))| pos_of.get(i).map(|p| (*b, *p)))
        .collect();
    fit("descriptors vs position", &desc_pts);
    fit("slots vs position", &slot_pts);
    fit("buffer bases vs position", &base_pts);

    // ---- 2. The subsystem's +0x40 array: 13 elements.
    let objects = reader.table.walk(&p).expect("walk");
    let root = objects
        .iter()
        .find(|o| {
            reader.name_at(&p, o.class).ok().as_deref()
                == Some("BlamCookedTagReferencesEngineSubsystem")
                && !reader.pool.text(&p, o.name_id).map(|n| n.starts_with("Default__")).unwrap_or(true)
        })
        .map(|o| o.object)
        .expect("subsystem");
    let hdr = p.read(root, 0x100).expect("hdr");
    let (d40, n40, m40) = (u64_at(&hdr, 0x40), u32_at(&hdr, 0x48), u32_at(&hdr, 0x4c));
    eprintln!("+0x40 array: Data {d40:#x}, Num {n40}, Max {m40}");
    // Element size unknown: dump the first 13*64 bytes and look for a repeat.
    if let Ok(a) = p.read(d40, (m40 as usize) * 64) {
        for off in (0..a.len().min(13 * 32)).step_by(8) {
            let v = u64_at(&a, off);
            let note = if v == 0 {
                String::new()
            } else if v >= mbase && v < mbase + msize {
                format!("  static exe+{:#x}", v - mbase)
            } else if heapish(v) {
                // TArray header right here?
                let num = u32_at(&a, off + 8);
                let max = if off + 16 <= a.len() { u32_at(&a, off + 12) } else { 0 };
                if num > 0 && max >= num && max < 10_000_000 {
                    format!("  heap; TArray? Num={num} Max={max}")
                } else {
                    "  heap".into()
                }
            } else {
                format!("  u32 {} | {}", v & 0xffff_ffff, v >> 32)
            };
            eprintln!("    +{off:#05x}: {v:016x}{note}");
        }
        // Follow every pointer in the first 13*64 bytes one hop, looking for
        // descriptors or bases in a 64 KB window — a per-container table.
        let desc_set: HashSet<u64> = desc_of.keys().copied().collect();
        let base_set: HashSet<u64> = resident.keys().copied().collect();
        for off in (0..a.len().saturating_sub(7)).step_by(8) {
            let v = u64_at(&a, off);
            if !heapish(v) {
                continue;
            }
            let Ok(w) = p.read(v, 0x10000) else { continue };
            let (mut d, mut b) = (0, 0);
            for io in (0..w.len().saturating_sub(7)).step_by(8) {
                let iv = u64_at(&w, io);
                if desc_set.contains(&iv) {
                    d += 1;
                }
                if base_set.contains(&iv) {
                    b += 1;
                }
            }
            if d + b >= 3 {
                eprintln!("    +{off:#05x} -> {v:#x}: {d} descriptors, {b} bases in 64 KB");
            }
        }
    }

    // ---- 3. Parallel-array headers, only the informative counts, in full.
    let mut heads = Vec::new();
    let want = [10201u32, 9147, 10240];
    let mut window = vec![0u8; 64 * 1024 * 1024];
    for region in p.writable_regions().expect("regions") {
        let mut at = 0u64;
        while at < region.size {
            let take = (window.len() as u64).min(region.size - at) as usize;
            if let Ok(got) = p.read_into(region.base + at, &mut window[..take]) {
                for off in (8..got.saturating_sub(7)).step_by(8) {
                    let v = u64_at(&window, off);
                    let num = (v & 0xffff_ffff) as u32;
                    let max = (v >> 32) as u32;
                    if want.contains(&num) && max >= num && max < 200_000 {
                        let data = u64_at(&window, off - 8);
                        if heapish(data) {
                            heads.push((region.base + at + off as u64 - 8, data, num, max));
                        }
                    }
                }
            }
            at += window.len() as u64;
        }
    }
    eprintln!("{} TArray headers with Num in {:?} and a heap Data pointer:", heads.len(), want);
    let desc_set: HashSet<u64> = desc_of.keys().copied().collect();
    let base_set: HashSet<u64> = resident.keys().copied().collect();
    for (h, data, num, max) in &heads {
        let tag = if *h == root + 0x30 { " (name index)" } else { "" };
        let Ok(a) = p.read(*data, (*max as usize) * 32) else {
            eprintln!("  {h:#x}: Data {data:#x} Num {num} Max {max}{tag} — unreadable");
            continue;
        };
        let (mut d, mut b) = (0, 0);
        for off in (0..a.len().saturating_sub(7)).step_by(8) {
            let v = u64_at(&a, off);
            if desc_set.contains(&v) {
                d += 1;
            }
            if base_set.contains(&v) {
                b += 1;
            }
        }
        let first: Vec<String> = (0..4).map(|k| format!("{:016x}", u64_at(&a, k * 8))).collect();
        eprintln!(
            "  {h:#x}: Data {data:#x} Num {num} Max {max}{tag}; {d} descriptors, {b} bases in {} KB; [{}]",
            a.len() >> 10,
            first.join(" ")
        );
    }
}
