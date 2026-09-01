//! The cooked-tag-reference table is `TArray<FString>`; find the parallel
//! table that holds the buffers.
//!
//! `tag_cache_registry.rs` showed the subsystem's 10,201-element array is
//! `{TCHAR* Data; int32 Num; int32 Max}` per element — an `FString` each, so
//! it is the **name** index, and its element position is the natural tag
//! index for the runtime to key everything else by. The buffer table should
//! then be a parallel array of the same length, indexed identically.
//!
//! Part 1 decodes the strings, confirms they are tag paths, and maps each
//! position to a catalog tag (saved for later probes and for `present.rs`).
//! Part 2 scans memory for every `TArray` header whose `Num` is one of the
//! characteristic counts — 10,201 (references), 9,147 (present), 12,292
//! (catalog), 362 (resident) — and inspects each such array for descriptors,
//! buffer bases, `UObject`s or `FName` ids, with stride inference.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`.

mod common;

use std::collections::{HashMap, HashSet};

use common::*;
use tag_editor_lib::{catalog::Catalog, present};

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

fn read_fstring(p: &blam_live::Process, data: u64, num: u32) -> Option<String> {
    if data == 0 || num == 0 || num > 1024 {
        return None;
    }
    let b = p.read(data, (num as usize) * 2).ok()?;
    let units: Vec<u16> = b.chunks_exact(2).map(|c| u16::from_le_bytes([c[0], c[1]])).collect();
    let s = String::from_utf16_lossy(&units);
    Some(s.trim_end_matches('\0').to_string())
}

