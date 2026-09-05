//! The simulation's own tag table as the editor's census.
//!
//! `blam_live::tagtable` reads the table the tag module keeps of every loaded
//! tag — name, group, handle, root address — in one pointer-chase. Mapped onto
//! the catalog it answers both live-mode questions at once: which level is
//! loaded (the one `scenario` in the table) and where every tag's root is, so
//! every poke is instant and exact. It replaces the memory sweep
//! (`crate::census`) whenever the running build has a profile; the sweep
//! stays as the fallback for one that does not.
//!
//! Root addresses are kept as roots, not payload bases: a base needs the tag
//! parsed for its root offset, and parsing 7,000 tags is not the price of a
//! census. The poke path knows its own root offset and subtracts.

use blam_live::tagtable::{self, LiveTags, Segments, TagTable};

use crate::catalog::Catalog;
use crate::live::LoadedTag;

/// What the table said, mapped onto the catalog.
pub struct TableCensus {
    /// `(tag key, root address, what the UI shows)` for every loaded tag the
    /// catalog knows.
    pub found: Vec<((String, String), u64, LoadedTag)>,
    /// The loaded mission's scenario, as a short path.
    pub level: Option<String>,
    pub segments: Segments,
    pub profile: &'static str,
    /// Entries in the table, including ones the catalog could not place.
    pub total: usize,
    /// Table entries no catalog tag matched — mod-only tags, or a mapping gap.
    pub unmapped: usize,
}

/// Why the table could not be used, in words for the UI. The sweep still can.
pub enum Unavailable {
    /// The tag module is not a build with a profile.
    UnknownBuild(String),
    /// No mission is loaded, so there is no table yet.
    NoMission,
}

/// Read the table and map it onto the catalog. `Ok(Err(_))` is the two
/// expected reasons the table is not there; `Err(_)` is a real failure.
pub fn read(
    process: &blam_live::Process,
    catalog: &Catalog,
) -> Result<Result<TableCensus, Unavailable>, String> {
    let attached = match tagtable::attach(process) {
        Ok(a) => a,
        Err(blam_live::Error::UnknownBuild(sha)) => return Ok(Err(Unavailable::UnknownBuild(sha))),
        Err(blam_live::Error::NoMission) => return Ok(Err(Unavailable::NoMission)),
        Err(e) => return Err(e.to_string()),
    };
    let table = match TagTable::open(process, attached.base, attached.profile) {
        Ok(t) => t,
        Err(blam_live::Error::NoMission) => return Ok(Err(Unavailable::NoMission)),
        Err(e) => return Err(e.to_string()),
    };
    let segments =
        Segments::read(process, attached.base, attached.profile).map_err(|e| e.to_string())?;
    let tags = LiveTags::new(table.walk(process).map_err(|e| e.to_string())?);

    let mut found = Vec::with_capacity(tags.len());
    let mut scenarios: Vec<String> = Vec::new();
    let mut unmapped = 0usize;
    for tag in &tags.tags {
        let Some(root) = tag.root_address(&segments) else {
            unmapped += 1;
            continue;
        };
        // The table spells the group as its four-CC and the path with
        // backslashes; the catalog's reference lookup takes both as they are.
        let Some(index) = catalog.resolve_ref(&tag.group_str(), &tag.name) else {
            unmapped += 1;
            continue;
        };
        let Some(entry) = catalog.entry(index) else {
            unmapped += 1;
            continue;
        };
        if entry.group == "scenario" {
            scenarios.push(entry.short.clone());
        }
        found.push((
            (entry.group.clone(), entry.short.clone()),
            root,
            LoadedTag {
                index,
                group: entry.group.clone(),
                short: entry.short.clone(),
                // The table is the engine's own record: nothing to score.
                fraction: 1.0,
            },
        ));
    }
    // A mission has one scenario loaded; if the UI shell's is alongside, the
    // mission's is the level.
    scenarios.sort_by_key(|s| s.contains("ui"));
    Ok(Ok(TableCensus {
        found,
        level: scenarios.into_iter().next(),
        segments,
        profile: attached.profile.label,
        total: tags.len(),
        unmapped,
    }))
}
