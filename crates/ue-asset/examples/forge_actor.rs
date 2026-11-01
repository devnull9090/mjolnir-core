//! Clone the shipped synchronized crate actor around a new Forge mesh.
//! No game package is overridden. The clone retains the native Blam binding,
//! uses one visual component, and leaves collision to the simulation.
//! forge_actor <paks> <new /Game/BP path> <mesh /Game path> <out.uasset>
//!             <centre x,y,z in cm> <normalization scale> [material paths...]
use std::error::Error;
use ue_asset::{
    edit,
    package::{public_export_hash, NameBatch, ZenPackage},
    props::Val,
};

fn fail(s: impl Into<String>) -> Box<dyn Error> {
    s.into().into()
}

fn import(pkg: &mut ZenPackage, path: &str) -> i32 {
    let pi = pkg.imported_package_names.intern(path);
    while pkg.imported_package_name_numbers.len() < pkg.imported_package_names.names.len() {
        pkg.imported_package_name_numbers.push(0);
    }
    let hi = pkg.imported_public_export_hashes.len() as u64;
    pkg.imported_public_export_hashes
        .push(public_export_hash(path.rsplit('/').next().unwrap()));
    pkg.import_map
        .push((2u64 << 62) | (u64::from(pi) << 32) | hi);
    -(pkg.import_map.len() as i32)
}

fn property(
    usmap: &ue_asset::Usmap,
    class: &str,
    block: &mut ue_asset::props::Block,
    name: &str,
    value: Val,
) -> Result<(), Box<dyn Error>> {
    let slot = (0..usmap.total_slots(class))
        .find(|s| {
            usmap
                .resolve(class, *s)
                .is_some_and(|(_, p)| p.name == name)
        })
        .ok_or_else(|| fail(format!("{class}.{name} is missing")))?;
    block.set(slot, value);
    Ok(())
}

