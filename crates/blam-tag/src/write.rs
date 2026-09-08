//! Serialise a decoded value tree back into `bdat` payload bytes.
//!
//! This is the exact inverse of [`crate::data`]. Everything the reader consumed
//! is reproduced, including each section's header, so writing a tree that was
//! read and not modified yields the original bytes byte for byte. That identity
//! is checked against every shipped tag by `mjolnir roundtrip --all`.
//!
//! Section header words are **not** stored in the value tree, because they are
//! all reconstructable. Measured across the shipped corpus:
//!
//! | Magic  | Version word | Sections measured |
//! |--------|--------------|------------------:|
//! | `tgbl` | always `0`   | 66,002 |
//! | `tgst` | always equals its own content size | 66,604 |
//! | `tgsi` | always `0`   | 22,384 |
//! | `tgrf` | always `0`   | 23,950 |
//! | `tgda` | always `0`   | 125 |
//!
//! So `tgst`'s second word is not a version at all; it is a duplicate of the
//! size. A `pageable resource` section is rare enough that its version is
//! carried on the value instead of assumed.
//!
//! See `docs/tag_body_format.md`.

use std::collections::BTreeMap;

use crate::data::{Block, Value};
use crate::section::SECTION_HEADER;

/// Serialise one element's `tgst` wrapper content — its variable-length
/// children exactly as they were read. This is what cloning an element copies:
/// the donor's sections verbatim, novel bytes nowhere (see [`crate::blockedit`]).
pub(crate) fn element_wrapper(children: &[Value<'_>]) -> Vec<u8> {
    write_children(children, None)
}

/// Crate-visible section writer for code that assembles block content itself.
pub(crate) fn section_into(out: &mut Vec<u8>, magic: &str, version: u32, content: &[u8]) {
    section(out, magic, version, content);
}

/// Append a section header and its content. Magics are stored reversed, so
/// `tgbl` is written as the bytes `l b g t`.
fn section(out: &mut Vec<u8>, magic: &str, version: u32, content: &[u8]) {
    out.extend(magic.bytes().rev());
    out.extend_from_slice(&version.to_le_bytes());
    out.extend_from_slice(&(content.len() as u32).to_le_bytes());
    out.extend_from_slice(content);
}

/// A section header and its content as standalone bytes, for callers
/// assembling `tgbl` content by hand (element editing does).
pub fn raw_section(magic: &str, version: u32, content: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(SECTION_HEADER + content.len());
    section(&mut out, magic, version, content);
    out
}

/// One element's per-element `tgst` wrapper, re-serialised from its decoded
/// children. Identical to the bytes it was read from, by the round-trip
/// identity the writer is checked against.
pub fn wrapper_section(element: &[Value<'_>]) -> Vec<u8> {
    let content = write_children(element, None);
    raw_section("tgst", content.len() as u32, &content)
}

/// Serialise a block into the bytes of a `tgbl` section's content.
///
/// The root block's bytes are the whole `bdat` payload, so this is what a
/// round-trip compares against.
pub fn write_block(block: &Block<'_>) -> Vec<u8> {
    let mut out = Vec::with_capacity(block.consumed);
    write_block_into(&mut out, block, None);
    out
}

/// Replace one section's content while re-serialising.
///
/// The section is identified by where its current content sits in `file`, which
/// every value slice is borrowed from, so there is no ambiguity between two
/// fields that happen to hold the same bytes.
pub struct Substitution<'a> {
    pub file: &'a [u8],
    /// Byte offset in `file` of the content being replaced.
    pub at: usize,
    pub content: Vec<u8>,
}

impl Substitution<'_> {
    /// Does `slice` name the section this substitution replaces?
    fn matches(&self, slice: &[u8]) -> bool {
        (slice.as_ptr() as usize).saturating_sub(self.file.as_ptr() as usize) == self.at
    }
}

/// Serialise a block, swapping one section's content for new bytes.
///
/// This is how a resizing edit is made: the tree is written out again with the
/// new content in place, and every enclosing section's size falls out of the
/// serialisation rather than having to be patched up by hand. Writing with no
/// substitution reproduces the original bytes exactly, which is what makes the
/// change attributable to the edit alone.
pub fn write_block_subst(block: &Block<'_>, sub: &Substitution<'_>) -> Vec<u8> {
    let mut out = Vec::with_capacity(block.consumed);
    write_block_into(&mut out, block, Some(sub));
    out
}

