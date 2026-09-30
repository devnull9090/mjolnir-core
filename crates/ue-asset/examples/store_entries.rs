//! Compare each package's store entry (the container header's
//! `FFilePackageStoreEntry`) against its own header's imported-package list.
//!
//!   cargo run -p ue-iostore --example store_entries -- <paks> <utoc substring> [package substring]
//!
//! A package import inside a cooked asset is `(imported package index, public
//! export hash index)`, and the runtime turns that index into an `FPackageId`
//! through the *store entry*, not through the asset header. If the two lists
//! are the same length and the same ids in the same order for every shipped
//! package, then adding an import to an asset without also growing its store
//! entry indexes off the end of that array — which is what this checks.
use std::collections::HashMap;

fn read_imports(store: &[u8], i: usize) -> Vec<u64> {
    let at = i * 16;
    let u32_at = |o: usize| {
        store
            .get(o..o + 4)
            .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
            .unwrap_or(0)
    };
    let count = u32_at(at) as usize;
    let rel = u32_at(at + 4) as usize;
    (0..count)
        .map(|k| {
            let o = at + rel + k * 8;
            store
                .get(o..o + 8)
                .map(|b| u64::from_le_bytes(b.try_into().unwrap()))
                .unwrap_or(0)
        })
        .collect()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let (paks, want) = (&a[0], &a[1]);
    let filter = a.get(2).map(|s| s.to_ascii_lowercase());
    let containers = ue_iostore::load_all(paks)?;
    let c = containers
        .iter()
        .find(|c| {
            c.utoc_path
                .file_name()
                .map(|n| n.to_string_lossy().contains(want.as_str()))
                .unwrap_or(false)
        })
        .expect("no container matched");

    let header_chunk = c
        .chunks
        .iter()
        .find(|k| k.chunk_type == 6)
        .expect("container has no header chunk");
    let header = ue_iostore::container_header::ContainerHeader::parse(&ue_iostore::read_chunk(
        c,
        header_chunk,
        None,
        &[],
    )?)?;
    let slot_of: HashMap<u64, usize> = header
        .package_ids
        .iter()
        .enumerate()
        .map(|(i, id)| (*id, i))
        .collect();
    println!(
        "{}: {} registered package(s)",
        c.utoc_path.file_name().unwrap().to_string_lossy(),
        header.package_ids.len()
    );

    let (mut same, mut differ, mut looked) = (0usize, 0usize, 0usize);
    for (rel, chunk_index) in &c.files {
        if !rel.ends_with(".uasset") {
            continue;
        }
        if let Some(f) = &filter {
            if !rel.to_ascii_lowercase().contains(f.as_str()) {
                continue;
            }
        }
        let data = ue_iostore::read_chunk(c, &c.chunks[*chunk_index], None, &[])?;
        let Ok(p) = ue_asset::package::ZenPackage::parse(&data) else {
            continue;
        };
        let name = p.name();
        let Some(slot) = slot_of.get(&ue_iostore::city::package_id(&name)) else {
            continue;
        };
        looked += 1;
        let store = read_imports(&header.store_entries, *slot);
        let asset: Vec<u64> = p
            .imported_package_names
            .names
            .iter()
            .map(|n| ue_iostore::city::package_id(n))
            .collect();
        if store == asset {
            same += 1;
        } else {
            differ += 1;
            if differ <= 10 {
                println!(
                    "  {name}\n    asset header: {} import(s) {:?}\n    store entry:  {} import(s) {:?}",
                    asset.len(),
                    asset.iter().take(4).map(|i| format!("{i:#018x}")).collect::<Vec<_>>(),
                    store.len(),
                    store.iter().take(4).map(|i| format!("{i:#018x}")).collect::<Vec<_>>()
                );
            }
        }
        if filter.is_some() {
            println!(
                "  {name}: asset {} import(s), store {} -- {}",
                asset.len(),
                store.len(),
                if store == asset {
                    "identical"
                } else {
                    "DIFFER"
                }
            );
            for (i, n) in p.imported_package_names.names.iter().enumerate() {
                println!(
                    "    [{i}] {n} -> {:#018x} / store {:#018x}",
                    ue_iostore::city::package_id(n),
                    store.get(i).copied().unwrap_or(0)
                );
            }
        }
    }
    println!("  {looked} package(s) checked: {same} identical, {differ} different");
    Ok(())
}
