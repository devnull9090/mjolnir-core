//! Pull the script section out of a decoded `scenario` tag.
//!
//! A scenario is the largest tag the game ships — `C45` decodes to twelve
//! megabytes — so this walks [`blam_tag::data::Block`] directly instead of
//! going through [`blam_tag::view`], which materialises `Node`s and caps the
//! elements it builds. The script blocks are exactly the ones that would be
//! truncated: `a30` alone has 22,281 expression datums against a cap of 64.

use std::collections::BTreeMap;

use blam_tag::data::{field_writes, Block, Value};
use blam_tag::layout::Layout;

use crate::expr::{DatumHandle, Expression, ValueTypes, DATUM_SIZE};
use crate::Error;

/// One entry of the scenario's `scripts` block.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Script {
    pub name: String,
    /// Index into the `script type` enum: `startup`, `dormant`, and so on.
    pub script_type: u16,
    /// Index into the value-type enum.
    pub return_type: u16,
    pub root: DatumHandle,
    pub parameters: Vec<Parameter>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Parameter {
    pub name: String,
    pub value_type: u16,
}

/// One entry of the scenario's `globals` block.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Global {
    pub name: String,
    pub value_type: u16,
    /// The expression evaluated to give this global its starting value.
    pub initializer: DatumHandle,
}

/// One `.hsc` file the mission was compiled from, kept verbatim in the tag.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceFile {
    pub name: String,
    /// The original text. Shipped as bytes; not guaranteed to be UTF-8, so it
    /// stays raw here and is decoded lossily at the edge.
    pub source: Vec<u8>,
    pub flags: u32,
}

impl SourceFile {
    /// The source as text, without the terminator the blob carries.
    ///
    /// Every shipped source file ends with a NUL. It is not whitespace, so a
    /// lexer that does not strip it reads it as part of a trailing word and the
    /// parser then reports a stray token at the end of every file.
    pub fn text(&self) -> std::borrow::Cow<'_, str> {
        let end = self
            .source
            .iter()
            .rposition(|b| *b != 0)
            .map_or(0, |i| i + 1);
        String::from_utf8_lossy(&self.source[..end])
    }
}

/// Everything a scenario carries about its scripting.
#[derive(Debug, Clone, Default)]
pub struct ScriptSection {
    /// The blob every node's `string_offset` points into.
    pub strings: Vec<u8>,
    /// The datum array, free slots included, at their original indices. Keeping
    /// the holes is what lets a handle be resolved by index.
    pub expressions: Vec<Expression>,
    pub scripts: Vec<Script>,
    pub globals: Vec<Global>,
    pub source_files: Vec<SourceFile>,
    /// Tags the scripts reference, in the order the `references` block lists.
    pub references: Vec<String>,
    /// The value-type enum as this build orders it.
    pub value_types: ValueTypes,
    /// The `script type` enum as this build orders it.
    pub script_types: ValueTypes,
    /// How each block this crate rewrites is laid out on disk. Empty for a
    /// section that was compiled rather than read from a tag.
    pub shapes: Shapes,
}

/// The on-disk shape of one block, learned from the tag rather than assumed.
///
/// Element width, the `tgst` flag and the definition's element cap are all
/// per-build facts. Writing a block back needs them, and hard-coding them here
/// would make the writer wrong the first time a game update changes one.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct BlockShape {
    /// Where the block's packed elements sit in the tag file. This is what
    /// identifies the block when substituting it.
    pub elements_at: usize,
    /// Where the enclosing element records how many elements this block has.
    ///
    /// A `block` field is twelve inline bytes and the first four are the count,
    /// duplicating the one in the `tgbl` header. Both have to move together: the
    /// reader here takes the header's, but leaving the inline copy stale would
    /// hand the engine a scenario claiming a different number of scripts than it
    /// has.
    pub count_at: usize,
    pub element_size: u32,
    /// The block header's second word: `0` means a `tgst` follows each element,
    /// `1` means none do.
    pub flags: u32,
    /// The most elements the definitions allow.
    pub max_count: u32,
}

impl BlockShape {
    /// Whether each element is followed by its own `tgst` wrapper.
    pub fn has_element_sections(&self) -> bool {
        self.flags == 0
    }
}

