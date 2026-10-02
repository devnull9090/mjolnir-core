//! Survey material instances: for each parent material, how many instances
//! the game ships and which texture/scalar/vector parameters they set. Used to
//! find a shipped master material that can carry a classic shader's layers
//! (base map, detail maps with their own tiling, a blend mask) as runtime
//! instances.
//!
//!   cargo run --release -p ue-asset --example material_survey -- <paks> [path substring]
//!
//! Prints one block per parent, most-instanced first: every parameter any of
//! its instances sets, with how many do, and a few example instances.
use std::collections::{BTreeMap, BTreeSet};

static USMAP: &[u8] = include_bytes!("../../../defs/ue/Meteorite-2607-CU3.usmap");

#[derive(Default)]
struct Parent {
    instances: usize,
    params: BTreeMap<String, usize>,
    examples: BTreeSet<String>,
}

fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args
        .next()
        .expect("usage: material_survey <paks> [substring]");
    let want = args.next().map(|s| s.to_lowercase());
    let usmap = ue_asset::Usmap::parse(USMAP).expect("usmap");
    let containers = ue_iostore::load_all(&paks).expect("load containers");
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .expect("global.utoc");
    let script_chunk = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .expect("ScriptObjects");
    let scripts = ue_asset::zen::ScriptObjects::parse(
        &ue_iostore::read_chunk(global, script_chunk, None, &[]).unwrap(),
    )
    .expect("script objects");

    let mut parents: BTreeMap<String, Parent> = BTreeMap::new();
    let (mut seen, mut failed) = (0usize, 0usize);
    for c in &containers {
        for (path, idx) in &c.files {
            let leaf = path.rsplit('/').next().unwrap_or(path);
            if !path.ends_with(".uasset") || !(leaf.starts_with("MI") || leaf.starts_with("M_")) {
                continue;
            }
            if want
                .as_ref()
                .is_some_and(|w| !path.to_lowercase().contains(w))
            {
                continue;
            }
            let Ok(data) = ue_iostore::read_chunk(c, &c.chunks[*idx], None, &[]) else {
                continue;
            };
            let Ok(pkg) = ue_asset::package::ZenPackage::parse(&data) else {
                continue;
            };
            let Some(index) = (0..pkg.export_map.len()).find(|i| {
                ue_asset::edit::export_class(&pkg, &scripts, *i)
                    .is_some_and(|c| c.starts_with("MaterialInstance"))
            }) else {
                continue;
            };
            let Ok(edit) = ue_asset::edit::open_export(&pkg, &usmap, &scripts, index) else {
                failed += 1;
                continue;
            };
            let rows = ue_asset::edit::describe(&usmap, &edit.class, &pkg.names.names, &edit.block);
            let mut params = BTreeSet::new();
            for r in &rows {
                if let Some(kind) = r
                    .path
                    .strip_suffix(".ParameterInfo.Name")
                    .and_then(|p| p.split('[').next())
                {
                    params.insert(format!(
                        "{}:{}",
                        kind.trim_end_matches("ParameterValues"),
                        r.value
                    ));
                }
            }
            seen += 1;
            let parent = pkg_parent(&pkg).unwrap_or_else(|| "?".into());
            let entry = parents.entry(parent).or_default();
            entry.instances += 1;
            for p in params {
                *entry.params.entry(p).or_default() += 1;
            }
            if entry.examples.len() < 3 {
                entry
                    .examples
                    .insert(path.trim_end_matches(".uasset").to_string());
            }
        }
    }
    let mut list: Vec<_> = parents.into_iter().collect();
    list.sort_by(|a, b| b.1.instances.cmp(&a.1.instances));
    for (parent, p) in &list {
        println!("{parent}  ({} instance(s))", p.instances);
        for (q, k) in &p.params {
            println!("    {k:5}  {q}");
        }
        for e in &p.examples {
            println!("    e.g. {e}");
        }
    }
    eprintln!(
        "{seen} instance(s), {failed} undecodable, {} parent(s)",
        list.len()
    );
}

/// The parent material's package: the first imported package whose name is a
/// material (the instance imports its parent and its textures).
fn pkg_parent(pkg: &ue_asset::package::ZenPackage) -> Option<String> {
    let names = &pkg.imported_package_names.names;
    names
        .iter()
        .find(|n| {
            let leaf = n.rsplit('/').next().unwrap_or(n);
            leaf.starts_with("M_")
                || leaf.starts_with("MI")
                || leaf.starts_with("MM_")
                || leaf.starts_with("Master")
        })
        .or_else(|| {
            names.iter().find(|n| {
                !n.contains("/Textures/") && !n.rsplit('/').next().unwrap_or(n).starts_with("T_")
            })
        })
        .cloned()
}
