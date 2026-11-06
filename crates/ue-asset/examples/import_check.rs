//! Resolve every import of a set of new containers against the game and each
//! other, by package id, so a container's mount point cannot hide a package.
//!
//! import_check <Paks dir> <new containers dir>
//!
//! Every package in the second folder is checked: each script import must be a
//! game script object, and each package import must reach a package that exports
//! the imported hash. The new folder wins over the game, as a mod does. Prints
//! each package's imported packages and where they came from, and exits non-zero
//! if anything is unresolved or a new package hides a shipped one.
use std::collections::{BTreeMap, HashMap};
use std::error::Error;
use ue_asset::package::ZenPackage;
use ue_asset::zen::{ObjectIndex, ScriptObjects};
use ue_iostore::Container;

const IMPORT_SCRIPT: u64 = 1;
const IMPORT_PACKAGE: u64 = 2;

type Found = (usize, usize);

fn packages(containers: &[Container], into: &mut HashMap<u64, Found>) -> Vec<u64> {
    let mut ids = Vec::new();
    for (ci, c) in containers.iter().enumerate() {
        for (i, chunk) in c.chunks.iter().enumerate() {
            if chunk.type_name() == "ExportBundleData" {
                into.insert(chunk.chunk_id, (ci, i));
                ids.push(chunk.chunk_id);
            }
        }
    }
    ids
}

fn main() -> Result<(), Box<dyn Error>> {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let [paks, new] = a.as_slice() else {
        return Err("import_check <Paks dir> <new containers dir>".into());
    };
    let game = ue_iostore::load_all(paks)?;
    let added = ue_iostore::load_all(new)?;
    let global = game
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .ok_or("no global container")?;
    let table = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .ok_or("no script objects")?;
    let scripts = ScriptObjects::parse(&ue_iostore::read_chunk(global, table, None, &[])?)?;

    let mut shipped = HashMap::new();
    packages(&game, &mut shipped);
    let mut own = HashMap::new();
    let ids = packages(&added, &mut own);
    let read = |id: u64| -> Result<Option<(Vec<u8>, String)>, Box<dyn Error>> {
        let (set, found) = match own.get(&id) {
            Some(f) => (&added, f),
            None => match shipped.get(&id) {
                Some(f) => (&game, f),
                None => return Ok(None),
            },
        };
        let c = &set[found.0];
        let from = c
            .utoc_path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        Ok(Some((
            ue_iostore::read_chunk(c, &c.chunks[found.1], None, &[])?,
            from,
        )))
    };

    let mut bad = 0;
    for id in ids {
        let (data, from) = read(id)?.ok_or("a listed package went missing")?;
        let p = ZenPackage::parse(&data)?;
        if shipped.contains_key(&id) {
            println!("HIDES a shipped package: {}", p.name());
            bad += 1;
        }
        let (mut script_ok, mut package_ok) = (0, 0);
        let mut sources: BTreeMap<String, String> = BTreeMap::new();
        for (i, entry) in p.import_map.iter().enumerate() {
            match entry >> 62 {
                IMPORT_SCRIPT if scripts.leaf(ObjectIndex(*entry)).is_some() => script_ok += 1,
                IMPORT_SCRIPT => {
                    println!(
                        "  {}: import {i}: script object {entry:#x} is not in the game",
                        p.name()
                    );
                    bad += 1;
                }
                IMPORT_PACKAGE => {
                    let at = ((entry >> 32) & 0x3fff_ffff) as usize;
                    let hash = p.imported_public_export_hashes[(entry & 0xffff_ffff) as usize];
                    let target = &p.imported_package_names.names[at];
                    let Some((bytes, source)) = read(ue_iostore::city::package_id(target))? else {
                        println!("  {}: import {i}: no package {target}", p.name());
                        bad += 1;
                        continue;
                    };
                    let imported = ZenPackage::parse(&bytes)?;
                    if imported
                        .export_map
                        .iter()
                        .any(|e| e.public_export_hash == hash)
                    {
                        package_ok += 1;
                        sources.insert(target.clone(), source);
                    } else {
                        println!(
                            "  {}: import {i}: {target} has no public export {hash:#x}",
                            p.name()
                        );
                        bad += 1;
                    }
                }
                _ => {}
            }
        }
        for (i, e) in p.export_map.iter().enumerate() {
            for (what, v) in [
                ("class", e.class),
                ("super", e.super_),
                ("template", e.template),
            ] {
                if v >> 62 == IMPORT_SCRIPT && scripts.leaf(ObjectIndex(v)).is_none() {
                    println!(
                        "  {}: export {i}: {what} {v:#x} is not a game script object",
                        p.name()
                    );
                    bad += 1;
                }
            }
        }
        println!(
            "{} [{from}]: {script_ok} script, {package_ok} package imports",
            p.name()
        );
        for (target, source) in &sources {
            println!("    {target} [{source}]");
        }
    }
    println!("{bad} unresolved");
    if bad > 0 {
        return Err("unresolved imports".into());
    }
    Ok(())
}
