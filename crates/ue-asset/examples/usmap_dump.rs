//! Sanity-check a usmap: counts, and the schemas the mesh parser will lean on.
//!
//!   cargo run -p ue-asset --example usmap_dump -- defs/ue/Meteorite-2607-CU3.usmap

use ue_asset::Usmap;

fn main() {
    let path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "defs/ue/Meteorite-2607-CU3.usmap".into());
    let data = std::fs::read(&path).expect("read usmap");
    let map = Usmap::parse(&data).expect("parse usmap");
    println!("enums: {}  structs: {}", map.enums.len(), map.structs.len());

    for class in [
        "StaticMesh",
        "SkeletalMesh",
        "MaterialInstanceConstant",
        "Texture2D",
        "StaticMeshComponent",
        "BodySetup",
    ] {
        match map.structs.get(class) {
            Some(s) => {
                println!(
                    "\n{} : {} (own slots {}, chain slots {})",
                    s.name,
                    s.super_name.as_deref().unwrap_or("-"),
                    s.prop_count,
                    map.total_slots(class),
                );
                for p in s.props.iter().take(12) {
                    println!("  [{:>3}] x{} {:<32} {:?}", p.schema_index, p.array_dim, p.name, p.ty);
                }
            }
            None => println!("\n{class}: MISSING"),
        }
    }
}
