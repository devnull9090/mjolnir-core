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
use tauri::{Manager, State};

pub mod bnk;
pub mod catalog;
pub mod census;
pub mod changelog;
pub mod decode;
pub mod geometry;
pub mod hub;
pub mod install;
pub mod keystore;
pub mod live;
pub mod modpack;
pub mod present;
pub mod project;
pub mod refcache;
pub mod scripts;
pub mod secret;
pub mod tagcache;
pub mod tagtable;
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
    /// Tags the mod adds, keyed like everything else by `(group, short)`.
    /// A new tag's own field edits live in `edits` under the same key and
    /// apply over the donor's bytes.
    new_tags: BTreeMap<TagKey, NewTagSpec>,
    /// Undo and redo per tag: snapshots of the tag's edit list as it stood
    /// before each change. In memory only — the project file holds the
    /// current recipe, not its history.
    history: BTreeMap<TagKey, Journal>,
    /// When set, every change to `edits` is mirrored to the project folder.
    project: Option<project::Project>,
}

/// One tag's undo and redo stacks. Each entry is a whole edit list, so undoing
/// restores exactly what the tag's recipe was, element ops included.
#[derive(Default)]
struct Journal {
    undo: Vec<Vec<PendingEdit>>,
    redo: Vec<Vec<PendingEdit>>,
}

/// How far back one tag's journal keeps. Field edits are a few bytes each, so
/// this is generous rather than tight.
const HISTORY_LIMIT: usize = 200;

/// How deep a tag's undo and redo stacks are, for the UI to enable buttons.
#[derive(Clone, Copy, Default, Serialize)]
struct HistoryView {
    undo: usize,
    redo: usize,
}

/// Where a new tag's bytes come from and how it binds to Unreal.
#[derive(Clone)]
struct NewTagSpec {
    /// The shipped tag of the same group it was cloned from.
    from: String,
    /// Package path of the Unreal asset to bind to; `None` keeps the donor's.
    asset_reference: Option<String>,
}

impl Workbench {
    /// Remember a tag's edit list as it stands, so the change about to be made
    /// can be undone. A new change forks history: whatever was undone before
    /// it can no longer be redone.
    fn remember(&mut self, key: &TagKey) {
        let snapshot = self.edits.get(key).cloned().unwrap_or_default();
        let journal = self.history.entry(key.clone()).or_default();
        journal.undo.push(snapshot);
        if journal.undo.len() > HISTORY_LIMIT {
            journal.undo.remove(0);
        }
        journal.redo.clear();
    }

    /// Put a tag's edit list back to the snapshot before the last change.
    /// Returns false when there is nothing to undo.
    fn undo(&mut self, key: &TagKey) -> bool {
        let Some(journal) = self.history.get_mut(key) else {
            return false;
        };
        let Some(previous) = journal.undo.pop() else {
            return false;
        };
        let current = self.edits.get(key).cloned().unwrap_or_default();
        journal.redo.push(current);
        self.set_edits(key, previous);
        true
    }

    /// Re-apply the last undone change. Returns false when there is none.
    fn redo(&mut self, key: &TagKey) -> bool {
        let Some(journal) = self.history.get_mut(key) else {
            return false;
        };
        let Some(next) = journal.redo.pop() else {
            return false;
        };
        let current = self.edits.get(key).cloned().unwrap_or_default();
        journal.undo.push(current);
        self.set_edits(key, next);
        true
    }

    fn history_of(&self, key: &TagKey) -> HistoryView {
        self.history.get(key).map_or(HistoryView::default(), |j| HistoryView {
            undo: j.undo.len(),
            redo: j.redo.len(),
        })
    }

    /// Replace a tag's edit list; an empty list means no entry at all, which
    /// is how "no edits" is spelled everywhere else.
    fn set_edits(&mut self, key: &TagKey, list: Vec<PendingEdit>) {
        if list.is_empty() {
            self.edits.remove(key);
        } else {
            self.edits.insert(key.clone(), list);
        }
    }

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

