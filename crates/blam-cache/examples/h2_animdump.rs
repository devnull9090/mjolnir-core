//! Dump a machine's animation graph data: every animation's block fields and
//! its frame data as hex words, for decoding multi-node codecs (Zanzibar's
//! house gate: 13 nodes, codec 6, 4 rotating and 10 sliding).
//!
//! Usage: h2_animdump <map> <mach name substring> [animation name]
use blam_cache::h2::{Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let file = &cache.map;
    let g = Group::new(b"mach");
    for e in file.tags.iter().filter(|e| e.group == g && e.name.contains(&a[2])) {
        let Some(t) = cache.tag(file, e.datum) else { continue };
        let Some(model) = t.root.tagref(0x34).and_then(|r| cache.follow(r)) else { continue };
        let Some(graph) = model.root.tagref(0x10).and_then(|r| cache.follow(r)) else { continue };
        println!("{} graph {}", e.name, graph.name());
        let nodes = graph.root.block(0x0C, 0x20);
        for (i, n) in nodes.iter().enumerate() {
            let w: Vec<String> = (0..8).map(|k| format!("{:08x}", n.u32(k * 4))).collect();
            println!("  node {i:2} {:12} {}", n.sid(0x00), w.join(" "));
        }
        for an in graph.root.block(0x2C, 0x60).iter() {
            if let Some(want) = a.get(3) {
                if an.sid(0x00) != want {
                    continue;
                }
            }
            let w: Vec<String> = (0..24).map(|k| format!("{:08x}", an.u32(k * 4))).collect();
            println!("  animation {}\n    fields {}", an.sid(0x00), w.join(" "));
            let size = an.u32(0x28) as usize;
            let Some(at) = graph.file.offset(an.u32(0x2C)) else { continue };
            let data = &graph.file.data[at..at + size];
            println!("    data {} bytes, static size {}", size, an.i16(0x36));
            for (row, chunk) in data.chunks(32).enumerate() {
                let words: Vec<String> = chunk.chunks(4).map(|c| {
                    let mut b = [0u8; 4];
                    b[..c.len()].copy_from_slice(c);
                    format!("{:08x}", u32::from_le_bytes(b))
                }).collect();
                println!("    {:04x}: {}", row * 32, words.join(" "));
            }
        }
    }
}
