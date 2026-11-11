//! Dump a tag's root words and every plausible block {count, address} with
//! the floats of its first element. Usage: h2_tagdump <map> <group> <name substring> [root bytes]
use blam_cache::h2::{Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let g = Group::new(a[2].as_bytes().try_into().expect("4-char group"));
    let len: usize = a.get(4).and_then(|s| usize::from_str_radix(s.trim_start_matches("0x"), 16).ok()).unwrap_or(0x200);
    for file in std::iter::once(&cache.map).chain(cache.shared.as_ref()) {
        for e in file.tags.iter() {
            if e.group != g || !e.name.contains(&a[3]) {
                continue;
            }
            let Some(off) = e.address.and_then(|x| file.offset(x)) else { continue };
            let root = blam_cache::h2::Struct { file, at: off };
            println!("{} ({})", e.name, a[2]);
            for o in (0..len).step_by(4) {
                let count = root.u32(o);
                let addr = root.u32(o + 4);
                if (1..=64).contains(&count) && file.offset(addr).is_some() {
                    let el = blam_cache::h2::Struct { file, at: file.offset(addr).unwrap() };
                    let fl: Vec<String> = (0..12).map(|k| format!("{:.3}", el.f32(k * 4))).collect();
                    println!("  +{o:#05x} block x{count} -> floats {}", fl.join(" "));
                }
            }
        }
    }
}
