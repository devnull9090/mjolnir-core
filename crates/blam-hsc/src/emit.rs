//! Serialise a script section back into the bytes a scenario tag holds.
//!
//! The inverse of [`crate::read`], and the last step before an edited script is
//! something the game runs. Four things are rewritten:
//!
//! | Field | Section | Why it moves |
//! |---|---|---|
//! | `script string data` | `tgda` | every name and string literal |
//! | `hs syntax datums` | `tgbl` | the expression tree |
//! | `scripts` | `tgbl` | declarations and their roots |
//! | `globals` | `tgbl` | declarations and their initializers |
//!
//! Everything else in the scenario is left exactly as it was, which is both the
//! smaller change and the checkable one: writing a section that was read and not
//! modified must reproduce the original bytes, and
//! `mjolnir script --rewrite-check` asserts that over every shipped scenario.
//!
//! Element widths and the `tgst` flag are not hard-coded here. They come from
//! [`crate::read::Shapes`], measured off the tag being written, so a game update
//! that changes one is a value that moves rather than a constant that rots.

use crate::expr::DATUM_SIZE;
use crate::read::{BlockShape, ScriptSection, Shapes};
use crate::Error;

/// A block's serialised `tgbl` content, and where it goes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BlockBytes {
    /// Offset of the original block's packed elements, which names the block.
    pub at: usize,
    /// `count | flags | elements | per-element tgst`.
    pub content: Vec<u8>,
}

/// Everything a rewritten script section replaces.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SectionBytes {
    /// Offset and content of the `script string data` payload.
    pub strings_at: usize,
    pub strings: Vec<u8>,
    pub blocks: Vec<BlockBytes>,
}

/// The `tgst` section header, which the block writer emits per element.
const SECTION_HEADER: usize = 12;

fn section(out: &mut Vec<u8>, magic: &str, version: u32, content: &[u8]) {
    out.extend(magic.bytes().rev());
    out.extend_from_slice(&version.to_le_bytes());
    out.extend_from_slice(&(content.len() as u32).to_le_bytes());
    out.extend_from_slice(content);
}

/// Start a block's content: the count and flags header.
fn block_header(count: usize, shape: &BlockShape) -> Vec<u8> {
    let mut out = Vec::with_capacity(8 + count * shape.element_size as usize);
    out.extend_from_slice(&(count as u32).to_le_bytes());
    out.extend_from_slice(&shape.flags.to_le_bytes());
    out
}

fn check_count(count: usize, shape: &BlockShape, what: &'static str) -> Result<(), Error> {
    if shape.max_count > 0 && count > shape.max_count as usize {
        return Err(Error::TooManyElements {
            what,
            count,
            max: shape.max_count,
        });
    }
    Ok(())
}

/// A NUL-padded fixed-width name, truncated to fit rather than overrunning the
/// field and corrupting whatever follows it.
fn fixed_name(name: &str, width: usize) -> Vec<u8> {
    let mut out = vec![0u8; width];
    let bytes = name.as_bytes();
    // One byte is kept for the terminator so a name that exactly fills the
    // field still reads back as a terminated string.
    let n = bytes.len().min(width.saturating_sub(1));
    out[..n].copy_from_slice(&bytes[..n]);
    out
}

/// Serialise the whole script section.
pub fn emit(section: &ScriptSection, shapes: &Shapes) -> Result<SectionBytes, Error> {
    if !shapes.are_known() {
        return Err(Error::UnknownShapes);
    }
    Ok(SectionBytes {
        strings_at: shapes.strings_at,
        strings: section.strings.clone(),
        blocks: vec![
            BlockBytes {
                at: shapes.expressions.elements_at,
                content: expressions(section, &shapes.expressions)?,
            },
            BlockBytes {
                at: shapes.scripts.elements_at,
                content: scripts(section, shapes)?,
            },
            BlockBytes {
                at: shapes.globals.elements_at,
                content: globals(section, &shapes.globals)?,
            },
            BlockBytes {
                at: shapes.source_files.elements_at,
                content: source_files(section, shapes)?,
            },
        ],
    })
}

