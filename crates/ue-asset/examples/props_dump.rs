//! Print a zen package file's export properties, decoded with a usmap.
//!
//!   cargo run -p ue-asset --example props_dump -- <global.utoc dir> <usmap> <package file> [export]
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let containers = ue_iostore::load_all(&a[0]).expect("containers");
    let global = containers
        .iter()
        .find(|c| {
            c.utoc_path
                .file_name()
                .map(|n| n == "global.utoc")
                .unwrap_or(false)
        })
        .expect("no global.utoc");
    let chunk = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .expect("no ScriptObjects chunk");
    let data = ue_iostore::read_chunk(global, chunk, None, &[]).expect("read ScriptObjects");
    let scripts = ue_asset::zen::ScriptObjects::parse(&data).expect("ScriptObjects");
    let usmap = ue_asset::Usmap::parse(&std::fs::read(&a[1]).expect("usmap")).expect("usmap");
    let pkg = ue_asset::package::ZenPackage::parse(&std::fs::read(&a[2]).expect("package"))
        .expect("package");
    let only: Option<usize> = a.get(3).map(|s| s.parse().expect("export index"));
    for i in 0..pkg.export_map.len() {
        if only.is_some_and(|o| o != i) {
            continue;
        }
        match ue_asset::edit::open_export(&pkg, &usmap, &scripts, i) {
            Ok(e) => {
                println!(
                    "export {i} {} (native tail {} bytes)",
                    e.class,
                    e.tail.len()
                );
                for r in ue_asset::edit::describe(&usmap, &e.class, &pkg.names.names, &e.block) {
                    println!("  {} = {}", r.path, r.value);
                }
            }
            Err(e) => println!("export {i}: {e}"),
        }
    }
}
