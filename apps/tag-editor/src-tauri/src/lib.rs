//! MJOLNIR Tag Editor backend.
//!
//! Reads Blam tag definitions and values from the user's own installation of
//! Halo Campaign Evolved. The installation itself is never modified: edits
//! accumulate in a mod project — a saved recipe of field changes — and leave
//! the editor only as new files (an exported tag, a baked container, a
//! `.mjolnir` archive).

use std::collections::BTreeMap;
use std::sync::Mutex;

use serde::Serialize;
use tauri::State;

pub mod bnk;
pub mod catalog;
pub mod changelog;
pub mod decode;
pub mod geometry;
pub mod hub;
pub mod install;
pub mod keystore;
pub mod live;
pub mod modpack;
pub mod project;
pub mod scripts;
pub mod secret;
pub mod sounds;
/// Cooked texture reading and rewriting, shared with the `mjolnir` CLI.
pub use ue_texture as textures;
pub mod wwise;
pub mod zen;

use catalog::{Catalog, GroupSummary, TagSummary};

/// Cap on how many rows a single query returns, to keep IPC payloads bounded.
const MAX_ROWS: usize = 500;

/// A tag's stable identity: `(group, short path)`.
///
/// Edits are keyed by this rather than by catalog index, because an index is
/// an artifact of one scan of one build of the game — a project keyed by
/// index would silently edit the wrong tags after a game update.
type TagKey = (String, String);

/// Everything the user is working on: their edits, and the project the edits
/// belong to when one is open.
#[derive(Default)]
struct Workbench {
    edits: BTreeMap<TagKey, Vec<PendingEdit>>,
    /// Scenarios whose Blam script the mod replaces, as `.hsc` source keyed by
    /// file name. Held as source rather than as a compiled tree so the recipe
    /// stays readable and re-applies against whatever the player's game ships,
    /// exactly like a field edit does.
    scripts: BTreeMap<TagKey, Vec<(String, String)>>,
    /// Textures whose pixels the mod replaces, keyed by catalog path and held
    /// as the replacement PNG. Held as the source image rather than as an
    /// encoded payload for the same reason scripts are held as source: the
    /// recipe re-encodes against whatever the player's game ships.
    textures: BTreeMap<String, Vec<u8>>,
    /// When set, every change to `edits` is mirrored to the project folder.
    project: Option<project::Project>,
}

impl Workbench {
    /// The edits flattened for the project file, in map order.
    fn saved_edits(&self) -> Vec<project::SavedEdit> {
        self.edits
            .iter()
            .flat_map(|((group, tag), pending)| {
                pending.iter().map(move |e| project::SavedEdit {
                    group: group.clone(),
                    tag: tag.clone(),
                    field: e.path.clone(),
                    value: e.value.clone(),
                })
            })
            .collect()
    }

    /// Mirror the edits to disk, when a project is open.
    ///
    /// The edit already happened in memory either way; a failed write is
    /// reported so the user knows the folder is not keeping up.
    fn autosave(&self) -> Result<(), String> {
        match &self.project {
            Some(p) => p.save_edits(&self.saved_edits()),
            None => Ok(()),
        }
    }

    /// Write the whole workbench into a project folder, sidecar files and all.
    ///
    /// Used when a project is created around work already in progress, where
    /// the folder has nothing to preserve and every list has to be written
    /// out rather than merged with what is on disk.
    fn mirror_all(&self) -> Result<(), String> {
        let Some(p) = &self.project else {
            return Ok(());
        };
        let mut scripts = Vec::new();
        for ((group, tag), files) in &self.scripts {
            p.write_script_files(group, tag, files)?;
            scripts.push(project::SavedScript {
                group: group.clone(),
                tag: tag.clone(),
            });
        }
        let mut textures = Vec::new();
        for (path, png) in &self.textures {
            p.write_texture_file(path, png)?;
            textures.push(project::SavedTexture { path: path.clone() });
        }
        p.save_all(&self.saved_edits(), &scripts, &textures)
    }
}

#[derive(Default)]
struct AppState {
    catalog: Mutex<Option<Catalog>>,
    work: Mutex<Workbench>,
}

#[derive(Clone, Serialize)]
struct PendingEdit {
    path: String,
    /// The text the user typed, re-parsed against the layout on each read.
    value: String,
}

#[derive(Serialize)]
struct OpenResult {
    groups: usize,
    tags: usize,
    /// `dll` or `built-in`, so the UI can say which decoder is in use.
    decoder: &'static str,
    /// The Paks folder actually opened, which is not always the path that was
    /// asked for — see `open_install`.
    paks: String,
}

#[derive(Serialize)]
struct NodeView {
    /// `field`, `struct`, `block`, `element` or `array`.
    kind: &'static str,
    name: String,
    #[serde(rename = "type")]
    type_name: String,
    offset: u32,
    size: u32,
    /// The value rendered for display, empty when there is nothing to show.
    value: String,
    /// Set for a tag reference, so the UI can offer to follow it.
    reference: Option<Reference>,
    /// Every option an enum or bitfield can take, in declaration order.
    options: Vec<String>,
    /// For an enum, which option is selected; for a bitfield, which bits are.
    selected: Vec<String>,
    block: Option<String>,
    max_count: Option<u32>,
    /// Elements this block really has; `children` may hold fewer.
    count: Option<u32>,
    children: Vec<NodeView>,
}

#[derive(Serialize)]
struct Reference {
    group: String,
    path: String,
}

#[derive(Serialize)]
struct TagView {
    path: String,
    group: String,
    four_cc: String,
    version: u32,
    chunk_size: u64,
    data_size: u32,
    /// Whether the value walk succeeded and consumed the payload exactly.
    data_exact: bool,
    /// Why the values could not be read, when they could not be.
    error: Option<String>,
    /// Total nodes in the tree, so the UI can warn before expanding everything.
    node_count: usize,
    /// Field paths with an unexported edit, so the UI can mark them.
    edited: Vec<String>,
    fields: Vec<NodeView>,
}

/// What one applied edit did, for the UI to report.
#[derive(Serialize)]
struct EditResult {
    path: String,
    #[serde(rename = "type")]
    type_name: String,
    before: String,
    after: String,
    /// Bytes of the file that changed. Zero when the value was already that.
    changed_bytes: usize,
}

fn kind_name(kind: blam_tag::view::Kind) -> &'static str {
    use blam_tag::view::Kind;
    match kind {
        Kind::Field => "field",
        Kind::Struct => "struct",
        Kind::Block => "block",
        Kind::Element => "element",
        Kind::Array => "array",
    }
}

fn to_view(node: &blam_tag::view::Node) -> NodeView {
    use blam_tag::Scalar;

    let (reference, selected) = match &node.value {
        Scalar::Reference { group, path } => (
            Some(Reference {
                group: group.clone(),
                path: path.clone(),
            }),
            Vec::new(),
        ),
        Scalar::Enum {
            option: Some(name), ..
        } => (None, vec![name.clone()]),
        Scalar::Flags { set, .. } => (None, set.clone()),
        _ => (None, Vec::new()),
    };

    NodeView {
        kind: kind_name(node.kind),
        name: node.name.clone(),
        type_name: node.type_name.clone(),
        offset: node.offset,
        size: node.size,
        value: node.value.display(),
        reference,
        options: node.options.clone(),
        selected,
        block: node.block_name.clone(),
        max_count: node.max_count,
        count: node.count,
        children: node.children.iter().map(to_view).collect(),
    }
}

#[tauri::command]
fn detect_install() -> install::Install {
    install::detect()
}

#[tauri::command]
fn open_install(
    paks: String,
    oodle: String,
    state: State<'_, AppState>,
) -> Result<OpenResult, String> {
    // The form takes whatever names the installation — the game folder, the
    // Steam library holding it, the Paks folder — so the reader is handed the
    // one path it can actually open.
    let paks = install::resolve_paks(&paks)
        .map(|p| p.display().to_string())
        .ok_or_else(|| {
            format!(
                "No game containers under {}. Choose the folder holding Halo Campaign Evolved, \
                 or its Meteorite\\Content\\Paks folder.",
                paks.trim()
            )
        })?;
    let catalog = Catalog::open(&paks, &oodle)?;
    let groups = catalog.groups()?.len();
    let tags = catalog.tags.len();
    let decoder = match catalog.oodle_backend() {
        ue_iostore::oodle::Backend::Dll(_) => "dll",
        ue_iostore::oodle::Backend::Pure => "built-in",
    };
    // These paths are now known to work; skip the search on the next launch.
    install::remember(&paks, &oodle);
    *state.catalog.lock().map_err(|e| e.to_string())? = Some(catalog);
    Ok(OpenResult {
        groups,
        tags,
        decoder,
        paks,
    })
}

fn with_catalog<T>(
    state: &State<'_, AppState>,
    f: impl FnOnce(&Catalog) -> Result<T, String>,
) -> Result<T, String> {
    let guard = state.catalog.lock().map_err(|e| e.to_string())?;
    let catalog = guard.as_ref().ok_or("no installation is open")?;
    f(catalog)
}

#[tauri::command]
fn list_groups(state: State<'_, AppState>) -> Result<Vec<GroupSummary>, String> {
    with_catalog(&state, |c| c.groups())
}

#[tauri::command]
fn list_tags(group: String, state: State<'_, AppState>) -> Result<Vec<TagSummary>, String> {
    with_catalog(&state, |c| Ok(c.tags_in(&group, MAX_ROWS)))
}

#[tauri::command]
fn search_tags(query: String, state: State<'_, AppState>) -> Result<Vec<TagSummary>, String> {
    with_catalog(&state, |c| Ok(c.search(&query, MAX_ROWS)))
}