/// Several replacements applied in one pass, of either kind.
///
/// A leaf substitution swaps the bytes of a `tgsi`, `tgda` or `tgrf`, which is
/// all a field edit ever needs. A block substitution swaps a whole `tgbl` — its
/// element count, its packed elements, and any per-element wrappers — which is
/// what an edit that changes how *many* elements there are requires. Rewriting
/// a scenario's script needs both at once: the string blob is a `tgda` and the
/// expression, script and global arrays are blocks that all resize together.
pub struct Edits<'a> {
    pub file: &'a [u8],
    /// Leaf section content, keyed by the offset of the bytes it replaces.
    pub sections: BTreeMap<usize, Vec<u8>>,
    /// Whole-block `tgbl` content, keyed by the offset of the block's packed
    /// elements. A block is named by its elements rather than by its header
    /// because that is the slice the reader borrows and hands back.
    pub blocks: BTreeMap<usize, Vec<u8>>,
    /// Bytes overwritten in place as packed element data is copied through,
    /// keyed by file offset.
    ///
    /// Packed elements are written verbatim, which is right until a block they
    /// point at changes size: a `block` field holds its element count inline and
    /// a `data` field holds its byte length, both duplicating what the section
    /// header says. Resizing a block without fixing its parent's copy leaves a
    /// scenario claiming a different number of scripts than it has.
    pub inline: BTreeMap<usize, Vec<u8>>,
}

impl<'a> Edits<'a> {
    pub fn new(file: &'a [u8]) -> Self {
        Edits {
            file,
            sections: BTreeMap::new(),
            blocks: BTreeMap::new(),
            inline: BTreeMap::new(),
        }
    }

    /// Copy packed element data through, applying any in-place fixes that fall
    /// inside it.
    fn write_elements(&self, out: &mut Vec<u8>, elements: &[u8]) {
        let start = self.offset_of(elements);
        let end = start + elements.len();
        let at = out.len();
        out.extend_from_slice(elements);
        if self.inline.is_empty() {
            return;
        }
        for (offset, bytes) in self.inline.range(start..end) {
            let local = at + (offset - start);
            let n = bytes.len().min(out.len().saturating_sub(local));
            out[local..local + n].copy_from_slice(&bytes[..n]);
        }
    }

    fn offset_of(&self, slice: &[u8]) -> usize {
        (slice.as_ptr() as usize).saturating_sub(self.file.as_ptr() as usize)
    }

    fn section_for(&self, slice: &[u8]) -> Option<&Vec<u8>> {
        self.sections.get(&self.offset_of(slice))
    }

    fn block_for(&self, block: &Block<'_>) -> Option<&Vec<u8>> {
        self.blocks.get(&self.offset_of(block.elements))
    }

    pub fn is_empty(&self) -> bool {
        self.sections.is_empty() && self.blocks.is_empty()
    }
}

/// Serialise a block, applying every edit in `edits`.
///
/// With no edits this reproduces the original bytes exactly, which is what
/// makes any difference attributable to the edits alone.
pub fn write_block_edits(block: &Block<'_>, edits: &Edits<'_>) -> Vec<u8> {
    let mut out = Vec::new();
    write_block_edited(&mut out, block, edits);
    out
}

fn write_block_edited(out: &mut Vec<u8>, block: &Block<'_>, edits: &Edits<'_>) {
    out.extend_from_slice(&block.count.to_le_bytes());
    out.extend_from_slice(&block.flags.to_le_bytes());
    edits.write_elements(out, block.elements);
    for element in &block.children {
        let content = write_children_edited(element, edits);
        section(out, "tgst", content.len() as u32, &content);
    }
}

