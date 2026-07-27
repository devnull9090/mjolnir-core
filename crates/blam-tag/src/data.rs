//! The `bdat` data section: a tag's actual field values.
//!
//! Fixed-width fields are packed inline in the element data. Fields whose
//! content is variable length write a trailing section instead, in declaration
//! order:
//!
//! ```text
//! block:
//!   u32   element count
//!   u32   flags: 0 when a per-element `tgst` follows, 1 when none does
//!   ..    count * element_size bytes of packed element data
//!   ..    one `tgst` per element, each containing that element's variable
//!         length fields in declaration order
//! ```
//!
//! What each field type writes:
//!
//! | Field type          | Writes                                              |
//! |---------------------|-----------------------------------------------------|
//! | `block`             | `tgbl`                                              |
//! | `struct`            | `tgst`, always, even when it ends up empty          |
//! | `string id`         | `tgsi`                                              |
//! | `data`              | `tgda`                                              |
//! | `tag reference`     | `tgrf`                                              |
//! | `pageable resource` | a section whose magic reads `tg?c`                  |
//! | `array`             | nothing; its elements' sections follow inline       |
//! | everything else     | nothing; the value is inline in the element data    |
//!
//! Whether a block writes its per-element `tgst` is decided by the `flags` word
//! in its own header, not by the element struct's field list. A block whose
//! elements have nothing variable length still writes one empty `tgst` each
//! when `flags` is 0.
//!
//! The root is not special: the outermost `tgbl` is a block holding one
//! element whose struct is the group's root.
//!
//! The walk is strict. It reports a missing or unread byte rather than stopping
//! early, and it checks each nested section is consumed exactly, because a
//! parent advances by a child's declared size and would otherwise hide a gap.
//!
//! See `docs/tag_body_format.md` for the evidence behind each rule.

use std::ops::Range;

use crate::layout::Layout;
use crate::section;

/// A walk failure, tagged with the field path it happened at.
///
/// The path is what makes a failure actionable: `root.seams[3].mopp code`
/// names the exact field rather than a bare buffer offset.
#[derive(Debug, thiserror::Error)]
#[error("{path}: {kind}")]
pub struct Error {
    /// Dotted field path from the root struct, e.g. `root.seams[3].errors`.
    pub path: String,
    #[source]
    pub kind: ErrorKind,
}

#[derive(Debug, thiserror::Error)]
pub enum ErrorKind {
    #[error("truncated block header, {0} bytes available")]
    TruncatedHeader(usize),
    #[error("block declares {count} elements of {size} bytes, overrunning the {available} bytes available")]
    ElementOverrun {
        count: u32,
        size: u32,
        available: usize,
    },
    #[error("element size for struct {0} could not be resolved")]
    UnknownElementSize(usize),
    #[error("expected a {want} section at offset {at} of {available}, found {found:?} [{preview}]")]
    WrongSection {
        want: &'static str,
        at: usize,
        available: usize,
        found: String,
        /// Hex preview of the bytes at `at`, to make a bad guess diagnosable.
        preview: String,
    },
    #[error("nesting exceeded {0} levels")]
    TooDeep(u32),
    #[error("expected a tg?c pageable-resource section at offset {at} of {available}, found [{preview}]")]
    NotResource {
        at: usize,
        available: usize,
        preview: String,
    },
    #[error("read {used} of the {declared} bytes the {magic} section declares, unread [{preview}]")]
    SectionSlack {
        magic: &'static str,
        used: usize,
        declared: usize,
        preview: String,
    },
}

/// First bytes of `buf` from `at`, as hex, for diagnosing an unread tail.
fn hex_preview(buf: &[u8], at: usize) -> String {
    buf.get(at..)
        .map(|b| {
            b.iter()
                .take(32)
                .map(|x| format!("{x:02x}"))
                .collect::<Vec<_>>()
                .join(" ")
        })
        .unwrap_or_default()
}

/// Maximum nesting. Real definitions are far shallower; this only stops a
/// malformed or cyclic definition from recursing forever.
const MAX_DEPTH: u32 = 64;

