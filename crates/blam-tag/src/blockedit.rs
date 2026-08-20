//! Resize a root-level block: append elements cloned from a donor, or truncate.
//!
//! The scenario editor's placement blocks (`vehicles`, `weapons`, `scenery`,
//! `player starting locations`, ...) all hang directly off the group's root
//! struct, and growing or shrinking one is the resize the level bake needs.
//! New elements are **clones of an existing element**, later re-pointed field
//! by field through [`crate::patch::set`]: cloning reuses the donor's trailing
//! sections verbatim, so no novel `string id` is ever introduced — a novel id
//! is known to poison a tag for the native parser.
//!
//! Two places duplicate a block's element count and both are kept true: the
//! `tgbl` section's own count word, and the four inline bytes of the `block`
//! field inside the parent's packed element data. The latter is exactly the
//! in-place fix [`crate::write::Edits::inline`] exists for, and the whole
//! rebuild goes through [`crate::patch::rewrite`] so every enclosing size
//! follows from the writer.
//!
//! Applying no ops reproduces the file byte for byte (`mjolnir level selftest`
//! checks that against every shipped scenario), which is what makes any
//! difference attributable to the ops alone.

use crate::data::{Block, Value};
use crate::patch::Error;
use crate::write::Edits;

/// One resize operation, applied in order.
#[derive(Debug, Clone, Copy)]
pub enum Op {
    /// Append `copies` clones of the element at `donor` (an index into the
    /// block as it stands when this op runs).
    CloneAppend { donor: usize, copies: usize },
    /// Keep only the first `keep` elements.
    Truncate { keep: usize },
}

/// What a resize did, for reporting.
#[derive(Debug, Clone)]
pub struct Resized {
    pub block: String,
    pub before: u32,
    pub after: u32,
}

/// Offset of `part` within `whole` (both borrowed from the same buffer).
fn offset_within(whole: &[u8], part: &[u8]) -> usize {
    (part.as_ptr() as usize).saturating_sub(whole.as_ptr() as usize)
}

