//! Diagnose the a15 scenario read failure: print the effect-scenery struct
//! run from the tag's own layout, with the writes predicate per field.

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;

fn main() -> Result<(), String> {
    let query = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "A15/_Generated_/a15".to_string());

    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    let index = catalog
        .tags
        .iter()
        .position(|t| t.group == "scenario" && t.short.contains(&query))
        .ok_or("no tag matched")?;
    eprintln!("tag: {}", catalog.tags[index].short);

    let file = catalog.read_tag(index)?;
    let tag = blam_tag::TagFile::parse(&file, None).map_err(|e| e.to_string())?;
    eprintln!("group {} v{}", tag.header.group.as_str(), tag.header.group_version);
    let layout = tag.layout().map_err(|e| e.to_string())?;

    // Find the block whose name contains "effect_scenery" / "effect scenery".
    for (bi, b) in layout.blocks.iter().enumerate() {
        let name = layout.string_at(b.name_offset).unwrap_or("");
        if !name.contains("effect_scenery") {
            continue;
        }
        eprintln!("\nblock [{bi}] {name} max {} struct {}", b.max_count, b.aux);
        let Some(run) = layout.struct_run(b.aux as usize) else {
            continue;
        };
        let Some(range) = layout.struct_ranges().get(run).cloned() else {
            continue;
        };
        for i in range {
            let f = layout.fields[i];
            let ty = layout.type_name_of(&f);
            let nm = layout.string_at(f.name_offset).unwrap_or("");
            let writes = blam_tag::data::field_writes(&layout, &f);
            let size = layout.field_size(&f).unwrap_or(0);
            eprintln!(
                "  [{i:4}] {ty:<24} {nm:<28} aux {:<4} size {size:<3} writes {writes}",
                f.aux
            );
        }
    }

    // Raw field table around the effect-scenery struct, ignoring range
    // heuristics, to see where the struct really ends.
    eprintln!("\nmultiplayer-data struct run (87) full range:");
    if let Some(range) = layout.struct_ranges().get(87).cloned() {
        for i in range {
            let f = layout.fields[i];
            let ty = layout.type_name_of(&f);
            let nm = layout.string_at(f.name_offset).unwrap_or("");
            let writes = blam_tag::data::field_writes(&layout, &f);
            if writes || ty == "terminator X" || ty == "struct" || ty == "string id" {
                eprintln!("  [{i:4}] {ty:<24} {nm:<32} aux {:<4} writes {writes}", f.aux);
            }
        }
    }

    eprintln!("\nraw fields 716..742 (with raw type_index):");
    for i in 716..742 {
        let f = layout.fields[i];
        let ty = layout.type_name_of(&f);
        let nm = layout.string_at(f.name_offset).unwrap_or("");
        eprintln!(
            "  [{i:4}] type_index {:<3} {ty:<24} {nm:<32} aux {} name_off {}",
            f.type_index, f.aux, f.name_offset
        );
    }

    // Can the two struct fields' targets be resolved to runs?
    for aux in [60usize, 93] {
        let entry = layout.structs.get(aux);
        eprintln!(
            "struct table [{aux}]: run {:?}, entry {}",
            layout.struct_run(aux),
            entry
                .map(|s| format!("{:?}", s))
                .unwrap_or_else(|| "<missing>".into())
        );
    }

    // Traced walk: the tail of the trace shows exactly what was read before
    // the failure.
    let payload = tag.data().ok_or("no data section")?;
    let (res, diag) = blam_tag::data::read_block_traced(&layout, payload.content, 0);
    match res {
        Ok(b) => eprintln!("\nread OK, consumed {}", b.consumed),
        Err(e) => eprintln!("\nread error: {e}"),
    }
    eprintln!("\ntrace tail:");
    for line in diag.trace.iter().rev().take(25).rev() {
        eprintln!("  {line}");
    }
    Ok(())
}
