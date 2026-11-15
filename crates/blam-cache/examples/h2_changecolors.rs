//! A Halo 2 object's change colours: obje +0xAC (0x10 each: initial
//! permutations block 0x00 of 0x20 each: weight, lower RGB, upper RGB,
//! variant string id; functions block 0x08). Usage: <map> <group> <name>
use blam_cache::h2::{Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let g = Group::new(a[2].as_bytes().try_into().expect("group"));
    for file in std::iter::once(&cache.map).chain(cache.shared.as_ref()) {
        for e in file.tags.iter().filter(|e| e.group == g && e.name.contains(&a[3])) {
            let Some(off) = e.address.and_then(|x| file.offset(x)) else { continue };
            let root = blam_cache::h2::Struct { file, at: off };
            println!("{}", e.name);
            for (c, cc) in root.block(0xAC, 0x10).iter().enumerate() {
                for p in cc.block(0x00, 0x20).iter() {
                    println!("  colour {c}: weight {:.2} lower {:?} upper {:?} variant '{}'", p.f32(0), p.vec3(4), p.vec3(0x10), p.sid(0x1C));
                }
                println!("  colour {c}: {} function(s)", cc.block(0x08, 0x20).count);
            }
        }
    }
}
