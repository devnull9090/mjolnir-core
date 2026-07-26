//! MJOLNIR Tag Editor backend.
//!
//! Reads Blam tag definitions and values from the user's own installation of
//! Halo Campaign Evolved. This build is read-only: nothing is written back to
//! the game, and no tag content is written to disk.

use std::sync::Mutex;

use serde::Serialize;
use tauri::State;

mod catalog;
mod install;

use catalog::{Catalog, GroupSummary, TagSummary};

/// Cap on how many rows a single query returns, to keep IPC payloads bounded.
const MAX_ROWS: usize = 500;

#[derive(Default)]
struct AppState {
    catalog: Mutex<Option<Catalog>>,
}

#[derive(Serialize)]
struct OpenResult {
    groups: usize,
    tags: usize,
}

#[derive(Serialize)]
struct FieldView {
    name: String,
    #[serde(rename = "type")]
    type_name: String,
    offset: Option<u32>,
    size: Option<u32>,
    options: Vec<String>,
    block: Option<String>,
    max_count: Option<u32>,
}

#[derive(Serialize)]
struct StructView {
    name: String,
    size: Option<u32>,
    fields: Vec<FieldView>,
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
    structs: Vec<StructView>,
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

#[tauri::command]
fn read_tag(index: usize, state: State<'_, AppState>) -> Result<TagView, String> {
    with_catalog(&state, |c| {
        let entry = c.entry(index).ok_or("tag index out of range")?;
        let path = entry.path.clone();
        let group = entry.group.clone();
        let chunk_size = entry.chunk.length;

        c.with_tag(index, |tag, layout| {
            let ranges = layout.struct_ranges();
            let mut structs = Vec::new();

            for (struct_index, entry) in layout.structs.iter().enumerate() {
                let Some(run) = layout.struct_run(struct_index) else {
                    continue;
                };
                let Some(range) = ranges.get(run) else {
                    continue;
                };

                let mut offset = Some(0u32);
                let mut fields = Vec::new();
                for f in &layout.fields[range.clone()] {
                    let type_name = layout.type_name_of(f).to_string();
                    // Padding and terminators are structural, not user data.
                    let structural =
                        matches!(type_name.as_str(), "pad" | "terminator X" | "custom");
                    let size = layout.field_size(f);

                    if !structural {
                        let block = layout
                            .blocks
                            .get(f.aux as usize)
                            .filter(|_| type_name == "block");
                        fields.push(FieldView {
                            name: layout.string_at(f.name_offset).unwrap_or("").to_string(),
                            type_name: type_name.clone(),
                            offset,
                            size,
                            options: if layout.has_options(f) {
                                layout.field_options(f).into_iter().map(String::from).collect()
                            } else {
                                Vec::new()
                            },
                            block: block
                                .and_then(|b| layout.string_at(b.name_offset))
                                .map(String::from),
                            max_count: block.map(|b| b.max_count),
                        });
                    }

                    offset = match (offset, size) {
                        (Some(o), Some(s)) => Some(o + s),
                        _ => None,
                    };
                }

                structs.push(StructView {
                    name: layout.string_at(entry.name_offset).unwrap_or("").to_string(),
                    size: layout.struct_size(run),
                    fields,
                });
            }

            let data_size = tag.data().map(|d| d.size).unwrap_or(0);
            let data_exact = tag
                .read_data(layout)
                .map(|b| b.consumed == data_size as usize)
                .unwrap_or(false);

            TagView {
                path,
                group,
                four_cc: tag.header.group.as_str(),
                version: tag.header.group_version,
                chunk_size,
                data_size,
                data_exact,
                structs,
            }
        })
    })
}

/// Raw bytes of a tag's data payload, for the hex fallback view.
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
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
