//! Print a Halo 2 map's netgame equipment as the tags hold it (scnr +0x120,
//! 0x90 each), with every permutation of each item or vehicle collection.
//! One line per placement: flags, game types, spawn time, respawn on empty
//! time, respawn timer starts, classification, collection, and the
//! collection's own spawn time and permutations (weight, object, variant).
//!
//! Usage: h2_netgame_items <map>...
use blam_cache::h2::Cache;
use std::path::Path;

fn main() {
    for map in std::env::args().skip(1) {
        let cache = Cache::open(Path::new(&map), None).expect("open");
        let scnr = cache.scenario().expect("scnr");
        let name = Path::new(&map).file_stem().unwrap().to_string_lossy().into_owned();
        for (i, e) in scnr.root.block(0x120, 0x90).iter().enumerate() {
            let types: Vec<String> = (0..4).map(|k| e.i16(4 + 2 * k).to_string()).collect();
            let Some(r) = e.tagref(0x58) else {
                println!("{name}\t{i}\tno collection");
                continue;
            };
            let (spawn, perms) = cache
                .follow(r)
                .map(|c| {
                    let perms: Vec<String> = c
                        .root
                        .block(0, 0x10)
                        .iter()
                        .map(|p| {
                            let object = p.tagref(4).map(|t| t.name().to_string()).unwrap_or_default();
                            format!("{}x {} '{}'", p.f32(0), object, c.file.string(p.u32(0x0C)))
                        })
                        .collect();
                    (c.root.i16(8), perms)
                })
                .unwrap_or((0, Vec::new()));
            println!(
                "{name}\t{i}\tflags {:#x}\ttypes {}\tw0c {}\tspawn {}\tempty {}\tstarts {}\tclass {}\t{}\tcollection spawn {}\t{}",
                e.u32(0),
                types.join(","),
                e.i16(0x0C),
                e.i16(0x0E),
                e.i16(0x10),
                e.i16(0x12),
                e.u8(0x14),
                r.name(),
                spawn,
                perms.join(" | "),
            );
        }
    }
}
