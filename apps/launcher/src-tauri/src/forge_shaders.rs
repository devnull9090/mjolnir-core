//! Forge shader libraries are addressed by their numeric pak chunk, not
//! their pack slug. Two different filenames do not isolate the same number.
use std::fs;
use std::path::Path;

pub struct Planned<'a> {
    pub slug: &'a str,
    pub source: &'a str,
    pub target: &'a str,
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
    // The launcher's previous release may have a different container index
    // or a live-update suffix. Match the entire numeric tail, so pack "foo"
    // never owns "foo-extra" or a merely similar hand-installed filename.
    let lower = stem.to_ascii_lowercase();
    let prefix = format!(
        "pakchunk{number}-mjolnirhub-{}-",
        planned.slug.to_ascii_lowercase()
    );
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
        let number = chunk(material.source)
            .filter(|n| (900..=999).contains(n))
            .ok_or_else(|| {
                format!(
                    "{} has an invalid Forge material shader chunk",
                    material.slug
                )
            })?;
        if chunk(material.target) != Some(number) {
            return Err(format!("{} must retain shader chunk {number}. Its material container is missing a readable shader library; reinstall a corrected release.", material.slug));
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
        let number = chunk(material.source).expect("validated above");
        for (stem, name) in &existing {
            if chunk(stem) == Some(number) && !same_pack(stem, material, number) {
                return Err(format!("{} needs shader chunk {number}, already used by {name}. Remove or disable the conflicting pack, or use a release cooked with a different shader chunk. No game files were changed.", material.slug));
            }
        }
    }
    Ok(())
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
    fn material() -> Planned<'static> {
        Planned {
            slug: "foundry-wide",
            source: "pakchunk967-MJOLNIRFORGEMAT-foundry-wide_P",
            target: "pakchunk967-MJOLNIRHUB-foundry-wide-0_P",
        }
    }

    #[test]
    fn two_slugs_in_one_pending_install_cannot_share_the_shader_number() {
        let f = Fixture::new();
        let other = Planned {
            slug: "other-kit",
            source: "pakchunk967-MJOLNIRFORGEMAT-other-kit_P",
            target: "pakchunk967-MJOLNIRHUB-other-kit-0_P",
        };
        let error = check(&f.0, &[material(), other], true).unwrap_err();
        assert!(
            error.contains("foundry-wide") && error.contains("other-kit") && error.contains("967")
        );
        assert_eq!(fs::read_dir(&f.0).unwrap().count(), 0);
    }

    #[test]
    fn existing_unrelated_content_blocks_each_sibling_and_is_untouched() {
        for ext in ["utoc", "ucas", "pak", "UTOC"] {
            let f = Fixture::new();
            let name = format!("pakchunk967-OtherCommunityPack_P.{ext}");
            f.put(&name);
            let error = check(&f.0, &[material()], true).unwrap_err();
            assert!(error.contains(&name));
            assert_eq!(
                fs::read(f.0.join(name)).unwrap(),
                b"preserve unrelated bytes"
            );
        }
    }

    #[test]
    fn same_pack_updates_and_container_triples_are_allowed() {
        let f = Fixture::new();
        for stem in [
            material().source,
            material().target,
            "pakchunk967-MJOLNIRHUB-foundry-wide-99_3_P",
        ] {
            for ext in ["utoc", "ucas", "pak"] {
                f.put(&format!("{stem}.{ext}"));
            }
        }
        check(&f.0, &[material()], false).unwrap();
        let ordinary = Planned {
            slug: "foundry-wide",
            source: "plain_visuals",
            target: "pakchunk967-MJOLNIRHUB-foundry-wide-1_P",
        };
        check(&f.0, &[material(), ordinary], true).unwrap();
    }

    #[test]
    fn similarly_named_pack_and_live_managed_content_still_conflict() {
        let f = Fixture::new();
        f.put("pakchunk967-MJOLNIRHUB-foundry-wide-extra-0_P.utoc");
        assert!(check(&f.0, &[material()], false).is_err());
        // Offline replacement deletes old managed files, but never exempts
        // the competing pack if it is also in the new plan.
        check(&f.0, &[material()], true).unwrap();
        let other = Planned {
            slug: "foundry-wide-extra",
            source: "ordinary",
            target: "pakchunk967-MJOLNIRHUB-foundry-wide-extra-0_P",
        };
        assert!(check(&f.0, &[material(), other], true).is_err());
    }

    #[test]
    fn distinct_chunks_ordinary_packs_and_noncontainer_files_remain_compatible() {
        let f = Fixture::new();
        for name in [
            "pakchunk968-Other_P.utoc",
            "pakchunk967-notes.txt",
            "notpakchunk967-fake.utoc",
        ] {
            f.put(name);
        }
        check(&f.0, &[material()], false).unwrap();
        let other = Planned {
            slug: "other",
            source: "pakchunk968-MJOLNIRFORGEMAT-other_P",
            target: "pakchunk968-MJOLNIRHUB-other-0_P",
        };
        let clean = Fixture::new();
        check(&clean.0, &[material(), other], false).unwrap();
        let ordinary = Planned {
            slug: "legacy",
            source: "pakchunk967-legacy",
            target: "pakchunk900-MJOLNIRHUB-legacy-0_P",
        };
        check(
            Path::new("this-directory-need-not-exist"),
            &[ordinary],
            false,
        )
        .unwrap();
    }

    #[test]
    fn material_chunk_cannot_be_renumbered_or_obscured_by_case() {
        let f = Fixture::new();
        let wrong = Planned {
            target: "pakchunk900-MJOLNIRHUB-foundry-wide-0_P",
            ..material()
        };
        assert!(check(&f.0, &[wrong], false)
            .unwrap_err()
            .contains("retain shader chunk 967"));
        f.put("PAKCHUNK0967-UNRELATED_P.UCAS");
        assert!(check(&f.0, &[material()], false).is_err());
        let bare = Fixture::new();
        bare.put("pakchunk967.utoc");
        assert!(check(&bare.0, &[material()], false).is_err());
    }
}
