//! Write a StaticMesh export's raw serialized bytes (and its ubulk) to files
//! for offline byte-level diffing.
//!
//!   cargo run --release --example dump_export_bytes -- SM_Name C:\out\dir

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;

fn main() -> Result<(), String> {
    let query = std::env::args().nth(1).ok_or("usage: dump_export_bytes <query> <outdir>")?;
    let outdir = std::env::args().nth(2).ok_or("usage: dump_export_bytes <query> <outdir>")?;
    let query_l = query.to_lowercase();

    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    let scripts = catalog.script_objects().ok_or("no scripts")?;

    let index = catalog
        .meshes
        .iter()
        .position(|m| m.short.to_lowercase().contains(&query_l))
        .ok_or("no mesh matched")?;
    let entry = &catalog.meshes[index];
    println!("mesh: {} (skeletal {})", entry.short, entry.skeletal);

    let data = catalog.read_mesh_uasset(index)?;
    let ubulk = catalog.read_mesh_ubulk(index)?;
    let package = ue_asset::zen::Package::parse(&data).map_err(|e| e.to_string())?;
    let export = package
        .exports
        .iter()
        .position(|e| scripts.leaf(e.class) == Some("StaticMesh"))
        .ok_or("no StaticMesh export")?;
    let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;

    std::fs::create_dir_all(&outdir).map_err(|e| e.to_string())?;
    let short_name = entry.short.rsplit('/').next().unwrap_or(&entry.short);
    let base = format!("{outdir}/{short_name}");
    std::fs::write(format!("{base}.export.bin"), bytes).map_err(|e| e.to_string())?;
    println!("export: {} bytes -> {base}.export.bin", bytes.len());
    if let Some(b) = ubulk {
        std::fs::write(format!("{base}.ubulk.bin"), &b).map_err(|e| e.to_string())?;
        println!("ubulk: {} bytes -> {base}.ubulk.bin", b.len());
    }
    Ok(())
}
