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
//! A field whose payload lives in a trailing section — a `string id` or
//! `tag reference` — cannot be changed this way, because the new value is a
//! different length. Those go through [`set_text`], which serialises the data
//! section again so every enclosing size follows from the writer rather than
//! being patched up by hand.

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
    #[error("{at} is not a block, so it has no elements to add or remove")]
    NotABlock { at: String },
    #[error("{at} already has {count} element(s), the most this block allows")]
    BlockFull { at: String, count: u32 },
    #[error("{at}: its elements hold a {type_name}, which this editor cannot create")]
    NoDefault { at: String, type_name: String },
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
    /// For a section-backed field, where its section's content sits in the file
    /// and how long it is. `None` for a plain inline field.
    pub section: Option<(usize, usize)>,
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
    // A `\.` is a literal dot inside a field name — the Havok mopp header's
    // fields are named `v.i`..`v.w` — so the split walks characters rather
    // than using str::split.
    let mut parts: Vec<String> = Vec::new();
    let mut current = String::new();
    let mut chars = path.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '\\' if chars.peek() == Some(&'.') => {
                current.push('.');
                chars.next();
            }
            '.' => {
                parts.push(std::mem::take(&mut current));
            }
            _ => current.push(c),
        }
    }
    parts.push(current);

    parts
        .iter()
        .filter(|s| !s.trim().is_empty())
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
    locate(layout, file, block, path).map(|(target, _, _)| target)
}

/// One block boundary a path crosses on its way to a field.
///
/// In the file this is nothing — an element's bytes are at a fixed offset
/// like any other — but a runtime that moves block elements out of the tag
/// needs to know where each boundary was crossed: which block field, which
/// element, and where that element's bytes began. See `blam_live`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Hop {
    /// File offset of the block field in the parent element — the twelve
    /// bytes the file holds for it.
    pub header: usize,
    /// The element the path enters.
    pub index: usize,
    /// File offset of that element's packed bytes.
    pub element: usize,
    /// Packed size of one element.
    pub element_size: usize,
}

/// Where a field sits, with the block boundaries crossed to reach it.
#[derive(Debug, Clone)]
pub struct Route {
    pub target: Target,
    /// Outermost first. Empty for a field of the root element, including one
    /// inside an inlined struct or a fixed array.
    pub hops: Vec<Hop>,
}

/// [`resolve`], keeping the block boundaries crossed along the way.
pub fn route(
    layout: &Layout<'_>,
    file: &[u8],
    block: &Block<'_>,
    path: &str,
) -> Result<Route, Error> {
    locate(layout, file, block, path).map(|(target, _, hops)| Route { target, hops })
}

/// [`resolve`], also returning the decoded value paired with the field, when
/// the field writes one, and the block boundaries crossed. The value is what
/// element editing needs: the `Value::Block` behind a `block` field carries
/// the packed elements and per-element wrappers that a count change has to
/// rebuild.
fn locate<'v, 'a>(
    layout: &Layout<'_>,
    file: &[u8],
    block: &'v Block<'a>,
    path: &str,
) -> Result<(Target, Option<&'v crate::data::Value<'a>>, Vec<Hop>), Error> {
    let mut run = layout
        .struct_run(block.struct_index)
        .ok_or(Error::NoData)?;
    let mut bytes = block.element(0).unwrap_or(&[]);
    let mut values: &'v [crate::data::Value<'a>] =
        block.children.first().map(Vec::as_slice).unwrap_or(&[]);
    let mut walked = String::new();
    let mut hops: Vec<Hop> = Vec::new();

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
                // A phantom pairs with no field; step over it.
                while matches!(values.get(next_value), Some(crate::data::Value::Phantom)) {
                    next_value += 1;
                }
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
            // A section-backed field shows the section's value, not the
            // inline handle, and an edit has to reach the section.
            let section = value.and_then(|v| match v {
                crate::data::Value::StringId(b)
                | crate::data::Value::TagRef(b)
                | crate::data::Value::Data(b) => Some((offset_within(file, b), b.len())),
                _ => None,
            });
            let current = match value {
                Some(crate::data::Value::StringId(b)) => {
                    let end = b.iter().position(|c| *c == 0).unwrap_or(b.len());
                    Scalar::Text(String::from_utf8_lossy(&b[..end]).into_owned())
                }
                Some(crate::data::Value::TagRef(b)) => value::reference(b),
                _ => value::read(layout, &field, slice),
            };
            return Ok((
                Target {
                    field,
                    current,
                    type_name,
                    file_offset: offset_within(file, slice),
                    size: size as usize,
                    section,
                },
                value,
                hops,
            ));
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
                hops.push(Hop {
                    header: offset_within(file, slice),
                    index: *k,
                    element: offset_within(file, bytes),
                    element_size: inner.element_size as usize,
                });
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