/// Parse each pending edit against the layout, dropping any that no longer
/// resolve. A stale edit is reported by the command that made it, not here.
fn parse_edits(
    layout: &blam_tag::Layout<'_>,
    file: &[u8],
    block: &blam_tag::data::Block<'_>,
    pending: &[PendingEdit],
) -> Vec<(String, blam_tag::Scalar)> {
    pending
        .iter()
        .filter_map(|e| {
            let target = blam_tag::patch::resolve(layout, file, block, &e.path).ok()?;
            let value = blam_tag::value::parse(layout, &target.field, &e.value).ok()?;
            Some((e.path.clone(), value))
        })
        .collect()
}

/// The tag as the user currently sees it: the shipped bytes with any pending
/// edits applied.
fn patched_bytes(c: &Catalog, index: usize, pending: &[PendingEdit]) -> Result<Vec<u8>, String> {
    patched_with_script(c, index, pending, None)
}

/// The tag as the mod leaves it: field edits first, then a script rewrite.
///
/// Order matters. A field edit is a byte-level patch resolved against the tag
/// it was recorded on, so it goes first; the script rewrite re-reads whatever
/// that produced and rebuilds `bdat` around it.
fn patched_with_script(
    c: &Catalog,
    index: usize,
    pending: &[PendingEdit],
    script: Option<&[(String, String)]>,
) -> Result<Vec<u8>, String> {
    let file = c.read_tag(index)?;
    let entry = c.entry(index).ok_or("tag index out of range")?;
    let chunk_len = entry.chunk.length as usize;

    let mut out = file;
    if !pending.is_empty() {
        let tag = blam_tag::TagFile::parse(&out, Some(chunk_len)).map_err(|e| e.to_string())?;
        let layout = tag.layout().map_err(|e| e.to_string())?;
        let block = tag.read_data(&layout).map_err(|e| e.to_string())?;
        let edits = parse_edits(&layout, &out, &block, pending);
        let (patched, _) = blam_tag::patch::set_many(&layout, &out, &block, &edits)
            .map_err(|e| e.to_string())?;
        out = patched;
    }

    if let Some(sources) = script.filter(|s| !s.is_empty()) {
        let len = out.len();
        let (rewritten, report) = scripts::compile_into(&out, len.min(chunk_len.max(len)), sources)?;
        if !report.ok {
            let first = report
                .errors
                .first()
                .map(|e| format!("line {}: {}", e.line, e.message))
                .unwrap_or_else(|| "compilation failed".into());
            return Err(format!(
                "the script does not compile ({} error(s)); first is {first}",
                report.errors.len()
            ));
        }
        out = rewritten;
    }
    Ok(out)
}

/// Parse `group:path`, or `none`, into a tag reference.
fn parse_reference(text: &str) -> Result<blam_tag::Scalar, String> {
    let t = text.trim();
    if t.is_empty() || t.eq_ignore_ascii_case("none") {
        return Ok(blam_tag::Scalar::Reference {
            group: String::new(),
            path: String::new(),
        });
    }
    let (group, path) = t
        .split_once(':')
        .ok_or("a tag reference is written as <group>:<path>")?;
    Ok(blam_tag::Scalar::Reference {
        group: group.trim().to_string(),
        path: path.trim().to_string(),
    })
}

/// The stable key of a catalog tag, for the edit map.
fn tag_key(state: &State<'_, AppState>, index: usize) -> Result<TagKey, String> {
    with_catalog(state, |c| {
        let e = c.entry(index).ok_or("tag index out of range")?;
        Ok((e.group.clone(), e.short.clone()))
    })
}

/// The pending edits for a catalog tag, cloned out of the lock.
fn pending_for(state: &State<'_, AppState>, key: &TagKey) -> Result<Vec<PendingEdit>, String> {
    let work = state.work.lock().map_err(|e| e.to_string())?;
    Ok(work.edits.get(key).cloned().unwrap_or_default())
}

/// The script override for a tag, if the mod has one.
fn script_for(
    state: &State<'_, AppState>,
    key: &TagKey,
) -> Result<Option<Vec<(String, String)>>, String> {
    let work = state.work.lock().map_err(|e| e.to_string())?;
    Ok(work.scripts.get(key).cloned())
}

#[tauri::command]
fn set_field(
    index: usize,
    path: String,
    value: String,
    state: State<'_, AppState>,
) -> Result<EditResult, String> {
    let key = tag_key(&state, index)?;
    let pending = pending_for(&state, &key)?;

    let result = with_catalog(&state, |c| {
        let file = patched_bytes(c, index, &pending)?;
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let tag = blam_tag::TagFile::parse(&file, Some(entry.chunk.length as usize))
            .map_err(|e| e.to_string())?;
        let layout = tag.layout().map_err(|e| e.to_string())?;
        let block = tag.read_data(&layout).map_err(|e| e.to_string())?;

        let target =
            blam_tag::patch::resolve(&layout, &file, &block, &path).map_err(|e| e.to_string())?;
        // A section-backed value resizes the tag, so it takes the rebuild path
        // rather than overwriting bytes.
        let resizes = target.section.is_some();
        let parsed = match target.type_name.as_str() {
            "string id" => blam_tag::Scalar::Text(value.trim_matches('"').to_string()),
            "tag reference" => parse_reference(&value)?,
            _ => {
                blam_tag::value::parse(&layout, &target.field, &value).map_err(|e| e.to_string())?
            }
        };
        let (out, applied) = if resizes {
            blam_tag::patch::set_text(&layout, &file, &block, &path, &parsed)
        } else {
            blam_tag::patch::set(&layout, &file, &block, &path, &parsed)
        }
        .map_err(|e| e.to_string())?;

        // Refuse the edit unless the result is still a tag that reads back.
        let after = blam_tag::TagFile::parse(&out, Some(out.len())).map_err(|e| e.to_string())?;
        let _ = resizes;
        let after_layout = after.layout().map_err(|e| e.to_string())?;
        let after_block = after.read_data(&after_layout).map_err(|e| e.to_string())?;
        let payload = after.data().ok_or("patched tag has no data section")?;
        if after_block.consumed != payload.size as usize {
            return Err("the edit left the tag unreadable and was discarded".to_string());
        }

        let a = &applied;
        Ok(EditResult {
            path: a.path.clone(),
            type_name: a.type_name.clone(),
            before: a.before.display(),
            after: a.after.display(),
            changed_bytes: a.changed.len(),
        })
    })?;

    // Only record once it is known to work.
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    let list = work.edits.entry(key).or_default();
    list.retain(|e| e.path != path);
    list.push(PendingEdit { path, value });
    work.autosave()?;
    Ok(result)
}

/// Work out everything a live poke needs, while the catalog lock is held.
///
/// Kept separate from the poke itself so the slow part — which may scan the
/// whole process — runs on a worker thread with owned data rather than holding
/// state across an await.
fn build_live_job(
    state: &State<'_, AppState>,
    index: usize,
    path: &str,
    value: &str,
) -> Result<live::Job, String> {
    let key = tag_key(state, index)?;
    let pending = pending_for(state, &key)?;
    with_catalog(state, |c| {
        let file = patched_bytes(c, index, &pending)?;
        let entry = c.entry(index).ok_or("tag index out of range")?;
        // Everything derived from `file` borrows it, so the whole analysis
        // happens in this block and hands back owned values; `file` itself is
        // only moved into the job once those borrows are gone.
        let (region, span, bytes) = {
            let tag = blam_tag::TagFile::parse(&file, Some(entry.chunk.length as usize))
                .map_err(|e| e.to_string())?;
            let layout = tag.layout().map_err(|e| e.to_string())?;
            let block = tag.read_data(&layout).map_err(|e| e.to_string())?;
            let target = blam_tag::patch::resolve(&layout, &file, &block, path)
                .map_err(|e| e.to_string())?;

            // A section-backed value lives in a trailing section, so changing it
            // moves every byte after it. In a file that is fine — the tag is
            // rebuilt. In a live heap buffer there is nowhere for them to go.
            if target.section.is_some() {
                return Err(format!(
                    "{} is a {} stored in a trailing section, so changing it resizes the tag. \
                     That cannot be poked into a running game — test it with a rebuild.",
                    path, target.type_name
                ));
            }

            let parsed =
                blam_tag::value::parse(&layout, &target.field, value).map_err(|e| e.to_string())?;
            let (patched, _) = blam_tag::patch::set(&layout, &file, &block, path, &parsed)
                .map_err(|e| e.to_string())?;

            // Only the data section is resident per tag; the header and layout
            // tables are not, so searching anywhere else is wasted effort.
            let data = tag.data().ok_or("this tag has no data section")?;
            let start = data.content.as_ptr() as usize - file.as_ptr() as usize;
            let span = target.file_offset..target.file_offset + target.size;
            let bytes = patched
                .get(span.clone())
                .ok_or("the field lies outside the tag payload")?
                .to_vec();
            (start..start + data.content.len(), span, bytes)
        };

        Ok(live::Job {
            key: key.clone(),
            payload: file,
            region,
            span,
            bytes,
        })
    })
}

#[tauri::command]
fn live_status(live: State<'_, live::Live>) -> live::Status {
    live.status()
}

#[tauri::command]
fn live_forget(live: State<'_, live::Live>) {
    live.forget()
}

