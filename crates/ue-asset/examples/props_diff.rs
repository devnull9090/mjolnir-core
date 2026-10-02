//! Decode one export's property block and print it slot by slot, with the
//! head of the raw bytes. Two packages side by side show exactly what an edit
//! changed in the serialization the engine reads.
//!
//!   cargo run -p ue-asset --example props_diff -- <paks> <donor substring> [edited.uasset]
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let (paks, want) = (&a[0], a[1].to_ascii_lowercase());
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

    let (ci, cidx) = containers
        .iter()
        .enumerate()
        .find_map(|(ci, c)| {
            c.files
                .iter()
                .find(|(p, _)| p.ends_with(".uasset") && p.to_ascii_lowercase().contains(&want))
                .map(|(_, i)| (ci, *i))
        })
        .expect("no donor");
    let donor = ue_iostore::read_chunk(&containers[ci], &containers[ci].chunks[cidx], None, &oodle)
        .expect("read donor");

    let show = |label: &str, data: &[u8]| {
        let zp = ue_asset::package::ZenPackage::parse(data).expect("parse");
        let export = (0..zp.export_map.len())
            .find(|i| {
                ue_asset::edit::open_export(&zp, &usmap, &scripts, *i)
                    .map(|e| e.class == "StaticMesh")
                    .unwrap_or(false)
            })
            .expect("no StaticMesh export");
        let bytes = zp.export_bytes(export).unwrap();
        let edit = ue_asset::edit::open_export(&zp, &usmap, &scripts, export).expect("open");
        println!(
            "== {label}: export {export}, {} byte(s), tail {}",
            bytes.len(),
            edit.tail.len()
        );
        let head: Vec<String> = bytes[..48.min(bytes.len())]
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        println!("   head {}", head.join(" "));
        for (slot, v) in &edit.block.values {
            let name = usmap
                .resolve("StaticMesh", *slot)
                .map(|(_, p)| p.name.clone())
                .unwrap_or_default();
            let brief = match v {
                ue_asset::props::Val::Array(items) => format!("Array({} item(s))", items.len()),
                other => format!("{other:?}"),
            };
            println!("   slot {slot:2} {name}: {brief}");
        }
        // Re-encoding the decoded block must reproduce the bytes it came
        // from; anything else means the codec is guessing.
        match edit.block.encode(&usmap, "StaticMesh") {
            Ok(again) => {
                let same = again.as_slice() == &bytes[..again.len().min(bytes.len())];
                println!(
                    "   re-encode: {} byte(s) vs {} of prefix -- {}",
                    again.len(),
                    bytes.len() - edit.tail.len(),
                    if same && again.len() == bytes.len() - edit.tail.len() {
                        "byte-exact"
                    } else {
                        "DIFFERS"
                    }
                );
            }
            Err(e) => println!("   re-encode failed: {e}"),
        }
    };

    show("donor", &donor);
    if let Some(path) = a.get(2) {
        let edited = std::fs::read(path).expect("read edited");
        show(path, &edited);
    }
}
