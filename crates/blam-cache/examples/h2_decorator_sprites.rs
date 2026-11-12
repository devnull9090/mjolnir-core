//! Print the first sprite vertices of a Halo 2 map's first decorator cache
//! block that has them (locator 0x48, 0x30 each: position, offset, axis,
//! texture coordinate, colour) and its sprite indices (locator 0x50).
//! Usage: h2_decorator_sprites <map> [vertices to show]
use blam_cache::h2::{Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let show: usize = a.get(2).and_then(|s| s.parse().ok()).unwrap_or(8);
    let file = &cache.map;
    for e in file.tags.iter().filter(|e| e.group == Group::new(b"sbsp")) {
        let Some(at) = e.address.and_then(|x| file.offset(x)) else { continue };
        let root = blam_cache::h2::Struct { file, at };
        for d in root.block(0x234, 0x30).iter() {
            for b in d.block(0x10, 0x34).iter() {
                let rs = blam_cache::h2::decorator::raw_resources_pub(&cache, file, b).expect("raw");
                let Some((_, v)) = rs.iter().find(|(l, _)| *l == 0x48) else { continue };
                let idx: Vec<u16> = rs.iter().find(|(l, _)| *l == 0x50).map(|(_, b)| b.chunks_exact(2).map(|c| u16::from_le_bytes([c[0], c[1]])).collect()).unwrap_or_default();
                let f = |b: &[u8], o: usize| f32::from_le_bytes(b[o..o + 4].try_into().unwrap());
                for (k, x) in v.chunks_exact(0x30).take(show).enumerate() {
                    println!("v{k}: pos ({:.3}, {:.3}, {:.3}) off ({:.3}, {:.3}, {:.3}) axis ({:.3}, {:.3}, {:.3}) uv ({:.3}, {:.3}) col {:08x}",
                        f(x, 0), f(x, 4), f(x, 8), f(x, 12), f(x, 16), f(x, 20), f(x, 24), f(x, 28), f(x, 32), f(x, 36), f(x, 40), u32::from_le_bytes(x[44..48].try_into().unwrap()));
                }
                println!("indices {:?}", &idx[..idx.len().min(12)]);
                return;
            }
        }
    }
}