/// Push one edit into the running game.
///
/// Slow the first time a tag is touched, because the address has to be found by
/// scanning; instant afterwards. Runs on a worker so the window stays alive
/// while that happens.
#[tauri::command]
async fn live_poke(
    index: usize,
    path: String,
    value: String,
    state: State<'_, AppState>,
    live: State<'_, live::Live>,
) -> Result<live::Poked, String> {
    let job = build_live_job(&state, index, &path, &value)?;
    let live = live.inner().clone();
    tauri::async_runtime::spawn_blocking(move || live.poke(&job))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn revert_field(index: usize, path: String, state: State<'_, AppState>) -> Result<usize, String> {
    let key = tag_key(&state, index)?;
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    let list = work.edits.entry(key.clone()).or_default();
    list.retain(|e| e.path != path);
    let left = list.len();
    if left == 0 {
        work.edits.remove(&key);
    }
    work.autosave()?;
    Ok(left)
}

#[tauri::command]
fn revert_tag(index: usize, state: State<'_, AppState>) -> Result<(), String> {
    let key = tag_key(&state, index)?;
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    work.edits.remove(&key);
    work.autosave()?;
    Ok(())
}

/// Write the tag, with its pending edits applied, to a file the user chose.
///
/// This is how an edit leaves the editor: the game's containers are read-only,
/// so there is nowhere to save in place. The bytes are game content and stay
/// wherever the user puts them.
#[tauri::command]
fn export_tag(index: usize, dest: String, state: State<'_, AppState>) -> Result<usize, String> {
    let key = tag_key(&state, index)?;
    let pending = pending_for(&state, &key)?;
    with_catalog(&state, |c| {
        let out = patched_bytes(c, index, &pending)?;
        std::fs::write(&dest, &out).map_err(|e| format!("{dest}: {e}"))?;
        Ok(out.len())
    })
}

#[tauri::command]
fn read_tag(index: usize, state: State<'_, AppState>) -> Result<TagView, String> {
    let key = tag_key(&state, index)?;
    let pending = pending_for(&state, &key)?;
    let edited: Vec<String> = pending.iter().map(|e| e.path.clone()).collect();

    with_catalog(&state, |c| {
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let path = entry.path.clone();
        let group = entry.group.clone();
        let chunk_size = entry.chunk.length;
        let file = patched_bytes(c, index, &pending)?;

        let tag = blam_tag::TagFile::parse(&file, Some(entry.chunk.length as usize))
            .map_err(|e| format!("{path}: {e}"))?;
        let layout = tag.layout().map_err(|e| format!("{path}: {e}"))?;
        let tag = &tag;
        let layout = &layout;
        {
            let data_size = tag.data().map(|d| d.size).unwrap_or(0);

            // The value tree is the point of the view. When it cannot be read
            // the reason is shown rather than silently falling back to schema.
            let (fields, data_exact, error) = match tag.read_data(layout) {
                Ok(block) => {
                    let exact = block.consumed == data_size as usize;
                    (
                        blam_tag::view::root(layout, &block)
                            .iter()
                            .map(to_view)
                            .collect::<Vec<_>>(),
                        exact,
                        None,
                    )
                }
                Err(e) => (Vec::new(), false, Some(e.to_string())),
            };

            let node_count = count(&fields);

            Ok(TagView {
                path,
                group,
                four_cc: tag.header.group.as_str(),
                version: tag.header.group_version,
                chunk_size,
                data_size,
                data_exact,
                error,
                node_count,
                edited,
                fields,
            })
        }
    })
}

fn count(nodes: &[NodeView]) -> usize {
    nodes.len() + nodes.iter().map(|n| count(&n.children)).sum::<usize>()
}

/// Find a tag by group and reference path. Reference paths come out of tag
/// bodies backslash-separated and in authored case; catalog shorts are
/// slash-separated container paths. The cooker also inserts a `_Generated_`
/// directory the authored paths never mention (a scenario references
/// `levels\halo1\solo\a30\holdouts`, the container holds
/// `Levels/Halo1/Solo/A30/_Generated_/holdouts`), so that segment is ignored
/// on both sides.
fn tag_by_ref(c: &Catalog, group: &str, path: &str) -> Option<usize> {
    let normalize = |p: &str| p.replace('\\', "/").to_ascii_lowercase().replace("/_generated_/", "/");
    let want = normalize(path);
    c.tags
        .iter()
        .position(|t| t.group == group && normalize(&t.short) == want)
}

/// The reflection schema for this game build, dumped by UE4SS and shipped
/// with the editor. Cooked packages serialize properties unversioned, so
/// nothing Unreal-side can be read without it. A game update changes the
/// schema; the errors that follow are loud rather than silent.
static USMAP: std::sync::OnceLock<Option<ue_asset::Usmap>> = std::sync::OnceLock::new();

fn usmap() -> Result<&'static ue_asset::Usmap, String> {
    USMAP
        .get_or_init(|| {
            static BYTES: &[u8] = include_bytes!("../../../../defs/ue/Meteorite-2607-CU3.usmap");
            ue_asset::Usmap::parse(BYTES).ok()
        })
        .as_ref()
        .ok_or_else(|| "the bundled usmap does not parse".to_string())
}

/// One section of a mesh, with its material resolved as far as it goes.
#[derive(Serialize)]
struct MeshSection {
    first_index: u32,
    num_triangles: u32,
    material: i32,
}

#[derive(Serialize)]
struct MeshMaterial {
    slot: String,
    /// Texture catalog index of the base colour, when the chain resolved.
    texture: Option<usize>,
    texture_path: Option<String>,
    material_path: Option<String>,
}

#[derive(Serialize)]
struct MeshHeader {
    path: String,
    verts: u32,
    tris: u32,
    sections: Vec<MeshSection>,
    materials: Vec<MeshMaterial>,
    /// Which LOD the buffers come from; higher means further from full
    /// detail (LOD0 slots replaced by Nanite carry no classic buffers).
    lod: usize,
    skeletal: bool,
}

/// A cooked mesh's renderable geometry, packed as `"UMSH"`, a u32 JSON
/// length, the JSON header, then positions, normals, uvs and indices.
#[tauri::command]
fn read_mesh(index: usize, state: State<'_, AppState>) -> Result<tauri::ipc::Response, String> {
    with_catalog(&state, |c| {
        let entry = c.meshes.get(index).ok_or("mesh index out of range")?;
        if entry.skeletal {
            return Err(format!(
                "{} is a skeletal mesh; the reader only handles static meshes so far",
                entry.short
            ));
        }
        let usmap = usmap()?;
        let data = c.read_mesh_uasset(index)?;
        let ubulk = c.read_mesh_ubulk(index)?;
        let package = ue_asset::zen::Package::parse(&data).map_err(|e| e.to_string())?;
        let scripts = c.script_objects().ok_or("no script-object table")?;
        let export = package
            .exports
            .iter()
            .position(|e| scripts.leaf(e.class) == Some("StaticMesh"))
            .ok_or_else(|| format!("{} has no StaticMesh export", entry.short))?;
        let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;
        let ctx = ue_asset::unversioned::Ctx {
            usmap,
            names: &package.names,
        };
        let mesh = ue_asset::mesh::parse_static_mesh(&ctx, bytes, ubulk.as_deref())
            .map_err(|e| e.to_string())?;

        // Chase each material slot to a base-colour texture.
        let materials: Vec<MeshMaterial> = mesh
            .materials
            .iter()
            .map(|(slot, object)| {
                let material_path = ue_asset::material::import_package_name(&package, *object);
                let mut texture_path = None;
                let mut query = material_path.clone();
                for _ in 0..4 {
                    let Some(pkg_name) = query.take() else { break };
                    let Some(bytes) = c.read_package(&pkg_name) else { break };
                    let Ok(mi_package) = ue_asset::zen::Package::parse(&bytes) else { break };
                    let Some(mi_export) = mi_package.exports.iter().position(|e| {
                        scripts.leaf(e.class) == Some("MaterialInstanceConstant")
                    }) else {
                        break;
                    };
                    let Ok(mi_bytes) = mi_package.export_data(&bytes, mi_export) else { break };
                    let mi_ctx = ue_asset::unversioned::Ctx {
                        usmap,
                        names: &mi_package.names,
                    };
                    let Ok(info) =
                        ue_asset::material::parse_material_instance(&mi_ctx, &mi_package, mi_bytes)
                    else {
                        break;
                    };
                    if let Some(base) = ue_asset::material::base_color(&info.textures) {
                        texture_path = Some(base.package.clone());
                        break;
                    }
                    query = info.parent;
                }
                let texture = texture_path.as_deref().and_then(|p| c.texture_by_package(p));
                MeshMaterial {
                    slot: slot.clone(),
                    texture,
                    texture_path,
                    material_path,
                }
            })
            .collect();

        // The best LOD that actually carries buffers.
        let (lod_index, lod) = mesh
            .lods
            .iter()
            .enumerate()
            .find(|(_, l)| !l.indices.is_empty())
            .ok_or("no LOD carries geometry (Nanite-only mesh?)")?;

        let header = MeshHeader {
            path: entry.short.clone(),
            verts: (lod.positions.len() / 3) as u32,
            tris: (lod.indices.len() / 3) as u32,
            sections: lod
                .sections
                .iter()
                .map(|s| MeshSection {
                    first_index: s.first_index,
                    num_triangles: s.num_triangles,
                    material: s.material_index,
                })
                .collect(),
            materials,
            lod: lod_index,
            skeletal: false,
        };
        let json = serde_json::to_vec(&header).map_err(|e| e.to_string())?;
        let mut out = Vec::with_capacity(
            12 + json.len()
                + lod.positions.len() * 4
                + lod.normals.len() * 4
                + lod.uvs.len() * 4
                + lod.indices.len() * 4,
        );
        out.extend_from_slice(b"UMSH");
        out.extend_from_slice(&(json.len() as u32).to_le_bytes());
        out.extend_from_slice(&json);
        while out.len() % 4 != 0 {
            out.push(0);
        }
        for v in lod
            .positions
            .iter()
            .chain(&lod.normals)
            .chain(&lod.uvs)
        {
            out.extend_from_slice(&v.to_le_bytes());
        }
        for i in &lod.indices {
            out.extend_from_slice(&i.to_le_bytes());
        }
        Ok(tauri::ipc::Response::new(out))
    })
}

