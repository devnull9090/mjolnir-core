//! Print the Halo 2 sound classes: the first words and floats of each
//! 0x78-byte entry of `sound\sound_classes` (in shared.map).
//!
//!   cargo run --release -p blam-cache --example h2_sound_classes -- <shared.map>
use blam_cache::h2::{Cache, Group};

fn main() {
    let path = std::env::args().nth(1).expect("usage: h2_sound_classes <map>");
    let cache = Cache::open(std::path::Path::new(&path), None).expect("open map");
    let sncl = Group::new(b"sncl");
    for f in [Some(&cache.map), cache.shared.as_ref()].into_iter().flatten() {
        for e in f.tags.iter().filter(|e| e.group == sncl && e.address.is_some()) {
            let Some(t) = cache.tag(f, e.datum) else { continue };
            for (i, c) in t.root.block(0x00, 0x78).iter().enumerate() {
                let words: Vec<i16> = (0..8).map(|k| c.i16(k * 2)).collect();
                let floats: Vec<f32> = (4..30).map(|k| c.f32(k * 4)).collect();
                println!("{i:2} {words:?} {floats:?}");
            }
            return;
        }
    }
}
