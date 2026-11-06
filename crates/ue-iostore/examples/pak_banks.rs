//! Write the ids of every Wwise bank the game ships, for `defs/hce/shipped_banks.json`.
//! Run it after a game update: a map pack may not carry a bank with one of these ids.
//!
//!   cargo run --release -p ue-iostore --example pak_banks -- <paks> <out.json>
use std::collections::BTreeSet;

fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args.next().expect("usage: pak_banks <paks> <out.json>");
    let out = args.next().expect("out file");
    let mut ids = BTreeSet::new();
    for pak in ue_iostore::pak::load_all(&paks).expect("load paks") {
        for rel in pak.files.keys() {
            let name = rel.rsplit('/').next().unwrap_or(rel);
            if let Some(id) = name.strip_suffix(".bnk") {
                if let Ok(id) = id.parse::<u32>() {
                    ids.insert(id);
                }
            }
        }
    }
    let rows: Vec<String> = ids.iter().map(u32::to_string).collect();
    std::fs::write(&out, format!("[\n{}\n]\n", rows.join(",\n"))).expect("write");
    println!("{} banks -> {out}", ids.len());
}
