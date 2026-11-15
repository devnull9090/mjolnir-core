//! Local builds in Paks: what a developer installed with `mjolnir dev
//! install` (`pakchunk<N>-MJOLNIRDEV-<name>_<v>_P`, above every hub
//! container), and the loose containers that lose to a hub copy.
//!
//! The launcher never sets a local build aside (`unsupported.rs` accepts any
//! `-MJOLNIR` name) and never renames or deletes one when it writes a profile
//! (`hub::materialize` only touches `-MJOLNIRHUB-` files). It lists them, so
//! they can be seen and removed, and names every loose container whose
//! version never loads (`ue_iostore::paks::shadowed_loose`).

use serde::Serialize;
use ue_iostore::paks;

#[derive(Debug, Serialize, Clone)]
pub struct LocalBuild {
    pub name: String,
    pub file: String,
    pub chunk: u32,
    pub order: u32,
}

#[derive(Debug, Serialize, Clone)]
pub struct Shadowed {
    /// The loose container that loses.
    pub container: String,
    /// What it loses to.
    pub winner: String,
    /// The hub mod the winner belongs to, when it is a hub container.
    pub hub_mod: Option<String>,
    pub differing: usize,
    pub identical: usize,
}

#[derive(Debug, Serialize, Clone, Default)]
pub struct LocalBuilds {
    pub builds: Vec<LocalBuild>,
    /// Only the losses that matter: chunks whose bytes differ.
    pub shadowed: Vec<Shadowed>,
}

/// The slug in `pakchunk<N>-MJOLNIRHUB-<slug>-<j>_<v>_P` (or the older
/// `…-<j>_P`).
fn hub_slug(stem: &str) -> Option<String> {
    let at = stem.find("-MJOLNIRHUB-")? + "-MJOLNIRHUB-".len();
    let rest = stem[at..].strip_suffix("_P")?;
    let rest = rest.split('_').next()?;
    let (slug, j) = rest.rsplit_once('-')?;
    j.bytes().all(|b| b.is_ascii_digit()).then(|| slug.to_string())
}

pub fn list_in(paks_dir: &std::path::Path) -> Result<LocalBuilds, String> {
    let builds = paks::list_dev(paks_dir)?
        .into_iter()
        .map(|d| LocalBuild { name: d.name, file: d.stem, chunk: d.number, order: d.suffix })
        .collect();
    let shadowed = paks::shadowed_loose(paks_dir)?
        .into_iter()
        .filter(|s| s.differing > 0)
        .map(|s| Shadowed {
            hub_mod: hub_slug(&s.winner),
            container: s.loser,
            winner: s.winner,
            differing: s.differing,
            identical: s.identical,
        })
        .collect();
    Ok(LocalBuilds { builds, shadowed })
}

pub fn list() -> Result<LocalBuilds, String> {
    list_in(&crate::hub::paks_dir()?)
}

pub fn remove(name: String) -> Result<LocalBuilds, String> {
    let paks_dir = crate::hub::paks_dir()?;
    paks::remove_dev(&paks_dir, &name)?;
    list_in(&paks_dir)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_hub_container_names_its_mod() {
        assert_eq!(hub_slug("pakchunk10042-MJOLNIRHUB-ce-blood-gulch-0_1168_P").as_deref(), Some("ce-blood-gulch"));
        assert_eq!(hub_slug("pakchunk902-MJOLNIRHUB-ce-blood-gulch-2_P").as_deref(), Some("ce-blood-gulch"));
        assert_eq!(hub_slug("pakchunk5000000-MJOLNIRDEV-MJOLNIRMAP-BGL_1000000_P"), None);
    }

    #[test]
    fn an_empty_paks_lists_nothing() {
        let dir = std::env::temp_dir().join(format!("mjolnir-local-builds-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let listed = list_in(&dir).unwrap();
        assert!(listed.builds.is_empty() && listed.shadowed.is_empty());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