/// `source files`: the `.hsc` text the tree was compiled from.
///
/// Rewritten along with the tree so the two cannot drift. A scenario whose
/// source says one thing and whose tree does another is exactly the state that
/// makes 45 of the shipped scripts impossible to explain.
fn source_files(s: &ScriptSection, shapes: &Shapes) -> Result<Vec<u8>, Error> {
    let shape = &shapes.source_files;
    if shape.element_size == 0 {
        return Err(Error::UnexpectedShape(
            "the source files block has no shape",
        ));
    }
    check_count(s.source_files.len(), shape, "source files")?;

    let width = shape.element_size as usize;
    let mut out = block_header(s.source_files.len(), shape);
    for f in &s.source_files {
        let start = out.len();
        out.resize(start + width, 0);
        let e = &mut out[start..];
        // name(32) | source: data(20) | external references: block(12) | flags
        e[..32].copy_from_slice(&fixed_name(&f.name, 32));
        e[32..36].copy_from_slice(&(f.source.len() as u32).to_le_bytes());
        // A `data` field's inline bytes carry a null handle where the runtime
        // pointer goes; the shipped tags all hold `0xFFFFFFFF` there.
        e[40..44].copy_from_slice(&u32::MAX.to_le_bytes());
        e[64..68].copy_from_slice(&f.flags.to_le_bytes());
    }

    if !shape.has_element_sections() {
        return Err(Error::UnexpectedShape(
            "the source files block has no element sections",
        ));
    }
    for f in &s.source_files {
        let mut children = Vec::new();
        section(&mut children, "tgda", 0, &f.source);
        let mut refs = Vec::new();
        refs.extend_from_slice(&0u32.to_le_bytes());
        refs.extend_from_slice(&shapes.source_file_references.flags.to_le_bytes());
        section(&mut children, "tgbl", 0, &refs);
        section(&mut out, "tgst", children.len() as u32, &children);
    }
    Ok(out)
}

/// `hs syntax datums`: a flat array of 24-byte datums, no per-element section.
fn expressions(s: &ScriptSection, shape: &BlockShape) -> Result<Vec<u8>, Error> {
    if (shape.element_size as usize) < DATUM_SIZE {
        return Err(Error::DatumSize(shape.element_size as usize));
    }
    check_count(s.expressions.len(), shape, "expressions")?;

    let mut out = block_header(s.expressions.len(), shape);
    for e in &s.expressions {
        let start = out.len();
        out.resize(start + shape.element_size as usize, 0);
        e.write(&mut out[start..])?;
    }
    debug_assert!(!shape.has_element_sections(), "datums carry no tgst");
    Ok(out)
}

/// `globals`: name, type, and the handle of the initializer expression.
fn globals(s: &ScriptSection, shape: &BlockShape) -> Result<Vec<u8>, Error> {
    check_count(s.globals.len(), shape, "globals")?;
    let width = shape.element_size as usize;
    let mut out = block_header(s.globals.len(), shape);

    for g in &s.globals {
        let start = out.len();
        out.resize(start + width, 0);
        let e = &mut out[start..];
        // A `string` field is inline and fixed-width; the layout puts the type
        // at 32 and the initializer handle at 36.
        e[..32].copy_from_slice(&fixed_name(&g.name, 32));
        e[32..34].copy_from_slice(&g.value_type.to_le_bytes());
        e[36..40].copy_from_slice(&g.initializer.0.to_le_bytes());
    }
    Ok(out)
}

