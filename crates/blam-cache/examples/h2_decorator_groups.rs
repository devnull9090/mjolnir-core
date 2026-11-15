//! Print a Halo 2 map's decorator groups with their vertex and index runs,
//! and every resource of each cache block (type, locator, size).
//! Usage: h2_decorator_groups <map>
use blam_cache::h2::{Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let file = &cache.map;
    for e in file.tags.iter().filter(|e| e.group == Group::new(b"sbsp")) {
        let Some(at) = e.address.and_then(|x| file.offset(x)) else { continue };
        let root = blam_cache::h2::Struct { file, at };
        for d in root.block(0x234, 0x30).iter() {
            for (i, b) in d.block(0x10, 0x34).iter().enumerate() {
                let rs: Vec<String> = b.block(0x10, 0x10).iter().map(|r| format!("t{} loc{:#x} {}b", r.u8(0), r.u16(4), r.u32(8))).collect();
                println!("block {i}: raw {:#x} size {} [{}]", b.u32(0), b.u32(4), rs.join(", "));
            }
            for (i, g) in d.block(0x18, 0x18).iter().enumerate() {
                println!("group {i}: set {} type {} shader {} block {} first {} count {} verts {}+{} idx {}+{}",
                    g.u8(0), g.u8(1), g.u8(2) as i8, g.i16(6), g.u16(8), g.u16(10), g.u16(0xC), g.u16(0xE), g.u16(0x10), g.u16(0x12));
            }
        }
    }
}