/// The level's collision world, as the binary payload `geometry::sbsp_world`
/// packs. Binary because a level is millions of triangles: holdouts packs to
/// ~50 MB, which JSON-over-IPC would triple and then parse.
#[tauri::command]
fn read_sbsp_world(index: usize, state: State<'_, AppState>) -> Result<tauri::ipc::Response, String> {
    with_catalog(&state, |c| {
        let entry = c.entry(index).ok_or("tag index out of range")?;
        if entry.group != "scenario_structure_bsp" {
            return Err(format!("{} is not a structure bsp", entry.short));
        }
        let file = c.read_tag(index)?;
        Ok(tauri::ipc::Response::new(geometry::sbsp_world(&file)?))
    })
}

/// A scenario's placements with everything resolved for drawing: BSP catalog
/// indices, and each palette entry chased through its object tag to the hlmt
/// whose geometry `read_model_geometry` serves.
#[derive(Serialize)]
struct ScenarioWorldView {
    layout: geometry::ScenarioLayout,
    /// Catalog index per `layout.bsps` entry.
    bsp_indices: Vec<Option<usize>>,
    /// Catalog index of the hlmt per palette entry, per category.
    palette_models: Vec<Vec<Option<usize>>>,
}

#[tauri::command]
fn read_scenario_layout(
    index: usize,
    state: State<'_, AppState>,
) -> Result<ScenarioWorldView, String> {
    with_catalog(&state, |c| {
        let entry = c.entry(index).ok_or("tag index out of range")?;
        if entry.group != "scenario" {
            return Err(format!("{} is not a scenario", entry.short));
        }
        let key = (entry.group.clone(), entry.short.clone());
        let pending = pending_for(&state, &key)?;
        let file = patched_bytes(c, index, &pending)?;
        let layout = geometry::scenario_layout(&file)?;

        let bsp_indices = layout
            .bsps
            .iter()
            .map(|p| tag_by_ref(c, "scenario_structure_bsp", p))
            .collect();
        let palette_models = layout
            .categories
            .iter()
            .map(|cat| {
                cat.palette
                    .iter()
                    .map(|path| {
                        let oi = tag_by_ref(c, cat.group, path)?;
                        let object = c.read_tag(oi).ok()?;
                        let hlmt = geometry::object_model_ref(&object)?;
                        tag_by_ref(c, "model", &hlmt)
                    })
                    .collect()
            })
            .collect();
        Ok(ScenarioWorldView {
            layout,
            bsp_indices,
            palette_models,
        })
    })
}

/// Geometry for the model viewer: collision meshes plus the skeleton that
/// poses them.
///
/// Accepts a `model` (hlmt), `collision_model`, or `skeleton_model` tag and
/// assembles whichever halves it can reach: an hlmt names both explicitly; a
/// bare half looks for its sibling at the same tag path.
#[tauri::command]
fn read_model_geometry(
    index: usize,
    state: State<'_, AppState>,
) -> Result<geometry::ModelGeometry, String> {
    with_catalog(&state, |c| {
        // Each tag is read as the user currently sees it: with its own
        // pending edits applied.
        let read = |i: usize| -> Result<Vec<u8>, String> {
            let e = c.entry(i).ok_or("tag index out of range")?;
            let key = (e.group.clone(), e.short.clone());
            let pending = pending_for(&state, &key)?;
            patched_bytes(c, i, &pending)
        };

        let entry = c.entry(index).ok_or("tag index out of range")?;
        let short = entry.short.clone();
        let (coll, skel) = match entry.group.as_str() {
            "model" => {
                let file = read(index)?;
                let mut coll = None;
                let mut skel = None;
                for r in geometry::model_refs(&file)? {
                    let found = tag_by_ref(c, r.group, &r.path);
                    match r.group {
                        "collision_model" => coll = found,
                        _ => skel = found,
                    }
                }
                (coll, skel)
            }
            "collision_model" => (Some(index), tag_by_ref(c, "skeleton_model", &short)),
            "skeleton_model" => (tag_by_ref(c, "collision_model", &short), Some(index)),
            other => return Err(format!("a {other} tag has no viewable geometry")),
        };
        if coll.is_none() && skel.is_none() {
            return Err("no collision_model or skeleton_model reachable from this tag".into());
        }

        let mut geo = geometry::ModelGeometry::default();
        if let Some(ci) = coll {
            let file = read(ci)?;
            geo.meshes = geometry::collision_meshes(&file)?;
            geo.collision = c.entry(ci).map(|e| e.short.clone());
        }
        if let Some(si) = skel {
            let file = read(si)?;
            let (nodes, marker_groups) = geometry::skeleton(&file)?;
            geo.nodes = nodes;
            geo.marker_groups = marker_groups;
            geo.skeleton = c.entry(si).map(|e| e.short.clone());
        }
        Ok(geo)
    })
}

/// One package a tag imports, resolved to something openable when possible.
#[derive(Serialize)]
struct LinkedAsset {
    /// Full package name, e.g. `/Game/Blueprints/.../BP_EliteBipedActor`.
    package: String,
    /// `tag`, `texture`, or `asset` for kinds the editor cannot open yet.
    kind: &'static str,
    /// Catalog index for `tag` and `texture` kinds.
    index: Option<usize>,
    /// Display label: the package tail, plus the group for tags.
    label: String,
}

/// The packages a tag imports: other tags, and the Unreal presentation
/// assets (Blueprints, and for some tags textures) it binds to.
#[tauri::command]
fn tag_links(index: usize, state: State<'_, AppState>) -> Result<Vec<LinkedAsset>, String> {
    with_catalog(&state, |c| {
        let uasset = c.read_tag_uasset(index)?;
        let mut out = Vec::new();
        for package in zen::imported_package_names(&uasset) {
            let tail = package.rsplit('/').next().unwrap_or(&package).to_string();
            if let Some(ti) = c.tag_by_package(&package) {
                let (short, group) = tail.rsplit_once('-').unwrap_or((tail.as_str(), ""));
                out.push(LinkedAsset {
                    package,
                    kind: "tag",
                    index: Some(ti),
                    label: format!("{short} ({group})"),
                });
            } else if let Some(xi) = c.texture_by_package(&package) {
                out.push(LinkedAsset {
                    package,
                    kind: "texture",
                    index: Some(xi),
                    label: tail,
                });
            } else {
                out.push(LinkedAsset {
                    package,
                    kind: "asset",
                    index: None,
                    label: tail,
                });
            }
        }
        // Openable things first, then the rest, each alphabetical.
        out.sort_by(|a, b| (a.index.is_none(), &a.label).cmp(&(b.index.is_none(), &b.label)));
        Ok(out)
    })
}

#[derive(Serialize)]
struct TextureSummary {
    index: usize,
    /// Content-relative path without extension.
    path: String,
    /// Bulk payload size; zero when the texture keeps its mips inline.
    size: u64,
}

#[derive(Serialize)]
struct TextureView {
    path: String,
    width: u32,
    height: u32,
    format: String,
    mip: u32,
    num_mips: u32,
    /// Assembled image as a data URI, ready for an `<img>`.
    png: String,
    /// Why this texture's format cannot be swapped, when it cannot. `None`
    /// means the Replace action is available.
    unsupported: Option<String>,
    /// Whether the open mod replaces this texture. When it does, `png` above
    /// is the replacement image the recipe holds rather than what shipped.
    replaced: bool,
}

/// What a swap did, reported once, when it is applied.
///
/// It is not carried on `TextureView`: producing these numbers means
/// re-encoding every tile of every mip, which is the expensive half of a
/// swap and not something reopening a texture should pay for.
#[derive(Serialize)]
struct SwapReport {
    /// How many mips were re-encoded.
    mips: u32,
    /// Payload bytes that differ from the shipped ones.
    changed: usize,
    /// Total size of the payload those bytes sit in.
    payload: usize,
    /// Mean per-channel readback error out of 255. Block compression costs a
    /// few levels, so this is never quite zero; it is surfaced because a big
    /// number is the signal that something is wrong.
    error: f64,
    /// The rewritten payload decoded again — what the game will actually
    /// show, as a data URI.
    png: String,
}

/// List one directory of the virtual asset filesystem.
#[tauri::command]
fn list_dir(path: String, state: State<'_, AppState>) -> Result<Vec<catalog::DirEntry>, String> {
    with_catalog(&state, |c| Ok(c.list_dir(&path)))
}

/// Search the whole virtual filesystem by path substring.
#[tauri::command]
fn search_files(
    query: String,
    state: State<'_, AppState>,
) -> Result<Vec<catalog::DirEntry>, String> {
    with_catalog(&state, |c| Ok(c.search_files(&query, MAX_ROWS)))
}

#[tauri::command]
fn list_textures(query: String, state: State<'_, AppState>) -> Result<Vec<TextureSummary>, String> {
    with_catalog(&state, |c| {
        Ok(c.search_textures(&query, MAX_ROWS)
            .into_iter()
            .map(|(index, t)| TextureSummary {
                index,
                path: t.short.clone(),
                size: t.ubulk.map(|(_, ch)| ch.length).unwrap_or(0),
            })
            .collect())
    })
}