/// Encode a section-backed value into the bytes its section should hold, and
/// the inline handle that must agree with it.
///
/// These two must be changed together. A `tag reference` keeps its group and
/// path in a `tgrf`, but its 16 inline bytes are
/// `{group four-CC, 0, path length, handle}` — the length is stored twice, and
/// leaving the inline copy stale would produce a tag that reads back wrong.
fn section_bytes(type_name: &str, value: &Scalar) -> Result<(Vec<u8>, Option<Vec<u8>>), Error> {
    match (type_name, value) {
        ("string id", Scalar::Text(s)) => {
            // The section holds the text with no terminator. The inline word is
            // *not* a length — it is zero on disk even for a populated string,
            // so it is left alone rather than "corrected".
            Ok((s.as_bytes().to_vec(), None))
        }
        ("tag reference", Scalar::Reference { group, path }) => {
            let mut content = Vec::new();
            let mut inline = Vec::new();
            if path.is_empty() {
                // An unset reference has no section content and a cleared
                // group, as the shipped data writes it.
                inline.extend_from_slice(&0xFFFF_FFFFu32.to_le_bytes());
                inline.extend_from_slice(&0u32.to_le_bytes());
                inline.extend_from_slice(&0u32.to_le_bytes());
                inline.extend_from_slice(&0xFFFF_FFFFu32.to_le_bytes());
                return Ok((content, Some(inline)));
            }
            if group.len() != 4 || !group.is_ascii() {
                return Err(Error::Write(value::WriteError::OutOfRange {
                    type_name: type_name.to_string(),
                    value: format!("group {group:?}"),
                }));
            }
            let cc: Vec<u8> = group.bytes().rev().collect();
            content.extend_from_slice(&cc);
            content.extend_from_slice(path.as_bytes());

            inline.extend_from_slice(&cc);
            inline.extend_from_slice(&0u32.to_le_bytes());
            inline.extend_from_slice(&(path.len() as u32).to_le_bytes());
            inline.extend_from_slice(&0xFFFF_FFFFu32.to_le_bytes());
            Ok((content, Some(inline)))
        }
        _ => Err(Error::Write(value::WriteError::NotEditable {
            type_name: type_name.to_string(),
        })),
    }
}

