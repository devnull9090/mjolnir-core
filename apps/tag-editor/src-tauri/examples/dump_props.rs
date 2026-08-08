//! Walk a cooked export's unversioned properties and report where they end —
//! the byte where native serialization begins. The empirical check for the
//! whole property-walker + usmap stack.
//!
//!   cargo run --release --example dump_props -- SM_Elite_Dead_Elbow_L_Default

use tag_editor_lib::install;
use ue_asset::unversioned::{Ctx, Keep, Walker};
use ue_asset::zen::{ObjectRef, Package, ScriptObjects};
use ue_asset::Usmap;

fn main() -> Result<(), String> {
    let query = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "SM_Elite_Dead_Elbow_L_Default".to_string())
        .to_lowercase();
    let usmap_path = std::env::args()
        .nth(2)
        .unwrap_or_else(|| "../../../defs/ue/Meteorite-2607-CU3.usmap".to_string());

    let usmap_bytes = std::fs::read(&usmap_path).map_err(|e| format!("{usmap_path}: {e}"))?;
    let usmap = Usmap::parse(&usmap_bytes).map_err(|e| e.to_string())?;

    let found = install::detect();
    let paks = found.paks.ok_or("no install")?;
    let oodle_roots: Vec<std::path::PathBuf> = found.oodle.iter().map(Into::into).collect();
    let containers = ue_iostore::load_all(&paks).map_err(|e| e.to_string())?;

    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .ok_or("no global.utoc")?;
    let chunk = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .ok_or("no ScriptObjects chunk")?;
    let script_bytes =
        ue_iostore::read_chunk(global, chunk, None, &oodle_roots).map_err(|e| e.to_string())?;
    let scripts = ScriptObjects::parse(&script_bytes).map_err(|e| e.to_string())?;

    let mut hit = None;
    for c in &containers {
        for (rel, &idx) in &c.files {
            let full = c.full_path(rel);
            let lower = full.to_lowercase();
            if lower.ends_with(".uasset") && lower.contains(&query) {
                hit = Some((c, idx, full.clone()));
                break;
            }
        }
        if hit.is_some() {
            break;
        }
    }
    let (container, chunk_index, full) = hit.ok_or_else(|| format!("no package matching {query:?}"))?;
    let chunk = container.chunks[chunk_index];
    let data = ue_iostore::read_chunk(container, &chunk, None, &oodle_roots)
        .map_err(|e| e.to_string())?;
    println!("{full}");

    let package = Package::parse(&data).map_err(|e| e.to_string())?;
    let ctx = Ctx {
        usmap: &usmap,
        names: &package.names,
    };

    for (i, e) in package.exports.iter().enumerate() {
        let class = match e.class.classify() {
            ObjectRef::Script(_) => scripts.leaf(e.class).unwrap_or("?").to_string(),
            other => format!("{other:?}"),
        };
        let bytes = package.export_data(&data, i).map_err(|e| e.to_string())?;
        if std::env::var_os("UE_ASSET_TRACE").is_some() {
            eprint!("export [{i}] head:");
            for (n, b) in bytes[..bytes.len().min(192)].iter().enumerate() {
                if n % 16 == 0 {
                    eprint!("\n  {n:4}:");
                }
                eprint!(" {b:02x}");
            }
            eprintln!();
        }
        let mut walker = Walker::new(&ctx, bytes);
        match walker.read_object(&class, Keep::All) {
            Ok(props) => {
                println!(
                    "\nexport [{i}] {} ({class}): properties end at {} of {} bytes ({} native remain)",
                    e.name,
                    walker.pos,
                    bytes.len(),
                    bytes.len() - walker.pos
                );
                let mut keys: Vec<_> = props.iter().collect();
                keys.sort_by(|a, b| a.0.cmp(b.0));
                for (k, v) in keys.iter().take(20) {
                    let shown = format!("{v:?}");
                    println!("  {k} = {}", &shown[..shown.len().min(120)]);
                }
                // The native tail's first bytes, to orient the mesh parser.
                let window: usize = std::env::var("UE_ASSET_TAIL")
                    .ok()
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(32);
                let tail = &bytes[walker.pos..bytes.len().min(walker.pos + window)];
                print!("  native head:");
                for (n, b) in tail.iter().enumerate() {
                    if n % 16 == 0 {
                        print!("\n    +{n:4}:");
                    }
                    print!(" {b:02x}");
                }
                println!();
            }
            Err(err) => println!("\nexport [{i}] {} ({class}): FAILED at {:#x}: {err}", e.name, walker.pos),
        }
    }
    Ok(())
}