/// The shapes of every block and section the writer replaces.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Shapes {
    /// Offset of the `script string data` payload, which is a `tgda` rather
    /// than a block.
    pub strings_at: usize,
    /// Where the root element records the string blob's byte length. A `data`
    /// field's twenty inline bytes start with it.
    pub strings_size_at: usize,
    pub expressions: BlockShape,
    pub scripts: BlockShape,
    /// The `parameters` block nested in each `scripts` element.
    pub script_parameters: BlockShape,
    pub globals: BlockShape,
    pub source_files: BlockShape,
    /// The `external references` block nested in each `source files` element.
    pub source_file_references: BlockShape,
}

impl Shapes {
    /// Whether these came from a real tag and can be written back.
    pub fn are_known(&self) -> bool {
        self.expressions.element_size > 0
            && self.scripts.element_size > 0
            && self.globals.element_size > 0
    }
}

impl ScriptSection {
    /// Whether this scenario has any scripting at all.
    pub fn is_empty(&self) -> bool {
        self.scripts.is_empty() && self.globals.is_empty() && self.source_files.is_empty()
    }

    /// Live expressions, paired with their index in the datum array.
    pub fn live(&self) -> impl Iterator<Item = (usize, &Expression)> {
        self.expressions
            .iter()
            .enumerate()
            .filter(|(_, e)| !e.is_free())
    }

    /// Resolve a handle, checking the generation so a stale link reads as absent
    /// rather than as whatever now occupies the slot.
    pub fn get(&self, handle: DatumHandle) -> Option<&Expression> {
        if handle.is_null() {
            return None;
        }
        let e = self.expressions.get(handle.index())?;
        (!e.is_free() && e.generation == handle.generation()).then_some(e)
    }

    /// The NUL-terminated string at `offset` in the string blob.
    pub fn string_at(&self, offset: u32) -> &str {
        let start = offset as usize;
        let Some(rest) = self.strings.get(start..) else {
            return "";
        };
        let end = rest.iter().position(|c| *c == 0).unwrap_or(rest.len());
        std::str::from_utf8(&rest[..end]).unwrap_or("")
    }

    /// Walk a call's arguments: its first child, then each `next` in turn.
    ///
    /// The chain is followed with a step budget because a corrupt or
    /// hand-edited tag can make it circular, and a scenario is not a place to
    /// discover that by hanging.
    pub fn arguments(&self, call: &Expression) -> Vec<DatumHandle> {
        let mut out = Vec::new();
        let Some(mut cur) = call.first_child() else {
            return out;
        };
        let budget = self.expressions.len() + 1;
        for _ in 0..budget {
            let Some(e) = self.get(cur) else { break };
            out.push(cur);
            if e.next.is_null() {
                break;
            }
            cur = e.next;
        }
        out
    }

    /// A call node's callee name, read from the child that names it.
    pub fn callee_name(&self, call: &Expression) -> Option<&str> {
        let name_node = self.get(call.first_child()?)?;
        let name = self.string_at(name_node.string_offset);
        (!name.is_empty()).then_some(name)
    }
}

/// The option names of one enum field, read from the tag's own definitions.
fn options_of(layout: &Layout<'_>, struct_name: &str, field_name: &str) -> ValueTypes {
    let Some(index) = layout
        .structs
        .iter()
        .position(|s| layout.string_at(s.name_offset) == Some(struct_name))
    else {
        return ValueTypes::default();
    };
    let Some(run) = layout.struct_run(index) else {
        return ValueTypes::default();
    };
    let Some(range) = layout.struct_ranges().get(run).cloned() else {
        return ValueTypes::default();
    };
    for field in &layout.fields[range] {
        if layout.string_at(field.name_offset) != Some(field_name) {
            continue;
        }
        return ValueTypes::new(
            layout
                .field_options(field)
                .into_iter()
                .map(String::from)
                .collect(),
        );
    }
    ValueTypes::default()
}