/// The section magic a field type serialises as, or `None` if the field is
/// fixed width and lives entirely in the packed element data.
pub fn section_for(type_name: &str) -> Option<&'static str> {
    Some(match type_name {
        BLOCK => "tgbl",
        STRUCT => "tgst",
        "string id" => "tgsi",
        "data" => "tgda",
        "tag reference" => "tgrf",
        _ => return None,
    })
}

/// Type names the walk special-cases.
const STRUCT: &str = "struct";
const ARRAY: &str = "array";
const BLOCK: &str = "block";
const PAGEABLE: &str = "pageable resource";

/// Does this field write a section into the data stream?
///
/// This is the single definition of that question. The walk uses it to know
/// what to read, and anything pairing fields back up with the values it
/// produced must use it too, or the two will drift out of step.
pub fn field_writes(layout: &Layout<'_>, field: &crate::layout::FieldEntry) -> bool {
    field_writes_inner(layout, field, 0)
}

fn field_writes_inner(layout: &Layout<'_>, field: &crate::layout::FieldEntry, depth: u32) -> bool {
    if depth > MAX_DEPTH {
        return false;
    }
    match layout.type_name_of(field) {
        PAGEABLE => true,
        // An array writes nothing of its own; it appears in the stream only
        // when its element struct writes something.
        ARRAY => layout
            .arrays
            .get(field.aux as usize)
            .and_then(|a| layout.struct_run(a.struct_index as usize))
            .is_some_and(|r| run_writes(layout, r, depth + 1)),
        other => section_for(other).is_some(),
    }
}

/// Does any field of this struct run write a section?
pub fn run_writes(layout: &Layout<'_>, run: usize, depth: u32) -> bool {
    if depth > MAX_DEPTH {
        return false;
    }
    let Some(range) = layout.struct_ranges().get(run).cloned() else {
        return false;
    };
    layout.fields[range]
        .iter()
        .any(|f| field_writes_inner(layout, f, depth + 1))
}

/// Breadcrumb for one field: its name, or its type in angle brackets when the
/// definition leaves it unnamed.
fn crumb(name: &str, type_name: &str) -> String {
    if name.is_empty() {
        format!("<{type_name}>")
    } else {
        name.to_string()
    }
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
    /// A `pageable resource` handle. Its section magic reads `tg?c`, where the
    /// third character is `r` when a resource is attached and NUL when it is
    /// not, so it is matched on `t`, `g` and `c` alone.
    Resource {
        kind: u8,
        version: u32,
        body: &'a [u8],
    },
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
    /// Second header word, and the authority on whether per-element `tgst`
    /// wrappers follow the packed element data: `0` means they do, `1` means
    /// they do not.
    ///
    /// This is not derivable from the definition. A block whose elements have
    /// no variable-length content still writes one empty `tgst` per element
    /// when this is `0`, which is why the element struct's field list cannot
    /// stand in for it.
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

/// Decode a block whose elements are described by struct-table index
/// `struct_index`.
pub fn read_block<'a>(
    layout: &Layout<'a>,
    buf: &'a [u8],
    struct_index: usize,
) -> Result<Block<'a>, Error> {
    Walker::new(layout, false).block(buf, struct_index, 0)
}

/// One section the walk read, for format analysis.
#[derive(Debug, Clone, Copy)]
pub struct SectionStat {
    pub magic: [u8; 4],
    pub version: u32,
    pub size: u32,
}

/// Diagnostics gathered alongside a traced walk.
#[derive(Debug, Default)]
pub struct WalkReport {
    pub trace: Vec<String>,
    pub sections: Vec<SectionStat>,
}

/// Decode a block, also returning a human-readable trace of the walk.
///
/// The trace is emitted as the walk proceeds, so it is still populated when the
/// walk fails, which is what makes it useful for diagnosing a new group.
pub fn read_block_traced<'a>(
    layout: &Layout<'a>,
    buf: &'a [u8],
    struct_index: usize,
) -> (Result<Block<'a>, Error>, WalkReport) {
    let mut w = Walker::new(layout, true);
    let result = w.block(buf, struct_index, 0);
    (
        result,
        WalkReport {
            trace: w.trace,
            sections: w.seen,
        },
    )
}

