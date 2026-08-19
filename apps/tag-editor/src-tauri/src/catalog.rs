//! An open game installation: the container index plus cached lookups.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

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

/// One Wwise audio file, which lives in a `.pak` rather than the IoStore.
pub struct SoundEntry {
    pub archive: usize,
    pub entry: ue_iostore::pak::PakEntry,
    /// Path below `WwiseAudio/`, e.g. `Media/English(US)/12/100018565.wem`.
    pub short: String,
    /// Language folder the file came from, or `None` for shared audio.
    pub language: Option<String>,
    /// Path below the language level, which is where the browser hangs it.
    tail: String,
}

/// One openable asset, placed in the virtual filesystem the browser walks.
///
/// The game ships no directories of its own — every asset is a flat chunk in a
/// container — so the tree is derived from the package paths. Tags land under
/// `tags/` named the way Guerilla wrote them (`elite.biped`), textures under
/// `textures/` at their content-relative path, and Wwise audio under `sounds/`.
struct VirtualFile {
    path: String,
    /// `tag`, `texture` or `sound`; the index is into that catalog list.
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
    /// `dir`, `tag`, `texture` or `sound`.
    pub kind: &'static str,
    /// Catalog index, for files only.
    pub index: Option<usize>,
    /// Payload bytes for a file; total of its contents for a directory.
    pub size: u64,
    /// How many assets live under a directory, at any depth.
    pub children: Option<usize>,
}

/// One cooked mesh package: `SM_` static or `SK_` skeletal, with its bulk
/// sibling (Nanite pages or streamed buffers) when it has one.
pub struct MeshEntry {
    pub container: usize,
    pub uasset: ChunkEntry,
    pub ubulk: Option<(usize, ChunkEntry)>,
    /// Path with the mount prefix and extension stripped.
    pub short: String,
    pub skeletal: bool,
}

/// A loaded catalog of every tag in an installation.
pub struct Catalog {
    pub(crate) containers: Vec<Container>,
    /// Cooked packages that may name Wwise media, as `(container, chunk,
    /// path)`. Kept unread; the name index is built on first use because it
    /// costs a pass over every audio package.
    audio_packages: Vec<(usize, ChunkEntry, String)>,
    /// Media short ID to event name, built lazily by [`Catalog::names`].
    names: std::sync::OnceLock<crate::wwise::NameIndex>,
    /// `.pak` archives alongside the IoStore containers; the game keeps its
    /// whole Wwise bank there.
    archives: Vec<ue_iostore::pak::PakArchive>,
    pub tags: Vec<TagEntry>,
    pub textures: Vec<TextureEntry>,
    pub sounds: Vec<SoundEntry>,
    pub meshes: Vec<MeshEntry>,
    /// Lowercased content-relative package stem to `(container, chunk)` for
    /// every cooked `.uasset`, built on first use; how a material instance's
    /// package name becomes readable bytes.
    package_index: std::sync::OnceLock<BTreeMap<String, (usize, ChunkEntry)>>,
    /// The global container's script-object table, parsed on first use.
    script_objects: std::sync::OnceLock<Option<ue_asset::zen::ScriptObjects>>,
    /// Lowercased mesh short path to mesh index, built on first use; how a
    /// Blueprint component's mesh reference becomes a viewable mesh.
    mesh_index: std::sync::OnceLock<BTreeMap<String, usize>>,
    /// Normalized hlmt tag path to the `/Game/...` folder of the
    /// `Blam*MeshSynchronization` data asset that anchors it, built on first
    /// use. The fallback route to a body mesh when the actor Blueprint's own
    /// meshes are Nanite placeholders.
    meshsync_index: std::sync::OnceLock<BTreeMap<String, String>>,
    /// Every asset by virtual path, sorted, so a listing is a contiguous range.
    files: Vec<VirtualFile>,
    /// Where to look for the optional Oodle DLL; empty means use the built-in
    /// decoder.
    pub(crate) oodle: Vec<PathBuf>,
    /// The Paks directory this catalog was read from, where a mod under test
    /// is installed.
    paks: PathBuf,
}

