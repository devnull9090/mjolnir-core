//! The `bdat` data section: a tag's actual field values.
//!
//! Fixed-width fields are packed inline in the element data. Fields whose
//! content is variable length emit a trailing section instead, one per field in
//! declaration order, wrapped per element:
//!
//! ```text
//! block:
//!   u32   element count
//!   u32   flags, not yet interpreted
//!   ..    count * element_size bytes of packed element data
//!   ..    one `tgst` per element, each containing that element's variable
//!         length fields in declaration order
//! ```
//!
//! The section magic identifies the field type:
//!
//! | Magic  | Field type      |
//! |--------|-----------------|
//! | `tgbl` | `block`         |
//! | `tgst` | `struct`        |
//! | `tgsi` | `string id`     |
//! | `tgda` | `data`          |
//! | `tgrf` | `tag reference` |
//! | `tgal` | `array`         |
//!
//! The root is not special: the outermost `tgbl` is a block holding one
//! element whose struct is the group's root.
//!
//! See `docs/tag_body_format.md`.

use crate::layout::Layout;
use crate::section;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("truncated block header at offset {0}")]
    TruncatedHeader(usize),
    #[error("block declares {count} elements of {size} bytes, overrunning the {available} bytes available")]
    ElementOverrun {
        count: u32,
        size: u32,
        available: usize,
    },
    #[error("element size for struct {0} could not be resolved")]
    UnknownElementSize(usize),
    #[error("expected a {want} section at offset {at}, found {found:?}")]
    WrongSection {
        want: &'static str,
        at: usize,
        found: String,
    },
    #[error("nesting exceeded {0} levels")]
    TooDeep(u32),
}

/// Maximum nesting. Real definitions are far shallower; this only stops a
/// malformed or cyclic definition from recursing forever.
const MAX_DEPTH: u32 = 64;

/// The section magic a field type serialises as, or `None` if the field is
/// fixed width and lives entirely in the packed element data.
pub fn section_for(type_name: &str) -> Option<&'static str> {
    Some(match type_name {
        "block" => "tgbl",
        "struct" => "tgst",
        "string id" => "tgsi",
        "data" => "tgda",
        "tag reference" => "tgrf",
        "array" => "tgal",
        _ => return None,
    })
}

/// A decoded value tree node.
#[derive(Debug)]
pub enum Value<'a> {
    /// A variable-length array of elements.
    Block(Block<'a>),
    /// An inlined struct's variable-length children.
    Struct { children: Vec<Value<'a>> },
    /// A `string id`, stored as raw UTF-8 without a terminator.
    StringId(&'a [u8]),
    /// A `tag_data` payload.
    Data(&'a [u8]),
    /// A tag reference payload.
    TagRef(&'a [u8]),
    /// A fixed-count array's children.
    Array { children: Vec<Value<'a>> },
}

impl<'a> Value<'a> {
    /// A `string id` decoded as UTF-8, if it is valid.
    pub fn as_str(&self) -> Option<&'a str> {
        match self {
            Value::StringId(b) => std::str::from_utf8(b).ok(),
            _ => None,
        }
    }
}

/// One decoded block.
#[derive(Debug)]
pub struct Block<'a> {
    /// Index into the struct table describing one element.
    pub struct_index: usize,
    pub count: u32,
    /// Second header word. Observed 0 at the root and 1 for nested blocks.
    pub flags: u32,
    pub element_size: u32,
    /// Packed element data, `count * element_size` bytes.
    pub elements: &'a [u8],
    /// Variable-length children, one entry per element.
    pub children: Vec<Vec<Value<'a>>>,
    /// Total bytes this block occupied, header and children included.
    pub consumed: usize,
}

impl<'a> Block<'a> {
    /// The packed bytes of element `i`.
    pub fn element(&self, i: usize) -> Option<&'a [u8]> {
        let size = self.element_size as usize;
        let start = i.checked_mul(size)?;
        self.elements.get(start..start.checked_add(size)?)
    }
}

fn expect<'a>(
    buf: &'a [u8],
    at: usize,
    want: &'static str,
) -> Result<section::Section<'a>, Error> {
    match section::read_at(buf, at) {
        Some(s) if s.is(want) => Ok(s),
        other => Err(Error::WrongSection {
            want,
            at,
            found: other.map(|s| s.name()).unwrap_or_else(|| "<none>".into()),
        }),
    }
}