/// The root block's top-level fields, by name.
///
/// Values arrive in the order the writing fields are declared, with phantom
/// entries the definitions do not name interleaved — the same pairing rule
/// [`blam_tag::view`] uses. Reimplementing it differently here would silently
/// pair values with the wrong fields.
fn top_level<'a, 'b>(
    layout: &Layout<'a>,
    block: &'b Block<'a>,
) -> BTreeMap<&'a str, &'b Value<'a>> {
    let mut out = BTreeMap::new();
    let Some(run) = layout.struct_run(block.struct_index) else {
        return out;
    };
    let Some(range) = layout.struct_ranges().get(run).cloned() else {
        return out;
    };
    let values = block.children.first().map(Vec::as_slice).unwrap_or(&[]);

    let mut next = 0usize;
    for index in range {
        let field = layout.fields[index];
        if !field_writes(layout, &field) {
            continue;
        }
        while matches!(values.get(next), Some(Value::Phantom)) {
            next += 1;
        }
        if let (Some(name), Some(value)) = (layout.string_at(field.name_offset), values.get(next)) {
            out.insert(name, value);
        }
        next += 1;
    }
    out
}

fn as_block<'a, 'b>(v: Option<&'b Value<'a>>) -> Option<&'b Block<'a>> {
    match v? {
        Value::Block(b) => Some(b),
        _ => None,
    }
}

fn as_data<'a>(v: Option<&Value<'a>>) -> Option<&'a [u8]> {
    match v? {
        Value::Data(d) => Some(*d),
        _ => None,
    }
}

/// Where `slice` sits inside `file`, if it is a view into it.
///
/// This is how a block or section is named when writing one back: the reader
/// hands out borrowed views, and their position in the original buffer is the
/// only stable identity they have. A slice from somewhere else reads as absent
/// rather than as a bogus offset.
fn offset_in(file: &[u8], slice: &[u8]) -> Option<usize> {
    let base = file.as_ptr() as usize;
    let at = slice.as_ptr() as usize;
    let end = at.checked_add(slice.len())?;
    (at >= base && end <= base + file.len()).then_some(at - base)
}

/// The definitions' cap on how many elements a named block of the root struct
/// may hold.
fn max_count_of(layout: &Layout<'_>, field_name: &str) -> u32 {
    let Some(root) = layout.root_struct() else {
        return 0;
    };
    let Some(run) = layout.struct_run(root) else {
        return 0;
    };
    let Some(range) = layout.struct_ranges().get(run).cloned() else {
        return 0;
    };
    for field in &layout.fields[range] {
        if layout.string_at(field.name_offset) != Some(field_name) {
            continue;
        }
        return layout
            .blocks
            .get(field.aux as usize)
            .map(|b| b.max_count)
            .unwrap_or(0);
    }
    0
}

/// Where a root-level field's inline bytes sit in the file.
fn inline_at(layout: &Layout<'_>, file: &[u8], block: &Block<'_>, field_name: &str) -> usize {
    blam_tag::patch::resolve(layout, file, block, field_name)
        .map(|t| t.file_offset)
        .unwrap_or(0)
}

/// The on-disk shape of one block.
fn shape_of(
    layout: &Layout<'_>,
    file: &[u8],
    block: &Block<'_>,
    field_name: &str,
    b: &Block<'_>,
) -> BlockShape {
    BlockShape {
        elements_at: offset_in(file, b.elements).unwrap_or(0),
        count_at: inline_at(layout, file, block, field_name),
        element_size: b.element_size,
        flags: b.flags,
        max_count: max_count_of(layout, field_name),
    }
}

/// A NUL-padded fixed-width string field.
fn fixed_string(bytes: &[u8]) -> String {
    let end = bytes.iter().position(|c| *c == 0).unwrap_or(bytes.len());
    String::from_utf8_lossy(&bytes[..end]).into_owned()
}

fn u16at(b: &[u8], o: usize) -> u16 {
    b.get(o..o + 2)
        .map(|s| u16::from_le_bytes([s[0], s[1]]))
        .unwrap_or(0)
}

fn u32at(b: &[u8], o: usize) -> u32 {
    b.get(o..o + 4)
        .map(|s| u32::from_le_bytes([s[0], s[1], s[2], s[3]]))
        .unwrap_or(0)
}