    /// The new tags for the project file, in map order.
    fn saved_new_tags(&self) -> Vec<project::SavedNewTag> {
        self.new_tags
            .iter()
            .map(|((group, tag), spec)| project::SavedNewTag {
                group: group.clone(),
                tag: tag.clone(),
                from: spec.from.clone(),
                asset_reference: spec.asset_reference.clone(),
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
        p.save_all(
            &self.saved_edits(),
            &scripts,
            &textures,
            &self.saved_new_tags(),
        )
    }
}

#[derive(Default)]
struct AppState {
    catalog: Mutex<Option<Catalog>>,
    work: Mutex<Workbench>,
}

#[derive(Clone, Serialize)]
pub struct PendingEdit {
    pub path: String,
    /// The text the user typed, re-parsed against the layout on each read.
    pub value: String,
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
    /// How much of this tag's editing can be undone or redone.
    history: HistoryView,
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
    let mut catalog = Catalog::open(&paks, &oodle)?;
    {
        // The workbench outlives the catalog: reopening the installation must
        // not lose the tags the open project adds.
        let work = state.work.lock().map_err(|e| e.to_string())?;
        restore_new_tags(&mut catalog, &work.new_tags);
    }
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

/// The value a pending edit's op string names, when its path resolves to a
/// block: `add`, `remove <i>` or `duplicate <i>`.
fn parse_op(value: &str) -> Option<blam_tag::patch::ElementOp> {
    use blam_tag::patch::ElementOp;
    let v = value.trim();
    if v == "add" {
        return Some(ElementOp::Add);
    }
    if let Some(n) = v.strip_prefix("remove ") {
        return n.trim().parse().ok().map(ElementOp::Remove);
    }
    if let Some(n) = v.strip_prefix("duplicate ") {
        return n.trim().parse().ok().map(ElementOp::Duplicate);
    }
    if let Some(n) = v.strip_prefix("insert ") {
        return n.trim().parse().ok().map(ElementOp::Insert);
    }
    None
}

/// One pending edit as the replay applied it — or did not.
pub struct Outcome {
    pub path: String,
    pub value: String,
    pub type_name: String,
    /// The value the field held just before this edit applied, displayed.
    pub before: Option<String>,
    /// False when the edit no longer resolves against these bytes, which
    /// usually means a game update moved the field. Skipped, not fatal:
    /// the command that cares makes it loud.
    pub applied: bool,
}

/// What one pending edit asks of the replay, decided by what its path
/// resolves to.
enum Step {
    /// A fixed-width value, overwritten in place; batchable.
    InPlace(blam_tag::Scalar),
    /// A section-backed value; rebuilds the tag around the new content.
    Text(blam_tag::Scalar),
    /// An element added, duplicated or removed; rebuilds the tag.
    Elements(blam_tag::patch::ElementOp),
}

fn classify(
    layout: &blam_tag::Layout<'_>,
    target: &blam_tag::patch::Target,
    value: &str,
) -> Option<Step> {
    if target.type_name == "block" {
        return parse_op(value).map(Step::Elements);
    }
    if target.section.is_some() {
        return match target.type_name.as_str() {
            "string id" => Some(Step::Text(blam_tag::Scalar::Text(
                value.trim_matches('"').to_string(),
            ))),
            "tag reference" => parse_reference(value).ok().map(Step::Text),
            _ => None,
        };
    }
    blam_tag::value::parse(layout, &target.field, value)
        .ok()
        .map(Step::InPlace)
}

/// Apply every pending edit to `bytes`, in the order they were recorded,
/// reporting per edit what happened.
///
/// Runs of in-place edits are applied as one batch, so a recipe of plain field
/// edits costs what it always did. An edit that resizes the tag — a section-
/// backed value, or an element count change — is applied on its own and the
/// tag re-read behind it, because everything after it may have moved, and an
/// edit recorded later may only resolve inside an element an earlier op added.
///
/// An edit that no longer resolves is skipped and reported in its outcome; a
/// mod must keep applying in the editor even when a game update broke one
/// field, and export is where staleness turns into a hard error.
pub fn apply_pending(
    bytes: Vec<u8>,
    pending: &[PendingEdit],
) -> Result<(Vec<u8>, Vec<Outcome>), String> {
    let mut out = bytes;
    let mut outcomes: Vec<Outcome> = Vec::with_capacity(pending.len());
    let mut i = 0usize;
    while i < pending.len() {
        let next = {
            let tag =
                blam_tag::TagFile::parse(&out, Some(out.len())).map_err(|e| e.to_string())?;
            let layout = tag.layout().map_err(|e| e.to_string())?;
            let block = tag.read_data(&layout).map_err(|e| e.to_string())?;

            let mut batch: Vec<(String, blam_tag::Scalar)> = Vec::new();
            let mut resize: Option<(usize, Step, blam_tag::patch::Target)> = None;
            while i < pending.len() {
                let e = &pending[i];
                let Ok(target) = blam_tag::patch::resolve(&layout, &out, &block, &e.path)
                else {
                    outcomes.push(Outcome {
                        path: e.path.clone(),
                        value: e.value.clone(),
                        type_name: String::new(),
                        before: None,
                        applied: false,
                    });
                    i += 1;
                    continue;
                };
                match classify(&layout, &target, &e.value) {
                    None => {
                        outcomes.push(Outcome {
                            path: e.path.clone(),
                            value: e.value.clone(),
                            type_name: target.type_name.clone(),
                            before: None,
                            applied: false,
                        });
                        i += 1;
                    }
                    Some(Step::InPlace(v)) => {
                        outcomes.push(Outcome {
                            path: e.path.clone(),
                            value: e.value.clone(),
                            type_name: target.type_name.clone(),
                            before: Some(target.current.display()),
                            applied: true,
                        });
                        batch.push((e.path.clone(), v));
                        i += 1;
                    }
                    Some(step) => {
                        // A resizer ends the batch; it applies against these
                        // bytes only when nothing in-place is queued ahead of
                        // it, else the next pass picks it up.
                        if batch.is_empty() {
                            resize = Some((i, step, target));
                            i += 1;
                        }
                        break;
                    }
                }
            }

            if !batch.is_empty() {
                let (applied, _) = blam_tag::patch::set_many(&layout, &out, &block, &batch)
                    .map_err(|e| e.to_string())?;
                Some(applied)
            } else if let Some((at, step, target)) = resize {
                let e = &pending[at];
                // A block field's inline bytes open with its element count.
                let before = match &target.current {
                    blam_tag::Scalar::Raw(b) if b.len() >= 4 => {
                        let n = u32::from_le_bytes(b[0..4].try_into().unwrap());
                        Some(format!("{n} element(s)"))
                    }
                    other => Some(other.display()),
                };
                let applied = match step {
                    Step::Text(v) => {
                        blam_tag::patch::set_text(&layout, &out, &block, &e.path, &v)
                            .map(|(bytes, _)| bytes)
                            .ok()
                    }
                    Step::Elements(op) => {
                        blam_tag::patch::edit_elements(&layout, &out, &block, &e.path, op)
                            .map(|(bytes, _)| bytes)
                            .ok()
                    }
                    Step::InPlace(_) => unreachable!("in-place edits join the batch"),
                };
                outcomes.push(Outcome {
                    path: e.path.clone(),
                    value: e.value.clone(),
                    type_name: target.type_name.clone(),
                    before,
                    applied: applied.is_some(),
                });
                applied
            } else {
                None
            }
        };
        if let Some(n) = next {
            out = n;
        }
    }
    Ok((out, outcomes))
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
        let (patched, _) = apply_pending(out, pending)?;
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
    set_field_inner(index, path, value, &state, true)
}

/// Apply one field edit to the tag as it currently stands and record it once
/// it is known to work. `journal` is false when the caller journals a whole
/// batch itself (a paste), in which case an edit that changes nothing is not
/// recorded either.
fn set_field_inner(
    index: usize,
    path: String,
    value: String,
    state: &State<'_, AppState>,
    journal: bool,
) -> Result<EditResult, String> {
    let key = tag_key(state, index)?;
    let pending = pending_for(state, &key)?;

    let result = with_catalog(state, |c| {
        let file = patched_bytes(c, index, &pending)?;
        // The pending edits may already have resized the tag, so the shipped
        // chunk length no longer describes `file`; its own length does.
        let tag = blam_tag::TagFile::parse(&file, Some(file.len()))
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
    if !journal && result.changed_bytes == 0 {
        return Ok(result);
    }
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    if journal {
        work.remember(&key);
    }
    let list = work.edits.entry(key).or_default();
    list.retain(|e| e.path != path);
    list.push(PendingEdit { path, value });
    work.autosave()?;
    Ok(result)
}

/// Apply one element op to the tag as it currently stands, and record it once
/// it is known to work.
///
/// Recorded like any field edit — path and value — so the project file format
/// does not change; the value is the op (`add`, `remove 2`, `duplicate 0`) and
/// the replay recognises it by the path resolving to a block.
fn record_element_op(
    index: usize,
    path: String,
    value: String,
    state: &State<'_, AppState>,
    journal: bool,
) -> Result<EditResult, String> {
    let op = parse_op(&value).ok_or("unrecognised element operation")?;
    let key = tag_key(state, index)?;
    let pending = pending_for(state, &key)?;

    let result = with_catalog(state, |c| {
        let file = patched_bytes(c, index, &pending)?;
        let tag =
            blam_tag::TagFile::parse(&file, Some(file.len())).map_err(|e| e.to_string())?;
        let layout = tag.layout().map_err(|e| e.to_string())?;
        let block = tag.read_data(&layout).map_err(|e| e.to_string())?;

        let (out, applied) = blam_tag::patch::edit_elements(&layout, &file, &block, &path, op)
            .map_err(|e| e.to_string())?;

        // Refuse the edit unless the result is still a tag that reads back.
        let after =
            blam_tag::TagFile::parse(&out, Some(out.len())).map_err(|e| e.to_string())?;
        let after_layout = after.layout().map_err(|e| e.to_string())?;
        let after_block = after.read_data(&after_layout).map_err(|e| e.to_string())?;
        let payload = after.data().ok_or("patched tag has no data section")?;
        if after_block.consumed != payload.size as usize {
            return Err("the edit left the tag unreadable and was discarded".to_string());
        }

        Ok(EditResult {
            path: applied.path.clone(),
            type_name: applied.type_name.clone(),
            before: format!("{} element(s)", applied.before.display()),
            after: format!("{} element(s)", applied.after.display()),
            changed_bytes: applied.changed.len(),
        })
    })?;

    // Element ops stack rather than replace: two adds are two elements, so
    // the same-path dedupe a value edit gets would lose the first one.
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    if journal {
        work.remember(&key);
    }
    work.edits
        .entry(key)
        .or_default()
        .push(PendingEdit { path, value });
    work.autosave()?;
    Ok(result)
}

#[tauri::command]
fn add_element(index: usize, path: String, state: State<'_, AppState>) -> Result<EditResult, String> {
    record_element_op(index, path, "add".to_string(), &state, true)
}

/// Insert a fresh element at `at`, before the element now there.
#[tauri::command]
fn insert_element(
    index: usize,
    path: String,
    at: usize,
    state: State<'_, AppState>,
) -> Result<EditResult, String> {
    record_element_op(index, path, format!("insert {at}"), &state, true)
}

#[tauri::command]
fn remove_element(
    index: usize,
    path: String,
    element: usize,
    state: State<'_, AppState>,
) -> Result<EditResult, String> {
    record_element_op(index, path, format!("remove {element}"), &state, true)
}

#[tauri::command]
fn duplicate_element(
    index: usize,
    path: String,
    element: usize,
    state: State<'_, AppState>,
) -> Result<EditResult, String> {
    record_element_op(index, path, format!("duplicate {element}"), &state, true)
}

/// One step of an element recipe: set a field to text, or (`op`) apply an
/// element op to a nested block — `add` before the fields inside the element
/// it creates.
#[derive(Clone, Serialize, serde::Deserialize)]
struct RecipeStep {
    /// Relative to the element, e.g. `firing.rounds per second`.
    path: String,
    value: String,
    op: bool,
}

/// One element copied out of a block, as the recipe that recreates it. Field
/// values travel as the text the inspector accepts, so the recipe is readable
/// and applies through the same path a typed edit takes.
#[derive(Clone, Serialize, serde::Deserialize)]
struct ElementClip {
    group: String,
    /// The block definition's name; a paste target must be the same kind of
    /// block.
    block: String,
    /// Where it came from, for the UI.
    source: String,
    fields: Vec<RecipeStep>,
    /// Fields that cannot travel as text — raw data, for one.
    skipped: Vec<String>,
}

#[derive(Serialize)]
struct Skipped {
    path: String,
    reason: String,
}

/// What a paste did.
#[derive(Serialize)]
struct PasteReport {
    /// Index of the first element the paste created.
    element: usize,
    elements: usize,
    /// Fields set to a value they did not already hold.
    applied: usize,
    /// Fields whose value the recipe matched already, so nothing was recorded.
    unchanged: usize,
    skipped: Vec<Skipped>,
}

/// The text a field is set with to hold `value` — the same forms the inspector
/// and the CLI accept, chosen so they parse back to exactly this value.
fn recipe_text(value: &blam_tag::Scalar) -> Option<String> {
    use blam_tag::Scalar;
    Some(match value {
        Scalar::Int(v) => v.to_string(),
        Scalar::Real(_) | Scalar::Reals(_) | Scalar::Ints(_) | Scalar::Color(_) | Scalar::FourCc(_) => {
            value.display()
        }
        Scalar::Enum { raw, option } => option.clone().unwrap_or_else(|| raw.to_string()),
        Scalar::Flags { raw, .. } => format!("0x{raw:x}"),
        Scalar::BlockIndex(i) if *i < 0 => "none".to_string(),
        Scalar::BlockIndex(i) => i.to_string(),
        Scalar::Text(s) => s.clone(),
        Scalar::Reference { group, path } if path.is_empty() => {
            let _ = group;
            "none".to_string()
        }
        Scalar::Reference { group, path } => format!("{group}:{path}"),
        Scalar::Raw(_) | Scalar::Empty => return None,
    })
}

/// The node at a field path (`a.b[2].c`, escapes as [`blam_tag::patch::segments`]
/// reads them) in a tag's value tree.
fn find_node<'a>(
    nodes: &'a [blam_tag::view::Node],
    path: &str,
) -> Option<&'a blam_tag::view::Node> {
    let mut current = nodes;
    let mut found = None;
    for (name, index) in blam_tag::patch::segments(path) {
        let node = current.iter().find(|n| n.name.trim() == name)?;
        found = Some(node);
        current = match index {
            Some(i) => {
                let element = node.children.get(i)?;
                found = Some(element);
                &element.children
            }
            None => &node.children,
        };
    }
    found
}

/// The recipe for everything under `node`, paths relative to `prefix`.
/// Nested blocks are walked when `blocks` is set (an element clip) and
/// reported as skipped otherwise (a TSV row has nowhere to put them).
fn element_recipe(
    node: &blam_tag::view::Node,
    prefix: &str,
    blocks: bool,
    out: &mut Vec<RecipeStep>,
    skipped: &mut Vec<String>,
) {
    use blam_tag::view::Kind;
    for child in &node.children {
        let name = format!("{prefix}{}", blam_tag::patch::escape_segment(&child.name));
        match child.kind {
            Kind::Field => match recipe_text(&child.value) {
                Some(value) => out.push(RecipeStep {
                    path: name,
                    value,
                    op: false,
                }),
                None => skipped.push(format!("{name} ({})", child.type_name)),
            },
            Kind::Struct | Kind::Element => {
                element_recipe(child, &format!("{name}."), blocks, out, skipped)
            }
            Kind::Array => {
                for (k, element) in child.children.iter().enumerate() {
                    element_recipe(element, &format!("{name}[{k}]."), blocks, out, skipped);
                }
            }
            Kind::Block => {
                if blocks {
                    for (k, element) in child.children.iter().enumerate() {
                        out.push(RecipeStep {
                            path: name.clone(),
                            value: "add".into(),
                            op: true,
                        });
                        element_recipe(element, &format!("{name}[{k}]."), true, out, skipped);
                    }
                } else if !child.children.is_empty() {
                    skipped.push(format!("{name} (a nested block)"));
                }
            }
        }
    }
}

/// Read a tag's value tree as it currently stands, then hand the block node at
/// `path` to `f`.
fn with_block<T>(
    state: &State<'_, AppState>,
    index: usize,
    path: &str,
    f: impl FnOnce(&catalog::TagEntry, &blam_tag::view::Node) -> Result<T, String>,
) -> Result<T, String> {
    let key = tag_key(state, index)?;
    let pending = pending_for(state, &key)?;
    with_catalog(state, |c| {
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let file = patched_bytes(c, index, &pending)?;
        let tag = blam_tag::TagFile::parse(&file, Some(file.len())).map_err(|e| e.to_string())?;
        let layout = tag.layout().map_err(|e| e.to_string())?;
        let block = tag.read_data(&layout).map_err(|e| e.to_string())?;
        let nodes = blam_tag::view::root(&layout, &block);
        let node = find_node(&nodes, path).ok_or_else(|| format!("{path}: no such field"))?;
        if !matches!(node.kind, blam_tag::view::Kind::Block) {
            return Err(format!("{path} is not a block"));
        }
        f(entry, node)
    })
}

/// Copy one element of a block as a recipe the same kind of block can take.
#[tauri::command]
fn copy_element(
    index: usize,
    path: String,
    element: usize,
    state: State<'_, AppState>,
) -> Result<ElementClip, String> {
    with_block(&state, index, &path, |entry, node| {
        let el = node
            .children
            .get(element)
            .ok_or_else(|| format!("{path} has no element {element}"))?;
        let mut fields = Vec::new();
        let mut skipped = Vec::new();
        element_recipe(el, "", true, &mut fields, &mut skipped);
        Ok(ElementClip {
            group: entry.group.clone(),
            block: node.block_name.clone().unwrap_or_default(),
            source: format!(
                "{}[{element}] of {}",
                path,
                entry.short.rsplit('/').next().unwrap_or(&entry.short)
            ),
            fields,
            skipped,
        })
    })
}

/// Apply a recipe under `base` (`weapons[3]`), field by field, reporting
/// rather than failing on a field that will not take its value.
fn apply_recipe(
    state: &State<'_, AppState>,
    index: usize,
    base: &str,
    fields: &[RecipeStep],
) -> (usize, usize, Vec<Skipped>) {
    let mut applied = 0;
    let mut unchanged = 0;
    let mut skipped = Vec::new();
    for step in fields {
        let path = format!("{base}.{}", step.path);
        let result = if step.op {
            record_element_op(index, path.clone(), step.value.clone(), state, false)
        } else {
            set_field_inner(index, path.clone(), step.value.clone(), state, false)
        };
        match result {
            Ok(r) if r.changed_bytes == 0 && !step.op => unchanged += 1,
            Ok(_) => applied += 1,
            Err(reason) => skipped.push(Skipped { path, reason }),
        }
    }
    (applied, unchanged, skipped)
}

/// Paste a copied element into a block of the same kind: a fresh element at
/// `at` (or appended), then every field of the recipe. One undo step.
#[tauri::command]
fn paste_element(
    index: usize,
    path: String,
    at: Option<usize>,
    clip: ElementClip,
    state: State<'_, AppState>,
) -> Result<PasteReport, String> {
    let key = tag_key(&state, index)?;
    let (count, block) = with_block(&state, index, &path, |_, node| {
        Ok((
            node.count.unwrap_or(node.children.len() as u32) as usize,
            node.block_name.clone().unwrap_or_default(),
        ))
    })?;
    if block != clip.block {
        return Err(format!(
            "the clipboard holds a {} element from {}; this block holds {}",
            clip.block, clip.source, block
        ));
    }
    {
        let mut work = state.work.lock().map_err(|e| e.to_string())?;
        work.remember(&key);
    }
    let position = at.unwrap_or(count).min(count);
    let op = if position == count {
        "add".to_string()
    } else {
        format!("insert {position}")
    };
    record_element_op(index, path.clone(), op, &state, false)?;
    let (applied, unchanged, skipped) =
        apply_recipe(&state, index, &format!("{path}[{position}]"), &clip.fields);
    Ok(PasteReport {
        element: position,
        elements: 1,
        applied,
        unchanged,
        skipped,
    })
}

/// A block as tab-separated text: one column per field of an element (structs
/// flattened, nested blocks left out), one row per element.
#[tauri::command]
fn copy_block_tsv(index: usize, path: String, state: State<'_, AppState>) -> Result<String, String> {
    with_block(&state, index, &path, |_, node| {
        let first = node
            .children
            .first()
            .ok_or_else(|| format!("{path} has no elements to copy"))?;
        let mut header = Vec::new();
        let mut skipped = Vec::new();
        element_recipe(first, "", false, &mut header, &mut skipped);
        let columns: Vec<&str> = header.iter().map(|s| s.path.as_str()).collect();
        let clean = |s: &str| s.replace(['\t', '\n', '\r'], " ");
        let mut out = columns.join("\t");
        out.push('\n');
        for element in &node.children {
            let mut steps = Vec::new();
            let mut ignored = Vec::new();
            element_recipe(element, "", false, &mut steps, &mut ignored);
            let row: Vec<String> = columns
                .iter()
                .map(|c| {
                    steps
                        .iter()
                        .find(|s| s.path == *c)
                        .map(|s| clean(&s.value))
                        .unwrap_or_default()
                })
                .collect();
            out.push_str(&row.join("\t"));
            out.push('\n');
        }
        Ok(out)
    })
}

/// Fill a block from tab-separated text whose header names the fields: one new
/// element per row, `replace` first removing what is there. One undo step.
#[tauri::command]
fn paste_block_tsv(
    index: usize,
    path: String,
    tsv: String,
    replace: bool,
    state: State<'_, AppState>,
) -> Result<PasteReport, String> {
    let key = tag_key(&state, index)?;
    let mut lines = tsv
        .lines()
        .map(|l| l.trim_end_matches('\r'))
        .filter(|l| !l.trim().is_empty());
    let header: Vec<String> = lines
        .next()
        .ok_or("the text is empty")?
        .split('\t')
        .map(|h| h.trim().to_string())
        .collect();
    let rows: Vec<Vec<String>> = lines
        .map(|l| l.split('\t').map(|c| c.trim().to_string()).collect())
        .collect();
    if rows.is_empty() {
        return Err("the text has a header but no rows".into());
    }
    let mut count = with_block(&state, index, &path, |_, node| {
        Ok(node.count.unwrap_or(node.children.len() as u32) as usize)
    })?;
    {
        let mut work = state.work.lock().map_err(|e| e.to_string())?;
        work.remember(&key);
    }
    if replace {
        for _ in 0..count {
            record_element_op(index, path.clone(), "remove 0".into(), &state, false)?;
        }
        count = 0;
    }
    let first = count;
    let (mut applied, mut unchanged, mut skipped) = (0, 0, Vec::new());
    for row in &rows {
        record_element_op(index, path.clone(), "add".into(), &state, false)?;
        let fields: Vec<RecipeStep> = header
            .iter()
            .zip(row.iter())
            .filter(|(_, cell)| !cell.is_empty())
            .map(|(col, cell)| RecipeStep {
                path: col.clone(),
                value: cell.clone(),
                op: false,
            })
            .collect();
        let (a, u, mut sk) = apply_recipe(&state, index, &format!("{path}[{count}]"), &fields);
        applied += a;
        unchanged += u;
        skipped.append(&mut sk);
        count += 1;
    }
    Ok(PasteReport {
        element: first,
        elements: rows.len(),
        applied,
        unchanged,
        skipped,
    })
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
        // Everything derived from `file` borrows it, so the whole analysis
        // happens in this block and hands back owned values; `file` itself is
        // only moved into the job once those borrows are gone.
        let (region, root, stable, headers, blocks, hops, span, bytes) = {
            let tag = blam_tag::TagFile::parse(&file, Some(file.len()))
                .map_err(|e| e.to_string())?;
            let layout = tag.layout().map_err(|e| e.to_string())?;
            let block = tag.read_data(&layout).map_err(|e| e.to_string())?;
            let route = blam_tag::patch::route(&layout, &file, &block, path)
                .map_err(|e| e.to_string())?;
            let target = &route.target;

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
            // tables are not, so searching anywhere else is wasted effort. And
            // within it only the root element keeps its file offsets — block
            // elements are relocated, and reached through their headers.
            let data = tag.data().ok_or("this tag has no data section")?;
            let start = data.content.as_ptr() as usize - file.as_ptr() as usize;
            let root_off = block.elements.as_ptr() as usize - file.as_ptr() as usize;
            let root = root_off..root_off + block.element_size as usize;
            let stable = blam_tag::view::scalar_mask(&layout, &block, &file);
            let blocks: Vec<(blam_live::Hop, u32)> =
                blam_tag::patch::root_blocks(&layout, &file, &block)
                    .iter()
                    .filter(|(_, n)| *n > 0)
                    .map(|(h, n)| (live::hop(h), *n))
                    .collect();
            let headers: Vec<usize> = blocks.iter().map(|(h, _)| h.header).collect();
            let hops: Vec<blam_live::Hop> = route.hops.iter().map(live::hop).collect();
            let span = target.file_offset..target.file_offset + target.size;
            let bytes = patched
                .get(span.clone())
                .ok_or("the field lies outside the tag payload")?
                .to_vec();
            (
                start..start + data.content.len(),
                root,
                stable,
                headers,
                blocks,
                hops,
                span,
                bytes,
            )
        };

        Ok(live::Job {
            key: key.clone(),
            payload: file,
            region,
            root,
            stable,
            headers,
            blocks,
            hops,
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

/// Progress of a running census, emitted as `live-census` events.
#[derive(Serialize, Clone)]
struct CensusProgress {
    /// `prints` while the fingerprint table is built or loaded, `scan` while
    /// process memory is swept.
    phase: &'static str,
    done_mb: u64,
    total_mb: u64,
}

/// What one census established.
#[derive(Serialize)]
struct CensusReport {
    /// Tags found and verified in the game's memory right now.
    located: usize,
    /// The loaded scenario's short path — which level the player is in.
    level: Option<String>,
    /// Tags whose census evidence was ambiguous and were left for a
    /// single-tag scan instead.
    ambiguous: usize,
    scanned_mb: u64,
    secs: f32,
    loaded: Vec<live::LoadedTag>,
    /// Tags with a live object per the object table — a superset of `loaded`.
    /// `None` when the engine globals could not be resolved.
    present: Option<usize>,
    /// Tags whose buffer the engine's loader cache handed over directly —
    /// exact, no sweep needed for them. `None` when the cache roots could
    /// not be found in this build.
    cached: Option<usize>,
    /// How the loaded set was established: `table` — read from the
    /// simulation's own tag table, exact and instant — or `sweep`.
    method: &'static str,
    /// With `table`: entries in the game's table that no catalog tag matched
    /// (tags only a mod provides, or a mapping gap). `None` for a sweep.
    table_unmapped: Option<usize>,
}

/// Find every loaded tag in one sweep of the game's memory.
///
/// One census makes every found tag poke-instant and names the level the
/// player is in. The sweep costs what a single tag's first poke used to cost;
/// progress goes out as `live-census` events so the UI can show it.
#[tauri::command]
async fn live_census(app: tauri::AppHandle) -> Result<CensusReport, String> {
    tauri::async_runtime::spawn_blocking(move || run_census(&app))
        .await
        .map_err(|e| e.to_string())?
}

fn run_census(app: &tauri::AppHandle) -> Result<CensusReport, String> {
    use tauri::Emitter;

    let started = std::time::Instant::now();
    let state = app.state::<AppState>();
    let live = app.state::<live::Live>().inner().clone();

    // Attach before the expensive parts, so "the game is not running" is said
    // in one second rather than after a table build.
    let process = blam_live::Process::attach().map_err(|e| e.to_string())?;

    // The object table first: about a second, and it settles the level
    // exactly before the sweep even starts. If the engine globals cannot be
    // resolved (a game update moved them), the sweep still runs and the
    // level falls back to the census's own fingerprint — so this never blocks.
    let _ = app.emit(
        "live-census",
        CensusProgress {
            phase: "objects",
            done_mb: 0,
            total_mb: 0,
        },
    );
    let present = probe_present(&state, &live, &process).ok();
    if let Some(p) = &present {
        live.adopt_present(process.pid, p.level.clone(), p.tags.len());
    }

    // The simulation's own tag table, when the running build has a profile:
    // every loaded tag's root at an exact address, and the level, in well
    // under a second. That is the whole census, so the sweep is skipped. On a
    // build without a profile, or before a mission is loaded, this is
    // `Err` and the older phases run as before.
    let _ = app.emit(
        "live-census",
        CensusProgress {
            phase: "table",
            done_mb: 0,
            total_mb: 0,
        },
    );
    if let Ok(census) = with_catalog(&state, |c| tagtable::read(&process, c))? {
        let located = census.found.len();
        let level = census.level.clone();
        let table_unmapped = Some(census.unmapped);
        let mut loaded: Vec<live::LoadedTag> =
            census.found.iter().map(|(_, _, t)| t.clone()).collect();
        loaded.sort_by(|a, b| (&a.group, &a.short).cmp(&(&b.group, &b.short)));
        live.adopt_table(process.pid, census);
        return Ok(CensusReport {
            located,
            level,
            ambiguous: 0,
            scanned_mb: 0,
            secs: started.elapsed().as_secs_f32(),
            loaded,
            present: present.as_ref().map(|p| p.tags.len()),
            cached: None,
            method: "table",
            table_unmapped,
        });
    }

    // The loader's own cache next: every tag it still references is a buffer
    // at an exact address, no sweep needed. Partial by nature (the loader
    // lets go after loading), so the sweep still runs for the rest; and if
    // the roots cannot be found in this build, the sweep is all there is.
    let _ = app.emit(
        "live-census",
        CensusProgress {
            phase: "cache",
            done_mb: 0,
            total_mb: 0,
        },
    );
    let cache_hits = {
        let paks = with_catalog(&state, |c| Ok(c.paks().to_path_buf()))?;
        match tagcache::roots(&process, &paks, &live.cache_rvas()) {
            Ok((roots, rvas)) => {
                live.set_cache_rvas(rvas);
                Some(with_catalog(&state, |c| Ok(tagcache::resolve(&process, c, &roots)))?)
            }
            Err(_) => None,
        }
    };

    let _ = app.emit(
        "live-census",
        CensusProgress {
            phase: "prints",
            done_mb: 0,
            total_mb: 0,
        },
    );

    // The fingerprint table: cached on disk after the first build, so this is
    // tens of seconds once per installation and sub-second afterwards. The
    // catalog lock is held only here, never across the sweep.
    let prints: Vec<census::TagPrint> = {
        let guard = state.catalog.lock().map_err(|e| e.to_string())?;
        let catalog = guard.as_ref().ok_or("no installation is open")?;
        census::table(catalog)
    };

    let table: Vec<blam_live::Print> = prints
        .iter()
        .map(|p| blam_live::Print {
            id: p.index,
            runs: p.runs.clone(),
            masks: p.masks.clone(),
        })
        .collect();

    // Progress events are throttled to every 256 MB; at 16 MB windows the raw
    // callback rate would be noise.
    let emitted = std::sync::atomic::AtomicU64::new(0);
    let app_events = app.clone();
    let outcome = blam_live::census(&process, &table, &move |done, total| {
        let step = done >> 28;
        if emitted.swap(step, std::sync::atomic::Ordering::Relaxed) != step {
            let _ = app_events.emit(
                "live-census",
                CensusProgress {
                    phase: "scan",
                    done_mb: done >> 20,
                    total_mb: total >> 20,
                },
            );
        }
    })
    .map_err(|e| e.to_string())?;

    // Census agreement is strong evidence but tags share structure — two
    // variants of a weapon differ in a handful of fields — so every hit is
    // re-scored against its own payload before being believed, at the same
    // bar a cached base must clear before a poke.
    let by_id: std::collections::HashMap<u32, &census::TagPrint> =
        prints.iter().map(|p| (p.index, p)).collect();
    let mut found = Vec::new();
    let mut cached_verified = 0usize;
    let mut unresolved = 0usize;
    {
        let guard = state.catalog.lock().map_err(|e| e.to_string())?;
        let catalog = guard.as_ref().ok_or("no installation is open")?;

        // Which of several candidate bases is the tag's working copy, and how
        // well it scores — `census::judge`, from what the print table carries,
        // so no hit sends the census back to the containers.
        let judge = |index: usize, bases: &[u64]| -> Option<(u64, f32)> {
            let print = by_id.get(&(index as u32))?;
            census::judge(&process, print, bases, || catalog.read_tag(index).ok())
        };
        let mut adopt = |index: usize, base: u64, fraction: f32| {
            if let Some(entry) = catalog.entry(index) {
                found.push((
                    (entry.group.clone(), entry.short.clone()),
                    base,
                    live::LoadedTag {
                        index,
                        group: entry.group.clone(),
                        short: entry.short.clone(),
                        fraction,
                    },
                ));
            }
        };

        // Cache hits first. They are exact by construction, but they go
        // through the same judgement as a sweep hit: the loader's buffer may
        // be its own image of the file rather than the working copy, and a
        // stale root cannot slip a wrong base in.
        if let Some(hits) = &cache_hits {
            for (index, base) in &hits.bases {
                if let Some((base, fraction)) = judge(*index, &[*base]) {
                    cached_verified += 1;
                    adopt(*index, base, fraction);
                }
            }
        }
        for hit in &outcome.hits {
            let index = hit.id as usize;
            let mut bases = vec![hit.base];
            bases.extend(&hit.rivals);
            match judge(index, &bases) {
                Some((base, fraction)) => adopt(index, base, fraction),
                None if !hit.rivals.is_empty() => unresolved += 1,
                None => {}
            }
        }
    }

    // A run is unique within its tag but not across the catalog, so two
    // near-identical tags can both claim one buffer and both clear the verify
    // bar. Distinct allocations never overlap: where verified data ranges do,
    // it is rival claims on one buffer, and the claim that matches its bytes
    // best is the tag actually loaded there. Best-first, keep non-overlapping.
    let mut order: Vec<usize> = (0..found.len()).collect();
    order.sort_by(|&a, &b| found[b].2.fraction.total_cmp(&found[a].2.fraction));
    let mut taken: Vec<(u64, u64)> = Vec::new();
    let mut keep = vec![false; found.len()];
    for i in order {
        let (_, base, ref tag) = found[i];
        // The root element is what is verified at the base; the rest of the
        // data section is relocated block elements, not resident here.
        let region = &by_id[&(tag.index as u32)].root;
        let (lo, hi) = (base + region.start as u64, base + region.end as u64);
        if taken.iter().all(|&(a, b)| hi <= a || b <= lo) {
            taken.push((lo, hi));
            keep[i] = true;
        }
    }
    let dropped_rivals = keep.iter().filter(|k| !**k).count();
    let found: Vec<_> = found
        .into_iter()
        .zip(keep)
        .filter_map(|(f, k)| k.then_some(f))
        .collect();

    // The loaded scenario names the level. If more than one is resident,
    // prefer a mission scenario over the UI shell, then the best-verified.
    let mut scenarios: Vec<&live::LoadedTag> = found
        .iter()
        .map(|(_, _, t)| t)
        .filter(|t| t.group == "scenario")
        .collect();
    scenarios.sort_by(|a, b| {
        let ui = |t: &live::LoadedTag| t.short.contains("ui");
        ui(a)
            .cmp(&ui(b))
            .then(b.fraction.total_cmp(&a.fraction))
    });
    let fingerprint_level = scenarios.first().map(|t| t.short.clone());
    drop(scenarios);

    // The object table names the level exactly — exactly one scenario object
    // is loaded — so it wins whenever it was readable. The census's own
    // fingerprint of the scenario is the fallback for a build whose engine
    // globals could not be resolved.
    let level = present
        .as_ref()
        .and_then(|p| p.level.clone())
        .or(fingerprint_level);

    // The scenario is the hardest tag to catch — the engine rewrites it more
    // than anything else — so the census can miss it while plainly holding a
    // level's contents. Fall back to the reference graph: the scenario whose
    // references cover the most loaded tags. Most loaded tags are shared
    // across levels, so this signal is noisy — measured on a real mission it
    // ranked a *wrong* level first by two votes. It therefore only speaks
    // when one scenario wins decisively: at least 8 covering tags and twice
    // the runner-up. A census with no level beats one with the wrong level.
    let level = match level {
        Some(level) => Some(level),
        None if !found.is_empty() => {
            let guard = state.catalog.lock().map_err(|e| e.to_string())?;
            let catalog = guard.as_ref().ok_or("no installation is open")?;
            let mut score: std::collections::HashMap<usize, usize> =
                std::collections::HashMap::new();
            for (_, _, tag) in &found {
                for s in catalog.referencing(tag.index, 64).unwrap_or_default() {
                    if s.group == "scenario" {
                        *score.entry(s.index).or_default() += 1;
                    }
                }
            }
            let mut ranked: Vec<(usize, usize)> = score.into_iter().collect();
            ranked.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
            match ranked.as_slice() {
                [(i, best), rest @ ..]
                    if *best >= 8 && rest.first().is_none_or(|(_, next)| *best >= next * 2) =>
                {
                    catalog.entry(*i).map(|e| e.short.clone())
                }
                _ => None,
            }
        }
        None => None,
    };

    let located = found.len();
    let mut loaded: Vec<live::LoadedTag> = found.iter().map(|(_, _, t)| t.clone()).collect();
    loaded.sort_by(|a, b| (&a.group, &a.short).cmp(&(&b.group, &b.short)));
    live.adopt_census(process.pid, found, level.clone());

    Ok(CensusReport {
        located,
        level,
        ambiguous: unresolved + dropped_rivals,
        scanned_mb: outcome.scanned >> 20,
        secs: started.elapsed().as_secs_f32(),
        loaded,
        present: present.as_ref().map(|p| p.tags.len()),
        cached: cache_hits.as_ref().map(|_| cached_verified),
        method: "sweep",
        table_unmapped: None,
    })
}

/// Read the object table: attach the reader (from cached RVAs when they still
/// validate), walk it, and map tag assets to the catalog. Holds the catalog
/// lock only for the mapping.
fn probe_present(
    state: &State<'_, AppState>,
    live: &live::Live,
    process: &blam_live::Process,
) -> Result<present::Present, String> {
    let paks = with_catalog(state, |c| Ok(c.paks().to_path_buf()))?;
    let (reader, rvas) = present::attach(process, &paks, live.rvas())?;
    live.set_rvas(rvas);
    with_catalog(state, |c| present::read(process, &reader, c))
}

/// What the object table says the game holds — the level and how many tags
/// have a live object — without a memory sweep. About a second; the thing to
/// call the moment live mode is armed.
#[derive(Serialize)]
struct ProbeReport {
    level: Option<String>,
    present: usize,
    objects: usize,
    secs: f32,
}

#[tauri::command]
async fn live_probe(app: tauri::AppHandle) -> Result<ProbeReport, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let started = std::time::Instant::now();
        let state = app.state::<AppState>();
        let live = app.state::<live::Live>().inner().clone();
        let process = blam_live::Process::attach().map_err(|e| e.to_string())?;
        let p = probe_present(&state, &live, &process)?;
        live.adopt_present(process.pid, p.level.clone(), p.tags.len());
        Ok(ProbeReport {
            level: p.level,
            present: p.tags.len(),
            objects: p.objects,
            secs: started.elapsed().as_secs_f32(),
        })
    })
    .await
    .map_err(|e| e.to_string())?
}

/// The tags the last census found loaded, for the UI's "in game" view.
#[tauri::command]
fn live_loaded(live: State<'_, live::Live>) -> Vec<live::LoadedTag> {
    live.loaded()
}

#[tauri::command]
fn revert_field(index: usize, path: String, state: State<'_, AppState>) -> Result<usize, String> {
    let key = tag_key(&state, index)?;
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    work.remember(&key);
    let list = work.edits.entry(key.clone()).or_default();
    // Reverting a block's element ops also drops every edit inside its
    // elements: an edit recorded inside an added element would otherwise
    // outlive the element and block the export as stale. For a plain field
    // the prefix matches nothing and this is the same edit it always was.
    let inside = format!("{path}[");
    list.retain(|e| e.path != path && !e.path.starts_with(&inside));
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
    work.remember(&key);
    work.edits.remove(&key);
    work.autosave()?;
    Ok(())
}

/// Take back the last change to a tag's edits — a field set, an element op, a
/// revert — restoring the edit list as it was. Returns the depths left.
#[tauri::command]
fn undo_edit(index: usize, state: State<'_, AppState>) -> Result<HistoryView, String> {
    let key = tag_key(&state, index)?;
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    if !work.undo(&key) {
        return Err("nothing to undo".into());
    }
    work.autosave()?;
    Ok(work.history_of(&key))
}

/// Re-apply the last change undone on a tag.
#[tauri::command]
fn redo_edit(index: usize, state: State<'_, AppState>) -> Result<HistoryView, String> {
    let key = tag_key(&state, index)?;
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    if !work.redo(&key) {
        return Err("nothing to redo".into());
    }
    work.autosave()?;
    Ok(work.history_of(&key))
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
fn read_tag(
    index: usize,
    expert: Option<bool>,
    state: State<'_, AppState>,
) -> Result<TagView, String> {
    let key = tag_key(&state, index)?;
    let pending = pending_for(&state, &key)?;
    let edited: Vec<String> = pending.iter().map(|e| e.path.clone()).collect();
    let history = state
        .work
        .lock()
        .map_err(|e| e.to_string())?
        .history_of(&key);

    with_catalog(&state, |c| {
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let path = entry.path.clone();
        let group = entry.group.clone();
        let chunk_size = entry.chunk.length;
        let file = patched_bytes(c, index, &pending)?;

        let tag = blam_tag::TagFile::parse(&file, Some(file.len()))
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
                    // Expert view: padding and markers too, as raw bytes.
                    let nodes = if expert.unwrap_or(false) {
                        blam_tag::view::root_expert(
                            layout,
                            &block,
                            blam_tag::view::DEFAULT_MAX_ELEMENTS,
                        )
                    } else {
                        blam_tag::view::root(layout, &block)
                    };
                    (
                        nodes.iter().map(to_view).collect::<Vec<_>>(),
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
                history,
                fields,
            })
        }
    })
}

fn count(nodes: &[NodeView]) -> usize {
    nodes.len() + nodes.iter().map(|n| count(&n.children)).sum::<usize>()
}

/// Find a tag by group and reference path — an exact, indexed lookup; the
/// path normalization it depends on lives with the index, at
/// [`catalog::normalize_ref_path`].
fn tag_by_ref(c: &Catalog, group: &str, path: &str) -> Option<usize> {
    c.resolve_ref(group, path)
}

/// One reference to resolve, as a tag body or a recipe holds it: the group as
/// a four-CC or directory name, and the authored path.
#[derive(serde::Deserialize)]
struct RefQuery {
    group: String,
    path: String,
}

/// Where a resolved reference lands.
#[derive(Serialize)]
struct RefHit {
    index: usize,
    group: String,
    short: String,
    size: u64,
}

/// Resolve a batch of tag references exactly.
///
/// Batched because the caller is a just-loaded tag validating every reference
/// field at once; one round trip beats one per field. An empty path is an
/// unset reference and resolves to nothing without being wrong.
#[tauri::command]
fn resolve_refs(
    refs: Vec<RefQuery>,
    state: State<'_, AppState>,
) -> Result<Vec<Option<RefHit>>, String> {
    with_catalog(&state, |c| {
        Ok(refs
            .iter()
            .map(|r| {
                if r.path.is_empty() {
                    return None;
                }
                let i = c.resolve_ref(&r.group, &r.path)?;
                let t = c.entry(i)?;
                Some(RefHit {
                    index: i,
                    group: t.group.clone(),
                    short: t.short.clone(),
                    size: t.chunk.length,
                })
            })
            .collect())
    })
}

/// What a reference points at, in enough detail to draw a preview card
/// without loading the tag itself.
#[derive(Serialize)]
struct TagPeek {
    group: String,
    four_cc: String,
    short: String,
    chunk_size: u64,
    /// Which card to draw: `model`, `texture`, `sound` or `summary`.
    preview: &'static str,
    /// Texture catalog index, when `preview` is `texture`.
    texture: Option<usize>,
    /// Sound catalog index, when `preview` is `sound`.
    sound: Option<usize>,
}

/// The first texture a tag's imports bind, if any — the same resolution
/// `tag_links` uses, bounded so a hover never walks a huge import table.
/// Public for the references e2e test, which proves it against real data.
pub fn texture_import(c: &Catalog, index: usize) -> Option<usize> {
    let uasset = c.read_tag_uasset(index).ok()?;
    zen::imported_package_names(&uasset)
        .iter()
        .take(16)
        .find_map(|p| c.texture_by_package(p))
}

/// A playable Wwise media file for a sound tag.
///
/// A sound tag's `.uasset` imports audio assets, which import variants, which
/// import the `Wwise/Play_*` event package whose name map finally lists the
/// `Media/<bucket>/<id>.wem` it plays (verified on the shipped build — the
/// door switch above resolves at hop two). So this is a bounded breadth-first
/// walk of the import graph: at most three hops and two dozen package reads,
/// packages on a `/wwise/` path first. No bank graph, and none of the
/// seconds-long name-index build [`Catalog::names`] pays — cheap enough for a
/// hover. Public for the references e2e test, which proves it on real data.
pub fn wwise_media_for_tag(c: &Catalog, index: usize) -> Option<usize> {
    const MAX_DEPTH: u8 = 3;
    const MAX_READS: usize = 24;

    let uasset = c.read_tag_uasset(index).ok()?;
    let mut queue: std::collections::VecDeque<(String, u8)> = std::collections::VecDeque::new();
    let enqueue = |queue: &mut std::collections::VecDeque<(String, u8)>,
                       names: Vec<String>,
                       depth: u8| {
        // Event packages live under a Wwise folder; look there first.
        let (wwise, rest): (Vec<_>, Vec<_>) = names
            .into_iter()
            .partition(|p| p.to_ascii_lowercase().contains("/wwise/"));
        for p in wwise {
            queue.push_front((p, depth));
        }
        for p in rest {
            queue.push_back((p, depth));
        }
    };
    enqueue(&mut queue, zen::imported_package_names(&uasset), 0);

    let mut seen = std::collections::BTreeSet::new();
    let mut reads = 0usize;
    while let Some((package, depth)) = queue.pop_front() {
        if reads >= MAX_READS || !seen.insert(package.clone()) {
            continue;
        }
        let Some(buf) = c.read_package(&package) else {
            continue;
        };
        reads += 1;
        // 52: where a cooked package's summary name map begins — the same
        // offset the Wwise name index reads (see `Catalog::names`).
        if let Some(names) = zen::load_name_batch(&buf, 52) {
            for name in &names {
                if !name.starts_with("Media/") {
                    continue;
                }
                let hit = wwise::media_id_of_path(name).and_then(|id| c.sound_by_media_id(id));
                if hit.is_some() {
                    return hit;
                }
            }
        }
        if depth + 1 < MAX_DEPTH {
            enqueue(&mut queue, zen::imported_package_names(&buf), depth + 1);
        }
    }
    None
}

/// One playable media file a sound tag's events reach.
#[derive(Serialize)]
pub struct TagMediaHit {
    /// Wwise media short ID.
    pub id: u32,
    /// Sound catalog index, when the media ships as a loose `.wem`.
    pub sound: Option<usize>,
    /// Sound catalog index of the bank carrying it, when embedded.
    pub bank: Option<usize>,
    /// Payload size in bytes, however it ships.
    pub size: Option<u64>,
    /// The event that reaches it, e.g. `Play_WEP_SniperRifle_Ammo_Pickup`.
    pub event: String,
}

#[derive(Serialize)]
pub struct TagAudioView {
    /// Every `Play_*` event the tag's import graph names.
    pub events: Vec<String>,
    pub media: Vec<TagMediaHit>,
}

/// Everything a sound tag can play, exhaustively.
///
/// [`wwise_media_for_tag`] answers "is there *a* sound?" with the first loose
/// media a package name map lists, which is right for a hover card and wrong
/// for a tag view: most events list no media in any package and reach theirs
/// only through the bank graph, and 546 tags of the shipped build play media
/// that exists *only inside* a bank's `DATA` section. So this walks the same
/// import graph but keeps every event stem and bank reference it sees, then
/// parses the referenced banks — the event package's own name map says which
/// (see `wwise::bank_names` for why that pairing is trustworthy) — and
/// resolves each media ID to a loose catalog sound or back into the bank it
/// is embedded in. A few package reads plus a bank read or two: fine for a
/// click, too heavy for a hover.
///
/// The per-media `event` label is the closest thing to a permutation name the
/// shipped build has: Wwise hashes the designers' names away, so individual
/// variations cannot be told apart beyond their media ID.
pub fn wwise_audio_for_tag(c: &Catalog, index: usize) -> Result<TagAudioView, String> {
    const MAX_DEPTH: u8 = 3;
    const MAX_READS: usize = 32;

    let uasset = c.read_tag_uasset(index)?;
    let mut queue: std::collections::VecDeque<(String, u8)> = std::collections::VecDeque::new();
    for p in zen::imported_package_names(&uasset) {
        queue.push_back((p, 0));
    }
    let mut seen = std::collections::BTreeSet::new();
    let mut stems: Vec<String> = Vec::new();
    let mut bank_shorts: Vec<String> = Vec::new();
    // Media named directly by package name maps, with the event package (or
    // "") it surfaced in.
    let mut walk_media: Vec<(u32, String)> = Vec::new();
    let mut reads = 0usize;
    while let Some((package, depth)) = queue.pop_front() {
        if reads >= MAX_READS || !seen.insert(package.clone()) {
            continue;
        }
        let Some(buf) = c.read_package(&package) else {
            continue;
        };
        reads += 1;
        let stem = package.rsplit('/').next().unwrap_or("").to_string();
        let is_event = stem.starts_with("Play_");
        if is_event && !stems.contains(&stem) {
            stems.push(stem.clone());
        }
        if let Some(names) = zen::load_name_batch(&buf, 52) {
            for name in &names {
                if name.ends_with(".bnk") && !bank_shorts.contains(name) {
                    bank_shorts.push(name.clone());
                } else if let Some(id) = name
                    .starts_with("Media/")
                    .then(|| wwise::media_id_of_path(name))
                    .flatten()
                {
                    if !walk_media.iter().any(|(m, _)| *m == id) {
                        let via = if is_event { stem.clone() } else { String::new() };
                        walk_media.push((id, via));
                    }
                }
            }
        }
        if depth + 1 < MAX_DEPTH {
            for p in zen::imported_package_names(&buf) {
                queue.push_back((p, depth + 1));
            }
        }
    }

    // The bank graph knows media the packages never name. Parse only the
    // banks the walk itself referenced, keeping each bank's bytes long enough
    // to know what it embeds.
    let wanted: std::collections::BTreeMap<u32, &str> =
        stems.iter().map(|s| (bnk::event_id(s), s.as_str())).collect();
    // Ordered media: bank-graph order first — Wwise container order is the
    // nearest thing to the authored variation order — then walk leftovers.
    let mut media: Vec<(u32, String)> = Vec::new();
    // Media id -> (bank catalog index, embedded size).
    let mut embedded: std::collections::BTreeMap<u32, (usize, u32)> =
        std::collections::BTreeMap::new();
    for short in &bank_shorts {
        let Some(bi) = (0..c.sounds.len()).find(|&i| {
            let s = &c.sounds[i].short;
            s == short || s.ends_with(&format!("/{short}"))
        }) else {
            continue;
        };
        let Ok(buf) = c.read_sound(bi, None) else {
            continue;
        };
        for (event, ids) in bnk::parse(&buf).events {
            let Some(&stem) = wanted.get(&event) else {
                continue;
            };
            for id in ids {
                if !media.iter().any(|(m, _)| *m == id) {
                    media.push((id, stem.to_string()));
                }
            }
        }
        for (id, size) in bnk::embedded_index(&buf) {
            embedded.entry(id).or_insert((bi, size));
        }
    }
    for (id, via) in walk_media {
        if !media.iter().any(|(m, _)| *m == id) {
            media.push((id, via));
        }
    }

    let media = media
        .into_iter()
        .filter_map(|(id, event)| {
            // Loose beats embedded: the pak copy is the one every player
            // hears, and it can be exported.
            if let Some(si) = c.sound_by_media_id(id) {
                return Some(TagMediaHit {
                    id,
                    sound: Some(si),
                    bank: None,
                    size: c.sound(si).map(|s| s.entry.uncompressed_size),
                    event,
                });
            }
            let (bi, size) = embedded.get(&id)?;
            Some(TagMediaHit {
                id,
                sound: None,
                bank: Some(*bi),
                size: Some(u64::from(*size)),
                event,
            })
        })
        .collect();
    Ok(TagAudioView { events: stems, media })
}

/// Everything a sound tag can play. See [`wwise_audio_for_tag`]; a few
/// package reads and a bank parse, so a command rather than part of the peek.
#[tauri::command]
fn sound_tag_media(index: usize, state: State<'_, AppState>) -> Result<TagAudioView, String> {
    with_catalog(&state, |c| wwise_audio_for_tag(c, index))
}

/// Build a playable stream for a media file that ships inside a bank.
///
/// The embedded payload is a complete RIFF `.wem`, so past the extraction it
/// is [`play_sound`] again.
#[tauri::command]
fn play_bank_media(bank: usize, media: u32, state: State<'_, AppState>) -> Result<SoundAudio, String> {
    use base64::Engine;
    with_catalog(&state, |c| {
        let data = c.read_sound(bank, None)?;
        let wem = bnk::embedded(&data, media)
            .ok_or_else(|| format!("media {media} is not embedded in this bank"))?;
        let out = decode::to_playable(wem)?;
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

/// Classify what a preview card can show for one tag, cheaply: catalog entry
/// data plus at most a package-header read. Never a full tag parse.
#[tauri::command]
fn peek_tag(index: usize, state: State<'_, AppState>) -> Result<TagPeek, String> {
    with_catalog(&state, |c| {
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let group = entry.group.clone();
        let short = entry.short.clone();
        let chunk_size = entry.chunk.length;
        let four_cc = c.four_cc_of_group(&group).unwrap_or_default().to_string();

        let (preview, texture, sound) = match group.as_str() {
            "model" | "collision_model" | "skeleton_model" => ("model", None, None),
            g if g.starts_with("sound") => match wwise_media_for_tag(c, index) {
                Some(si) => ("sound", None, Some(si)),
                None => ("summary", None, None),
            },
            _ => match texture_import(c, index) {
                Some(xi) => ("texture", Some(xi), None),
                None => ("summary", None, None),
            },
        };

        Ok(TagPeek {
            group,
            four_cc,
            short,
            chunk_size,
            preview,
            texture,
            sound,
        })
    })
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
    /// Flat base colour (linear RGBA) from the instance's vector parameters —
    /// what the material library's layered materials use instead of an albedo
    /// texture. The viewer's stand-in when `texture` is absent.
    tint: Option<[f64; 4]>,
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
    /// The geometry is the full-detail mesh decoded from the Nanite pages.
    nanite: bool,
    skeletal: bool,
}

/// A cooked mesh's renderable geometry, packed as `"UMSH"`, a u32 JSON
/// length, the JSON header, then positions, normals, uvs and indices.
#[tauri::command]
fn read_mesh(index: usize, state: State<'_, AppState>) -> Result<tauri::ipc::Response, String> {
    with_catalog(&state, |c| {
        let entry = c.meshes.get(index).ok_or("mesh index out of range")?;
        let skeletal = entry.skeletal;
        let usmap = usmap()?;
        let data = c.read_mesh_uasset(index)?;
        let ubulk = c.read_mesh_ubulk(index)?;
        let package = ue_asset::zen::Package::parse(&data).map_err(|e| e.to_string())?;
        let scripts = c.script_objects().ok_or("no script-object table")?;
        let wanted_class = if skeletal { "SkeletalMesh" } else { "StaticMesh" };
        let export = package
            .exports
            .iter()
            .position(|e| scripts.leaf(e.class) == Some(wanted_class))
            .ok_or_else(|| format!("{} has no {wanted_class} export", entry.short))?;
        let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;
        let ctx = ue_asset::unversioned::Ctx {
            usmap,
            names: &package.names,
        };
        let bulk_map = ue_asset::mesh::bulk_map_of(&data);
        let mesh = if skeletal {
            let sk = ue_asset::mesh::parse_skeletal_mesh_with_bulk_map(&ctx, bytes, ubulk.as_deref(), &bulk_map)
                .map_err(|e| e.to_string())?;
            ue_asset::mesh::StaticMeshData {
                materials: sk.materials,
                lods: sk.lods,
                nanite: sk.nanite,
                nanite_report: sk.nanite_report,
                nanite_note: sk.nanite_note,
            }
        } else {
            ue_asset::mesh::parse_static_mesh_with_bulk_map(&ctx, bytes, ubulk.as_deref(), &bulk_map)
                .map_err(|e| e.to_string())?
        };

        // Chase each material slot to a base-colour texture.
        let materials: Vec<MeshMaterial> = mesh
            .materials
            .iter()
            .map(|(slot, object)| {
                let material_path = ue_asset::material::import_package_name(&package, *object);
                let mut texture_path = None;
                let mut tint = None;
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
                    if tint.is_none() {
                        tint = ue_asset::material::base_color_tint(&info.colors);
                    }
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
                    tint,
                }
            })
            .collect();

        // The Nanite mesh at full detail when its pages decoded, else the
        // best classic LOD that carries buffers. Skeletal Nanite meshes ship
        // a single placeholder triangle, which is worth naming.
        let (lod_index, lod, nanite) = match mesh.nanite.as_ref() {
            Some(n) => (0, n, true),
            None => {
                let (i, l) = mesh
                    .lods
                    .iter()
                    .enumerate()
                    .find(|(_, l)| !l.indices.is_empty())
                    .ok_or("no LOD carries geometry (Nanite-only mesh?)")?;
                (i, l, false)
            }
        };
        if lod.indices.len() <= 3 {
            return Err(format!(
                "{} is Nanite-only: its classic buffers hold a placeholder triangle{}",
                entry.short,
                match &mesh.nanite_note {
                    Some(note) => format!(", and its Nanite pages did not decode: {note}"),
                    None => String::new(),
                }
            ));
        }

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
            nanite,
            skeletal,
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
    /// Unreal render meshes per palette entry, per category — empty where the
    /// chase found none (the collision proxy stays the fallback).
    palette_render: Vec<Vec<Vec<RenderMeshRef>>>,
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
        let palette_render = layout
            .categories
            .iter()
            .map(|cat| {
                cat.palette
                    .iter()
                    .map(|path| {
                        tag_by_ref(c, cat.group, path)
                            .map(|oi| render_mesh_refs(c, oi))
                            .unwrap_or_default()
                    })
                    .collect()
            })
            .collect();
        Ok(ScenarioWorldView {
            layout,
            bsp_indices,
            palette_models,
            palette_render,
        })
    })
}

/// One Unreal mesh an object's actor Blueprint binds, with the component
/// transform that places it in actor space.
///
/// The tags themselves carry no visuals: an object tag names a `BP_*` actor,
/// whose mesh components name the cooked `SK_`/`SM_` packages. This is that
/// chase, resolved to mesh catalog indices `read_mesh` can serve.
#[derive(Serialize, Clone)]
pub struct RenderMeshRef {
    /// Mesh catalog index.
    pub mesh: usize,
    pub skeletal: bool,
    /// Mesh package tail, for display.
    pub label: String,
    /// Component translation in actor space (Unreal centimetres).
    pub location: [f64; 3],
    /// Component rotation as an Unreal Rotator: pitch, yaw, roll in degrees.
    pub rotation: [f64; 3],
    pub scale: [f64; 3],
    /// Rotation as a quaternion (i j k w, Unreal space), which wins over
    /// `rotation` when present — rig pieces sit at bone rest poses, which a
    /// Rotator cannot carry exactly.
    pub quat: Option<[f64; 4]>,
    /// A stand-in found through the MeshSynchronization data asset rather
    /// than the Blueprint. Drawn only when no non-fallback mesh is readable —
    /// characters bind Nanite placeholders in the Blueprint and pick their
    /// real body mesh at runtime, which this approximates.
    pub fallback: bool,
}

// Quaternion arithmetic for composing bone rest poses (i j k w).

fn quat_mul(a: [f64; 4], b: [f64; 4]) -> [f64; 4] {
    [
        a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
        a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
        a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
        a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2],
    ]
}

fn quat_rotate(q: [f64; 4], v: [f64; 3]) -> [f64; 3] {
    let p = [v[0], v[1], v[2], 0.0];
    let qc = [-q[0], -q[1], -q[2], q[3]];
    let r = quat_mul(quat_mul(q, p), qc);
    [r[0], r[1], r[2]]
}

/// An Unreal Rotator (pitch, yaw, roll in degrees) as a quaternion — UE's own
/// FRotator::Quaternion.
fn rotator_to_quat(r: [f64; 3]) -> [f64; 4] {
    let h = std::f64::consts::PI / 360.0;
    let (sp, cp) = (r[0] * h).sin_cos();
    let (sy, cy) = (r[1] * h).sin_cos();
    let (sr, cr) = (r[2] * h).sin_cos();
    [
        cr * sp * sy - sr * cp * cy,
        -cr * sp * cy - sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    ]
}

/// Object groups whose tags bind an actor Blueprint worth chasing.
const OBJECT_GROUPS: &[&str] = &[
    "biped",
    "vehicle",
    "weapon",
    "equipment",
    "projectile",
    "scenery",
    "device_machine",
    "device_control",
    "device_light_fixture",
    "sound_scenery",
    "crate",
    "creature",
];

fn vec3_of(v: Option<&ue_asset::unversioned::Value>, default: f64) -> [f64; 3] {
    match v {
        Some(ue_asset::unversioned::Value::Array(items)) if items.len() >= 3 => {
            let f = |i: usize| match items[i] {
                ue_asset::unversioned::Value::Float(x) => x,
                _ => default,
            };
            [f(0), f(1), f(2)]
        }
        _ => [default; 3],
    }
}

/// The render meshes reachable from one object tag: its imported `BP_*` actor
/// packages, each mesh component template's mesh reference resolved through
/// the import map (or a soft object path), hidden components skipped.
pub fn render_mesh_refs(c: &Catalog, tag_index: usize) -> Vec<RenderMeshRef> {
    let mut out: Vec<RenderMeshRef> = Vec::new();
    let Ok(uasset) = c.read_tag_uasset(tag_index) else {
        return out;
    };
    let Ok(usmap) = usmap() else { return out };
    let Some(scripts) = c.script_objects() else {
        return out;
    };
    for bp in zen::imported_package_names(&uasset) {
        let tail = bp.rsplit('/').next().unwrap_or(&bp);
        // FluidFlux and BPC_* are shared helper components, never the body.
        if !tail.starts_with("BP_") || bp.contains("/FluidFlux/") {
            continue;
        }
        let Some(bytes) = c.read_package(&bp) else { continue };
        let Ok(package) = ue_asset::zen::Package::parse(&bytes) else {
            continue;
        };
        for (ei, export) in package.exports.iter().enumerate() {
            let class = scripts.leaf(export.class);
            if !matches!(class, Some("SkeletalMeshComponent" | "StaticMeshComponent")) {
                continue;
            }
            let Ok(data) = package.export_data(&bytes, ei) else { continue };
            let ctx = ue_asset::unversioned::Ctx {
                usmap,
                names: &package.names,
            };
            let mut w = ue_asset::unversioned::Walker::new(&ctx, data);
            let Ok(props) = w.read_object(
                class.unwrap_or_default(),
                ue_asset::unversioned::Keep::Names(&[
                    "SkeletalMesh",
                    "SkinnedAsset",
                    "SkeletalMeshAsset",
                    "StaticMesh",
                    "RelativeLocation",
                    "RelativeRotation",
                    "RelativeScale3D",
                    "bHiddenInGame",
                    "bRenderInMainPass",
                ]),
            ) else {
                continue;
            };
            let hidden = |name: &str, when: bool| {
                matches!(
                    props.get(name),
                    Some(ue_asset::unversioned::Value::Bool(b)) if *b == when
                )
            };
            if hidden("bHiddenInGame", true) || hidden("bRenderInMainPass", false) {
                continue;
            }
            let mesh_package = ["SkinnedAsset", "SkeletalMesh", "SkeletalMeshAsset", "StaticMesh"]
                .iter()
                .find_map(|key| {
                    let v = props.get(*key)?;
                    if let Some(object) = v.as_object() {
                        return ue_asset::material::import_package_name(&package, object);
                    }
                    // A soft path serializes as "/Game/Pkg.Asset".
                    let s = v.as_str()?;
                    Some(s.split('.').next().unwrap_or(s).to_string())
                });
            let Some(mesh_package) = mesh_package else { continue };
            let Some(mesh) = c.mesh_by_package(&mesh_package) else {
                continue;
            };
            if out.iter().any(|r| r.mesh == mesh) {
                continue;
            }
            out.push(RenderMeshRef {
                mesh,
                skeletal: c.meshes[mesh].skeletal,
                label: mesh_package
                    .rsplit('/')
                    .next()
                    .unwrap_or(&mesh_package)
                    .to_string(),
                location: vec3_of(props.get("RelativeLocation"), 0.0),
                rotation: vec3_of(props.get("RelativeRotation"), 0.0),
                scale: vec3_of(props.get("RelativeScale3D"), 1.0),
                quat: None,
                fallback: false,
            });
        }
    }
    for mesh in meshsync_fallback(c, tag_index) {
        if out.iter().any(|r| r.mesh == mesh) {
            continue;
        }
        out.push(RenderMeshRef {
            mesh,
            skeletal: c.meshes[mesh].skeletal,
            label: c.meshes[mesh]
                .short
                .rsplit('/')
                .next()
                .unwrap_or(&c.meshes[mesh].short)
                .to_string(),
            location: [0.0; 3],
            rotation: [0.0; 3],
            scale: [1.0; 3],
            quat: None,
            fallback: true,
        });
    }
    // Rig statics: a skeletal mesh's per-region pieces (hull, panels, wheels)
    // live beside it in a `Static/` folder, in bone-local frames, attached at
    // runtime. Attach each to its bone's rest pose so vehicles draw whole.
    let skeletal: Vec<RenderMeshRef> = out.iter().filter(|r| r.skeletal).cloned().collect();
    for sk_ref in &skeletal {
        for piece in rig_static_refs(c, sk_ref) {
            if out.iter().any(|r| r.mesh == piece.mesh) {
                continue;
            }
            out.push(piece);
        }
    }
    out
}

/// Loose name tokens: split on underscores and camel-case, lowercased, with
/// the rig's synonyms mapped (`Tire` vs `Wheel`, `Upper` vs `Up`), sorted.
fn rig_tokens(s: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut cur = String::new();
    for c in s.chars() {
        let boundary = c == '_'
            || (c.is_ascii_uppercase()
                && !cur.is_empty()
                && !cur.ends_with(|p: char| p.is_ascii_uppercase()));
        if boundary && !cur.is_empty() {
            out.push(std::mem::take(&mut cur).to_lowercase());
        }
        if c != '_' {
            cur.push(c);
        }
    }
    if !cur.is_empty() {
        out.push(cur.to_lowercase());
    }
    let mut mapped = Vec::new();
    for t in out {
        match t.as_str() {
            "tire" => mapped.push("wheel".to_string()),
            "upper" => mapped.push("up".to_string()),
            "lower" => mapped.push("down".to_string()),
            "ebrake" => {
                mapped.push("emergency".to_string());
                mapped.push("brake".to_string());
            }
            _ => mapped.push(t),
        }
    }
    mapped.sort();
    mapped
}

/// The rig statics belonging to one skeletal mesh, each placed at its bone's
/// rest-pose transform (composed with the owning component's transform).
///
/// Matching is by name, loosely: the piece is `SM_<Thing>_<BoneName>` with
/// word-order swaps (`Base_Axle` vs `Axle_Base`), missing underscores
/// (`SteeringArm`) and synonyms — so suffixes are compared as token sets,
/// then as a subset when exactly one bone qualifies. What the rig does not
/// name sits in the chassis frame: the Blam collision hangs panels and
/// accessories off the hull node, whose bone is `Body` (or `Chassis`).
fn rig_static_refs(c: &Catalog, sk_ref: &RenderMeshRef) -> Vec<RenderMeshRef> {
    let Some(entry) = c.meshes.get(sk_ref.mesh) else {
        return Vec::new();
    };
    let sk_dir = entry.short.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
    let static_dir = format!("{}/static/", sk_dir.to_ascii_lowercase());

    // The candidate pieces, before any parsing: most skeletal meshes have no
    // Static sibling, and the SK parse below is not free.
    let pieces: Vec<usize> = c
        .meshes
        .iter()
        .enumerate()
        .filter(|(_, m)| {
            if m.skeletal {
                return false;
            }
            let lower = m.short.to_ascii_lowercase();
            lower.starts_with(&static_dir)
                && !lower[static_dir.len()..].contains('/')
                && !lower.contains("damaged")
        })
        .map(|(i, _)| i)
        .collect();
    if pieces.is_empty() {
        return Vec::new();
    }

    // The SK's reference skeleton, posed to rest in component space.
    let Ok(usmap) = usmap() else { return Vec::new() };
    let Some(scripts) = c.script_objects() else {
        return Vec::new();
    };
    let Ok(data) = c.read_mesh_uasset(sk_ref.mesh) else {
        return Vec::new();
    };
    let Ok(ubulk) = c.read_mesh_ubulk(sk_ref.mesh) else {
        return Vec::new();
    };
    let Ok(package) = ue_asset::zen::Package::parse(&data) else {
        return Vec::new();
    };
    let Some(export) = package
        .exports
        .iter()
        .position(|e| scripts.leaf(e.class) == Some("SkeletalMesh"))
    else {
        return Vec::new();
    };
    let Ok(bytes) = package.export_data(&data, export) else {
        return Vec::new();
    };
    let ctx = ue_asset::unversioned::Ctx {
        usmap,
        names: &package.names,
    };
    let Ok(sk) = ue_asset::mesh::parse_skeletal_mesh(&ctx, bytes, ubulk.as_deref()) else {
        return Vec::new();
    };

    let mut world: Vec<([f64; 3], [f64; 4])> = Vec::new();
    for (i, b) in sk.bones.iter().enumerate() {
        let t = [
            b.translation[0] as f64,
            b.translation[1] as f64,
            b.translation[2] as f64,
        ];
        let q = [
            b.rotation[0] as f64,
            b.rotation[1] as f64,
            b.rotation[2] as f64,
            b.rotation[3] as f64,
        ];
        let w = match b.parent {
            p if p >= 0 && (p as usize) < i => {
                let (pt, pq) = world[p as usize];
                let rt = quat_rotate(pq, t);
                ([pt[0] + rt[0], pt[1] + rt[1], pt[2] + rt[2]], quat_mul(pq, q))
            }
            _ => (t, q),
        };
        world.push(w);
    }

    let bone_sets: Vec<Vec<String>> = sk.bones.iter().map(|b| rig_tokens(&b.name)).collect();
    let bone_keys: Vec<String> = bone_sets.iter().map(|t| t.concat()).collect();
    let body = sk
        .bones
        .iter()
        .position(|b| b.name == "Body")
        .or_else(|| sk.bones.iter().position(|b| b.name == "Chassis"));

    // The owning component's transform, to compose the pieces into.
    let comp_q = rotator_to_quat(sk_ref.rotation);
    let comp_t = sk_ref.location;

    let mut out = Vec::new();
    for mi in pieces {
        let tail = c.meshes[mi]
            .short
            .rsplit('/')
            .next()
            .unwrap_or(&c.meshes[mi].short)
            .to_string();
        let parts: Vec<&str> = tail.split('_').collect();
        let mut bone_hit: Option<usize> = None;
        'outer: for start in 1..parts.len() {
            let cand = rig_tokens(&parts[start..].join("_"));
            if cand.is_empty() {
                continue;
            }
            if let Some(bi) = bone_keys.iter().position(|k| *k == cand.concat()) {
                bone_hit = Some(bi);
                break 'outer;
            }
            let subs: Vec<usize> = bone_sets
                .iter()
                .enumerate()
                .filter(|(_, b)| cand.iter().all(|t| b.contains(t)))
                .map(|(i, _)| i)
                .collect();
            if subs.len() == 1 {
                bone_hit = Some(subs[0]);
                break 'outer;
            }
        }
        let Some(bi) = bone_hit.or(body) else { continue };
        let (bt, bq) = world[bi];
        let scaled = [
            bt[0] * sk_ref.scale[0],
            bt[1] * sk_ref.scale[1],
            bt[2] * sk_ref.scale[2],
        ];
        let rt = quat_rotate(comp_q, scaled);
        out.push(RenderMeshRef {
            mesh: mi,
            skeletal: false,
            label: tail,
            location: [comp_t[0] + rt[0], comp_t[1] + rt[1], comp_t[2] + rt[2]],
            rotation: [0.0; 3],
            scale: sk_ref.scale,
            quat: Some(quat_mul(comp_q, bq)),
            fallback: sk_ref.fallback,
        });
    }
    out
}

/// Stand-in meshes for an object whose Blueprint binds only placeholders:
/// its hlmt's MeshSynchronization data asset names the asset folder, and the
/// best skeletal-mesh directory under that folder's root stands in for the
/// runtime's own pick. `Common` directories outrank `Default`, which outrank
/// the rest; ties go to the shallowest.
fn meshsync_fallback(c: &Catalog, tag_index: usize) -> Vec<usize> {
    let Some(hlmt) = c
        .read_tag(tag_index)
        .ok()
        .and_then(|object| geometry::object_model_ref(&object))
    else {
        return Vec::new();
    };
    let Some(folder) = c.meshsync_folder(&hlmt) else {
        return Vec::new();
    };
    let root = folder.strip_suffix("/Common").unwrap_or(folder);
    let root_prefix = format!(
        "{}/",
        root.trim_start_matches("/Game/").to_ascii_lowercase()
    );
    // Group candidate meshes by directory and keep the best-ranked directory.
    let mut best: Option<(u32, String, Vec<usize>)> = None;
    let mut dirs: std::collections::BTreeMap<String, Vec<usize>> = Default::default();
    for (i, m) in c.meshes.iter().enumerate() {
        if !m.skeletal {
            continue;
        }
        let lower = m.short.to_ascii_lowercase();
        if !lower.starts_with(&root_prefix) {
            continue;
        }
        let dir = lower.rsplit_once('/').map(|(d, _)| d.to_string()).unwrap_or_default();
        dirs.entry(dir).or_default().push(i);
    }
    for (dir, meshes) in dirs {
        let rank = if dir.contains("/common") || dir.ends_with("common") {
            0
        } else if dir.contains("/default") || dir.ends_with("default") {
            1
        } else {
            2
        };
        let score = rank * 1000 + dir.matches('/').count() as u32;
        if best.as_ref().map_or(true, |(s, _, _)| score < *s) {
            best = Some((score, dir, meshes));
        }
    }
    best.map(|(_, _, meshes)| meshes).unwrap_or_default()
}

/// The render meshes for a tag opened in the Model view.
///
/// An object tag chases its own Blueprint. A `model`, `collision_model` or
/// `skeleton_model` tag finds the object tag that names it — by convention
/// they share the same path.
#[tauri::command]
fn object_render_model(index: usize, state: State<'_, AppState>) -> Result<Vec<RenderMeshRef>, String> {
    with_catalog(&state, |c| {
        let entry = c.entry(index).ok_or("tag index out of range")?;
        if OBJECT_GROUPS.contains(&entry.group.as_str()) {
            return Ok(render_mesh_refs(c, index));
        }
        if !matches!(entry.group.as_str(), "model" | "collision_model" | "skeleton_model") {
            return Ok(Vec::new());
        }
        let short = entry.short.clone();
        let object = c.tags.iter().position(|t| {
            OBJECT_GROUPS.contains(&t.group.as_str()) && t.short.eq_ignore_ascii_case(&short)
        });
        Ok(object.map(|oi| render_mesh_refs(c, oi)).unwrap_or_default())
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
        let tag = blam_tag::TagFile::parse(&file, Some(file.len()))
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

/// A small render of one texture for a preview card.
///
/// Unlike `read_texture` this never consults the mod project — the card shows
/// shipped pixels — and never populates the swap-related fields, so it takes
/// only the catalog lock. `max_dim` is clamped: below 16 the card is noise,
/// above 512 it is a viewer's job.
#[tauri::command]
fn read_texture_thumb(
    index: usize,
    max_dim: u32,
    state: State<'_, AppState>,
) -> Result<TextureView, String> {
    with_catalog(&state, |c| {
        let path = c
            .textures
            .get(index)
            .ok_or("texture index out of range")?
            .short
            .clone();
        let (tex, img) = decode_texture(c, index, max_dim.clamp(16, 512))?;
        let png = textures::to_png(&img)?;
        Ok(TextureView {
            path,
            width: tex.width,
            height: tex.height,
            format: img.format.clone(),
            mip: img.mip,
            num_mips: tex.num_mips,
            png: data_uri(&png),
            // The card offers no replace, so encodability is nobody's business.
            unsupported: None,
            replaced: false,
        })
    })
}

/// Every tag whose body references this one.
///
/// The first call per session builds the reverse index — reading and scanning
/// every tag chunk, tens of seconds of work — so this runs on a blocking thread,
/// reached through the app handle because `State` cannot cross into
/// `spawn_blocking`. The catalog mutex is held for the build and every other
/// command waits it out; the caller is watching the one spinner that explains
/// why. Every later call is an index lookup.
#[tauri::command]
async fn referencing_tags(
    index: usize,
    app: tauri::AppHandle,
) -> Result<Vec<TagSummary>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<AppState>();
        let guard = state.catalog.lock().map_err(|e| e.to_string())?;
        let c = guard.as_ref().ok_or("no installation is open")?;
        c.referencing(index, MAX_ROWS)
    })
    .await
    .map_err(|e| e.to_string())?
}

/// One field that differs between two tags (or a tag and its edits).
#[derive(Serialize)]
struct FieldDiffView {
    path: String,
    a: Option<String>,
    b: Option<String>,
}

/// Two tags compared field by field.
#[derive(Serialize)]
struct DiffView {
    a: String,
    b: String,
    /// Fields both sides decode to, with values.
    fields: Vec<FieldDiffView>,
    /// Materialised fields the two sides agree on.
    same: usize,
    /// Set when a side did not decode; the fields list is then empty.
    error: Option<String>,
}

/// Elements per block the diff materialises. Past this a block is compared
/// by count alone, which the view says.
const DIFF_ELEMENTS: usize = 64;

fn diff_of(a_label: String, a_bytes: &[u8], b_label: String, b_bytes: &[u8]) -> DiffView {
    let fa = blam_tag::diff::flatten(a_bytes, a_bytes.len(), DIFF_ELEMENTS);
    let fb = blam_tag::diff::flatten(b_bytes, b_bytes.len(), DIFF_ELEMENTS);
    match (fa, fb) {
        (Some(fa), Some(fb)) => {
            let fields: Vec<FieldDiffView> = blam_tag::diff::diff_maps(&fa, &fb)
                .into_iter()
                .map(|d| FieldDiffView {
                    path: d.path,
                    a: d.before,
                    b: d.after,
                })
                .collect();
            let same = fa.iter().filter(|(k, v)| fb.get(*k) == Some(v)).count();
            DiffView {
                a: a_label,
                b: b_label,
                fields,
                same,
                error: None,
            }
        }
        (fa, fb) => DiffView {
            a: a_label,
            b: b_label,
            fields: Vec::new(),
            same: 0,
            error: Some(match (fa.is_some(), fb.is_some()) {
                (false, false) => "neither side decodes".into(),
                (false, true) => "the first side does not decode".into(),
                _ => "the second side does not decode".into(),
            }),
        },
    }
}

/// Compare two tags of the same group as the editor sees them, pending edits
/// included, field by field.
#[tauri::command]
fn diff_tags(a: usize, b: usize, state: State<'_, AppState>) -> Result<DiffView, String> {
    let key_a = tag_key(&state, a)?;
    let key_b = tag_key(&state, b)?;
    if key_a.0 != key_b.0 {
        return Err(format!(
            "a {} tag and a {} tag have different layouts; compare tags of one group",
            key_a.0, key_b.0
        ));
    }
    let pending_a = pending_for(&state, &key_a)?;
    let pending_b = pending_for(&state, &key_b)?;
    with_catalog(&state, |c| {
        let bytes_a = patched_bytes(c, a, &pending_a)?;
        let bytes_b = patched_bytes(c, b, &pending_b)?;
        Ok(diff_of(
            format!("{}.{}", key_a.1, key_a.0),
            &bytes_a,
            format!("{}.{}", key_b.1, key_b.0),
            &bytes_b,
        ))
    })
}

/// Compare a tag as shipped with the tag as the mod leaves it: every field
/// the recipe changes, including those inside elements the recipe added.
#[tauri::command]
fn diff_edits(index: usize, state: State<'_, AppState>) -> Result<DiffView, String> {
    let key = tag_key(&state, index)?;
    let pending = pending_for(&state, &key)?;
    let script = script_for(&state, &key)?;
    with_catalog(&state, |c| {
        let shipped = c.read_tag(index)?;
        let edited = patched_with_script(c, index, &pending, script.as_deref())?;
        Ok(diff_of(
            "as shipped".into(),
            &shipped,
            "with this mod's edits".into(),
            &edited,
        ))
    })
}

/// One tag in a reference tree.
#[derive(Serialize)]
struct RefNode {
    /// Catalog index, when the reference resolves in this installation.
    index: Option<usize>,
    group: String,
    /// The path as the referencing body wrote it.
    path: String,
    /// The tag references itself through an ancestor, so it is not expanded.
    cycle: bool,
    /// Children not built: the depth limit or the node budget stopped here.
    truncated: bool,
    children: Vec<RefNode>,
}

/// Children per node and nodes in total a reference tree may build. A
/// scenario references thousands of tags directly; the caps keep a tree
/// browsable and the command quick.
const REF_TREE_CHILDREN: usize = 200;
const REF_TREE_NODES: usize = 4000;

/// A tag's body references, resolved: `(four-CC, path, catalog index)`.
fn body_refs(c: &Catalog, index: usize, pending: &[PendingEdit]) -> Result<Vec<(String, String, Option<usize>)>, String> {
    let file = patched_bytes(c, index, pending)?;
    let data = blam_tag::TagFile::parse(&file, Some(file.len()))
        .ok()
        .and_then(|t| t.data().map(|d| d.content.to_vec()))
        .unwrap_or_else(|| file.clone());
    let mut seen = std::collections::BTreeSet::new();
    let mut out = Vec::new();
    for (cc, path) in blam_tag::refs::tgrf_refs(&data, |cc| c.group_of_four_cc(cc).is_some()) {
        if !seen.insert((cc.clone(), catalog::normalize_ref_path(&path))) {
            continue;
        }
        let hit = c.resolve_ref(&cc, &path);
        out.push((cc, path, hit));
    }
    Ok(out)
}

fn build_ref_tree(
    c: &Catalog,
    state: &State<'_, AppState>,
    index: usize,
    depth: usize,
    trail: &mut Vec<usize>,
    budget: &mut usize,
) -> Result<Vec<RefNode>, String> {
    if depth == 0 || *budget == 0 {
        return Ok(Vec::new());
    }
    let key = tag_key(state, index)?;
    let pending = pending_for(state, &key)?;
    let refs = body_refs(c, index, &pending)?;
    let mut children = Vec::new();
    for (i, (cc, path, hit)) in refs.into_iter().enumerate() {
        if i >= REF_TREE_CHILDREN || *budget == 0 {
            if let Some(last) = children.last_mut() {
                let last: &mut RefNode = last;
                last.truncated = true;
            }
            break;
        }
        *budget -= 1;
        let group = c.group_of_four_cc(&cc).unwrap_or(&cc).to_string();
        let cycle = hit.is_some_and(|h| trail.contains(&h));
        let mut node = RefNode {
            index: hit,
            group,
            path,
            cycle,
            truncated: false,
            children: Vec::new(),
        };
        if let (Some(h), false) = (hit, cycle) {
            if depth > 1 {
                trail.push(h);
                node.children = build_ref_tree(c, state, h, depth - 1, trail, budget)?;
                trail.pop();
            } else {
                node.truncated = true;
            }
        }
        children.push(node);
    }
    Ok(children)
}

/// The tags a tag references, and what they reference, to `depth` levels.
/// Built from the bodies as the editor sees them, pending edits included.
#[tauri::command]
fn reference_tree(index: usize, depth: usize, state: State<'_, AppState>) -> Result<RefNode, String> {
    let key = tag_key(&state, index)?;
    let depth = depth.clamp(1, 6);
    with_catalog(&state, |c| {
        let mut budget = REF_TREE_NODES;
        let mut trail = vec![index];
        let children = build_ref_tree(c, &state, index, depth, &mut trail, &mut budget)?;
        Ok(RefNode {
            index: Some(index),
            group: key.0.clone(),
            path: key.1.clone(),
            cycle: false,
            truncated: budget == 0,
            children,
        })
    })
}

/// Tags of a group that no shipped tag's body references. The reverse index
/// is built on first use (seconds, cached afterwards), so this runs off the
/// UI thread. A tag the Unreal side loads directly — a scenario, the globals
/// — is unreferenced by this measure and still very much in use.
#[tauri::command]
async fn unreferenced_tags(group: String, app: tauri::AppHandle) -> Result<Vec<TagSummary>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<AppState>();
        let guard = state.catalog.lock().map_err(|e| e.to_string())?;
        let c = guard.as_ref().ok_or("no installation is open")?;
        let mut out = Vec::new();
        for t in c.tags_in(&group, usize::MAX) {
            if c.referencing(t.index, 1)?.is_empty() {
                out.push(t);
            }
            if out.len() >= MAX_ROWS {
                break;
            }
        }
        Ok(out)
    })
    .await
    .map_err(|e| e.to_string())?
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
        let bytes = export_texture_bytes(c, index, &dest)?;
        std::fs::write(&dest, &bytes).map_err(|e| format!("{dest}: {e}"))?;
        Ok(bytes.len())
    })
}

