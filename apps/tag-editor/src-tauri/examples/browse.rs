//! Walk the virtual asset filesystem from the command line.
//!
//! Usage:
//!   cargo run --example browse -- ls <dir>
//!   cargo run --example browse -- find <query>

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;

fn main() -> Result<(), String> {
    let mut args = std::env::args().skip(1);
    let verb = args.next().unwrap_or_else(|| "ls".to_string());
    let arg = args.next().unwrap_or_default();

    let found = install::detect();
    let (paks, oodle) = match (found.paks, found.oodle) {
        (Some(p), Some(o)) => (p, o),
        _ => return Err("no installation found".to_string()),
    };
    let catalog = Catalog::open(&paks, &oodle)?;

    let rows = match verb.as_str() {
        "find" => catalog.search_files(&arg, 40),
        _ => catalog.list_dir(&arg),
    };

    println!("{} row(s)", rows.len());
    for r in rows.iter().take(40) {
        match r.kind {
            "dir" => println!("  {:<44} {:>7} items", format!("{}/", r.name), r.children.unwrap_or(0)),
            kind => println!("  {:<44} {:>9} b  {kind}  [{}]", r.name, r.size, r.path),
        }
    }
    Ok(())
}
