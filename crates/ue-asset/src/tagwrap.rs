//! A tag wrapper for any group, built from what an author knows.
//!
//! [`crate::package::ZenPackage::bare_tag`] covers the groups whose wrapper
//! class adds nothing. The other 54 groups bind the tag to Unreal: an
//! `AssetReference` (the actor Blueprint class, or a sound / cinematic /
//! damage-response asset), the `CookedAssetsReferencedByTag` preload list
//! (the tag's own references, as packages), a `model`'s region string table
//! and `RuntimeVariants`, an `effect`'s `bSpawnPerInstance`. Given those as a
//! [`WrapperSpec`], this builds the package: import map, imported public
//! export hashes, imported package names, name map, dependency bundle and the
//! export body — every derivation the shipped wrappers follow, checked over
//! the corpus by `mjolnir zen-roundtrip` (the *semantic* gate, since the
//! cooker's import slot order is not reproducible and need not be).

use std::collections::BTreeMap;

use crate::package::{
    bare_cooked_header_size, public_export_hash, script_import_index, utf16_lower_hash,
    wrapper_class, BulkEntry, DependencyBundleHeader, ExportEntry, NameBatch, ZenPackage,
    BLAM_MODULE, BULK_FLAGS, GENERATED_GROUPS, OBJECT_FLAGS, OBJECT_FLAGS_GENERATED, PACKAGE_FLAGS,
    PACKAGE_FLAGS_GENERATED,
};
use crate::props::{self, Block, Name, Val};
use crate::usmap::Usmap;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("{class} has no property named {prop}")]
    NoProperty { class: String, prop: &'static str },
    #[error(transparent)]
    Props(#[from] props::Error),
}

/// An object in another package, as the import map needs it: the package
/// name and the hash of the object's name.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ImportTarget {
    pub package: String,
    pub object_hash: u64,
}

impl ImportTarget {
    /// A Blueprint's generated class: `/Game/.../BP_X` → object `BP_X_C`.
    /// What `TSubclassOf` properties (the object groups and `effect`) point at.
    pub fn blueprint_class(package: &str) -> ImportTarget {
        let leaf = package.rsplit('/').next().unwrap_or(package);
        ImportTarget {
            package: package.to_string(),
            object_hash: utf16_lower_hash(&format!("{leaf}_C")),
        }
    }

    /// A plain asset whose object is named after its package leaf: another
    /// tag, a sound asset, a data asset.
    pub fn asset(package: &str) -> ImportTarget {
        let leaf = package.rsplit('/').next().unwrap_or(package);
        ImportTarget {
            package: package.to_string(),
            object_hash: utf16_lower_hash(leaf),
        }
    }
}

/// What an author decides about a tag's wrapper; everything else derives.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct WrapperSpec {
    pub group: String,
    /// `/Game/Tags/<path>-<group>`.
    pub package_path: String,
    pub ubulk_len: u64,
    /// The Unreal asset the tag is bound to, for the 22 groups that have one.
    pub asset_reference: Option<ImportTarget>,
    /// The tags this one references, as packages — the loader's preload list.
    pub cooked_refs: Vec<ImportTarget>,
    /// `effect` only.
    pub spawn_per_instance: bool,
    /// `model` only.
    pub model_region_string_table: Option<ImportTarget>,
    /// `model` only: `(variant name, [(region, permutation)])`.
    pub runtime_variants: Vec<(String, Vec<(String, String)>)>,
}

/// UE's FName split: a trailing `_<digits>` with no leading zero (a lone `0`
/// counts) that fits an `i32` becomes the number plus one. `hood_10` is
/// (`hood`, 11); `default_0` is (`default`, 1); `x_007` stays whole.
pub fn fname_split(name: &str) -> (&str, u32) {
    if let Some((base, digits)) = name.rsplit_once('_') {
        let ok = !digits.is_empty()
            && digits.len() <= 10
            && digits.bytes().all(|b| b.is_ascii_digit())
            && (digits == "0" || !digits.starts_with('0'))
            && !base.is_empty();
        if ok {
            if let Ok(n) = digits.parse::<u32>() {
                if n < i32::MAX as u32 {
                    return (base, n + 1);
                }
            }
        }
    }
    (name, 0)
}

/// The inverse of [`fname_split`].
pub fn fname_join(base: &str, number: u32) -> String {
    if number == 0 {
        base.to_string()
    } else {
        format!("{base}_{}", number - 1)
    }
}

