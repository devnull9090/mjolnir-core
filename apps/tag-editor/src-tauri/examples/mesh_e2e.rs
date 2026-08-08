//! The read_mesh command's path, end to end, without the GUI: catalog mesh
//! entry → parse → material chase via the package index → texture catalog hit.
//!
//!   cargo run --release --example mesh_e2e -- SM_Ground_Soil_Pile_B_Rocky

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;

fn main() -> Result<(), String> {
    let query = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "SM_Ground_Soil_Pile_B_Rocky".to_string())
        .to_lowercase();

    let usmap_bytes = std::fs::read("../../../defs/ue/Meteorite-2607-CU3.usmap")
        .map_err(|e| e.to_string())?;
    let usmap = ue_asset::Usmap::parse(&usmap_bytes).map_err(|e| e.to_string())?;

    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    println!("meshes indexed: {}", catalog.meshes.len());

    let index = catalog
        .meshes
        .iter()
        .position(|m| m.short.to_lowercase().contains(&query))
        .ok_or("no mesh matched")?;
    let entry = &catalog.meshes[index];
    println!("mesh: {} (skeletal {})", entry.short, entry.skeletal);

    let data = catalog.read_mesh_uasset(index)?;
    let ubulk = catalog.read_mesh_ubulk(index)?;
    let package = ue_asset::zen::Package::parse(&data).map_err(|e| e.to_string())?;
    let scripts = catalog.script_objects().ok_or("no scripts")?;
    let export = package
        .exports
        .iter()
        .position(|e| scripts.leaf(e.class) == Some("StaticMesh"))
        .ok_or("no StaticMesh export")?;
    let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;
    let ctx = ue_asset::unversioned::Ctx {
        usmap: &usmap,
        names: &package.names,
    };
    let mesh = ue_asset::mesh::parse_static_mesh(&ctx, bytes, ubulk.as_deref())
        .map_err(|e| e.to_string())?;

    for (slot, object) in &mesh.materials {
        let material_path = ue_asset::material::import_package_name(&package, *object);
        print!("  slot {slot}: {}", material_path.as_deref().unwrap_or("?"));
        let mut query = material_path;
        let mut resolved = None;
        for _ in 0..4 {
            let Some(pkg_name) = query.take() else { break };
            let Some(bytes) = catalog.read_package(&pkg_name) else {
                print!(" [package not found]");
                break;
            };
            let Ok(mi) = ue_asset::zen::Package::parse(&bytes) else { break };
            let Some(mi_export) = mi
                .exports
                .iter()
                .position(|e| scripts.leaf(e.class) == Some("MaterialInstanceConstant"))
            else {
                print!(" [not an MI]");
                break;
            };
            let Ok(mi_bytes) = mi.export_data(&bytes, mi_export) else { break };
            let mi_ctx = ue_asset::unversioned::Ctx {
                usmap: &usmap,
                names: &mi.names,
            };
            let Ok(info) = ue_asset::material::parse_material_instance(&mi_ctx, &mi, mi_bytes)
            else {
                print!(" [walk failed]");
                break;
            };
            if let Some(base) = ue_asset::material::base_color(&info.textures) {
                resolved = Some(base.package.clone());
                break;
            }
            query = info.parent;
        }
        match resolved {
            Some(tex) => {
                let idx = catalog.texture_by_package(&tex);
                println!(" -> {tex} (texture index {idx:?})");
            }
            None => println!(" -> no base colour"),
        }
    }
    let lod = mesh.lods.iter().find(|l| !l.indices.is_empty()).ok_or("no geometry")?;
    println!(
        "geometry: {} verts, {} tris",
        lod.positions.len() / 3,
        lod.indices.len() / 3
    );
    Ok(())
}