/// Change a field whose value lives in a trailing section, resizing the tag.
///
/// Unlike [`set`], this cannot be done by overwriting bytes: the new content is
/// a different length, so every enclosing section's size changes with it.
/// Rather than patch those up by hand, the payload is serialised again with the
/// new content in place, so the sizes come out of the same writer that is
/// checked byte-for-byte against every shipped tag.
///
/// Returns the new file and what changed.
pub fn set_text(
    layout: &Layout<'_>,
    file: &[u8],
    block: &Block<'_>,
    path: &str,
    value: &Scalar,
) -> Result<(Vec<u8>, Applied), Error> {
    let target = resolve(layout, file, block, path)?;
    let (content, inline) = section_bytes(&target.type_name, value)?;

    let Some((section_at, _)) = target.section else {
        return Err(Error::NotAValue {
            at: path.to_string(),
        });
    };

    // The inline handle lives in the packed element data, which the writer
    // copies verbatim, so it has to be correct before the tree is re-read.
    let mut staged = file.to_vec();
    if let Some(inline) = inline {
        let end = target.file_offset + target.size.min(inline.len());
        staged[target.file_offset..end].copy_from_slice(&inline[..end - target.file_offset]);
    }

    let tag = crate::TagFile::parse(&staged, None).map_err(|_| Error::NoData)?;
    let staged_layout = tag.layout().map_err(|_| Error::NoData)?;
    let staged_block = tag.read_data(&staged_layout).map_err(|_| Error::NoData)?;
    // The `bdat` section itself, not the `tgbl` inside it: its offset is where
    // the rebuilt data section has to start.
    let sections = tag.sections();
    let bdat = crate::section::find(&sections, "bdat").ok_or(Error::NoData)?;

    let payload = crate::write::write_block_subst(
        &staged_block,
        &crate::write::Substitution {
            file: &staged,
            at: section_at,
            content,
        },
    );

    // Reassemble: the header and the whole layout section are untouched; only
    // the data section is rebuilt, and the container's payload size follows it.
    let body_before_bdat = bdat.at;
    let mut out = Vec::with_capacity(HEADER_SIZE + body_before_bdat + payload.len() + 24);
    out.extend_from_slice(&file[..HEADER_SIZE + body_before_bdat]);

    let tgbl_total = crate::section::SECTION_HEADER + payload.len();
    out.extend(b"tadb".iter().copied());
    out.extend_from_slice(&1u32.to_le_bytes());
    out.extend_from_slice(&(tgbl_total as u32).to_le_bytes());
    out.extend(b"lbgt".iter().copied());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    out.extend_from_slice(&payload);

    let body_len = out.len() - HEADER_SIZE;
    out[0x48..0x4C].copy_from_slice(&(body_len as u32).to_le_bytes());

    let changed = if out.len() == file.len() {
        match (0..file.len()).find(|i| out[*i] != file[*i]) {
            Some(start) => {
                let last = (start..file.len())
                    .rev()
                    .find(|i| out[*i] != file[*i])
                    .unwrap_or(start);
                start..last + 1
            }
            None => 0..0,
        }
    } else {
        // The file resized, so a byte range is not the useful description.
        HEADER_SIZE + body_before_bdat..out.len()
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

/// Rebuild a tag with several sections and blocks replaced at once.
///
/// [`set_text`] rebuilds a tag around one changed leaf section; this does the
/// same around any number of them, and around whole blocks as well, which is
/// what an edit that changes how many elements a block has requires. The layout
/// section and the file header are untouched — only `bdat` is rebuilt, and the
/// container's payload size follows from it.
///
/// Passing no edits reproduces `file` byte for byte, which is the check that
/// any difference belongs to the edits.
pub fn rewrite(file: &[u8], edits: &crate::write::Edits<'_>) -> Result<Vec<u8>, Error> {
    let tag = crate::TagFile::parse(file, None).map_err(|_| Error::NoData)?;
    let layout = tag.layout().map_err(|_| Error::NoData)?;
    let block = tag.read_data(&layout).map_err(|_| Error::NoData)?;

    let sections = tag.sections();
    let bdat = crate::section::find(&sections, "bdat").ok_or(Error::NoData)?;
    let payload = crate::write::write_block_edits(&block, edits);

    let body_before_bdat = bdat.at;
    let mut out = Vec::with_capacity(HEADER_SIZE + body_before_bdat + payload.len() + 24);
    out.extend_from_slice(&file[..HEADER_SIZE + body_before_bdat]);

    let tgbl_total = crate::section::SECTION_HEADER + payload.len();
    out.extend(b"tadb".iter().copied());
    out.extend_from_slice(&1u32.to_le_bytes());
    out.extend_from_slice(&(tgbl_total as u32).to_le_bytes());
    out.extend(b"lbgt".iter().copied());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    out.extend_from_slice(&payload);

    let body_len = out.len() - HEADER_SIZE;
    out[0x48..0x4C].copy_from_slice(&(body_len as u32).to_le_bytes());
    Ok(out)
}

/// Where the `bdat` payload starts within a tag file, for reporting.
pub fn payload_offset(body_offset: usize) -> usize {
    HEADER_SIZE + body_offset
}

/// A change to how many elements a block has.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ElementOp {
    /// Append one default-initialised element.
    Add,
    /// Insert a copy of element `i` directly after it.
    Duplicate(usize),
    /// Remove element `i`.
    Remove(usize),
}

/// Add, duplicate or remove one element of the block `path` names, returning
/// the whole new tag file.
///
/// The block's `tgbl` is rebuilt with the element spliced in or out — packed
/// bytes and per-element wrapper both — and the parent element's inline copy
/// of the count is fixed to match, exactly as [`crate::write::Edits`]
/// documents. Everything else about the file is reproduced by the same writer
/// the round-trip check runs against every shipped tag.
///
/// A new element is not all zeroes. Where the shipped data has a sentinel for
/// "unset" the default follows it: a `tag reference`'s inline handle is the
/// cleared pattern unset references ship with, and a `* block index` is `-1`
/// ("none") rather than a live index 0. Everything else — enums, integers,
/// reals, strings — is zeroed, and every section-backed field starts as an
/// empty section.
pub fn edit_elements(
    layout: &Layout<'_>,
    file: &[u8],
    block: &Block<'_>,
    path: &str,
    op: ElementOp,
) -> Result<(Vec<u8>, Applied), Error> {
    let (target, value, _) = locate(layout, file, block, path)?;
    let Some(crate::data::Value::Block(inner)) = value else {
        return Err(Error::NotABlock {
            at: path.to_string(),
        });
    };
    let entry = layout
        .blocks
        .get(target.field.aux as usize)
        .copied()
        .ok_or(Error::NoData)?;
    let run = layout.struct_run(entry.aux as usize).ok_or(Error::NoData)?;

    let count = inner.count as usize;
    if let ElementOp::Duplicate(i) | ElementOp::Remove(i) = op {
        if i >= count {
            return Err(Error::IndexOutOfRange {
                at: path.to_string(),
                index: i,
                count: inner.count,
            });
        }
    }
    let new_count = match op {
        ElementOp::Add | ElementOp::Duplicate(_) => {
            if entry.max_count != 0 && inner.count >= entry.max_count {
                return Err(Error::BlockFull {
                    at: path.to_string(),
                    count: inner.count,
                });
            }
            count + 1
        }
        ElementOp::Remove(_) => count - 1,
    };

    let wrapped = inner.flags == 0;
    let size = inner.element_size as usize;

    // The packed bytes and (when this block wraps its elements) the `tgst`
    // wrapper of the element being introduced.
    let (fresh_packed, fresh_wrapper) = match op {
        ElementOp::Add => (
            default_packed(layout, run, path)?,
            if wrapped {
                default_wrapper(layout, run, path)?
            } else {
                Vec::new()
            },
        ),
        ElementOp::Duplicate(i) => (
            inner.element(i).unwrap_or(&[]).to_vec(),
            if wrapped {
                crate::write::wrapper_section(
                    inner.children.get(i).map(Vec::as_slice).unwrap_or(&[]),
                )
            } else {
                Vec::new()
            },
        ),
        ElementOp::Remove(_) => (Vec::new(), Vec::new()),
    };
    if matches!(op, ElementOp::Add) && fresh_packed.len() != size {
        // The layout described an element this builder could not reproduce
        // exactly; refusing beats writing a block the game cannot read.
        return Err(Error::NoDefault {
            at: path.to_string(),
            type_name: format!(
                "{}-byte element ({} built)",
                size,
                fresh_packed.len()
            ),
        });
    }

    // The block's whole new `tgbl` content: header, packed elements, wrappers.
    let mut content = Vec::with_capacity(8 + new_count * size);
    content.extend_from_slice(&(new_count as u32).to_le_bytes());
    content.extend_from_slice(&inner.flags.to_le_bytes());
    match op {
        ElementOp::Add => {
            content.extend_from_slice(inner.elements);
            content.extend_from_slice(&fresh_packed);
        }
        ElementOp::Duplicate(i) => {
            content.extend_from_slice(&inner.elements[..(i + 1) * size]);
            content.extend_from_slice(&fresh_packed);
            content.extend_from_slice(&inner.elements[(i + 1) * size..]);
        }
        ElementOp::Remove(i) => {
            content.extend_from_slice(&inner.elements[..i * size]);
            content.extend_from_slice(&inner.elements[(i + 1) * size..]);
        }
    }
    if wrapped {
        for (k, element) in inner.children.iter().enumerate() {
            if matches!(op, ElementOp::Remove(i) if i == k) {
                continue;
            }
            content.extend_from_slice(&crate::write::wrapper_section(element));
            if matches!(op, ElementOp::Duplicate(i) if i == k) {
                content.extend_from_slice(&fresh_wrapper);
            }
        }
        if matches!(op, ElementOp::Add) {
            content.extend_from_slice(&fresh_wrapper);
        }
    }

    let mut edits = crate::write::Edits::new(file);
    edits
        .blocks
        .insert(offset_within(file, inner.elements), content);
    // The parent element's inline copy of the count must agree with the
    // section header, or the tag describes itself wrongly.
    edits.inline.insert(
        target.file_offset,
        (new_count as u32).to_le_bytes().to_vec(),
    );
    let out = rewrite(file, &edits)?;

    let changed = match (0..file.len().min(out.len())).find(|i| out[*i] != file[*i]) {
        Some(start) => start..out.len(),
        None => file.len().min(out.len())..out.len(),
    };
    Ok((
        out,
        Applied {
            path: path.to_string(),
            type_name: "block".to_string(),
            before: Scalar::Int(inner.count as i64),
            after: Scalar::Int(new_count as i64),
            changed,
        },
    ))
}

/// The packed bytes of one default element of struct run `run`.
fn default_packed(layout: &Layout<'_>, run: usize, at: &str) -> Result<Vec<u8>, Error> {
    let mut out = Vec::new();
    default_packed_into(layout, run, &mut out, at, 0)?;
    Ok(out)
}

fn default_packed_into(
    layout: &Layout<'_>,
    run: usize,
    out: &mut Vec<u8>,
    at: &str,
    depth: u32,
) -> Result<(), Error> {
    if depth > 64 {
        return Err(Error::NoDefault {
            at: at.to_string(),
            type_name: "cyclic struct".to_string(),
        });
    }
    let Some(range) = layout.struct_ranges().get(run).cloned() else {
        return Ok(());
    };
    for i in range {
        let field = layout.fields[i];
        let size = layout.field_size(&field).unwrap_or(0) as usize;
        match layout.type_name_of(&field) {
            "struct" => match layout.struct_run(field.aux as usize) {
                Some(t) => default_packed_into(layout, t, out, at, depth + 1)?,
                None => out.resize(out.len() + size, 0),
            },
            "array" => {
                let target = layout
                    .arrays
                    .get(field.aux as usize)
                    .and_then(|a| Some((a.count, layout.struct_run(a.struct_index as usize)?)));
                match target {
                    Some((n, t)) => {
                        for _ in 0..n {
                            default_packed_into(layout, t, out, at, depth + 1)?;
                        }
                    }
                    None => out.resize(out.len() + size, 0),
                }
            }
            // The inline handle of an unset reference, exactly as the shipped
            // data writes it: cleared group, zero length, unset handle.
            "tag reference" if size == 16 => {
                out.extend_from_slice(&0xFFFF_FFFFu32.to_le_bytes());
                out.extend_from_slice(&0u32.to_le_bytes());
                out.extend_from_slice(&0u32.to_le_bytes());
                out.extend_from_slice(&0xFFFF_FFFFu32.to_le_bytes());
            }
            // Block indices use -1 as "none"; 0 would point at a real element.
            t if t.ends_with("block index") => out.resize(out.len() + size, 0xFF),
            _ => out.resize(out.len() + size, 0),
        }
    }
    Ok(())
}

/// One default element's `tgst` wrapper: an empty or zero-count section for
/// every field that writes one, in declaration order — the order the walker
/// pairs them back up in.
fn default_wrapper(layout: &Layout<'_>, run: usize, at: &str) -> Result<Vec<u8>, Error> {
    let mut content = Vec::new();
    default_children_into(layout, run, &mut content, at, 0)?;
    Ok(crate::write::raw_section(
        "tgst",
        content.len() as u32,
        &content,
    ))
}

fn default_children_into(
    layout: &Layout<'_>,
    run: usize,
    out: &mut Vec<u8>,
    at: &str,
    depth: u32,
) -> Result<(), Error> {
    if depth > 64 {
        return Err(Error::NoDefault {
            at: at.to_string(),
            type_name: "cyclic struct".to_string(),
        });
    }
    let Some(range) = layout.struct_ranges().get(run).cloned() else {
        return Ok(());
    };
    for i in range {
        let field = layout.fields[i];
        if !crate::data::field_writes(layout, &field) {
            continue;
        }
        match layout.type_name_of(&field) {
            "block" => {
                // An empty block: zero elements, wrappers declared present.
                let mut header = Vec::with_capacity(8);
                header.extend_from_slice(&0u32.to_le_bytes());
                header.extend_from_slice(&0u32.to_le_bytes());
                out.extend_from_slice(&crate::write::raw_section("tgbl", 0, &header));
            }
            // A struct's children are defaulted recursively rather than left
            // as the empty `tgst` the shipped data also accepts: a field
            // behind an empty struct has no section to edit, so a defaulted
            // element would be born read-only.
            "struct" => {
                let mut content = Vec::new();
                if let Some(t) = layout.struct_run(field.aux as usize) {
                    default_children_into(layout, t, &mut content, at, depth + 1)?;
                }
                out.extend_from_slice(&crate::write::raw_section(
                    "tgst",
                    content.len() as u32,
                    &content,
                ));
            }
            "string id" => out.extend_from_slice(&crate::write::raw_section("tgsi", 0, &[])),
            "data" => out.extend_from_slice(&crate::write::raw_section("tgda", 0, &[])),
            "tag reference" => out.extend_from_slice(&crate::write::raw_section("tgrf", 0, &[])),
            "array" => {
                // An array writes no wrapper; its elements' sections follow
                // back to back. `field_writes` said the element struct writes.
                let target = layout
                    .arrays
                    .get(field.aux as usize)
                    .and_then(|a| Some((a.count, layout.struct_run(a.struct_index as usize)?)));
                if let Some((n, t)) = target {
                    for _ in 0..n {
                        default_children_into(layout, t, out, at, depth + 1)?;
                    }
                }
            }
            other => {
                // A `pageable resource`'s version word is not reconstructable,
                // so a block holding one cannot grow here.
                return Err(Error::NoDefault {
                    at: at.to_string(),
                    type_name: other.to_string(),
                });
            }
        }
    }
    Ok(())
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
    fn a_route_to_a_root_field_crosses_no_block() {
        let (body, payload) = synth();
        let layout = Layout::parse(&body).unwrap();
        let block = crate::data::read_block(&layout, &payload, 0).unwrap();

        // Through an inlined struct is still the root element: no hop.
        let r = route(&layout, &payload, &block, "meta.n").unwrap();
        assert!(r.hops.is_empty());
        let t = resolve(&layout, &payload, &block, "meta.n").unwrap();
        assert_eq!(r.target.file_offset, t.file_offset);
        assert_eq!(r.target.size, t.size);
        // The synthetic root has no block with elements.
        assert!(root_blocks(&layout, &payload, &block).is_empty());
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

    /// A whole tag file: container header, the layout, then the data section.
    fn synth_file() -> Vec<u8> {
        let body_layout = crate::data::tests::synth_layout();
        let payload = crate::data::tests::synth_payload();

        let mut body = body_layout;
        // bdat { tgbl { payload } }
        let tgbl_total = crate::section::SECTION_HEADER + payload.len();
        body.extend(b"tadb".iter().copied());
        body.extend_from_slice(&1u32.to_le_bytes());
        body.extend_from_slice(&(tgbl_total as u32).to_le_bytes());
        body.extend(b"lbgt".iter().copied());
        body.extend_from_slice(&0u32.to_le_bytes());
        body.extend_from_slice(&(payload.len() as u32).to_le_bytes());
        body.extend_from_slice(&payload);

        let mut file = vec![0u8; HEADER_SIZE];
        file[0x24..0x28].copy_from_slice(&1u32.to_le_bytes());
        file[0x28..0x2C].copy_from_slice(&2u32.to_le_bytes());
        file[0x2C..0x30].copy_from_slice(&0xFFFF_FFFFu32.to_le_bytes());
        file[0x30..0x34].copy_from_slice(&0x7465_7374u32.to_le_bytes());
        file[0x3C..0x40].copy_from_slice(b"MALB");
        file[0x40..0x44].copy_from_slice(b"!gat");
        file[0x48..0x4C].copy_from_slice(&(body.len() as u32).to_le_bytes());
        file.extend_from_slice(&body);
        file
    }

    /// The identity a resizing edit rests on: rebuilding with the value that is
    /// already there must reproduce the file exactly, so any difference is
    /// attributable to the edit and not to the rebuild.
    #[test]
    fn a_resize_to_the_same_value_reproduces_the_file() {
        let file = synth_file();
        let tag = crate::TagFile::parse(&file, Some(file.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();

        let (out, _) = set_text(
            &layout,
            &file,
            &block,
            "tags[0].label",
            &Scalar::Text("aa".into()),
        )
        .unwrap();
        assert_eq!(out, file);
    }

    #[test]
    fn a_longer_value_grows_the_file_and_still_reads_back() {
        let file = synth_file();
        let tag = crate::TagFile::parse(&file, Some(file.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();

        let (out, applied) = set_text(
            &layout,
            &file,
            &block,
            "tags[0].label",
            &Scalar::Text("a_much_longer_value".into()),
        )
        .unwrap();

        assert_eq!(applied.before, Scalar::Text("aa".into()));
        assert_eq!(out.len(), file.len() + ("a_much_longer_value".len() - 2));

        // The rebuilt tag parses, walks exactly, and holds the new value.
        let after = crate::TagFile::parse(&out, Some(out.len())).unwrap();
        let after_layout = after.layout().unwrap();
        let after_block = after.read_data(&after_layout).unwrap();
        let payload = after.data().unwrap();
        assert_eq!(after_block.consumed, payload.size as usize);
        let t = resolve(&after_layout, &out, &after_block, "tags[0].label").unwrap();
        assert_eq!(t.current, Scalar::Text("a_much_longer_value".into()));

        // The other array element is untouched.
        let other = resolve(&after_layout, &out, &after_block, "tags[1].label").unwrap();
        assert_eq!(other.current, Scalar::Text("bb".into()));
    }

    fn section_bytes(magic: &[u8; 4], version: u32, content: &[u8]) -> Vec<u8> {
        let mut out = Vec::new();
        out.extend_from_slice(magic);
        out.extend_from_slice(&version.to_le_bytes());
        out.extend_from_slice(&(content.len() as u32).to_le_bytes());
        out.extend_from_slice(content);
        out
    }

    fn words(vals: &[u32]) -> Vec<u8> {
        vals.iter().flat_map(|v| v.to_le_bytes()).collect()
    }

    fn struct_record(name_offset: u32, first_field: u32) -> Vec<u8> {
        let mut out = vec![0u8; 16];
        out.extend_from_slice(&name_offset.to_le_bytes());
        out.extend_from_slice(&first_field.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out
    }

    /// A layout with two real nested blocks, for element editing:
    ///
    /// ```text
    /// item run (fields 0..4)  long integer n, string id label,
    ///                         short block index link, tag reference ref
    /// raw run  (fields 5..6)  long integer m
    /// root     (fields 7..9)  block items -> blv2[0] (max 3, wrapped)
    ///                         block raws  -> blv2[1] (max 4, flags 1)
    /// ```
    fn synth_block_layout() -> Vec<u8> {
        let names = [
            "terminator X",      // 0
            "block",             // 1
            "string id",         // 2
            "long integer",      // 3
            "short block index", // 4
            "tag reference",     // 5
            "n",                 // 6
            "label",             // 7
            "link",              // 8
            "ref",               // 9
            "items",             // 10
            "raws",              // 11
            "m",                 // 12
            "items_block",       // 13
            "raws_block",        // 14
        ];
        let mut blob = Vec::new();
        let mut at = Vec::new();
        for n in names {
            at.push(blob.len() as u32);
            blob.extend_from_slice(n.as_bytes());
            blob.push(0);
        }

        let mut tgly = section_bytes(b"*rts", 0, &blob);
        tgly.extend_from_slice(&section_bytes(b"sz+x", 0, &[]));
        tgly.extend_from_slice(&section_bytes(
            b"tfgt",
            0,
            &words(&[
                at[0], 0, 0, // terminator X
                at[1], 12, 1, // block
                at[2], 4, 0, // string id
                at[3], 4, 0, // long integer
                at[4], 2, 0, // short block index
                at[5], 16, 0, // tag reference
            ]),
        ));
        tgly.extend_from_slice(&section_bytes(
            b"sarg",
            0,
            &words(&[
                at[6], 3, 0, // 0 long integer n
                at[7], 2, 0, // 1 string id label
                at[8], 4, 0, // 2 short block index link
                at[9], 5, 0, // 3 tag reference ref
                0, 0, 0, //    4 terminator
                at[12], 3, 0, // 5 long integer m
                0, 0, 0, //    6 terminator
                at[10], 1, 0, // 7 block items -> blv2[0]
                at[11], 1, 1, // 8 block raws -> blv2[1]
                0, 0, 0, //    9 terminator
            ]),
        ));
        // stv4: [0] root (first_field 7), [1] item (0), [2] raw (5).
        let mut stv4 = struct_record(0, 7);
        stv4.extend_from_slice(&struct_record(0, 0));
        stv4.extend_from_slice(&struct_record(0, 5));
        tgly.extend_from_slice(&section_bytes(b"4vts", 0, &stv4));
        tgly.extend_from_slice(&section_bytes(
            b"2vlb",
            0,
            &words(&[at[13], 3, 1, at[14], 4, 2]),
        ));

        let mut blay = vec![0u8; 0x4C];
        blay.extend_from_slice(&section_bytes(b"ylgt", 4, &tgly));
        section_bytes(b"yalb", 2, &blay)
    }

    /// One item element's 26 packed bytes: n, then zeroed inline handles.
    fn item_packed(n: u32) -> Vec<u8> {
        let mut e = vec![0u8; 26];
        e[0..4].copy_from_slice(&n.to_le_bytes());
        e
    }

    /// One item element's wrapper: its label and an unset reference.
    fn item_wrapper(label: &str) -> Vec<u8> {
        let mut inner = section_bytes(b"isgt", 0, label.as_bytes());
        inner.extend_from_slice(&section_bytes(b"frgt", 0, &[]));
        section_bytes(b"tsgt", inner.len() as u32, &inner)
    }

    /// The root payload: `items` holding "aa" and "bb", `raws` holding one 7.
    fn synth_block_payload() -> Vec<u8> {
        let mut items = words(&[2, 0]);
        items.extend_from_slice(&item_packed(1));
        items.extend_from_slice(&item_packed(2));
        items.extend_from_slice(&item_wrapper("aa"));
        items.extend_from_slice(&item_wrapper("bb"));

        let mut raws = words(&[1, 1]);
        raws.extend_from_slice(&7u32.to_le_bytes());

        let mut inner = section_bytes(b"lbgt", 0, &items);
        inner.extend_from_slice(&section_bytes(b"lbgt", 0, &raws));

        let mut out = words(&[1, 0]);
        // Root packed data: each block field's 12 inline bytes open with its
        // element count.
        out.extend_from_slice(&words(&[2, 0, 0]));
        out.extend_from_slice(&words(&[1, 0, 0]));
        out.extend_from_slice(&section_bytes(b"tsgt", inner.len() as u32, &inner));
        out
    }

    fn synth_block_file() -> Vec<u8> {
        let body_layout = synth_block_layout();
        let payload = synth_block_payload();

        let mut body = body_layout;
        let tgbl_total = crate::section::SECTION_HEADER + payload.len();
        body.extend(b"tadb".iter().copied());
        body.extend_from_slice(&1u32.to_le_bytes());
        body.extend_from_slice(&(tgbl_total as u32).to_le_bytes());
        body.extend(b"lbgt".iter().copied());
        body.extend_from_slice(&0u32.to_le_bytes());
        body.extend_from_slice(&(payload.len() as u32).to_le_bytes());
        body.extend_from_slice(&payload);

        let mut file = vec![0u8; HEADER_SIZE];
        file[0x24..0x28].copy_from_slice(&1u32.to_le_bytes());
        file[0x28..0x2C].copy_from_slice(&2u32.to_le_bytes());
        file[0x2C..0x30].copy_from_slice(&0xFFFF_FFFFu32.to_le_bytes());
        file[0x30..0x34].copy_from_slice(&0x7465_7374u32.to_le_bytes());
        file[0x3C..0x40].copy_from_slice(b"MALB");
        file[0x40..0x44].copy_from_slice(b"!gat");
        file[0x48..0x4C].copy_from_slice(&(body.len() as u32).to_le_bytes());
        file.extend_from_slice(&body);
        file
    }

    /// Parse `file` and hand its layout and root block to `f`.
    fn with_tag<T>(file: &[u8], f: impl FnOnce(&Layout<'_>, &Block<'_>) -> T) -> T {
        let tag = crate::TagFile::parse(file, Some(file.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();
        f(&layout, &block)
    }

    /// The rebuilt tag must parse, walk exactly, and hold what a check asks.
    fn assert_reads_exactly(out: &[u8]) {
        let tag = crate::TagFile::parse(out, Some(out.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();
        let payload = tag.data().unwrap();
        assert_eq!(block.consumed, payload.size as usize, "walk must be exact");
    }

    #[test]
    fn the_block_synth_walks_and_round_trips() {
        let file = synth_block_file();
        with_tag(&file, |layout, block| {
            let t = resolve(layout, &file, block, "items[1].label").unwrap();
            assert_eq!(t.current, Scalar::Text("bb".into()));
            let t = resolve(layout, &file, block, "raws[0].m").unwrap();
            assert_eq!(t.current, Scalar::Int(7));
        });
    }

    #[test]
    fn adding_an_element_appends_defaults_and_reads_back() {
        let file = synth_block_file();
        let (out, applied) = with_tag(&file, |layout, block| {
            edit_elements(layout, &file, block, "items", ElementOp::Add).unwrap()
        });
        assert_eq!(applied.before, Scalar::Int(2));
        assert_eq!(applied.after, Scalar::Int(3));
        assert_reads_exactly(&out);

        with_tag(&out, |layout, block| {
            // Zeroed value fields, sentinel "unset" defaults elsewhere.
            let t = resolve(layout, &out, block, "items[2].n").unwrap();
            assert_eq!(t.current, Scalar::Int(0));
            let t = resolve(layout, &out, block, "items[2].label").unwrap();
            assert_eq!(t.current, Scalar::Text("".into()));
            let t = resolve(layout, &out, block, "items[2].link").unwrap();
            assert_eq!(t.current, Scalar::BlockIndex(-1));
            let t = resolve(layout, &out, block, "items[2].ref").unwrap();
            assert_eq!(t.current, Scalar::Empty, "an unset reference is empty");
            // The shipped elements are untouched.
            let t = resolve(layout, &out, block, "items[0].label").unwrap();
            assert_eq!(t.current, Scalar::Text("aa".into()));
            // The parent's inline copy of the count followed the header.
            let t = resolve(layout, &out, block, "items").unwrap();
            let Scalar::Raw(inline) = t.current else {
                panic!("a block field reads as its raw inline bytes");
            };
            assert_eq!(&inline[0..4], &3u32.to_le_bytes());
        });
    }

    #[test]
    fn adding_then_removing_reproduces_the_file() {
        let file = synth_block_file();
        let (grown, _) = with_tag(&file, |layout, block| {
            edit_elements(layout, &file, block, "items", ElementOp::Add).unwrap()
        });
        let (back, _) = with_tag(&grown, |layout, block| {
            edit_elements(layout, &grown, block, "items", ElementOp::Remove(2)).unwrap()
        });
        assert_eq!(back, file);
    }

    #[test]
    fn removing_a_middle_element_keeps_the_others() {
        let file = synth_block_file();
        let (out, applied) = with_tag(&file, |layout, block| {
            edit_elements(layout, &file, block, "items", ElementOp::Remove(0)).unwrap()
        });
        assert_eq!(applied.after, Scalar::Int(1));
        assert_reads_exactly(&out);
        with_tag(&out, |layout, block| {
            let t = resolve(layout, &out, block, "items[0].label").unwrap();
            assert_eq!(t.current, Scalar::Text("bb".into()));
            let t = resolve(layout, &out, block, "items[0].n").unwrap();
            assert_eq!(t.current, Scalar::Int(2));
        });
    }

    #[test]
    fn duplicating_copies_packed_data_and_wrapper() {
        let file = synth_block_file();
        let (out, _) = with_tag(&file, |layout, block| {
            edit_elements(layout, &file, block, "items", ElementOp::Duplicate(0)).unwrap()
        });
        assert_reads_exactly(&out);
        with_tag(&out, |layout, block| {
            for (i, (label, n)) in [("aa", 1), ("aa", 1), ("bb", 2)].iter().enumerate() {
                let t = resolve(layout, &out, block, &format!("items[{i}].label")).unwrap();
                assert_eq!(t.current, Scalar::Text((*label).into()), "label {i}");
                let t = resolve(layout, &out, block, &format!("items[{i}].n")).unwrap();
                assert_eq!(t.current, Scalar::Int(*n), "n {i}");
            }
        });
    }

    #[test]
    fn a_full_block_refuses_another_element() {
        let file = synth_block_file();
        let (grown, _) = with_tag(&file, |layout, block| {
            edit_elements(layout, &file, block, "items", ElementOp::Add).unwrap()
        });
        // max_count is 3, and the block now holds 3.
        let err = with_tag(&grown, |layout, block| {
            edit_elements(layout, &grown, block, "items", ElementOp::Add).unwrap_err()
        });
        assert!(matches!(err, Error::BlockFull { count: 3, .. }), "{err}");
    }

    #[test]
    fn an_unwrapped_block_gains_no_wrapper() {
        let file = synth_block_file();
        let (out, _) = with_tag(&file, |layout, block| {
            edit_elements(layout, &file, block, "raws", ElementOp::Add).unwrap()
        });
        assert_reads_exactly(&out);
        with_tag(&out, |layout, block| {
            let t = resolve(layout, &out, block, "raws[1].m").unwrap();
            assert_eq!(t.current, Scalar::Int(0));
            let t = resolve(layout, &out, block, "raws[0].m").unwrap();
            assert_eq!(t.current, Scalar::Int(7));
        });
        // Flags 1: the grown block still declares no per-element wrappers.
        let tag = crate::TagFile::parse(&out, Some(out.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();
        let Some(crate::data::Value::Block(items)) = block.children[0].get(1) else {
            panic!("raws should be the second child of the root element");
        };
        assert_eq!(items.flags, 1);
        assert!(items.children.is_empty());
    }

    #[test]
    fn out_of_range_and_non_block_paths_are_refused() {
        let file = synth_block_file();
        with_tag(&file, |layout, block| {
            let err =
                edit_elements(layout, &file, block, "items", ElementOp::Remove(2)).unwrap_err();
            assert!(matches!(err, Error::IndexOutOfRange { index: 2, .. }), "{err}");
            let err =
                edit_elements(layout, &file, block, "items[0].n", ElementOp::Add).unwrap_err();
            assert!(matches!(err, Error::NotABlock { .. }), "{err}");
        });
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

/// The root element's block fields that have elements, as [`Hop`]s into
/// element 0, each with the block's element count.
///
/// What a runtime that relocates block elements needs in order to work out
/// where it put them: the header to read, and the file's own bytes for the
/// elements to look for. Only root-level blocks; a block inside an element
/// is reached through its parent.
pub fn root_blocks(layout: &Layout<'_>, file: &[u8], block: &Block<'_>) -> Vec<(Hop, u32)> {
    let mut out = Vec::new();
    let Some(run) = layout.struct_run(block.struct_index) else {
        return out;
    };
    let Some(range) = layout.struct_ranges().get(run).cloned() else {
        return out;
    };
    let bytes = block.element(0).unwrap_or(&[]);
    let values = block.children.first().map(Vec::as_slice).unwrap_or(&[]);
    let mut offset = 0u32;
    let mut next_value = 0usize;
    for i in range {
        let field = layout.fields[i];
        let size = layout.field_size(&field).unwrap_or(0);
        let value = if crate::data::field_writes(layout, &field) {
            while matches!(values.get(next_value), Some(crate::data::Value::Phantom)) {
                next_value += 1;
            }
            let v = values.get(next_value);
            next_value += 1;
            v
        } else {
            None
        };
        if layout.type_name_of(&field) == "block" {
            if let (Some(crate::data::Value::Block(inner)), Some(slice)) = (
                value,
                bytes.get(offset as usize..(offset + size) as usize),
            ) {
                if let Some(first) = inner.element(0) {
                    out.push((
                        Hop {
                            header: offset_within(file, slice),
                            index: 0,
                            element: offset_within(file, first),
                            element_size: inner.element_size as usize,
                        },
                        inner.count,
                    ));
                }
            }
        }
        offset += size;
    }
    out
}
