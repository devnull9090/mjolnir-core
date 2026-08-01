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

/// One openable asset, placed in the virtual filesystem the browser walks.
///
/// The game ships no directories of its own — every asset is a flat chunk in a
/// container — so the tree is derived from the package paths. Tags land under
/// `tags/` named the way Guerilla wrote them (`elite.biped`), textures under
/// `textures/` at their content-relative path.
struct VirtualFile {
    path: String,
    /// `tag` or `texture`; the index is into that catalog list.
    kind: &'static str,
    index: usize,
    size: u64,
}

/// One row of a directory listing: a subdirectory or an openable asset.
#[derive(Debug, Serialize)]
pub struct DirEntry {
    /// Display name within its parent, e.g. `characters` or `elite.biped`.
    pub name: String,
    /// Full virtual path.
    pub path: String,
    /// `dir`, `tag`, or `texture`.
    pub kind: &'static str,
    /// Catalog index, for files only.
    pub index: Option<usize>,
    /// Payload bytes for a file; total of its contents for a directory.
    pub size: u64,
    /// How many assets live under a directory, at any depth.
    pub children: Option<usize>,
}

/// A loaded catalog of every tag in an installation.
pub struct Catalog {
    containers: Vec<Container>,
    pub tags: Vec<TagEntry>,
    pub textures: Vec<TextureEntry>,
    /// Every asset by virtual path, sorted, so a listing is a contiguous range.
    files: Vec<VirtualFile>,
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

        let mut files: Vec<VirtualFile> = tags
            .iter()
            .enumerate()
            .map(|(index, t)| VirtualFile {
                path: format!("tags/{}.{}", t.short, t.group),
                kind: "tag",
                index,
                size: t.chunk.length,
            })
            .chain(textures.iter().enumerate().map(|(index, t)| VirtualFile {
                path: format!("textures/{}", t.short),
                kind: "texture",
                index,
                size: t.ubulk.map(|(_, c)| c.length).unwrap_or(0),
            }))
            .collect();
        // Sorted so every directory's contents form one contiguous run.
        files.sort_by(|a, b| a.path.cmp(&b.path));

