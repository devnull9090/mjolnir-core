//! Dump a tag's root words and every plausible block {count, address} with
//! the floats of its first element. Usage: h2_tagdump <map> <group> <name substring> [root bytes]
//! [block offset] [element bytes]: with a block, every element of it as floats.
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
            if let (Some(bo), Some(sz)) = (a.get(5), a.get(6)) {
                let bo = usize::from_str_radix(bo.trim_start_matches("0x"), 16).expect("block offset");
                let sz = usize::from_str_radix(sz.trim_start_matches("0x"), 16).expect("element bytes");
                for (i, el) in root.block(bo, sz).iter().enumerate() {
                    let fl: Vec<String> = (0..sz / 4).map(|k| format!("{:.3}", el.f32(k * 4))).collect();
                    let words: Vec<String> = (0..sz / 4).map(|k| format!("{:08x}", el.u32(k * 4))).collect();
                    println!("  [{i}] {}
      {}", fl.join(" "), words.join(" "));
                }
                continue;
            }
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
