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

use crate::data::{Block, Value};
use crate::section::SECTION_HEADER;

/// Append a section header and its content. Magics are stored reversed, so
/// `tgbl` is written as the bytes `l b g t`.
fn section(out: &mut Vec<u8>, magic: &str, version: u32, content: &[u8]) {
    out.extend(magic.bytes().rev());
    out.extend_from_slice(&version.to_le_bytes());
    out.extend_from_slice(&(content.len() as u32).to_le_bytes());
    out.extend_from_slice(content);
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
