//! The tree of tags one tag references, found by scanning its data for tag
//! references (a group four-CC followed by a datum whose index entry has that
//! group: self-validating, so no field layout is needed), recursively.
//!
//! Usage: h2_reftree <map> <group> <name substring> [depth]
//!
//! Each line is `offset  group  name`, the offset counted from the tag's
//! root. A tag's blocks follow its root in the cache, so the scan runs from
//! the root to the next tag's address (the index stores no sizes in MCC Halo
//! 2 maps). Used to map what a Halo 2 prop depends on (a fusion coil's crate
//! tag -> model -> damage effects, effects -> sounds, shaders) before
//! decoding any field.
use blam_cache::h2::{Cache, CacheFile, Group};
use std::collections::HashSet;
use std::path::Path;

fn span(file: &CacheFile, at: usize) -> &[u8] {
    // Addresses are virtual; compare image offsets of every tag in the file.
    let next = file
        .tags
        .iter()
        .filter_map(|t| t.address.and_then(|a| file.offset(a)))
        .filter(|&x| x > at)
        .min()
        .unwrap_or(at + 0x10000);
    &file.data[at..next.min(at + 0x40000).min(file.data.len())]
}

fn walk(cache: &Cache, file: &CacheFile, datum: u32, depth: usize, max: usize, seen: &mut HashSet<(usize, u32)>) {
    let Some(tag) = cache.tag(file, datum) else { return };
    let bytes = span(tag.file, tag.root.at);
    for o in (0..bytes.len().saturating_sub(8)).step_by(4) {
        let g = u32::from_le_bytes(bytes[o..o + 4].try_into().unwrap());
        let d = u32::from_le_bytes(bytes[o + 4..o + 8].try_into().unwrap());
        if g == 0 || d == u32::MAX {
            continue;
        }
        let Some(e) = tag.file.entry(d) else { continue };
        if e.group.0 != g || e.datum != d {
            continue;
        }
        println!("{}{:#07x}  {}  {}", "  ".repeat(depth), o, e.group.name(), e.name);
        let key = (tag.file as *const CacheFile as usize, d);
        if depth + 1 < max && seen.insert(key) {
            walk(cache, tag.file, d, depth + 1, max, seen);
        }
    }
}

/// `--machine`: the device fields and animation graph of a machine (type,
/// transition times, nodes, animations and their codec headers), for
/// deciding how a door or gate can be drawn.
fn machine(cache: &Cache, tag: &blam_cache::h2::Tag<'_>) {
    let r = tag.root;
    println!(
        "  machine type {} flags {:#x} position transition {:.3} accel {:.3} power transition {:.3} delay {:.3} auto radius {:.3} door open {:.3}",
        r.u16(0x11C), r.u16(0x11E), r.f32(0xC8), r.f32(0xCC), r.f32(0xC0), r.f32(0x10C), r.f32(0x118), r.f32(0x120)
    );
    let Some(model) = r.tagref(0x34).and_then(|t| cache.follow(t)) else { return };
    let Some(graph) = model.root.tagref(0x10).and_then(|t| cache.follow(t)) else { return };
    for (i, n) in graph.root.block(0x0C, 0x20).iter().enumerate() {
        println!("  node {i} {}", n.sid(0x00));
    }
    for a in graph.root.block(0x2C, 0x60).iter() {
        let frames = a.i16(0x14);
        let size = a.u32(0x28) as usize;
        let head = graph
            .file
            .offset(a.u32(0x2C))
            .and_then(|at| graph.file.data.get(at..at + size))
            .and_then(|d| d.get(a.i16(0x36).max(0) as usize..))
            .map(|d| format!("codec {} rot {} slide {} scale {}", d[0], d[1], d[2], d[3]))
            .unwrap_or_default();
        println!("  animation {} frames {} {}", a.sid(0x00), frames, head);
    }
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let g = Group::new(a[2].as_bytes().try_into().expect("4-char group"));
    let max: usize = a.get(4).and_then(|s| s.parse().ok()).unwrap_or(4);
    let file = &cache.map;
    for e in file.tags.iter().filter(|e| e.group == g && e.name.contains(&a[3])) {
        println!("{} {}", e.group.name(), e.name);
        if a.iter().any(|x| x == "--machine") {
            if let Some(t) = cache.tag(file, e.datum) {
                machine(&cache, &t);
            }
            continue;
        }
        let mut seen = HashSet::new();
        walk(&cache, file, e.datum, 1, max, &mut seen);
    }
}
