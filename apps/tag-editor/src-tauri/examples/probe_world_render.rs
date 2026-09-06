//! The World view's render-model path for one scenario, end to end: every
//! palette entry chased to meshes, every mesh through the read path, so the
//! fallback split (render vs collision proxy) is known before the GUI runs.
//!   cargo run --release --example probe_world_render -- a30
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{geometry, install};
use ue_asset::unversioned::Ctx;

fn main() -> Result<(), String> {
    let q = std::env::args().nth(1).unwrap_or_else(|| "a30".into()).to_lowercase();
    let usmap_bytes = std::fs::read("../../../defs/ue/Meteorite-2607-CU3.usmap").map_err(|e| e.to_string())?;
    let usmap = ue_asset::Usmap::parse(&usmap_bytes).map_err(|e| e.to_string())?;
    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    let scripts = catalog.script_objects().ok_or("no scripts")?;
    let si = catalog
        .tags
        .iter()
        .position(|t| t.group == "scenario" && t.short.to_lowercase().contains(&q))
        .ok_or("no scenario matched")?;
    let file = catalog.read_tag(si)?;
    let layout = geometry::scenario_layout(&file)?;
    let normalize = |p: &str| {
        p.replace('\\', "/").to_ascii_lowercase().replace("/_generated_/", "/")
    };
    let mut drawn = 0;
    let mut fell_back = 0;
    for cat in &layout.categories {
        for path in &cat.palette {
            let want = normalize(path);
            let Some(oi) = catalog
                .tags
                .iter()
                .position(|t| t.group == cat.group && normalize(&t.short) == want)
            else {
                println!("  {} {}: TAG NOT FOUND", cat.group, path);
                continue;
            };
            let refs = tag_editor_lib::render_mesh_refs(&catalog, oi);
            if refs.is_empty() {
                println!("  {} {}: no render refs -> collision proxy", cat.group, path);
                fell_back += 1;
                continue;
            }
            let mut readable = 0;
            for r in &refs {
                let entry = &catalog.meshes[r.mesh];
                let ok = (|| -> Option<usize> {
                    let data = catalog.read_mesh_uasset(r.mesh).ok()?;
                    let ubulk = catalog.read_mesh_ubulk(r.mesh).ok()?;
                    let package = ue_asset::zen::Package::parse(&data).ok()?;
                    let wanted = if entry.skeletal { "SkeletalMesh" } else { "StaticMesh" };
                    let export = package
                        .exports
                        .iter()
                        .position(|e| scripts.leaf(e.class) == Some(wanted))?;
                    let bytes = package.export_data(&data, export).ok()?;
                    let ctx = Ctx { usmap: &usmap, names: &package.names };
                    let mesh = if entry.skeletal {
                        ue_asset::mesh::parse_skeletal_mesh(&ctx, bytes, ubulk.as_deref())
                            .map(|sk| ue_asset::mesh::StaticMeshData {
                                materials: sk.materials,
                                lods: sk.lods,
                                ..Default::default()
                            })
                            .ok()?
                    } else {
                        ue_asset::mesh::parse_static_mesh(&ctx, bytes, ubulk.as_deref()).ok()?
                    };
                    let lod = mesh.lods.iter().find(|l| !l.indices.is_empty())?;
                    (lod.indices.len() > 3).then(|| lod.indices.len() / 3)
                })();
                match ok {
                    Some(tris) => {
                        readable += 1;
                        println!("  {} {}: {} -> {} tris", cat.group, path, r.label, tris);
                    }
                    None => println!("  {} {}: {} -> UNREADABLE (placeholder?)", cat.group, path, r.label),
                }
            }
            if readable > 0 { drawn += 1 } else { fell_back += 1 }
        }
    }
    println!("\npalette entries drawing render meshes: {drawn}, falling back: {fell_back}");
    Ok(())
}
