//! Shader libraries are addressed by their numeric pak chunk, not their
//! pack slug. Two different filenames do not isolate the same number.
//!
//! The launcher gives each container it writes a local number
//! (`chunk_numbers`) and renames its library to match, so the numbers
//! checked here are the ones a container takes in Paks, not the ones it was
//! cooked under.
use std::fs;
use std::path::Path;

pub struct Planned<'a> {
    pub slug: &'a str,
    /// The container's name in the release cache.
    pub source: &'a str,
    /// Its name in Paks.
    pub target: &'a str,
    /// The chunk number its shader library opens under in Paks, when it has
    /// one.
    pub library: Option<u32>,
}

pub fn is_surface_container(stem: &str) -> bool {
    stem.to_ascii_lowercase().contains("-mjolnirforgemat-")
}

fn chunk(stem: &str) -> Option<u32> {
    let lower = stem.to_ascii_lowercase();
    let rest = lower.strip_prefix("pakchunk")?;
    let digits = rest.bytes().take_while(u8::is_ascii_digit).count();
    if digits == 0 {
        return None;
    }
    rest[..digits].parse().ok()
}

fn same_pack(stem: &str, planned: &Planned<'_>, number: u32) -> bool {
    if stem.eq_ignore_ascii_case(planned.source) || stem.eq_ignore_ascii_case(planned.target) {
        return true;
    }
    hub_copy_of(stem, planned.slug, number)
}

/// Whether `stem` is the launcher's copy of `slug` under chunk `number`.
/// The launcher's previous release may have a different container index, a
/// load-order suffix or a live-update suffix. Match the entire numeric tail,
/// so pack "foo" never owns "foo-extra" or a merely similar hand-installed
/// filename.
fn hub_copy_of(stem: &str, slug: &str, number: u32) -> bool {
    let lower = stem.to_ascii_lowercase();
    let prefix = format!("pakchunk{number}-mjolnirhub-{}-", slug.to_ascii_lowercase());
    lower
        .strip_prefix(&prefix)
        .and_then(|s| s.strip_suffix("_p"))
        .is_some_and(|tail| {
            tail.split('_')
                .all(|n| !n.is_empty() && n.bytes().all(|b| b.is_ascii_digit()))
        })
}

