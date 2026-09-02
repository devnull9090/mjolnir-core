//! Decoding the cooked-tag-reference registry.
//!
//! `BlamCookedTagReferencesEngineSubsystem` — a singleton reachable by class
//! name through the object table — holds, right after its `UObject` header, a
//! `TArray` of 10,201 elements (`+0x30`) and a hash table (mask `0x1fff` at
//! `+0x50`). In the subsystem named for cooked tag references, that array is
//! the registry.
//!
//! This decodes it without assuming a layout. It reads the whole array and
//! correlates every aligned word against what is known per tag — object and
//! package `FName` ids, `UObject` addresses, buffer descriptors and bases —
//! so the offsets where those land reveal the element **stride** and the
//! **field** each identity sits at. Then each element's pointer fields are
//! followed one hop to see which reaches the tag's descriptor or buffer.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`.

mod common;

use std::collections::{BTreeMap, HashMap, HashSet};

use common::*;
use tag_editor_lib::{catalog::Catalog, present};

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

/// Most common gap between sorted hit offsets — the stride, if the hits are
/// one field of a fixed-size element.
fn stride_of(offsets: &[usize]) -> Option<(usize, usize)> {
    let mut s: Vec<usize> = offsets.to_vec();
    s.sort_unstable();
    s.dedup();
    let mut gaps: HashMap<usize, usize> = HashMap::new();
    for w in s.windows(2) {
        let g = w[1] - w[0];
        if g > 0 && g <= 4096 {
            *gaps.entry(g).or_default() += 1;
        }
    }
    gaps.into_iter().max_by_key(|(_, n)| *n)
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn tag_cache_registry() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, msize) = p.module(blam_live::GAME_EXE).expect("module");
    let (reader, _) = present::attach(&p, catalog.paks(), None).expect("reader");

    let t = targets(&p);
    let desc_of: HashMap<u64, usize> = t.descriptors.iter().copied().collect();
    let resident = load_resident();
    let base_of: HashMap<u64, usize> = resident.iter().map(|(b, (i, _, _))| (*b, *i)).collect();
    let tags = tag_objects(&p, &catalog);
    let name_of: HashMap<u32, usize> = tags.iter().map(|(i, t)| (t.name_id, *i)).collect();
    let pkg_of: HashMap<u32, usize> = tags.iter().map(|(i, t)| (t.package_name_id, *i)).collect();
    let uobj_of: HashMap<u64, usize> = tags.iter().map(|(i, t)| (t.uobject, *i)).collect();

    // ---- The subsystem, by class name.
    let objects = reader.table.walk(&p).expect("walk");
    let mut root = None;
    for o in &objects {
        if reader.name_at(&p, o.class).ok().as_deref() == Some("BlamCookedTagReferencesEngineSubsystem")
            && !reader.pool.text(&p, o.name_id).map(|n| n.starts_with("Default__")).unwrap_or(true)
        {
            root = Some(o.object);
            break;
        }
    }
    let root = root.expect("BlamCookedTagReferencesEngineSubsystem instance");
    let hdr = p.read(root, 0x100).expect("read subsystem");
    let data = u64_at(&hdr, 0x30);
    let num = u32_at(&hdr, 0x38) as usize;
    let max = u32_at(&hdr, 0x3c) as usize;
    eprintln!("subsystem @ {root:#x}: array data {data:#x}, Num {num}, Max {max}; +0x40 array Num {} ; +0x50 mask {:#x}",
        u32_at(&hdr, 0x48), u64_at(&hdr, 0x50));
    assert!(num > 1000 && num <= max, "array header does not look right");

    // ---- Read the whole array. Element size is unknown; try up to 256 B
    // each and take what the region gives.
    let want = max * 256;
    let arr = p.read(data, want).expect("read array");
    eprintln!("read {} KB of the array", arr.len() >> 10);

    // ---- Correlate. Where do known identities land?
    let mut hit_name: Vec<(usize, usize)> = Vec::new(); // (offset, tag idx)
    let mut hit_pkg: Vec<(usize, usize)> = Vec::new();
    let mut hit_uobj: Vec<(usize, usize)> = Vec::new();
    let mut hit_desc: Vec<(usize, usize)> = Vec::new();
    let mut hit_base: Vec<(usize, usize)> = Vec::new();
    for off in (0..arr.len().saturating_sub(3)).step_by(4) {
        let v = u32_at(&arr, off);
        if v != 0 {
            if let Some(&i) = name_of.get(&v) {
                hit_name.push((off, i));
            }
            if let Some(&i) = pkg_of.get(&v) {
                hit_pkg.push((off, i));
            }
        }
    }
    for off in (0..arr.len().saturating_sub(7)).step_by(8) {
        let v = u64_at(&arr, off);
        if v == 0 {
            continue;
        }
        if let Some(&i) = uobj_of.get(&v) {
            hit_uobj.push((off, i));
        }
        if let Some(&i) = desc_of.get(&v) {
            hit_desc.push((off, i));
        }
        if let Some(&i) = base_of.get(&v) {
            hit_base.push((off, i));
        }
    }
    let report = |label: &str, hits: &[(usize, usize)]| {
        let offs: Vec<usize> = hits.iter().map(|(o, _)| *o).collect();
        let distinct: HashSet<usize> = hits.iter().map(|(_, i)| *i).collect();
        match stride_of(&offs) {
            Some((stride, n)) if hits.len() >= 8 => {
                let mut residues: HashMap<usize, usize> = HashMap::new();
                for o in &offs {
                    *residues.entry(o % stride).or_default() += 1;
                }
                let mut r: Vec<_> = residues.into_iter().collect();
                r.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
                eprintln!(
                    "  {label:<16} {:>5} hits ({} tags): stride {stride} (x{n}), field offset(s) {:?}",
                    hits.len(),
                    distinct.len(),
                    &r[..r.len().min(3)]
                );
            }
            _ => eprintln!("  {label:<16} {:>5} hits ({} tags)", hits.len(), distinct.len()),
        }
    };
    eprintln!("identities found in the array:");
    report("object FName", &hit_name);
    report("package FName", &hit_pkg);
    report("UObject ptr", &hit_uobj);
    report("descriptor ptr", &hit_desc);
    report("buffer base", &hit_base);

    // ---- Infer the element stride from whichever identity is densest, and
    // check whether position tracks the catalog.
    let densest = [&hit_name, &hit_pkg, &hit_uobj]
        .into_iter()
        .max_by_key(|h| h.len())
        .unwrap();
    let offs: Vec<usize> = densest.iter().map(|(o, _)| *o).collect();
    let Some((stride, _)) = stride_of(&offs) else {
        eprintln!("no stride inferable; raw first 512 bytes:");
        for off in (0..512.min(arr.len() - 7)).step_by(8) {
            eprintln!("    +{off:#05x}: {:016x}", u64_at(&arr, off));
        }
        return;
    };
    let field = offs.iter().map(|o| o % stride).fold(HashMap::<usize, usize>::new(), |mut m, r| {
        *m.entry(r).or_default() += 1;
        m
    });
    let field = *field.iter().max_by_key(|(_, n)| **n).unwrap().0;
    eprintln!("element stride {stride}, identity field at +{field:#x}; {} elements fit in what was read", arr.len() / stride);
    let mut pos_idx: Vec<(usize, usize)> = densest
        .iter()
        .filter(|(o, _)| o % stride == field)
        .map(|(o, i)| (o / stride, *i))
        .collect();
    pos_idx.sort_unstable();
    let mono = pos_idx.windows(2).filter(|w| w[1].1 > w[0].1).count();
    let eq = pos_idx.iter().filter(|(pos, i)| pos == i).count();
    eprintln!(
        "  position == catalog index: {eq}/{}; monotone pairs {mono}/{}",
        pos_idx.len(),
        pos_idx.len().saturating_sub(1)
    );
    for (pos, i) in pos_idx.iter().take(6) {
        eprintln!("    element {pos:5} -> tag {i:5} {}", catalog.entry(*i).map(|e| e.short.as_str()).unwrap_or("?"));
    }

    // ---- Four elements raw, annotated.
    for (pos, i) in pos_idx.iter().take(4) {
        let s = pos * stride;
        let short = catalog.entry(*i).map(|e| e.short.as_str()).unwrap_or("?");
        let is_res = resident.values().any(|(ri, _, _)| ri == i);
        eprintln!("element {pos} (tag {i} {short}{}):", if is_res { ", RESIDENT" } else { "" });
        for off in (s..(s + stride).min(arr.len() - 7)).step_by(8) {
            let v = u64_at(&arr, off);
            let note = if v == 0 {
                String::new()
            } else if desc_of.contains_key(&v) {
                " <- DESCRIPTOR".into()
            } else if base_of.contains_key(&v) {
                " <- BUFFER BASE".into()
            } else if uobj_of.contains_key(&v) {
                " <- UObject".into()
            } else if v >= mbase && v < mbase + msize {
                format!(" static exe+{:#x}", v - mbase)
            } else if heapish(v) {
                " heap ptr".into()
            } else {
                format!(" u32 {} | {}", v & 0xffff_ffff, v >> 32)
            };
            eprintln!("    +{:#04x}: {v:016x}{note}", off - s);
        }
    }

    // ---- One hop from each element's pointer fields: which (field, inner
    // offset) reaches the tag's descriptor or buffer? Score by resident tags.
    let mut reach: BTreeMap<(usize, usize, &str), usize> = BTreeMap::new();
    let mut checked = 0usize;
    let resident_idx: HashSet<usize> = resident.values().map(|(i, _, _)| *i).collect();
    for (pos, i) in &pos_idx {
        if !resident_idx.contains(i) {
            continue;
        }
        checked += 1;
        let s = pos * stride;
        for off in (s..(s + stride).min(arr.len() - 7)).step_by(8) {
            let v = u64_at(&arr, off);
            if !heapish(v) {
                continue;
            }
            let Ok(w) = p.read(v, 0x200) else { continue };
            for io in (0..w.len() - 7).step_by(8) {
                let iv = u64_at(&w, io);
                if desc_of.get(&iv) == Some(i) {
                    *reach.entry((off - s, io, "descriptor")).or_default() += 1;
                }
                if base_of.get(&iv) == Some(i) {
                    *reach.entry((off - s, io, "base")).or_default() += 1;
                }
            }
        }
    }
    let mut r: Vec<_> = reach.into_iter().collect();
    r.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    eprintln!("one hop from element fields, over {checked} resident tags (field, inner offset, what) -> count:");
    for ((f, io, what), n) in r.iter().take(10) {
        eprintln!("  +{f:#04x} -> +{io:#05x} {what}: {n}");
    }
    if r.is_empty() {
        eprintln!("  none — the buffer is not one hop from the element");
    }
}
