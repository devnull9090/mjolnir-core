//! The render_mesh_refs chase for one tag, printed.
//!   cargo run --release --example probe_render_refs -- warthog vehicle
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;
fn main() -> Result<(), String> {
    let q = std::env::args().nth(1).unwrap_or_else(|| "warthog".into()).to_lowercase();
    let group = std::env::args().nth(2).unwrap_or_else(|| "vehicle".into());
    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    let ti = catalog
        .tags
        .iter()
        .position(|t| t.group == group && t.short.to_lowercase().contains(&q))
        .ok_or("no tag matched")?;
    println!("tag: {}", catalog.tags[ti].short);
    for r in tag_editor_lib::render_mesh_refs(&catalog, ti) {
        println!(
            "  mesh {} ({}) skeletal {} loc {:?} rot {:?} scale {:?}",
            r.mesh, r.label, r.skeletal, r.location, r.rotation, r.scale
        );
    }
    Ok(())
}
