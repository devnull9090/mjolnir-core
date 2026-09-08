//! Walking the pointer graph up from a tag's data buffer to a static root.
//!
//! `tag_cache.rs` settled the bottom of the chain: each resident tag's buffer
//! is owned by an individually allocated 32-byte descriptor
//! `{ ptr; u32 size; u32 = 1; u64 = 0; u8 0; u8 1; pad }` living in the
//! engine's small-block pools — not an array, which is why the holders never
//! clustered. So the root is found by walking *up*: who points at the
//! descriptors, who points at those, and so on, until a holder sits inside
//! the game image's static data. That address, expressed as an RVA, is the
//! `exe + offset` global the classic approach keys on.
//!
//! At every level the walker also asks whether the containing structure
//! references the tag's `UObject` (addresses from the object-table reader).
//! A level whose nodes hold both the `UObject` and the descriptor is the
//! per-tag record — and the map that holds *those* is the tag cache.
//!
//! Levels above the descriptor point at the *start* of a containing struct,
//! not at the slot we found, so from level 2 the scan matches any value in a
//! window before each known slot rather than an exact address.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, and `MJOLNIR_RESIDENT`
//! (a census dump from this same game session). Several full memory scans;
//! allow ~10 minutes.

use std::collections::{BTreeMap, HashMap, HashSet};

use tag_editor_lib::{catalog::Catalog, present};

fn u64_at(b: &[u8], o: usize) -> u64 {
    u64::from_le_bytes(b[o..o + 8].try_into().unwrap())
}

/// Every aligned 8-byte slot in writable memory whose value falls in one of
/// `ranges` (`[lo, hi)`, sorted, non-overlapping), as `(holder, value)`.
fn range_scan(p: &blam_live::Process, ranges: &[(u64, u64)]) -> Vec<(u64, u64)> {
    let (min, max) = (ranges[0].0, ranges[ranges.len() - 1].1);
    let starts: Vec<u64> = ranges.iter().map(|r| r.0).collect();
    let mut out = Vec::new();
    let mut window = vec![0u8; 64 * 1024 * 1024];
    for region in p.writable_regions().expect("regions") {
        let mut at = 0u64;
        while at < region.size {
            let want = (window.len() as u64).min(region.size - at) as usize;
            if let Ok(got) = p.read_into(region.base + at, &mut window[..want]) {
                for off in (0..got.saturating_sub(7)).step_by(8) {
                    let v = u64_at(&window, off);
                    if v < min || v >= max {
                        continue;
                    }
                    let i = match starts.binary_search(&v) {
                        Ok(i) => i,
                        Err(0) => continue,
                        Err(i) => i - 1,
                    };
                    if v < ranges[i].1 {
                        out.push((region.base + at + off as u64, v));
                    }
                }
            }
            at += window.len() as u64;
        }
    }
    out.sort_unstable();
    out
}

fn exact_ranges(addrs: &[u64]) -> Vec<(u64, u64)> {
    let mut v: Vec<(u64, u64)> = addrs.iter().map(|a| (*a, *a + 8)).collect();
    v.sort_unstable();
    v.dedup();
    v
}

/// `[a - before, a + 8)` around each slot, merged where they overlap.
fn window_ranges(addrs: &[u64], before: u64) -> Vec<(u64, u64)> {
    let mut v: Vec<(u64, u64)> = addrs.iter().map(|a| (a.saturating_sub(before), *a + 8)).collect();
    v.sort_unstable();
    let mut merged: Vec<(u64, u64)> = Vec::new();
    for r in v {
        match merged.last_mut() {
            Some(last) if r.0 <= last.1 => last.1 = last.1.max(r.1),
            _ => merged.push(r),
        }
    }
    merged
}