/// The slot of a property in a class's flattened schema, by name.
fn slot_of(usmap: &Usmap, class: &str, prop: &'static str) -> Result<u16, Error> {
    (0..usmap.total_slots(class))
        .find(|s| {
            usmap
                .resolve(class, *s)
                .is_some_and(|(_, p)| p.name == prop)
        })
        .ok_or_else(|| Error::NoProperty {
            class: class.to_string(),
            prop,
        })
}

/// The class whose schema a group's wrapper is decoded with: the group's own
/// wrapper class, or the base when the usmap does not describe it
/// (`BlamFrameEventListTagDataAsset` is an editor-only class the cooked
/// reflection data omits; its 130 tags carry no properties).
pub fn schema_class(usmap: &Usmap, group: &str) -> String {
    let class = wrapper_class(group);
    if usmap.structs.contains_key(&class) {
        class
    } else {
        "BlamTagDataAssetBase".to_string()
    }
}

/// Build the wrapper.
pub fn build(spec: &WrapperSpec, usmap: &Usmap) -> Result<ZenPackage, Error> {
    let object_name = spec
        .package_path
        .rsplit('/')
        .next()
        .unwrap_or(&spec.package_path)
        .to_string();
    let class = wrapper_class(&spec.group);
    let schema = schema_class(usmap, &spec.group);
    let generated = GENERATED_GROUPS.contains(&spec.group.as_str());

    // --- imports: packages sorted by id, one Null slot each, then one slot per
    // object; the imported public export hashes in slot order.
    let mut targets: Vec<&ImportTarget> = Vec::new();
    if let Some(t) = &spec.asset_reference {
        targets.push(t);
    }
    targets.extend(spec.cooked_refs.iter());
    if let Some(t) = &spec.model_region_string_table {
        targets.push(t);
    }
    let mut packages: Vec<String> = targets.iter().map(|t| t.package.clone()).collect();
    packages.sort_by_key(|p| ue_iostore::city::package_id(p));
    packages.dedup();

    let cdo = script_import_index(&format!("{BLAM_MODULE}.Default__{class}"));
    let class_index = script_import_index(&format!("{BLAM_MODULE}.{class}"));
    let module = script_import_index(BLAM_MODULE);
    let mut import_map = vec![cdo, class_index, module];
    let mut ipeh: Vec<u64> = Vec::new();
    // target -> FPackageIndex
    let mut index_of: BTreeMap<ImportTarget, i32> = BTreeMap::new();
    for (pkg_index, package) in packages.iter().enumerate() {
        import_map.push(u64::MAX);
        for t in targets.iter().filter(|t| &t.package == package) {
            if index_of.contains_key(*t) {
                continue;
            }
            let hash_index = ipeh.len() as u64;
            ipeh.push(t.object_hash);
            import_map.push((2u64 << 62) | ((pkg_index as u64) << 32) | hash_index);
            index_of.insert((*t).clone(), -(import_map.len() as i32));
        }
    }

    // --- names: the FName values the properties carry, sorted, then object
    // and package. Numbers fold into (base, n + 1).
    let mut fname_bases: Vec<String> = Vec::new();
    for (variant, perms) in &spec.runtime_variants {
        fname_bases.push(fname_split(variant).0.to_string());
        for (region, perm) in perms {
            fname_bases.push(fname_split(region).0.to_string());
            fname_bases.push(fname_split(perm).0.to_string());
        }
    }
    // Distinct display strings (`None` and `none` are two entries), `None`
    // first when present — it is NAME_None, FName index 0 — then the rest in
    // case-insensitive order, ties broken by byte order.
    fname_bases.sort();
    fname_bases.dedup();
    let has_none = fname_bases.iter().any(|n| n == "None");
    fname_bases.retain(|n| n != "None");
    fname_bases.sort_by(|a, b| {
        a.to_lowercase()
            .cmp(&b.to_lowercase())
            .then_with(|| a.cmp(b))
    });
    if has_none {
        fname_bases.insert(0, "None".to_string());
    }
    let mut names = NameBatch::from_names(fname_bases);
    let object_index = names.intern(&object_name);
    let package_index = names.intern(&spec.package_path);
    let fname = |names: &NameBatch, s: &str| -> Name {
        let (base, number) = fname_split(s);
        let index = names
            .names
            .iter()
            .position(|n| n == base)
            .expect("every FName base was interned") as u32;
        Name { index, number }
    };

    // --- the body.
    let mut block = Block::default();
    if let Some(t) = &spec.asset_reference {
        block.set(
            slot_of(usmap, &schema, "AssetReference")?,
            Val::Object(index_of[t]),
        );
    }
    if spec.spawn_per_instance {
        block.set(
            slot_of(usmap, &schema, "bSpawnPerInstance")?,
            Val::Bool(true),
        );
    }
    if !spec.cooked_refs.is_empty() {
        block.set(
            slot_of(usmap, &schema, "CookedAssetsReferencedByTag")?,
            Val::Array(
                spec.cooked_refs
                    .iter()
                    .map(|t| Val::Object(index_of[t]))
                    .collect(),
            ),
        );
    }
    if let Some(t) = &spec.model_region_string_table {
        block.set(
            slot_of(usmap, &schema, "ModelRegionStringTable")?,
            Val::Object(index_of[t]),
        );
    }
    if !spec.runtime_variants.is_empty() {
        let variants = spec
            .runtime_variants
            .iter()
            .map(|(variant, perms)| {
                let mut v = Block::default();
                v.set(0, Val::Name(fname(&names, variant)));
                v.set(
                    1,
                    Val::Map(
                        perms
                            .iter()
                            .map(|(r, p)| {
                                (Val::Name(fname(&names, r)), Val::Name(fname(&names, p)))
                            })
                            .collect(),
                    ),
                );
                Val::Struct(v)
            })
            .collect();
        block.set(
            slot_of(usmap, &schema, "RuntimeVariants")?,
            Val::Array(variants),
        );
    }
    let export_data = props::encode_tag_body(usmap, &schema, &block)?;

    // --- dependency bundle: every object the properties reference, base-class
    // properties first (the reverse of schema order), each array in order.
    let mut dependency_bundle_entries: Vec<i32> = Vec::new();
    for (_, value) in block.values.iter().rev() {
        let mut one = Block::default();
        one.set(0, value.clone());
        dependency_bundle_entries.extend(one.object_refs());
    }

    // --- imported package names, with their FName numbers.
    let mut imported_package_names = NameBatch::default();
    let mut imported_package_name_numbers = Vec::new();
    for p in &packages {
        let (base, number) = fname_split(p);
        imported_package_names.intern(base);
        imported_package_name_numbers.push(number);
    }
    if !packages.is_empty() {
        imported_package_names.hash_version = crate::package::NAME_HASH_VERSION;
    }

    let pad_len = (8 - (crate::package::SUMMARY + names.serialized_len() + 8) % 8) % 8;

    Ok(ZenPackage {
        has_versioning_info: 0,
        name_index: package_index,
        name_number: 0,
        package_flags: if generated {
            PACKAGE_FLAGS_GENERATED
        } else {
            PACKAGE_FLAGS
        },
        cooked_header_size: bare_cooked_header_size(&spec.package_path, &object_name, &class),
        names,
        pad: vec![0; pad_len],
        bulk: vec![BulkEntry {
            serial_offset: 0,
            duplicate_serial_offset: -1,
            serial_size: spec.ubulk_len as i64,
            flags: BULK_FLAGS,
            cooked_index: 0,
        }],
        imported_public_export_hashes: ipeh,
        import_map,
        export_map: vec![ExportEntry {
            cooked_serial_offset: 0,
            cooked_serial_size: export_data.len() as u64,
            name_index: object_index,
            name_number: 0,
            outer: u64::MAX,
            class: class_index,
            super_: u64::MAX,
            template: cdo,
            public_export_hash: public_export_hash(&object_name),
            object_flags: if generated {
                OBJECT_FLAGS_GENERATED
            } else {
                OBJECT_FLAGS
            },
            filter_flags: 0,
        }],
        export_bundle_entries: vec![(0, 0), (0, 1)],
        dependency_bundle_headers: vec![DependencyBundleHeader {
            first_entry_index: 0,
            counts: [0, 0, dependency_bundle_entries.len() as u32, 0],
        }],
        dependency_bundle_entries,
        imported_package_names,
        imported_package_name_numbers,
        export_data,
        trailer: true,
    })
}