/// Recursive walk state: the layout, the cached struct runs, and the breadcrumb
/// path used to tag failures.
struct Walker<'a, 'l> {
    layout: &'l Layout<'a>,
    ranges: &'l [Range<usize>],
    /// Struct-table index to field run, from `stv4[i].first_field`.
    run_map: &'l [Option<usize>],
    /// `has_children` memo, one slot per struct run.
    children_memo: Vec<Option<bool>>,
    crumbs: Vec<String>,
    trace: Vec<String>,
    tracing: bool,
    /// Every section read, recorded only while tracing.
    seen: Vec<SectionStat>,
}

impl<'a, 'l> Walker<'a, 'l> {
    fn new(layout: &'l Layout<'a>, tracing: bool) -> Self {
        let ranges = layout.struct_ranges();
        Walker {
            layout,
            ranges,
            run_map: layout.struct_run_map(),
            children_memo: vec![None; ranges.len()],
            crumbs: Vec::new(),
            trace: Vec::new(),
            tracing,
            seen: Vec::new(),
        }
    }

    /// Field run for a struct-table index.
    fn run(&self, struct_index: usize) -> Option<usize> {
        *self.run_map.get(struct_index)?
    }

    fn path(&self) -> String {
        if self.crumbs.is_empty() {
            "root".to_string()
        } else {
            format!("root.{}", self.crumbs.join("."))
        }
    }

    fn err(&self, kind: ErrorKind) -> Error {
        Error {
            path: self.path(),
            kind,
        }
    }

    fn log(&mut self, depth: u32, line: impl AsRef<str>) {
        if self.tracing {
            let indent = "  ".repeat(depth as usize);
            self.trace.push(format!("{indent}{}", line.as_ref()));
        }
    }

    /// Does this struct run write anything into the data stream? Memoised,
    /// because a block asks it once per element otherwise.
    fn has_children(&mut self, run: usize) -> bool {
        if let Some(Some(known)) = self.children_memo.get(run) {
            return *known;
        }
        let answer = run_writes(self.layout, run, 0);
        if let Some(slot) = self.children_memo.get_mut(run) {
            *slot = Some(answer);
        }
        answer
    }

    fn note(&mut self, s: &section::Section<'a>) {
        if self.tracing {
            self.seen.push(SectionStat {
                magic: s.magic,
                version: s.version,
                size: s.size,
            });
        }
    }

