//! Print a tag's root as words and floats, four bytes a line.
//! Usage: h2_rootdump <map> <group> <name substring> [root bytes, hex]
use blam_cache::h2::{Cache, Group, Struct};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let g = Group::new(a[2].as_bytes().try_into().expect("4-char group"));
    let len: usize = a.get(4).and_then(|s| usize::from_str_radix(s.trim_start_matches("0x"), 16).ok()).unwrap_or(0x100);
    for file in std::iter::once(&cache.map).chain(cache.shared.as_ref()) {
        for e in file.tags.iter() {
            if e.group != g || !e.name.contains(&a[3]) {
                continue;
            }
            let Some(off) = e.address.and_then(|x| file.offset(x)) else { continue };
            let root = Struct { file, at: off };
            println!("{}", e.name);
            for o in (0..len).step_by(4) {
                println!("  +{o:#05x} {:08x} {:>14.4}", root.u32(o), root.f32(o));
            }
        }
    }
}
