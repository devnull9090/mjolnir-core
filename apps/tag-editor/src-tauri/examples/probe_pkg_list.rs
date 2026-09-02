//! List cooked package names matching a substring.
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;
fn main() -> Result<(), String> {
    let q = std::env::args().nth(1).unwrap_or_else(|| "warthog".into());
    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    for p in catalog.packages_matching(&q) {
        println!("{p}");
    }
    Ok(())
}
