//! Put an edited cooked Unreal package in front of the game as an override
//! container.
//!
//! ```text
//! cargo run -p blam-pack --example package_override -- \
//!     <paks> <package path substring> <patched .uasset> <out dir> //!     [--name <container base>] [imported /Game or /Engine package path]...
//! ```
//!
//! The imported paths, when given, are written into a package-store entry for
//! the overridden package in this container's own header: an override that
//! adds imports to the asset needs them, because the runtime resolves an
//! import's package through the store entry rather than the asset header, and
//! the shipped entry still describes the shipped import list. List them in the
//! asset's own order -- `mesh_rewrite` prints it.
//!
//! This is the plain-package sibling of `mjolnir pack`, which handles Blam
//! tags. The chunk id is taken from the shipped index, so the override answers
//! exactly the request the game already makes for that package, and the
//! written container is read back through the perfect hash before the tool
//! reports success — a container whose tables do not resolve reads fine from a
//! chunk list and is silently ignored in game.
use std::path::PathBuf;

fn main() {
    let mut a: Vec<String> = std::env::args().skip(1).collect();
    // `--name <container base>`: two overrides installed side by side need
    // containers of their own (default pakchunk989-MJOLNIRMESH-Windows_P).
    let mut container_name = "pakchunk989-MJOLNIRMESH-Windows_P".to_string();
    if let Some(i) = a.iter().position(|x| x == "--name") {
        container_name = a.get(i + 1).expect("--name needs a value").clone();
        a.drain(i..i + 2);
    }
    if a.len() < 4 {
        eprintln!("usage: package_override <paks> <package substring> <patched.uasset> <out dir>");
        std::process::exit(2);
    }
    let (paks, want, patched_path, out_dir) = (&a[0], a[1].to_ascii_lowercase(), &a[2], &a[3]);
    let imported: Vec<String> = a[4..].to_vec();
    let oodle: Vec<PathBuf> = Vec::new();

    let patched = std::fs::read(patched_path).expect("read patched package");
    let containers = ue_iostore::load_all(paks).expect("load containers");

    let (container, chunk) = containers
        .iter()
        .find_map(|c| {
            c.files
                .iter()
                .find(|(p, _)| p.ends_with(".uasset") && p.to_ascii_lowercase().contains(&want))
                .map(|(p, i)| {
                    println!(
                        "overriding {p}\n  in {}",
                        c.utoc_path.file_name().unwrap().to_string_lossy()
                    );
                    (c, c.chunks[*i].clone())
                })
        })
        .expect("no package matched");

    let original = ue_iostore::read_chunk(container, &chunk, None, &oodle).expect("read original");
    println!("  {} -> {} bytes", original.len(), patched.len());

    // The package id a store entry is keyed by comes from the zen package's
    // own name, not from the file path.
    let store: Vec<(u64, Vec<u64>)> = if imported.is_empty() {
        Vec::new()
    } else {
        let name = ue_asset::package::ZenPackage::parse(&patched)
            .expect("parse the patched package for its name")
            .name();
        println!("  store entry for {name}:");
        for p in &imported {
            println!(
                "    imports {p} -> {:#018x}",
                ue_iostore::city::package_id(p)
            );
        }
        vec![(
            ue_iostore::city::package_id(&name),
            imported
                .iter()
                .map(|p| ue_iostore::city::package_id(p))
                .collect(),
        )]
    };

    let built = blam_pack::build_override_with_store(
        container,
        &oodle,
        &[blam_pack::ChunkEdit {
            label: want.clone(),
            chunk: chunk.clone(),
            // A cooked Unreal package has no Blam `BinaryBlobSize` to keep in
            // step, so the resize fixup that a tag payload needs must not run:
            // declaring the original length as the patched one keeps the
            // packer on the plain-replacement path.
            original_len: patched.len(),
            patched: patched.clone(),
        }],
        &store,
    )
    .expect("build override");

    std::fs::create_dir_all(out_dir).expect("create out dir");
    let name = container_name.as_str();
    let utoc = PathBuf::from(format!("{out_dir}/{name}.utoc"));
    let ucas = PathBuf::from(format!("{out_dir}/{name}.ucas"));
    std::fs::write(&utoc, &built.utoc).expect("write utoc");
    std::fs::write(&ucas, &built.ucas).expect("write ucas");

    match blam_pack::verify_written(&utoc, &oodle, &built.expect) {
        Ok(()) => println!("  verify   the container reads back through its perfect hash"),
        Err(e) => {
            eprintln!("  verify FAILED: {e}");
            std::process::exit(1);
        }
    }
    println!("  wrote {}", utoc.display());
    println!("  wrote {}", ucas.display());
    println!("  copy a small shipped .pak beside them as {name}.pak, then install all three.");
}