/// What a shipped wrapper says, in the terms of a [`WrapperSpec`] — read back
/// out of the package so a rebuild can be compared with it.
#[derive(Debug, Clone, PartialEq)]
pub struct Reading {
    pub spec: WrapperSpec,
    /// The body's object references resolved to targets, in dependency-bundle
    /// order, exactly as the shipped bundle lists them.
    pub dependencies: Vec<ImportTarget>,
    /// The name map's FName strings other than object and package.
    pub fnames: Vec<String>,
}

/// Resolve an `FPackageIndex` in `pkg` to the import it names.
pub fn resolve_import(pkg: &ZenPackage, index: i32) -> Option<ImportTarget> {
    if index >= 0 {
        return None;
    }
    let slot = (-index - 1) as usize;
    let raw = *pkg.import_map.get(slot)?;
    if raw >> 62 != 2 {
        return None;
    }
    let pkg_index = ((raw >> 32) & 0x3FFF_FFFF) as usize;
    let hash_index = (raw & 0xFFFF_FFFF) as usize;
    let base = pkg.imported_package_names.names.get(pkg_index)?;
    let number = pkg
        .imported_package_name_numbers
        .get(pkg_index)
        .copied()
        .unwrap_or(0);
    Some(ImportTarget {
        package: fname_join(base, number),
        object_hash: *pkg.imported_public_export_hashes.get(hash_index)?,
    })
}