/// Decode a texture and return it as PNG. Large textures are served at the
/// first mip at or below `max_dim` to keep the IPC payload sane.
fn decode_texture(
    c: &Catalog,
    index: usize,
    max_dim: u32,
) -> Result<(textures::Texture, textures::TextureImage), String> {
    let uasset = c.read_texture_uasset(index)?;
    let header = textures::zen_header_size(&uasset).ok_or("not a zen package")?;
    let tex = textures::parse_texture(&uasset[header..])?;
    // A texture whose mips are all inline has no bulk file at all.
    let ubulk = c.read_texture_ubulk(index).unwrap_or_default();
    let mut mip = 0;
    while mip + 1 < tex.num_mips {
        let (w, h) = tex.mip_dims(mip);
        if w.max(h) <= max_dim {
            break;
        }
        mip += 1;
    }
    let img = textures::assemble_mip(&tex, &ubulk, mip)?;
    Ok((tex, img))
}

/// Read the Blam script a scenario carries.
///
/// Goes through `patched_bytes` like the field commands do, so a scenario with
/// unexported edits reports the script section of the tag as it now stands
/// rather than as it shipped.
#[tauri::command]
fn read_scripts(index: usize, state: State<'_, AppState>) -> Result<scripts::ScriptView, String> {
    let key = tag_key(&state, index)?;
    let pending = pending_for(&state, &key)?;
    let script = script_for(&state, &key)?;
    with_catalog(&state, |c| {
        // Shows the tag as the mod leaves it, so an applied script edit is what
        // comes back rather than what the game shipped.
        let file = patched_with_script(c, index, &pending, script.as_deref())?;
        let entry = c.entry(index).ok_or("tag index out of range")?;
        if entry.group != "scenario" {
            return Err(format!("{} tags carry no script", entry.group));
        }
        let path = entry.short.clone();
        let tag = blam_tag::TagFile::parse(&file, Some(entry.chunk.length as usize))
            .map_err(|e| e.to_string())?;
        let layout = tag.layout().map_err(|e| e.to_string())?;
        let block = tag.read_data(&layout).map_err(|e| e.to_string())?;
        scripts::view(path, &layout, &block, &file, script.is_some())
    })
}

/// Compile edited script source without changing anything.
///
/// The editor calls this as the user types so diagnostics are live; nothing is
/// recorded and no tag is touched.
#[tauri::command]
fn compile_scripts(
    index: usize,
    files: Vec<(String, String)>,
    state: State<'_, AppState>,
) -> Result<scripts::CompileReport, String> {
    with_catalog(&state, |c| {
        let file = c.read_tag(index)?;
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let len = entry.chunk.length as usize;
        scripts::compile_into(&file, len, &files).map(|(_, report)| report)
    })
}

/// Record edited script source as part of the mod.
///
/// Compiles first and refuses to record anything that does not build, so the
/// recipe never holds a state the bake would choke on.
#[tauri::command]
fn set_scripts(
    index: usize,
    files: Vec<(String, String)>,
    state: State<'_, AppState>,
) -> Result<scripts::CompileReport, String> {
    let key = tag_key(&state, index)?;
    let pending = pending_for(&state, &key)?;

    let report = with_catalog(&state, |c| {
        let patched = patched_with_script(c, index, &pending, Some(&files))?;
        let file = c.read_tag(index)?;
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let (_, mut report) =
            scripts::compile_into(&file, entry.chunk.length as usize, &files)?;
        report.tag_bytes = patched.len();
        Ok(report)
    })?;
    if !report.ok {
        return Ok(report);
    }

    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    work.scripts.insert(key.clone(), files.clone());
    save_scripts(&work)?;
    if let Some(p) = &work.project {
        p.write_script_files(&key.0, &key.1, &files)?;
    }
    Ok(report)
}

/// Drop a scenario's script override, restoring what the game ships.
#[tauri::command]
fn revert_scripts(index: usize, state: State<'_, AppState>) -> Result<(), String> {
    let key = tag_key(&state, index)?;
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    work.scripts.remove(&key);
    save_scripts(&work)?;
    if let Some(p) = &work.project {
        p.remove_script_files(&key.0, &key.1)?;
    }
    Ok(())
}

/// Mirror the script overrides into `edits.json`.
fn save_scripts(work: &Workbench) -> Result<(), String> {
    let Some(p) = &work.project else {
        return Ok(());
    };
    let scripts: Vec<project::SavedScript> = work
        .scripts
        .keys()
        .map(|(group, tag)| project::SavedScript {
            group: group.clone(),
            tag: tag.clone(),
        })
        .collect();
    p.save_edits_and_scripts(&work.saved_edits(), &scripts)
}

/// Write one of a scenario's source files to disk as `.hsc`.
///
/// `name` is the source file's name as `read_scripts` lists it, or
/// `<decompiled>` for the rendered tree when the scenario shipped no source.
#[tauri::command]
fn export_script(
    index: usize,
    name: String,
    dest: String,
    state: State<'_, AppState>,
) -> Result<usize, String> {
    let view = read_scripts(index, state)?;
    let file = view
        .source_files
        .iter()
        .find(|f| f.name == name)
        .ok_or_else(|| format!("no source file named {name:?}"))?;
    std::fs::write(&dest, file.text.as_bytes()).map_err(|e| e.to_string())?;
    Ok(file.text.len())
}

/// Render one script back from the compiled tree, for comparing against the
/// source the scenario shipped with.
#[tauri::command]
fn decompile_script(
    index: usize,
    name: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    with_catalog(&state, |c| {
        let file = c.read_tag(index)?;
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let tag = blam_tag::TagFile::parse(&file, Some(entry.chunk.length as usize))
            .map_err(|e| e.to_string())?;
        let layout = tag.layout().map_err(|e| e.to_string())?;
        let block = tag.read_data(&layout).map_err(|e| e.to_string())?;
        scripts::decompile_one(&layout, &block, &file, &name)
    })
}

fn data_uri(png: &[u8]) -> String {
    use base64::Engine;
    format!(
        "data:image/png;base64,{}",
        base64::engine::general_purpose::STANDARD.encode(png)
    )
}

#[tauri::command]
fn read_texture(index: usize, state: State<'_, AppState>) -> Result<TextureView, String> {
    // The two locks are taken one after the other, never nested, so this can
    // never be the half of a deadlock that holds `work` and wants `catalog`.
    let path = with_catalog(&state, |c| {
        Ok(c.textures
            .get(index)
            .ok_or("texture index out of range")?
            .short
            .clone())
    })?;
    let replacement = {
        let work = state.work.lock().map_err(|e| e.to_string())?;
        work.textures.get(&path).cloned()
    };
    with_catalog(&state, |c| {
        let (tex, img) = decode_texture(c, index, 4096)?;
        // A replaced texture shows the image the recipe holds, so reopening
        // it shows the repaint rather than what the game shipped. It is the
        // source PNG, not a readback: the readback costs a full re-encode and
        // is reported when the swap is applied.
        let png = match &replacement {
            Some(bytes) => bytes.clone(),
            None => textures::to_png(&img)?,
        };
        Ok(TextureView {
            path,
            width: tex.width,
            height: tex.height,
            format: img.format.clone(),
            mip: img.mip,
            num_mips: tex.num_mips,
            png: data_uri(&png),
            unsupported: textures::encode::encodable(&tex.format).err(),
            replaced: replacement.is_some(),
        })
    })
}

/// Replace a texture's pixels with a PNG on disk.
///
/// The swap is proven here — re-encoded, packed-length checked and decoded
/// back — but nothing is written to the game: the recipe stores the image,
/// and containers are baked at test, export or publish time like every other
/// edit. Runs off the UI thread because re-encoding every tile of every mip
/// of a large virtual texture takes seconds.
#[tauri::command]
async fn swap_texture(
    index: usize,
    image: String,
    state: State<'_, AppState>,
) -> Result<SwapReport, String> {
    let png = std::fs::read(&image).map_err(|e| format!("{image}: {e}"))?;
    let img = textures::encode::Image::from_png(&png)?;

    let (path, tex, ubulk) = with_catalog(&state, |c| {
        let entry = c.textures.get(index).ok_or("texture index out of range")?;
        let path = entry.short.clone();
        let uasset = c.read_texture_uasset(index)?;
        let header = textures::zen_header_size(&uasset).ok_or("not a zen package")?;
        let tex = textures::parse_texture(&uasset[header..])?;
        let ubulk = c.read_texture_ubulk(index)?;
        Ok((path, tex, ubulk))
    })?;

    let out = tauri::async_runtime::spawn_blocking(move || {
        textures::encode::swap(&tex, &ubulk, &img).map(|s| {
            let payload = s.ubulk.len();
            (s.mips, s.changed, s.error, payload, textures::to_png(&s.decoded))
        })
    })
    .await
    .map_err(|e| e.to_string())??;
    let (mips, changed, error, payload, decoded) = out;

    {
        let mut work = state.work.lock().map_err(|e| e.to_string())?;
        work.textures.insert(path.clone(), png);
        if let Some(p) = &work.project {
            p.write_texture_file(&path, &work.textures[&path])?;
        }
        save_textures(&work)?;
    }

    Ok(SwapReport {
        mips,
        changed,
        payload,
        error,
        png: data_uri(&decoded?),
    })
}

/// Drop a texture swap from the recipe, restoring what the game ships.
#[tauri::command]
fn revert_texture(index: usize, state: State<'_, AppState>) -> Result<(), String> {
    let path = with_catalog(&state, |c| {
        Ok(c.textures
            .get(index)
            .ok_or("texture index out of range")?
            .short
            .clone())
    })?;
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    work.textures.remove(&path);
    if let Some(p) = &work.project {
        p.remove_texture_file(&path)?;
    }
    save_textures(&work)
}