/// Read-only preflight. Offline materialization removes all MJOLNIRHUB files
/// before copying its complete plan; live mounts must also respect those
/// existing files. Unmanaged content is never ignored or deleted here.
pub fn check(
    paks: &Path,
    planned: &[Planned<'_>],
    replacing_hub_files: bool,
) -> Result<(), String> {
    let protected: Vec<_> = planned
        .iter()
        .filter(|m| is_surface_container(m.source))
        .collect();
    if protected.is_empty() {
        return Ok(()); // Ordinary packs retain their existing behavior.
    }
    for material in &protected {
        let number = material.library.ok_or_else(|| {
            format!("{} has a Forge material container without a readable shader library; reinstall a corrected release.", material.slug)
        })?;
        if chunk(material.target) != Some(number) {
            return Err(format!("{} must mount its material container as shader chunk {number}, not as {}.", material.slug, material.target));
        }
        for other in planned {
            if other.slug != material.slug && chunk(other.target) == Some(number) {
                return Err(format!("{} and {} both need shader chunk {number}. Disable one pack or install a release cooked with a different shader chunk.", material.slug, other.slug));
            }
        }
    }
    let mut existing = Vec::new();
    for entry in fs::read_dir(paks).map_err(|e| format!("Cannot check Forge shader chunks: {e}"))? {
        let entry = entry.map_err(|e| e.to_string())?;
        if !entry.path().is_file() {
            continue;
        }
        let name = entry.file_name().to_string_lossy().into_owned();
        let Some((stem, ext)) = name.rsplit_once('.') else {
            continue;
        };
        if !matches!(ext.to_ascii_lowercase().as_str(), "pak" | "utoc" | "ucas") {
            continue;
        }
        if replacing_hub_files && stem.contains("-MJOLNIRHUB-") {
            continue;
        }
        existing.push((stem.to_string(), name.clone()));
    }
    existing.sort();
    for material in protected {
        let number = material.library.expect("validated above");
        for (stem, name) in &existing {
            if chunk(stem) == Some(number) && !same_pack(stem, material, number) {
                return Err(format!("{} needs shader chunk {number}, already used by {name}. Remove or disable the conflicting pack, or use a release cooked with a different shader chunk. No game files were changed.", material.slug));
            }
        }
    }
    Ok(())
}

/// Whether chunk `number` is free in Paks for `slug`'s library: no container
/// there carries the number except the launcher's own copies of `slug`. Two
/// libraries under one number cannot both open, so a container written while
/// the game runs checks this first (a launch rewrites every hub container
/// and has nothing to check).
pub fn library_free(paks: &Path, slug: &str, number: u32) -> Result<(), String> {
    let mut taken = Vec::new();
    for entry in fs::read_dir(paks).map_err(|e| format!("Cannot check shader chunks: {e}"))? {
        let name = entry.map_err(|e| e.to_string())?.file_name().to_string_lossy().into_owned();
        let Some((stem, ext)) = name.rsplit_once('.') else { continue };
        if matches!(ext.to_ascii_lowercase().as_str(), "pak" | "utoc" | "ucas")
            && chunk(stem) == Some(number)
            && !hub_copy_of(stem, slug, number)
        {
            taken.push(name);
        }
    }
    taken.sort();
    match taken.first() {
        None => Ok(()),
        Some(name) => Err(format!("{slug} needs shader chunk {number}, already used by {name}.")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicUsize, Ordering};
    static NEXT: AtomicUsize = AtomicUsize::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let p = std::env::temp_dir().join(format!(
                "mjolnir-forge-shaders-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir_all(&p).unwrap();
            Self(p)
        }
        fn put(&self, name: &str) {
            fs::write(self.0.join(name), b"preserve unrelated bytes").unwrap();
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    /// A Forge material container cooked under 967, mounted under the local
    /// number the launcher gave it.
    fn material() -> Planned<'static> {
        Planned {
            slug: "foundry-wide",
            source: "pakchunk967-MJOLNIRFORGEMAT-foundry-wide_P",
            target: "pakchunk10026-MJOLNIRHUB-foundry-wide-0_1104_P",
            library: Some(10026),
        }
    }

    #[test]
    fn two_packs_cooked_under_one_number_install_side_by_side() {
        let f = Fixture::new();
        let other = Planned {
            slug: "other-kit",
            source: "pakchunk967-MJOLNIRFORGEMAT-other-kit_P",
            target: "pakchunk10140-MJOLNIRHUB-other-kit-0_1560_P",
            library: Some(10140),
        };
        check(&f.0, &[material(), other], true).unwrap();
    }

    #[test]
    fn two_slugs_in_one_pending_install_cannot_share_the_assigned_number() {
        let f = Fixture::new();
        let other = Planned {
            slug: "other-kit",
            source: "pakchunk967-MJOLNIRFORGEMAT-other-kit_P",
            target: "pakchunk10026-MJOLNIRHUB-other-kit-0_1560_P",
            library: Some(10026),
        };
        let error = check(&f.0, &[material(), other], true).unwrap_err();
        assert!(
            error.contains("foundry-wide") && error.contains("other-kit") && error.contains("10026")
        );
        assert_eq!(fs::read_dir(&f.0).unwrap().count(), 0);
    }

    #[test]
    fn existing_unrelated_content_blocks_each_sibling_and_is_untouched() {
        for ext in ["utoc", "ucas", "pak", "UTOC"] {
            let f = Fixture::new();
            let name = format!("pakchunk10026-OtherCommunityPack_P.{ext}");
            f.put(&name);
            let error = check(&f.0, &[material()], true).unwrap_err();
            assert!(error.contains(&name));
            assert_eq!(
                fs::read(f.0.join(name)).unwrap(),
                b"preserve unrelated bytes"
            );
        }
        // The number it was cooked under is no longer the one it opens under.
        let f = Fixture::new();
        f.put("pakchunk967-OtherCommunityPack_P.utoc");
        check(&f.0, &[material()], true).unwrap();
    }

    #[test]
    fn same_pack_updates_and_container_triples_are_allowed() {
        let f = Fixture::new();
        for stem in [
            material().source,
            material().target,
            "pakchunk10026-MJOLNIRHUB-foundry-wide-0_1105_P",
            "pakchunk10026-MJOLNIRHUB-foundry-wide-99_3_P",
        ] {
            for ext in ["utoc", "ucas", "pak"] {
                f.put(&format!("{stem}.{ext}"));
            }
        }
        check(&f.0, &[material()], false).unwrap();
        let ordinary = Planned {
            slug: "foundry-wide",
            source: "plain_visuals",
            target: "pakchunk10027-MJOLNIRHUB-foundry-wide-1_1108_P",
            library: None,
        };
        check(&f.0, &[material(), ordinary], true).unwrap();
    }

    #[test]
    fn similarly_named_pack_and_live_managed_content_still_conflict() {
        let f = Fixture::new();
        f.put("pakchunk10026-MJOLNIRHUB-foundry-wide-extra-0_1200_P.utoc");
        assert!(check(&f.0, &[material()], false).is_err());
        // Offline replacement deletes old managed files, but never exempts
        // the competing pack if it is also in the new plan.
        check(&f.0, &[material()], true).unwrap();
        let other = Planned {
            slug: "foundry-wide-extra",
            source: "ordinary",
            target: "pakchunk10026-MJOLNIRHUB-foundry-wide-extra-0_1200_P",
            library: None,
        };
        assert!(check(&f.0, &[material(), other], true).is_err());
    }

    #[test]
    fn distinct_chunks_ordinary_packs_and_noncontainer_files_remain_compatible() {
        let f = Fixture::new();
        for name in [
            "pakchunk10027-Other_P.utoc",
            "pakchunk10026-notes.txt",
            "notpakchunk10026-fake.utoc",
        ] {
            f.put(name);
        }
        check(&f.0, &[material()], false).unwrap();
        let other = Planned {
            slug: "other",
            source: "pakchunk967-MJOLNIRFORGEMAT-other_P",
            target: "pakchunk10027-MJOLNIRHUB-other-0_1108_P",
            library: Some(10027),
        };
        let clean = Fixture::new();
        check(&clean.0, &[material(), other], false).unwrap();
        let ordinary = Planned {
            slug: "legacy",
            source: "pakchunk967-legacy",
            target: "pakchunk10000-MJOLNIRHUB-legacy-0_1000_P",
            library: None,
        };
        check(
            Path::new("this-directory-need-not-exist"),
            &[ordinary],
            false,
        )
        .unwrap();
    }

    #[test]
    fn a_material_container_needs_its_library_under_its_mounted_number() {
        let f = Fixture::new();
        let bare = Planned {
            library: None,
            ..material()
        };
        assert!(check(&f.0, &[bare], false)
            .unwrap_err()
            .contains("without a readable shader library"));
        let wrong = Planned {
            target: "pakchunk10099-MJOLNIRHUB-foundry-wide-0_1104_P",
            ..material()
        };
        assert!(check(&f.0, &[wrong], false).unwrap_err().contains("10026"));
        f.put("PAKCHUNK010026-UNRELATED_P.UCAS");
        assert!(check(&f.0, &[material()], false).is_err());
        let bare = Fixture::new();
        bare.put("pakchunk10026.utoc");
        assert!(check(&bare.0, &[material()], false).is_err());
    }

    #[test]
    fn a_live_library_needs_its_number_free_of_other_mods() {
        let f = Fixture::new();
        library_free(&f.0, "tst-proving-ground", 10120).unwrap();
        // Its own copies, under any index or suffix, are its to replace.
        f.put("pakchunk10120-MJOLNIRHUB-tst-proving-ground-0_1480_P.ucas");
        f.put("pakchunk10120-MJOLNIRHUB-tst-proving-ground-0_1481_P.utoc");
        f.put("pakchunk10121-MJOLNIRHUB-ce-blood-gulch-0_1484_P.utoc");
        f.put("pakchunk10120-notes.txt");
        library_free(&f.0, "tst-proving-ground", 10120).unwrap();
        // Another mod's container under the number is not.
        f.put("pakchunk10120-MJOLNIRHUB-ce-blood-gulch-1_1488_P.utoc");
        let error = library_free(&f.0, "tst-proving-ground", 10120).unwrap_err();
        assert!(error.contains("ce-blood-gulch"), "{error}");
        let g = Fixture::new();
        g.put("pakchunk10120-MJOLNIRHUB-tst-proving-ground-extra-0_1480_P.pak");
        assert!(library_free(&g.0, "tst-proving-ground", 10120).is_err());
    }
}
