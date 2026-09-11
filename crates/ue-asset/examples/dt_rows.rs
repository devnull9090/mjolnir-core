//! Print a cooked `UDataTable`'s rows, property by property.
//!
//!   cargo run -p ue-asset --example dt_rows -- <paks> <package substring> <row struct> [row name]
//!
//! `--hex` after the arguments also dumps each shown value's raw bytes for
//! the natively serialized ones (`FText` in particular), which is how a new
//! row's title gets written by hand.
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 3 {
        eprintln!("usage: dt_rows <paks> <package substring> <row struct> [row name] [--hex]");
        std::process::exit(2);
    }
    let hex = a.iter().any(|s| s == "--hex");
    let (paks, want, row_struct) = (&a[0], a[1].to_ascii_lowercase(), &a[2]);
    let only = a.get(3).filter(|s| !s.starts_with("--")).cloned();
    let oodle: Vec<std::path::PathBuf> = Vec::new();
    let usmap_bytes = std::fs::read("defs/ue/Meteorite-2607-CU3.usmap").expect("usmap");
    let usmap = ue_asset::Usmap::parse(&usmap_bytes).expect("parse usmap");
    let containers = ue_iostore::load_all(paks).expect("containers");
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().unwrap() == "global.utoc")
        .expect("global");
    let sc = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .expect("ScriptObjects");
    let scripts = ue_asset::zen::ScriptObjects::parse(
        &ue_iostore::read_chunk(global, sc, None, &oodle).unwrap(),
    )
    .expect("scripts");
    let data = containers
        .iter()
        .find_map(|c| {
            c.files
                .iter()
                .find(|(p, _)| p.ends_with(".uasset") && p.to_ascii_lowercase().contains(&want))
                .map(|(_, i)| ue_iostore::read_chunk(c, &c.chunks[*i], None, &oodle).unwrap())
        })
        .expect("no package matched");
    let zp = ue_asset::package::ZenPackage::parse(&data).expect("parse");
    let edit = ue_asset::edit::open_export(&zp, &usmap, &scripts, 0).expect("open");
    let (rows, used) = ue_asset::datatable::decode(&usmap, row_struct, &edit.tail).expect("rows");
    println!(
        "{}: {} row(s) in {} of {} tail byte(s)",
        zp.name(),
        rows.len(),
        used,
        edit.tail.len()
    );
    for r in &rows {
        let name = &zp.names.names[r.name.index as usize];
        if only.as_deref().map(|o| o != name).unwrap_or(false) {
            continue;
        }
        println!("-- {name}");
        for row in ue_asset::edit::describe(&usmap, row_struct, &zp.names.names, &r.block) {
            println!("   {} = {}", row.path, row.value);
        }
        if hex {
            for (slot, v) in &r.block.values {
                if let ue_asset::props::Val::Text(bytes) = v {
                    println!(
                        "   slot {slot} FText {} byte(s): {}",
                        bytes.len(),
                        bytes
                            .iter()
                            .map(|b| format!("{b:02x}"))
                            .collect::<Vec<_>>()
                            .join(" ")
                    );
                }
            }
        }
    }
}