/// `scripts`: the packed elements, then one `tgst` per element holding the
/// name's `tgsi` and the parameters block.
fn scripts(s: &ScriptSection, shapes: &Shapes) -> Result<Vec<u8>, Error> {
    let shape = &shapes.scripts;
    check_count(s.scripts.len(), shape, "scripts")?;
    let width = shape.element_size as usize;
    let mut out = block_header(s.scripts.len(), shape);

    for script in &s.scripts {
        let start = out.len();
        out.resize(start + width, 0);
        let e = &mut out[start..];
        // `name` is a string id, so its bytes live in a trailing section and
        // the inline handle stays zero; the rest is packed here.
        e[4..6].copy_from_slice(&script.script_type.to_le_bytes());
        e[6..8].copy_from_slice(&script.return_type.to_le_bytes());
        e[8..12].copy_from_slice(&script.root.0.to_le_bytes());
        // The `parameters` block field is twelve inline bytes from offset 12,
        // and the first four are how many parameters there are.
        e[12..16].copy_from_slice(&(script.parameters.len() as u32).to_le_bytes());
    }

    if !shape.has_element_sections() {
        // Without wrappers there is nowhere to put a name or a parameter, so a
        // scenario shaped like that is one this writer does not understand.
        return Err(Error::UnexpectedShape(
            "scripts block has no element sections",
        ));
    }

    for script in &s.scripts {
        let mut children = Vec::new();
        section(&mut children, "tgsi", 0, script.name.as_bytes());
        section(
            &mut children,
            "tgbl",
            0,
            &parameters(&script.parameters, &shapes.script_parameters)?,
        );
        section(&mut out, "tgst", children.len() as u32, &children);
    }
    Ok(out)
}

/// The `parameters` block nested in one script element.
fn parameters(params: &[crate::read::Parameter], shape: &BlockShape) -> Result<Vec<u8>, Error> {
    // A scenario whose every script is parameterless never shows this block's
    // shape, so writing parameters into it would be guesswork.
    if params.is_empty() {
        let mut out = Vec::with_capacity(8);
        out.extend_from_slice(&0u32.to_le_bytes());
        out.extend_from_slice(&shape.flags.to_le_bytes());
        return Ok(out);
    }
    if shape.element_size == 0 {
        return Err(Error::UnexpectedShape(
            "the parameters block's shape is unknown; no shipped script declares one",
        ));
    }

    let width = shape.element_size as usize;
    let mut out = block_header(params.len(), shape);
    for p in params {
        let start = out.len();
        out.resize(start + width, 0);
        let e = &mut out[start..];
        e[..32].copy_from_slice(&fixed_name(&p.name, 32));
        e[32..34].copy_from_slice(&p.value_type.to_le_bytes());
    }
    if shape.has_element_sections() {
        for _ in params {
            section(&mut out, "tgst", 0, &[]);
        }
    }
    Ok(out)
}

/// Turn emitted bytes into the edit set `blam_tag` applies.
///
/// As well as the new section contents this carries the in-place fixes for the
/// counts the *enclosing* element duplicates. A block field holds its element
/// count inline and a data field holds its byte length; resizing either without
/// updating those leaves the scenario describing itself wrongly.
pub fn as_edits<'a>(
    bytes: &SectionBytes,
    section: &ScriptSection,
    file: &'a [u8],
) -> blam_tag::write::Edits<'a> {
    let mut edits = blam_tag::write::Edits::new(file);
    edits
        .sections
        .insert(bytes.strings_at, bytes.strings.clone());
    for b in &bytes.blocks {
        edits.blocks.insert(b.at, b.content.clone());
    }

    let shapes = &section.shapes;
    let mut inline = |at: usize, value: usize| {
        if at != 0 {
            edits
                .inline
                .insert(at, (value as u32).to_le_bytes().to_vec());
        }
    };
    inline(shapes.strings_size_at, section.strings.len());
    inline(shapes.expressions.count_at, section.expressions.len());
    inline(shapes.scripts.count_at, section.scripts.len());
    inline(shapes.globals.count_at, section.globals.len());
    inline(shapes.source_files.count_at, section.source_files.len());
    edits
}

/// Rewrite a scenario tag with this script section in place of its own.
pub fn rewrite(section: &ScriptSection, file: &[u8]) -> Result<Vec<u8>, Error> {
    let bytes = emit(section, &section.shapes)?;
    let edits = as_edits(&bytes, section, file);
    blam_tag::patch::rewrite(file, &edits).map_err(|e| Error::Rewrite(e.to_string()))
}

