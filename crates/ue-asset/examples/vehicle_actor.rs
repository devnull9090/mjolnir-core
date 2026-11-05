//! Clone a shipped synchronized vehicle or weapon actor under a new package
//! path, so a custom object can wear its own parts while the stock one stays
//! stock. The clone keeps the donor's Blueprint code and native Blam bindings.
//! vehicle_actor <paks> <donor leaf> <new /Game/MJOLNIR/Vehicles/... path>
//!               <out.uasset> [<export name or index>|<field>|<value> ...]
//! A value of `@len=N` resizes the array at `field`. A long list goes in a
//! file, one edit a line, as `@file`.
use std::error::Error;
use ue_asset::{
    edit,
    package::{public_export_hash, NameBatch, ZenPackage},
};

fn fail(s: impl Into<String>) -> Box<dyn Error> {
    s.into().into()
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
    if a.len() < 4 {
        return Err(fail(
            "vehicle_actor <paks> <donor leaf> <new path> <out> [export|field|value ...]",
        ));
    }
    let new_path = &a[2];
    let new_leaf = new_path.rsplit('/').next().ok_or("new actor leaf")?;
    if !new_path.starts_with("/Game/MJOLNIR/Vehicles/") || !new_leaf.starts_with("BP_") {
        return Err(fail("use a /Game/MJOLNIR/Vehicles/.../BP_* path"));
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
    let suffix = format!("/{}.uasset", a[1]);
    let (container, ci) = containers
        .iter()
        .find_map(|c| {
            c.files
                .iter()
                .find(|(p, _)| p.ends_with(&suffix))
                .map(|(_, i)| (c, *i))
        })
        .ok_or("donor actor not found")?;
    let data = ue_iostore::read_chunk(container, &container.chunks[ci], None, &[])?;
    let old_header = u32::from_le_bytes(data[4..8].try_into()?);
    let mut pkg = ZenPackage::parse(&data)?;
    let old_path = pkg.name();
    let old_leaf = old_path.rsplit('/').next().ok_or("actor leaf")?.to_string();
    // The package, its generated class and that class's default object.
    // Nested public hashes follow from their outer paths.
    pkg.names = NameBatch::from_names(
        pkg.names
            .names
            .iter()
            .map(|n| {
                if n == &old_path {
                    new_path.clone()
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
    let mut edits = Vec::new();
    for arg in &a[4..] {
        match arg.strip_prefix('@') {
            Some(file) => edits.extend(std::fs::read_to_string(file)?.lines().map(String::from)),
            None => edits.push(arg.clone()),
        }
    }
    for edit_arg in edits.iter().filter(|l| !l.trim().is_empty()) {
        let mut parts = edit_arg.splitn(3, '|');
        let (which, field, value) = (
            parts.next().ok_or("export")?,
            parts.next().ok_or("field")?,
            parts.next().ok_or("value")?,
        );
        let index = match which.parse::<usize>() {
            Ok(i) => i,
            Err(_) => (0..pkg.export_map.len())
                .find(|i| {
                    let e = &pkg.export_map[*i];
                    pkg.mapped_name(e.name_index, e.name_number) == which
                })
                .ok_or_else(|| fail(format!("no export {which}")))?,
        };
        let mut e = edit::open_export(&pkg, &usmap, &scripts, index).map_err(fail)?;
        if let Some(len) = value.strip_prefix("@len=") {
            let names = pkg.names.names.clone();
            edit::resize(&usmap, &e.class, &names, &mut e.block, field, len.parse()?)
                .map_err(fail)?;
        } else {
            edit::set(&usmap, &e.class, &mut pkg.names, &mut e.block, field, value)
                .map_err(fail)?;
        }
        edit::write_export(&mut pkg, &usmap, &e).map_err(fail)?;
    }
    // New names change the Zen header's length; keep its distance from
    // CookedHeaderSize, which ZenPackage::write preserves verbatim.
    let once = pkg.write();
    let new_header = u32::from_le_bytes(once[4..8].try_into()?);
    pkg.cooked_header_size = u32::try_from(
        i64::from(pkg.cooked_header_size) + i64::from(new_header) - i64::from(old_header),
    )
    .map_err(|_| fail("actor cooked header size overflow"))?;
    let out = pkg.write();
    let reread = ZenPackage::parse(&out)?;
    if reread.name() != *new_path {
        return Err(fail("actor readback did not preserve its identity"));
    }
    std::fs::write(&a[3], out)?;
    println!("{new_path}: cloned {old_path}, {} edit(s)", edits.len());
    Ok(())
}
