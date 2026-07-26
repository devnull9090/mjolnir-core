//! Shared discovery of shipped tag payloads across a game's IoStore containers.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use ue_iostore::{ChunkEntry, Container};

/// One shipped tag payload located in a container.
pub struct TagEntry {
    pub container: usize,
    pub chunk: ChunkEntry,
    /// Full package path, e.g. `/Game/Tags/objects/.../elite-biped.ubulk`.
    pub path: String,
    /// Group directory name parsed from the filename suffix, e.g. `biped`.
    pub group: String,
}

pub struct Index {
    pub containers: Vec<Container>,
    pub tags: Vec<TagEntry>,
}

impl Index {
    /// Group directory name to the tags in it, sorted by path.
    pub fn by_group(&self) -> BTreeMap<&str, Vec<&TagEntry>> {
        let mut map: BTreeMap<&str, Vec<&TagEntry>> = BTreeMap::new();
        for t in &self.tags {
            map.entry(t.group.as_str()).or_default().push(t);
        }
        for v in map.values_mut() {
            v.sort_by(|a, b| a.path.cmp(&b.path));
        }
        map
    }

    /// Read a tag payload, optionally capped to a prefix.
    pub fn read(
        &self,
        entry: &TagEntry,
        max_bytes: Option<usize>,
        oodle: &[PathBuf],
    ) -> Result<Vec<u8>> {
        ue_iostore::read_chunk(
            &self.containers[entry.container],
            &entry.chunk,
            max_bytes,
            oodle,
        )
        .with_context(|| format!("reading {}", entry.path))
    }
}

/// Parse the group from a package name like `elite-biped.ubulk`.
fn group_from_path(path: &str) -> Option<String> {
    let file = path.rsplit('/').next()?;
    let stem = file.strip_suffix(".ubulk")?;
    let group = stem.rsplit_once('-')?.1;
    if group.is_empty() {
        None
    } else {
        Some(group.to_string())
    }
}

/// Enumerate every `Tags/**.ubulk` payload in a `Paks` directory.
pub fn build(paks: impl AsRef<Path>) -> Result<Index> {
    let paks = paks.as_ref();
    let containers = ue_iostore::load_all(paks)
        .with_context(|| format!("loading containers from {}", paks.display()))?;

    let mut tags = Vec::new();
    for (ci, c) in containers.iter().enumerate() {
        for (rel, chunk_index) in &c.files {
            let full = c.full_path(rel);
            if !full.contains("/Tags/") || !full.ends_with(".ubulk") {
                continue;
            }
            if let Some(group) = group_from_path(&full) {
                tags.push(TagEntry {
                    container: ci,
                    chunk: c.chunks[*chunk_index],
                    path: full,
                    group,
                });
            }
        }
    }
    tags.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(Index { containers, tags })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_group_from_package_name() {
        assert_eq!(
            group_from_path("/Game/Tags/objects/characters/elite/elite-biped.ubulk").as_deref(),
            Some("biped")
        );
        assert_eq!(
            group_from_path("/Game/Tags/a/b-scenario_structure_bsp.ubulk").as_deref(),
            Some("scenario_structure_bsp")
        );
    }

    #[test]
    fn ignores_non_tag_paths() {
        assert_eq!(group_from_path("/Game/Blueprints/BP_Foo.uasset"), None);
        assert_eq!(group_from_path("no-slash-at-all"), None);
    }
}
