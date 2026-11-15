//! A Halo 2 template's passes and what each feeds its shaders. The stem's
//! postprocess definition (+0x58, 0x28) holds five {count, address} blocks;
//! block 2 is the passes (10 bytes: the `spas` reference, then a u16 of
//! implementations: start in the low 9 bits, count above), block 3 the
//! implementations (6 bytes: three u16 ranges, start low 9 bits and count
//! above, into the remappings for the bitmaps, the pixel constants and the
//! vertex constants) and block 4 the remappings (4 bytes: u16 descriptor,
//! u8, u8 source; kind = descriptor >> 5 & 31, register = & 31, source
//! slot = >> 10 & 7).
//! Usage: h2_template_blocks <map> <template name suffix>
use blam_cache::h2::{Cache, Group};
use std::path::Path;

fn range(v: u16) -> (usize, usize) {
    ((v & 0x1FF) as usize, (v >> 9) as usize)
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    for file in std::iter::once(&cache.map).chain(cache.shared.as_ref()) {
        for e in file.tags.iter().filter(|e| e.group == Group::new(b"stem") && e.name.ends_with(&a[2])) {
            let Some(at) = e.address.and_then(|x| file.offset(x)) else { continue };
            let root = blam_cache::h2::Struct { file, at };
            println!("{}", e.name);
            let Some(d) = root.block(0x58, 0x28).get(0) else { continue };
            let passes = d.block(0x10, 10);
            let imps = d.block(0x18, 6);
            let remaps = d.block(0x20, 4);
            for (p, pass) in passes.iter().enumerate() {
                let name = file.entry(pass.u32(4)).map(|t| t.name.rsplit('\\').next().unwrap_or("").to_string()).unwrap_or("?".into());
                let (start, count) = range(pass.u16(8));
                println!(" pass {p}: {name} (implementations {start}..{})", start + count);
                for i in start..start + count {
                    let Some(im) = imps.get(i) else { continue };
                    let mut parts = Vec::new();
                    for (label, k) in [("bitmaps", 0), ("pixel", 2), ("vertex", 4)] {
                        let (s, n) = range(im.u16(k));
                        let items: Vec<String> = (s..s + n)
                            .filter_map(|r| remaps.get(r))
                            .map(|r| {
                                let v = r.u16(0);
                                format!("r{}<-{}{}", v & 31, if (v >> 10) & 7 == 0 { "" } else { "x" }, r.u8(3))
                            })
                            .collect();
                        if !items.is_empty() {
                            parts.push(format!("{label} {}", items.join(" ")));
                        }
                    }
                    println!("   impl {i}: {}", parts.join(" | "));
                }
            }
        }
    }
}
