//! Chase a mesh to its textures: mesh → material instance → texture packages.
//!
//!   cargo run --release --example dump_material -- MI_Dead_Elite_Armor
//!   cargo run --release --example dump_material -- SM_Ground_Soil_Pile_B_Rocky --from-mesh

use tag_editor_lib::install;
use ue_asset::material::{base_color, import_package_name, parse_material_instance};
use ue_asset::mesh::parse_static_mesh;
use ue_asset::unversioned::Ctx;
use ue_asset::zen::{Package, ScriptObjects};
use ue_asset::Usmap;

fn find_chunk<'a>(
    containers: &'a [ue_iostore::Container],
    query: &str,
    ext: &str,
) -> Option<(&'a ue_iostore::Container, usize, String)> {
    let query = query.to_lowercase();
    for c in containers {
        for (rel, &idx) in &c.files {
            let lower = rel.to_lowercase();
            if lower.ends_with(ext) && lower.contains(&query) {
                return Some((c, idx, c.full_path(rel)));
            }
        }
    }
    None
}

fn main() -> Result<(), String> {
    let query = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "MI_Dead_Elite_Armor".to_string());
    let from_mesh = std::env::args().any(|a| a == "--from-mesh");
    let usmap_path = "../../../defs/ue/Meteorite-2607-CU3.usmap";

    let usmap_bytes = std::fs::read(usmap_path).map_err(|e| format!("{usmap_path}: {e}"))?;
    let usmap = Usmap::parse(&usmap_bytes).map_err(|e| e.to_string())?;

    let found = install::detect();
    let paks = found.paks.ok_or("no install")?;
    let oodle_roots: Vec<std::path::PathBuf> = found.oodle.iter().map(Into::into).collect();
    let containers = ue_iostore::load_all(&paks).map_err(|e| e.to_string())?;

    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .ok_or("no global.utoc")?;
    let chunk = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .ok_or("no ScriptObjects chunk")?;
    let script_bytes =
        ue_iostore::read_chunk(global, chunk, None, &oodle_roots).map_err(|e| e.to_string())?;
    let scripts = ScriptObjects::parse(&script_bytes).map_err(|e| e.to_string())?;

    // Resolve the material query: either straight to an MI package, or via a
    // mesh's first material slot.
    let mut material_query = query.clone();
    if from_mesh {
        let (c, idx, full) =
            find_chunk(&containers, &query, ".uasset").ok_or("no mesh package")?;
        let data = ue_iostore::read_chunk(c, &c.chunks[idx], None, &oodle_roots)
            .map_err(|e| e.to_string())?;
        let package = Package::parse(&data).map_err(|e| e.to_string())?;
        let export = package
            .exports
            .iter()
            .position(|e| scripts.leaf(e.class) == Some("StaticMesh"))
            .ok_or("no StaticMesh export")?;
        let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;
        let ctx = Ctx {
            usmap: &usmap,
            names: &package.names,
        };
        let mesh = parse_static_mesh(&ctx, bytes, None).map_err(|e| e.to_string())?;
        println!("{full}");
        for (slot, object) in &mesh.materials {
            let pkg = import_package_name(&package, *object);
            println!("  slot {slot} -> {}", pkg.as_deref().unwrap_or("?"));
        }
        material_query = mesh
            .materials
            .first()
            .and_then(|(_, o)| import_package_name(&package, *o))
            .ok_or("mesh has no imported material")?
            .rsplit('/')
            .next()
            .unwrap()
            .to_string();
    }

    // Walk the material-instance parent chain until textures appear.
    let mut seen = 0;
    loop {
        let (c, idx, full) = find_chunk(&containers, &material_query, ".uasset")
            .ok_or_else(|| format!("no material package matching {material_query:?}"))?;
        let data = ue_iostore::read_chunk(c, &c.chunks[idx], None, &oodle_roots)
            .map_err(|e| e.to_string())?;
        let package = Package::parse(&data).map_err(|e| e.to_string())?;
        println!("\n{full}");
        let export = package
            .exports
            .iter()
            .position(|e| {
                matches!(
                    scripts.leaf(e.class),
                    Some("MaterialInstanceConstant" | "Material")
                )
            })
            .ok_or("no material export")?;
        let class = scripts.leaf(package.exports[export].class).unwrap_or("?");
        println!("  class {class}");
        if class == "Material" {
            println!("  (a root material — texture bindings live in its expressions; stopping)");
            return Ok(());
        }
        let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;
        let ctx = Ctx {
            usmap: &usmap,
            names: &package.names,
        };
        let info = parse_material_instance(&ctx, &package, bytes).map_err(|e| e.to_string())?;
        for t in &info.textures {
            println!("  texture {} = {}", t.name, t.package);
        }
        if let Some(base) = base_color(&info.textures) {
            println!("  base colour -> {}", base.package);
            return Ok(());
        }
        match info.parent {
            Some(parent) if seen < 4 => {
                println!("  no base colour here; parent {parent}");
                material_query = parent.rsplit('/').next().unwrap().to_string();
                seen += 1;
            }
            _ => {
                println!("  chain ended without a base colour");
                return Ok(());
            }
        }
    }
}
