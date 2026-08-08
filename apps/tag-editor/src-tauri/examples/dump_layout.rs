//! Print the element struct layout (field, type, offset, size) of every block
//! whose path contains a filter string, plus a hex dump of its first element.
//! Offsets accumulate the way `view.rs` walks them, from the tag's own layout.
//!
//!   cargo run --example dump_layout -- collision_model elite bsp/
//!   cargo run --example dump_layout -- skeleton_model elite nodes

use blam_tag::data::{Block, Value};
use blam_tag::layout::Layout;
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;

fn crumb(name: &str, ty: &str) -> String {
    if name.is_empty() {
        format!("<{ty}>")
    } else {
        name.to_string()
    }
}

fn dump_struct(layout: &Layout<'_>, run: usize, block: &Block<'_>, path: &str) {
    println!(
        "\n== {path}  (count {}, element size {}) ==",
        block.count, block.element_size
    );
    let Some(range) = layout.struct_ranges().get(run).cloned() else {
        println!("  <no struct run>");
        return;
    };
    let mut offset = 0u32;
    for i in range {
        let f = layout.fields[i];
        let ty = layout.type_name_of(&f);
        let nm = layout.string_at(f.name_offset).unwrap_or("");
        let size = layout.field_size(&f).unwrap_or(0);
        println!("  @{offset:<4} +{size:<3} {ty:<24} {nm}");
        offset += size;
    }
    if let Some(el) = block.element(0) {
        print!("  element[0]:");
        for (i, b) in el.iter().enumerate() {
            if i % 16 == 0 {
                print!("\n    {i:04x}: ");
            }
            print!("{b:02x} ");
        }
        println!();
    }
}

fn walk_block(layout: &Layout<'_>, block: &Block<'_>, path: &str, filter: &str, seen: &mut std::collections::HashSet<String>) {
    if path.contains(filter) && seen.insert(path.to_string()) {
        if let Some(run) = layout.struct_run(block.struct_index) {
            dump_struct(layout, run, block, path);
        }
    }
    let Some(run) = layout.struct_run(block.struct_index) else {
        return;
    };
    for values in &block.children {
        walk_values(layout, run, values, path, filter, seen);
    }
}

fn walk_values(
    layout: &Layout<'_>,
    run: usize,
    values: &[Value<'_>],
    path: &str,
    filter: &str,
    seen: &mut std::collections::HashSet<String>,
) {
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
            Some(Value::Block(b)) => walk_block(layout, b, &sub, filter, seen),
            Some(Value::Struct { children }) => {
                if let Some(target) = layout.struct_run(field.aux as usize) {
                    walk_values(layout, target, children, &sub, filter, seen);
                }
            }
            Some(Value::Array { children }) => {
                if let Some(arr) = layout.arrays.get(field.aux as usize) {
                    if let Some(target) = layout.struct_run(arr.struct_index as usize) {
                        for child in children {
                            if let Value::Struct { children } = child {
                                walk_values(layout, target, children, &sub, filter, seen);
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }
}

fn main() -> Result<(), String> {
    let group = std::env::args().nth(1).ok_or("usage: dump_layout <group> <query> [filter]")?;
    let query = std::env::args().nth(2).unwrap_or_default();
    let filter = std::env::args().nth(3).unwrap_or_default();

    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    let index = catalog
        .tags
        .iter()
        .position(|t| t.group == group && t.short.contains(&query))
        .ok_or_else(|| format!("no {group} tag matching {query:?}"))?;
    println!("tag: {} ({})", catalog.tags[index].short, catalog.tags[index].group);

    let file = catalog.read_tag(index)?;
    let tag = blam_tag::TagFile::parse(&file, None).map_err(|e| e.to_string())?;
    let layout = tag.layout().map_err(|e| e.to_string())?;
    let payload = tag.data().ok_or("no data section")?;
    let block = blam_tag::data::read_block(&layout, payload.content, 0).map_err(|e| e.to_string())?;

    let mut seen = std::collections::HashSet::new();
    walk_block(&layout, &block, "", &filter, &mut seen);
    Ok(())
}