/// Does this struct run contain anything that serialises as a section?
///
/// A `struct` field whose target has no variable-length content emits no
/// section at all, so the walk must not expect one.
fn has_children(layout: &Layout<'_>, run: usize, depth: u32) -> bool {
    if depth > MAX_DEPTH {
        return false;
    }
    let ranges = layout.struct_ranges();
    let Some(range) = ranges.get(run).cloned() else {
        return false;
    };
    layout.fields[range].iter().any(|f| {
        let name = layout.type_name_of(f);
        match name {
            "struct" => layout
                .struct_run(f.aux as usize)
                .is_some_and(|r| has_children(layout, r, depth + 1)),
            "array" => layout
                .arrays
                .get(f.aux as usize)
                .and_then(|a| layout.struct_run(a.struct_index as usize))
                .is_some_and(|r| has_children(layout, r, depth + 1)),
            other => section_for(other).is_some(),
        }
    })
}

/// Decode a block whose elements are described by struct-table index
/// `struct_index`.
pub fn read_block<'a>(
    layout: &Layout<'a>,
    buf: &'a [u8],
    struct_index: usize,
) -> Result<Block<'a>, Error> {
    read_block_inner(layout, buf, struct_index, 0)
}

fn read_block_inner<'a>(
    layout: &Layout<'a>,
    buf: &'a [u8],
    struct_index: usize,
    depth: u32,
) -> Result<Block<'a>, Error> {
    if depth > MAX_DEPTH {
        return Err(Error::TooDeep(MAX_DEPTH));
    }
    if buf.len() < 8 {
        return Err(Error::TruncatedHeader(buf.len()));
    }
    let count = u32::from_le_bytes(buf[0..4].try_into().unwrap());
    let flags = u32::from_le_bytes(buf[4..8].try_into().unwrap());

    let run = layout
        .struct_run(struct_index)
        .ok_or(Error::UnknownElementSize(struct_index))?;
    let element_size = layout
        .struct_size(run)
        .ok_or(Error::UnknownElementSize(struct_index))?;

    let span = (count as usize)
        .checked_mul(element_size as usize)
        .ok_or(Error::UnknownElementSize(struct_index))?;
    let elements = buf.get(8..8 + span).ok_or(Error::ElementOverrun {
        count,
        size: element_size,
        available: buf.len().saturating_sub(8),
    })?;

    // Variable-length content follows the packed elements. Each element gets
    // its own `tgst`, but only when the element struct declares anything
    // variable length.
    //
    // This is deliberately strict: a walk that cannot find the next section
    // fails rather than stopping early, so a short read is never mistaken for
    // a complete one.
    let mut pos = 8 + span;
    let mut children = Vec::with_capacity(count as usize);
    if has_children(layout, run, 0) {
        for _ in 0..count {
            let wrapper = expect(buf, pos, "tgst")?;
            children.push(read_struct_children(layout, wrapper.content, run, depth + 1)?);
            pos += wrapper.total();
        }
    }

    Ok(Block {
        struct_index,
        count,
        flags,
        element_size,
        elements,
        children,
        consumed: pos,
    })
}

