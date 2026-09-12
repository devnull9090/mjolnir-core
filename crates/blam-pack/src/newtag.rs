//! Building a brand-new tag package from a body and a donor's wrapper.
//!
//! A tag is one UE package — a cooked `.uasset` wrapper plus the `.ubulk` tag
//! body — and its identity (the chunk ids the game addresses it by, the
//! package-store entry, the export hash) all derive from its name. The wrapper
//! is built from scratch for every group (`ue_asset::tagwrap`): its preload
//! list from the references the body actually carries, its Unreal binding
//! (`AssetReference`) and its model variants from the donor's wrapper unless
//! overridden. So the new path can be anything, and the body can be edited on
//! the way.
//!
//! This is the one implementation shared by `mjolnir new-tag` and the tag
//! editor's New Tag command. Measured 2026-09-05: a package built this way is
//! registered by the mod container's own `ContainerHeader`, resolved by name
//! the moment a tag references it, and loaded.

use ue_asset::package::ZenPackage;
use ue_asset::tagwrap::{self, ImportTarget};
use ue_asset::Usmap;
use ue_iostore::toc::Toc;
use ue_iostore::Container;

use crate::NewPackage;

/// Groups whose `AssetReference` names a plain asset rather than a Blueprint
/// class.
pub const ASSET_BOUND_GROUPS: [&str; 5] = [
    "sound",
    "sound_looping",
    "sound_combiner",
    "cinematic",
    "damage_response_definition",
];

/// Everything a new tag needs from outside its own bytes.
pub struct NewTag<'a> {
    /// Group directory name, e.g. `collision_model`.
    pub group: &'a str,
    /// The new tag's path without group or extension, slashes either way —
    /// see [`normalize_path`].
    pub path: &'a str,
    /// The tag body, already edited.
    pub body: &'a [u8],
    /// The donor's cooked wrapper: the Unreal-side facts a body cannot tell.
    pub donor_uasset: &'a [u8],
    /// Package path of the Unreal asset to bind to (`/Game/Blueprints/.../
    /// BP_Thing`); `None` keeps the donor's. Object groups and `effect` bind to
    /// the Blueprint's class, sound-like groups to the asset itself.
    pub asset_reference: Option<&'a str>,
}

/// What building a new tag produced, and what it learned on the way.
pub struct BuiltTag {
    /// The package, minus the chunk meta records a container needs — see
    /// [`donor_chunk_meta`].
    pub package: NewPackage,
    /// `/Game/Tags/<path>-<group>`.
    pub package_name: String,
    /// The package's leaf, `<name>-<group>`.
    pub leaf: String,
    /// Tags the body references that exist in this installation.
    pub preloads: usize,
    /// References the body carries that point at nothing shipped. Ordinary:
    /// 1,381 shipped instances do.
    pub dangling: usize,
    /// The Unreal package the tag was bound to, when its group has a binding.
    pub bound: Option<String>,
    /// Model variants carried over from the donor.
    pub variants: usize,
}

/// Bring a user-typed tag path to the cooker's spelling: forward slashes, no
/// leading or trailing slash, no empty segments.
///
/// The leaf may not contain `-`, because the package name is `<leaf>-<group>`
/// and the group is split off at the last hyphen; a `.` would read as an
/// extension. Anything outside printable ASCII is refused too — the string
/// becomes a file name in the container's directory index.
pub fn normalize_path(path: &str) -> Result<String, String> {
    let joined = path.trim().replace('\\', "/");
    let segments: Vec<&str> = joined
        .split('/')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .collect();
    if segments.is_empty() {
        return Err("a tag path is needed, e.g. objects/weapons/pistol/pistol_mk2".into());
    }
    for s in &segments {
        if *s == ".." || *s == "." {
            return Err(format!("{s:?} is not a tag path segment"));
        }
        if let Some(bad) = s
            .chars()
            .find(|c| !c.is_ascii_graphic() && *c != ' ' || matches!(c, '-' | '.' | ':' | '"'))
        {
            return Err(format!(
                "{bad:?} cannot appear in a tag path; use letters, digits, `_` and `/`"
            ));
        }
    }
    Ok(segments.join("/"))
}

/// `/Game/Tags/<path>-<group>` for a normalized path.
pub fn package_name(group: &str, normalized_path: &str) -> String {
    format!("/Game/Tags/{normalized_path}-{group}")
}