/// Bytes a serialised section will occupy, for reporting.
pub fn size_of(bytes: &SectionBytes) -> usize {
    bytes.strings.len()
        + bytes
            .blocks
            .iter()
            .map(|b| b.content.len() + SECTION_HEADER)
            .sum::<usize>()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::expr::{DatumHandle, Expression, ExpressionType};
    use crate::read::{Global, Parameter, Script};

    fn shapes() -> Shapes {
        Shapes {
            strings_at: 100,
            strings_size_at: 10100,
            expressions: BlockShape {
                elements_at: 200,
                count_at: 10200,
                element_size: 24,
                flags: 1,
                max_count: 64512,
            },
            scripts: BlockShape {
                elements_at: 300,
                count_at: 10300,
                element_size: 24,
                flags: 0,
                max_count: 2048,
            },
            script_parameters: BlockShape {
                elements_at: 400,
                count_at: 10400,
                element_size: 36,
                flags: 1,
                max_count: 8,
            },
            source_files: BlockShape {
                elements_at: 600,
                count_at: 10600,
                element_size: 68,
                flags: 0,
                max_count: 16,
            },
            source_file_references: BlockShape {
                elements_at: 700,
                count_at: 0,
                element_size: 16,
                flags: 0,
                max_count: 512,
            },
            globals: BlockShape {
                elements_at: 500,
                count_at: 10500,
                element_size: 40,
                flags: 1,
                max_count: 512,
            },
        }
    }

    fn section_with(scripts: Vec<Script>, globals: Vec<Global>) -> ScriptSection {
        ScriptSection {
            strings: b"\0begin\0".to_vec(),
            expressions: vec![Expression {
                generation: 0xE373,
                opcode: 0,
                value_type: 4,
                expression_type: ExpressionType::Group,
                next: DatumHandle::NULL,
                string_offset: 0,
                data: 0,
                line: 1,
                tail: 0,
            }],
            scripts,
            globals,
            ..ScriptSection::default()
        }
    }

    fn u32at(b: &[u8], o: usize) -> u32 {
        u32::from_le_bytes([b[o], b[o + 1], b[o + 2], b[o + 3]])
    }

    #[test]
    fn a_section_with_no_shapes_cannot_be_written() {
        let s = section_with(Vec::new(), Vec::new());
        assert!(matches!(
            emit(&s, &Shapes::default()),
            Err(Error::UnknownShapes)
        ));
    }

    #[test]
    fn each_block_is_addressed_by_where_its_elements_were() {
        let s = section_with(Vec::new(), Vec::new());
        let out = emit(&s, &shapes()).unwrap();
        assert_eq!(out.strings_at, 100);
        let ats: Vec<usize> = out.blocks.iter().map(|b| b.at).collect();
        assert_eq!(ats, vec![200, 300, 500, 600]);
    }

    #[test]
    fn the_datum_block_is_a_header_then_packed_elements() {
        let s = section_with(Vec::new(), Vec::new());
        let out = emit(&s, &shapes()).unwrap();
        let datums = &out.blocks[0].content;
        assert_eq!(u32at(datums, 0), 1, "count");
        assert_eq!(u32at(datums, 4), 1, "flags: no tgst per element");
        assert_eq!(datums.len(), 8 + 24);
    }

    #[test]
    fn a_global_writes_its_name_type_and_initializer() {
        let s = section_with(
            Vec::new(),
            vec![Global {
                name: "b_awake".into(),
                value_type: 5,
                initializer: DatumHandle::new(7, 0xE37A),
            }],
        );
        let out = emit(&s, &shapes()).unwrap();
        let g = &out.blocks[2].content;
        assert_eq!(u32at(g, 0), 1);
        let element = &g[8..48];
        assert_eq!(&element[..7], b"b_awake");
        assert_eq!(element[7], 0, "the name is NUL-terminated");
        assert_eq!(u16::from_le_bytes([element[32], element[33]]), 5);
        assert_eq!(u32at(element, 36), DatumHandle::new(7, 0xE37A).0);
    }

    #[test]
    fn a_script_writes_a_tgst_per_element_holding_its_name() {
        let s = section_with(
            vec![Script {
                name: "on_wake".into(),
                script_type: 1,
                return_type: 4,
                root: DatumHandle::new(0, 0xE373),
                parameters: Vec::new(),
            }],
            Vec::new(),
        );
        let out = emit(&s, &shapes()).unwrap();
        let sc = &out.blocks[1].content;
        assert_eq!(u32at(sc, 0), 1);
        assert_eq!(u32at(sc, 4), 0, "flags: a tgst follows each element");

        let element = &sc[8..32];
        assert_eq!(u16::from_le_bytes([element[4], element[5]]), 1, "kind");
        assert_eq!(u16::from_le_bytes([element[6], element[7]]), 4, "return");
        assert_eq!(u32at(element, 8), DatumHandle::new(0, 0xE373).0);

        // `tgst` wrapper, then `tgsi` with the name, then the parameters `tgbl`.
        let wrapper = &sc[32..];
        assert_eq!(&wrapper[..4], b"tsgt");
        let inner = &wrapper[12..];
        assert_eq!(&inner[..4], b"isgt");
        let name_len = u32at(inner, 8) as usize;
        assert_eq!(&inner[12..12 + name_len], b"on_wake");
    }

    #[test]
    fn parameters_are_written_with_their_names_and_types() {
        let s = section_with(
            vec![Script {
                name: "f_a".into(),
                script_type: 3,
                return_type: 4,
                root: DatumHandle::NULL,
                parameters: vec![
                    Parameter {
                        name: "delay".into(),
                        value_type: 7,
                    },
                    Parameter {
                        name: "who".into(),
                        value_type: 19,
                    },
                ],
            }],
            Vec::new(),
        );
        let out = emit(&s, &shapes()).unwrap();
        let sc = &out.blocks[1].content;
        // Past the element and the tgst + tgsi headers to the parameters tgbl.
        let at = sc.windows(4).position(|w| w == b"lbgt").expect("a tgbl");
        let params = &sc[at + 12..];
        assert_eq!(u32at(params, 0), 2, "two parameters");
        assert_eq!(&params[8..13], b"delay");
        assert_eq!(u16::from_le_bytes([params[40], params[41]]), 7);
        assert_eq!(&params[44..47], b"who");
    }

    #[test]
    fn a_name_too_long_for_its_field_is_truncated_not_overrun() {
        let long = "x".repeat(200);
        let s = section_with(
            Vec::new(),
            vec![Global {
                name: long,
                value_type: 5,
                initializer: DatumHandle::NULL,
            }],
        );
        let out = emit(&s, &shapes()).unwrap();
        let element = &out.blocks[2].content[8..48];
        assert_eq!(element[31], 0, "still terminated inside the field");
        assert_eq!(&element[..31], "x".repeat(31).as_bytes());
    }

    #[test]
    fn exceeding_the_definitions_element_cap_is_an_error() {
        let mut shapes = shapes();
        shapes.globals.max_count = 2;
        let s = section_with(
            Vec::new(),
            (0..3)
                .map(|i| Global {
                    name: format!("g{i}"),
                    value_type: 5,
                    initializer: DatumHandle::NULL,
                })
                .collect(),
        );
        assert!(matches!(
            emit(&s, &shapes),
            Err(Error::TooManyElements {
                what: "globals",
                count: 3,
                max: 2
            })
        ));
    }

    #[test]
    fn writing_parameters_without_a_known_shape_is_refused() {
        let mut shapes = shapes();
        shapes.script_parameters.element_size = 0;
        let s = section_with(
            vec![Script {
                name: "f_a".into(),
                script_type: 3,
                return_type: 4,
                root: DatumHandle::NULL,
                parameters: vec![Parameter {
                    name: "n".into(),
                    value_type: 7,
                }],
            }],
            Vec::new(),
        );
        assert!(matches!(emit(&s, &shapes), Err(Error::UnexpectedShape(_))));
    }
}
