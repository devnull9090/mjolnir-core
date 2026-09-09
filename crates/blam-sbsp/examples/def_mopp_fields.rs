//! The two copies of a definition's mopp header — the one inside the
//! definition element (+3289 size, +3293 code info, +3329 mopp scale) and the
//! one in its `mopp codes` element (56 size, 32 code info) — plus a histogram
//! of its surface flags and materials.
//!   cargo run -p blam-sbsp --example def_mopp_fields -- <payload> <def>...
use blam_sbsp::transplant;
use blam_tag::blockedit::find_block;
use std::collections::BTreeMap;

const DEFS: &str = "resource interface.raw_resources[0].raw_items.instanced geometries definitions";

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    for d in a[1..].iter().filter_map(|s| s.parse::<usize>().ok()) {
        let (e, _) = transplant::donor_element(&file, DEFS, d).expect("definition element");
        let f = |o: usize| f32::from_le_bytes(e[o..o + 4].try_into().unwrap());
        let u = |o: usize| u32::from_le_bytes(e[o..o + 4].try_into().unwrap());
        println!("-- definition {d}: element {} bytes", e.len());
        let _ = (f, u);
        let base = transplant::definition(d);
        let base = base.trim_end_matches(".collision info");
        match transplant::donor_element(&file, &format!("{base}.mopp codes"), 0) {
            Ok((m, _)) => {
                let g = |o: usize| f32::from_le_bytes(m[o..o + 4].try_into().unwrap());
                println!("   mopp element:     size {} code info ({:.3}, {:.3}, {:.3}) w {:.1}",
                    u32::from_le_bytes(m[56..60].try_into().unwrap()), g(32), g(36), g(40), g(44));
            }
            Err(_) => println!("   mopp element:     none"),
        }
        let surfaces = find_block(&layout, &file, &root, &format!("{base}.collision info.surfaces")).expect("surfaces");
        let mut flags: BTreeMap<u16, usize> = BTreeMap::new();
        let mut mats: BTreeMap<i16, usize> = BTreeMap::new();
        for i in 0..surfaces.block.count as usize {
            let s = surfaces.block.element(i).unwrap();
            *flags.entry(u16::from_le_bytes([s[10], s[11]])).or_default() += 1;
            *mats.entry(i16::from_le_bytes([s[4], s[5]])).or_default() += 1;
        }
        println!("   surface flags {flags:?}");
        println!("   surface materials {mats:?}");
    }
}