/// Mirror the texture list to `edits.json`, when a project is open.
fn save_textures(work: &Workbench) -> Result<(), String> {
    let Some(p) = &work.project else {
        return Ok(());
    };
    let textures: Vec<project::SavedTexture> = work
        .textures
        .keys()
        .map(|path| project::SavedTexture { path: path.clone() })
        .collect();
    p.save_edits_and_textures(&work.saved_edits(), &textures)
}

#[derive(Serialize)]
struct SoundSummary {
    index: usize,
    /// Path below `WwiseAudio/`.
    path: String,
    /// Language folder, or `null` for audio shared across languages.
    language: Option<String>,
    size: u64,
    /// The Wwise event that plays this, when one claims it. Wwise names media
    /// numerically, so without this a row is just an ID.
    event: Option<String>,
}

#[derive(Serialize)]
struct SoundView {
    path: String,
    language: Option<String>,
    /// Stored size of the whole `.wem`.
    size: u64,
    /// Header fields, absent for a sound bank rather than a media file.
    info: Option<sounds::WemInfo>,
    /// Why the header could not be read, when it could not be.
    error: Option<String>,
    /// Every Wwise event that plays this media, and the sources behind them.
    events: Vec<EventRef>,
}

/// One Wwise event that plays a media file.
#[derive(Serialize)]
struct EventRef {
    name: String,
    package: String,
    /// The authored `.wav` files the event draws from. Which one this
    /// particular media is cannot be told from the package alone, so the whole
    /// set is listed.
    sources: Vec<String>,
}

#[tauri::command]
fn list_sounds(query: String, state: State<'_, AppState>) -> Result<Vec<SoundSummary>, String> {
    with_catalog(&state, |c| {
        let rows: Vec<(usize, String, Option<String>, u64)> = c
            .search_sounds(&query, MAX_ROWS)
            .into_iter()
            .map(|(index, s)| {
                (
                    index,
                    s.short.clone(),
                    s.language.clone(),
                    s.entry.uncompressed_size,
                )
            })
            .collect();
        Ok(rows
            .into_iter()
            .map(|(index, path, language, size)| SoundSummary {
                event: c.sound_label(index).map(str::to_string),
                index,
                path,
                language,
                size,
            })
            .collect())
    })
}

/// Describe one Wwise audio file from its header alone.
///
/// Only the leading bytes are read: a listing must not pull whole megabytes
/// out of the pak just to show a duration.
#[tauri::command]
fn read_sound(index: usize, state: State<'_, AppState>) -> Result<SoundView, String> {
    with_catalog(&state, |c| {
        let s = c.sound(index).ok_or("sound index out of range")?;
        let path = s.short.clone();
        let language = s.language.clone();
        let size = s.entry.uncompressed_size;
        // A `.bnk` is a bank of events, not a RIFF media file; report it as
        // such instead of surfacing a parse failure.
        let (info, error) = if path.ends_with(".bnk") {
            (None, Some("sound bank, not a media file".to_string()))
        } else {
            match c
                .read_sound(index, Some(sounds::HEADER_BYTES))
                .and_then(|d| sounds::parse_wem(&d))
            {
                Ok(info) => (Some(info), None),
                Err(e) => (None, Some(e)),
            }
        };
        let events = match crate::wwise::media_id_of_path(&path) {
            Some(id) => c
                .names()
                .events_for(id)
                .map(|e| EventRef {
                    name: e.name.clone(),
                    package: e.package.clone(),
                    sources: e.sources.clone(),
                })
                .collect(),
            None => Vec::new(),
        };
        Ok(SoundView {
            path,
            language,
            size,
            info,
            error,
            events,
        })
    })
}

#[derive(Serialize)]
struct SoundAudio {
    /// The stream as a data URI, ready for an `<audio>` element.
    src: String,
    /// How it was produced, e.g. the codebook library used.
    via: &'static str,
    bytes: usize,
}

/// Build a playable stream for one sound.
///
/// The webview decodes Ogg Vorbis natively, so the backend's job is only to
/// rebuild the Wwise stream into one — no samples are decoded here.
#[tauri::command]
fn play_sound(index: usize, state: State<'_, AppState>) -> Result<SoundAudio, String> {
    use base64::Engine;
    with_catalog(&state, |c| {
        let wem = c.read_sound(index, None)?;
        let out = decode::to_playable(&wem)?;
        Ok(SoundAudio {
            src: format!(
                "data:{};base64,{}",
                out.mime,
                base64::engine::general_purpose::STANDARD.encode(&out.bytes)
            ),
            via: out.via,
            bytes: out.bytes.len(),
        })
    })
}

/// Write a sound's raw `.wem` to a file the user chose.
///
/// The payload is copied out byte for byte; decoding Wwise Vorbis is not
/// implemented yet, so this is what a converter needs as input.
#[tauri::command]
fn export_sound(index: usize, dest: String, state: State<'_, AppState>) -> Result<usize, String> {
    with_catalog(&state, |c| {
        let data = c.read_sound(index, None)?;
        std::fs::write(&dest, &data).map_err(|e| format!("{dest}: {e}"))?;
        Ok(data.len())
    })
}

/// Write a texture's top mip as PNG to a file the user chose.
#[tauri::command]
fn export_texture(index: usize, dest: String, state: State<'_, AppState>) -> Result<usize, String> {
    with_catalog(&state, |c| {
        let (_, img) = decode_texture(c, index, u32::MAX)?;
        let png = textures::to_png(&img)?;
        std::fs::write(&dest, &png).map_err(|e| format!("{dest}: {e}"))?;
        Ok(png.len())
    })
}

/// One edited field in the project change list.
#[derive(Serialize)]
struct FieldChange {
    field: String,
    /// The value the mod sets, as the user typed it.
    value: String,
    /// The shipped value, when the field still resolves.
    before: Option<String>,
    /// True when the tag or field no longer resolves in this installation —
    /// usually the game updated underneath the recipe.
    stale: bool,
}

/// Every edit the project makes to one tag.
#[derive(Serialize)]
struct TagChange {
    group: String,
    tag: String,
    /// Catalog index in the open installation, when the tag still exists.
    index: Option<usize>,
    edits: Vec<FieldChange>,
}

/// One texture the mod repaints, for the project change list.
#[derive(Serialize)]
struct TextureChange {
    path: String,
    /// Catalog index in the open installation, so the panel can open it.
    /// `None` means the game no longer ships this texture.
    index: Option<usize>,
    /// Size of the replacement image the recipe holds.
    bytes: usize,
}

#[derive(Serialize)]
struct ProjectView {
    root: String,
    meta: project::Meta,
    changes: Vec<TagChange>,
    /// Textures the mod replaces.
    textures: Vec<TextureChange>,
    /// Files a test install left in the Paks folder, so the panel can show
    /// that the mod is currently installed for testing.
    test_files: Vec<String>,
}

/// The project change list, with each edit resolved against the open
/// installation so the panel can show shipped → modded values and flag
/// anything the last game update broke.
fn changes_for(c: &Catalog, edits: &BTreeMap<TagKey, Vec<PendingEdit>>) -> Vec<TagChange> {
    edits
        .iter()
        .map(|((group, tag), pending)| {
            let index = c.tag_index(group, tag);
            let resolved = index.and_then(|i| {
                let file = c.read_tag(i).ok()?;
                let parsed = blam_tag::TagFile::parse(&file, Some(file.len())).ok()?;
                let layout = parsed.layout().ok()?;
                let block = parsed.read_data(&layout).ok()?;
                Some(
                    pending
                        .iter()
                        .map(
                            |e| match blam_tag::patch::resolve(&layout, &file, &block, &e.path) {
                                Ok(t) => FieldChange {
                                    field: e.path.clone(),
                                    value: e.value.clone(),
                                    before: Some(t.current.display()),
                                    stale: false,
                                },
                                Err(_) => FieldChange {
                                    field: e.path.clone(),
                                    value: e.value.clone(),
                                    before: None,
                                    stale: true,
                                },
                            },
                        )
                        .collect::<Vec<_>>(),
                )
            });
            let edits = resolved.unwrap_or_else(|| {
                pending
                    .iter()
                    .map(|e| FieldChange {
                        field: e.path.clone(),
                        value: e.value.clone(),
                        before: None,
                        stale: true,
                    })
                    .collect()
            });
            TagChange {
                group: group.clone(),
                tag: tag.clone(),
                index,
                edits,
            }
        })
        .collect()
}

/// The current project rendered for the UI, or `None` when none is open.
fn project_view(state: &State<'_, AppState>) -> Result<Option<ProjectView>, String> {
    let (root, meta, edits, swaps) = {
        let work = state.work.lock().map_err(|e| e.to_string())?;
        match &work.project {
            None => return Ok(None),
            Some(p) => (
                p.root.display().to_string(),
                p.meta.clone(),
                work.edits.clone(),
                work.textures.clone(),
            ),
        }
    };
    let (changes, textures, test_files) = with_catalog(state, |c| {
        let textures = swaps
            .iter()
            .map(|(path, png)| TextureChange {
                path: path.clone(),
                index: c.texture_index(path),
                bytes: png.len(),
            })
            .collect();
        Ok((
            changes_for(c, &edits),
            textures,
            modpack::test_files(c.paks()),
        ))
    })?;
    Ok(Some(ProjectView {
        root,
        meta,
        changes,
        textures,
        test_files,
    }))
}

#[tauri::command]
fn project_status(state: State<'_, AppState>) -> Result<Option<ProjectView>, String> {
    project_view(&state)
}

