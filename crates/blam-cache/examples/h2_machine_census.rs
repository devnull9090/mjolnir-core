//! Every machine (`mach`) of Halo 2 maps: its device and machine fields and
//! whether its `device:position` animation decodes (crate::h2::door).
//! Usage: h2_machine_census <map>...
//!
//! Device (MCC Halo 2): position transition time 0xC8 (stored as a rate),
//! automatic activation radius 0x118. Machine: type 0x11C (0 door,
//! 1 platform, 2 gear), flags 0x11E, door open time 0x120, collision
//! response 0x12C.
use blam_cache::h2::{door, Cache, Group};
use std::path::Path;

fn main() {
    for path in std::env::args().skip(1) {
        let cache = Cache::open(Path::new(&path), None).expect("open");
        let file = &cache.map;
        println!("{}", Path::new(&path).file_stem().unwrap().to_string_lossy());
        for e in file.tags.iter().filter(|e| e.group == Group::new(b"mach")) {
            let Some(t) = cache.tag(file, e.datum) else { continue };
            let r = t.root;
            let leaf = e.name.rsplit('\\').next().unwrap_or(&e.name);
            let head = format!(
                "  {leaf:32} type {} flags {:#06x} rate {:.3} radius {:.2} open {:.2} response {}",
                r.u16(0x11C),
                r.u16(0x11E),
                r.f32(0xC8),
                r.f32(0x118),
                r.f32(0x120),
                r.u16(0x12C)
            );
            match door::opening(&cache, &t) {
                Ok(o) => {
                    let moving = (0..o.nodes.len())
                        .filter(|&n| o.poses.iter().any(|f| f[n] != o.poses[0][n]))
                        .count();
                    println!("{head}  opening: {} nodes, {moving} moving, {} frames, {:.2} s", o.nodes.len(), o.frames, o.seconds);
                }
                Err(why) => println!("{head}  no opening: {why}"),
            }
        }
    }
}
