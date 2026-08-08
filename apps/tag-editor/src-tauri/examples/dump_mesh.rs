//! Parse a cooked StaticMesh end-to-end and export it as OBJ for eyeballing.
//!
//!   cargo run --release --example dump_mesh -- SM_Elite_Dead_Elbow_L_Default out.obj

use tag_editor_lib::install;
use ue_asset::mesh::parse_static_mesh;
use ue_asset::unversioned::Ctx;
use ue_asset::zen::Package;
use ue_asset::Usmap;

fn main() -> Result<(), String> {
    let query = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "SM_Elite_Dead_Elbow_L_Default".to_string())
        .to_lowercase();
    let obj_out = std::env::args().nth(2);
    let usmap_path = "../../../defs/ue/Meteorite-2607-CU3.usmap";

    let usmap_bytes = std::fs::read(usmap_path).map_err(|e| format!("{usmap_path}: {e}"))?;
    let usmap = Usmap::parse(&usmap_bytes).map_err(|e| e.to_string())?;

    let found = install::detect();
    let paks = found.paks.ok_or("no install")?;
    let oodle_roots: Vec<std::path::PathBuf> = found.oodle.iter().map(Into::into).collect();
    let containers = ue_iostore::load_all(&paks).map_err(|e| e.to_string())?;

    if query == "--soak" {
        return soak(&usmap, &containers, &oodle_roots);
    }

    // The .uasset and its .ubulk sibling.
    let mut uasset = None;
    let mut ubulk = None;
    for c in &containers {
        for (rel, &idx) in &c.files {
            let full = c.full_path(rel);
            let lower = full.to_lowercase();
            if lower.contains(&query) {
                if lower.ends_with(".uasset") {
                    uasset = Some((c, idx, full.clone()));
                } else if lower.ends_with(".ubulk") {
                    ubulk = Some((c, idx));
                }
            }
        }
        if uasset.is_some() {
            break;
        }
    }
    let (container, chunk_index, full) =
        uasset.ok_or_else(|| format!("no package matching {query:?}"))?;
    let data = ue_iostore::read_chunk(container, &container.chunks[chunk_index], None, &oodle_roots)
        .map_err(|e| e.to_string())?;
    let bulk_bytes = match ubulk {
        Some((c, idx)) => Some(
            ue_iostore::read_chunk(c, &c.chunks[idx], None, &oodle_roots)
                .map_err(|e| e.to_string())?,
        ),
        None => None,
    };
    println!(
        "{full}\n  uasset {} bytes, ubulk {}",
        data.len(),
        bulk_bytes.as_ref().map_or("none".into(), |b| format!("{} bytes", b.len()))
    );

    let package = Package::parse(&data).map_err(|e| e.to_string())?;
    let mesh_export = package
        .exports
        .iter()
        .position(|e| e.name.to_lowercase().contains(&query) || package.exports.len() == 1)
        .or_else(|| Some(package.exports.len().saturating_sub(1)))
        .unwrap();
    let bytes = package.export_data(&data, mesh_export).map_err(|e| e.to_string())?;

    if std::env::var_os("UE_ASSET_HEX").is_some() {
        if let Some(b) = &bulk_bytes {
            print!("ubulk head:");
            for (n, x) in b[..b.len().min(96)].iter().enumerate() {
                if n % 16 == 0 {
                    print!("\n  {n:4}:");
                }
                print!(" {x:02x}");
            }
            println!();
        }
        for (n, b) in bytes[150..bytes.len().min(560)].iter().enumerate() {
            if n % 16 == 0 {
                print!("\n  {:4}:", n + 150);
            }
            print!(" {b:02x}");
        }
        println!();
    }

    let ctx = Ctx {
        usmap: &usmap,
        names: &package.names,
    };
    let mesh = parse_static_mesh(&ctx, bytes, bulk_bytes.as_deref()).map_err(|e| e.to_string())?;

    println!("materials:");
    for (slot, object) in &mesh.materials {
        let import = if *object < 0 {
            package
                .imported_package_names
                .get((-object - 1) as usize % package.imported_package_names.len().max(1))
                .cloned()
                .unwrap_or_default()
        } else {
            String::new()
        };
        println!("  {slot} -> {object} {import}");
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
        let bad = lod.indices.iter().filter(|&&x| x as usize >= verts).count();
        println!(
            "lod {i}: {} sections, {verts} verts, {tris} tris, {} — bounds ({:.1} {:.1} {:.1})..({:.1} {:.1} {:.1}), {bad} bad indices",
            lod.sections.len(),
            if lod.inlined { "inline" } else { "streamed" },
            min[0], min[1], min[2], max[0], max[1], max[2]
        );
    }

    if let Some(path) = obj_out {
        let lod = mesh
            .lods
            .iter()
            .find(|l| !l.positions.is_empty())
            .ok_or("no lod with data")?;
        let mut obj = String::new();
        for p in lod.positions.chunks_exact(3) {
            obj.push_str(&format!("v {} {} {}\n", p[0], p[1], p[2]));
        }
        for t in lod.uvs.chunks_exact(2) {
            obj.push_str(&format!("vt {} {}\n", t[0], 1.0 - t[1]));
        }
        for f in lod.indices.chunks_exact(3) {
            obj.push_str(&format!(
                "f {}/{} {}/{} {}/{}\n",
                f[0] + 1, f[0] + 1, f[1] + 1, f[1] + 1, f[2] + 1, f[2] + 1
            ));
        }
        std::fs::write(&path, obj).map_err(|e| e.to_string())?;
        println!("wrote {path}");
    }
    Ok(())
}

