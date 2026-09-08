//! The engine's loader cache as a poke source — exact, and no sweep.
//!
//! `blam_live::cache` reaches the map the engine's loader keeps of every
//! package it currently references: static roots in the game image, a node
//! walk, and a lookup by `FPackageId`. Each hit is a tag's live data buffer
//! at its exact address. It is partial by nature — the loader lets go of a
//! buffer once loading is done, and the buffer lives on in the simulation —
//! so in a settled mission it covers a fraction of what the census finds
//! by fingerprint (37 of 362 measured), and likely most during and just
//! after a level load. What it covers it covers instantly and exactly, so
//! the census runs it first and adopts its bases; the sweep then finds the
//! rest. See `docs/live_tag_locating.md`.
//!
//! Root RVAs are a property of the build: the caller keeps them and hands
//! them back, and [`roots`] revalidates each against the record signature
//! before trusting it, so a game update that moves them is noticed rather
//! than followed into garbage.

use std::path::Path;

use crate::catalog::Catalog;
use blam_live::cache::{self, Root};

/// Find the cache roots: cached RVAs when they still validate, otherwise a
/// fresh discovery from the image (a few seconds). Returns the roots and
/// the RVAs worth caching for next time.
pub fn roots(
    process: &blam_live::Process,
    paks: &Path,
    cached: &[u64],
) -> Result<(Vec<Root>, Vec<u64>), String> {
    let (module_base, _) = process.module(blam_live::GAME_EXE).map_err(|e| e.to_string())?;
    if !cached.is_empty() {
        let live = cache::roots_at(process, module_base, cached);
        // Any root still carrying the signature means the build has not
        // moved them; one that stopped is dropped from the cache. Only when
        // none survives is the image searched again.
        if !live.is_empty() {
            let rvas = live.iter().map(|r| r.static_rva).collect();
            return Ok((live, rvas));
        }
    }
    let exe = crate::present::exe_path(paks).ok_or_else(|| {
        format!(
            "could not find {} beside the Paks folder ({})",
            blam_live::GAME_EXE,
            paks.display()
        )
    })?;
    let bytes = std::fs::read(&exe).map_err(|e| format!("{}: {e}", exe.display()))?;
    let found = cache::find_roots(process, &bytes, module_base).map_err(|e| e.to_string())?;
    if found.is_empty() {
        return Err("the engine's loader cache could not be found in this build".into());
    }
    let rvas = found.iter().map(|r| r.static_rva).collect();
    Ok((found, rvas))
}

/// What the loader cache says about the catalog: `(tag index, base)` for
/// every tag it currently references, plus the walk's size for the report.
pub struct Hits {
    pub bases: Vec<(usize, u64)>,
    pub nodes: usize,
}

/// Walk the cache once and look up every catalog tag by its package id.
pub fn resolve(process: &blam_live::Process, catalog: &Catalog, roots: &[Root]) -> Hits {
    let walked = cache::walk(process, roots);
    let mut bases = Vec::new();
    for (i, e) in catalog.tags.iter().enumerate() {
        let id = blam_live::package_id::package_id(&e.short, &e.group);
        if let Some(h) = walked.lookup(id) {
            bases.push((i, h.base));
        }
    }
    Hits {
        bases,
        nodes: walked.nodes,
    }
}
