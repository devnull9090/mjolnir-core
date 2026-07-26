//! An open game installation: the container index plus cached lookups.

use std::collections::BTreeMap;
use std::path::PathBuf;

use blam_tag::TagFile;
use serde::Serialize;
use ue_iostore::{ChunkEntry, Container};

/// One shipped tag payload.
pub struct TagEntry {
    pub container: usize,
    pub chunk: ChunkEntry,
    /// Full package path.
    pub path: String,
    /// Group directory name, e.g. `weapon`.
    pub group: String,
    /// Path with the group suffix and extension stripped, e.g.
    /// `objects/characters/elite/elite`.
    pub short: String,
}

/// A loaded catalog of every tag in an installation.
pub struct Catalog {
    containers: Vec<Container>,
    pub tags: Vec<TagEntry>,
    oodle: Vec<PathBuf>,
}

#[derive(Debug, Serialize)]
pub struct GroupSummary {
    pub group: String,
    pub four_cc: String,
    pub count: usize,
}

#[derive(Debug, Serialize)]
pub struct TagSummary {
    pub index: usize,
    pub group: String,
    pub path: String,
    pub short: String,
    pub size: u64,
}

/// Strip the group suffix and extension from a package path.
fn split_path(full: &str) -> Option<(String, String)> {
    let file = full.rsplit('/').next()?;
    let stem = file.strip_suffix(".ubulk")?;
    let (name, group) = stem.rsplit_once('-')?;
    if group.is_empty() {
        return None;
    }
    let dir = full.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
    let short = if dir.is_empty() {
        name.to_string()
    } else {
        format!("{dir}/{name}")
    };
    // Trim the constant package prefix so the tree reads like Blam paths.
    let short = short
        .trim_start_matches("../../../Meteorite/Content/Tags/")
        .trim_start_matches("/Game/Tags/")
        .to_string();
    Some((group.to_string(), short))
}

impl Catalog {
    pub fn open(paks: &str, oodle: &str) -> Result<Self, String> {
        let containers = ue_iostore::load_all(paks).map_err(|e| e.to_string())?;

        let mut tags = Vec::new();
        for (ci, c) in containers.iter().enumerate() {
            for (rel, chunk_index) in &c.files {
                let full = c.full_path(rel);
                if !full.contains("/Tags/") || !full.ends_with(".ubulk") {
                    continue;
                }
                if let Some((group, short)) = split_path(&full) {
                    tags.push(TagEntry {
                        container: ci,
                        chunk: c.chunks[*chunk_index],
                        path: full,
                        group,
                        short,
                    });
                }
            }
        }
        tags.sort_by(|a, b| (&a.group, &a.short).cmp(&(&b.group, &b.short)));

        Ok(Catalog {
            containers,
            tags,
            oodle: vec![PathBuf::from(oodle)],
        })
    }

    /// Group summaries with their four-CC, sorted by name.
    pub fn groups(&self) -> Result<Vec<GroupSummary>, String> {
        let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
        let mut first: BTreeMap<&str, usize> = BTreeMap::new();
        for (i, t) in self.tags.iter().enumerate() {
            *counts.entry(t.group.as_str()).or_default() += 1;
            first.entry(t.group.as_str()).or_insert(i);
        }

        let mut out = Vec::with_capacity(counts.len());
        for (group, count) in counts {
            let four_cc = first
                .get(group)
                .and_then(|i| self.read_header(*i).ok())
                .unwrap_or_default();
            out.push(GroupSummary {
                group: group.to_string(),
                four_cc,
                count,
            });
        }
        Ok(out)
    }

    /// The four-CC of one tag, read from its container header only.
    fn read_header(&self, index: usize) -> Result<String, String> {
        let entry = self.tags.get(index).ok_or("tag index out of range")?;
        let buf = self.read_chunk(entry, Some(blam_tag::HEADER_SIZE))?;
        let header = blam_tag::TagHeader::parse(&buf, None).map_err(|e| e.to_string())?;
        Ok(header.group.as_str())
    }

    fn read_chunk(&self, entry: &TagEntry, max: Option<usize>) -> Result<Vec<u8>, String> {
        ue_iostore::read_chunk(
            &self.containers[entry.container],
            &entry.chunk,
            max,
            &self.oodle,
        )
        .map_err(|e| format!("{}: {e}", entry.path))
    }

    /// Tags in one group.
    pub fn tags_in(&self, group: &str, limit: usize) -> Vec<TagSummary> {
        self.tags
            .iter()
            .enumerate()
            .filter(|(_, t)| t.group == group)
            .take(limit)
            .map(|(index, t)| TagSummary {
                index,
                group: t.group.clone(),
                path: t.path.clone(),
                short: t.short.clone(),
                size: t.chunk.length,
            })
            .collect()
    }

    /// Case-insensitive substring search over tag paths.
    pub fn search(&self, query: &str, limit: usize) -> Vec<TagSummary> {
        let q = query.trim().to_ascii_lowercase();
        if q.is_empty() {
            return Vec::new();
        }
        self.tags
            .iter()
            .enumerate()
            .filter(|(_, t)| {
                t.short.to_ascii_lowercase().contains(&q) || t.group.contains(&q)
            })
            .take(limit)
            .map(|(index, t)| TagSummary {
                index,
                group: t.group.clone(),
                path: t.path.clone(),
                short: t.short.clone(),
                size: t.chunk.length,
            })
            .collect()
    }

    /// Read one tag's full payload.
    pub fn read_tag(&self, index: usize) -> Result<Vec<u8>, String> {
        let entry = self.tags.get(index).ok_or("tag index out of range")?;
        self.read_chunk(entry, None)
    }

    pub fn entry(&self, index: usize) -> Option<&TagEntry> {
        self.tags.get(index)
    }

    /// Parse one tag, handing the borrowed view to `f`.
    pub fn with_tag<T>(
        &self,
        index: usize,
        f: impl FnOnce(&TagFile<'_>, &blam_tag::Layout<'_>) -> T,
    ) -> Result<T, String> {
        let entry = self.tags.get(index).ok_or("tag index out of range")?;
        let buf = self.read_chunk(entry, None)?;
        let tag = TagFile::parse(&buf, Some(entry.chunk.length as usize))
            .map_err(|e| format!("{}: {e}", entry.path))?;
        let layout = tag.layout().map_err(|e| format!("{}: {e}", entry.path))?;
        Ok(f(&tag, &layout))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_group_and_short_path() {
        let (group, short) =
            split_path("../../../Meteorite/Content/Tags/objects/characters/elite/elite-biped.ubulk")
                .unwrap();
        assert_eq!(group, "biped");
        assert_eq!(short, "objects/characters/elite/elite");
    }

    #[test]
    fn handles_multi_word_groups() {
        let (group, short) =
            split_path("/Game/Tags/levels/a10/a10-scenario_structure_bsp.ubulk").unwrap();
        assert_eq!(group, "scenario_structure_bsp");
        assert_eq!(short, "levels/a10/a10");
    }

    #[test]
    fn rejects_non_tag_paths() {
        assert!(split_path("/Game/Blueprints/BP_Foo.uasset").is_none());
        assert!(split_path("no-extension").is_none());
    }
}
