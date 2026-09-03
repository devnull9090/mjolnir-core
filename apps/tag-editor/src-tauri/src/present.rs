//! What the game holds, read from UE's own object table — instant, no sweep.
//!
//! The census answers "which tags have resident data I can poke" by sweeping
//! ~13 GB of memory. This answers the cheaper questions the reader in
//! `blam_live::objects` makes a bounded pointer chase: **which level is
//! loaded**, and **which tags have a live object at all**.
//!
//! The two are not the same set. Measured in a mission, 9,147 tag assets had
//! a `UObject` but only 369 had resident data — the object is a shell whose
//! bulk data is unloaded until needed (see `docs/guobjectarray_reader.md`). So
//! this never decides what is pokeable; the census does. What it decides,
//! exactly and in about a second, is the level (exactly one scenario object is
//! ever loaded) and the identity index.

use std::path::{Path, PathBuf};

use serde::Serialize;

use crate::catalog::Catalog;

/// What the object table says the game holds right now.
#[derive(Serialize, Clone, Debug, Default)]
pub struct Present {
    /// The loaded scenario's short path — the level. Read from the one
    /// scenario object, so it is exact, not inferred.
    pub level: Option<String>,
    /// Catalog indices of every tag with a live object. A superset of the
    /// pokeable set; see the module note.
    pub tags: Vec<usize>,
    /// Live objects walked, for the report.
    pub objects: usize,
}

/// Where the game executable sits relative to the Paks folder the catalog was
/// opened on: `<game>/Meteorite/Content/Paks` → `<game>/Meteorite/Binaries/
/// Win64/HaloCampaignEvolved.exe`. The image bytes feed the static signature
/// scans; the running process supplies the base they land on.
pub fn exe_path(paks: &Path) -> Option<PathBuf> {
    let meteorite = paks.parent()?.parent()?;
    let exe = meteorite
        .join("Binaries")
        .join("Win64")
        .join(blam_live::GAME_EXE);
    exe.is_file().then_some(exe)
}

/// Attach the reader, from cached RVAs when they still validate and from the
/// image otherwise. Returns the reader and its RVAs, so the caller can refresh
/// its cache. `cached` is `(GUObjectArray rva, name pool rva)` from a previous
/// attach against this build.
pub fn attach(
    process: &blam_live::Process,
    paks: &Path,
    cached: Option<(u64, u64)>,
) -> Result<(blam_live::objects::Reader, (u64, u64)), String> {
    if let Some((g, n)) = cached {
        if let Ok(r) = blam_live::objects::Reader::from_rvas(process, g, n) {
            return Ok((r, (g, n)));
        }
        // Stale — most likely a game update moved the globals. Fall through
        // and resolve afresh rather than trust an address that failed its check.
    }
    let exe = exe_path(paks).ok_or_else(|| {
        format!(
            "could not find {} beside the Paks folder ({})",
            blam_live::GAME_EXE,
            paks.display()
        )
    })?;
    let bytes = std::fs::read(&exe).map_err(|e| format!("{}: {e}", exe.display()))?;
    let reader = blam_live::objects::Reader::attach(process, &bytes).map_err(|e| {
        format!(
            "could not resolve the engine's object table in {}: {e}. A game update may \
             have moved it; the memory scan still works without it",
            exe.display()
        )
    })?;
    let rvas = reader.rvas();
    Ok((reader, rvas))
}

/// Walk the object table and map every tag asset to the catalog.
pub fn read(
    process: &blam_live::Process,
    reader: &blam_live::objects::Reader,
    catalog: &Catalog,
) -> Result<Present, String> {
    let objects = reader.table.walk(process).map_err(|e| e.to_string())?;

    // Each class's name is resolved once — a few thousand classes against a
    // quarter-million objects — and only tag-asset classes are looked at.
    let mut class_is_tag: std::collections::HashMap<u64, bool> =
        std::collections::HashMap::new();
    let mut tags: Vec<usize> = Vec::new();
    let mut scenarios: Vec<String> = Vec::new();
    for o in &objects {
        let is_tag = *class_is_tag.entry(o.class).or_insert_with(|| {
            reader
                .name_at(process, o.class)
                .map(|n| n.ends_with("TagDataAsset"))
                .unwrap_or(false)
        });
        if !is_tag {
            continue;
        }
        let Ok((name, pkg)) = reader.identity(process, o) else {
            continue;
        };
        // Class default objects and engine-script instances share the class
        // but are not tags; real cooked tags live under /Game/Tags/.
        if name.starts_with("Default__") || !pkg.starts_with("/Game/Tags/") {
            continue;
        }
        let Some(index) = catalog.tag_by_package(&pkg) else {
            continue;
        };
        tags.push(index);
        if catalog.entry(index).is_some_and(|e| e.group == "scenario") {
            if let Some(e) = catalog.entry(index) {
                scenarios.push(e.short.clone());
            }
        }
    }
    tags.sort_unstable();
    tags.dedup();

    // Exactly one scenario object is loaded in a mission. If a UI shell's is
    // ever alongside it, the mission one is the level.
    scenarios.sort_by_key(|s| s.contains("ui"));
    Ok(Present {
        level: scenarios.into_iter().next(),
        tags,
        objects: objects.len(),
    })
}