        Ok(Catalog {
            containers,
            tags,
            textures,
            files,
            oodle: vec![PathBuf::from(oodle)],
        })
    }

    /// The contiguous run of files under a directory prefix.
    fn under(&self, dir: &str) -> &[VirtualFile] {
        let prefix = if dir.is_empty() {
            String::new()
        } else {
            format!("{}/", dir.trim_end_matches('/'))
        };
        let start = self.files.partition_point(|f| f.path.as_str() < prefix.as_str());
        let len = self.files[start..]
            .iter()
            .take_while(|f| f.path.starts_with(&prefix))
            .count();
        &self.files[start..start + len]
    }

    /// List one directory: its immediate subdirectories, then its assets.
    pub fn list_dir(&self, dir: &str) -> Vec<DirEntry> {
        let dir = dir.trim_matches('/');
        let skip = if dir.is_empty() { 0 } else { dir.len() + 1 };

        let mut dirs: BTreeMap<&str, (usize, u64)> = BTreeMap::new();
        let mut out = Vec::new();
        for f in self.under(dir) {
            let rest = &f.path[skip..];
            match rest.split_once('/') {
                Some((name, _)) => {
                    let e = dirs.entry(name).or_insert((0, 0));
                    e.0 += 1;
                    e.1 += f.size;
                }
                None => out.push(DirEntry {
                    name: rest.to_string(),
                    path: f.path.clone(),
                    kind: f.kind,
                    index: Some(f.index),
                    size: f.size,
                    children: None,
                }),
            }
        }

        // Directories first, the way a file dialog orders them.
        let mut rows: Vec<DirEntry> = dirs
            .into_iter()
            .map(|(name, (count, size))| DirEntry {
                name: name.to_string(),
                path: if dir.is_empty() {
                    name.to_string()
                } else {
                    format!("{dir}/{name}")
                },
                kind: "dir",
                index: None,
                size,
                children: Some(count),
            })
            .collect();
        rows.sort_by_key(|d| d.name.to_ascii_lowercase());
        out.sort_by_key(|f| f.name.to_ascii_lowercase());
        rows.extend(out);
        rows
    }

    /// Case-insensitive substring search over the whole virtual tree.
    pub fn search_files(&self, query: &str, limit: usize) -> Vec<DirEntry> {
        let q = query.trim().to_ascii_lowercase();
        if q.is_empty() {
            return Vec::new();
        }
        self.files
            .iter()
            .filter(|f| f.path.to_ascii_lowercase().contains(&q))
            .take(limit)
            .map(|f| DirEntry {
                name: f.path.rsplit('/').next().unwrap_or(&f.path).to_string(),
                path: f.path.clone(),
                kind: f.kind,
                index: Some(f.index),
                size: f.size,
                children: None,
            })
            .collect()
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

    /// A catalog with only the virtual filesystem populated, which is all the
    /// listing and search paths read.
    fn with_files(paths: &[(&str, &str)]) -> Catalog {
        let mut files: Vec<VirtualFile> = paths
            .iter()
            .enumerate()
            .map(|(index, (path, kind))| VirtualFile {
                path: (*path).to_string(),
                kind: if *kind == "tag" { "tag" } else { "texture" },
                index,
                size: 10,
            })
            .collect();
        files.sort_by(|a, b| a.path.cmp(&b.path));
        Catalog {
            containers: Vec::new(),
            tags: Vec::new(),
            textures: Vec::new(),
            files,
            oodle: Vec::new(),
        }
    }

    fn sample() -> Catalog {
        with_files(&[
            ("tags/objects/characters/elite/elite.biped", "tag"),
            ("tags/objects/characters/elite/elite.model", "tag"),
            ("tags/objects/weapons/rifle/ar.weapon", "tag"),
            ("textures/characters/GuiltySpark/T_Spark_D", "texture"),
        ])
    }

    #[test]
    fn the_root_lists_the_two_asset_kinds() {
        let rows = sample().list_dir("");
        let names: Vec<_> = rows.iter().map(|r| r.name.as_str()).collect();
        assert_eq!(names, ["tags", "textures"]);
        assert!(rows.iter().all(|r| r.kind == "dir"));
        // A directory counts every asset beneath it, at any depth.
        assert_eq!(rows[0].children, Some(3));
        assert_eq!(rows[1].children, Some(1));
    }

    #[test]
    fn a_directory_lists_subdirectories_before_files() {
        let rows = sample().list_dir("tags/objects/characters/elite");
        let names: Vec<_> = rows.iter().map(|r| r.name.as_str()).collect();
        assert_eq!(names, ["elite.biped", "elite.model"]);

        let rows = sample().list_dir("tags/objects");
        let names: Vec<_> = rows.iter().map(|r| r.name.as_str()).collect();
        assert_eq!(names, ["characters", "weapons"]);
        assert!(rows.iter().all(|r| r.kind == "dir"));
    }

    /// Matching is bounded at separators: without the trailing one,
    /// `tags/objects/w` would happily list `weapons`.
    #[test]
    fn a_partial_segment_lists_nothing() {
        assert!(sample().list_dir("tags/objects/w").is_empty());
    }

    #[test]
    fn trailing_and_leading_slashes_are_tolerated() {
        let a = sample().list_dir("tags/objects/");
        let b = sample().list_dir("/tags/objects");
        let c = sample().list_dir("tags/objects");
        assert_eq!(a.len(), c.len());
        assert_eq!(b.len(), c.len());
    }

    #[test]
    fn search_spans_the_tree_and_ignores_case() {
        let c = sample();
        let hits = c.search_files("ELITE", 50);
        assert_eq!(hits.len(), 2);
        assert!(hits.iter().all(|h| h.kind == "tag"));
        assert_eq!(hits[0].name, "elite.biped");

        assert_eq!(c.search_files("t_spark", 50).len(), 1);
        assert!(c.search_files("", 50).is_empty(), "an empty query matches nothing");
        assert_eq!(c.search_files("e", 1).len(), 1, "the limit is honoured");
    }

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