fn export_path(pkg: &ZenPackage, index: usize, depth: usize) -> Result<String, Box<dyn Error>> {
    if depth > 32 {
        return Err(fail("export outer cycle"));
    }
    let e = &pkg.export_map[index];
    let name = pkg.mapped_name(e.name_index, e.name_number);
    if e.outer >> 62 == 0 {
        let outer = usize::try_from(e.outer)?;
        if outer >= pkg.export_map.len() {
            return Err(fail("invalid export outer"));
        }
        Ok(format!("{}/{}", export_path(pkg, outer, depth + 1)?, name))
    } else {
        Ok(name)
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 6 {
        return Err(fail(
            "forge_actor <paks> <actor path> <mesh path> <out> <x,y,z> <scale> [materials...]",
        ));
    }
    let centre: Vec<f64> = a[4].split(',').map(str::parse).collect::<Result<_, _>>()?;
    let scale: f64 = a[5].parse()?;
    if centre.len() != 3
        || centre.iter().any(|x| !x.is_finite())
        || !scale.is_finite()
        || scale <= 0.0
    {
        return Err(fail("invalid component transform"));
    }
    let containers = ue_iostore::load_all(&a[0])?;
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .ok_or("no global container")?;
    let sc = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .ok_or("no script objects")?;
    let scripts =
        ue_asset::zen::ScriptObjects::parse(&ue_iostore::read_chunk(global, sc, None, &[])?)?;
    let usmap =
        ue_asset::Usmap::parse(include_bytes!("../../../defs/ue/Meteorite-2607-CU3.usmap"))?;
    let (container, ci) = containers
        .iter()
        .find_map(|c| {
            c.files
                .iter()
                .find(|(p, _)| p.ends_with("/BP_CrateSpaceACrateActor.uasset"))
                .map(|(_, i)| (c, *i))
        })
        .ok_or("shipped crate actor not found")?;
    let data = ue_iostore::read_chunk(container, &container.chunks[ci], None, &[])?;
    let old_header = u32::from_le_bytes(data[4..8].try_into()?);
    let mut pkg = ZenPackage::parse(&data)?;
    let old_path = pkg.name();
    let old_leaf = old_path.rsplit('/').next().ok_or("actor leaf")?.to_string();
    let new_leaf = a[1].rsplit('/').next().ok_or("new actor leaf")?;
    if !a[1].starts_with("/Game/MJOLNIR/Forge/")
        || !new_leaf.starts_with("BP_")
        || !a[2].starts_with("/Game/MJOLNIR/Forge/")
    {
        return Err(fail("use namespaced Forge actor/mesh paths"));
    }
    // Rename the generated class and CDO as well as the package. Rebuild all
    // nested public hashes from their outer paths (component templates too).
    pkg.names = NameBatch::from_names(
        pkg.names
            .names
            .iter()
            .map(|n| {
                if n == &old_path {
                    a[1].clone()
                } else if n == &format!("{old_leaf}_C") {
                    format!("{new_leaf}_C")
                } else if n == &format!("Default__{old_leaf}_C") {
                    format!("Default__{new_leaf}_C")
                } else {
                    n.clone()
                }
            })
            .collect(),
    );
    for i in 0..pkg.export_map.len() {
        if pkg.export_map[i].public_export_hash != 0 {
            pkg.export_map[i].public_export_hash = public_export_hash(&export_path(&pkg, i, 0)?);
        }
    }
    let mesh = import(&mut pkg, &a[2]);
    let materials: Vec<i32> = a[6..].iter().map(|p| import(&mut pkg, p)).collect();
    let mut main_index = None;
    for i in 0..pkg.export_map.len() {
        if edit::export_class(&pkg, &scripts, i).as_deref() != Some("StaticMeshComponent") {
            continue;
        }
        let mut e = edit::open_export(&pkg, &usmap, &scripts, i).map_err(fail)?;
        let main =
            pkg.names.names[pkg.export_map[i].name_index as usize] == "StaticMesh_GEN_VARIABLE";
        property(
            &usmap,
            &e.class,
            &mut e.block,
            "StaticMesh",
            Val::Object(if main { mesh } else { 0 }),
        )?;
        property(
            &usmap,
            &e.class,
            &mut e.block,
            "OverrideMaterials",
            Val::Array(if main {
                materials.iter().map(|x| Val::Object(*x)).collect()
            } else {
                vec![]
            }),
        )?;
        for (p, v) in [
            ("RelativeLocation", a[4].clone()),
            ("RelativeRotation", "0,0,0".into()),
            ("RelativeScale3D", format!("{scale},{scale},{scale}")),
            ("bVisible", main.to_string()),
            ("BodyInstance.CollisionEnabled", "NoCollision".into()),
        ] {
            edit::set(&usmap, &e.class, &mut pkg.names, &mut e.block, p, &v).map_err(fail)?;
        }
        edit::write_export(&mut pkg, &usmap, &e).map_err(fail)?;
        if main {
            main_index = Some(i);
        }
    }
    let main = main_index.ok_or("no main mesh component")?;
    // Preserve the donor's dependency ordering and append the new references
    // to the main component's serialize-before-serialize group.
    let old_entries = pkg.dependency_bundle_entries.clone();
    let mut entries = Vec::new();
    for (i, h) in pkg.dependency_bundle_headers.iter_mut().enumerate() {
        let start = h.first_entry_index as usize;
        let count: usize = h.counts.iter().map(|x| *x as usize).sum();
        h.first_entry_index = entries.len() as i32;
        entries.extend_from_slice(
            old_entries
                .get(start..start + count)
                .ok_or("invalid dependency range")?,
        );
        if i == main {
            entries.push(mesh);
            entries.extend_from_slice(&materials);
            h.counts[3] += 1 + materials.len() as u32;
        }
    }
    pkg.dependency_bundle_entries = entries;
    // Names, imports and dependencies change the Zen header's length. Keep
    // its distance from CookedHeaderSize, as mesh_rewrite does for renamed
    // meshes; ZenPackage::write deliberately preserves this field verbatim.
    let once = pkg.write();
    let new_header = u32::from_le_bytes(once[4..8].try_into()?);
    pkg.cooked_header_size = u32::try_from(
        i64::from(pkg.cooked_header_size) + i64::from(new_header) - i64::from(old_header),
    )
    .map_err(|_| fail("actor cooked header size overflow"))?;
    let out = pkg.write();
    let reread = ZenPackage::parse(&out)?;
    if reread.name() != a[1]
        || reread.export_map[0].public_export_hash != public_export_hash(&format!("{new_leaf}_C"))
    {
        return Err(fail("actor readback did not preserve its identity"));
    }
    std::fs::write(&a[3], out)?;
    println!(
        "header {old_header} -> {new_header}; cooked header {}",
        reread.cooked_header_size
    );
    println!(
        "{}: cloned synchronized actor, one visual component, simulation collision",
        a[1]
    );
    Ok(())
}