/// Every aligned u64 whose low u32 is one of `nums` and whose high u32 is a
/// plausible `Max` (>= Num, < 1M): candidate `TArray` `{Num, Max}` words.
/// Returns `(address of the Num word, Num, Max)`.
fn tarray_header_scan(p: &blam_live::Process, nums: &[u32]) -> Vec<(u64, u32, u32)> {
    let want: HashSet<u32> = nums.iter().copied().collect();
    let mut out = Vec::new();
    let mut window = vec![0u8; 64 * 1024 * 1024];
    for region in p.writable_regions().expect("regions") {
        let mut at = 0u64;
        while at < region.size {
            let take = (window.len() as u64).min(region.size - at) as usize;
            if let Ok(got) = p.read_into(region.base + at, &mut window[..take]) {
                for off in (0..got.saturating_sub(7)).step_by(8) {
                    let v = u64_at(&window, off);
                    let num = (v & 0xffff_ffff) as u32;
                    let max = (v >> 32) as u32;
                    if want.contains(&num) && max >= num && max < 1_000_000 {
                        out.push((region.base + at + off as u64, num, max));
                    }
                }
            }
            at += window.len() as u64;
        }
    }
    out
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn tag_cache_parallel() {
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
    let uobj_of: HashMap<u64, usize> = tags.iter().map(|(i, t)| (t.uobject, *i)).collect();

    // ---- Part 1: the name index.
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
    let hdr = p.read(root, 0x60).expect("hdr");
    let (data, num) = (u64_at(&hdr, 0x30), u32_at(&hdr, 0x38) as usize);
    let arr = p.read(data, num * 16).expect("read names");
    let mut names: Vec<String> = Vec::with_capacity(num);
    let mut index_to_tag: Vec<Option<usize>> = Vec::with_capacity(num);
    let mut mapped = 0usize;
    for i in 0..num {
        let e = &arr[i * 16..i * 16 + 16];
        let s = read_fstring(&p, u64_at(e, 0), u32_at(e, 8)).unwrap_or_default();
        // Cooked references are "<short>-<group>" style or "/Game/Tags/..."
        // package paths; try the package form first, then group suffix.
        let idx = catalog.tag_by_package(&s).or_else(|| {
            let (short, group) = s.rsplit_once('-')?;
            let short = short.replace('\\', "/");
            catalog.tag_index(group, &short).or_else(|| {
                let g = catalog.groups().ok()?.into_iter().find(|g| g.four_cc == group)?;
                catalog.tag_index(&g.group, &short)
            })
        });
        if idx.is_some() {
            mapped += 1;
        }
        index_to_tag.push(idx);
        names.push(s);
    }
    eprintln!("name index: {num} entries, {mapped} mapped to catalog tags");
    for (i, s) in names.iter().enumerate().take(6) {
        eprintln!("  [{i:5}] {s:?} -> {:?}", index_to_tag[i]);
    }
    // Where do resident tags sit? Their positions are what a parallel table
    // must light up at.
    let resident_idx: HashSet<usize> = resident.values().map(|(i, _, _)| *i).collect();
    let resident_pos: Vec<usize> = index_to_tag
        .iter()
        .enumerate()
        .filter_map(|(pos, i)| i.filter(|i| resident_idx.contains(i)).map(|_| pos))
        .collect();
    eprintln!("  {} resident tags located in the name index", resident_pos.len());
    if let Ok(out) = std::env::var("MJOLNIR_NAMEINDEX_OUT") {
        let rows: Vec<serde_json::Value> = names
            .iter()
            .zip(&index_to_tag)
            .map(|(s, i)| serde_json::json!({ "name": s, "tag": i }))
            .collect();
        std::fs::write(&out, serde_json::to_string(&rows).unwrap()).unwrap();
        eprintln!("  wrote {out}");
    }

    // ---- Part 2: parallel tables. Every TArray header with a telling Num.
    let counts = [num as u32, 9147u32, 12292, 362, 369, 1982];
    let heads = tarray_header_scan(&p, &counts);
    eprintln!("{} TArray headers with Num in {:?}", heads.len(), counts);
    let this_num_word = root + 0x38;
    for (addr, n, max) in &heads {
        let Ok(dw) = p.read(addr - 8, 8) else { continue };
        let dptr = u64_at(&dw, 0);
        if !heapish(dptr) {
            continue;
        }
        let owner = if *addr == this_num_word { " (the name index itself)" } else { "" };
        eprintln!("== header at {addr:#x}: Data {dptr:#x}, Num {n}, Max {max}{owner}");
        if *addr == this_num_word {
            continue;
        }
        // Read up to 64 bytes per element and correlate.
        let Ok(a) = p.read(dptr, (*max as usize) * 64) else { continue };
        let mut h_desc: Vec<usize> = Vec::new();
        let mut h_base: Vec<usize> = Vec::new();
        let mut h_uobj: Vec<usize> = Vec::new();
        let mut h_name: Vec<usize> = Vec::new();
        for off in (0..a.len().saturating_sub(7)).step_by(8) {
            let v = u64_at(&a, off);
            if desc_of.contains_key(&v) {
                h_desc.push(off);
            }
            if base_of.contains_key(&v) {
                h_base.push(off);
            }
            if uobj_of.contains_key(&v) {
                h_uobj.push(off);
            }
        }
        for off in (0..a.len().saturating_sub(3)).step_by(4) {
            let v = u32_at(&a, off);
            if v != 0 && name_of.contains_key(&v) {
                h_name.push(off);
            }
        }
        let stride = |offs: &[usize]| -> String {
            let mut s = offs.to_vec();
            s.sort_unstable();
            s.dedup();
            let mut gaps: HashMap<usize, usize> = HashMap::new();
            for w in s.windows(2) {
                *gaps.entry(w[1] - w[0]).or_default() += 1;
            }
            gaps.into_iter()
                .max_by_key(|(_, n)| *n)
                .map(|(g, n)| format!("stride {g} x{n}"))
                .unwrap_or_default()
        };
        eprintln!(
            "   read {} KB: descriptors {} ({}), bases {} ({}), UObjects {} ({}), FName ids {} ({})",
            a.len() >> 10,
            h_desc.len(), stride(&h_desc),
            h_base.len(), stride(&h_base),
            h_uobj.len(), stride(&h_uobj),
            h_name.len(), stride(&h_name),
        );
        // Do resident positions in the name index line up with hits here?
        // If element size is E, a hit at offset o is element o/E.
        for e in [8usize, 16, 24, 32, 48, 64] {
            let hit_pos: HashSet<usize> = h_desc.iter().chain(&h_base).map(|o| o / e).collect();
            if hit_pos.is_empty() {
                continue;
            }
            let overlap = resident_pos.iter().filter(|p| hit_pos.contains(p)).count();
            if overlap > 0 {
                eprintln!("   with element size {e}: {overlap} hits sit at resident name-index positions");
            }
        }
        // First 4 elements raw at 32 bytes each.
        for i in 0..4 {
            let s = i * 32;
            if s + 32 > a.len() {
                break;
            }
            let words: Vec<String> = (0..4)
                .map(|k| {
                    let v = u64_at(&a, s + k * 8);
                    if desc_of.contains_key(&v) {
                        format!("{v:016x}<D>")
                    } else if base_of.contains_key(&v) {
                        format!("{v:016x}<B>")
                    } else if v >= mbase && v < mbase + msize {
                        format!("{v:016x}<S>")
                    } else {
                        format!("{v:016x}")
                    }
                })
                .collect();
            eprintln!("   [{i}] {}", words.join(" "));
        }
    }
}
