//! Print each BSP cluster's bounds and background sound.
//!
//!   cargo run --release -p blam-cache --example h2_cluster_sounds -- <map>
use blam_cache::h2::{Cache, Group};

fn main() {
    let path = std::env::args().nth(1).expect("usage: h2_cluster_sounds <map>");
    let cache = Cache::open(std::path::Path::new(&path), None).expect("open map");
    let sbsp = Group::new(b"sbsp");
    for e in cache.map.tags.iter().filter(|e| e.group == sbsp && e.address.is_some()) {
        let Some(t) = cache.tag(&cache.map, e.datum) else { continue };
        let palette = t.root.block(0xD4, 0x64);
        for (i, c) in t.root.block(0x9C, 0xB0).iter().enumerate() {
            let f: Vec<f32> = (0..6).map(|k| c.f32(0x58 + 4 * k)).collect();
            let bg = c.i16(0x72);
            let name = usize::try_from(bg).ok().and_then(|i| palette.get(i)).and_then(|p| p.tagref(0x20)).and_then(|r| cache.follow(r)).map(|t| t.name().to_string());
            println!("{i:3} bounds {f:.1?} bg {bg} {}", name.unwrap_or_default());
        }
        for (i, p) in palette.iter().enumerate() {
            let f: Vec<f32> = (0..15).map(|k| p.f32(0x28 + 4 * k)).collect();
            println!("palette {i}: {f:?}");
        }
    }
}
