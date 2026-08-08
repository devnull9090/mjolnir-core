//! Open a cooked mesh package and print its structure: exports with resolved
//! classes and data ranges. The groundwork check for the UE mesh parser.
//!
//!   cargo run --release --example dump_zen -- SM_Elite_Dead_Elbow_L_Default

use tag_editor_lib::install;
use ue_asset::zen::{ObjectRef, Package, ScriptObjects};

fn main() -> Result<(), String> {
    let query = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "SM_Elite_Dead_Elbow_L_Default".to_string())
        .to_lowercase();

    let found = install::detect();
    let paks = found.paks.ok_or("no install")?;
    let oodle_roots: Vec<std::path::PathBuf> = found.oodle.iter().map(Into::into).collect();
    let containers = ue_iostore::load_all(&paks).map_err(|e| e.to_string())?;

    // Script object table from the global container.
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
    println!("script objects: {}", scripts.paths.len());

    // Find the wanted .uasset (and its .ubulk sibling if any).
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
    println!("\n{full}\n  chunk {} bytes", data.len());

    let package = Package::parse(&data).map_err(|e| e.to_string())?;
    println!(
        "  package {:?}  header {} cooked-header {}  names {}  imports {}  exports {}",
        package.name,
        package.header_size,
        package.cooked_header_size,
        package.names.len(),
        package.imports.len(),
        package.exports.len()
    );
    for p in &package.imported_package_names {
        println!("  imported pkg: {p}");
    }

    for (i, e) in package.exports.iter().enumerate() {
        let class = match e.class.classify() {
            ObjectRef::Script(_) => scripts
                .leaf(e.class)
                .unwrap_or("<unknown script>")
                .to_string(),
            other => format!("{other:?}"),
        };
        let range = package.export_data(&data, i).map(|d| d.len());
        println!(
            "  export [{i}] {:<40} class {:<28} cooked-off {:>8}  size {:>8}  slice {:?}",
            e.name, class, e.cooked_serial_offset, e.serial_size, range.map(|l| l)
        );
    }

    // Exports should tile the chunk contiguously from the header.
    let mut sorted: Vec<_> = package.exports.iter().collect();
    sorted.sort_by_key(|e| e.cooked_serial_offset);
    let mut expect = 0u64;
    let mut contiguous = true;
    for e in &sorted {
        if e.cooked_serial_offset != expect {
            contiguous = false;
        }
        expect = e.cooked_serial_offset + e.serial_size;
    }
    println!(
        "\n  exports {} · tail at {} of {} chunk bytes ({} trailing)",
        if contiguous { "tile contiguously" } else { "DO NOT TILE" },
        package.header_size as u64 + expect,
        data.len(),
        data.len() as i64 - (package.header_size as u64 + expect) as i64,
    );
    Ok(())
}
