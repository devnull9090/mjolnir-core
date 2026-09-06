//! Search the usmap: which structs carry a property whose name contains a
//! string, and the full schema (with supers) of a named struct.
//!
//!   cargo run -p ue-asset --example usmap_find -- prop <substring>
//!   cargo run -p ue-asset --example usmap_find -- struct <name>

use ue_asset::Usmap;

static USMAP: &[u8] = include_bytes!("../../../defs/ue/Meteorite-2607-CU3.usmap");

fn main() {
    let mut args = std::env::args().skip(1);
    let mode = args.next().unwrap_or_default();
    let want = args.next().unwrap_or_default();
    let map = Usmap::parse(USMAP).expect("parse usmap");
    match mode.as_str() {
        "prop" => {
            let lower = want.to_ascii_lowercase();
            let mut names: Vec<&String> = map.structs.keys().collect();
            names.sort();
            for name in names {
                let s = &map.structs[name];
                for p in &s.props {
                    if p.name.to_ascii_lowercase().contains(&lower) {
                        println!("{name} (super {:?}) slot {} {} : {:?}", s.super_name, p.schema_index, p.name, p.ty);
                    }
                }
            }
        }
        "struct" => {
            let mut current = Some(want.clone());
            let mut base = 0u16;
            let mut chain: Vec<String> = Vec::new();
            while let Some(name) = current {
                chain.push(name.clone());
                current = map.structs.get(&name).and_then(|s| s.super_name.clone());
            }
            // Slots count from the root super downward.
            for name in chain.iter().rev() {
                let s = &map.structs[name];
                println!("== {name} ({} slots from {base})", s.prop_count);
                for p in &s.props {
                    println!("   slot {:3} {} : {:?}{}", base + p.schema_index, p.name, p.ty, if p.array_dim > 1 { format!(" [{}]", p.array_dim) } else { String::new() });
                }
                base += s.prop_count;
            }
        }
        _ => eprintln!("usage: usmap_find <prop|struct> <name>"),
    }
}