/// Find a root-struct field that is a block, returning the block value and the
/// file offset of the field's inline bytes (whose first four bytes duplicate
/// the element count).
fn find_root_block<'t, 'a>(
    layout: &crate::Layout<'_>,
    file: &[u8],
    root: &'t Block<'a>,
    name: &str,
) -> Result<(&'t Block<'a>, usize), Error> {
    let run = layout.struct_run(root.struct_index).ok_or(Error::NoData)?;
    let range = layout
        .struct_ranges()
        .get(run)
        .cloned()
        .ok_or(Error::NoData)?;
    let bytes = root.element(0).unwrap_or(&[]);
    let values: &[Value<'_>] = root.children.first().map(Vec::as_slice).unwrap_or(&[]);

    let mut offset = 0u32;
    let mut next_value = 0usize;
    for i in range {
        let field = layout.fields[i];
        let size = layout.field_size(&field).unwrap_or(0);
        let value = if crate::data::field_writes(layout, &field) {
            while matches!(values.get(next_value), Some(Value::Phantom)) {
                next_value += 1;
            }
            let v = values.get(next_value);
            next_value += 1;
            v
        } else {
            None
        };
        if layout.string_at(field.name_offset).unwrap_or("") == name {
            if layout.type_name_of(&field) != "block" {
                return Err(Error::NotIndexable {
                    at: name.to_string(),
                });
            }
            let Some(Value::Block(inner)) = value else {
                return Err(Error::NotIndexable {
                    at: name.to_string(),
                });
            };
            let slice = bytes
                .get(offset as usize..(offset + size) as usize)
                .unwrap_or(&[]);
            if slice.len() < 4 {
                return Err(Error::NotAValue {
                    at: name.to_string(),
                });
            }
            return Ok((inner, offset_within(file, slice)));
        }
        offset += size;
    }
    Err(Error::NoSuchField {
        segment: name.to_string(),
        at: "the root struct".to_string(),
    })
}

/// The element order a run of ops produces, as indices into the original block.
fn element_order(count: usize, ops: &[Op]) -> Result<Vec<usize>, Error> {
    let mut order: Vec<usize> = (0..count).collect();
    for op in ops {
        match *op {
            Op::CloneAppend { donor, copies } => {
                let &source = order.get(donor).ok_or(Error::IndexOutOfRange {
                    at: "clone donor".to_string(),
                    index: donor,
                    count: order.len() as u32,
                })?;
                for _ in 0..copies {
                    order.push(source);
                }
            }
            Op::Truncate { keep } => order.truncate(keep),
        }
    }
    Ok(order)
}

/// Rebuild one root block's `tgbl` content with its elements in `order`.
fn rebuilt_content(block: &Block<'_>, order: &[usize]) -> Result<Vec<u8>, Error> {
    let mut content = Vec::new();
    content.extend_from_slice(&(order.len() as u32).to_le_bytes());
    content.extend_from_slice(&block.flags.to_le_bytes());
    for &i in order {
        let element = block.element(i).ok_or(Error::IndexOutOfRange {
            at: "element".to_string(),
            index: i,
            count: block.count,
        })?;
        content.extend_from_slice(element);
    }
    // Flags word 0 means one `tgst` wrapper per element follows the packed
    // data; 1 means none (see `data::Block::flags`).
    if block.flags == 0 {
        for &i in order {
            let children = block.children.get(i).map(Vec::as_slice).unwrap_or(&[]);
            let wrapper = crate::write::element_wrapper(children);
            crate::write::section_into(&mut content, "tgst", wrapper.len() as u32, &wrapper);
        }
    }
    Ok(content)
}

/// Resize the named root-level block, returning the whole new tag file.
///
/// `file` is the complete tag, container header included, exactly as
/// [`crate::patch::set`] takes it.
pub fn resize(file: &[u8], block_name: &str, ops: &[Op]) -> Result<(Vec<u8>, Resized), Error> {
    let tag = crate::TagFile::parse(file, None).map_err(|_| Error::NoData)?;
    let layout = tag.layout().map_err(|_| Error::NoData)?;
    let root = tag.read_data(&layout).map_err(|_| Error::NoData)?;

    let (block, count_at) = find_root_block(&layout, file, &root, block_name)?;
    let order = element_order(block.count as usize, ops)?;
    let content = rebuilt_content(block, &order)?;

    let mut edits = Edits::new(file);
    edits
        .blocks
        .insert(offset_within(file, block.elements), content);
    edits
        .inline
        .insert(count_at, (order.len() as u32).to_le_bytes().to_vec());

    let out = crate::patch::rewrite(file, &edits)?;
    Ok((
        out,
        Resized {
            block: block_name.to_string(),
            before: block.count,
            after: order.len() as u32,
        },
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_order_appends_clones_of_the_donor() {
        let order = element_order(3, &[Op::CloneAppend { donor: 1, copies: 2 }]).unwrap();
        assert_eq!(order, vec![0, 1, 2, 1, 1]);
    }

    #[test]
    fn a_truncate_keeps_the_prefix() {
        let order = element_order(4, &[Op::Truncate { keep: 1 }]).unwrap();
        assert_eq!(order, vec![0]);
    }

    #[test]
    fn ops_compose_in_sequence() {
        let order = element_order(
            2,
            &[
                Op::Truncate { keep: 1 },
                Op::CloneAppend { donor: 0, copies: 2 },
            ],
        )
        .unwrap();
        assert_eq!(order, vec![0, 0, 0]);
    }

    #[test]
    fn a_bad_donor_is_an_error() {
        assert!(element_order(2, &[Op::CloneAppend { donor: 5, copies: 1 }]).is_err());
    }

    #[test]
    fn no_ops_is_the_identity_order() {
        assert_eq!(element_order(3, &[]).unwrap(), vec![0, 1, 2]);
    }
}
