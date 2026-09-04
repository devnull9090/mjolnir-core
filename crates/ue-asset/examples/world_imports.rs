//! List a cooked package's imported packages and names, found by directory-index path.
//!
//!   cargo run -p ue-asset --example world_imports -- <paks> <path substring> [grep]
use ue_asset::zen::Package;

fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args.next().expect("usage: world_imports <paks> <substring> [grep]");
    let want = args.next().expect("usage: world_imports <paks> <substring> [grep]");
    let grep = args.next();
    let containers = ue_iostore::load_all(&paks).expect("load containers");
    for c in &containers {
        let mut hits: Vec<(&String, usize)> = c
            .files
            .iter()
            .filter(|(p, _)| p.contains(&want) && p.ends_with(".uasset") || p.contains(&want) && p.ends_with(".umap"))
            .map(|(p, i)| (p, *i))
            .collect();
        hits.sort();
        for (path, idx) in hits {
            let chunk = &c.chunks[idx];
            println!("{} ({} bytes, {})", path, chunk.length, c.utoc_path.file_name().unwrap().to_string_lossy());
            let data = ue_iostore::read_chunk(c, chunk, None, &[]).expect("read chunk");
            match Package::parse(&data) {
                Ok(pkg) => {
                    println!("  name {}  header {}  names {}  imports {}  exports {}  imported packages {}",
                        pkg.name, pkg.header_size, pkg.names.len(), pkg.imports.len(), pkg.exports.len(), pkg.imported_package_names.len());
                    for n in &pkg.imported_package_names {
                        if grep.as_deref().map_or(true, |g| n.to_lowercase().contains(&g.to_lowercase())) {
                            println!("    import pkg: {n}");
                        }
                    }
                    for e in &pkg.exports {
                        if grep.as_deref().map_or(false, |g| e.name.to_lowercase().contains(&g.to_lowercase())) {
                            println!("    export: {} class {:?}", e.name, e.class);
                        }
                    }
                    for n in &pkg.names {
                        if grep.as_deref().map_or(false, |g| n.to_lowercase().contains(&g.to_lowercase())) {
                            println!("    name: {n}");
                        }
                    }
                }
                Err(e) => println!("  parse failed: {e}"),
            }
        }
    }
}
