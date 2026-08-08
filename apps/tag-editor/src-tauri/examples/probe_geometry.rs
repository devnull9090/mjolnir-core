//! Answer one question: do shipped tags carry real geometry payloads?
//!
//! Walks a whole tag's value tree (no element cap), aggregates every block by
//! path with its total packed-element bytes, and lists every pageable-resource
//! body with its size. Run with a search string, e.g.:
//!
//!   cargo run --example probe_geometry -- sbsp holdouts
//!   cargo run --example probe_geometry -- collision_model elite

use std::collections::BTreeMap;

use blam_tag::data::{Block, Value};
use blam_tag::layout::Layout;
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;

#[derive(Default)]
struct Agg {
    blocks: BTreeMap<String, (u64, u64)>, // path -> (total elements, total packed bytes)
    resources: Vec<(String, u8, u32, usize)>, // path, kind, version, body len
    data_fields: BTreeMap<String, u64>,   // path -> total tag_data bytes
}

fn crumb(name: &str, ty: &str) -> String {
    if name.is_empty() {
        format!("<{ty}>")
    } else {
        name.to_string()
    }
}

fn walk_block(layout: &Layout<'_>, block: &Block<'_>, path: &str, agg: &mut Agg) {
    let entry = agg.blocks.entry(path.to_string()).or_default();
    entry.0 += block.count as u64;
    entry.1 += block.elements.len() as u64;

    let Some(run) = layout.struct_run(block.struct_index) else {
        return;
    };
    for values in &block.children {
        walk_values(layout, run, values, path, agg);
    }
}

fn walk_values(layout: &Layout<'_>, run: usize, values: &[Value<'_>], path: &str, agg: &mut Agg) {
    let Some(range) = layout.struct_ranges().get(run).cloned() else {
        return;
    };
    let mut next = 0usize;
    for i in range {
        let field = layout.fields[i];
        if !blam_tag::data::field_writes(layout, &field) {
            continue;
        }
        while matches!(values.get(next), Some(Value::Phantom)) {
            next += 1;
        }
        let value = values.get(next);
        next += 1;
        let ty = layout.type_name_of(&field);
        let name = crumb(layout.string_at(field.name_offset).unwrap_or(""), ty);
        let sub = format!("{path}/{name}");
        match value {
            Some(Value::Block(b)) => walk_block(layout, b, &sub, agg),
            Some(Value::Struct { children }) => {
                if let Some(target) = layout.struct_run(field.aux as usize) {
                    walk_values(layout, target, children, &sub, agg);
                }
            }
            Some(Value::Array { children }) => {
                if let Some(arr) = layout.arrays.get(field.aux as usize) {
                    if let Some(target) = layout.struct_run(arr.struct_index as usize) {
                        for child in children {
                            if let Value::Struct { children } = child {
                                walk_values(layout, target, children, &sub, agg);
                            }
                        }
                    }
                }
            }
            Some(Value::Resource {
                kind,
                version,
                body,
            }) => {
                agg.resources.push((sub.clone(), *kind, *version, body.len()));
                probe_resource_interior(layout, body, &sub, agg);
            }
            Some(Value::Data(d)) => {
                *agg.data_fields.entry(sub).or_default() += d.len() as u64;
            }
            _ => {}
        }
    }
}

/// A resource body may itself be a serialized value stream; just record its
/// first bytes so we can eyeball what lives inside.
fn probe_resource_interior(_layout: &Layout<'_>, body: &[u8], path: &str, _agg: &mut Agg) {
    if body.len() >= 16 {
        let head: Vec<String> = body[..16].iter().map(|b| format!("{b:02x}")).collect();
        eprintln!("  resource {path}: head {}", head.join(" "));
    }
}

fn human(n: u64) -> String {
    if n >= 1 << 20 {
        format!("{:.1} MiB", n as f64 / (1 << 20) as f64)
    } else if n >= 1 << 10 {
        format!("{:.1} KiB", n as f64 / (1 << 10) as f64)
    } else {
        format!("{n} B")
    }
}

fn main() -> Result<(), String> {
    let group = std::env::args().nth(1).unwrap_or_else(|| "scenario_structure_bsp".into());
    let query = std::env::args().nth(2).unwrap_or_else(|| "holdouts".into());

    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    let index = catalog
        .tags
        .iter()
        .position(|t| t.group == group && t.short.contains(&query))
        .ok_or_else(|| format!("no {group} tag matching {query:?}"))?;
    eprintln!("tag: {} ({})", catalog.tags[index].short, catalog.tags[index].group);

    let file = catalog.read_tag(index)?;
    eprintln!("tag file size: {}", human(file.len() as u64));

    let tag = blam_tag::TagFile::parse(&file, None).map_err(|e| e.to_string())?;
    let layout = tag.layout().map_err(|e| e.to_string())?;
    let payload = tag.data().ok_or("no data section")?;
    let block = blam_tag::data::read_block(&layout, payload.content, 0).map_err(|e| e.to_string())?;

    let mut agg = Agg::default();
    walk_block(&layout, &block, "", &mut agg);

    eprintln!("\n== blocks by packed bytes (top 40) ==");
    let mut rows: Vec<_> = agg.blocks.iter().collect();
    rows.sort_by_key(|(_, (_, bytes))| std::cmp::Reverse(*bytes));
    for (path, (count, bytes)) in rows.iter().take(40) {
        eprintln!("  {:>12}  x{:<9} {}", human(*bytes), count, path);
    }

    eprintln!("\n== tag_data fields ==");
    let mut rows: Vec<_> = agg.data_fields.iter().collect();
    rows.sort_by_key(|(_, bytes)| std::cmp::Reverse(**bytes));
    for (path, bytes) in rows.iter().take(20) {
        eprintln!("  {:>12}  {}", human(**bytes), path);
    }

    eprintln!("\n== pageable resources ==");
    for (path, kind, version, len) in &agg.resources {
        eprintln!(
            "  kind '{}' v{} body {:>12}  {}",
            (*kind as char),
            version,
            human(*len as u64),
            path
        );
    }
    if agg.resources.is_empty() {
        eprintln!("  (none)");
    }
    Ok(())
}