    fn expect(
        &self,
        buf: &'a [u8],
        at: usize,
        want: &'static str,
    ) -> Result<section::Section<'a>, Error> {
        match section::read_at(buf, at) {
            Some(s) if s.is(want) => Ok(s),
            other => Err(self.err(ErrorKind::WrongSection {
                want,
                at,
                available: buf.len(),
                found: other.map(|s| s.name()).unwrap_or_else(|| "<none>".into()),
                preview: buf
                    .get(at..)
                    .map(|b| {
                        b.iter()
                            .take(24)
                            .map(|x| format!("{x:02x}"))
                            .collect::<Vec<_>>()
                            .join(" ")
                    })
                    .unwrap_or_default(),
            })),
        }
    }

    /// Read the section a `pageable resource` field emits.
    ///
    /// It uses the standard 12-byte section shape, but its magic carries a NUL
    /// in the third character when no resource is attached, which the printable
    /// check in [`section::read_at`] rejects. Stored magics are reversed, so the
    /// on-disk bytes are `c ? g t`.
    fn resource(&self, buf: &'a [u8], at: usize) -> Result<(u8, u32, &'a [u8], usize), Error> {
        let head = buf.get(at..at + section::SECTION_HEADER).filter(|h| {
            h[3] == b't' && h[2] == b'g' && h[0] == b'c'
        });
        let Some(head) = head else {
            return Err(self.err(ErrorKind::NotResource {
                at,
                available: buf.len(),
                preview: buf
                    .get(at..)
                    .map(|b| {
                        b.iter()
                            .take(24)
                            .map(|x| format!("{x:02x}"))
                            .collect::<Vec<_>>()
                            .join(" ")
                    })
                    .unwrap_or_default(),
            }));
        };
        let kind = head[1];
        let version = u32::from_le_bytes(head[4..8].try_into().unwrap());
        let size = u32::from_le_bytes(head[8..12].try_into().unwrap()) as usize;
        let start = at + section::SECTION_HEADER;
        let body = buf.get(start..start + size).ok_or_else(|| {
            self.err(ErrorKind::NotResource {
                at,
                available: buf.len(),
                preview: String::new(),
            })
        })?;
        Ok((kind, version, body, section::SECTION_HEADER + size))
    }

    fn block(
        &mut self,
        buf: &'a [u8],
        struct_index: usize,
        depth: u32,
    ) -> Result<Block<'a>, Error> {
        if depth > MAX_DEPTH {
            return Err(self.err(ErrorKind::TooDeep(MAX_DEPTH)));
        }
        if buf.len() < 8 {
            return Err(self.err(ErrorKind::TruncatedHeader(buf.len())));
        }
        let count = u32::from_le_bytes(buf[0..4].try_into().unwrap());
        let flags = u32::from_le_bytes(buf[4..8].try_into().unwrap());

        let run = self
            .run(struct_index)
            .ok_or_else(|| self.err(ErrorKind::UnknownElementSize(struct_index)))?;
        let element_size = self
            .layout
            .struct_size(run)
            .ok_or_else(|| self.err(ErrorKind::UnknownElementSize(struct_index)))?;

        let wrapped = flags == 0;
        self.log(
            depth,
            format!(
                "block {} struct#{struct_index} run#{run} count={count} flags={flags} \
                 elem={element_size}b wrappers={wrapped} avail={}",
                self.path(),
                buf.len()
            ),
        );

        let span = (count as usize)
            .checked_mul(element_size as usize)
            .ok_or_else(|| self.err(ErrorKind::UnknownElementSize(struct_index)))?;
        let elements = buf.get(8..8 + span).ok_or_else(|| {
            self.err(ErrorKind::ElementOverrun {
                count,
                size: element_size,
                available: buf.len().saturating_sub(8),
            })
        })?;

        // Variable-length content follows the packed elements. Each element gets
        // its own `tgst`, but only when the element struct declares anything
        // variable length.
        //
        // This is deliberately strict: a walk that cannot find the next section
        // fails rather than stopping early, so a short read is never mistaken
        // for a complete one.
        let mut pos = 8 + span;
        let mut children = Vec::with_capacity(count as usize);
        if wrapped {
            for i in 0..count {
                self.crumbs.push(format!("[{i}]"));
                let outcome = self.expect(buf, pos, "tgst").inspect(|w| self.note(w)).and_then(|wrapper| {
                    let (kids, used) = self.struct_children(wrapper.content, run, depth + 1)?;
                    if used != wrapper.content.len() {
                        return Err(self.err(ErrorKind::SectionSlack {
                            magic: "tgst",
                            used,
                            declared: wrapper.content.len(),
                            preview: hex_preview(wrapper.content, used),
                        }));
                    }
                    Ok((kids, wrapper.total()))
                });
                self.crumbs.pop();
                let (kids, used) = outcome?;
                children.push(kids);
                pos += used;
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

    /// Read the variable-length fields of one struct run, in declaration order,
    /// starting at the front of `buf`.
    ///
    /// Returns the values and the number of bytes consumed. The byte count is
    /// what lets an `array` chain its elements, which are laid down back to back
    /// with no wrapper of their own.
    fn struct_children(
        &mut self,
        buf: &'a [u8],
        run: usize,
        depth: u32,
    ) -> Result<(Vec<Value<'a>>, usize), Error> {
        if depth > MAX_DEPTH {
            return Err(self.err(ErrorKind::TooDeep(MAX_DEPTH)));
        }
        let Some(range) = self.ranges.get(run).cloned() else {
            return Ok((Vec::new(), 0));
        };

        let mut out = Vec::new();
        let mut pos = 0usize;
        for index in range {
            let field = self.layout.fields[index];
            let type_name = self.layout.type_name_of(&field);
            let name = self.layout.string_at(field.name_offset).unwrap_or("");

            // A `pageable resource` writes a section whose magic the generic
            // reader rejects, so it is read on its own path.
            if type_name == PAGEABLE {
                let (kind, version, body, used) = self.resource(buf, pos)?;
                self.log(
                    depth,
                    format!(
                        "{}.{name} pageable resource -> tg{}c at +{pos} size {}",
                        self.path(),
                        if kind == 0 { '.' } else { kind as char },
                        body.len()
                    ),
                );
                out.push(Value::Resource { kind, version, body });
                pos += used;
                continue;
            }

            // An `array` is an inline repetition. Its fixed-width part is
            // already inside the packed element data, counted by
            // `Layout::field_size`, and it has no wrapper section of its own:
            // each element's sections follow back to back. So it appears in the
            // stream only when its element struct writes something.
            if type_name == ARRAY {
                let Some(entry) = self.layout.arrays.get(field.aux as usize).copied() else {
                    continue;
                };
                let Some(target) = self.run(entry.struct_index as usize) else {
                    continue;
                };
                if !self.has_children(target) {
                    continue;
                }
                self.crumbs.push(crumb(name, type_name));
                self.log(
                    depth,
                    format!("{} array x{} inline at +{pos}", self.path(), entry.count),
                );
                let mut children = Vec::new();
                for i in 0..entry.count {
                    self.crumbs.push(format!("[{i}]"));
                    let (kids, used) = self.struct_children(&buf[pos..], target, depth + 1)?;
                    self.crumbs.pop();
                    children.push(Value::Struct { children: kids });
                    pos += used;
                }
                self.crumbs.pop();
                out.push(Value::Array { children });
                continue;
            }

            let Some(magic) = section_for(type_name) else {
                continue;
            };
            // A `struct` inlines another run; resolve it before reading, so the
            // section body can be walked against it.
            let struct_target = if type_name == STRUCT {
                match self.run(field.aux as usize) {
                    Some(t) => Some(t),
                    None => continue,
                }
            } else {
                None
            };

            self.crumbs.push(crumb(name, type_name));
            let s = self.expect(buf, pos, magic)?;
            self.note(&s);
            self.log(
                depth,
                format!(
                    "{} {type_name} -> {magic} at +{pos} size {}",
                    self.path(),
                    s.size
                ),
            );
            let value = match type_name {
                BLOCK => {
                    let entry = *self
                        .layout
                        .blocks
                        .get(field.aux as usize)
                        .ok_or_else(|| self.err(ErrorKind::UnknownElementSize(field.aux as usize)))?;
                    let inner = self.block(s.content, entry.aux as usize, depth + 1)?;
                    if inner.consumed != s.content.len() {
                        return Err(self.err(ErrorKind::SectionSlack {
                            magic: "tgbl",
                            used: inner.consumed,
                            declared: s.content.len(),
                            preview: hex_preview(s.content, inner.consumed),
                        }));
                    }
                    Value::Block(inner)
                }
                // A `tgst` of declared size zero carries no children even when
                // its struct declares fields that would write: the section
                // header is the authority on what is present, and the shipped
                // scenario tags use an empty `tgst` for a struct left at its
                // defaults.
                STRUCT if s.content.is_empty() => Value::Struct {
                    children: Vec::new(),
                },
                STRUCT => {
                    let (children, used) =
                        self.struct_children(s.content, struct_target.unwrap(), depth + 1)?;
                    if used != s.content.len() {
                        return Err(self.err(ErrorKind::SectionSlack {
                            magic: "tgst",
                            used,
                            declared: s.content.len(),
                            preview: hex_preview(s.content, used),
                        }));
                    }
                    Value::Struct { children }
                }
                "string id" => Value::StringId(s.content),
                "data" => Value::Data(s.content),
                "tag reference" => Value::TagRef(s.content),
                _ => unreachable!("section_for returned a magic for {type_name}"),
            };
            self.crumbs.pop();
            pos += s.total();
            out.push(value);
        }
        Ok((out, pos))
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

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

    /// A layout exercising the three rules the shipped data pinned down: a
    /// `struct` always emits, even with nothing variable length under it; an
    /// `array` emits its elements inline with no wrapper; and a
    /// `pageable resource` emits a `tg?c` section.
    ///
    /// ```text
    /// run A  (fields 0..1)  long integer n            <- nothing variable length
    /// run B  (fields 2..3)  string id label
    /// root   (fields 4..7)  struct meta -> run A
    ///                       array tags  -> 2 x run B
    ///                       pageable resource res
    /// ```
    pub(crate) fn synth_layout() -> Vec<u8> {
        let names = [
            "terminator X",
            "struct",
            "string id",
            "long integer",
            "array",
            "pageable resource",
            "n",
            "label",
            "meta",
            "tags",
            "res",
            "elem",
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
                at[0], 0, 0, at[1], 0, 1, at[2], 4, 0, at[3], 4, 0, at[4], 0, 0, at[5], 8, 0,
            ]),
        ));
        tgly.extend_from_slice(&section_bytes(
            b"sarg",
            0,
            &words(&[
                at[6], 3, 0, // 0 long integer n
                0, 0, 0, // 1 terminator
                at[7], 2, 0, // 2 string id label
                0, 0, 0, // 3 terminator
                at[8], 1, 1, // 4 struct meta -> stv4[1]
                at[9], 4, 0, // 5 array tags -> arr![0]
                at[10], 5, 0, // 6 pageable resource res
                0, 0, 0, // 7 terminator
            ]),
        ));
        tgly.extend_from_slice(&section_bytes(b"!rra", 0, &words(&[at[11], 2, 2])));
        let mut stv4 = struct_record(0, 4);
        stv4.extend_from_slice(&struct_record(0, 0));
        stv4.extend_from_slice(&struct_record(0, 2));
        tgly.extend_from_slice(&section_bytes(b"4vts", 0, &stv4));

        let mut blay = vec![0u8; 0x4C];
        blay.extend_from_slice(&section_bytes(b"ylgt", 4, &tgly));
        section_bytes(b"yalb", 2, &blay)
    }

    /// One root element: 20 bytes packed, then its `tgst` holding an empty
    /// `tgst` for `meta`, two inline `tgsi` for `tags`, and a `tg?c` for `res`.
    pub(crate) fn synth_payload() -> Vec<u8> {
        let mut inner = section_bytes(b"tsgt", 0, &[]);
        inner.extend_from_slice(&section_bytes(b"isgt", 0, b"aa"));
        inner.extend_from_slice(&section_bytes(b"isgt", 0, b"bb"));
        inner.extend_from_slice(&section_bytes(b"crgt", 0, &[]));

        let mut out = words(&[1, 0]);
        out.extend_from_slice(&[0u8; 20]);
        // A `tgst` repeats its content size in the version word, as the shipped
        // data does; the empty one above is size 0, so its version is 0 too.
        out.extend_from_slice(&section_bytes(b"tsgt", inner.len() as u32, &inner));
        out
    }

    #[test]
    fn walks_struct_array_and_resource_exactly() {
        let body = synth_layout();
        let l = Layout::parse(&body).unwrap();
        let payload = synth_payload();

        let block = read_block(&l, &payload, 0).expect("walk");
        assert_eq!(block.count, 1);
        assert_eq!(block.element_size, 20);
        assert_eq!(block.consumed, payload.len(), "must consume the payload exactly");

        let kids = &block.children[0];
        assert!(matches!(kids[0], Value::Struct { ref children } if children.is_empty()));
        match &kids[1] {
            Value::Array { children } => {
                assert_eq!(children.len(), 2);
                let texts: Vec<_> = children
                    .iter()
                    .map(|c| match c {
                        Value::Struct { children } => children[0].as_str().unwrap(),
                        _ => panic!("array element should be a struct"),
                    })
                    .collect();
                assert_eq!(texts, ["aa", "bb"]);
            }
            other => panic!("expected an array, got {other:?}"),
        }
        assert!(matches!(kids[2], Value::Resource { kind: b'r', .. }));
    }

    /// The identity the whole editing path rests on: bytes in, tree, bytes out.
    #[test]
    fn a_walked_payload_re_serialises_to_the_same_bytes() {
        let body = synth_layout();
        let l = Layout::parse(&body).unwrap();
        let payload = synth_payload();

        let block = read_block(&l, &payload, 0).expect("walk");
        assert_eq!(crate::write::write_block(&block), payload);
    }

    #[test]
    fn a_block_with_flags_1_has_no_element_wrappers() {
        let body = synth_layout();
        let l = Layout::parse(&body).unwrap();
        // Same root, but flagged as carrying no per-element wrappers, so the
        // payload is just the header and the packed element.
        let mut payload = words(&[1, 1]);
        payload.extend_from_slice(&[0u8; 20]);

        let block = read_block(&l, &payload, 0).expect("walk");
        assert_eq!(block.flags, 1);
        assert!(block.children.is_empty());
        assert_eq!(block.consumed, payload.len());
        assert_eq!(crate::write::write_block(&block), payload);
    }

    #[test]
    fn a_missing_section_names_the_field_path() {
        let body = synth_layout();
        let l = Layout::parse(&body).unwrap();
        let mut payload = synth_payload();
        // Corrupt the `tgsi` magic of the array's first element.
        let at = payload.len() - 12 - 14 - 14;
        payload[at..at + 4].copy_from_slice(b"zzzz");

        let err = read_block(&l, &payload, 0).unwrap_err();
        assert_eq!(err.path, "root.[0].tags.[0].label");
        assert!(matches!(err.kind, ErrorKind::WrongSection { want: "tgsi", .. }));
    }

    #[test]
    fn a_short_read_inside_a_section_is_reported_not_ignored() {
        let body = synth_layout();
        let l = Layout::parse(&body).unwrap();
        let mut payload = synth_payload();
        // Grow the element wrapper's declared size without adding content, so
        // the walk reads less than the section claims.
        payload.extend_from_slice(&[0u8; 4]);
        let head = 8 + 20;
        let size = u32::from_le_bytes(payload[head + 8..head + 12].try_into().unwrap());
        payload[head + 8..head + 12].copy_from_slice(&(size + 4).to_le_bytes());

        let err = read_block(&l, &payload, 0).unwrap_err();
        assert!(matches!(err.kind, ErrorKind::SectionSlack { .. }), "{err}");
    }

    #[test]
    fn field_types_map_to_section_magics() {
        assert_eq!(section_for("block"), Some("tgbl"));
        assert_eq!(section_for("struct"), Some("tgst"));
        assert_eq!(section_for("string id"), Some("tgsi"));
        assert_eq!(section_for("data"), Some("tgda"));
        assert_eq!(section_for("tag reference"), Some("tgrf"));
    }

    #[test]
    fn fixed_width_types_have_no_section() {
        for t in ["real", "long integer", "short enum", "real vector 3d", "pad"] {
            assert_eq!(section_for(t), None, "{t} should be inline");
        }
    }

    /// `array` and `pageable resource` are handled on their own paths: an array
    /// writes its elements inline with no wrapper, and a pageable resource
    /// writes a `tg?c` magic the generic reader will not accept.
    #[test]
    fn array_and_resource_are_not_generic_sections() {
        assert_eq!(section_for("array"), None);
        assert_eq!(section_for("pageable resource"), None);
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