/// Read the script section from a scenario's decoded root block.
///
/// `file` must be the buffer `block` was decoded from. It is what the block
/// shapes are measured against, and those are what let a rewritten section be
/// put back in the right places; passing a different buffer leaves them zeroed
/// rather than wrong.
pub fn read(layout: &Layout<'_>, block: &Block<'_>, file: &[u8]) -> Result<ScriptSection, Error> {
    let fields = top_level(layout, block);

    let mut out = ScriptSection {
        value_types: options_of(layout, "hs_scripts_block", "return type"),
        script_types: options_of(layout, "hs_scripts_block", "script type"),
        ..ScriptSection::default()
    };

    let strings = as_data(fields.get("script string data").copied()).unwrap_or_default();
    out.strings = strings.to_vec();
    out.shapes.strings_at = offset_in(file, strings).unwrap_or(0);
    out.shapes.strings_size_at = inline_at(layout, file, block, "script string data");

    if let Some(b) = as_block(fields.get("hs syntax datums").copied()) {
        out.shapes.expressions = shape_of(layout, file, block, "hs syntax datums", b);
        if b.element_size as usize != DATUM_SIZE && b.count > 0 {
            return Err(Error::DatumSize(b.element_size as usize));
        }
        out.expressions.reserve(b.count as usize);
        for i in 0..b.count as usize {
            let el = b
                .element(i)
                .ok_or(Error::UnexpectedShape("hs syntax datums"))?;
            out.expressions.push(Expression::parse(el)?);
        }
    }

    if let Some(b) = as_block(fields.get("scripts").copied()) {
        out.shapes.scripts = shape_of(layout, file, block, "scripts", b);
        // The nested `parameters` block is only observable through an element,
        // so its shape comes from the first one that has it.
        if let Some(pb) = b.children.iter().flatten().find_map(|v| match v {
            Value::Block(pb) => Some(pb),
            _ => None,
        }) {
            out.shapes.script_parameters = BlockShape {
                elements_at: offset_in(file, pb.elements).unwrap_or(0),
                // The count lives inline in each script element, which this
                // writer builds itself rather than patching.
                count_at: 0,
                element_size: pb.element_size,
                flags: pb.flags,
                max_count: 0,
            };
        }
        for i in 0..b.count as usize {
            let el = b.element(i).ok_or(Error::UnexpectedShape("scripts"))?;
            let kids = b.children.get(i).map(Vec::as_slice).unwrap_or(&[]);
            // `name` is a string id, so its text arrives as a trailing section
            // rather than inline; `parameters` follows it.
            let name = kids
                .iter()
                .find_map(Value::as_str)
                .unwrap_or_default()
                .to_string();
            let parameters = kids
                .iter()
                .find_map(|v| match v {
                    Value::Block(pb) => Some(pb),
                    _ => None,
                })
                .map(|pb| {
                    (0..pb.count as usize)
                        .filter_map(|p| pb.element(p))
                        .map(|pe| Parameter {
                            name: fixed_string(&pe[..32.min(pe.len())]),
                            value_type: u16at(pe, 32),
                        })
                        .collect()
                })
                .unwrap_or_default();
            out.scripts.push(Script {
                name,
                script_type: u16at(el, 4),
                return_type: u16at(el, 6),
                root: DatumHandle(u32at(el, 8)),
                parameters,
            });
        }
    }

    if let Some(b) = as_block(fields.get("globals").copied()) {
        out.shapes.globals = shape_of(layout, file, block, "globals", b);
        for i in 0..b.count as usize {
            let el = b.element(i).ok_or(Error::UnexpectedShape("globals"))?;
            out.globals.push(Global {
                name: fixed_string(&el[..32.min(el.len())]),
                value_type: u16at(el, 32),
                initializer: DatumHandle(u32at(el, 36)),
            });
        }
    }

    if let Some(b) = as_block(fields.get("source files").copied()) {
        out.shapes.source_files = shape_of(layout, file, block, "source files", b);
        if let Some(rb) = b.children.iter().flatten().find_map(|v| match v {
            Value::Block(rb) => Some(rb),
            _ => None,
        }) {
            out.shapes.source_file_references = BlockShape {
                elements_at: offset_in(file, rb.elements).unwrap_or(0),
                count_at: 0,
                element_size: rb.element_size,
                flags: rb.flags,
                max_count: 0,
            };
        }
        for i in 0..b.count as usize {
            let el = b.element(i).ok_or(Error::UnexpectedShape("source files"))?;
            let kids = b.children.get(i).map(Vec::as_slice).unwrap_or(&[]);
            let source = kids
                .iter()
                .find_map(|v| match v {
                    Value::Data(d) => Some(d.to_vec()),
                    _ => None,
                })
                .unwrap_or_default();
            out.source_files.push(SourceFile {
                name: fixed_string(&el[..32.min(el.len())]),
                source,
                flags: u32at(el, 64),
            });
        }
    }

    if let Some(b) = as_block(fields.get("references").copied()) {
        for i in 0..b.count as usize {
            let kids = b.children.get(i).map(Vec::as_slice).unwrap_or(&[]);
            let path = kids
                .iter()
                .find_map(|v| match v {
                    Value::TagRef(r) => match blam_tag::value::reference(r) {
                        blam_tag::Scalar::Reference { path, .. } => Some(path),
                        _ => None,
                    },
                    _ => None,
                })
                .unwrap_or_default();
            out.references.push(path);
        }
    }

    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::expr::ExpressionType;

    fn section_with(exprs: Vec<Expression>, strings: &[u8]) -> ScriptSection {
        ScriptSection {
            expressions: exprs,
            strings: strings.to_vec(),
            ..ScriptSection::default()
        }
    }

    fn expr(generation: u16, ty: ExpressionType, next: DatumHandle, data: u32) -> Expression {
        Expression {
            generation,
            opcode: 0,
            value_type: 0,
            expression_type: ty,
            next,
            string_offset: 0,
            data,
            line: 0,
            tail: 0,
        }
    }

    fn free() -> Expression {
        Expression::parse(&{
            let mut b = [0xBAu8; DATUM_SIZE];
            b[0] = 0;
            b[1] = 0;
            b
        })
        .unwrap()
    }

    #[test]
    fn a_stale_handle_does_not_resolve_to_the_slots_new_tenant() {
        let s = section_with(
            vec![expr(
                0x1111,
                ExpressionType::Expression,
                DatumHandle::NULL,
                0,
            )],
            b"",
        );
        assert!(s.get(DatumHandle::new(0, 0x1111)).is_some());
        assert!(s.get(DatumHandle::new(0, 0x2222)).is_none());
        assert!(s.get(DatumHandle::NULL).is_none());
    }

    #[test]
    fn free_slots_keep_their_index_but_never_resolve() {
        let s = section_with(
            vec![
                free(),
                expr(0x1111, ExpressionType::Expression, DatumHandle::NULL, 0),
            ],
            b"",
        );
        assert_eq!(s.expressions.len(), 2);
        assert_eq!(s.live().count(), 1);
        assert_eq!(s.live().next().unwrap().0, 1);
        assert!(s.get(DatumHandle::new(0, 0)).is_none());
    }

    #[test]
    fn arguments_follow_the_sibling_chain_to_its_end() {
        let s = section_with(
            vec![
                expr(1, ExpressionType::Group, DatumHandle::NULL, 0x0002_0001),
                expr(2, ExpressionType::Expression, DatumHandle::new(2, 3), 0),
                expr(3, ExpressionType::Expression, DatumHandle::NULL, 0),
            ],
            b"",
        );
        let args = s.arguments(&s.expressions[0]);
        assert_eq!(args, vec![DatumHandle::new(1, 2), DatumHandle::new(2, 3)]);
    }

    #[test]
    fn a_circular_sibling_chain_terminates() {
        // A hand-edited tag can point a node's `next` back at itself.
        let s = section_with(
            vec![
                expr(1, ExpressionType::Group, DatumHandle::NULL, 0x0002_0001),
                expr(2, ExpressionType::Expression, DatumHandle::new(1, 2), 0),
            ],
            b"",
        );
        let args = s.arguments(&s.expressions[0]);
        assert_eq!(args.len(), s.expressions.len() + 1);
    }

    #[test]
    fn a_leaf_has_no_arguments() {
        let s = section_with(
            vec![expr(1, ExpressionType::Expression, DatumHandle::NULL, 42)],
            b"",
        );
        assert!(s.arguments(&s.expressions[0]).is_empty());
    }

    #[test]
    fn strings_are_read_to_their_terminator() {
        let s = section_with(Vec::new(), b"begin\0if\0");
        assert_eq!(s.string_at(0), "begin");
        assert_eq!(s.string_at(6), "if");
        // Past the end reads as absent rather than panicking.
        assert_eq!(s.string_at(999), "");
    }

    #[test]
    fn a_fixed_width_name_stops_at_its_padding() {
        assert_eq!(fixed_string(b"a30_start\0\0\0\0"), "a30_start");
        assert_eq!(fixed_string(b"unterminated"), "unterminated");
    }
}
