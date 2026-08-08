//! Sanity-check the scenario-viewer extraction: the packed sbsp world and the
//! scenario layout, against real tags.
//!
//!   cargo run --release --example dump_world -- a30

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::geometry;
use tag_editor_lib::install;

fn main() -> Result<(), String> {
    let query = std::env::args().nth(1).unwrap_or_else(|| "a30".to_string());

    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;

    let index = catalog
        .tags
        .iter()
        .position(|t| t.group == "scenario" && t.short.to_lowercase().contains(&query.to_lowercase()))
        .ok_or_else(|| format!("no scenario matching {query:?}"))?;
    println!("scenario: {}", catalog.tags[index].short);

    let file = catalog.read_tag(index)?;
    let started = std::time::Instant::now();
    let layout = geometry::scenario_layout(&file)?;
    println!("scenario_layout in {:?}", started.elapsed());

    let normalize =
        |p: &str| p.replace('\\', "/").to_ascii_lowercase().replace("/_generated_/", "/");
    let find_bsp = |p: &str| {
        let want = normalize(p);
        catalog
            .tags
            .iter()
            .position(|t| t.group == "scenario_structure_bsp" && normalize(&t.short) == want)
    };
    println!("\nbsps ({}):", layout.bsps.len());
    for p in &layout.bsps {
        println!("  {} {}", if find_bsp(p).is_some() { "ok " } else { "MISSING" }, p);
    }
    println!("object names: {}", layout.object_names.len());
    for c in &layout.categories {
        println!(
            "  {:<16} palette {:>3}  placements {:>4}",
            c.block,
            c.palette.len(),
            c.placements.len()
        );
        for p in c.placements.iter().take(2) {
            println!(
                "    [{}] palette {} pos ({:+.2} {:+.2} {:+.2}) rot ({:+.2} {:+.2} {:+.2}) scale {:.2}",
                p.element, p.palette, p.position[0], p.position[1], p.position[2],
                p.rotation[0], p.rotation[1], p.rotation[2], p.scale
            );
        }
    }
    println!("trigger volumes: {}", layout.trigger_volumes.len());
    println!(
        "squads: {} ({} spawn points)",
        layout.squads.len(),
        layout.squads.iter().map(|s| s.spawn_points.len()).sum::<usize>()
    );
    println!("player starts: {}", layout.player_starts.len());

    // The exact paths the World view writes must resolve through the patch
    // pipeline. Prove it on the first placement of each populated category.
    {
        let tag = blam_tag::TagFile::parse(&file, None).map_err(|e| e.to_string())?;
        let tag_layout = tag.layout().map_err(|e| e.to_string())?;
        let block = tag.read_data(&tag_layout).map_err(|e| e.to_string())?;
        for c in &layout.categories {
            let Some(p) = c.placements.first() else {
                continue;
            };
            for field in ["position", "rotation"] {
                let path = format!("{}[{}].object data.{}", c.block, p.element, field);
                match blam_tag::patch::resolve(&tag_layout, &file, &block, &path) {
                    Ok(t) => println!("  patch ok  {path} -> {:?} @ {}", t.current, t.file_offset),
                    Err(e) => println!("  patch ERR {path}: {e}"),
                }
            }
        }
    }

    // The first BSP's packed world.
    let Some(bsp_path) = layout.bsps.first() else {
        return Ok(());
    };
    let bsp_index = find_bsp(bsp_path).ok_or("first bsp not in catalog")?;
    let bsp_file = catalog.read_tag(bsp_index)?;
    let started = std::time::Instant::now();
    let packed = geometry::sbsp_world(&bsp_file)?;
    println!(
        "\nsbsp_world({}) -> {:.1} MiB in {:?}",
        catalog.tags[bsp_index].short,
        packed.len() as f64 / (1 << 20) as f64,
        started.elapsed()
    );

    // Parse the header back out and spot-check the framing.
    if &packed[..4] != b"SBSP" {
        return Err("bad magic".into());
    }
    let json_len = u32::from_le_bytes(packed[4..8].try_into().unwrap()) as usize;
    let header: serde_json::Value =
        serde_json::from_slice(&packed[8..8 + json_len]).map_err(|e| e.to_string())?;
    let defs = header["defs"].as_array().unwrap();
    let total_tris: u64 = defs.iter().map(|d| d["tris"].as_u64().unwrap()).sum();
    let total_verts: u64 = defs.iter().map(|d| d["verts"].as_u64().unwrap()).sum();
    println!(
        "defs {} ({} verts, {} tris) · world {} · instances {}",
        defs.len(),
        total_verts,
        total_tris,
        header["world"],
        header["instances"]
    );
    let mut payload = 8 + json_len;
    payload += (4 - payload % 4) % 4;
    let expected: u64 = defs
        .iter()
        .map(|d| d["verts"].as_u64().unwrap() * 12 + d["tris"].as_u64().unwrap() * 16)
        .sum::<u64>()
        + header["world"]
            .as_object()
            .map(|w| w["verts"].as_u64().unwrap() * 12 + w["tris"].as_u64().unwrap() * 16)
            .unwrap_or(0)
        + header["instances"].as_u64().unwrap() * 56;
    let actual = (packed.len() - payload) as u64;
    println!(
        "payload {} bytes, expected {} — {}",
        actual,
        expected,
        if actual == expected { "exact" } else { "MISMATCH" }
    );
    Ok(())
}
