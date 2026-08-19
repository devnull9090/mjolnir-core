//! Every Blam*MeshSynchronization data asset: which model tag it anchors, and
//! which SK meshes live nearby — the route to a biped's body mesh.
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{install, zen};
fn main() -> Result<(), String> {
    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    let das = catalog.packages_matching("meshsynchronization");
    println!("{} data assets", das.len());
    for da in &das {
        let Some(bytes) = catalog.read_package(da) else {
            println!("{da}: unreadable");
            continue;
        };
        let tags: Vec<String> = zen::imported_package_names(&bytes)
            .into_iter()
            .filter(|p| p.starts_with("/Game/Tags/"))
            .collect();
        // Skeletal meshes directly in the DA's Mesh folder, or its parent's
        // (a `Common` DA usually sits beside a shared Mesh folder).
        let folder = da.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
        let root = folder.strip_suffix("/Common").unwrap_or(folder);
        let in_dir = |dir: &str| -> Vec<String> {
            let mesh_dir = format!("{}/mesh/", dir.trim_start_matches("/Game/").to_ascii_lowercase());
            catalog
                .meshes
                .iter()
                .filter(|m| {
                    let lower = m.short.to_ascii_lowercase();
                    m.skeletal
                        && lower.starts_with(&mesh_dir)
                        && !lower[mesh_dir.len()..].contains('/')
                })
                .map(|m| m.short.rsplit('/').next().unwrap_or(&m.short).to_string())
                .collect()
        };
        let mut sks = in_dir(folder);
        let mut whence = "<DA>/Mesh";
        if sks.is_empty() && root != folder {
            sks = in_dir(root);
            whence = "<root>/Mesh";
        }
        println!("{da}\n  tags: {tags:?}\n  SK in {whence}: {} {:?}", sks.len(), sks);
    }
    Ok(())
}