/// Parse a sample of every SM_ package and tally the outcomes.
fn soak(
    usmap: &Usmap,
    containers: &[ue_iostore::Container],
    oodle_roots: &[std::path::PathBuf],
) -> Result<(), String> {
    let stride: usize = std::env::args()
        .nth(2)
        .and_then(|s| s.parse().ok())
        .unwrap_or(10);
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
        ue_iostore::read_chunk(global, chunk, None, oodle_roots).map_err(|e| e.to_string())?;
    let scripts = ue_asset::zen::ScriptObjects::parse(&script_bytes).map_err(|e| e.to_string())?;
    let mut targets: Vec<(usize, usize, String)> = Vec::new();
    for (ci, c) in containers.iter().enumerate() {
        for (rel, &idx) in &c.files {
            let lower = rel.to_lowercase();
            if lower.ends_with(".uasset")
                && lower.rsplit('/').next().unwrap_or("").starts_with("sm_")
            {
                targets.push((ci, idx, rel.clone()));
            }
        }
    }
    targets.sort();
    println!("{} SM_ packages, sampling every {stride}th", targets.len());

    let mut ok = 0usize;
    let mut with_geometry = 0usize;
    let mut total_tris = 0u64;
    let mut failures: std::collections::BTreeMap<String, (usize, String)> = Default::default();
    for (ci, idx, rel) in targets.iter().step_by(stride) {
        let c = &containers[*ci];
        let chunk = c.chunks[*idx];
        let Ok(data) = ue_iostore::read_chunk(c, &chunk, None, oodle_roots) else {
            continue;
        };
        let result = (|| -> Result<usize, String> {
            let package = Package::parse(&data).map_err(|e| e.to_string())?;
            let export = package
                .exports
                .iter()
                .position(|e| scripts.leaf(e.class) == Some("StaticMesh"))
                .ok_or("no StaticMesh export")?;
            let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;
            // Only walk actual StaticMesh exports.
            let ctx = Ctx {
                usmap,
                names: &package.names,
            };
            let mesh = parse_static_mesh(&ctx, bytes, None).map_err(|e| e.to_string())?;
            Ok(mesh
                .lods
                .iter()
                .map(|l| l.indices.len() / 3)
                .sum::<usize>())
        })();
        match result {
            Ok(tris) => {
                ok += 1;
                if tris > 0 {
                    with_geometry += 1;
                    total_tris += tris as u64;
                }
            }
            Err(e) => {
                let key = e.chars().take(60).collect::<String>();
                let entry = failures.entry(key).or_insert((0, String::new()));
                entry.0 += 1;
                if entry.1.is_empty() {
                    entry.1 = rel.clone();
                }
            }
        }
    }
    println!(
        "ok {ok} ({} with inline geometry, {} tris total) · failures {}",
        with_geometry,
        total_tris,
        failures.values().map(|(n, _)| n).sum::<usize>()
    );
    let mut rows: Vec<_> = failures.into_iter().collect();
    rows.sort_by_key(|(_, (n, _))| std::cmp::Reverse(*n));
    for (msg, (n, example)) in rows.iter().take(15) {
        println!("  {n:>5} × {msg}\n          e.g. {example}");
    }
    Ok(())
}
