//! Build a serializable definition corpus from the shipped tag layouts.
//!
//! Only schema is emitted: field names, type names, offsets, sizes, and option
//! names. Tag values are game content and are never written.

use blam_defs::{BlockRef, FieldDef, StructDef, TagGroupDef};
use blam_tag::Layout;

/// Convert one group's layout into a serializable definition.
pub fn build_group(
    name: &str,
    group: &str,
    version: u32,
    tag_count: usize,
    l: &Layout<'_>,
) -> TagGroupDef {
    let ranges = l.struct_ranges();
    let mut structs = Vec::with_capacity(ranges.len());

    // stv4 is ordered root first while the field runs are innermost first, so
    // emit in struct-table order to keep indices meaningful to consumers.
    for (struct_index, entry) in l.structs.iter().enumerate() {
        let Some(run) = l.struct_run(struct_index) else {
            continue;
        };
        let Some(range) = ranges.get(run) else {
            continue;
        };

        let mut offset = Some(0u32);
        let mut fields = Vec::new();
        for f in &l.fields[range.clone()] {
            let type_name = l.type_name_of(f).to_string();
            let size = l.field_size(f);

            let options = if l.has_options(f) {
                l.field_options(f).into_iter().map(String::from).collect()
            } else {
                Vec::new()
            };

            let block = if type_name == "block" {
                l.blocks.get(f.aux as usize).map(|b| BlockRef {
                    name: l.string_at(b.name_offset).unwrap_or("").to_string(),
                    max_count: b.max_count,
                })
            } else {
                None
            };

            let (struct_index_ref, array_count) = match type_name.as_str() {
                "struct" => (Some(f.aux as usize), None),
                "array" => l
                    .arrays
                    .get(f.aux as usize)
                    .map(|a| (Some(a.struct_index as usize), Some(a.count)))
                    .unwrap_or((None, None)),
                _ => (None, None),
            };

            fields.push(FieldDef {
                name: l.string_at(f.name_offset).unwrap_or("").to_string(),
                type_name,
                offset,
                size,
                options,
                block,
                struct_index: struct_index_ref,
                array_count,
            });

            // Once a size is unknown every later offset is unknown too.
            offset = match (offset, size) {
                (Some(o), Some(s)) => Some(o + s),
                _ => None,
            };
        }

        structs.push(StructDef {
            name: l.string_at(entry.name_offset).unwrap_or("").to_string(),
            guid: entry.guid.iter().map(|b| format!("{b:02x}")).collect(),
            size: l.struct_size(run),
            fields,
        });
    }

    TagGroupDef {
        group: group.to_string(),
        name: name.to_string(),
        version,
        tag_count,
        structs,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn offsets_stop_once_a_size_is_unknown() {
        // Exercised end to end by `mjolnir defs`; this guards the offset rule
        // in isolation.
        let mut offset = Some(0u32);
        let sizes = [Some(4u32), Some(12), None, Some(4)];
        let mut offsets = Vec::new();
        for s in sizes {
            offsets.push(offset);
            offset = match (offset, s) {
                (Some(o), Some(sz)) => Some(o + sz),
                _ => None,
            };
        }
        assert_eq!(offsets, vec![Some(0), Some(4), Some(16), None]);
    }
}
