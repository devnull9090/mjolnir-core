//! Parse any cooked package as a `UStaticMesh` and report its shape — including
//! packages the `mjolnir mesh` commands skip, which only enumerate `SM_`/`SK_`
//! names under `/Game`.
//!
//! ```text
//! cargo run -p ue-asset --example mesh_probe -- <paks> <path substring> [--all]
//! ```
//!
//! `--all` reports every match rather than the first, which is how a donor for
//! a geometry rewrite gets chosen: the rewrite needs a mesh with **no Nanite
//! pages**, because the engine renders the Nanite representation when there is
//! one and ignores the classic LOD the rewrite produces.
use ue_asset::unversioned::Ctx;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 2 {
        eprintln!("usage: mesh_probe <paks> <path substring> [--all]");
        std::process::exit(2);
    }
    let all = a.iter().any(|s| s == "--all");
    let (paks, want) = (&a[0], a[1].to_ascii_lowercase());
    let oodle: Vec<std::path::PathBuf> = Vec::new();

    let usmap_bytes = std::fs::read("defs/ue/Meteorite-2607-CU3.usmap").expect("read usmap");
    let usmap = ue_asset::Usmap::parse(&usmap_bytes).expect("parse usmap");

    let containers = ue_iostore::load_all(paks).expect("load containers");
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().unwrap() == "global.utoc")
        .expect("no global.utoc");
    let script_chunk = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .expect("no ScriptObjects");
    let script_bytes = ue_iostore::read_chunk(global, script_chunk, None, &oodle).expect("scripts");
    let scripts = ue_asset::zen::ScriptObjects::parse(&script_bytes).expect("parse scripts");

    let mut hits = 0;
    for c in &containers {
        let mut paths: Vec<(&String, &usize)> = c
            .files
            .iter()
            .filter(|(p, _)| p.ends_with(".uasset") && p.to_ascii_lowercase().contains(&want))
            .collect();
        paths.sort();
        for (path, idx) in paths {
            let chunk = &c.chunks[*idx];
            let Ok(data) = ue_iostore::read_chunk(c, chunk, None, &oodle) else {
                continue;
            };
            let Ok(package) = ue_asset::zen::Package::parse(&data) else {
                continue;
            };
            let Some(export) = package
                .exports
                .iter()
                .position(|e| scripts.leaf(e.class) == Some("StaticMesh"))
            else {
                continue;
            };
            let Ok(bytes) = package.export_data(&data, export) else {
                continue;
            };
            let ctx = Ctx {
                usmap: &usmap,
                names: &package.names,
            };
            // The .ubulk is not needed to see the shape; a streamed LOD simply
            // reports no buffers.
            let bulk_map = ue_asset::mesh::bulk_map_of(&data);
            match ue_asset::mesh::parse_static_mesh_with_bulk_map(&ctx, bytes, None, &bulk_map) {
                Ok(m) => {
                    hits += 1;
                    let nanite = match (&m.nanite_report, &m.nanite_note) {
                        (Some(r), _) => format!("NANITE {} page(s), {} tri", r.pages, r.triangles),
                        (None, Some(n)) => format!("nanite? {n}"),
                        _ => "no nanite".to_string(),
                    };
                    let lods: Vec<String> = m
                        .lods
                        .iter()
                        .map(|l| {
                            format!(
                                "{}v/{}i{}",
                                l.positions.len() / 3,
                                l.indices.len(),
                                if l.inlined { "" } else { " streamed" }
                            )
                        })
                        .collect();
                    println!(
                        "{path}\n  export {export} ({} bytes), {} material(s), {} lod(s) [{}], {nanite}",
                        bytes.len(),
                        m.materials.len(),
                        m.lods.len(),
                        lods.join(", ")
                    );
                    if let Some((lo, hi)) = m.lod_span {
                        println!("  lod array span {lo:#x}..{hi:#x} of {:#x}", bytes.len());
                        let tail = &bytes[hi.min(bytes.len())..];
                        let show = &tail[..tail.len().min(160)];
                        for (i, row) in show.chunks(16).enumerate() {
                            let hex: Vec<String> = row.iter().map(|b| format!("{b:02x}")).collect();
                            println!("  tail +{:04x}: {}", i * 16, hex.join(" "));
                        }
                        // Any double in the tail that reads as a plausible
                        // bound is worth naming: that is where culling comes
                        // from, and a rewrite has to move it.
                        for o in 0..tail.len().saturating_sub(8) {
                            let v = f64::from_le_bytes(tail[o..o + 8].try_into().unwrap());
                            if v.is_finite() && v != 0.0 && v.abs() > 0.01 && v.abs() < 1.0e7 {
                                println!("    double @+{o:#06x} = {v}");
                            }
                        }
                    }
                    if !all {
                        return;
                    }
                }
                Err(e) => println!("{path}\n  parse failed: {e}"),
            }
        }
    }
    if hits == 0 {
        println!("no StaticMesh package matched {want:?}");
    }
}
