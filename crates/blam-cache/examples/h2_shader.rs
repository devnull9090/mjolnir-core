//! Print a Halo 2 shader's template, postprocess bitmaps (slot order) and
//! runtime-properties maps. Usage: h2_shader <map> <shader name substring>
use blam_cache::h2::{Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    for file in std::iter::once(&cache.map).chain(cache.shared.as_ref()) {
        for (i, e) in file.tags.iter().enumerate() {
            if e.group != Group::new(b"shad") || !e.name.contains(&a[2]) || e.address.is_none() {
                continue;
            }
            let Some(off) = e.address.and_then(|x| file.offset(x)) else { continue };
            let _ = i;
            let root = blam_cache::h2::Struct { file, at: off };
            println!("{} template {}", e.name, root.tagref(0).map(|r| r.name()).unwrap_or(""));
            if let Some(p) = root.block(0x20, 0x7C).get(0) {
                for (s, b) in p.block(0x04, 0x0C).iter().enumerate() {
                    let n = cache.tag(file, b.u32(0)).map(|t| t.name().to_string()).unwrap_or("?".into());
                    println!("  slot {s}: {n} (sub {})", b.u32(4));
                }
                for (k, c) in p.block(0x0C, 4).iter().enumerate() {
                    println!("  pc{k} rgba: {:?}", [c.u8(2), c.u8(1), c.u8(0), c.u8(3)]);
                }
                for (k, o) in p.block(0x3C, 0x14).iter().enumerate() {
                    let n = o.u32(0x0C) as usize;
                    let f = p.file.offset(o.u32(0x10)).map(|at| p.file.data[at..at + n.min(48)].to_vec()).unwrap_or_default();
                    println!("  overlay{k}: period {} fn[{n}] {:02x?}", o.f32(8), f);
                }
                for (k, r) in p.block(0x44, 4).iter().enumerate() {
                    println!("  overlay-ref{k}: overlay {} type {}", r.i16(0), r.i16(2));
                }
                for (k, r) in p.block(0x4C, 2).iter().enumerate() {
                    let v = r.u16(0);
                    println!("  anim-param{k}: count {} first {}", v >> 9, v & 0x1FF);
                }
                for (k, r) in p.block(0x54, 4).iter().enumerate() {
                    println!("  anim-ref{k}: descriptor {:#06x} b {} param {}", r.u16(0), r.u8(2), r.u8(3) as i8);
                }
                for (k, c) in p.block(0x14, 0x10).iter().enumerate() {
                    println!("  vc{k}: {:?}", [c.f32(0), c.f32(4), c.f32(8), c.f32(12)]);
                }
            }
            for rp in root.block(0x0C, 0x50).iter() {
                for o in [0x00usize, 0x08, 0x10, 0x18, 0x20] {
                    if let Some(r) = rp.tagref(o) {
                        println!("  runtime +{o:#x}: {}", r.name());
                    }
                }
            }
        }
    }
}
