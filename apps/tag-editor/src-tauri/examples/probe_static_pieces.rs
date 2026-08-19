//! Static rig pieces near a skeletal mesh: names, and bounds of a few, to
//! test whether their vertices are bone-local or component-space.
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;
use ue_asset::unversioned::Ctx;
fn main() -> Result<(), String> {
    let q = std::env::args().nth(1).unwrap_or_else(|| "vehicles/human/warthog/static".into()).to_lowercase();
    let usmap_bytes = std::fs::read("../../../defs/ue/Meteorite-2607-CU3.usmap").map_err(|e| e.to_string())?;
    let usmap = ue_asset::Usmap::parse(&usmap_bytes).map_err(|e| e.to_string())?;
    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    let scripts = catalog.script_objects().ok_or("no scripts")?;
    let mut shown = 0;
    for mi in 0..catalog.meshes.len() {
        let m = &catalog.meshes[mi];
        if m.skeletal || !m.short.to_lowercase().contains(&q) { continue; }
        print!("{}", m.short);
        if shown < 8 {
            let ok = (|| -> Option<([f32;3],[f32;3],usize)> {
                let data = catalog.read_mesh_uasset(mi).ok()?;
                let ubulk = catalog.read_mesh_ubulk(mi).ok()?;
                let package = ue_asset::zen::Package::parse(&data).ok()?;
                let export = package.exports.iter().position(|e| scripts.leaf(e.class) == Some("StaticMesh"))?;
                let bytes = package.export_data(&data, export).ok()?;
                let ctx = Ctx { usmap: &usmap, names: &package.names };
                let mesh = ue_asset::mesh::parse_static_mesh(&ctx, bytes, ubulk.as_deref()).ok()?;
                let lod = mesh.lods.iter().find(|l| !l.indices.is_empty())?;
                let mut lo = [f32::MAX;3]; let mut hi = [f32::MIN;3];
                for v in lod.positions.chunks(3) { for a in 0..3 { lo[a]=lo[a].min(v[a]); hi[a]=hi[a].max(v[a]); } }
                Some((lo, hi, lod.indices.len()/3))
            })();
            match ok {
                Some((lo, hi, tris)) => print!("  [{} tris, bounds ({:.0} {:.0} {:.0})..({:.0} {:.0} {:.0})]", tris, lo[0],lo[1],lo[2],hi[0],hi[1],hi[2]),
                None => print!("  [unreadable]"),
            }
        }
        println!();
        shown += 1;
    }
    println!("total: {shown}");
    Ok(())
}
