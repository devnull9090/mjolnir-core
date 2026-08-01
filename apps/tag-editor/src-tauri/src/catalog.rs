//! An open game installation: the container index plus cached lookups.

use std::collections::BTreeMap;
use std::path::PathBuf;

use serde::Serialize;
use ue_iostore::{ChunkEntry, Container};

/// One shipped tag payload.
pub struct TagEntry {
    pub container: usize,
    pub chunk: ChunkEntry,
    /// The tag's `.uasset` package header, which carries the import table.
    pub uasset: Option<(usize, ChunkEntry)>,
    /// Full package path.
    pub path: String,
    /// Group directory name, e.g. `weapon`.
    pub group: String,
    /// Path with the group suffix and extension stripped, e.g.
    /// `objects/characters/elite/elite`.
    pub short: String,
}

/// One texture asset: the `.uasset` header package and its `.ubulk` payload.
pub struct TextureEntry {
    pub container: usize,
    pub uasset: ChunkEntry,
    /// The sibling bulk chunk; a texture without one keeps its (small) mips
    /// inline and is not supported yet.
    pub ubulk: Option<(usize, ChunkEntry)>,
    /// Path with the mount prefix and extension stripped.
    pub short: String,
}

/// A loaded catalog of every tag in an installation.
pub struct Catalog {
    containers: Vec<Container>,
    pub tags: Vec<TagEntry>,
    pub textures: Vec<TextureEntry>,
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
        // Tag package headers, keyed by path stem, to attach after the scan.
        let mut tag_uassets: BTreeMap<String, (usize, ChunkEntry)> = BTreeMap::new();
        // Texture candidates by path convention; the format is verified when
        // one is actually opened.
        let mut candidates: BTreeMap<String, (usize, ChunkEntry, Option<(usize, ChunkEntry)>)> =
            BTreeMap::new();
        for (ci, c) in containers.iter().enumerate() {
            for (rel, chunk_index) in &c.files {
                let full = c.full_path(rel);
                if full.contains("/Tags/") && full.ends_with(".uasset") {
                    let stem = full.trim_end_matches(".uasset").to_string();
                    tag_uassets.insert(stem, (ci, c.chunks[*chunk_index]));
                    continue;
                }
                if full.contains("/Tags/") && full.ends_with(".ubulk") {
                    if let Some((group, short)) = split_path(&full) {
                        tags.push(TagEntry {
                            container: ci,
                            chunk: c.chunks[*chunk_index],
                            uasset: None,
                            path: full,
                            group,
                            short,
                        });
                    }
                    continue;
                }
                if full.contains("/Engine/") || full.contains("/Tags/") {
                    continue;
                }
                let is_texture_path = full.rsplit('/').next().is_some_and(|f| {
                    f.starts_with("T_") || full.contains("/Textures/")
                });
                if !is_texture_path {
                    continue;
                }
                let (stem, is_uasset) = if let Some(s) = full.strip_suffix(".uasset") {
                    (s, true)
                } else if let Some(s) = full.strip_suffix(".ubulk") {
                    (s, false)
                } else {
                    continue;
                };
                let entry = candidates
                    .entry(stem.to_string())
                    .or_insert((usize::MAX, c.chunks[*chunk_index], None));
                if is_uasset {
                    entry.0 = ci;
                    entry.1 = c.chunks[*chunk_index];
                } else {
                    entry.2 = Some((ci, c.chunks[*chunk_index]));
                }
            }
        }
        tags.sort_by(|a, b| (&a.group, &a.short).cmp(&(&b.group, &b.short)));
        for t in &mut tags {
            t.uasset = tag_uassets
                .get(t.path.trim_end_matches(".ubulk"))
                .copied();
        }

        let mut textures: Vec<TextureEntry> = candidates
            .into_iter()
            .filter(|(_, (ci, _, _))| *ci != usize::MAX)
            .map(|(stem, (ci, uasset, ubulk))| TextureEntry {
                container: ci,
                uasset,
                ubulk,
                short: stem
                    .trim_start_matches("../../../Meteorite/Content/")
                    .to_string(),
            })
            .collect();
        textures.sort_by(|a, b| a.short.cmp(&b.short));

        Ok(Catalog {
            containers,
            tags,
            textures,
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

    /// Case-insensitive substring search over texture paths.
    pub fn search_textures(&self, query: &str, limit: usize) -> Vec<(usize, &TextureEntry)> {
        let q = query.trim().to_ascii_lowercase();
        self.textures
            .iter()
            .enumerate()
            .filter(|(_, t)| q.is_empty() || t.short.to_ascii_lowercase().contains(&q))
            .take(limit)
            .collect()
    }

    /// Read a tag's `.uasset` package header, which carries its import table.
    pub fn read_tag_uasset(&self, index: usize) -> Result<Vec<u8>, String> {
        let t = self.tags.get(index).ok_or("tag index out of range")?;
        let (ci, chunk) = t.uasset.ok_or("tag has no package header")?;
        ue_iostore::read_chunk(&self.containers[ci], &chunk, None, &self.oodle)
            .map_err(|e| format!("{}: {e}", t.short))
    }

    /// Resolve an imported package name like `/Game/Tags/.../elite-model`
    /// to a tag index.
    pub fn tag_by_package(&self, package: &str) -> Option<usize> {
        let rest = package.strip_prefix("/Game/Tags/")?;
        let (short, group) = rest.rsplit_once('-')?;
        self.tags
            .iter()
            .position(|t| t.group == group && t.short.eq_ignore_ascii_case(short))
    }

    /// Resolve an imported package name like `/Game/characters/.../T_x`
    /// to a texture index.
    pub fn texture_by_package(&self, package: &str) -> Option<usize> {
        let rest = package.strip_prefix("/Game/")?;
        self.textures
            .iter()
            .position(|t| t.short.eq_ignore_ascii_case(rest))
    }

    /// Read a texture's `.uasset` header package.
    pub fn read_texture_uasset(&self, index: usize) -> Result<Vec<u8>, String> {
        let t = self.textures.get(index).ok_or("texture index out of range")?;
        ue_iostore::read_chunk(&self.containers[t.container], &t.uasset, None, &self.oodle)
            .map_err(|e| format!("{}: {e}", t.short))
    }

    /// Read a texture's `.ubulk` payload, if it has one.
    pub fn read_texture_ubulk(&self, index: usize) -> Result<Vec<u8>, String> {
        let t = self.textures.get(index).ok_or("texture index out of range")?;
        let (ci, chunk) = t.ubulk.ok_or("texture has no bulk payload (inline mips)")?;
        ue_iostore::read_chunk(&self.containers[ci], &chunk, None, &self.oodle)
            .map_err(|e| format!("{}: {e}", t.short))
    }

    pub fn entry(&self, index: usize) -> Option<&TagEntry> {
        self.tags.get(index)
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
