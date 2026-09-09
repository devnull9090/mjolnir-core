//! Put an edited cooked Unreal package in front of the game as an override
//! container.
//!
//! ```text
//! cargo run -p blam-pack --example package_override -- \
//!     <paks> <package path substring> <patched .uasset> <out dir>
//! ```
//!
//! This is the plain-package sibling of `mjolnir pack`, which handles Blam
//! tags. The chunk id is taken from the shipped index, so the override answers
//! exactly the request the game already makes for that package, and the
//! written container is read back through the perfect hash before the tool
//! reports success — a container whose tables do not resolve reads fine from a
//! chunk list and is silently ignored in game.
use std::path::PathBuf;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 4 {
        eprintln!("usage: package_override <paks> <package substring> <patched.uasset> <out dir>");
        std::process::exit(2);
    }
    let (paks, want, patched_path, out_dir) = (&a[0], a[1].to_ascii_lowercase(), &a[2], &a[3]);
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

    let built = blam_pack::build_override(
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
    )
    .expect("build override");

    std::fs::create_dir_all(out_dir).expect("create out dir");
    let name = "pakchunk989-MJOLNIRMESH-Windows_P";
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
