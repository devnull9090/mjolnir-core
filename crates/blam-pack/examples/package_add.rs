//! Add a brand-new cooked Unreal package to the game, rather than replacing a
//! shipped one.
//!
//! ```text
//! cargo run -p blam-pack --example package_add -- \
//!     <paks> <new /Game package path> <package.uasset> <out dir> [imported /Game or /Engine path]...
//! ```
//!
//! Overriding a shipped mesh replaces every use of it — override
//! `/Engine/BasicShapes/Cube` and every cube in the game becomes the new
//! geometry. A new package is placed by nothing, so it only appears where it
//! is spawned.
//!
//! The loader has never seen the id, so the container must register it: the
//! `ContainerHeader` this writes carries the package's own `FPackageId` and
//! the ids of the packages it imports, which is where the async loader takes
//! dependencies from. The imported paths have to be listed because they cannot
//! be recovered from the `.uasset` alone without resolving its import map.
use std::path::PathBuf;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 4 {
        eprintln!(
            "usage: package_add <paks> <new package path> <package.uasset> <out dir> [imported path]..."
        );
        std::process::exit(2);
    }
    let (paks, package_name, uasset_path, out_dir) = (&a[0], &a[1], &a[2], &a[3]);
    let imported: Vec<String> = a[4..].to_vec();
    let oodle: Vec<PathBuf> = Vec::new();

    let uasset = std::fs::read(uasset_path).expect("read package");
    let containers = ue_iostore::load_all(paks).expect("load containers");
    // Any shipped container works as the TOC template; the chunk ids here are
    // derived from the package name, not taken from an index.
    let source = containers
        .iter()
        .find(|c| {
            c.utoc_path
                .file_name()
                .map(|n| n.to_string_lossy().starts_with("pakchunk0-"))
                .unwrap_or(false)
        })
        .expect("no pakchunk0 to use as a TOC template");

    let imported_package_ids: Vec<u64> = imported
        .iter()
        .map(|p| ue_iostore::city::package_id(p))
        .collect();
    println!("adding {package_name}");
    println!(
        "  id {:#018x}, {} byte(s), {} import(s)",
        ue_iostore::city::package_id(package_name),
        uasset.len(),
        imported.len()
    );
    for (p, id) in imported.iter().zip(&imported_package_ids) {
        println!("    imports {p} -> {id:#018x}");
    }

    let container_name = "pakchunk989-MJOLNIRMESH-Windows_P";
    let built = blam_pack::build_addition(
        source,
        &oodle,
        container_name,
        &[blam_pack::NewPackage {
            package_name: package_name.clone(),
            uasset,
            ubulk: Vec::new(),
            imported_package_ids,
            uasset_meta: Vec::new(),
            ubulk_meta: Vec::new(),
        }],
    )
    .expect("build addition");

    std::fs::create_dir_all(out_dir).expect("create out dir");
    let utoc = PathBuf::from(format!("{out_dir}/{container_name}.utoc"));
    let ucas = PathBuf::from(format!("{out_dir}/{container_name}.ucas"));
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
    println!("  copy a small shipped .pak beside them as {container_name}.pak, then install all three.");
}