#[tauri::command]
fn project_new(
    dir: String,
    name: String,
    slug: String,
    version: String,
    summary: String,
    state: State<'_, AppState>,
) -> Result<ProjectView, String> {
    let meta = project::Meta {
        schema_version: 1,
        name: name.trim().to_string(),
        slug,
        version,
        summary: summary.trim().to_string(),
    };
    let p = project::Project::create(std::path::Path::new(&dir), meta)?;
    {
        let mut work = state.work.lock().map_err(|e| e.to_string())?;
        work.project = Some(p);
        // Any work done before the project existed becomes its first content:
        // "start a mod from what I've been trying out" is the natural flow,
        // and that includes texture swaps and scripts, not only field edits.
        work.mirror_all()?;
    }
    install::remember_project(Some(&dir));
    project_view(&state)?.ok_or_else(|| "the new project did not open".to_string())
}

#[tauri::command]
fn project_open(dir: String, state: State<'_, AppState>) -> Result<ProjectView, String> {
    let (p, saved) = project::Project::open(std::path::Path::new(&dir))?;
    // Everything the recipe holds comes back into the workbench, not just the
    // field edits: a bake reads the workbench, so anything left behind here is
    // silently dropped from the mod.
    let mut scripts: BTreeMap<TagKey, Vec<(String, String)>> = BTreeMap::new();
    for s in p.load_scripts()? {
        let files = p.read_script_files(&s.group, &s.tag)?;
        if !files.is_empty() {
            scripts.insert((s.group, s.tag), files);
        }
    }
    let mut textures: BTreeMap<String, Vec<u8>> = BTreeMap::new();
    for t in p.load_textures()? {
        let png = p.read_texture_file(&t.path)?;
        textures.insert(t.path, png);
    }
    {
        let mut work = state.work.lock().map_err(|e| e.to_string())?;
        let mut edits: BTreeMap<TagKey, Vec<PendingEdit>> = BTreeMap::new();
        for e in saved {
            edits
                .entry((e.group, e.tag))
                .or_default()
                .push(PendingEdit {
                    path: e.field,
                    value: e.value,
                });
        }
        work.edits = edits;
        work.scripts = scripts;
        work.textures = textures;
        work.project = Some(p);
    }
    install::remember_project(Some(&dir));
    project_view(&state)?.ok_or_else(|| "the project did not open".to_string())
}

/// Close the project. Edits are already on disk — autosave runs on every
/// change — so this only clears the workbench.
#[tauri::command]
fn project_close(state: State<'_, AppState>) -> Result<(), String> {
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    work.project = None;
    work.edits.clear();
    work.scripts.clear();
    work.textures.clear();
    install::remember_project(None);
    Ok(())
}

#[tauri::command]
fn project_set_meta(
    name: String,
    slug: String,
    version: String,
    summary: String,
    state: State<'_, AppState>,
) -> Result<ProjectView, String> {
    {
        let mut work = state.work.lock().map_err(|e| e.to_string())?;
        let p = work.project.as_mut().ok_or("no project is open")?;
        let before = p.meta.clone();
        p.meta.name = name.trim().to_string();
        p.meta.slug = slug;
        p.meta.version = version;
        p.meta.summary = summary.trim().to_string();
        if let Err(e) = p.save_meta() {
            p.meta = before;
            return Err(e);
        }
    }
    project_view(&state)?.ok_or_else(|| "no project is open".to_string())
}

/// Revert edits by identity rather than catalog index, so the change list
/// can drop edits whose tag no longer exists in this installation.
#[tauri::command]
fn project_revert(
    group: String,
    tag: String,
    field: Option<String>,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let key = (group, tag);
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    match field {
        Some(f) => {
            if let Some(list) = work.edits.get_mut(&key) {
                list.retain(|e| e.path != f);
                if list.is_empty() {
                    work.edits.remove(&key);
                }
            }
        }
        None => {
            work.edits.remove(&key);
        }
    }
    work.autosave()?;
    Ok(())
}

/// The project folder from the last session, if it still is one.
#[tauri::command]
fn last_project() -> Option<String> {
    install::recall_project()
        .filter(|dir| std::path::Path::new(dir).join(project::MOD_FILE).is_file())
}

/// Every project edit resolved against the open installation and proven to
/// produce a tag that still reads back exactly. Anything stale fails loudly
/// here — a mod must never silently ship half its recipe.
///
/// Also returns per-edit warnings. The one that exists today: a `string id`
/// set to text the game's string table does not already contain makes the
/// game reject the whole tag — verified in game 2026-08-02, where a marker
/// string turned the assault rifle into the pistol-fallback. The editor
/// cannot see the game's string table, so it warns rather than blocks.
fn resolved_edits(
    c: &Catalog,
    edits: &BTreeMap<TagKey, Vec<PendingEdit>>,
    scripts: &BTreeMap<TagKey, Vec<(String, String)>>,
    textures: &BTreeMap<String, Vec<u8>>,
) -> Result<(Vec<modpack::ResolvedEdit>, Vec<String>), String> {
    let mut out = Vec::new();
    let mut warnings = Vec::new();
    resolve_textures(c, textures, &mut out)?;
    // A scenario may be changed only by its script, with no field edits at all,
    // so the two sets are walked together rather than iterating `edits` alone.
    let keys: std::collections::BTreeSet<&TagKey> = edits.keys().chain(scripts.keys()).collect();
    for key in keys {
        let (group, tag) = key;
        let no_edits = Vec::new();
        let pending = edits.get(key).unwrap_or(&no_edits);
        let script = scripts.get(key).map(Vec::as_slice);
        if pending.is_empty() && script.is_none() {
            continue;
        }
        let label = format!("{tag}.{group}");
        let index = c.tag_index(group, tag).ok_or_else(|| {
            format!("{label}: not present in this installation — revert the stale edit first")
        })?;
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let original = c.read_tag(index)?;

        // Every edit in the recipe must land; one failing to resolve means
        // the game updated underneath it.
        {
            let parsed = blam_tag::TagFile::parse(&original, Some(original.len()))
                .map_err(|e| format!("{label}: {e}"))?;
            let layout = parsed.layout().map_err(|e| format!("{label}: {e}"))?;
            let block = parsed
                .read_data(&layout)
                .map_err(|e| format!("{label}: {e}"))?;
            let mut missing = 0usize;
            for e in pending {
                match blam_tag::patch::resolve(&layout, &original, &block, &e.path) {
                    Ok(target) => {
                        if target.type_name == "string id" && target.current.display() != e.value {
                            warnings.push(format!(
                                "{label}: \"{}\" sets a string id. A string the game does not \
                                 already know makes it reject the whole tag (the weapon simply \
                                 vanishes in game) — test before sharing.",
                                e.path
                            ));
                        }
                    }
                    Err(_) => missing += 1,
                }
            }
            if missing != 0 {
                return Err(format!(
                    "{label}: {missing} of {} edits no longer resolve — the game may have \
                     updated; revert the stale edits first",
                    pending.len()
                ));
            }
        }

        let patched = patched_bytes(c, index, pending)?;
        if patched == original {
            continue;
        }
        // And the result must still be a tag that walks exactly.
        {
            let parsed = blam_tag::TagFile::parse(&patched, Some(patched.len()))
                .map_err(|e| format!("{label}: {e}"))?;
            let layout = parsed.layout().map_err(|e| format!("{label}: {e}"))?;
            let block = parsed
                .read_data(&layout)
                .map_err(|e| format!("{label}: {e}"))?;
            let payload = patched.len();
            let expected = parsed.data().map(|d| d.size as usize).unwrap_or(payload);
            if block.consumed != expected {
                return Err(format!(
                    "{label}: the patched tag does not read back exactly"
                ));
            }
        }
        out.push(modpack::ResolvedEdit {
            label,
            container: entry.container,
            chunk: entry.chunk,
            original_len: original.len(),
            patched,
        });
    }
    if out.is_empty() {
        return Err("the mod changes nothing yet — edit a tag first".into());
    }
    Ok((out, warnings))
}

/// Re-encode every replaced texture against the installation being packed.
///
/// The recipe stores the author's PNG, not a cooked payload, so this is where
/// the image meets the dimensions and pixel format the player's game actually
/// ships — the same reason a field edit is re-applied rather than stored as
/// patched bytes. A swap replaces the texture's `.ubulk` chunk and nothing
/// else, so it rides the ordinary container path.
pub fn resolve_textures(
    c: &Catalog,
    textures: &BTreeMap<String, Vec<u8>>,
    out: &mut Vec<modpack::ResolvedEdit>,
) -> Result<(), String> {
    for (path, png) in textures {
        let index = c.texture_index(path).ok_or_else(|| {
            format!("{path}: not present in this installation — revert the stale swap first")
        })?;
        let entry = c.textures.get(index).ok_or("texture index out of range")?;
        // The bulk payload can live in a different container from the header
        // package, and it is the bulk chunk that gets overridden.
        let (container, chunk) = entry
            .ubulk
            .ok_or_else(|| format!("{path}: keeps every mip inline, so it has no bulk chunk"))?;

        let uasset = c.read_texture_uasset(index)?;
        let header =
            textures::zen_header_size(&uasset).ok_or_else(|| format!("{path}: not a zen package"))?;
        let tex = textures::parse_texture(&uasset[header..]).map_err(|e| format!("{path}: {e}"))?;
        let ubulk = c.read_texture_ubulk(index)?;
        let img = textures::encode::Image::from_png(png).map_err(|e| format!("{path}: {e}"))?;
        let swap =
            textures::encode::swap(&tex, &ubulk, &img).map_err(|e| format!("{path}: {e}"))?;

        out.push(modpack::ResolvedEdit {
            label: format!("{path}.ubulk"),
            container,
            chunk,
            original_len: ubulk.len(),
            patched: swap.ubulk,
        });
    }
    Ok(())
}

