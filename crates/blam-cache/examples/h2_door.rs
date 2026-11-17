//! Print a Halo 2 door's opening (crate::h2::door): node defaults, frame 0
//! and the last frame of every node, and its render model sections' vertex
//! node indices. Usage: h2_door <map> <mach name substring>
use blam_cache::h2::{door, geometry, Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let file = &cache.map;
    for e in file.tags.iter().filter(|e| e.group == Group::new(b"mach") && e.name.contains(&a[2])) {
        let Some(t) = cache.tag(file, e.datum) else { continue };
        println!("{}", e.name);
        match door::opening(&cache, &t) {
            Ok(o) => {
                println!("  {} frames over {:.2} s", o.frames, o.seconds);
                for (i, n) in o.nodes.iter().enumerate() {
                    let (t0, r0) = o.poses[0][i];
                    let (t1, r1) = o.poses[o.frames - 1][i];
                    println!(
                        "  {i:2} {:12} parent {:2} default t {:?} r {:?}\n       f0 t {:?} r {:?}\n       fN t {:?} r {:?}",
                        n.name, n.parent, n.translation, n.rotation, t0, r0, t1, r1
                    );
                }
            }
            Err(why) => println!("  {why}"),
        }
        let hlmt = t.root.tagref(0x34).and_then(|r| cache.follow(r)).unwrap();
        let mode = hlmt.root.tagref(0x00).and_then(|r| cache.follow(r)).unwrap();
        let sections = mode.root.block(0x24, 0x5C);
        for (i, sec) in sections.iter().enumerate() {
            let bounds = sec.block(0x1C, 0x38).get(0).or_else(|| mode.root.block(0x14, 0x38).get(0));
            let c = geometry::Compression::from(sec.u16(0x1A), bounds);
            match geometry::read(&cache, mode.file, sec.at(0x38), sec.u16(0x04) as usize, c) {
                Ok(s) => {
                    let mut h = [0usize; 256];
                    for &n in &s.vertex_nodes {
                        h[n as usize] += 1;
                    }
                    let used: Vec<String> = h.iter().enumerate().filter(|(_, &c)| c > 0).map(|(n, c)| format!("{n}:{c}")).collect();
                    let w: Vec<String> = (0..8).map(|k| format!("{:04x}", sec.u16(k * 2))).collect();
                    println!("  section {i}: {} vertices, words {} nodes {}", s.vertices.len(), w.join(" "), used.join(" "));
                    println!("    resources {:?} node map {:?}", s.resources, s.node_map);
                }
                Err(err) => println!("  section {i}: {err}"),
            }
        }
    }
}
