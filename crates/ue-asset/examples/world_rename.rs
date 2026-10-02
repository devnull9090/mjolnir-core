//! Show a cooked package's identity — name, names, exports — and optionally
//! write it back under another package path.
//!
//!   cargo run -p ue-asset --example world_rename -- <in.umap> [/Game/New/Path/Leaf out.umap]
//!
//! Made for the bare canvas world: a standalone map needs a world of its
//! own, and a bare level renamed from `/Solo/B40/B40` to `/Solo/BGL/BGL` is
//! the smallest package that can test whether a brand-new Unreal world
//! package loads through the campaign flow.
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&a[0]).expect("read");
    let mut zp = ue_asset::package::ZenPackage::parse(&data).expect("parse");
    println!("{} ({} bytes)", zp.name(), data.len());
    for (i, n) in zp.names.names.iter().enumerate() {
        println!("  name[{i}] {n}");
    }
    for (i, e) in zp.export_map.iter().enumerate() {
        println!(
            "  export[{i}] {} hash {:#018x} class {:#x} outer {:#x}",
            zp.names
                .names
                .get(e.name_index as usize)
                .map(String::as_str)
                .unwrap_or("?"),
            e.public_export_hash,
            e.class,
            e.outer
        );
    }
    for (i, n) in zp.imported_package_names.names.iter().enumerate() {
        println!("  imported package[{i}] {n}");
    }
    if a.len() >= 3 {
        let log = zp.rename_package(&a[1]).expect("rename");
        for l in &log {
            println!("  {l}");
        }
        let out = zp.write();
        std::fs::write(&a[2], &out).expect("write");
        let back = ue_asset::package::ZenPackage::parse(&out).expect("re-parse");
        println!("  wrote {} as {} ({} bytes)", a[2], back.name(), out.len());
    }
}
