//! Print a Halo 2 map's scenery/crate placements of objects whose path
//! contains a filter, with the bytes after the shared 0x34 header
//! (permutation: variant, active change colours, colours). Census aid.
use blam_cache::h2::Cache;
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let root = cache.scenario().expect("scnr").root;
    for (kind, pal, size, group) in [(0x50usize, 0x58usize, 0x5Cusize, "scen"), (0x328, 0x330, 0x4C, "bloc")] {
        let palette = root.block(pal, 0x28);
        for e in root.block(kind, size).iter() {
            let i = e.i16(0);
            let Some(obj) = (i >= 0).then(|| palette.get(i as usize)).flatten().and_then(|p| p.tagref(0)).and_then(|r| cache.follow(r)) else { continue };
            if !obj.name().contains(&a[2]) {
                continue;
            }
            let tail: Vec<String> = (0x34..size).step_by(4).map(|o| format!("{:08x}", e.u32(o))).collect();
            println!("{group} {} pos {:?} variant '{}' tail {}", obj.name(), e.vec3(0x08), e.sid(0x34), tail.join(" "));
        }
    }
}
