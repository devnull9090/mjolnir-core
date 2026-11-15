//! List the tags of one group a Halo 2 tag references, in tag order:
//! by default the `spas` passes a shader template (`stem`) draws.
//! Usage: h2_template_passes <map> <name suffix> [owner group] [referenced group]
use blam_cache::h2::{Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let group = |i: usize, d: &[u8; 4]| Group::new(a.get(i).map(|g| g.as_bytes().try_into().expect("4-char group")).unwrap_or(d));
    let owner = group(3, b"stem");
    let spas = group(4, b"spas");
    for file in std::iter::once(&cache.map).chain(cache.shared.as_ref()) {
        for e in file.tags.iter().filter(|e| e.group == owner && e.name.ends_with(&a[2])) {
            let Some(at) = e.address.and_then(|x| file.offset(x)) else { continue };
            println!("{}", e.name);
            // Tag data may sit past the root; scan the referenced region.
            let end = (at + e.size as usize).min(file.data.len());
            for i in (at..end.saturating_sub(8)).step_by(4) {
                let g = u32::from_le_bytes(file.data[i..i + 4].try_into().unwrap());
                if g == spas.0 {
                    let d = u32::from_le_bytes(file.data[i + 4..i + 8].try_into().unwrap());
                    if let Some(t) = file.entry(d) {
                        println!("  +{:#x} {}", i - at, t.name);
                    }
                }
            }
        }
    }
}
