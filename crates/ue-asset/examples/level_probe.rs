//! Probe the cooked level packages: list what matches a substring, or dump
//! one package's exports with the component properties a level exporter
//! cares about and the native bytes that trail them.
//!
//!   cargo run -p ue-asset --example level_probe -- list <paks> <substring> [limit]
//!   cargo run -p ue-asset --example level_probe -- exports <paks> <substring> [export-limit]

use std::collections::HashMap;

use ue_asset::unversioned::{Ctx, Keep, Value, Walker};

static USMAP: &[u8] = include_bytes!("../../../defs/ue/Meteorite-2607-CU3.usmap");

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let mode = args.next().unwrap_or_default();
    let paks = args.next().expect("usage: level_probe <list|exports> <paks> <substring> [limit]");
    let want = args.next().expect("usage: level_probe <list|exports> <paks> <substring> [limit]");
    let limit: usize = args.next().and_then(|v| v.parse().ok()).unwrap_or(40);

    let containers = ue_iostore::load_all(&paks)?;
    match mode.as_str() {
        "list" => {
            let mut shown = 0;
            let mut by_folder: HashMap<String, usize> = HashMap::new();
            for c in &containers {
                let utoc = c.utoc_path.file_name().unwrap().to_string_lossy().to_string();
                let mut names: Vec<&String> = c.files.keys().collect();
                names.sort();
                for rel in names {
                    let full = c.full_path(rel);
                    if !full.to_ascii_lowercase().contains(&want.to_ascii_lowercase()) {
                        continue;
                    }
                    let folder = full.rsplit_once('/').map(|(f, _)| f.to_string()).unwrap_or_default();
                    *by_folder.entry(format!("{utoc} {folder}")).or_default() += 1;
                    if shown < limit {
                        let chunk = c.chunks[c.files[rel]];
                        println!("{utoc}  {full}  ({} bytes)", chunk.length);
                        shown += 1;
                    }
                }
            }
            let mut folders: Vec<(String, usize)> = by_folder.into_iter().collect();
            folders.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
            println!("--- files per folder");
            for (f, n) in folders.iter().take(60) {
                println!("{n:6}  {f}");
            }
        }
        "exports" => {
            let global = containers
                .iter()
                .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
                .unwrap();
            let script_chunk = global.chunks.iter().find(|c| c.type_name() == "ScriptObjects").unwrap();
            let scripts = ue_asset::zen::ScriptObjects::parse(&ue_iostore::read_chunk(global, script_chunk, None, &[])?)?;
            let usmap = ue_asset::Usmap::parse(USMAP)?;
            for c in &containers {
                let mut names: Vec<&String> = c.files.keys().collect();
                names.sort();
                for rel in names {
                    let full = c.full_path(rel);
                    if !full.to_ascii_lowercase().contains(&want.to_ascii_lowercase()) || !(full.ends_with(".uasset") || full.ends_with(".umap")) {
                        continue;
                    }
                    println!("== {full}");
                    let data = ue_iostore::read_chunk(c, &c.chunks[c.files[rel]], None, &[])?;
                    let pkg = ue_asset::zen::Package::parse(&data)?;
                    println!("   {} names, {} imports, {} exports, {} imported packages", pkg.names.len(), pkg.imports.len(), pkg.exports.len(), pkg.imported_package_names.len());
                    for (i, p) in pkg.imported_package_names.iter().enumerate().take(30) {
                        println!("   imported package {i}: {p}");
                    }
                    let ctx = Ctx { usmap: &usmap, names: &pkg.names };
                    let mut class_hist: HashMap<String, usize> = HashMap::new();
                    for (ei, e) in pkg.exports.iter().enumerate() {
                        let class = match e.class.classify() {
                            ue_asset::zen::ObjectRef::Script(_) => scripts.leaf(e.class).unwrap_or("?").to_string(),
                            ue_asset::zen::ObjectRef::Export(x) => format!("export:{}", pkg.exports[x].name),
                            ue_asset::zen::ObjectRef::PackageImport(v) => {
                                let index = ((v >> 32) & 0x3FFF_FFFF) as usize;
                                format!("import:{}", pkg.imported_package_names.get(index).map(|s| s.rsplit('/').next().unwrap_or(s)).unwrap_or("?"))
                            }
                            ue_asset::zen::ObjectRef::Null => "null".into(),
                        };
                        *class_hist.entry(class.clone()).or_default() += 1;
                        if ei >= limit {
                            continue;
                        }
                        let outer = match e.outer.classify() {
                            ue_asset::zen::ObjectRef::Export(x) => format!("{x}:{}", pkg.exports[x].name),
                            _ => "-".into(),
                        };
                        println!("   [{ei}] {} : {class}  outer {outer}  {} bytes", e.name, e.serial_size);
                        let leaf = class.rsplit(':').next().unwrap_or(&class).to_string();
                        if !matches!(leaf.as_str(), "Level" | "World" | "Model" | "BlamWorldSettings" | "NavigationSystemModuleConfig") {
                            let Ok(bytes) = pkg.export_data(&data, ei) else { continue };
                            if std::env::var_os("LEVEL_PROBE_HEX").is_some() {
                                let hex: Vec<String> = bytes.iter().take(176).map(|b| format!("{b:02x}")).collect();
                                println!("       bytes: {}", hex.join(" "));
                            }
                            let mut w = Walker::new(&ctx, bytes);
                            let props = match w.read_object(&leaf, Keep::All) {
                                Ok(p) => p,
                                Err(err) => {
                                    println!("       props: {err}");
                                    continue;
                                }
                            };
                            let mut keys: Vec<&String> = props.keys().collect();
                            keys.sort();
                            for k in keys {
                                let v = &props[k];
                                let shown = match v {
                                    Value::Array(a) => format!("Array[{}]", a.len()),
                                    Value::Struct(s) => {
                                        let mut ks: Vec<String> = s.iter().map(|(k, v)| format!("{k}={v:?}")).collect();
                                        ks.sort();
                                        format!("{{{}}}", ks.join(", "))
                                    }
                                    other => format!("{other:?}"),
                                };
                                let shown = if shown.len() > 160 { format!("{}…", &shown[..160]) } else { shown };
                                println!("       {k} = {shown}");
                            }
                            let rest = &bytes[w.pos.min(bytes.len())..];
                            let hex: Vec<String> = rest.iter().take(96).map(|b| format!("{b:02x}")).collect();
                            println!("       native tail {} bytes at {:#x}: {}", rest.len(), w.pos, hex.join(" "));
                        }
                    }
                    let mut hist: Vec<(String, usize)> = class_hist.into_iter().collect();
                    hist.sort_by(|a, b| b.1.cmp(&a.1));
                    println!("   --- export classes");
                    for (k, n) in hist.iter().take(40) {
                        println!("   {n:6}  {k}");
                    }
                    return Ok(());
                }
            }
        }
        "classes" => {
            let global = containers
                .iter()
                .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
                .unwrap();
            let script_chunk = global.chunks.iter().find(|c| c.type_name() == "ScriptObjects").unwrap();
            let scripts = ue_asset::zen::ScriptObjects::parse(&ue_iostore::read_chunk(global, script_chunk, None, &[])?)?;
            let mut hist: HashMap<String, (usize, usize, String)> = HashMap::new();
            let mut packages = 0usize;
            for c in &containers {
                let mut names: Vec<&String> = c.files.keys().collect();
                names.sort();
                for rel in names {
                    let full = c.full_path(rel);
                    if !full.to_ascii_lowercase().contains(&want.to_ascii_lowercase()) || !(full.ends_with(".uasset") || full.ends_with(".umap")) {
                        continue;
                    }
                    if packages >= limit {
                        break;
                    }
                    packages += 1;
                    let data = ue_iostore::read_chunk(c, &c.chunks[c.files[rel]], None, &[])?;
                    let Ok(pkg) = ue_asset::zen::Package::parse(&data) else { continue };
                    let mut seen: std::collections::HashSet<String> = Default::default();
                    for e in &pkg.exports {
                        let class = match e.class.classify() {
                            ue_asset::zen::ObjectRef::Script(_) => scripts.leaf(e.class).unwrap_or("?").to_string(),
                            ue_asset::zen::ObjectRef::Export(x) => format!("export:{}", pkg.exports[x].name),
                            ue_asset::zen::ObjectRef::PackageImport(v) => {
                                let index = ((v >> 32) & 0x3FFF_FFFF) as usize;
                                format!("import:{}", pkg.imported_package_names.get(index).map(|s| s.rsplit('/').next().unwrap_or(s)).unwrap_or("?"))
                            }
                            ue_asset::zen::ObjectRef::Null => "null".into(),
                        };
                        let entry = hist.entry(class.clone()).or_insert((0, 0, full.rsplit('/').next().unwrap_or("").to_string()));
                        entry.0 += 1;
                        if seen.insert(class) {
                            entry.1 += 1;
                        }
                    }
                }
            }
            let mut rows: Vec<(String, (usize, usize, String))> = hist.into_iter().collect();
            rows.sort_by(|a, b| b.1 .0.cmp(&a.1 .0));
            println!("{packages} packages");
            println!("{:>8} {:>6}  class  (example package)", "exports", "pkgs");
            for (k, (n, p, ex)) in rows.iter().take(80) {
                println!("{n:8} {p:6}  {k}  ({ex})");
            }
        }
        _ => eprintln!("usage: level_probe <list|exports|classes> <paks> <substring> [limit]"),
    }
    Ok(())
}
