//! Who holds the buffers? Resolve each descriptor slot to the `UObject` that
//! contains it.
//!
//! Every upward walk from the buffers found the same thing: descriptor
//! pointers sit in small inline pointer buffers inside assorted objects, with
//! no identity field and no owner chain. Nothing is laid out by tag index.
//! The simplest structure consistent with all of it is that there is **no
//! central cache** — each descriptor is a shared block held by whatever
//! consumes the tag (a spawned actor's component, say), and it lives as long
//! as something holds it.
//!
//! That is testable without a scan: the object table gives every `UObject`'s
//! address, so for each slot the nearest preceding object is its container.
//! If the slots resolve to instances of a few component classes, the holders
//! are consumers and the buffer follows the object, not a registry. The same
//! lookup names the owner of the `Num = 10201` per-tag u64 array.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, `MJOLNIR_RESIDENT`,
//! `MJOLNIR_NAMEINDEX`.

mod common;

use std::collections::{BTreeMap, HashMap};

use common::*;
use tag_editor_lib::{catalog::Catalog, present};

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS, MJOLNIR_RESIDENT, MJOLNIR_NAMEINDEX"]
fn tag_cache_holders() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (reader, _) = present::attach(&p, catalog.paks(), None).expect("reader");
    let t = targets(&p);
    let desc_of: HashMap<u64, usize> = t.descriptors.iter().copied().collect();

    // Every live object, sorted by address, with its class name.
    let objects = reader.table.walk(&p).expect("walk");
    let mut class_name: HashMap<u64, String> = HashMap::new();
    let mut by_addr: BTreeMap<u64, (u64, String)> = BTreeMap::new(); // addr -> (class, object name)
    for o in &objects {
        let cname = class_name
            .entry(o.class)
            .or_insert_with(|| reader.name_at(&p, o.class).unwrap_or_default())
            .clone();
        let oname = reader.pool.text(&p, o.name_id).unwrap_or_default();
        by_addr.insert(o.object, (o.class, format!("{cname} '{oname}'")));
    }
    // The nearest object at or before an address, if within `max_size`.
    let containing = |addr: u64, max_size: u64| -> Option<(u64, &(u64, String))> {
        by_addr
            .range(..=addr)
            .next_back()
            .filter(|(base, _)| addr - **base < max_size)
            .map(|(b, v)| (*b, v))
    };

    // ---- 1. The slots.
    let mut class_hist: HashMap<String, usize> = HashMap::new();
    let mut offset_hist: HashMap<(String, u64), usize> = HashMap::new();
    let mut outside = 0usize;
    let mut examples = 0usize;
    for s in &t.slots {
        let Ok(b) = p.read(*s, 8) else { continue };
        let d = u64_at(&b, 0);
        let tag = desc_of.get(&d).copied();
        match containing(*s, 0x20000) {
            Some((base, (_, label))) => {
                let cls = label.split(' ').next().unwrap_or("").to_string();
                *class_hist.entry(cls.clone()).or_default() += 1;
                *offset_hist.entry((cls, s - base)).or_default() += 1;
                if examples < 8 {
                    let short = tag
                        .and_then(|i| catalog.entry(i))
                        .map(|e| e.short.as_str())
                        .unwrap_or("?");
                    eprintln!(
                        "  slot {s:#x} = {label} + {:#x}   (tag {short})",
                        s - base
                    );
                    examples += 1;
                }
            }
            None => outside += 1,
        }
    }
    let mut ch: Vec<_> = class_hist.into_iter().collect();
    ch.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    eprintln!(
        "slots inside a UObject: {} / {} ({outside} not within 128 KB of any object)",
        t.slots.len() - outside,
        t.slots.len()
    );
    eprintln!("containing classes:");
    for (c, n) in ch.iter().take(12) {
        eprintln!("  {n:>4}  {c}");
    }
    let mut oh: Vec<_> = offset_hist.into_iter().collect();
    oh.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    eprintln!("(class, offset within object) — a fixed offset means a real field:");
    for ((c, off), n) in oh.iter().take(12) {
        eprintln!("  {n:>4}  {c} + {off:#x}");
    }

    // ---- 2. The descriptors themselves: inside any object?
    let mut inside = 0usize;
    for (d, _) in &t.descriptors {
        if containing(*d, 0x20000).is_some() {
            inside += 1;
        }
    }
    eprintln!(
        "descriptors inside a UObject: {inside} / {} (expected ~0: they are pool blocks)",
        t.descriptors.len()
    );

    // ---- 3. Owner of the Num=10201 per-tag u64 array, and what its values are.
    let ni: Vec<serde_json::Value> = serde_json::from_str(
        &std::fs::read_to_string(std::env::var("MJOLNIR_NAMEINDEX").unwrap()).unwrap(),
    )
    .unwrap();
    let hdr_addr = 0x1a5c47822c0u64;
    match containing(hdr_addr, 0x20000) {
        Some((base, (_, label))) => eprintln!("per-tag u64 array header {hdr_addr:#x} is {label} + {:#x}", hdr_addr - base),
        None => eprintln!("per-tag u64 array header {hdr_addr:#x} is not inside a UObject"),
    }
    if let Ok(h) = p.read(hdr_addr, 16) {
        let data = u64_at(&h, 0);
        let num = u32_at(&h, 8) as usize;
        if let Ok(a) = p.read(data, num * 8) {
            // Compare each u64 with the catalog chunk length of the tag at
            // that position, for stride 8 (u64 per tag) and 16 (two u64s).
            for stride in [8usize, 16] {
                let mut eq = 0usize;
                let mut n = 0usize;
                for pos in 0..num.min(a.len() / stride) {
                    let Some(i) = ni[pos]["tag"].as_u64() else { continue };
                    let Some(e) = catalog.entry(i as usize) else { continue };
                    n += 1;
                    let v = u64_at(&a, pos * stride);
                    if v == e.chunk.length as u64 {
                        eq += 1;
                    }
                }
                eprintln!("  stride {stride}: value == catalog chunk length for {eq}/{n} positions");
            }
            for pos in 0..6 {
                let i = ni[pos]["tag"].as_u64().unwrap_or(0) as usize;
                let e = catalog.entry(i);
                eprintln!(
                    "  [{pos}] {:#x} ({})  chunk {}  {}",
                    u64_at(&a, pos * 8),
                    u64_at(&a, pos * 8),
                    e.map(|e| e.chunk.length).unwrap_or(0),
                    e.map(|e| e.short.as_str()).unwrap_or("?")
                );
            }
        }
    }
}