/// Read the variable-length fields of one struct run, in declaration order.
fn read_struct_children<'a>(
    layout: &Layout<'a>,
    buf: &'a [u8],
    run: usize,
    depth: u32,
) -> Result<Vec<Value<'a>>, Error> {
    if depth > MAX_DEPTH {
        return Err(Error::TooDeep(MAX_DEPTH));
    }
    let ranges = layout.struct_ranges();
    let Some(range) = ranges.get(run).cloned() else {
        return Ok(Vec::new());
    };

    let mut out = Vec::new();
    let mut pos = 0usize;
    for field in &layout.fields[range] {
        let type_name = layout.type_name_of(field);
        let Some(magic) = section_for(type_name) else {
            continue;
        };
        // Structs and arrays with no variable-length content emit nothing.
        if type_name == "struct" {
            let Some(target) = layout.struct_run(field.aux as usize) else {
                continue;
            };
            if !has_children(layout, target, 0) {
                continue;
            }
        }
        if type_name == "array" {
            let target = layout
                .arrays
                .get(field.aux as usize)
                .and_then(|a| layout.struct_run(a.struct_index as usize));
            match target {
                Some(t) if has_children(layout, t, 0) => {}
                _ => continue,
            }
        }
        let s = expect(buf, pos, magic)?;
        pos += s.total();

        let value = match type_name {
            "block" => {
                let entry = layout
                    .blocks
                    .get(field.aux as usize)
                    .ok_or(Error::UnknownElementSize(field.aux as usize))?;
                Value::Block(read_block_inner(
                    layout,
                    s.content,
                    entry.aux as usize,
                    depth + 1,
                )?)
            }
            "struct" => {
                let target = layout
                    .struct_run(field.aux as usize)
                    .ok_or(Error::UnknownElementSize(field.aux as usize))?;
                Value::Struct {
                    children: read_struct_children(layout, s.content, target, depth + 1)?,
                }
            }
            "array" => {
                let entry = layout
                    .arrays
                    .get(field.aux as usize)
                    .ok_or(Error::UnknownElementSize(field.aux as usize))?;
                let target = layout
                    .struct_run(entry.struct_index as usize)
                    .ok_or(Error::UnknownElementSize(entry.struct_index as usize))?;
                let mut children = Vec::new();
                let mut inner = 0usize;
                for _ in 0..entry.count {
                    let w = expect(s.content, inner, "tgst")?;
                    children.push(Value::Struct {
                        children: read_struct_children(layout, w.content, target, depth + 1)?,
                    });
                    inner += w.total();
                }
                Value::Array { children }
            }
            "string id" => Value::StringId(s.content),
            "data" => Value::Data(s.content),
            "tag reference" => Value::TagRef(s.content),
            _ => continue,
        };
        out.push(value);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn field_types_map_to_section_magics() {
        assert_eq!(section_for("block"), Some("tgbl"));
        assert_eq!(section_for("struct"), Some("tgst"));
        assert_eq!(section_for("string id"), Some("tgsi"));
        assert_eq!(section_for("data"), Some("tgda"));
        assert_eq!(section_for("tag reference"), Some("tgrf"));
        assert_eq!(section_for("array"), Some("tgal"));
    }

    #[test]
    fn fixed_width_types_have_no_section() {
        for t in ["real", "long integer", "short enum", "real vector 3d", "pad"] {
            assert_eq!(section_for(t), None, "{t} should be inline");
        }
    }

    #[test]
    fn element_slices_are_bounded() {
        let block = Block {
            struct_index: 0,
            count: 3,
            flags: 0,
            element_size: 4,
            elements: &[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            children: Vec::new(),
            consumed: 20,
        };
        assert_eq!(block.element(0), Some(&[1, 2, 3, 4][..]));
        assert_eq!(block.element(2), Some(&[9, 10, 11, 12][..]));
        assert_eq!(block.element(3), None);
    }

    #[test]
    fn string_id_values_decode_as_utf8() {
        assert_eq!(Value::StringId(b"event_time").as_str(), Some("event_time"));
        assert_eq!(Value::Data(b"event_time").as_str(), None);
    }
}
