//! Every placement of a mission's World Partition cells whose mesh path
//! contains one of the filters, as CSV: mesh, x, y, z (cm), yaw (degrees),
//! uniform scale, kind, cell, and the full 3 x 3 (rotation and scale, row
//! vectors: m00..m22) for parts that tilt (a tree's branches).
//!
//!   cargo run -p ue-asset --example placements_csv -- <paks> <usmap> <mission> <out.csv> [filter...]
//!
//! What B30's beach is built from (rocks, plants, their spacing and heights)
//! for tools/level/scatter_grass.py's rules.
use std::collections::HashMap;
use std::io::Write;

use ue_asset::level::{mission_cells, translation, CellReader, Kind, MeshRef};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let (paks, usmap_path, mission, out) = (&args[0], &args[1], &args[2], &args[3]);
    let filters: Vec<String> = args[4..].iter().map(|f| f.to_ascii_lowercase()).collect();
    let containers = ue_iostore::load_all(paks).expect("load containers");
    let oodle: Vec<std::path::PathBuf> = Vec::new();
    let mut index: HashMap<String, (usize, usize)> = HashMap::new();
    for (ci, c) in containers.iter().enumerate() {
        for (rel, chunk) in &c.files {
            let full = c.full_path(rel);
            if full.ends_with(".uptnl") || full.ends_with(".ubulk") {
                continue;
            }
            if let Some(name) = ue_asset::level::package_name_of(&full) {
                index.insert(name.to_ascii_lowercase(), (ci, *chunk));
            }
        }
    }
    let usmap = ue_asset::Usmap::parse(&std::fs::read(usmap_path).expect("usmap")).expect("parse usmap");
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .expect("global.utoc");
    let script_chunk = global.chunks.iter().find(|c| c.type_name() == "ScriptObjects").expect("ScriptObjects");
    let scripts = ue_asset::zen::ScriptObjects::parse(
        &ue_iostore::read_chunk(global, script_chunk, None, &oodle).expect("read scripts"),
    )
    .expect("parse scripts");
    let load = |name: &str| -> Option<Vec<u8>> {
        let (ci, chunk) = index.get(&name.to_ascii_lowercase())?;
        ue_iostore::read_chunk(&containers[*ci], &containers[*ci].chunks[*chunk], None, &oodle).ok()
    };
    let reader = CellReader::new(&usmap, &scripts, &load);
    let cells = mission_cells(index.keys().map(|k| k.as_str()), mission);
    let mut f = std::fs::File::create(out).expect("create csv");
    writeln!(f, "mesh,x,y,z,yaw,scale,kind,cell,m00,m01,m02,m10,m11,m12,m20,m21,m22").unwrap();
    let mut rows = 0usize;
    for key in &cells {
        let Some(data) = load(key) else { continue };
        let Ok(cell) = reader.read(&data) else { continue };
        for p in &cell.placements {
            let MeshRef::Package(mesh) = &p.mesh else { continue };
            let lower = mesh.to_ascii_lowercase();
            if !filters.is_empty() && !filters.iter().any(|w| lower.contains(w)) {
                continue;
            }
            let m = &p.world;
            let t = translation(m);
            // Row-vector matrices: the first row is the local x axis.
            let sx = (m[0][0] * m[0][0] + m[0][1] * m[0][1] + m[0][2] * m[0][2]).sqrt();
            let yaw = m[0][1].atan2(m[0][0]).to_degrees();
            let kind = match p.kind {
                Kind::Static => "static",
                Kind::Instanced => "instanced",
                Kind::Hlod => "hlod",
            };
            writeln!(f, "{mesh},{:.1},{:.1},{:.1},{:.1},{:.3},{kind},{},{:.5},{:.5},{:.5},{:.5},{:.5},{:.5},{:.5},{:.5},{:.5}",
                t[0], t[1], t[2], yaw, sx, key.rsplit('/').next().unwrap_or(key),
                m[0][0], m[0][1], m[0][2], m[1][0], m[1][1], m[1][2], m[2][0], m[2][1], m[2][2])
            .unwrap();
            rows += 1;
        }
    }
    eprintln!("{rows} placement(s) from {} cell(s) -> {out}", cells.len());
}