impl Catalog {
    /// Which Oodle decoder this catalog reads with.
    pub fn oodle_backend(&self) -> ue_iostore::oodle::Backend {
        ue_iostore::oodle::backend(&self.oodle)
    }

    pub fn oodle_paths(&self) -> &[PathBuf] {
        &self.oodle
    }

    pub fn paks(&self) -> &Path {
        &self.paks
    }

    /// The loaded source container a tag entry points into.
    pub fn container(&self, index: usize) -> Option<&Container> {
        self.containers.get(index)
    }
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

/// Split a Wwise path into its language and the part below it.
///
/// Media sits under `Media/<bucket>/`, where the bucket is a language name for
/// localised audio and a number for everything else. Sound banks skip the
/// `Media/` level and name the language directly. The `Media/` level itself
/// carries no information, so it is dropped either way.
fn split_language(short: &str) -> (Option<String>, String) {
    let rest = short.strip_prefix("Media/").unwrap_or(short);
    let Some((first, tail)) = rest.split_once('/') else {
        return (None, rest.to_string());
    };
    if first.is_empty() || first.chars().all(|c| c.is_ascii_digit()) {
        return (None, rest.to_string());
    }
    (Some(first.to_string()), tail.to_string())
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
        let mut mesh_candidates: BTreeMap<
            String,
            (usize, ChunkEntry, Option<(usize, ChunkEntry)>),
        > = BTreeMap::new();
        let mut audio_packages = Vec::new();
        for (ci, c) in containers.iter().enumerate() {
            for (rel, chunk_index) in &c.files {
                let full = c.full_path(rel);
                // Wwise event packages are the only place the readable names
                // for `.wem` media survive cooking.
                if full.contains("/Audio/") && full.ends_with(".uasset") {
                    audio_packages.push((ci, c.chunks[*chunk_index], full));
                    continue;
                }
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
                let leaf = full.rsplit('/').next().unwrap_or("");
                let is_mesh_path = leaf.starts_with("SM_") || leaf.starts_with("SK_");
                if is_mesh_path {
                    let (stem, is_uasset) = if let Some(s) = full.strip_suffix(".uasset") {
                        (s, true)
                    } else if let Some(s) = full.strip_suffix(".ubulk") {
                        (s, false)
                    } else {
                        continue;
                    };
                    let entry = mesh_candidates.entry(stem.to_string()).or_insert((
                        usize::MAX,
                        c.chunks[*chunk_index],
                        None,
                    ));
                    if is_uasset {
                        entry.0 = ci;
                        entry.1 = c.chunks[*chunk_index];
                    } else {
                        entry.2 = Some((ci, c.chunks[*chunk_index]));
                    }
                    continue;
                }
                let is_texture_path = leaf.starts_with("T_") || full.contains("/Textures/");
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
                let entry = candidates.entry(stem.to_string()).or_insert((
                    usize::MAX,
                    c.chunks[*chunk_index],
                    None,
                ));
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
            t.uasset = tag_uassets.get(t.path.trim_end_matches(".ubulk")).copied();
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

        let mut meshes: Vec<MeshEntry> = mesh_candidates
            .into_iter()
            .filter(|(_, (ci, _, _))| *ci != usize::MAX)
            .map(|(stem, (ci, uasset, ubulk))| {
                let short = stem
                    .trim_start_matches("../../../Meteorite/Content/")
                    .to_string();
                let skeletal = short
                    .rsplit('/')
                    .next()
                    .is_some_and(|leaf| leaf.starts_with("SK_"));
                MeshEntry {
                    container: ci,
                    uasset,
                    ubulk,
                    short,
                    skeletal,
                }
            })
            .collect();
        meshes.sort_by(|a, b| a.short.cmp(&b.short));

        // Wwise audio ships in the `.pak` siblings, not the IoStore. A pak
        // that fails to parse is skipped rather than failing the whole load.
        let archives = ue_iostore::pak::load_all(paks).unwrap_or_default();
        let mut sounds = Vec::new();
        for (ai, archive) in archives.iter().enumerate() {
            for (rel, entry) in &archive.files {
                if !rel.ends_with(".wem") && !rel.ends_with(".bnk") {
                    continue;
                }
                // The shared pak mounts at the content root and the localised
                // ones at `WwiseAudio/`, so normalise both to the same shape.
                let full = archive.full_path(rel);
                let short = match full.split_once("WwiseAudio/") {
                    Some((_, rest)) => rest.to_string(),
                    None => continue,
                };
                let (language, tail) = split_language(&short);
                sounds.push(SoundEntry {
                    archive: ai,
                    entry: entry.clone(),
                    short,
                    language,
                    tail,
                });
            }
        }
        // Media first: sound banks are not playable and sort to the front
        // otherwise, filling the whole first page with the least useful rows.
        sounds.sort_by(|a, b| {
            (a.short.ends_with(".bnk"), &a.short).cmp(&(b.short.ends_with(".bnk"), &b.short))
        });

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
            .chain(meshes.iter().enumerate().map(|(index, m)| VirtualFile {
                path: format!("meshes/{}", m.short),
                kind: "mesh",
                index,
                size: m.uasset.length + m.ubulk.map(|(_, c)| c.length).unwrap_or(0),
            }))
            .chain(sounds.iter().enumerate().map(|(index, s)| VirtualFile {
                // Localised audio is grouped by language so the same line in
                // two languages sits side by side.
                path: format!(
                    "sounds/{}/{}",
                    s.language.as_deref().unwrap_or("shared"),
                    s.tail
                ),
                kind: "sound",
                index,
                size: s.entry.uncompressed_size,
            }))
            .collect();
        // Sorted so every directory's contents form one contiguous run.
        files.sort_by(|a, b| a.path.cmp(&b.path));

        Ok(Catalog {
            containers,
            audio_packages,
            names: std::sync::OnceLock::new(),
            archives,
            tags,
            textures,
            sounds,
            meshes,
            package_index: std::sync::OnceLock::new(),
            script_objects: std::sync::OnceLock::new(),
            mesh_index: std::sync::OnceLock::new(),
            meshsync_index: std::sync::OnceLock::new(),
            files,
            // Empty means the caller has no DLL, which is fine: the reader
            // falls back to its own decoder.
            oodle: match oodle.trim() {
                "" => Vec::new(),
                path => vec![PathBuf::from(path)],
            },
            paks: PathBuf::from(paks),
        })
    }

    /// The contiguous run of files under a directory prefix.
    fn under(&self, dir: &str) -> &[VirtualFile] {
        let prefix = if dir.is_empty() {
            String::new()
        } else {
            format!("{}/", dir.trim_end_matches('/'))
        };
        let start = self
            .files
            .partition_point(|f| f.path.as_str() < prefix.as_str());
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
            .filter(|(_, t)| t.short.to_ascii_lowercase().contains(&q) || t.group.contains(&q))
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

    /// Resolve an imported package name like `/Game/Vehicles/.../SK_Warthog_01`
    /// to a mesh index.
    pub fn mesh_by_package(&self, package: &str) -> Option<usize> {
        let index = self.mesh_index.get_or_init(|| {
            self.meshes
                .iter()
                .enumerate()
                .map(|(i, m)| (m.short.to_ascii_lowercase(), i))
                .collect()
        });
        let rest = package.strip_prefix("/Game/")?;
        index.get(&rest.to_ascii_lowercase()).copied()
    }

    /// Read a mesh's `.uasset` package.
    pub fn read_mesh_uasset(&self, index: usize) -> Result<Vec<u8>, String> {
        let m = self.meshes.get(index).ok_or("mesh index out of range")?;
        ue_iostore::read_chunk(&self.containers[m.container], &m.uasset, None, &self.oodle)
            .map_err(|e| format!("{}: {e}", m.short))
    }

    /// Read a mesh's `.ubulk` payload, if it has one.
    pub fn read_mesh_ubulk(&self, index: usize) -> Result<Option<Vec<u8>>, String> {
        let m = self.meshes.get(index).ok_or("mesh index out of range")?;
        let Some((ci, chunk)) = m.ubulk else {
            return Ok(None);
        };
        ue_iostore::read_chunk(&self.containers[ci], &chunk, None, &self.oodle)
            .map(Some)
            .map_err(|e| format!("{}: {e}", m.short))
    }

    /// The asset folder a model tag's MeshSynchronization data asset lives
    /// in, by normalized hlmt short path (`objects/characters/elite/elite_ai`
    /// lowercased, forward slashes).
    pub fn meshsync_folder(&self, hlmt_short: &str) -> Option<&str> {
        let index = self.meshsync_index.get_or_init(|| {
            let mut map = BTreeMap::new();
            for da in self.packages_matching("meshsynchronization") {
                let Some(bytes) = self.read_package(&da) else { continue };
                let folder = match da.rsplit_once('/') {
                    Some((d, _)) => d.to_string(),
                    None => continue,
                };
                for import in crate::zen::imported_package_names(&bytes) {
                    let Some(rest) = import.strip_prefix("/Game/Tags/") else {
                        continue;
                    };
                    let Some((short, "model")) = rest.rsplit_once('-') else {
                        continue;
                    };
                    let key = short.to_ascii_lowercase();
                    // The AI variant of a character (`elite_ai`) shares the
                    // rig and meshes of its base (`elite`); alias the key so
                    // both models find the folder.
                    let alias = key.replace("_ai/", "/").trim_end_matches("_ai").to_string();
                    if alias != key {
                        map.entry(alias).or_insert_with(|| folder.clone());
                    }
                    map.insert(key, folder.clone());
                }
            }
            map
        });
        index
            .get(&hlmt_short.replace('\\', "/").to_ascii_lowercase())
            .map(String::as_str)
    }

    /// Package names (as `/Game/...`) whose path contains `substr`, matched
    /// case-insensitively — how the biped body chase finds the
    /// `Blam*MeshSynchronization` data assets.
    pub fn packages_matching(&self, substr: &str) -> Vec<String> {
        let want = substr.to_ascii_lowercase();
        let mut out = Vec::new();
        for c in &self.containers {
            for (rel, _) in &c.files {
                if let Some(stem) = rel.strip_suffix(".uasset") {
                    let stem = stem.trim_start_matches("Meteorite/Content/");
                    if stem.to_ascii_lowercase().contains(&want) {
                        out.push(format!("/Game/{stem}"));
                    }
                }
            }
        }
        out.sort();
        out.dedup();
        out
    }

    /// Read any cooked package by its `/Game/...` name — how a mesh's
    /// material-instance reference becomes bytes.
    pub fn read_package(&self, package: &str) -> Option<Vec<u8>> {
        let index = self.package_index.get_or_init(|| {
            let mut map = BTreeMap::new();
            for (ci, c) in self.containers.iter().enumerate() {
                for (rel, &chunk_index) in &c.files {
                    if let Some(stem) = rel.strip_suffix(".uasset") {
                        let key = stem
                            .trim_start_matches("Meteorite/Content/")
                            .to_ascii_lowercase();
                        map.insert(key, (ci, c.chunks[chunk_index]));
                    }
                }
            }
            map
        });
        let key = package.strip_prefix("/Game/")?.to_ascii_lowercase();
        let (ci, chunk) = index.get(&key)?;
        ue_iostore::read_chunk(&self.containers[*ci], chunk, None, &self.oodle).ok()
    }

    /// The global container's script-object table, for resolving export
    /// classes; `None` when the global container cannot be read.
    pub fn script_objects(&self) -> Option<&ue_asset::zen::ScriptObjects> {
        self.script_objects
            .get_or_init(|| {
                let global = self
                    .containers
                    .iter()
                    .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))?;
                let chunk = global
                    .chunks
                    .iter()
                    .find(|c| c.type_name() == "ScriptObjects")?;
                let bytes = ue_iostore::read_chunk(global, chunk, None, &self.oodle).ok()?;
                ue_asset::zen::ScriptObjects::parse(&bytes).ok()
            })
            .as_ref()
    }

    /// Resolve a texture's stored path back to an index.
    ///
    /// A mod recipe keys a swap by path rather than by index, for the same
    /// reason a field edit is keyed by tag path: an index is an artifact of
    /// one scan of one build of the game.
    pub fn texture_index(&self, short: &str) -> Option<usize> {
        self.textures
            .iter()
            .position(|t| t.short.eq_ignore_ascii_case(short))
    }

    /// Read a texture's `.uasset` header package.
    pub fn read_texture_uasset(&self, index: usize) -> Result<Vec<u8>, String> {
        let t = self
            .textures
            .get(index)
            .ok_or("texture index out of range")?;
        ue_iostore::read_chunk(&self.containers[t.container], &t.uasset, None, &self.oodle)
            .map_err(|e| format!("{}: {e}", t.short))
    }

    /// Read a texture's `.ubulk` payload, if it has one.
    pub fn read_texture_ubulk(&self, index: usize) -> Result<Vec<u8>, String> {
        let t = self
            .textures
            .get(index)
            .ok_or("texture index out of range")?;
        let (ci, chunk) = t.ubulk.ok_or("texture has no bulk payload (inline mips)")?;
        ue_iostore::read_chunk(&self.containers[ci], &chunk, None, &self.oodle)
            .map_err(|e| format!("{}: {e}", t.short))
    }

    /// Read a Wwise audio file out of its `.pak`.
    ///
    /// `max` caps the read: a listing only needs the RIFF header, not a
    /// multi-megabyte payload.
    pub fn read_sound(&self, index: usize, max: Option<usize>) -> Result<Vec<u8>, String> {
        let s = self.sounds.get(index).ok_or("sound index out of range")?;
        let archive = self
            .archives
            .get(s.archive)
            .ok_or("sound archive is not loaded")?;
        ue_iostore::pak::read_file(archive, &s.entry, max, &self.oodle)
            .map_err(|e| format!("{}: {e}", s.short))
    }

    pub fn sound(&self, index: usize) -> Option<&SoundEntry> {
        self.sounds.get(index)
    }

    /// The Wwise name index, built on first use.
    ///
    /// Building it reads every cooked audio package, which is seconds of work,
    /// so it is deferred until something actually asks for a name rather than
    /// paid on every launch.
    pub fn names(&self) -> &crate::wwise::NameIndex {
        self.names.get_or_init(|| {
            let mut index = crate::wwise::NameIndex::default();
            for (ci, chunk, path) in &self.audio_packages {
                let Ok(buf) =
                    ue_iostore::read_chunk(&self.containers[*ci], chunk, None, &self.oodle)
                else {
                    continue;
                };
                // The summary name map holds the media paths, the event name
                // and the authored `.wav` sources.
                let Some(names) = crate::zen::load_name_batch(&buf, 52) else {
                    continue;
                };
                index.add_package(path, &names);
            }
            // The banks are deliberately *not* folded in here. Their event
            // graph parses fine, but of 195,215 bank events only 1,621 match a
            // name the packages carry — Wwise strips names to hashes, and the
            // game ships packages for barely 1% of its events. Walking every
            // bank costs seconds and names nothing new. See `bnk::parse`, which
            // is kept for when a name list does exist.
            index
        })
    }

    /// The readable event name for one sound, when a package claims it.
    pub fn sound_label(&self, index: usize) -> Option<&str> {
        let s = self.sounds.get(index)?;
        let id = crate::wwise::media_id_of_path(&s.short)?;
        self.names().label_for(id)
    }

    /// Case-insensitive substring search over Wwise audio paths.
    pub fn search_sounds(&self, query: &str, limit: usize) -> Vec<(usize, &SoundEntry)> {
        let q = query.trim().to_ascii_lowercase();
        self.sounds
            .iter()
            .enumerate()
            .filter(|(_, s)| q.is_empty() || s.short.to_ascii_lowercase().contains(&q))
            .take(limit)
            .collect()
    }

    pub fn entry(&self, index: usize) -> Option<&TagEntry> {
        self.tags.get(index)
    }

    /// Resolve a tag by its stable identity `(group, short path)` — how a mod
    /// project names tags, so a recipe finds them again in any installation.
    ///
    /// Binary search over the `(group, short)` order the tag list is built in.
    pub fn tag_index(&self, group: &str, short: &str) -> Option<usize> {
        self.tags
            .binary_search_by(|t| (t.group.as_str(), t.short.as_str()).cmp(&(group, short)))
            .ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Read every shipped `.wem` header through the pak reader.
    ///
    /// This is the ground truth for [`ue_iostore::pak`]: a wrong entry offset
    /// or block extent yields bytes that are not a RIFF file, and a wrong
    /// length shows up as a declared size that disagrees with what came back.
    /// Ignored by default because it needs an installed game; point
    /// `MJOLNIR_PAKS` at the `Paks` directory and run with `--ignored`.
    #[test]
    #[ignore = "needs an installed game; set MJOLNIR_PAKS"]
    fn every_shipped_wem_header_parses() {
        let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
        let c = Catalog::open(&paks, "").expect("catalog opens");
        assert!(!c.sounds.is_empty(), "no Wwise audio found under {paks}");

        let mut parsed = 0usize;
        let mut banks = 0usize;
        let mut codecs: BTreeMap<String, usize> = BTreeMap::new();
        for (i, s) in c.sounds.iter().enumerate() {
            if s.short.ends_with(".bnk") {
                banks += 1;
                continue;
            }
            let head = c
                .read_sound(i, Some(crate::sounds::HEADER_BYTES))
                .unwrap_or_else(|e| panic!("{}: {e}", s.short));
            let info = crate::sounds::parse_wem(&head)
                .unwrap_or_else(|e| panic!("{}: {e}", s.short));
            // The declared RIFF size must match what the pak entry says it
            // stored, or the entry decode picked up the wrong extent.
            let declared = u32::from_le_bytes(head[4..8].try_into().unwrap()) as u64 + 8;
            assert_eq!(declared, s.entry.uncompressed_size, "{}", s.short);
            assert!(info.sample_rate > 0, "{}", s.short);
            assert!(info.channels > 0, "{}", s.short);
            *codecs.entry(info.codec.clone()).or_default() += 1;
            parsed += 1;
        }
        eprintln!("parsed {parsed} wem headers and skipped {banks} banks: {codecs:?}");
    }

    /// Convert a broad sample of shipped media to Ogg and decode it.
    ///
    /// Conversion against the wrong codebook library still yields a well-formed
    /// Ogg stream that decodes to noise, so this asserts on what came out: the
    /// stream's channel count and sample rate must match what the `.wem` header
    /// declared, and its audio packets must decode.
    ///
    /// Ignored by default; set `MJOLNIR_PAKS` and run with `--ignored`.
    #[test]
    #[ignore = "needs an installed game; set MJOLNIR_PAKS"]
    fn shipped_media_converts_to_playable_ogg() {
        use std::collections::BTreeMap;

        let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
        let c = Catalog::open(&paks, "").expect("catalog opens");

        // Spread the sample across the whole catalog rather than one language.
        let media: Vec<usize> = (0..c.sounds.len())
            .filter(|i| !c.sounds[*i].short.ends_with(".bnk"))
            .collect();
        let want = 400usize;
        let step = (media.len() / want).max(1);

        let mut ok = 0usize;
        let mut failed = Vec::new();
        let mut books: BTreeMap<&str, usize> = BTreeMap::new();
        for i in media.iter().step_by(step).take(want) {
            let wem = c.read_sound(*i, None).expect("media reads");
            let header = crate::sounds::parse_wem(&wem).expect("header parses");
            match crate::decode::to_playable(&wem) {
                Ok(out) => {
                    *books.entry(out.via).or_default() += 1;
                    // A converted Vorbis stream must describe the same audio;
                    // PCM is passed through and has nothing to re-check.
                    if out.mime == "audio/ogg" {
                        let r = lewton::inside_ogg::OggStreamReader::new(std::io::Cursor::new(
                            &out.bytes,
                        ))
                        .expect("converted stream opens");
                        assert_eq!(
                            r.ident_hdr.audio_channels as u16, header.channels,
                            "{}: channel count changed",
                            c.sounds[*i].short
                        );
                        assert_eq!(
                            r.ident_hdr.audio_sample_rate, header.sample_rate,
                            "{}: sample rate changed",
                            c.sounds[*i].short
                        );
                    }
                    ok += 1;
                }
                Err(e) => failed.push(format!("{}: {e}", c.sounds[*i].short)),
            }
        }

        eprintln!("converted {ok} of {} sampled media; codebooks {books:?}", ok + failed.len());
        for f in failed.iter().take(10) {
            eprintln!("  FAILED {f}");
        }
        assert!(failed.is_empty(), "{} media failed to convert", failed.len());
    }

    /// Measure how far the sound banks could ever go towards naming media.
    ///
    /// The bank graph parses — events resolve through actions and containers
    /// down to sounds — but a bank names nothing: Wwise reduces every name to
    /// an FNV-1 hash. Only the cooked packages keep names, and the game ships
    /// packages for a tiny fraction of its events, so most of the library
    /// cannot be named from shipped data at all. This records that ceiling so
    /// the conclusion is re-checkable against a future build.
    ///
    /// Ignored by default; set `MJOLNIR_PAKS` and run with `--ignored`.
    #[test]
    #[ignore = "needs an installed game; set MJOLNIR_PAKS"]
    fn banks_cannot_name_what_the_game_does_not_ship() {
        let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
        let c = Catalog::open(&paks, "").expect("catalog opens");
        let names = c.names();

        // Seed with every name the packages carry, so the match count below
        // measures the real ceiling rather than an empty index.
        let mut index = crate::wwise::NameIndex::default();
        for e in &names.events {
            index.add_event_name(&e.name, &e.package);
        }
        let mut with_graph = 0usize;
        let banks: Vec<usize> = (0..c.sounds.len())
            .filter(|i| c.sounds[*i].short.ends_with(".bnk"))
            .collect();
        for i in &banks {
            let Ok(raw) = c.read_sound(*i, None) else {
                continue;
            };
            let bank = crate::bnk::parse(&raw);
            if !bank.events.is_empty() {
                with_graph += 1;
            }
            index.add_bank(&bank);
        }

        eprintln!(
            "{} banks, {with_graph} with a readable event graph; {} events seen, {} match a name \
             the packages carry ({} event names known)",
            banks.len(),
            index.bank_events,
            index.bank_events_named,
            names.events.len(),
        );
        // The parser must work — the point is that names, not structure, are
        // what is missing.
        assert!(with_graph > 0, "no bank yielded an event graph");
        assert!(index.bank_events > 10_000, "suspiciously few bank events");
    }

    /// Recover readable names for the shipped media and report the coverage.
    ///
    /// Ignored by default; set `MJOLNIR_PAKS` and run with `--ignored`.
    #[test]
    #[ignore = "needs an installed game; set MJOLNIR_PAKS"]
    fn wwise_media_resolve_to_event_names() {
        let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
        let c = Catalog::open(&paks, "").expect("catalog opens");

        let t = std::time::Instant::now();
        let names = c.names();
        let build = t.elapsed();
        assert!(!names.events.is_empty(), "no Wwise events were indexed");

        let mut named = 0usize;
        let mut unnamed = 0usize;
        let mut sample = Vec::new();
        for (i, s) in c.sounds.iter().enumerate() {
            if s.short.ends_with(".bnk") {
                continue;
            }
            match c.sound_label(i) {
                Some(label) => {
                    named += 1;
                    if sample.len() < 5 {
                        sample.push(format!("{} -> {label}", s.short));
                    }
                }
                None => unnamed += 1,
            }
        }
        eprintln!(
            "indexed {} events over {} packages in {build:.1?}; {} media ids named",
            names.events.len(),
            c.audio_packages.len(),
            names.media_named()
        );
        eprintln!("{named} sounds named, {unnamed} unnamed");
        for s in &sample {
            eprintln!("  {s}");
        }
        assert!(named > 0, "no sound resolved to an event name");
    }

    #[test]
    fn localised_audio_is_grouped_under_its_language() {
        // Media buckets are numeric for shared audio and named for localised.
        assert_eq!(
            split_language("Media/English(US)/12/100018565.wem"),
            (Some("English(US)".to_string()), "12/100018565.wem".to_string())
        );
        assert_eq!(
            split_language("Media/10/100018565.wem"),
            (None, "10/100018565.wem".to_string())
        );
        // Banks name the language directly, without a Media level.
        assert_eq!(
            split_language("Italian/1005569379.bnk"),
            (Some("Italian".to_string()), "1005569379.bnk".to_string())
        );
        // A shared bank sits at the root and has no language at all.
        assert_eq!(
            split_language("Init.bnk"),
            (None, "Init.bnk".to_string())
        );
    }

    /// A catalog with only the virtual filesystem populated, which is all the
    /// listing and search paths read.
    fn with_files(paths: &[(&str, &str)]) -> Catalog {
        let mut files: Vec<VirtualFile> = paths
            .iter()
            .enumerate()
            .map(|(index, (path, kind))| VirtualFile {
                path: (*path).to_string(),
                kind: match *kind {
                    "tag" => "tag",
                    "sound" => "sound",
                    _ => "texture",
                },
                index,
                size: 10,
            })
            .collect();
        files.sort_by(|a, b| a.path.cmp(&b.path));
        Catalog {
            containers: Vec::new(),
            audio_packages: Vec::new(),
            names: std::sync::OnceLock::new(),
            archives: Vec::new(),
            tags: Vec::new(),
            textures: Vec::new(),
            sounds: Vec::new(),
            meshes: Vec::new(),
            package_index: std::sync::OnceLock::new(),
            script_objects: std::sync::OnceLock::new(),
            mesh_index: std::sync::OnceLock::new(),
            meshsync_index: std::sync::OnceLock::new(),
            files,
            oodle: Vec::new(),
            paks: PathBuf::new(),
        }
    }

    fn sample() -> Catalog {
        with_files(&[
            ("tags/objects/characters/elite/elite.biped", "tag"),
            ("tags/objects/characters/elite/elite.model", "tag"),
            ("tags/objects/weapons/rifle/ar.weapon", "tag"),
            ("textures/characters/GuiltySpark/T_Spark_D", "texture"),
            ("sounds/English(US)/12/100018565.wem", "sound"),
            ("sounds/shared/10/243917884.wem", "sound"),
        ])
    }

    #[test]
    fn the_root_lists_every_asset_kind() {
        let rows = sample().list_dir("");
        let names: Vec<_> = rows.iter().map(|r| r.name.as_str()).collect();
        assert_eq!(names, ["sounds", "tags", "textures"]);
        assert!(rows.iter().all(|r| r.kind == "dir"));
        // A directory counts every asset beneath it, at any depth.
        assert_eq!(rows[0].children, Some(2));
        assert_eq!(rows[1].children, Some(3));
        assert_eq!(rows[2].children, Some(1));
    }

    #[test]
    fn a_sound_directory_lists_its_media() {
        let rows = sample().list_dir("sounds/English(US)/12");
        let names: Vec<_> = rows.iter().map(|r| r.name.as_str()).collect();
        assert_eq!(names, ["100018565.wem"]);
        assert_eq!(rows[0].kind, "sound");
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
        assert!(
            c.search_files("", 50).is_empty(),
            "an empty query matches nothing"
        );
        assert_eq!(c.search_files("e", 1).len(), 1, "the limit is honoured");
    }

    #[test]
    fn splits_group_and_short_path() {
        let (group, short) = split_path(
            "../../../Meteorite/Content/Tags/objects/characters/elite/elite-biped.ubulk",
        )
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