#[derive(Serialize)]
struct ExportView {
    /// Where the `.mjolnir` archive was written.
    archive: String,
    size: u64,
    containers: Vec<String>,
    chunk_count: usize,
    resized: bool,
    /// The archive carries an author signature from this device's key.
    signed: bool,
    signer_fingerprint: Option<String>,
    warnings: Vec<String>,
}

/// Bake the project and write the `.mjolnir` archive into `<project>/build`.
///
/// `allow_sign` is false only when publishing could not register the device
/// key: a signature the hub cannot bind to the uploader would reject the
/// release, so the archive honestly ships unsigned instead.
fn export_archive(
    state: &State<'_, AppState>,
    allow_sign: bool,
) -> Result<(ExportView, std::path::PathBuf, project::Meta), String> {
    let (root, meta, (edits, scripts, swaps)) = {
        let work = state.work.lock().map_err(|e| e.to_string())?;
        let p = work.project.as_ref().ok_or("no project is open")?;
        (
            p.root.clone(),
            p.meta.clone(),
            (
                work.edits.clone(),
                work.scripts.clone(),
                work.textures.clone(),
            ),
        )
    };
    // The device key signs every archive it can; the author identity rides
    // along when a publish has cached it. Failing to sign is a warning, not
    // a failed export — unsigned archives stay valid during the transition.
    let identity = if allow_sign {
        Some(keystore::load_or_create())
    } else {
        None
    };
    let author =
        install::recall_author().map(|(id, username)| mjolnir_sign::Author { id, username });
    with_catalog(state, |c| {
        let (resolved, mut warnings) = resolved_edits(c, &edits, &scripts, &swaps)?;
        let baked = modpack::bake(c, &meta.slug, resolved)?;
        let build_dir = root.join("build");
        modpack::write_and_verify(&build_dir, &baked, c.oodle_paths())?;

        let (signer, signer_fingerprint) = match &identity {
            Some(Ok(identity)) => (
                Some(modpack::SignContext {
                    identity,
                    author: author.clone(),
                }),
                Some(identity.fingerprint()),
            ),
            Some(Err(e)) => {
                warnings.push(format!("The archive is unsigned: {e}"));
                (None, None)
            }
            None => (None, None),
        };

        let archive = build_dir.join(format!("{}-{}.mjolnir", meta.slug, meta.version));
        let readme = root.join("README.md");
        let size = modpack::write_archive(
            &archive,
            &meta,
            &baked,
            readme.is_file().then(|| readme.as_path()),
            signer,
        )?;

        let resized = baked.iter().any(|b| b.built.resized());
        if size > modpack::MAX_ARCHIVE_BYTES {
            warnings.push(format!(
                "The archive is {size} bytes, over the hub's 50 MiB limit — it will be \
                 rejected on upload."
            ));
        }
        let view = ExportView {
            archive: archive.display().to_string(),
            size,
            containers: baked.iter().map(|b| b.basename.clone()).collect(),
            chunk_count: baked.iter().map(|b| b.built.expect.len()).sum(),
            resized,
            signed: signer_fingerprint.is_some(),
            signer_fingerprint,
            warnings,
        };
        Ok((view, archive, meta.clone()))
    })
}

#[tauri::command]
fn project_export(state: State<'_, AppState>) -> Result<ExportView, String> {
    export_archive(&state, true).map(|(view, _, _)| view)
}

#[derive(Serialize)]
struct TestView {
    files: Vec<String>,
    resized: bool,
    warnings: Vec<String>,
}

/// Bake the project and install it into the Paks folder for an in-game test.
#[tauri::command]
fn project_test(state: State<'_, AppState>) -> Result<TestView, String> {
    let (meta, (edits, scripts, swaps)) = {
        let work = state.work.lock().map_err(|e| e.to_string())?;
        let p = work.project.as_ref().ok_or("no project is open")?;
        (
            p.meta.clone(),
            (
                work.edits.clone(),
                work.scripts.clone(),
                work.textures.clone(),
            ),
        )
    };
    with_catalog(&state, |c| {
        let (resolved, warnings) = resolved_edits(c, &edits, &scripts, &swaps)?;
        let baked = modpack::bake(c, &meta.slug, resolved)?;
        let resized = baked.iter().any(|b| b.built.resized());
        let files = modpack::install_test(c.paks(), &baked, c.oodle_paths())?;
        Ok(TestView {
            files,
            resized,
            warnings,
        })
    })
}

/// Remove the test install. Returns how many files were removed.
#[tauri::command]
fn project_untest(state: State<'_, AppState>) -> Result<usize, String> {
    with_catalog(&state, |c| modpack::remove_test(c.paks()))
}

#[tauri::command]
fn hub_status() -> hub::HubStatus {
    hub::HubStatus {
        base: hub::base_url(),
        has_key: install::recall_hub_key().is_some(),
        username: install::recall_author().map(|(_, username)| username),
    }
}

/// Store (or clear, with an empty string) the hub API key.
///
/// The fallback for someone who would rather mint a key by hand than link;
/// the identity behind a pasted key is unknown until the first publish looks
/// it up, so any cached name is dropped rather than left to mislead.
#[tauri::command]
fn hub_set_key(key: String) -> Result<(), String> {
    install::remember_hub_key(&key)?;
    install::forget_author();
    Ok(())
}

/// Begin linking this editor to a hub account.
#[tauri::command]
fn hub_link_start() -> Result<hub::LinkStart, String> {
    hub::auth_start()
}

/// Check whether the link has been approved yet.
#[tauri::command]
fn hub_link_poll() -> Result<hub::LinkPoll, String> {
    hub::auth_poll()
}

/// Forget the stored key. Revoking it is a hub-side action.
#[tauri::command]
fn hub_unlink() -> Result<(), String> {
    hub::unlink()
}

/// Bake, sign, archive and publish the project to the hub, returning the
/// scan verdict. A rejection comes back as data — the findings are the point.
#[tauri::command]
fn project_publish(
    changelog: String,
    state: State<'_, AppState>,
) -> Result<hub::PublishView, String> {
    let key = install::recall_hub_key()
        .ok_or("not linked to a hub account — link one from the publish panel first")?;

    // Register the device key and refresh the author identity before baking,
    // so the signature embeds the right account and the hub can bind the key
    // to the uploader. Only a missing key (DPAPI unavailable) degrades to an
    // unsigned publish; a *failed registration* is an error, because signing
    // with an unregistered key would get the release rejected as foreign.
    let allow_sign = match keystore::load_or_create() {
        Ok(identity) => {
            use base64::Engine;
            let author = hub::whoami(&key)?;
            install::remember_author(&author.id, &author.username);
            let public_key =
                base64::engine::general_purpose::STANDARD.encode(identity.public_key());
            let label = std::env::var("COMPUTERNAME").unwrap_or_else(|_| "this device".into());
            hub::register_key(&key, &public_key, &label)?;
            true
        }
        Err(_) => false,
    };

    let (view, archive, meta) = export_archive(&state, allow_sign)?;
    if view.size > modpack::MAX_ARCHIVE_BYTES {
        return Err(format!(
            "the archive is {} bytes, over the hub's 50 MiB limit",
            view.size
        ));
    }
    hub::publish(&key, &meta, &archive, &changelog)
}

#[derive(Serialize)]
struct SigningStatus {
    /// This device's key fingerprint; None until a key is first created.
    fingerprint: Option<String>,
    /// Whether the key is registered to the hub account; None when either
    /// the key or the API key is missing, or the hub was unreachable.
    registered: Option<bool>,
    /// The label registration uses — the machine name.
    label: String,
}

#[tauri::command]
fn signing_status() -> SigningStatus {
    let fingerprint = keystore::existing().map(|i| i.fingerprint());
    let label = std::env::var("COMPUTERNAME").unwrap_or_else(|_| "this device".into());
    let registered = match (&fingerprint, install::recall_hub_key()) {
        (Some(fp), Some(key)) => hub::key_registered(&key, fp).ok(),
        _ => None,
    };
    SigningStatus {
        fingerprint,
        registered,
        label,
    }
}

#[tauri::command]
fn read_tag_bytes(
    index: usize,
    limit: usize,
    state: State<'_, AppState>,
) -> Result<Vec<u8>, String> {
    with_catalog(&state, |c| {
        let buf = c.read_tag(index)?;
        Ok(buf.into_iter().take(limit.min(64 * 1024)).collect())
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(AppState::default())
        .manage(live::Live::default())
        .invoke_handler(tauri::generate_handler![
            changelog::fetch_changelog,
            detect_install,
            open_install,
            list_groups,
            list_tags,
            search_tags,
            read_tag,
            read_tag_bytes,
            read_model_geometry,
            read_sbsp_world,
            read_scenario_layout,
            read_mesh,
            set_field,
            live_status,
            live_forget,
            live_poke,
            revert_field,
            revert_tag,
            export_tag,
            project_status,
            project_new,
            project_open,
            project_close,
            project_set_meta,
            project_revert,
            last_project,
            project_export,
            project_test,
            project_untest,
            project_publish,
            hub_status,
            hub_set_key,
            hub_link_start,
            hub_link_poll,
            hub_unlink,
            signing_status,
            list_textures,
            read_texture,
            read_scripts,
            decompile_script,
            export_script,
            compile_scripts,
            set_scripts,
            revert_scripts,
            export_texture,
            swap_texture,
            revert_texture,
            list_sounds,
            read_sound,
            export_sound,
            play_sound,
            tag_links,
            list_dir,
            search_files,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