/// A texture as the file the destination's extension asks for: `.dds` keeps
/// the cooked pixel format and every mip, `.tif`/`.tiff` and `.png` decode
/// the largest mip to RGBA.
fn export_texture_bytes(c: &Catalog, index: usize, dest: &str) -> Result<Vec<u8>, String> {
    let ext = std::path::Path::new(dest)
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| e.to_ascii_lowercase())
        .unwrap_or_default();
    match ext.as_str() {
        "dds" => {
            let uasset = c.read_texture_uasset(index)?;
            let header = textures::zen_header_size(&uasset).ok_or("not a zen package")?;
            let tex = textures::parse_texture(&uasset[header..])?;
            let ubulk = c.read_texture_ubulk(index).unwrap_or_default();
            textures::dds::write_dds(&tex, &ubulk)
        }
        "tif" | "tiff" => {
            let (_, img) = decode_texture(c, index, u32::MAX)?;
            textures::to_tiff(&img)
        }
        _ => {
            let (_, img) = decode_texture(c, index, u32::MAX)?;
            textures::to_png(&img)
        }
    }
}

/// A mesh as glTF binary: every LOD, a primitive per section named after its
/// material slot, in metres and +Y up. A skeletal mesh comes out in its rest
/// pose with the bones as nodes.
#[tauri::command]
fn export_mesh(index: usize, dest: String, state: State<'_, AppState>) -> Result<usize, String> {
    with_catalog(&state, |c| {
        let entry = c.meshes.get(index).ok_or("mesh index out of range")?;
        let name = entry.short.rsplit('/').next().unwrap_or(&entry.short).to_string();
        let usmap = usmap()?;
        let data = c.read_mesh_uasset(index)?;
        let ubulk = c.read_mesh_ubulk(index)?;
        let package = ue_asset::zen::Package::parse(&data).map_err(|e| e.to_string())?;
        let scripts = c.script_objects().ok_or("no script-object table")?;
        let wanted_class = if entry.skeletal { "SkeletalMesh" } else { "StaticMesh" };
        let export = package
            .exports
            .iter()
            .position(|e| scripts.leaf(e.class) == Some(wanted_class))
            .ok_or_else(|| format!("{} has no {wanted_class} export", entry.short))?;
        let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;
        let ctx = ue_asset::unversioned::Ctx {
            usmap,
            names: &package.names,
        };
        let bulk_map = ue_asset::mesh::bulk_map_of(&data);
        let glb = if entry.skeletal {
            let sk = ue_asset::mesh::parse_skeletal_mesh_with_bulk_map(&ctx, bytes, ubulk.as_deref(), &bulk_map)
                .map_err(|e| e.to_string())?;
            let lods: Vec<ue_asset::mesh::Lod> = sk.export_lods().into_iter().cloned().collect();
            ue_asset::gltf::write_glb(&ue_asset::gltf::MeshExport {
                name: &name,
                materials: &sk.materials,
                lods: &lods,
                bones: &sk.bones,
            })?
        } else {
            let sm = ue_asset::mesh::parse_static_mesh_with_bulk_map(&ctx, bytes, ubulk.as_deref(), &bulk_map)
                .map_err(|e| e.to_string())?;
            let lods: Vec<ue_asset::mesh::Lod> = sm.export_lods().into_iter().cloned().collect();
            ue_asset::gltf::write_glb(&ue_asset::gltf::MeshExport {
                name: &name,
                materials: &sm.materials,
                lods: &lods,
                bones: &[],
            })?
        };
        std::fs::write(&dest, &glb).map_err(|e| format!("{dest}: {e}"))?;
        Ok(glb.len())
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

/// One tag the mod adds, for the project change list.
#[derive(Serialize)]
struct NewTagView {
    group: String,
    tag: String,
    /// The shipped tag it was cloned from.
    from: String,
    asset_reference: Option<String>,
    /// Catalog index in the open installation, so the panel can open it.
    /// `None` means the donor is no longer shipped, so the clone has no bytes.
    index: Option<usize>,
    /// How many of its fields the mod changes from the donor's.
    edits: usize,
}

#[derive(Serialize)]
struct ProjectView {
    root: String,
    meta: project::Meta,
    changes: Vec<TagChange>,
    /// Textures the mod replaces.
    textures: Vec<TextureChange>,
    /// Tags the mod adds.
    new_tags: Vec<NewTagView>,
    /// Files a test install left in the Paks folder, so the panel can show
    /// that the mod is currently installed for testing.
    test_files: Vec<String>,
}

/// The project change list, with each edit resolved against the open
/// installation so the panel can show shipped → modded values and flag
/// anything the last game update broke.
fn changes_for(
    c: &Catalog,
    edits: &BTreeMap<TagKey, Vec<PendingEdit>>,
    new_tags: &BTreeMap<TagKey, NewTagSpec>,
) -> Vec<TagChange> {
    edits
        .iter()
        // A new tag's edits are part of the new tag, shown on its own row.
        .filter(|(key, _)| !new_tags.contains_key(key))
        .map(|((group, tag), pending)| {
            let index = c.tag_index(group, tag);
            // Replayed rather than merely resolved: an edit inside an element
            // that an earlier op added only resolves once the op has applied.
            let resolved = index.and_then(|i| {
                let file = c.read_tag(i).ok()?;
                let (_, outcomes) = apply_pending(file, pending).ok()?;
                Some(
                    outcomes
                        .into_iter()
                        .map(|o| FieldChange {
                            field: o.path,
                            value: o.value,
                            before: o.before,
                            stale: !o.applied,
                        })
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
    let (root, meta, edits, swaps, added) = {
        let work = state.work.lock().map_err(|e| e.to_string())?;
        match &work.project {
            None => return Ok(None),
            Some(p) => (
                p.root.display().to_string(),
                p.meta.clone(),
                work.edits.clone(),
                work.textures.clone(),
                work.new_tags.clone(),
            ),
        }
    };
    let (changes, textures, new_tags, test_files) = with_catalog(state, |c| {
        let textures = swaps
            .iter()
            .map(|(path, png)| TextureChange {
                path: path.clone(),
                index: c.texture_index(path),
                bytes: png.len(),
            })
            .collect();
        let new_tags = added
            .iter()
            .map(|((group, tag), spec)| NewTagView {
                group: group.clone(),
                tag: tag.clone(),
                from: spec.from.clone(),
                asset_reference: spec.asset_reference.clone(),
                index: c.new_tag_index(group, tag),
                edits: edits.get(&(group.clone(), tag.clone())).map_or(0, Vec::len),
            })
            .collect();
        Ok((
            changes_for(c, &edits, &added),
            textures,
            new_tags,
            modpack::test_files(c.paks()),
        ))
    })?;
    Ok(Some(ProjectView {
        root,
        meta,
        changes,
        textures,
        new_tags,
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
    let new_tags: BTreeMap<TagKey, NewTagSpec> = p
        .load_new_tags()?
        .into_iter()
        .map(|t| {
            (
                (t.group, t.tag),
                NewTagSpec {
                    from: t.from,
                    asset_reference: t.asset_reference,
                },
            )
        })
        .collect();
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
        work.new_tags = new_tags.clone();
        work.history.clear();
        work.project = Some(p);
    }
    {
        let mut guard = state.catalog.lock().map_err(|e| e.to_string())?;
        if let Some(c) = guard.as_mut() {
            restore_new_tags(c, &new_tags);
        }
    }
    install::remember_project(Some(&dir));
    project_view(&state)?.ok_or_else(|| "the project did not open".to_string())
}

/// Close the project. Edits are already on disk — autosave runs on every
/// change — so this only clears the workbench.
#[tauri::command]
fn project_close(state: State<'_, AppState>) -> Result<(), String> {
    {
        let mut work = state.work.lock().map_err(|e| e.to_string())?;
        work.project = None;
        work.edits.clear();
        work.scripts.clear();
        work.textures.clear();
        work.new_tags.clear();
        work.history.clear();
    }
    {
        let mut guard = state.catalog.lock().map_err(|e| e.to_string())?;
        if let Some(c) = guard.as_mut() {
            c.clear_new_tags();
        }
    }
    install::remember_project(None);
    Ok(())
}

/// Put the workbench's new tags into a catalog, replacing whatever it held.
///
/// A new tag whose donor this installation no longer ships is left out; the
/// project panel shows it without an index so it can be removed.
fn restore_new_tags(c: &mut Catalog, new_tags: &BTreeMap<TagKey, NewTagSpec>) {
    c.clear_new_tags();
    for ((group, tag), spec) in new_tags {
        if let Some(donor) = c.tag_index(group, &spec.from) {
            let _ = c.add_new_tag(group, tag, donor);
        }
    }
}

/// Mirror the new-tag list into `edits.json`, when a project is open.
fn save_new_tags(work: &Workbench) -> Result<(), String> {
    let Some(p) = &work.project else {
        return Ok(());
    };
    p.save_edits_and_new_tags(&work.saved_edits(), &work.saved_new_tags())
}

/// Add a tag to the mod: a clone of the shipped tag at `from`, under a new
/// path in the same group, optionally bound to a different Unreal asset.
///
/// The clone starts as the donor currently is in the mod — the donor's
/// pending edits are copied to it — and is opened like any other tag. Its
/// bytes only exist at bake time; until then it reads as the donor plus the
/// edits recorded under its own name.
#[tauri::command]
fn project_new_tag(
    from: usize,
    path: String,
    asset_reference: Option<String>,
    state: State<'_, AppState>,
) -> Result<NewTagView, String> {
    let short = blam_pack::newtag::normalize_path(&path)?;
    let asset_reference = asset_reference
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty());
    if let Some(a) = &asset_reference {
        if !a.starts_with("/Game/") || a.contains('.') {
            return Err(
                "an asset reference is the package path of a Blueprint or asset, e.g. \
                 /Game/Blueprints/Weapons/BP_Pistol"
                    .into(),
            );
        }
    }
    let (group, donor_short, index) = {
        let mut guard = state.catalog.lock().map_err(|e| e.to_string())?;
        let c = guard.as_mut().ok_or("no installation is open")?;
        let donor = c.entry(from).ok_or("tag index out of range")?;
        let group = donor.group.clone();
        let donor_short = donor.short.clone();
        let index = c.add_new_tag(&group, &short, from)?;
        (group, donor_short, index)
    };
    let mut work = state.work.lock().map_err(|e| e.to_string())?;
    let key = (group.clone(), short.clone());
    let inherited = work
        .edits
        .get(&(group.clone(), donor_short.clone()))
        .cloned()
        .unwrap_or_default();
    let edits = inherited.len();
    if !inherited.is_empty() {
        work.edits.insert(key.clone(), inherited);
    }
    work.new_tags.insert(
        key,
        NewTagSpec {
            from: donor_short.clone(),
            asset_reference: asset_reference.clone(),
        },
    );
    save_new_tags(&work)?;
    Ok(NewTagView {
        group,
        tag: short,
        from: donor_short,
        asset_reference,
        index: Some(index),
        edits,
    })
}

/// Drop a new tag from the mod, with every edit recorded under its name.
#[tauri::command]
fn project_remove_new_tag(
    group: String,
    tag: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let key = (group.clone(), tag.clone());
    {
        let mut work = state.work.lock().map_err(|e| e.to_string())?;
        work.new_tags
            .remove(&key)
            .ok_or("this tag is not one the mod adds")?;
        work.edits.remove(&key);
        save_new_tags(&work)?;
    }
    let mut guard = state.catalog.lock().map_err(|e| e.to_string())?;
    if let Some(c) = guard.as_mut() {
        c.remove_new_tag(&group, &tag);
    }
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
    work.remember(&key);
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

/// What a bake consumes: chunk overrides, new packages, and the warnings the
/// resolution raised on the way.
type Resolved = (
    Vec<modpack::ResolvedEdit>,
    Vec<modpack::NewTagPackage>,
    Vec<String>,
);

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
    new_tags: &BTreeMap<TagKey, NewTagSpec>,
) -> Result<Resolved, String> {
    let mut out = Vec::new();
    let mut warnings = Vec::new();
    resolve_textures(c, textures, &mut out)?;
    // A scenario may be changed only by its script, with no field edits at all,
    // so the two sets are walked together rather than iterating `edits` alone.
    let keys: std::collections::BTreeSet<&TagKey> = edits.keys().chain(scripts.keys()).collect();
    for key in keys {
        let (group, tag) = key;
        // A new tag's edits become its own package below. Packing them here
        // would override the donor's chunk with the clone's bytes.
        if new_tags.contains_key(key) {
            continue;
        }
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

        // Every edit in the recipe must land; one failing to apply means
        // the game updated underneath it. The replay is the authority — an
        // edit inside an element the recipe itself adds resolves only once
        // the add has applied, so resolving against the shipped bytes alone
        // would call it stale.
        {
            let (_, outcomes) = apply_pending(original.clone(), pending)
                .map_err(|e| format!("{label}: {e}"))?;
            let missing = outcomes.iter().filter(|o| !o.applied).count();
            if missing != 0 {
                return Err(format!(
                    "{label}: {missing} of {} edits no longer resolve — the game may have \
                     updated; revert the stale edits first",
                    pending.len()
                ));
            }
            for o in &outcomes {
                if o.type_name == "string id" && o.before.as_deref() != Some(o.value.as_str()) {
                    warnings.push(format!(
                        "{label}: \"{}\" sets a string id. A string the game does not \
                         already know makes it reject the whole tag (the weapon simply \
                         vanishes in game) — test before sharing.",
                        o.path
                    ));
                }
            }
        }

        let patched = patched_with_script(c, index, pending, script)?;
        if patched == original {
            continue;
        }
        // And the result must still be a tag that walks exactly.
        check_walks(&label, &patched)?;
        out.push(modpack::ResolvedEdit {
            label,
            container: entry.container,
            chunk: entry.chunk,
            original_len: original.len(),
            patched,
        });
    }

    let mut additions = Vec::new();
    for ((group, tag), spec) in new_tags {
        let label = format!("{tag}.{group}");
        let donor = c.tag_index(group, &spec.from).ok_or_else(|| {
            format!(
                "{label}: cloned from {}.{group}, which this installation does not ship — \
                 remove the new tag first",
                spec.from
            )
        })?;
        let entry = c.entry(donor).ok_or("tag index out of range")?;
        let original = c.read_tag(donor)?;
        let no_edits = Vec::new();
        let pending = edits
            .get(&(group.clone(), tag.clone()))
            .unwrap_or(&no_edits);
        let (patched, outcomes) =
            apply_pending(original, pending).map_err(|e| format!("{label}: {e}"))?;
        let missing = outcomes.iter().filter(|o| !o.applied).count();
        if missing != 0 {
            return Err(format!(
                "{label}: {missing} of {} edits no longer resolve — the game may have \
                 updated; revert the stale edits first",
                pending.len()
            ));
        }
        check_walks(&label, &patched)?;
        let donor_uasset = c
            .read_tag_uasset(donor)
            .map_err(|e| format!("{label}: donor wrapper: {e}"))?;
        let resolve = |cc: &str, path: &str| -> Option<String> {
            c.resolve_ref(cc, path)
                .and_then(|i| c.entry(i))
                .map(|e| package_name_of(&e.path))
        };
        let built = blam_pack::newtag::build(
            &blam_pack::newtag::NewTag {
                group,
                path: tag,
                body: &patched,
                donor_uasset: &donor_uasset,
                asset_reference: spec.asset_reference.as_deref(),
            },
            usmap()?,
            resolve,
        )
        .map_err(|e| format!("{label}: {e}"))?;
        if built.dangling > 0 {
            warnings.push(format!(
                "{label}: {} reference(s) in it point at tags this installation does not \
                 ship, so they resolve to nothing in game.",
                built.dangling
            ));
        }
        let source = c
            .container(entry.container)
            .ok_or("source container index out of range")?;
        let (uasset_meta, ubulk_meta) =
            blam_pack::newtag::donor_chunk_meta(source, entry.chunk.chunk_id)?;
        let mut package = built.package;
        package.uasset_meta = uasset_meta;
        package.ubulk_meta = ubulk_meta;
        additions.push(modpack::NewTagPackage {
            label,
            source: entry.container,
            package,
        });
    }

    // A new tag nothing points at is never loaded. The references are read
    // from the bodies the mod ships — edited shipped tags and the other new
    // tags — the same way the loader's preload list is derived.
    if !additions.is_empty() {
        let mut referenced: std::collections::BTreeSet<(String, String)> = Default::default();
        let bodies = out
            .iter()
            .map(|e| e.patched.as_slice())
            .chain(additions.iter().map(|a| a.package.ubulk.as_slice()));
        for body in bodies {
            for (cc, path) in blam_tag::refs::tgrf_refs(body, |_| true) {
                referenced.insert((cc, catalog::normalize_ref_path(&path)));
            }
        }
        for (group, tag) in new_tags.keys() {
            let Some(cc) = c.four_cc_of_group(group) else {
                continue;
            };
            if !referenced.contains(&(cc.to_string(), catalog::normalize_ref_path(tag))) {
                warnings.push(format!(
                    "{tag}.{group} is referenced by nothing in the mod, so the game will never \
                     load it. Point a tag at `{group}:{}` to use it.",
                    tag.replace('/', "\\")
                ));
            }
        }
    }

    if out.is_empty() && additions.is_empty() {
        return Err("the mod changes nothing yet — edit a tag first".into());
    }
    Ok((out, additions, warnings))
}

/// A patched tag must still be a tag that walks exactly.
fn check_walks(label: &str, patched: &[u8]) -> Result<(), String> {
    let parsed = blam_tag::TagFile::parse(patched, Some(patched.len()))
        .map_err(|e| format!("{label}: {e}"))?;
    let layout = parsed.layout().map_err(|e| format!("{label}: {e}"))?;
    let block = parsed
        .read_data(&layout)
        .map_err(|e| format!("{label}: {e}"))?;
    let expected = parsed
        .data()
        .map(|d| d.size as usize)
        .unwrap_or(patched.len());
    if block.consumed != expected {
        return Err(format!(
            "{label}: the patched tag does not read back exactly"
        ));
    }
    Ok(())
}

/// A catalog entry's container path as the package name the cooker gave it:
/// `../../../Meteorite/Content/Tags/x/y-group.ubulk` is `/Game/Tags/x/y-group`.
fn package_name_of(path: &str) -> String {
    let stem = path.trim_end_matches(".ubulk");
    match stem.strip_prefix("../../../Meteorite/Content/") {
        Some(rest) => format!("/Game/{rest}"),
        None => stem.to_string(),
    }
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
    let (root, meta, (edits, scripts, swaps, added)) = {
        let work = state.work.lock().map_err(|e| e.to_string())?;
        let p = work.project.as_ref().ok_or("no project is open")?;
        (
            p.root.clone(),
            p.meta.clone(),
            (
                work.edits.clone(),
                work.scripts.clone(),
                work.textures.clone(),
                work.new_tags.clone(),
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
        let (resolved, additions, mut warnings) =
            resolved_edits(c, &edits, &scripts, &swaps, &added)?;
        let baked = modpack::bake(c, &meta.slug, resolved, additions)?;
        let build_dir = root.join("build");
        modpack::write_and_verify(&build_dir, &baked, c.oodle_paths())?;

        // The declared change list the hub and launcher show players. Built
        // from the same resolved view as the editor's Changes panel, so what
        // the mod page says is what the author saw at export.
        let declared = modpack::DeclaredChanges {
            schema_version: 1,
            tags: changes_for(c, &edits, &added)
                .into_iter()
                .map(|t| modpack::DeclaredTag {
                    group: t.group,
                    tag: t.tag,
                    fields: t
                        .edits
                        .into_iter()
                        .map(|e| modpack::DeclaredField {
                            field: e.field,
                            before: e.before,
                            value: e.value,
                        })
                        .collect(),
                })
                .collect(),
            textures: swaps
                .iter()
                .map(|(path, png)| modpack::DeclaredTexture {
                    path: path.clone(),
                    bytes: png.len(),
                })
                .collect(),
            scripts: scripts
                .keys()
                .map(|(group, tag)| modpack::DeclaredScript {
                    group: group.clone(),
                    tag: tag.clone(),
                })
                .collect(),
            new_tags: added
                .iter()
                .map(|((group, tag), spec)| modpack::DeclaredNewTag {
                    group: group.clone(),
                    tag: tag.clone(),
                    from: spec.from.clone(),
                })
                .collect(),
        };
        let changes_json =
            serde_json::to_string_pretty(&declared).map_err(|e| e.to_string())? + "\n";

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
        if meta.summary.trim().is_empty() && !readme.is_file() {
            warnings.push(
                "The mod has no summary and no README.md, so its hub page will say nothing \
                 about it. Add a summary in the project settings or a README.md in the \
                 project folder."
                    .into(),
            );
        }
        let size = modpack::write_archive(
            &archive,
            &meta,
            &baked,
            readme.is_file().then(|| readme.as_path()),
            Some(&changes_json),
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
    let (meta, (edits, scripts, swaps, added)) = {
        let work = state.work.lock().map_err(|e| e.to_string())?;
        let p = work.project.as_ref().ok_or("no project is open")?;
        (
            p.meta.clone(),
            (
                work.edits.clone(),
                work.scripts.clone(),
                work.textures.clone(),
                work.new_tags.clone(),
            ),
        )
    };
    with_catalog(&state, |c| {
        let (resolved, additions, warnings) = resolved_edits(c, &edits, &scripts, &swaps, &added)?;
        let baked = modpack::bake(c, &meta.slug, resolved, additions)?;
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
            resolve_refs,
            peek_tag,
            referencing_tags,
            read_model_geometry,
            object_render_model,
            read_sbsp_world,
            read_scenario_layout,
            read_mesh,
            set_field,
            add_element,
            insert_element,
            remove_element,
            duplicate_element,
            copy_element,
            paste_element,
            copy_block_tsv,
            paste_block_tsv,
            live_status,
            live_forget,
            live_poke,
            live_census,
            live_loaded,
            live_probe,
            revert_field,
            revert_tag,
            undo_edit,
            redo_edit,
            export_tag,
            project_status,
            project_new,
            project_open,
            project_close,
            project_set_meta,
            project_revert,
            project_new_tag,
            project_remove_new_tag,
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
            read_texture_thumb,
            read_scripts,
            decompile_script,
            export_script,
            compile_scripts,
            set_scripts,
            revert_scripts,
            export_texture,
            export_mesh,
            swap_texture,
            revert_texture,
            list_sounds,
            read_sound,
            sound_tag_media,
            play_bank_media,
            export_sound,
            play_sound,
            tag_links,
            diff_tags,
            diff_edits,
            reference_tree,
            unreferenced_tags,
            list_dir,
            search_files,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn edit(path: &str, value: &str) -> PendingEdit {
        PendingEdit {
            path: path.into(),
            value: value.into(),
        }
    }

    #[test]
    fn the_journal_steps_edits_back_and_forward_and_forks_on_a_new_change() {
        let key: TagKey = ("weapon".into(), "objects/weapons/pistol/pistol".into());
        let mut w = Workbench::default();
        assert!(!w.undo(&key), "nothing to undo on a fresh tag");

        // Two edits, each remembered before it lands.
        w.remember(&key);
        w.edits.insert(key.clone(), vec![edit("a", "1")]);
        w.remember(&key);
        w.edits
            .get_mut(&key)
            .unwrap()
            .push(edit("b", "2"));
        assert_eq!(w.history_of(&key).undo, 2);

        assert!(w.undo(&key));
        assert_eq!(w.edits[&key].len(), 1);
        assert!(w.undo(&key));
        assert!(!w.edits.contains_key(&key), "an empty list is no entry");
        assert_eq!(w.history_of(&key).redo, 2);
        assert!(!w.undo(&key));

        assert!(w.redo(&key));
        assert_eq!(w.edits[&key].len(), 1);
        assert_eq!(w.edits[&key][0].path, "a");

        // A new change after an undo drops what could have been redone.
        w.remember(&key);
        w.edits.get_mut(&key).unwrap().push(edit("c", "3"));
        assert_eq!(w.history_of(&key).redo, 0);
        assert_eq!(w.history_of(&key).undo, 2);
    }

    #[test]
    fn a_field_path_finds_its_node() {
        use blam_tag::view::{Kind, Node};
        let leaf = |name: &str| Node {
            kind: Kind::Field,
            name: name.into(),
            type_name: "real".into(),
            offset: 0,
            size: 4,
            value: blam_tag::Scalar::Real(1.5),
            options: Vec::new(),
            block_name: None,
            max_count: None,
            count: None,
            children: Vec::new(),
        };
        let element = |fields: Vec<Node>| Node {
            kind: Kind::Element,
            name: String::new(),
            type_name: String::new(),
            offset: 0,
            size: 0,
            value: blam_tag::Scalar::Empty,
            options: Vec::new(),
            block_name: None,
            max_count: None,
            count: None,
            children: fields,
        };
        let block = Node {
            kind: Kind::Block,
            name: "barrels".into(),
            type_name: "block".into(),
            offset: 0,
            size: 0,
            value: blam_tag::Scalar::Empty,
            options: Vec::new(),
            block_name: Some("weapon_barrels".into()),
            max_count: Some(2),
            count: Some(2),
            children: vec![element(vec![leaf("spread")]), element(vec![leaf("spread")])],
        };
        let nodes = vec![leaf("mass"), block];
        assert_eq!(find_node(&nodes, "mass").map(|n| n.name.as_str()), Some("mass"));
        assert!(matches!(find_node(&nodes, "barrels").map(|n| n.kind), Some(Kind::Block)));
        assert!(matches!(find_node(&nodes, "barrels[1]").map(|n| n.kind), Some(Kind::Element)));
        assert_eq!(
            find_node(&nodes, "barrels[1].spread").map(|n| n.type_name.as_str()),
            Some("real")
        );
        assert!(find_node(&nodes, "barrels[2].spread").is_none());
        assert!(find_node(&nodes, "nothing").is_none());

        let mut steps = Vec::new();
        let mut skipped = Vec::new();
        element_recipe(&nodes[1].children[0], "", true, &mut steps, &mut skipped);
        assert_eq!(steps.len(), 1);
        assert_eq!(steps[0].path, "spread");
        assert_eq!(steps[0].value, "1.5");
        assert!(skipped.is_empty());
    }

    /// Every recipe text must parse back to exactly the value it came from —
    /// the promise a paste relies on. Checked over the first tag of every
    /// group in a real installation.
    #[test]
    fn recipe_text_round_trips_every_field_of_every_group() {
        let Ok(paks) = std::env::var("HCE_PAKS") else {
            return;
        };
        let c = Catalog::open(&paks, "").unwrap();
        let mut checked = 0usize;
        let mut failures: Vec<String> = Vec::new();
        for group in c.groups().unwrap() {
            let Some(t) = c.tags_in(&group.group, 1).into_iter().next() else {
                continue;
            };
            let file = c.read_tag(t.index).unwrap();
            let tag = blam_tag::TagFile::parse(&file, Some(file.len())).unwrap();
            let layout = tag.layout().unwrap();
            let Ok(block) = tag.read_data(&layout) else {
                continue;
            };
            // Cap the walk: a scenario has millions of elements.
            let nodes = blam_tag::view::root_capped(&layout, &block, 4);
            let root = blam_tag::view::Node {
                kind: blam_tag::view::Kind::Element,
                name: String::new(),
                type_name: String::new(),
                offset: 0,
                size: 0,
                value: blam_tag::Scalar::Empty,
                options: Vec::new(),
                block_name: None,
                max_count: None,
                count: None,
                children: nodes,
            };
            let mut steps = Vec::new();
            let mut skipped = Vec::new();
            element_recipe(&root, "", true, &mut steps, &mut skipped);
            for step in steps.iter().filter(|s| !s.op) {
                let target = match blam_tag::patch::resolve(&layout, &file, &block, &step.path) {
                    Ok(t) => t,
                    Err(e) => {
                        failures.push(format!("{}: {}: {e}", t.short, step.path));
                        continue;
                    }
                };
                let parsed = match target.type_name.as_str() {
                    // The two kinds `set_field` parses itself.
                    "string id" => Ok(blam_tag::Scalar::Text(step.value.clone())),
                    "tag reference" => parse_reference(&step.value).map_err(|e| e.to_string()),
                    _ => blam_tag::value::parse(&layout, &target.field, &step.value)
                        .map_err(|e| e.to_string()),
                };
                match parsed {
                    Ok(v) if scalar_matches(&v, &target.current) => checked += 1,
                    Ok(v) => failures.push(format!(
                        "{}: {} = {:?} parsed {:?} from {:?}",
                        t.short, step.path, target.current, v, step.value
                    )),
                    Err(e) => failures.push(format!("{}: {}: {e}", t.short, step.path)),
                }
            }
        }
        eprintln!("{checked} fields round-tripped");
        for f in &failures {
            eprintln!("FAIL {f}");
        }
        assert!(checked > 1000, "too few fields checked: {checked}");
        assert!(
            failures.is_empty(),
            "{} field(s) do not round-trip; first: {:?}",
            failures.len(),
            &failures[..failures.len().min(10)]
        );
    }

    /// Equality for the round-trip: a parsed enum or flags value carries the
    /// option names the layout resolves, which the reader also resolved, so a
    /// plain comparison holds; reals compare as their f32 bits after the
    /// display precision the text carries.
    fn scalar_matches(parsed: &blam_tag::Scalar, current: &blam_tag::Scalar) -> bool {
        use blam_tag::Scalar;
        match (parsed, current) {
            (Scalar::Real(a), Scalar::Real(b)) => {
                a == b || (a - b).abs() <= b.abs() * 1e-6 + 1e-6
            }
            (Scalar::Reals(a), Scalar::Reals(b)) => {
                a.len() == b.len()
                    && a
                        .iter()
                        .zip(b)
                        .all(|(x, y)| x == y || (x - y).abs() <= y.abs() * 1e-6 + 1e-6)
            }
            (Scalar::Enum { raw: a, .. }, Scalar::Enum { raw: b, .. }) => a == b,
            (Scalar::Flags { raw: a, .. }, Scalar::Flags { raw: b, .. }) => a == b,
            (Scalar::Reference { group: g1, path: p1 }, Scalar::Reference { group: g2, path: p2 }) => {
                p1 == p2 && (g1 == g2 || p1.is_empty())
            }
            (a, b) => a == b,
        }
    }

    /// On a real tag the expert view surfaces padding the plain view hides.
    #[test]
    fn the_expert_view_shows_padding_on_a_shipped_tag() {
        let Ok(paks) = std::env::var("HCE_PAKS") else {
            return;
        };
        let c = Catalog::open(&paks, "").unwrap();
        let t = c.tags_in("weapon", 1).into_iter().next().unwrap();
        let file = c.read_tag(t.index).unwrap();
        let tag = blam_tag::TagFile::parse(&file, Some(file.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();
        fn count(nodes: &[blam_tag::view::Node]) -> usize {
            nodes
                .iter()
                .map(|n| {
                    usize::from(matches!(n.type_name.as_str(), "pad" | "custom" | "terminator X"))
                        + count(&n.children)
                })
                .sum()
        }
        let plain = blam_tag::view::root(&layout, &block);
        let expert = blam_tag::view::root_expert(&layout, &block, 8);
        assert_eq!(count(&plain), 0);
        let shown = count(&expert);
        eprintln!("{shown} structural fields shown for {}", t.short);
        assert!(shown > 0, "a weapon layout carries padding");
        // Every one is a read-only raw leaf with a real offset.
        fn check(nodes: &[blam_tag::view::Node]) {
            for n in nodes {
                if matches!(n.type_name.as_str(), "pad" | "custom" | "terminator X") {
                    assert!(matches!(n.value, blam_tag::Scalar::Raw(_)), "{}", n.name);
                    assert!(!n.name.is_empty());
                }
                check(&n.children);
            }
        }
        check(&expert);
    }

    /// The diff and the reference tree on real tags: a tag against itself
    /// has no differences; two weapons differ somewhere; the rifle's body
    /// references resolve to loaded tags with the four-CCs the layout names.
    #[test]
    fn diff_and_reference_tree_on_shipped_tags() {
        let Ok(paks) = std::env::var("HCE_PAKS") else {
            return;
        };
        let c = Catalog::open(&paks, "").unwrap();
        let weapons = c.tags_in("weapon", 3);
        let a = c.read_tag(weapons[0].index).unwrap();
        let b = c.read_tag(weapons[1].index).unwrap();
        let same = diff_of("a".into(), &a, "a".into(), &a);
        assert!(same.error.is_none());
        assert!(same.fields.is_empty());
        assert!(same.same > 50);
        let differ = diff_of("a".into(), &a, "b".into(), &b);
        assert!(differ.error.is_none());
        assert!(!differ.fields.is_empty());

        let rifle = c
            .search("assault_rifle/assault_rifle", 20)
            .into_iter()
            .find(|t| t.group == "weapon" && t.short.ends_with("/assault_rifle"))
            .expect("the rifle ships");
        let refs = body_refs(&c, rifle.index, &[]).unwrap();
        assert!(refs.len() > 10, "the rifle references many tags: {}", refs.len());
        let resolved = refs.iter().filter(|(_, _, hit)| hit.is_some()).count();
        assert!(resolved > 0);
        for (cc, _, _) in &refs {
            assert!(c.group_of_four_cc(cc).is_some(), "{cc} is a known group");
        }
    }

    /// DDS export on shipped textures: a classic chain's first mip is the
    /// bulk bytes verbatim, and a virtual texture's tiles reassemble into a
    /// block image that decodes to the same pixels the tile path shows.
    #[test]
    fn dds_export_keeps_cooked_bytes_and_reassembles_virtual_textures() {
        let Ok(paks) = std::env::var("HCE_PAKS") else {
            return;
        };
        let c = Catalog::open(&paks, "").unwrap();
        let mut seen_classic = false;
        let mut seen_virtual = false;
        for index in 0..c.textures.len().min(400) {
            if seen_classic && seen_virtual {
                break;
            }
            let Ok(uasset) = c.read_texture_uasset(index) else {
                continue;
            };
            let Some(header) = textures::zen_header_size(&uasset) else {
                continue;
            };
            let Ok(tex) = textures::parse_texture(&uasset[header..]) else {
                continue;
            };
            let ubulk = c.read_texture_ubulk(index).unwrap_or_default();
            let Ok(dds) = textures::dds::write_dds(&tex, &ubulk) else {
                continue;
            };
            let body_at = if dds[84..88] == *b"DX10" { 148 } else { 128 };
            match &tex.payload {
                textures::Payload::Classic(mips) if !seen_classic => {
                    let m = &mips[0];
                    let first: &[u8] = match &m.source {
                        textures::MipSource::Inline { bytes, .. } => bytes,
                        textures::MipSource::Bulk { offset, len } => {
                            &ubulk[*offset as usize..(*offset + *len) as usize]
                        }
                    };
                    assert_eq!(&dds[body_at..body_at + first.len()], first);
                    assert_eq!(u32::from_le_bytes(dds[28..32].try_into().unwrap()), tex.num_mips);
                    eprintln!("classic: {} {}x{} {} mips", tex.format, tex.width, tex.height, tex.num_mips);
                    seen_classic = true;
                }
                textures::Payload::Virtual(_) if !seen_virtual => {
                    // Re-decode mip 0 from the linear block image the DDS holds
                    // and compare with the tile-by-tile decode.
                    let (w, h) = tex.mip_dims(0);
                    let (block_bytes, edge) = match tex.format.as_str() {
                        "PF_DXT1" | "PF_BC4" => (8u64, 4u64),
                        "PF_B8G8R8A8" => (4, 1),
                        "PF_G8" | "PF_A8" => (1, 1),
                        _ => (16, 4),
                    };
                    let len = ((w as u64).div_ceil(edge) * (h as u64).div_ceil(edge) * block_bytes) as usize;
                    let linear = dds[body_at..body_at + len].to_vec();
                    let flat = textures::Texture {
                        width: w,
                        height: h,
                        format: tex.format.clone(),
                        num_mips: 1,
                        payload: textures::Payload::Classic(vec![textures::Mip {
                            width: w,
                            height: h,
                            source: textures::MipSource::Inline { at: 0, bytes: linear },
                        }]),
                    };
                    let from_tiles = textures::assemble_mip(&tex, &ubulk, 0).unwrap();
                    let from_dds = textures::assemble_mip(&flat, &[], 0).unwrap();
                    assert_eq!(from_tiles.rgba, from_dds.rgba, "{} {}x{}", tex.format, w, h);
                    eprintln!("virtual: {} {}x{} {} mips", tex.format, w, h, tex.num_mips);
                    seen_virtual = true;
                }
                _ => {}
            }
        }
        assert!(seen_classic, "no classic texture among the first 400");
        assert!(seen_virtual, "no virtual texture among the first 400");
    }

    #[test]
    fn the_journal_is_bounded() {
        let key: TagKey = ("weapon".into(), "x".into());
        let mut w = Workbench::default();
        for i in 0..(HISTORY_LIMIT + 25) {
            w.remember(&key);
            w.edits.insert(key.clone(), vec![edit("a", &i.to_string())]);
        }
        assert_eq!(w.history_of(&key).undo, HISTORY_LIMIT);
    }

    /// The whole New Tag path against a real installation: clone a shipped
    /// tag under a new name, resolve it into an addition package, bake it, and
    /// read the container back the way the game's loader does.
    #[test]
    fn a_new_tag_bakes_into_a_container_that_reads_back() {
        let Ok(paks) = std::env::var("HCE_PAKS") else {
            return;
        };
        let mut c = Catalog::open(&paks, "").unwrap();
        let donor = c
            .tags_in("weapon", 1)
            .into_iter()
            .next()
            .expect("weapons ship");
        let from = donor.short.clone();
        let to = format!("{from}_mk2");
        let index = c.add_new_tag("weapon", &to, donor.index).unwrap();
        assert!(c.is_new_tag(index));
        assert_eq!(c.tag_index("weapon", &to), Some(index));
        assert_eq!(c.read_tag(index).unwrap(), c.read_tag(donor.index).unwrap());

        let mut new_tags = BTreeMap::new();
        new_tags.insert(
            ("weapon".to_string(), to.clone()),
            NewTagSpec {
                from: from.clone(),
                asset_reference: None,
            },
        );
        let (edits, scripts, textures) = (BTreeMap::new(), BTreeMap::new(), BTreeMap::new());
        let (overrides, additions, warnings) =
            resolved_edits(&c, &edits, &scripts, &textures, &new_tags).unwrap();
        assert!(overrides.is_empty());
        assert_eq!(additions.len(), 1);
        assert_eq!(
            additions[0].package.package_name,
            format!("/Game/Tags/{to}-weapon")
        );
        assert_eq!(additions[0].package.ubulk, c.read_tag(donor.index).unwrap());
        assert!(!additions[0].package.uasset.is_empty());
        assert!(
            warnings.iter().any(|w| w.contains("referenced by nothing")),
            "{warnings:?}"
        );

        let baked = modpack::bake(&c, "test-mod", overrides, additions).unwrap();
        assert_eq!(baked.len(), 1);
        assert_eq!(baked[0].basename, "test-mod-new_P");
        let dir = std::env::temp_dir().join(format!("mjolnir-newtag-{}", std::process::id()));
        modpack::write_and_verify(&dir, &baked, c.oodle_paths()).unwrap();
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// A shipped tag by group and the tail of its short path.
    fn shipped(c: &Catalog, group: &str, tail: &str) -> TagSummary {
        c.search(tail, 50)
            .into_iter()
            .find(|t| t.group == group && t.short.to_ascii_lowercase().ends_with(&tail.to_ascii_lowercase()))
            .unwrap_or_else(|| panic!("{tail}.{group} ships"))
    }

    /// One new tag for a staging run: group, donor tail, new leaf suffix and
    /// an optional Unreal binding.
    struct Clone<'a> {
        group: &'a str,
        donor_tail: &'a str,
        suffix: &'a str,
        asset_reference: Option<&'a str>,
    }

    /// Stage a mod the way `project_test` does — clones, field edits, bake,
    /// install — and print what was installed. The caller launches the game
    /// and reads its tag table (`mjolnir live tags --filter <suffix>`).
    fn stage(slug: &str, clones: &[Clone], edits: &[(&str, &str, &str, &str)]) {
        let paks = std::env::var("HCE_PAKS").expect("HCE_PAKS");
        let mut c = Catalog::open(&paks, "").unwrap();
        let mut new_tags = BTreeMap::new();
        for cl in clones {
            let donor = shipped(&c, cl.group, cl.donor_tail);
            let source = c
                .container(c.entry(donor.index).unwrap().container)
                .unwrap()
                .utoc_path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default();
            eprintln!("donor {}.{} lives in {source}", donor.short, donor.group);
            let to = format!("{}{}", donor.short, cl.suffix);
            c.add_new_tag(cl.group, &to, donor.index).unwrap();
            new_tags.insert(
                (cl.group.to_string(), to),
                NewTagSpec {
                    from: donor.short.clone(),
                    asset_reference: cl.asset_reference.map(str::to_string),
                },
            );
        }
        let mut pending: BTreeMap<TagKey, Vec<PendingEdit>> = BTreeMap::new();
        for (group, tail, field, value) in edits {
            let target = shipped(&c, group, tail);
            let source = c
                .container(c.entry(target.index).unwrap().container)
                .unwrap()
                .utoc_path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default();
            eprintln!("edit  {}.{} lives in {source}", target.short, target.group);
            pending
                .entry((group.to_string(), target.short.clone()))
                .or_default()
                .push(PendingEdit {
                    path: (*field).to_string(),
                    value: (*value).to_string(),
                });
        }
        let (scripts, textures) = (BTreeMap::new(), BTreeMap::new());
        let (overrides, additions, warnings) =
            resolved_edits(&c, &pending, &scripts, &textures, &new_tags).unwrap();
        assert_eq!(additions.len(), clones.len());
        assert!(
            !warnings.iter().any(|w| w.contains("referenced by nothing")),
            "every clone is referenced: {warnings:?}"
        );
        let baked = modpack::bake(&c, slug, overrides, additions).unwrap();
        for b in &baked {
            eprintln!(
                "container {}: {} chunk(s){}",
                b.basename,
                b.built.expect.len(),
                if b.built.resized() { ", resized" } else { "" }
            );
        }
        for f in modpack::install_test(c.paks(), &baked, c.oodle_paths()).unwrap() {
            eprintln!("installed {f}");
        }
        for w in warnings {
            eprintln!("warning: {w}");
        }
    }

    /// The in-game measurement of the editor's New Tag path: clone the
    /// assault rifle's projectile as `assault_rifle_bullet_mk3`, repoint the
    /// rifle at the clone, bake the override and the addition, install both.
    ///
    /// Then launch a mission with the rifle and run
    /// `mjolnir live tags --filter mk3`: the game's own tag table lists the
    /// clone if the editor's containers did their job. Remove the install
    /// afterwards from the mod panel or by deleting the `-MJOLNIRDEV-` files.
    #[test]
    #[ignore = "installs a test mod into the game's Paks folder"]
    fn stage_a_new_tag_for_the_in_game_test() {
        stage(
            "editor-newtag",
            &[Clone {
                group: "projectile",
                donor_tail: "projectiles/assault_rifle_bullet",
                suffix: "_mk3",
                asset_reference: None,
            }],
            &[(
                "weapon",
                "assault_rifle/assault_rifle",
                "barrels[0].projectile",
                "proj:objects\\weapons\\rifle\\assault_rifle\\projectiles\\assault_rifle_bullet_mk3",
            )],
        );
    }

    /// Matrix rows 4 and 5: a new object-group tag bound to a *different*
    /// Blueprint than its donor (the rifle's bullet on the magnum's projectile
    /// actor), and a new `model` carrying the donor's `RuntimeVariants`; the
    /// rifle is repointed at both. Two clones in two folders, so two addition
    /// containers.
    #[test]
    #[ignore = "installs a test mod into the game's Paks folder"]
    fn stage_matrix_rifle_rows() {
        stage(
            "matrix-rifle",
            &[
                Clone {
                    group: "projectile",
                    donor_tail: "projectiles/assault_rifle_bullet",
                    suffix: "_mk4",
                    asset_reference: Some(
                        "/Game/_Prototypes/SynchronizationTestContent/Assets/Weapons/ProjectileActors/BP_MagnumProjectileActor",
                    ),
                },
                Clone {
                    group: "model",
                    donor_tail: "assault_rifle/assault_rifle",
                    suffix: "_mk4",
                    asset_reference: None,
                },
            ],
            &[
                (
                    "weapon",
                    "assault_rifle/assault_rifle",
                    "barrels[0].projectile",
                    "proj:objects\\weapons\\rifle\\assault_rifle\\projectiles\\assault_rifle_bullet_mk4",
                ),
                (
                    "weapon",
                    "assault_rifle/assault_rifle",
                    "item.object.model",
                    "hlmt:objects\\weapons\\rifle\\assault_rifle\\assault_rifle_mk4",
                ),
            ],
        );
    }

    /// Matrix rows 6 and 7: an override of a tag that ships in a per-level
    /// container (the A30 scenario), pointing one structure's lighting info at
    /// a clone in a `_Generated_` group.
    #[test]
    #[ignore = "installs a test mod into the game's Paks folder"]
    fn stage_matrix_scenario_rows() {
        stage(
            "matrix-scenario",
            &[Clone {
                group: "scenario_structure_lighting_info",
                donor_tail: "A30/_Generated_/landing_zone_p1",
                suffix: "_mk4",
                asset_reference: None,
            }],
            &[(
                "scenario",
                "A30/_Generated_/a30",
                "structure bsps[7].structure lighting_info",
                "stli:levels\\halo1\\solo\\a30\\landing_zone_p1_mk4",
            )],
        );
    }
}
