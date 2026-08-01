//! MJOLNIR Tag Editor backend.
//!
//! Reads Blam tag definitions and values from the user's own installation of
//! Halo Campaign Evolved. This build is read-only: nothing is written back to
//! the game, and no tag content is written to disk.

use std::collections::BTreeMap;
use std::sync::Mutex;

use serde::Serialize;
use tauri::State;

pub mod catalog;
pub mod install;
pub mod textures;
pub mod zen;

use catalog::{Catalog, GroupSummary, TagSummary};

/// Cap on how many rows a single query returns, to keep IPC payloads bounded.
const MAX_ROWS: usize = 500;

#[derive(Default)]
struct AppState {
    catalog: Mutex<Option<Catalog>>,
    /// Edits the user has made but not exported, per tag index.
    ///
    /// Held in memory on purpose. The game loads tags from read-only IoStore
    /// containers, so there is nowhere to save them back to; an edit is a
    /// pending change until it is exported to a file.
    edits: Mutex<BTreeMap<usize, Vec<PendingEdit>>>,
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
    let catalog = Catalog::open(&paks, &oodle)?;
    let groups = catalog.groups()?.len();
    let tags = catalog.tags.len();
    *state.catalog.lock().map_err(|e| e.to_string())? = Some(catalog);
    Ok(OpenResult { groups, tags })
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
fn patched_bytes(
    c: &Catalog,
    index: usize,
    pending: &[PendingEdit],
) -> Result<Vec<u8>, String> {
    let file = c.read_tag(index)?;
    if pending.is_empty() {
        return Ok(file);
    }
    let entry = c.entry(index).ok_or("tag index out of range")?;
    let tag = blam_tag::TagFile::parse(&file, Some(entry.chunk.length as usize))
        .map_err(|e| e.to_string())?;
    let layout = tag.layout().map_err(|e| e.to_string())?;
    let block = tag.read_data(&layout).map_err(|e| e.to_string())?;
    let edits = parse_edits(&layout, &file, &block, pending);
    let (out, _) = blam_tag::patch::set_many(&layout, &file, &block, &edits)
        .map_err(|e| e.to_string())?;
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

#[tauri::command]
fn set_field(
    index: usize,
    path: String,
    value: String,
    state: State<'_, AppState>,
) -> Result<EditResult, String> {
    let pending = {
        let all = state.edits.lock().map_err(|e| e.to_string())?;
        all.get(&index).cloned().unwrap_or_default()
    };

    let result = with_catalog(&state, |c| {
        let file = patched_bytes(c, index, &pending)?;
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let tag = blam_tag::TagFile::parse(&file, Some(entry.chunk.length as usize))
            .map_err(|e| e.to_string())?;
        let layout = tag.layout().map_err(|e| e.to_string())?;
        let block = tag.read_data(&layout).map_err(|e| e.to_string())?;

        let target = blam_tag::patch::resolve(&layout, &file, &block, &path)
            .map_err(|e| e.to_string())?;
        // A section-backed value resizes the tag, so it takes the rebuild path
        // rather than overwriting bytes.
        let resizes = target.section.is_some();
        let parsed = match target.type_name.as_str() {
            "string id" => blam_tag::Scalar::Text(value.trim_matches('"').to_string()),
            "tag reference" => parse_reference(&value)?,
            _ => blam_tag::value::parse(&layout, &target.field, &value)
                .map_err(|e| e.to_string())?,
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
    let mut all = state.edits.lock().map_err(|e| e.to_string())?;
    let list = all.entry(index).or_default();
    list.retain(|e| e.path != path);
    list.push(PendingEdit { path, value });
    Ok(result)
}

#[tauri::command]
fn revert_field(index: usize, path: String, state: State<'_, AppState>) -> Result<usize, String> {
    let mut all = state.edits.lock().map_err(|e| e.to_string())?;
    let list = all.entry(index).or_default();
    list.retain(|e| e.path != path);
    let left = list.len();
    if left == 0 {
        all.remove(&index);
    }
    Ok(left)
}

#[tauri::command]
fn revert_tag(index: usize, state: State<'_, AppState>) -> Result<(), String> {
    state.edits.lock().map_err(|e| e.to_string())?.remove(&index);
    Ok(())
}

/// Write the tag, with its pending edits applied, to a file the user chose.
///
/// This is how an edit leaves the editor: the game's containers are read-only,
/// so there is nowhere to save in place. The bytes are game content and stay
/// wherever the user puts them.
#[tauri::command]
fn export_tag(index: usize, dest: String, state: State<'_, AppState>) -> Result<usize, String> {
    let pending = {
        let all = state.edits.lock().map_err(|e| e.to_string())?;
        all.get(&index).cloned().unwrap_or_default()
    };
    with_catalog(&state, |c| {
        let out = patched_bytes(c, index, &pending)?;
        std::fs::write(&dest, &out).map_err(|e| format!("{dest}: {e}"))?;
        Ok(out.len())
    })
}

#[tauri::command]
fn read_tag(index: usize, state: State<'_, AppState>) -> Result<TagView, String> {
    let pending = {
        let all = state.edits.lock().map_err(|e| e.to_string())?;
        all.get(&index).cloned().unwrap_or_default()
    };
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
fn list_textures(
    query: String,
    state: State<'_, AppState>,
) -> Result<Vec<TextureSummary>, String> {
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
) -> Result<(textures::VtData, textures::TextureImage), String> {
    let uasset = c.read_texture_uasset(index)?;
    let header = textures::zen_header_size(&uasset).ok_or("not a zen package")?;
    let vt = textures::parse_vt(&uasset[header..])?;
    let ubulk = c.read_texture_ubulk(index)?;
    let mut mip = 0;
    while mip + 1 < vt.num_mips && (vt.width >> mip).max(vt.height >> mip) > max_dim {
        mip += 1;
    }
    let img = textures::assemble_mip(&vt, &ubulk, mip)?;
    Ok((vt, img))
}

#[tauri::command]
fn read_texture(index: usize, state: State<'_, AppState>) -> Result<TextureView, String> {
    use base64::Engine;
    with_catalog(&state, |c| {
        let entry = c.textures.get(index).ok_or("texture index out of range")?;
        let path = entry.short.clone();
        let (vt, img) = decode_texture(c, index, 4096)?;
        let png = textures::to_png(&img)?;
        Ok(TextureView {
            path,
            width: vt.width,
            height: vt.height,
            format: img.format.clone(),
            mip: img.mip,
            num_mips: vt.num_mips,
            png: format!(
                "data:image/png;base64,{}",
                base64::engine::general_purpose::STANDARD.encode(png)
            ),
        })
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
        .invoke_handler(tauri::generate_handler![
            detect_install,
            open_install,
            list_groups,
            list_tags,
            search_tags,
            read_tag,
            read_tag_bytes,
            set_field,
            revert_field,
            revert_tag,
            export_tag,
            list_textures,
            read_texture,
            export_texture,
            tag_links,
            list_dir,
            search_files,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