fn write_children_edited(children: &[Value<'_>], edits: &Edits<'_>) -> Vec<u8> {
    let swap = |b: &[u8]| -> Vec<u8> {
        match edits.section_for(b) {
            Some(content) => content.clone(),
            None => b.to_vec(),
        }
    };

    let mut out = Vec::new();
    for value in children {
        match value {
            Value::Block(b) => {
                // A substituted block replaces its whole content, wrappers and
                // all, so its children are not walked.
                match edits.block_for(b) {
                    Some(content) => section(&mut out, "tgbl", 0, content),
                    None => {
                        let mut content = Vec::with_capacity(b.consumed);
                        write_block_edited(&mut content, b, edits);
                        section(&mut out, "tgbl", 0, &content);
                    }
                }
            }
            Value::Struct { children } => {
                let content = write_children_edited(children, edits);
                section(&mut out, "tgst", content.len() as u32, &content);
            }
            Value::StringId(b) => section(&mut out, "tgsi", 0, &swap(b)),
            Value::Data(b) => section(&mut out, "tgda", 0, &swap(b)),
            Value::TagRef(b) => section(&mut out, "tgrf", 0, &swap(b)),
            Value::Phantom => section(&mut out, "tgst", 0, &[]),
            Value::Array { children } => {
                for element in children {
                    match element {
                        Value::Struct { children } => {
                            out.extend_from_slice(&write_children_edited(children, edits))
                        }
                        other => out.extend_from_slice(&write_children_edited(
                            std::slice::from_ref(other),
                            edits,
                        )),
                    }
                }
            }
            Value::Resource {
                kind,
                version,
                body,
            } => {
                out.extend_from_slice(&[b'c', *kind, b'g', b't']);
                out.extend_from_slice(&version.to_le_bytes());
                out.extend_from_slice(&(body.len() as u32).to_le_bytes());
                out.extend_from_slice(body);
            }
        }
    }
    out
}

fn write_block_into(out: &mut Vec<u8>, block: &Block<'_>, sub: Option<&Substitution<'_>>) {
    out.extend_from_slice(&block.count.to_le_bytes());
    out.extend_from_slice(&block.flags.to_le_bytes());
    out.extend_from_slice(block.elements);
    // One `tgst` per element, present only when the reader found them; a block
    // whose element struct writes nothing has no children at all.
    for element in &block.children {
        let content = write_children(element, sub);
        section(out, "tgst", content.len() as u32, &content);
    }
}

/// Serialise one struct run's variable-length fields, in declaration order.
fn write_children(children: &[Value<'_>], sub: Option<&Substitution<'_>>) -> Vec<u8> {
    // A substitution replaces the content of exactly one section; everything
    // else is written back as it was read.
    let swap = |b: &[u8]| -> Vec<u8> {
        match sub {
            Some(s) if s.matches(b) => s.content.clone(),
            _ => b.to_vec(),
        }
    };

    let mut out = Vec::new();
    for value in children {
        match value {
            Value::Block(b) => {
                let mut content = Vec::with_capacity(b.consumed);
                write_block_into(&mut content, b, sub);
                section(&mut out, "tgbl", 0, &content);
            }
            Value::Struct { children } => {
                let content = write_children(children, sub);
                section(&mut out, "tgst", content.len() as u32, &content);
            }
            Value::StringId(b) => section(&mut out, "tgsi", 0, &swap(b)),
            Value::Data(b) => section(&mut out, "tgda", 0, &swap(b)),
            Value::TagRef(b) => section(&mut out, "tgrf", 0, &swap(b)),
            // A phantom is an empty `tgst` the layout does not declare; it is
            // written back exactly as it was read.
            Value::Phantom => section(&mut out, "tgst", 0, &[]),
            // An array writes no wrapper: its elements' sections follow inline.
            Value::Array { children } => {
                for element in children {
                    match element {
                        Value::Struct { children } => {
                            out.extend_from_slice(&write_children(children, sub))
                        }
                        other => out
                            .extend_from_slice(&write_children(std::slice::from_ref(other), sub)),
                    }
                }
            }
            Value::Resource {
                kind,
                version,
                body,
            } => {
                out.extend_from_slice(&[b'c', *kind, b'g', b't']);
                out.extend_from_slice(&version.to_le_bytes());
                out.extend_from_slice(&(body.len() as u32).to_le_bytes());
                out.extend_from_slice(body);
            }
        }
    }
    out
}

#[cfg(test)]
mod edit_tests {
    use super::*;

    /// A one-element block whose element is four bytes of packed data.
    fn block(file: &[u8]) -> Block<'_> {
        Block {
            struct_index: 0,
            count: 1,
            flags: 1,
            element_size: 4,
            elements: &file[8..12],
            children: Vec::new(),
            consumed: 12,
        }
    }

    #[test]
    fn no_edits_reproduces_the_original_bytes() {
        let file: Vec<u8> = (0..12u8).collect();
        let b = block(&file);
        assert_eq!(write_block_edits(&b, &Edits::new(&file)), write_block(&b));
    }

    #[test]
    fn an_inline_fix_lands_at_its_file_offset() {
        let file: Vec<u8> = (0..12u8).collect();
        let b = block(&file);
        let mut edits = Edits::new(&file);
        // Offset 9 is the second byte of the packed element.
        edits.inline.insert(9, vec![0xAA, 0xBB]);
        let out = write_block_edits(&b, &edits);
        // count | flags | elements
        assert_eq!(&out[8..12], &[8, 0xAA, 0xBB, 11]);
    }

    #[test]
    fn an_inline_fix_outside_the_elements_is_ignored() {
        let file: Vec<u8> = (0..12u8).collect();
        let b = block(&file);
        let mut edits = Edits::new(&file);
        edits.inline.insert(0, vec![0xFF]);
        assert_eq!(write_block_edits(&b, &edits), write_block(&b));
    }

    #[test]
    fn an_inline_fix_is_clipped_rather_than_overrunning() {
        let file: Vec<u8> = (0..12u8).collect();
        let b = block(&file);
        let mut edits = Edits::new(&file);
        // Three bytes written one byte before the end of the element.
        edits.inline.insert(11, vec![1, 2, 3]);
        let out = write_block_edits(&b, &edits);
        assert_eq!(out.len(), 12);
        assert_eq!(out[11], 1);
    }
}

/// Bytes a serialised block will occupy, without building it.
pub fn block_len(block: &Block<'_>) -> usize {
    8 + block.elements.len()
        + block
            .children
            .iter()
            .map(|e| SECTION_HEADER + children_len(e))
            .sum::<usize>()
}

fn children_len(children: &[Value<'_>]) -> usize {
    children
        .iter()
        .map(|v| match v {
            Value::Block(b) => SECTION_HEADER + block_len(b),
            Value::Struct { children } => SECTION_HEADER + children_len(children),
            Value::StringId(b) | Value::Data(b) | Value::TagRef(b) => SECTION_HEADER + b.len(),
            Value::Array { children } => children
                .iter()
                .map(|e| match e {
                    Value::Struct { children } => children_len(children),
                    other => children_len(std::slice::from_ref(other)),
                })
                .sum(),
            Value::Resource { body, .. } => SECTION_HEADER + body.len(),
            Value::Phantom => SECTION_HEADER,
        })
        .sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn writes_a_section_header_with_the_magic_reversed() {
        let mut out = Vec::new();
        section(&mut out, "tgbl", 0, &[1, 2, 3, 4]);
        assert_eq!(&out[0..4], b"lbgt");
        assert_eq!(&out[4..8], &0u32.to_le_bytes());
        assert_eq!(&out[8..12], &4u32.to_le_bytes());
        assert_eq!(&out[12..], &[1, 2, 3, 4]);
    }

    #[test]
    fn a_tgst_repeats_its_size_in_the_version_word() {
        let mut out = Vec::new();
        let content = [7u8; 24];
        section(&mut out, "tgst", content.len() as u32, &content);
        assert_eq!(&out[4..8], &24u32.to_le_bytes());
        assert_eq!(&out[8..12], &24u32.to_le_bytes());
    }

    #[test]
    fn an_empty_block_is_just_its_header() {
        let block = Block {
            struct_index: 0,
            count: 0,
            flags: 0,
            element_size: 4,
            elements: &[],
            children: Vec::new(),
            consumed: 8,
        };
        assert_eq!(write_block(&block), vec![0, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(block_len(&block), 8);
    }

    #[test]
    fn predicted_length_matches_what_is_written() {
        let inner = Block {
            struct_index: 1,
            count: 2,
            flags: 1,
            element_size: 3,
            elements: &[1, 2, 3, 4, 5, 6],
            children: Vec::new(),
            consumed: 14,
        };
        let block = Block {
            struct_index: 0,
            count: 1,
            flags: 0,
            element_size: 2,
            elements: &[9, 9],
            children: vec![vec![
                Value::Block(inner),
                Value::StringId(b"hi"),
                Value::Struct {
                    children: Vec::new(),
                },
            ]],
            consumed: 0,
        };
        assert_eq!(write_block(&block).len(), block_len(&block));
    }
}