/// Build the package for a new tag.
///
/// `resolve` turns one body reference — a group four-CC and the backslash
/// path the body carries — into the package name of the tag it points at in
/// this installation (`/Game/Tags/.../marine-collision_model`), or `None`
/// when nothing shipped answers. Those become the loader's preload list.
pub fn build(
    tag: &NewTag,
    usmap: &Usmap,
    resolve: impl Fn(&str, &str) -> Option<String>,
) -> Result<BuiltTag, String> {
    let path = normalize_path(tag.path)?;
    let package_name = package_name(tag.group, &path);
    let leaf = package_name.rsplit('/').next().unwrap_or("").to_string();

    let donor_pkg =
        ZenPackage::parse(tag.donor_uasset).map_err(|e| format!("donor package: {e}"))?;
    let donor = tagwrap::read(&donor_pkg, usmap).map_err(|e| format!("donor wrapper: {e}"))?;

    let mut cooked_refs: Vec<ImportTarget> = Vec::new();
    let mut dangling = 0usize;
    for (cc, ref_path) in blam_tag::refs::tgrf_refs(tag.body, |_| true) {
        match resolve(&cc, &ref_path) {
            Some(real) => {
                let target = ImportTarget::asset(&real);
                if !cooked_refs.contains(&target) {
                    cooked_refs.push(target);
                }
            }
            None => dangling += 1,
        }
    }

    let asset_reference = match tag.asset_reference.map(str::trim).filter(|s| !s.is_empty()) {
        Some(pkg) if ASSET_BOUND_GROUPS.contains(&tag.group) => Some(ImportTarget::asset(pkg)),
        Some(pkg) => Some(ImportTarget::blueprint_class(pkg)),
        None => donor.spec.asset_reference.clone(),
    };
    let spec = tagwrap::WrapperSpec {
        group: tag.group.to_string(),
        package_path: package_name.clone(),
        ubulk_len: tag.body.len() as u64,
        asset_reference,
        cooked_refs,
        spawn_per_instance: donor.spec.spawn_per_instance,
        model_region_string_table: donor.spec.model_region_string_table.clone(),
        runtime_variants: donor.spec.runtime_variants.clone(),
    };
    let built = tagwrap::build(&spec, usmap).map_err(|e| format!("wrapper: {e}"))?;
    let imported_package_ids: Vec<u64> = built
        .imported_package_names
        .names
        .iter()
        .zip(&built.imported_package_name_numbers)
        .map(|(base, n)| ue_iostore::city::package_id(&tagwrap::fname_join(base, *n)))
        .collect();

    Ok(BuiltTag {
        package: NewPackage {
            package_name: package_name.clone(),
            uasset: built.write(),
            ubulk: tag.body.to_vec(),
            imported_package_ids,
            uasset_meta: Vec::new(),
            ubulk_meta: Vec::new(),
        },
        package_name,
        leaf,
        preloads: spec.cooked_refs.len(),
        dangling,
        bound: spec.asset_reference.as_ref().map(|t| t.package.clone()),
        variants: spec.runtime_variants.len(),
    })
}

/// The chunk meta records of a donor's package and bulk chunks, read from its
/// container's index, for a new package to carry.
pub fn donor_chunk_meta(source: &Container, chunk_id: u64) -> Result<(Vec<u8>, Vec<u8>), String> {
    let toc =
        Toc::read(&source.utoc_path).map_err(|e| format!("{}: {e}", source.utoc_path.display()))?;
    let meta_of = |kind: u8| -> Vec<u8> {
        toc.chunk_ids
            .iter()
            .position(|c| c.id == chunk_id && c.kind == kind)
            .and_then(|slot| toc.meta(slot))
            .map(<[u8]>::to_vec)
            .unwrap_or_default()
    };
    Ok((meta_of(1), meta_of(2)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn paths_are_normalized_to_the_cookers_spelling() {
        assert_eq!(
            normalize_path("objects\\weapons\\pistol\\pistol_mk2").unwrap(),
            "objects/weapons/pistol/pistol_mk2"
        );
        assert_eq!(normalize_path(" /a//b/ ").unwrap(), "a/b");
        assert_eq!(
            package_name("weapon", "objects/weapons/pistol/pistol_mk2"),
            "/Game/Tags/objects/weapons/pistol/pistol_mk2-weapon"
        );
    }

    #[test]
    fn hyphens_dots_and_traversal_are_refused() {
        assert!(normalize_path("").is_err());
        assert!(normalize_path("a/b-c").is_err());
        assert!(normalize_path("a/b.weapon").is_err());
        assert!(normalize_path("a/../b").is_err());
        assert!(normalize_path("a/\u{e9}").is_err());
    }
}
