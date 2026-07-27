//! Change one field of a tag, in place, touching nothing else.
//!
//! Editing a fixed-width field does not change any size, so it does not need
//! the tag rebuilt: the new value is written over the bytes the old one
//! occupied and every other byte of the file is left exactly as it was. That is
//! both the simplest implementation and the strongest guarantee — "only these
//! bytes changed" is checkable by comparing buffers, and does not depend on the
//! writer being perfect.
//!
//! A field is named by its path in the value tree, the same path the walk
//! reports in errors:
//!
//! ```text
//! bounding radius                  a root field
//! unit.object.bounding radius      through inlined structs
//! control points[3].position       into a block element
//! ```
//!
//! Fields whose payload lives in a trailing section — `string id`, `data`,
//! `tag reference` — are refused. Changing those resizes the tag, which is a
//! different operation and must not be smuggled through this path.

use crate::data::Block;
use crate::layout::{FieldEntry, Layout};
use crate::value::{self, Scalar};
use crate::HEADER_SIZE;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("no field named {segment:?} in {at}")]
    NoSuchField { segment: String, at: String },
    #[error("{at} is not a block or array, so it cannot be indexed")]
    NotIndexable { at: String },
    #[error("index {index} is out of range for {at}, which has {count} element(s)")]
    IndexOutOfRange {
        at: String,
        index: usize,
        count: u32,
    },
    #[error("{at} has no value bytes of its own")]
    NotAValue { at: String },
    #[error("the tag has no bdat data section")]
    NoData,
    #[error(transparent)]
    Write(#[from] value::WriteError),
    #[error(transparent)]
    Parse(#[from] value::ParseError),
}

/// Where a field's bytes live in the tag file, and what type they are.
#[derive(Debug, Clone)]
pub struct Target {
    pub field: FieldEntry,
    pub type_name: String,
    /// Byte offset of this field within the whole tag file.
    pub file_offset: usize,
    pub size: usize,
    /// The value currently stored there.
    pub current: Scalar,
}

/// Byte offset of `part` inside `whole`.
///
/// Every slice the reader produces is a subslice of the one buffer the tag was
/// parsed from, so the difference of their addresses is that offset. No
/// dereferencing, and it avoids threading a running offset through two modules
/// where a single missed update would silently point an edit at the wrong byte.
fn offset_within(whole: &[u8], part: &[u8]) -> usize {
    (part.as_ptr() as usize).saturating_sub(whole.as_ptr() as usize)
}

/// Split `a.b[2].c` into its segments, keeping any index with its name.
fn segments(path: &str) -> Vec<(String, Option<usize>)> {
    path.split('.')
        .filter(|s| !s.is_empty())
        .map(|s| match s.split_once('[') {
            Some((name, rest)) => (
                name.trim().to_string(),
                rest.trim_end_matches(']').trim().parse::<usize>().ok(),
            ),
            None => (s.trim().to_string(), None),
        })
        .collect()
}

/// Find the field a path names, and where its bytes are in `file`.
///
/// `file` is the whole tag, header included; `block` must have been read from
/// that same buffer.
pub fn resolve(
    layout: &Layout<'_>,
    file: &[u8],
    block: &Block<'_>,
    path: &str,
) -> Result<Target, Error> {
    let mut run = layout
        .struct_run(block.struct_index)
        .ok_or(Error::NoData)?;
    let mut bytes = block.element(0).unwrap_or(&[]);
    let mut values: &[crate::data::Value<'_>] =
        block.children.first().map(Vec::as_slice).unwrap_or(&[]);
    let mut walked = String::new();

    let parts = segments(path);
    for (depth, (name, index)) in parts.iter().enumerate() {
        let last = depth + 1 == parts.len();
        let at = if walked.is_empty() {
            "the root struct".to_string()
        } else {
            format!("{walked:?}")
        };

        // Find the named field in this run, tracking its offset and the value
        // that goes with it. The value order must follow `field_writes`, the
        // same predicate the reader used.
        let range = layout
            .struct_ranges()
            .get(run)
            .cloned()
            .ok_or(Error::NoData)?;
        let mut offset = 0u32;
        let mut next_value = 0usize;
        let mut found = None;

        for i in range {
            let field = layout.fields[i];
            let size = layout.field_size(&field).unwrap_or(0);
            let value = if crate::data::field_writes(layout, &field) {
                let v = values.get(next_value);
                next_value += 1;
                v
            } else {
                None
            };
            if layout.string_at(field.name_offset).unwrap_or("") == name {
                found = Some((field, offset, size, value));
                break;
            }
            offset += size;
        }

        let (field, offset, size, value) = found.ok_or_else(|| Error::NoSuchField {
            segment: name.clone(),
            at,
        })?;

        if walked.is_empty() {
            walked = name.clone();
        } else {
            walked = format!("{walked}.{name}");
        }
        let type_name = layout.type_name_of(&field).to_string();
        let slice = bytes
            .get(offset as usize..(offset + size) as usize)
            .unwrap_or(&[]);

        if last && index.is_none() {
            if slice.is_empty() {
                return Err(Error::NotAValue { at: walked });
            }
            return Ok(Target {
                field,
                current: value::read(layout, &field, slice),
                type_name,
                file_offset: offset_within(file, slice),
                size: size as usize,
            });
        }

        // Descend.
        match (type_name.as_str(), index) {
            ("struct", None) => {
                run = layout.struct_run(field.aux as usize).ok_or(Error::NoData)?;
                bytes = slice;
                values = match value {
                    Some(crate::data::Value::Struct { children }) => children.as_slice(),
                    _ => &[],
                };
            }
            ("block", Some(k)) => {
                let Some(crate::data::Value::Block(inner)) = value else {
                    return Err(Error::NotIndexable { at: walked });
                };
                if *k >= inner.count as usize {
                    return Err(Error::IndexOutOfRange {
                        at: walked,
                        index: *k,
                        count: inner.count,
                    });
                }
                run = layout
                    .struct_run(inner.struct_index)
                    .ok_or(Error::NoData)?;
                bytes = inner.element(*k).unwrap_or(&[]);
                values = inner.children.get(*k).map(Vec::as_slice).unwrap_or(&[]);
                walked = format!("{walked}[{k}]");
            }
            ("array", Some(k)) => {
                let entry = layout
                    .arrays
                    .get(field.aux as usize)
                    .copied()
                    .ok_or(Error::NoData)?;
                if *k >= entry.count as usize {
                    return Err(Error::IndexOutOfRange {
                        at: walked,
                        index: *k,
                        count: entry.count,
                    });
                }
                let element_size = size.checked_div(entry.count).unwrap_or(0) as usize;
                run = layout
                    .struct_run(entry.struct_index as usize)
                    .ok_or(Error::NoData)?;
                bytes = slice
                    .get(k * element_size..(k + 1) * element_size)
                    .unwrap_or(&[]);
                values = match value {
                    Some(crate::data::Value::Array { children }) => {
                        match children.get(*k) {
                            Some(crate::data::Value::Struct { children }) => children.as_slice(),
                            _ => &[],
                        }
                    }
                    _ => &[],
                };
                walked = format!("{walked}[{k}]");
            }
            _ => return Err(Error::NotIndexable { at: walked }),
        }
    }

    Err(Error::NoSuchField {
        segment: path.to_string(),
        at: "the tag".to_string(),
    })
}

/// What an edit did, so a caller can report and check it.
#[derive(Debug, Clone)]
pub struct Applied {
    pub path: String,
    pub type_name: String,
    pub before: Scalar,
    pub after: Scalar,
    /// The byte range of the file that changed. Empty when the new value
    /// encodes to the same bytes as the old.
    pub changed: std::ops::Range<usize>,
}

/// Write `value` into the field `path` names, returning the whole new tag file.
///
/// The input is copied and only the field's own bytes are overwritten, so the
/// result differs from the original in exactly one contiguous range — and never
/// in more bytes than the field is wide.
pub fn set(
    layout: &Layout<'_>,
    file: &[u8],
    block: &Block<'_>,
    path: &str,
    value: &Scalar,
) -> Result<(Vec<u8>, Applied), Error> {
    let target = resolve(layout, file, block, path)?;
    let mut out = file.to_vec();
    let end = target.file_offset + target.size;

    value::write(
        layout,
        &target.field,
        value,
        &mut out[target.file_offset..end],
    )?;

    // Report the range that actually differs, which is narrower than the field
    // whenever only part of it moved.
    let first = (target.file_offset..end).find(|i| out[*i] != file[*i]);
    let changed = match first {
        Some(start) => {
            let last = (start..end).rev().find(|i| out[*i] != file[*i]).unwrap_or(start);
            start..last + 1
        }
        None => 0..0,
    };

    Ok((
        out,
        Applied {
            path: path.to_string(),
            type_name: target.type_name,
            before: target.current,
            after: value.clone(),
            changed,
        },
    ))
}

/// Apply several edits at once, returning the new file and what each one did.
///
/// Every target is resolved against the *original* buffer before anything is
/// written. That is sound because an in-place edit never changes a size, so no
/// field moves; resolving as we went would be resolving against a buffer that
/// is already half-edited.
///
/// An edit that fails leaves the whole set unapplied.
pub fn set_many(
    layout: &Layout<'_>,
    file: &[u8],
    block: &Block<'_>,
    edits: &[(String, Scalar)],
) -> Result<(Vec<u8>, Vec<Applied>), Error> {
    let mut targets = Vec::with_capacity(edits.len());
    for (path, value) in edits {
        targets.push((resolve(layout, file, block, path)?, path, value));
    }

    let mut out = file.to_vec();
    let mut applied = Vec::with_capacity(edits.len());
    for (target, path, value) in targets {
        let end = target.file_offset + target.size;
        value::write(layout, &target.field, value, &mut out[target.file_offset..end])?;
        let first = (target.file_offset..end).find(|i| out[*i] != file[*i]);
        let changed = match first {
            Some(start) => {
                let last = (start..end).rev().find(|i| out[*i] != file[*i]).unwrap_or(start);
                start..last + 1
            }
            None => 0..0,
        };
        applied.push(Applied {
            path: path.clone(),
            type_name: target.type_name,
            before: target.current,
            after: value.clone(),
            changed,
        });
    }
    Ok((out, applied))
}

/// Where the `bdat` payload starts within a tag file, for reporting.
pub fn payload_offset(body_offset: usize) -> usize {
    HEADER_SIZE + body_offset
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_path_splits_into_names_and_indices() {
        assert_eq!(
            segments("unit.object.bounding radius"),
            vec![
                ("unit".to_string(), None),
                ("object".to_string(), None),
                ("bounding radius".to_string(), None)
            ]
        );
        assert_eq!(
            segments("control points[3].position"),
            vec![
                ("control points".to_string(), Some(3)),
                ("position".to_string(), None)
            ]
        );
    }

    #[test]
    fn a_field_name_may_contain_spaces() {
        assert_eq!(
            segments("rounds total maximum"),
            vec![("rounds total maximum".to_string(), None)]
        );
    }

    #[test]
    fn offsets_are_measured_against_the_parent_buffer() {
        let buf = vec![0u8; 64];
        assert_eq!(offset_within(&buf, &buf[16..32]), 16);
        assert_eq!(offset_within(&buf, &buf[..0]), 0);
    }

    /// The synthetic tag from `data`: a root with `meta` (a struct holding one
    /// `long integer n`), a `tags` array, and a `res` pageable resource.
    fn synth() -> (Vec<u8>, Vec<u8>) {
        (
            crate::data::tests::synth_layout(),
            crate::data::tests::synth_payload(),
        )
    }

    #[test]
    fn a_path_resolves_to_the_bytes_the_field_occupies() {
        let (body, payload) = synth();
        let layout = Layout::parse(&body).unwrap();
        let block = crate::data::read_block(&layout, &payload, 0).unwrap();

        let t = resolve(&layout, &payload, &block, "meta.n").unwrap();
        assert_eq!(t.type_name, "long integer");
        assert_eq!(t.size, 4);
        // The root element's packed data starts after the block's 8-byte
        // header, and `meta` is the first field.
        assert_eq!(t.file_offset, 8);
        assert_eq!(t.current, Scalar::Int(0));
    }

    #[test]
    fn setting_a_field_changes_only_that_field() {
        let (body, payload) = synth();
        let layout = Layout::parse(&body).unwrap();
        let block = crate::data::read_block(&layout, &payload, 0).unwrap();

        let (out, applied) =
            set(&layout, &payload, &block, "meta.n", &Scalar::Int(0x0A0B0C0D)).unwrap();

        assert_eq!(out.len(), payload.len(), "an in-place edit cannot resize");
        assert_eq!(applied.before, Scalar::Int(0));
        assert_eq!(applied.changed, 8..12);

        // Every byte outside the field is untouched.
        for (i, (a, b)) in payload.iter().zip(&out).enumerate() {
            if !(8..12).contains(&i) {
                assert_eq!(a, b, "byte {i} changed outside the field");
            }
        }

        // And the patched bytes read back as the new value.
        let block = crate::data::read_block(&layout, &out, 0)
            .unwrap_or_else(|e| panic!("patched payload no longer walks: {e}"));
        let t = resolve(&layout, &out, &block, "meta.n").unwrap();
        assert_eq!(t.current, Scalar::Int(0x0A0B0C0D));
    }

    #[test]
    fn writing_the_value_already_there_changes_nothing() {
        let (body, payload) = synth();
        let layout = Layout::parse(&body).unwrap();
        let block = crate::data::read_block(&layout, &payload, 0).unwrap();

        let (out, applied) = set(&layout, &payload, &block, "meta.n", &Scalar::Int(0)).unwrap();
        assert_eq!(applied.changed, 0..0);
        assert_eq!(out, payload);
    }

    #[test]
    fn an_unknown_field_is_named_in_the_error() {
        let (body, payload) = synth();
        let layout = Layout::parse(&body).unwrap();
        let block = crate::data::read_block(&layout, &payload, 0).unwrap();

        let err = resolve(&layout, &payload, &block, "meta.nope").unwrap_err();
        assert!(
            matches!(&err, Error::NoSuchField { segment, .. } if segment == "nope"),
            "{err}"
        );
    }

    #[test]
    fn a_section_backed_field_cannot_be_set_in_place() {
        let (body, payload) = synth();
        let layout = Layout::parse(&body).unwrap();
        let block = crate::data::read_block(&layout, &payload, 0).unwrap();

        // `res` is a pageable resource: its payload is a section, not bytes in
        // the element.
        let err = set(
            &layout,
            &payload,
            &block,
            "res",
            &Scalar::Text("x".into()),
        )
        .unwrap_err();
        assert!(matches!(err, Error::Write(_)), "{err}");
    }
}
