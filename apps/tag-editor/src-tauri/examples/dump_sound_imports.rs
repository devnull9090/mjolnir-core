//! What do sound tags import? Scratch probe for the peek chase.
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{install, zen};

fn main() {
    let found = install::detect();
    let c = Catalog::open(&found.paks.unwrap(), &found.oodle.unwrap_or_default()).unwrap();
    let sounds: Vec<usize> = c
        .tags
        .iter()
        .enumerate()
        .filter(|(_, t)| t.group.starts_with("sound"))
        .map(|(i, _)| i)
        .take(6)
        .collect();
    for i in sounds {
        let t = &c.tags[i];
        println!("== {} ({})", t.short, t.group);
        match c.read_tag_uasset(i) {
            Ok(uasset) => {
                for p in zen::imported_package_names(&uasset) {
                    println!("   {p}");
                    if let Some(buf) = c.read_package(&p) {
                        for p2 in zen::imported_package_names(&buf) {
                            println!("      import: {p2}");
                            if let Some(buf2) = c.read_package(&p2) {
                                if let Some(names) = zen::load_name_batch(&buf2, 52) {
                                    for n in names.iter().take(10) {
                                        println!("         name: {n}");
                                    }
                                }
                            }
                        }
                    } else {
                        println!("      (package unreadable)");
                    }
                }
            }
            Err(e) => println!("   uasset: {e}"),
        }
    }
}
