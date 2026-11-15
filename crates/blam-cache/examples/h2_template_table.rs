//! A Halo 2 template's postprocess remapping tables: for each definition in
//! stem +0x58 (0x28 each), its 4-byte entries (u16 descriptor, u8, u8 source).
use blam_cache::h2::{Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    for file in std::iter::once(&cache.map).chain(cache.shared.as_ref()) {
        for e in file.tags.iter().filter(|e| e.group == Group::new(b"stem") && e.name.ends_with(&a[2])) {
            let Some(at) = e.address.and_then(|x| file.offset(x)) else { continue };
            let root = blam_cache::h2::Struct { file, at };
            println!("{}", e.name);
            for (k, d) in root.block(0x58, 0x28).iter().enumerate() {
                let words: Vec<String> = (0..0x28).step_by(4).map(|o| format!("{:08x}", d.u32(o))).collect();
                println!(" def {k}: {}", words.join(" "));
                for (j, t) in d.block(0x20, 4).iter().enumerate() {
                    let v = t.u16(0);
                    println!("   [{j}] d {v:#06x} kind {} idx {} slot {} b2 {} src {}", (v >> 5) & 0x1F, v & 0x1F, (v >> 10) & 7, t.u8(2), t.u8(3));
                }
            }
        }
    }
}
