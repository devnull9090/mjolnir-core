//! Parse a cooked SkeletalMesh and report bones/sections/buffers.
//!
//!   cargo run --release --example dump_skel -- SK_Warthog_01

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;

fn main() -> Result<(), String> {
    let query = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "SK_Warthog_01".to_string())
        .to_lowercase();

    let usmap_bytes = std::fs::read("../../../defs/ue/Meteorite-2607-CU3.usmap")
        .map_err(|e| e.to_string())?;
    let usmap = ue_asset::Usmap::parse(&usmap_bytes).map_err(|e| e.to_string())?;

    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    if query == "--soak" {
        let mut ok = 0usize;
        let mut nanite_only = 0usize;
        let mut total_tris = 0u64;
        let mut failures: std::collections::BTreeMap<String, (usize, String)> = Default::default();
        let targets: Vec<usize> = (0..catalog.meshes.len())
            .filter(|&i| catalog.meshes[i].skeletal)
            .collect();
        println!("{} skeletal meshes", targets.len());
        for &i in &targets {
            let result = (|| -> Result<usize, String> {
                let data = catalog.read_mesh_uasset(i)?;
                let ubulk = catalog.read_mesh_ubulk(i)?;
                let package = ue_asset::zen::Package::parse(&data).map_err(|e| e.to_string())?;
                let scripts = catalog.script_objects().ok_or("no scripts")?;
                let export = package
                    .exports
                    .iter()
                    .position(|e| scripts.leaf(e.class) == Some("SkeletalMesh"))
                    .ok_or("no SkeletalMesh export")?;
                let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;
                let ctx = ue_asset::unversioned::Ctx {
                    usmap: &usmap,
                    names: &package.names,
                };
                let mesh = ue_asset::mesh::parse_skeletal_mesh(&ctx, bytes, ubulk.as_deref())
                    .map_err(|e| e.to_string())?;
                Ok(mesh
                    .lods
                    .iter()
                    .map(|l| l.indices.len() / 3)
                    .max()
                    .unwrap_or(0))
            })();
            match result {
                Ok(tris) if tris <= 1 => nanite_only += 1,
                Ok(tris) => {
                    ok += 1;
                    total_tris += tris as u64;
                }
                Err(e) => {
                    let key = e.chars().take(60).collect::<String>();
                    let entry = failures.entry(key).or_insert((0, String::new()));
                    entry.0 += 1;
                    if entry.1.is_empty() {
                        entry.1 = catalog.meshes[i].short.clone();
                    }
                }
            }
        }
        println!(
            "ok {ok} ({total_tris} tris) · nanite-only {nanite_only} · failures {}",
            failures.values().map(|(n, _)| n).sum::<usize>()
        );
        let mut rows: Vec<_> = failures.into_iter().collect();
        rows.sort_by_key(|(_, (n, _))| std::cmp::Reverse(*n));
        for (msg, (n, example)) in rows.iter().take(12) {
            println!("  {n:>4} × {msg}\n         e.g. {example}");
        }
        return Ok(());
    }

    let index = catalog
        .meshes
        .iter()
        .position(|m| m.skeletal && m.short.to_lowercase().contains(&query))
        .ok_or("no skeletal mesh matched")?;
    let entry = &catalog.meshes[index];
    println!("mesh: {}", entry.short);

    let data = catalog.read_mesh_uasset(index)?;
    let ubulk = catalog.read_mesh_ubulk(index)?;
    println!(
        "uasset {} bytes, ubulk {}",
        data.len(),
        ubulk.as_ref().map_or("none".into(), |b| format!("{} bytes", b.len()))
    );
    let package = ue_asset::zen::Package::parse(&data).map_err(|e| e.to_string())?;
    let scripts = catalog.script_objects().ok_or("no scripts")?;
    let export = package
        .exports
        .iter()
        .position(|e| scripts.leaf(e.class) == Some("SkeletalMesh"))
        .ok_or("no SkeletalMesh export")?;
    let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;
    let ctx = ue_asset::unversioned::Ctx {
        usmap: &usmap,
        names: &package.names,
    };
    let mesh = ue_asset::mesh::parse_skeletal_mesh(&ctx, bytes, ubulk.as_deref())
        .map_err(|e| e.to_string())?;

    println!("materials:");
    for (slot, object) in &mesh.materials {
        println!(
            "  {slot} -> {}",
            ue_asset::material::import_package_name(&package, *object).unwrap_or_default()
        );
    }
    println!("bones: {}", mesh.bones.len());
    for b in mesh.bones.iter().take(6) {
        println!(
            "  {:<24} parent {:>3}  t ({:+.1} {:+.1} {:+.1})",
            b.name, b.parent, b.translation[0], b.translation[1], b.translation[2]
        );
    }
    for (i, lod) in mesh.lods.iter().enumerate() {
        let verts = lod.positions.len() / 3;
        let tris = lod.indices.len() / 3;
        let mut min = [f32::MAX; 3];
        let mut max = [f32::MIN; 3];
        for p in lod.positions.chunks_exact(3) {
            for a in 0..3 {
                min[a] = min[a].min(p[a]);
                max[a] = max[a].max(p[a]);
            }
        }
        let bad = lod.indices.iter().filter(|&&x| x as usize >= verts.max(1)).count();
        println!(
            "lod {i}: {} sections, {verts} verts, {tris} tris, {} — bounds ({:.0} {:.0} {:.0})..({:.0} {:.0} {:.0}), {bad} bad indices",
            lod.sections.len(),
            if lod.inlined { "inline" } else { "streamed" },
            min[0], min[1], min[2], max[0], max[1], max[2]
        );
    }
    Ok(())
}
