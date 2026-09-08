//! Rebuild a container with one extra package-import edge in its store entry.
//!
//! ```text
//! cargo run -p ue-iostore --example relink_container -- \
//!     <paks> <utoc substring> <importer /Game/...> <imported /Game/...> <out dir>
//! ```
//!
//! Why this exists: a cooked package is only loaded when something pulls it
//! in. The async loader takes those dependencies from the container header's
//! `FFilePackageStoreEntry` for the importing package, not from the asset
//! header, so adding the imported package's `FPackageId` to that list makes
//! the engine load it alongside its importer with no reference in the world
//! itself. That matters here because a cooked *actor* referencing the asset
//! crashes this game's build (see `unreal/MJOLNIRMapKit/README.md`), while the
//! asset alone may be fine.
//!
//! The whole container is re-emitted rather than patched in place: the edit
//! changes a chunk's length, which moves every later chunk and invalidates the
//! offsets and the BLAKE3 chunk-meta hash the game checks when it mounts a
//! `ContainerHeader`. `pack::build_indexed` recomputes all of that.
use std::path::PathBuf;
use ue_iostore::container_header::ContainerHeader;

/// One package's two carrays in a store entry: imported packages and shader
/// map hashes. Both are `{u32 count, u32 offset}` where the offset is
/// relative to that member's own position.
fn read_entries(store: &[u8], n: usize) -> Vec<(Vec<u64>, Vec<u64>)> {
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        let mut members = Vec::new();
        for member in [0usize, 8] {
            let at = i * 16 + member;
            let read_u32 = |o: usize| {
                store
                    .get(o..o + 4)
                    .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
                    .unwrap_or(0)
            };
            let count = read_u32(at) as usize;
            let rel = read_u32(at + 4) as usize;
            let mut ids = Vec::with_capacity(count);
            for k in 0..count {
                let o = at + rel + k * 8;
                ids.push(
                    store
                        .get(o..o + 8)
                        .map(|b| u64::from_le_bytes(b.try_into().unwrap()))
                        .unwrap_or(0),
                );
            }
            members.push(ids);
        }
        let shaders = members.pop().unwrap();
        let imports = members.pop().unwrap();
        out.push((imports, shaders));
    }
    out
}

/// Rebuild the store-entry block, preserving both carrays of every package.
fn write_entries(entries: &[(Vec<u64>, Vec<u64>)]) -> Vec<u8> {
    let fixed = entries.len() * 16;
    let mut out = vec![0u8; fixed];
    let mut heap: Vec<u8> = Vec::new();
    for (i, (imports, shaders)) in entries.iter().enumerate() {
        for (member, ids) in [(0usize, imports), (8usize, shaders)] {
            if ids.is_empty() {
                continue;
            }
            let member_at = i * 16 + member;
            let data_at = fixed + heap.len();
            let rel = (data_at - member_at) as u32;
            out[member_at..member_at + 4].copy_from_slice(&(ids.len() as u32).to_le_bytes());
            out[member_at + 4..member_at + 8].copy_from_slice(&rel.to_le_bytes());
            for id in ids {
                heap.extend_from_slice(&id.to_le_bytes());
            }
        }
    }
    out.extend_from_slice(&heap);
    out
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 5 {
        eprintln!("usage: relink_container <paks> <utoc substring> <importer> <imported> <out dir>");
        std::process::exit(2);
    }
    let (paks, want, importer, imported, out_dir) = (&a[0], &a[1], &a[2], &a[3], &a[4]);
    let oodle: Vec<PathBuf> = Vec::new();

    let containers = ue_iostore::load_all(paks).expect("load containers");
    let c = containers
        .iter()
        .find(|c| {
            c.utoc_path
                .file_name()
                .map(|n| n.to_string_lossy().contains(want.as_str()))
                .unwrap_or(false)
        })
        .expect("no container matched");
    println!(
        "{}: {} chunk(s), {} indexed file(s), mount {:?}",
        c.utoc_path.file_name().unwrap().to_string_lossy(),
        c.chunks.len(),
        c.files.len(),
        c.mount_point
    );

    // "none" rebuilds the container byte-for-byte in content but through the
    // same code path, which is the control for "did the rebuild itself break
    // anything" before any conclusion is drawn from an edited one.
    let no_change = imported == "none";
    let importer_id = ue_iostore::city::package_id(importer);
    let imported_id = ue_iostore::city::package_id(imported);
    println!("  importer {importer} -> {importer_id:#018x}");
    println!("  imported {imported} -> {imported_id:#018x}");

    // Read every chunk out, patching the container header on the way.
    let mut entries: Vec<ue_iostore::pack::Entry> = Vec::new();
    let mut chunk_to_entry = std::collections::HashMap::new();
    let mut patched = false;
    for ch in &c.chunks {
        let mut data = ue_iostore::read_chunk(c, ch, None, &oodle).expect("read chunk");
        if ch.chunk_type == 6 && !no_change {
            let mut h = ContainerHeader::parse(&data).expect("parse container header");
            let n = h.package_ids.len();
            let mut per = read_entries(&h.store_entries, n);
            let idx = h
                .package_ids
                .iter()
                .position(|id| *id == importer_id)
                .expect("the importer package is not registered in this container");
            if !h.package_ids.contains(&imported_id) {
                eprintln!("warning: the imported package is not in this container's store");
            }
            if per[idx].0.contains(&imported_id) {
                println!("  already imported; nothing to add");
            } else {
                per[idx].0.push(imported_id);
                patched = true;
            }
            println!(
                "  header: {n} package(s); importer slot {idx} now imports {} package(s)",
                per[idx].0.len()
            );
            h.store_entries = write_entries(&per);
            data = h.write();
        }
        chunk_to_entry.insert(ch.index, entries.len());
        entries.push(ue_iostore::pack::Entry {
            id: ue_iostore::toc::ChunkId {
                id: ch.chunk_id,
                index: ch.chunk_index,
                pad: 0,
                kind: ch.chunk_type,
            },
            data,
            meta: Vec::new(),
        });
    }
    if !patched {
        println!("  (no change made)");
    }

    // Preserve the directory index so paths keep resolving.
    let mut files: Vec<(String, usize)> = c
        .files
        .iter()
        .filter_map(|(path, chunk_index)| {
            chunk_to_entry.get(chunk_index).map(|e| (path.clone(), *e))
        })
        .collect();
    files.sort();

    let template = ue_iostore::toc::Toc::read(&c.utoc_path).expect("read toc");
    let built = ue_iostore::pack::build_indexed(
        &template,
        c.container_id,
        &entries,
        Some((c.mount_point.as_str(), &files)),
    );

    std::fs::create_dir_all(out_dir).expect("create out dir");
    let stem = c
        .utoc_path
        .file_stem()
        .unwrap()
        .to_string_lossy()
        .to_string();
    let utoc = format!("{out_dir}/{stem}.utoc");
    let ucas = format!("{out_dir}/{stem}.ucas");
    std::fs::write(&utoc, &built.utoc).expect("write utoc");
    std::fs::write(&ucas, &built.ucas).expect("write ucas");
    println!("  wrote {utoc} ({} bytes)", built.utoc.len());
    println!("  wrote {ucas} ({} bytes)", built.ucas.len());
}
