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
    let mut a: Vec<String> = std::env::args().skip(1).collect();
    // `--name <container base>` (default pakchunk989-MJOLNIRMESH-Windows_P)
    // and any number of `--package </Game/new/path>=<file.uasset>`: one
    // container can carry several new packages (a converted map's meshes),
    // each with its imports read from the package itself.
    let mut container_name = "pakchunk989-MJOLNIRMESH-Windows_P".to_string();
    if let Some(i) = a.iter().position(|x| x == "--name") {
        container_name = a.get(i + 1).expect("--name needs a value").clone();
        a.drain(i..i + 2);
    }
    let mut extra: Vec<(String, String)> = Vec::new();
    while let Some(i) = a.iter().position(|x| x == "--package") {
        let spec = a.get(i + 1).expect("--package needs path=file").clone();
        let (path, file) = spec
            .split_once('=')
            .expect("--package takes </Game/path>=<file.uasset>");
        extra.push((path.to_string(), file.to_string()));
        a.drain(i..i + 2);
    }
    if a.len() < 2 || (extra.is_empty() && a.len() < 4) {
        eprintln!(
            "usage: package_add <paks> <new package path> <package.uasset> <out dir> [imported path]...\n       package_add <paks> <out dir> [--name <container>] --package <path>=<uasset>..."
        );
        std::process::exit(2);
    }
    let paks = &a[0];
    let (packages, out_dir): (Vec<(String, String, Vec<String>)>, String) = if extra.is_empty() {
        (
            vec![(a[1].clone(), a[2].clone(), a[4..].to_vec())],
            a[3].clone(),
        )
    } else {
        let packages = extra
            .into_iter()
            .map(|(path, file)| {
                let bytes = std::fs::read(&file).expect("read package");
                let zp = ue_asset::package::ZenPackage::parse(&bytes)
                    .expect("parse package for its imports");
                let imports: Vec<String> = zp.imported_package_names.names.clone();
                (path, file, imports)
            })
            .collect();
        (packages, a[1].clone())
    };
    let out_dir = &out_dir;
    let oodle: Vec<PathBuf> = Vec::new();
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

    let mut new_packages = Vec::new();
    for (package_name, uasset_path, imported) in &packages {
        let uasset = std::fs::read(uasset_path).expect("read package");
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
        new_packages.push(blam_pack::NewPackage {
            package_name: package_name.clone(),
            uasset,
            ubulk: Vec::new(),
            imported_package_ids,
            uasset_meta: Vec::new(),
            ubulk_meta: Vec::new(),
        });
    }

    let container_name = container_name.as_str();
    let built = blam_pack::build_addition(source, &oodle, container_name, &new_packages)
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
    println!(
        "  copy a small shipped .pak beside them as {container_name}.pak, then install all three."
    );
}
