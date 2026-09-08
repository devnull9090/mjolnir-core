//! The tag cache, by name: which field of which Blam singleton reaches the
//! loaded buffers?
//!
//! `tag_cache_by_name.rs` listed the live `Blam*` classes, and one is named
//! for exactly this — `BlamCookedTagReferencesEngineSubsystem` — beside a few
//! other plausible managers. Its wide breadth-first search was useless (UE's
//! object graph is so connected that every root reached everything within
//! three hops), so this asks a sharper question: for each singleton, follow
//! each pointer **field** exactly one hop into a large window and count the
//! known descriptors, slots and buffer bases found there. A registry shows as
//! **one field reaching most of the 167 descriptors**; scattered single hits
//! are graph noise. Where a field reaches a struct rather than an array, one
//! more hop is tried from that struct's fields, still bounded.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`.

mod common;

use std::collections::{HashMap, HashSet};

use common::*;
use tag_editor_lib::{catalog::Catalog, present};

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

/// Count targets inside `[addr, addr+len)`: descriptor pointers and buffer
/// bases as *values*, slots as *addresses*.
fn count_hits(
    p: &blam_live::Process,
    addr: u64,
    len: usize,
    desc: &HashSet<u64>,
    slots: &HashSet<u64>,
    bases: &HashSet<u64>,
) -> (usize, usize, usize, usize) {
    let Ok(w) = p.read(addr, len) else { return (0, 0, 0, 0) };
    let (mut d, mut s, mut b) = (HashSet::new(), HashSet::new(), HashSet::new());
    for off in (0..w.len().saturating_sub(7)).step_by(8) {
        let v = u64_at(&w, off);
        if desc.contains(&v) {
            d.insert(v);
        }
        if bases.contains(&v) {
            b.insert(v);
        }
        if slots.contains(&(addr + off as u64)) {
            s.insert(addr + off as u64);
        }
    }
    (d.len(), s.len(), b.len(), w.len())
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn tag_cache_subsystem() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (mbase, msize) = p.module(blam_live::GAME_EXE).expect("module");
    let (reader, _) = present::attach(&p, catalog.paks(), None).expect("reader");

    let t = targets(&p);
    let desc: HashSet<u64> = t.descriptors.iter().map(|(a, _)| *a).collect();
    let slots: HashSet<u64> = t.slots.iter().copied().collect();
    let bases: HashSet<u64> = t.bases.iter().copied().collect();

    // Singleton Blam objects (one live non-CDO instance), by class name.
    let objects = reader.table.walk(&p).expect("walk");
    let mut class_name: HashMap<u64, String> = HashMap::new();
    let mut instances: HashMap<u64, Vec<u64>> = HashMap::new();
    for o in &objects {
        let name = class_name
            .entry(o.class)
            .or_insert_with(|| reader.name_at(&p, o.class).unwrap_or_default());
        if !name.contains("Blam") || name.ends_with("TagDataAsset") {
            continue;
        }
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
    let mut singletons: Vec<(String, u64)> = instances
        .iter()
        .filter(|(_, v)| v.len() == 1)
        .map(|(c, v)| (class_name[c].clone(), v[0]))
        .collect();
    singletons.sort();
    eprintln!("{} Blam singletons", singletons.len());

    const ROOT: usize = 0x4000;
    const WINDOW: usize = 0x20000; // 16k pointers — a registry of ~9k tags fits
    const MAX_FIELDS: usize = 400;
    const CHILD_WINDOW: usize = 0x8000;
    const MAX_CHILDREN: usize = 24;
    // The second hop is where an unbounded search explodes (fields x children
    // x window ran ~25 minutes); it is only worth it for the named suspects.
    const SUSPECTS: [&str; 6] = [
        "BlamCookedTagReferencesEngineSubsystem",
        "BlamEngineSynchronizationManager",
        "BlamEngineAssetManager",
        "BlamEngineLoadingManagerEngineSubsystem",
        "BlamSynchronizationEngineGlueSubsystem",
        "BlamScenario",
    ];
    struct Hit {
        class: String,
        path: String,
        d: usize,
        s: usize,
        b: usize,
        read: usize,
    }
    let mut hits: Vec<Hit> = Vec::new();

    for (class, root) in &singletons {
        let Ok(rw) = p.read(*root, ROOT) else { continue };
        let is_suspect = SUSPECTS.contains(&class.as_str());
        let mut seen: HashSet<u64> = HashSet::new();
        let mut fields = 0usize;
        for off in (0..rw.len().saturating_sub(7)).step_by(8) {
            let v = u64_at(&rw, off);
            if !heapish(v) || v >= mbase && v < mbase + msize || !seen.insert(v) {
                continue;
            }
            fields += 1;
            if fields > MAX_FIELDS {
                break;
            }
            let (d, s, b, read) = count_hits(&p, v, WINDOW, &desc, &slots, &bases);
            if d + s + b >= 3 {
                hits.push(Hit {
                    class: class.clone(),
                    path: format!("+{off:#x} -> {v:#x}"),
                    d,
                    s,
                    b,
                    read,
                });
            }
            // One more hop from a struct — suspects only, tightly capped.
            if d + s + b < 3 && is_suspect {
                let Ok(cw) = p.read(v, 0x400) else { continue };
                let mut children = 0usize;
                for coff in (0..cw.len().saturating_sub(7)).step_by(8) {
                    let cv = u64_at(&cw, coff);
                    if !heapish(cv) || cv >= mbase && cv < mbase + msize || !seen.insert(cv) {
                        continue;
                    }
                    children += 1;
                    if children > MAX_CHILDREN {
                        break;
                    }
                    let (d2, s2, b2, read2) = count_hits(&p, cv, CHILD_WINDOW, &desc, &slots, &bases);
                    if d2 + s2 + b2 >= 10 {
                        hits.push(Hit {
                            class: class.clone(),
                            path: format!("+{off:#x} -> +{coff:#x} -> {cv:#x}"),
                            d: d2,
                            s: s2,
                            b: b2,
                            read: read2,
                        });
                    }
                }
            }
        }
    }
    hits.sort_by_key(|h| std::cmp::Reverse(h.d * 4 + h.s * 4 + h.b));
    eprintln!("fields reaching targets (descriptors / slots / bases, of {} / {} / {}):", desc.len(), slots.len(), bases.len());
    for h in hits.iter().take(25) {
        eprintln!(
            "  {:>3}d {:>3}s {:>3}b  {}  {}  (window {} KB)",
            h.d,
            h.s,
            h.b,
            h.class,
            h.path,
            h.read >> 10
        );
    }

    // ---- The prime suspect, laid out: first 0x400 bytes annotated.
    for (class, root) in &singletons {
        if class != "BlamCookedTagReferencesEngineSubsystem"
            && class != "BlamEngineSynchronizationManager"
        {
            continue;
        }
        eprintln!("{class} @ {root:#x}:");
        let Ok(w) = p.read(*root, 0x400) else { continue };
        for off in (0..w.len() - 7).step_by(8) {
            let v = u64_at(&w, off);
            if v == 0 {
                continue;
            }
            let note = if v >= mbase && v < mbase + msize {
                format!("static exe+{:#x}", v - mbase)
            } else if heapish(v) {
                // TArray-ish? next two u32 as Num/Max.
                let num = u32_at(&w, off + 8);
                let max = if off + 16 <= w.len() { u32_at(&w, off + 12) } else { 0 };
                if num > 0 && max >= num && max < 10_000_000 {
                    format!("heap ptr; TArray? Num={num} Max={max}")
                } else {
                    "heap ptr".into()
                }
            } else {
                format!("u32 {} | {}", v & 0xffff_ffff, v >> 32)
            };
            eprintln!("    +{off:#05x}: {v:016x}  {note}");
        }
    }
}
