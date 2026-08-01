//! Print the resolved import links of one tag, to verify against the game.
//!
//! Usage: cargo run --example tag_links -- <group> <path-substring>

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{install, zen};

fn main() -> Result<(), String> {
    let mut args = std::env::args().skip(1);
    let group = args.next().unwrap_or_else(|| "biped".to_string());
    let query = args.next().unwrap_or_else(|| "elite/elite".to_string());

    let found = install::detect();
    let (paks, oodle) = match (found.paks, found.oodle) {
        (Some(p), Some(o)) => (p, o),
        _ => return Err("no installation found".to_string()),
    };
    let catalog = Catalog::open(&paks, &oodle)?;

    let index = catalog
        .tags
        .iter()
        .position(|t| t.group == group && t.short.contains(&query))
        .ok_or("no tag matched")?;
    eprintln!("tag: {} ({})", catalog.tags[index].short, group);

    let uasset = catalog.read_tag_uasset(index)?;
    for package in zen::imported_package_names(&uasset) {
        let resolved = if let Some(i) = catalog.tag_by_package(&package) {
            format!("tag #{i} {}", catalog.tags[i].short)
        } else if let Some(i) = catalog.texture_by_package(&package) {
            format!("texture #{i} {}", catalog.textures[i].short)
        } else {
            "asset (not openable)".to_string()
        };
        println!("{package}\n    -> {resolved}");
    }
    Ok(())
}