/// Read a shipped wrapper back into a spec.
pub fn read(pkg: &ZenPackage, usmap: &Usmap) -> Result<Reading, Error> {
    let name = pkg.name();
    let leaf = name.rsplit('/').next().unwrap_or("");
    let group = leaf
        .rsplit_once('-')
        .map(|(_, g)| g)
        .unwrap_or("")
        .to_string();
    let schema = schema_class(usmap, &group);
    let block = props::decode_tag_body(usmap, &schema, &pkg.export_data)?;
    let name_of = |n: Name| -> String {
        let base = pkg
            .names
            .names
            .get((n.index & ((1 << 30) - 1)) as usize)
            .cloned()
            .unwrap_or_default();
        fname_join(&base, n.number)
    };
    let mut spec = WrapperSpec {
        group: group.clone(),
        package_path: name.clone(),
        ubulk_len: pkg.bulk.first().map(|b| b.serial_size as u64).unwrap_or(0),
        ..Default::default()
    };
    let target = |v: &Val| match v {
        Val::Object(i) => resolve_import(pkg, *i),
        _ => None,
    };
    for (slot, value) in &block.values {
        let prop = usmap
            .resolve(&schema, *slot)
            .map(|(_, p)| p.name.clone())
            .unwrap_or_default();
        match (prop.as_str(), value) {
            ("AssetReference", v) => spec.asset_reference = target(v),
            ("ModelRegionStringTable", v) => spec.model_region_string_table = target(v),
            ("bSpawnPerInstance", Val::Bool(b)) => spec.spawn_per_instance = *b,
            ("CookedAssetsReferencedByTag", Val::Array(items)) => {
                spec.cooked_refs = items.iter().filter_map(target).collect();
            }
            ("RuntimeVariants", Val::Array(items)) => {
                for item in items {
                    if let Val::Struct(v) = item {
                        let variant = match v.get(0) {
                            Some(Val::Name(n)) => name_of(*n),
                            _ => String::new(),
                        };
                        let perms = match v.get(1) {
                            Some(Val::Map(pairs)) => pairs
                                .iter()
                                .map(|(k, v)| match (k, v) {
                                    (Val::Name(k), Val::Name(v)) => (name_of(*k), name_of(*v)),
                                    _ => (String::new(), String::new()),
                                })
                                .collect(),
                            _ => Vec::new(),
                        };
                        spec.runtime_variants.push((variant, perms));
                    }
                }
            }
            _ => {}
        }
    }
    let dependencies = pkg
        .dependency_bundle_entries
        .iter()
        .filter_map(|i| resolve_import(pkg, *i))
        .collect();
    let n = pkg.names.names.len();
    let fnames = pkg.names.names[..n.saturating_sub(2)].to_vec();
    Ok(Reading {
        spec,
        dependencies,
        fnames,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fname_numbers_split_the_way_the_engine_does() {
        assert_eq!(fname_split("wraith_hood_10"), ("wraith_hood", 11));
        assert_eq!(fname_split("default_0"), ("default", 1));
        assert_eq!(fname_split("x_007"), ("x_007", 0));
        assert_eq!(
            fname_split("marine-collision_model"),
            ("marine-collision_model", 0)
        );
        assert_eq!(fname_split("_5"), ("_5", 0));
        assert_eq!(fname_join("wraith_hood", 11), "wraith_hood_10");
    }

    #[test]
    fn blueprint_and_asset_targets_hash_the_right_leaf() {
        let bp = ImportTarget::blueprint_class("/Game/Blueprints/FX/BP_CharacterCollisionEffect");
        assert_eq!(
            bp.object_hash,
            utf16_lower_hash("BP_CharacterCollisionEffect_C")
        );
        let tag = ImportTarget::asset("/Game/Tags/globals/globals-globals");
        assert_eq!(tag.object_hash, public_export_hash("globals-globals"));
    }
}