/// Describe one level's holders: how many, coverage of the level below,
/// where they cluster, and whether any sit in the image's static data.
fn describe(
    label: &str,
    holders: &[(u64, u64)],
    below: usize,
    module: (u64, u64),
) -> Vec<u64> {
    let distinct_targets: HashSet<u64> = holders.iter().map(|(_, v)| *v).collect();
    eprintln!(
        "== {label}: {} holders, covering {} of {} targets",
        holders.len(),
        distinct_targets.len(),
        below
    );
    let mut by_mb: BTreeMap<u64, usize> = BTreeMap::new();
    for (a, _) in holders {
        *by_mb.entry(a >> 20).or_default() += 1;
    }
    let mut mbs: Vec<_> = by_mb.into_iter().collect();
    mbs.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    for (mb, n) in mbs.iter().take(5) {
        eprintln!("   {:#x}xxxxx: {n} holders", *mb);
    }
    let mut align: HashMap<u64, usize> = HashMap::new();
    for (a, _) in holders {
        *align.entry(a % 32).or_default() += 1;
    }
    let mut align: Vec<_> = align.into_iter().collect();
    align.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    eprintln!("   holder mod 32: {:?}", &align[..align.len().min(4)]);
    let (mb, msz) = module;
    let statics: Vec<u64> = holders
        .iter()
        .map(|(a, _)| *a)
        .filter(|a| *a >= mb && *a < mb + msz)
        .collect();
    for a in &statics {
        eprintln!("   *** STATIC holder {a:#x} = exe + {:#x} ***", a - mb);
    }
    statics
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn tag_cache_root() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let module = p.module(blam_live::GAME_EXE).expect("module");
    eprintln!("module at {:#x}, {} MiB", module.0, module.1 >> 20);

    // Resident tags: base -> catalog index.
    let rows: Vec<serde_json::Value> = serde_json::from_str(
        &std::fs::read_to_string(std::env::var("MJOLNIR_RESIDENT").unwrap()).unwrap(),
    )
    .unwrap();
    let mut base_to_index: HashMap<u64, usize> = HashMap::new();
    for r in &rows {
        let base =
            u64::from_str_radix(r["base"].as_str().unwrap().trim_start_matches("0x"), 16).unwrap();
        base_to_index.insert(base, r["index"].as_u64().unwrap() as usize);
    }

    // Tag UObject addresses, by catalog index, from the object table.
    let (reader, _) = present::attach(&p, catalog.paks(), None).expect("reader");
    let objects = reader.table.walk(&p).expect("walk");
    let mut class_is_tag: HashMap<u64, bool> = HashMap::new();
    let mut uobject_of: HashMap<usize, u64> = HashMap::new();
    for o in &objects {
        let is_tag = *class_is_tag.entry(o.class).or_insert_with(|| {
            reader
                .name_at(&p, o.class)
                .map(|n| n.ends_with("TagDataAsset"))
                .unwrap_or(false)
        });
        if !is_tag {
            continue;
        }
        let Ok((name, pkg)) = reader.identity(&p, o) else { continue };
        if name.starts_with("Default__") || !pkg.starts_with("/Game/Tags/") {
            continue;
        }
        if let Some(idx) = catalog.tag_by_package(&pkg) {
            uobject_of.insert(idx, o.object);
        }
    }
    let uobject_set: HashSet<u64> = uobject_of.values().copied().collect();
    eprintln!("{} tag UObjects known", uobject_of.len());

    // ---- Level 0: descriptors — the 32-byte records holding a buffer base.
    let bases: Vec<u64> = base_to_index.keys().copied().collect();
    let l0 = range_scan(&p, &exact_ranges(&bases));
    // Keep the ones that are real descriptors: 32-aligned with the decoded
    // constant fields (+0xC == 1, +0x10 == 0).
    let mut descriptors: Vec<(u64, usize)> = Vec::new(); // (descriptor addr, tag index)
    for (a, v) in &l0 {
        if a % 32 != 0 {
            continue;
        }
        let Ok(r) = p.read(*a, 32) else { continue };
        if u32::from_le_bytes(r[12..16].try_into().unwrap()) == 1 && u64_at(&r, 16) == 0 {
            descriptors.push((*a, base_to_index[v]));
        }
    }
    let _ = describe("level 0 (buffer holders)", &l0, bases.len(), module);
    eprintln!(
        "   {} are shape-valid 32-byte descriptors, for {} distinct tags",
        descriptors.len(),
        descriptors.iter().map(|(_, i)| i).collect::<HashSet<_>>().len()
    );
    assert!(descriptors.len() >= 50, "too few descriptors to walk from");
    let desc_to_index: HashMap<u64, usize> = descriptors.iter().copied().collect();

    // ---- Level 1: who points at a descriptor? Exact, since the descriptor is
    // the start of its allocation.
    let desc_addrs: Vec<u64> = descriptors.iter().map(|(a, _)| *a).collect();
    let l1 = range_scan(&p, &exact_ranges(&desc_addrs));
    let statics1 = describe("level 1 (descriptor holders)", &l1, desc_addrs.len(), module);

    // Does the struct around a level-1 slot also reference the tag's UObject?
    // Read a window before and after each slot and look for that address.
    let mut uobj_link: HashMap<i64, usize> = HashMap::new(); // (offset of UObject slot rel. to holder) -> count
    let mut checked = 0usize;
    for (h, d) in l1.iter().take(400) {
        let Some(&idx) = desc_to_index.get(d) else { continue };
        let Some(&uo) = uobject_of.get(&idx) else { continue };
        checked += 1;
        let Ok(w) = p.read(h.saturating_sub(0x200), 0x400) else { continue };
        for off in (0..w.len() - 7).step_by(8) {
            if u64_at(&w, off) == uo {
                let rel = off as i64 - 0x200;
                *uobj_link.entry(rel).or_default() += 1;
            }
        }
    }
    let mut links: Vec<_> = uobj_link.into_iter().collect();
    links.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    eprintln!(
        "   UObject link near level-1 slots ({checked} checked): {:?}",
        &links[..links.len().min(6)]
    );
    // And the reverse: does any level-1 holder's window hold *any* tag UObject?
    let mut any_uobj = 0usize;
    for (h, _) in l1.iter().take(400) {
        let Ok(w) = p.read(h.saturating_sub(0x200), 0x400) else { continue };
        if (0..w.len() - 7).step_by(8).any(|o| uobject_set.contains(&u64_at(&w, o))) {
            any_uobj += 1;
        }
    }
    eprintln!("   level-1 windows containing some tag UObject: {any_uobj}/400");

    // ---- Levels 2+: containers of containers. Match a window before each
    // slot, since pointers target struct starts. Stop at a static holder.
    let mut current: Vec<u64> = l1.iter().map(|(a, _)| *a).collect();
    let mut found_static = statics1;
    for level in 2..=5 {
        if !found_static.is_empty() {
            break;
        }
        current.sort_unstable();
        current.dedup();
        // Too many targets means we followed noise; keep the structured
        // majority by sampling the densest holders' neighbourhoods.
        if current.len() > 4000 {
            current.truncate(4000);
        }
        let ranges = window_ranges(&current, 0x400);
        let ln = range_scan(&p, &ranges);
        let s = describe(&format!("level {level}"), &ln, current.len(), module);
        // Sample the values (struct starts) for the next level.
        let mut next: Vec<u64> = ln.iter().map(|(a, _)| *a).collect();
        next.sort_unstable();
        next.dedup();
        eprintln!("   {} distinct holder slots to follow", next.len());
        found_static = s;
        current = next;
        if ln.is_empty() {
            break;
        }
    }

    if found_static.is_empty() {
        eprintln!("no static holder reached within 5 levels");
    } else {
        eprintln!("ROOT CANDIDATES: {:x?}", found_static);
    }
}
