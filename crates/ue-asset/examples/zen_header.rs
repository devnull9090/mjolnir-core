//! Dump a package's zen header the way `ZenPackage` models it: names,
//! imports (resolved to their packages), exports, bundles and the dependency
//! bundle. This is the layout an edited package has to reproduce.
//!
//!   cargo run -p ue-asset --example zen_header -- <paks> <path substring>
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let paks = args.next().expect("usage: zen_header <paks> <substring>");
    let want = args
        .next()
        .expect("usage: zen_header <paks> <substring>")
        .to_ascii_lowercase();
    let containers = ue_iostore::load_all(&paks)?;
    for c in &containers {
        for (rel, chunk_index) in &c.files {
            if !rel.ends_with(".uasset") || !rel.to_ascii_lowercase().contains(&want) {
                continue;
            }
            let data = ue_iostore::read_chunk(c, &c.chunks[*chunk_index], None, &[])?;
            let p = ue_asset::package::ZenPackage::parse(&data)?;
            println!("== {rel} ({} bytes)", data.len());
            println!(
                "   name {} header {:#x} cooked header {:#x} flags {:#x}",
                p.name(),
                u32::from_le_bytes(data[4..8].try_into().unwrap()),
                p.cooked_header_size,
                p.package_flags
            );
            for (i, n) in p.names.names.iter().enumerate() {
                println!("   name[{i}] {n}");
            }
            for (i, n) in p.imported_package_names.names.iter().enumerate() {
                println!(
                    "   imported package[{i}] {n} #{}",
                    p.imported_package_name_numbers.get(i).copied().unwrap_or(0)
                );
            }
            for (i, h) in p.imported_public_export_hashes.iter().enumerate() {
                println!("   public export hash[{i}] {h:#018x}");
            }
            for (i, v) in p.import_map.iter().enumerate() {
                let kind = v >> 62;
                let what = match kind {
                    2 => format!(
                        "package import: package {} hash {}",
                        (v >> 32) & 0x3fff_ffff,
                        v & 0xffff_ffff
                    ),
                    0 if *v == u64::MAX => "null".to_string(),
                    _ => format!("kind {kind} value {v:#018x}"),
                };
                println!("   import[{i}] (object {}) {what}", -(i as i32) - 1);
            }
            for (i, e) in p.export_map.iter().enumerate() {
                println!(
                    "   export[{i}] serial {}+{} name {} class {:#x} hash {:#018x} flags {:#x}",
                    e.cooked_serial_offset,
                    e.cooked_serial_size,
                    p.names
                        .names
                        .get(e.name_index as usize)
                        .map(String::as_str)
                        .unwrap_or("?"),
                    e.class,
                    e.public_export_hash,
                    e.object_flags
                );
            }
            for (i, (local, cmd)) in p.export_bundle_entries.iter().enumerate() {
                println!("   export bundle[{i}] export {local} command {cmd}");
            }
            for (i, h) in p.dependency_bundle_headers.iter().enumerate() {
                println!(
                    "   dependency bundle[{i}] first {} counts {:?}",
                    h.first_entry_index, h.counts
                );
            }
            for (i, e) in p.dependency_bundle_entries.iter().enumerate() {
                println!("   dependency entry[{i}] {e}");
            }
        }
    }
    Ok(())
}
