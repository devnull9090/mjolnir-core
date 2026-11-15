//! Write the DXBC shader blobs a Halo 2 `spas` tag holds or points at, for
//! `fxc /dumpbin`. Usage: h2_dxbc <map> <name substring> <out dir> [group, default spas]
use blam_cache::h2::{Cache, Group};
use std::collections::BTreeSet;
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let out = Path::new(&a[3]);
    std::fs::create_dir_all(out).unwrap();
    for file in std::iter::once(&cache.map).chain(cache.shared.as_ref()) {
        for e in file.tags.iter().filter(|e| e.group == Group::new(a.get(4).map(|g| g.as_bytes().try_into().expect("group")).unwrap_or(b"spas")) && e.name.contains(&a[2])) {
            let Some(at) = e.address.and_then(|x| file.offset(x)) else { continue };
            let end = (at + e.size as usize).min(file.data.len());
            let mut starts = BTreeSet::new();
            for i in at..end.saturating_sub(4) {
                if &file.data[i..i + 4] == b"DXBC" {
                    starts.insert(i);
                }
            }
            for i in (at..end.saturating_sub(4)).step_by(4) {
                let w = u32::from_le_bytes(file.data[i..i + 4].try_into().unwrap());
                if let Some(o) = file.offset(w) {
                    if file.data.get(o..o + 4) == Some(b"DXBC") {
                        starts.insert(o);
                    }
                }
            }
            let stem = e.name.rsplit(char::from(92)).next().unwrap_or("pass");
            for (k, s) in starts.iter().enumerate() {
                let len = u32::from_le_bytes(file.data[s + 0x18..s + 0x1C].try_into().unwrap()) as usize;
                let p = out.join(format!("{stem}_{k}.dxbc"));
                std::fs::write(&p, &file.data[*s..s + len]).unwrap();
                println!("{} -> {} ({len} bytes)", e.name, p.display());
            }
        }
    }
}
