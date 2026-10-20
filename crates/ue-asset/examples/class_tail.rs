//! Find exports of one class in the packages matching a path substring and
//! print the native bytes after their properties (decoded with a usmap), to
//! compare a class's native serialization between builds.
//!
//!   cargo run -p ue-asset --example class_tail -- <paks> <usmap> <path substring> <class> [limit] [bytes]
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let (paks, usmap, want, class) = (&a[0], &a[1], a[2].to_lowercase(), &a[3]);
    let limit: usize = a.get(4).map(|s| s.parse().expect("limit")).unwrap_or(3);
    let show: usize = a.get(5).map(|s| s.parse().expect("bytes")).unwrap_or(96);
    let containers = ue_iostore::load_all(paks).expect("containers");
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
    let scripts = ue_asset::zen::ScriptObjects::parse(
        &ue_iostore::read_chunk(global, chunk, None, &[]).expect("read"),
    )
    .expect("ScriptObjects");
    let usmap = ue_asset::Usmap::parse(&std::fs::read(usmap).expect("usmap")).expect("usmap");
    let mut found = 0;
    for c in &containers {
        for (path, idx) in &c.files {
            if found >= limit {
                return;
            }
            let lower = path.to_lowercase();
            if !lower.contains(&want) || !(lower.ends_with(".umap") || lower.ends_with(".uasset")) {
                continue;
            }
            let Ok(data) = ue_iostore::read_chunk(c, &c.chunks[*idx], None, &[]) else {
                continue;
            };
            let Ok(pkg) = ue_asset::package::ZenPackage::parse(&data) else {
                continue;
            };
            for i in 0..pkg.export_map.len() {
                if ue_asset::edit::export_class(&pkg, &scripts, i).as_deref()
                    != Some(class.as_str())
                {
                    continue;
                }
                let bytes = pkg.export_bytes(i).unwrap_or(&[]);
                match ue_asset::props::decode_prefix(&usmap, class, bytes) {
                    Ok((_, used)) => {
                        let tail = &bytes[used..];
                        println!(
                            "{path} export {i}: {} bytes, properties {used}, native tail {}",
                            bytes.len(),
                            tail.len()
                        );
                        for row in tail[..tail.len().min(show)].chunks(16) {
                            println!(
                                "    {}",
                                row.iter()
                                    .map(|b| format!("{b:02x}"))
                                    .collect::<Vec<_>>()
                                    .join(" ")
                            );
                        }
                    }
                    Err(e) => println!("{path} export {i}: {e}"),
                }
                found += 1;
                if found >= limit {
                    return;
                }
            }
        }
    }
}
