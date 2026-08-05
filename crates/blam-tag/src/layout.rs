//! The `blay` layout section: a tag's own description of its fields.
//!
//! The tag body is a chain of sections (see [`crate::section`]). The first is
//! `blay`, the layout, and the second is `bdat`, the data. Inside `blay`:
//!
//! ```text
//! blay                       layout root, 0x4C bytes of preamble then children
//!   tgly                     container for the definition tables
//!     str*                   NUL-separated UTF-8 string blob
//!     <options>              enum and bitfield option name offsets
//!     tgft                   type table:   {name, size_bytes, flags}
//!     gras                   field list:   {name, type_index, aux}
//!     blv2                   block table:  {name, max_count, aux}
//!     stv4                   struct table: {guid[16], name, ...}
//! ```
//!
//! Everything is referenced by byte offset into the string blob rather than by
//! index, and the whole section is byte-packed, so offsets are frequently not
//! dword aligned.
//!
//! See `docs/tag_body_format.md` for evidence and reproduction.

use std::ops::Range;
use std::sync::OnceLock;

use crate::section::{self, Section};

/// Offset of the first child section within `blay`'s content.
///
/// `blay` carries a fixed preamble before its children: `0xFFFFFFFF`, the ASCII
/// fill constants `4444`/`CCCC`/`wwww`, a per-group constant, two words that
/// are still unidentified, and then one count per `tgly` child table.
const BLAY_PREAMBLE: usize = 0x4C;

/// The `tgly` child tables, in the order the `blay` preamble counts them, with
/// the on-disk width of one record. `str*` is counted in bytes rather than
/// records, so it carries a width of 1.
///
/// Indexed from [`Layout::PREAMBLE_COUNTS`].
pub const PREAMBLE_TABLES: [(&str, u32); 12] = [
    ("str*", 1),
    ("sz+x", 4),
    ("sz[]", 12),
    ("csbn", 4),
    ("dtnm", 4),
    ("arr!", 12),
    ("tgft", 12),
    ("gras", 12),
    ("stv4", 28),
    ("blv2", 12),
    ("rcv2", 12),
    ("]==[", 24),
];

/// Guard against a struct definition that references itself. Real definitions
/// nest far shallower than this; the limit exists only to stop a cycle.
const MAX_STRUCT_DEPTH: u32 = 128;

/// Type names whose size is not the value in the type table.
const PAD: &str = "pad";
const STRUCT: &str = "struct";
const ARRAY: &str = "array";
const BLOCK: &str = "block";
const TERMINATOR: &str = "terminator X";

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("body is {0} bytes, too short for a blay header")]
    TooShort(usize),
    #[error("expected a blay section at body 0x00, found {0:?}")]
    NotBlay(String),
    #[error("unsupported blay section version {0} (expected 2)")]
    BadVersion(u32),
    #[error("blay contains no tgly container")]
    NoTgly,
    #[error("tgly contains no str* string blob")]
    NoStringBlob,
}

/// An entry in the `tgft` type table.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TypeEntry {
    pub name_offset: u32,
    /// On-disk size of a value of this type, in bytes.
    pub size: u32,
    /// Non-zero for composite types such as `block`.
    pub flags: u32,
}

/// An entry in the `gras` field list.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FieldEntry {
    pub name_offset: u32,
    /// Index into the `tgft` type table.
    pub type_index: u32,
    pub aux: u32,
}

/// An entry in the `blv2` block table.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BlockEntry {
    pub name_offset: u32,
    /// Maximum element count Guerilla enforced for this block.
    pub max_count: u32,
    pub aux: u32,
}

/// An entry in the `stv4` struct table. Struct definitions carry a GUID, which
/// is characteristic of third-generation Blam tag definitions.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StructEntry {
    pub guid: [u8; 16],
    pub name_offset: u32,
    /// Index of this struct's first field in the `gras` list.
    ///
    /// This is the authoritative struct-to-field-run link. The field list is a
    /// flattened tree closed by `terminator X` entries, and `first_field` names
    /// the run start directly, so no ordering assumption is needed.
    pub first_field: u32,
    /// Trailing word. Zero in every shipped group.
    pub aux: u32,
}

/// An entry in the `arr!` array table.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ArrayEntry {
    pub name_offset: u32,
    /// Number of repetitions.
    pub count: u32,
    /// Index of the struct field run holding one element.
    pub struct_index: u32,
}

/// An entry in the `sz[]` enum and bitfield table.
///
/// `first_option` indexes the shared option table, and the runs tile it
/// exactly: each entry begins where the previous one ended.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EnumEntry {
    pub name_offset: u32,
    pub option_count: u32,
    pub first_option: u32,
}

/// A parsed `blay` layout section borrowed from the tag body.
#[derive(Debug)]
pub struct Layout<'a> {
    pub version: u32,
    pub size: u32,
    /// The `blay` preamble words, body `0x0C`..`0x58`.
    ///
    /// Words 0..4 are the fixed markers; words 5..18 are a table of counts and
    /// sizes for the definition tables that follow. See `docs/tag_body_format.md`.
    pub header_words: [u32; 19],
    /// NUL-separated UTF-8 string blob.
    pub blob: &'a [u8],
    /// String-blob offsets for every enum and bitfield option, in order.
    pub option_offsets: Vec<u32>,
    pub types: Vec<TypeEntry>,
    pub fields: Vec<FieldEntry>,
    pub blocks: Vec<BlockEntry>,
    pub structs: Vec<StructEntry>,
    pub arrays: Vec<ArrayEntry>,
    pub enums: Vec<EnumEntry>,
    /// Every child section of `tgly`, including ones not yet interpreted.
    pub sections: Vec<Section<'a>>,
    /// Cache for [`Layout::struct_ranges`], which every size and walk query
    /// hits repeatedly.
    runs: OnceLock<Vec<Range<usize>>>,
    /// Cache for [`Layout::struct_run`]: struct-table index to field run.
    runs_by_struct: OnceLock<Vec<Option<usize>>>,
}

impl<'a> Layout<'a> {
    pub fn parse(body: &'a [u8]) -> Result<Self, Error> {
        let blay = section::read_at(body, 0).ok_or(Error::TooShort(body.len()))?;
        if !blay.is("blay") {
            return Err(Error::NotBlay(blay.name()));
        }
        if blay.version != 2 {
            return Err(Error::BadVersion(blay.version));
        }

        let mut header_words = [0u32; 19];
        for (i, w) in header_words.iter_mut().enumerate() {
            if let Some(b) = blay.content.get(i * 4..i * 4 + 4) {
                *w = u32::from_le_bytes(b.try_into().unwrap());
            }
        }

        // blay's only child is the tgly container, after the fixed preamble.
        let tgly = section::read_at(blay.content, BLAY_PREAMBLE)
            .filter(|s| s.is("tgly"))
            .ok_or(Error::NoTgly)?;

        let sections = section::walk(tgly.content, 0);
        let blob_section = section::find(&sections, "str*").ok_or(Error::NoStringBlob)?;
        let blob = blob_section.content;

        // The option table is `sz+x` in all 101 shipped groups and always sits
        // directly after the string blob. Prefer the name, and fall back to the
        // position so a group that named it differently still resolves.
        let mut option_offsets = Vec::new();
        if let Some(opts) = section::find(&sections, "sz+x").or_else(|| {
            sections
                .iter()
                .find(|s| s.at == blob_section.at + blob_section.total())
                .copied()
        }) {
            option_offsets = opts
                .content
                .chunks_exact(4)
                .map(|c| u32::from_le_bytes(c.try_into().unwrap()))
                .collect();
        }

        let types = section::find(&sections, "tgft")
            .map(|s| {
                s.records::<3>()
                    .into_iter()
                    .map(|[name_offset, size, flags]| TypeEntry {
                        name_offset,
                        size,
                        flags,
                    })
                    .collect()
            })
            .unwrap_or_default();

        let fields = section::find(&sections, "gras")
            .map(|s| {
                s.records::<3>()
                    .into_iter()
                    .map(|[name_offset, type_index, aux]| FieldEntry {
                        name_offset,
                        type_index,
                        aux,
                    })
                    .collect()
            })
            .unwrap_or_default();

        let blocks = section::find(&sections, "blv2")
            .map(|s| {
                s.records::<3>()
                    .into_iter()
                    .map(|[name_offset, max_count, aux]| BlockEntry {
                        name_offset,
                        max_count,
                        aux,
                    })
                    .collect()
            })
            .unwrap_or_default();

        let structs = section::find(&sections, "stv4")
            .map(|s| {
                s.content
                    .chunks_exact(28)
                    .map(|c| StructEntry {
                        guid: c[0..16].try_into().unwrap(),
                        name_offset: u32::from_le_bytes(c[16..20].try_into().unwrap()),
                        first_field: u32::from_le_bytes(c[20..24].try_into().unwrap()),
                        aux: u32::from_le_bytes(c[24..28].try_into().unwrap()),
                    })
                    .collect()
            })
            .unwrap_or_default();

        let arrays = section::find(&sections, "arr!")
            .map(|s| {
                s.records::<3>()
                    .into_iter()
                    .map(|[name_offset, count, struct_index]| ArrayEntry {
                        name_offset,
                        count,
                        struct_index,
                    })
                    .collect()
            })
            .unwrap_or_default();

        let enums = section::find(&sections, "sz[]")
            .map(|s| {
                s.records::<3>()
                    .into_iter()
                    .map(|[name_offset, option_count, first_option]| EnumEntry {
                        name_offset,
                        option_count,
                        first_option,
                    })
                    .collect()
            })
            .unwrap_or_default();

        Ok(Layout {
            version: blay.version,
            size: blay.size,
            header_words,
            blob,
            option_offsets,
            types,
            fields,
            blocks,
            structs,
            arrays,
            enums,
            sections,
            runs: OnceLock::new(),
            runs_by_struct: OnceLock::new(),
        })
    }

    /// Index of the first `tgly` table count in [`Layout::header_words`].
    pub const PREAMBLE_COUNTS: usize = 7;

    /// The count the `blay` preamble declares for each `tgly` child table,
    /// paired with the count actually present in the section.
    ///
    /// The two agree for every shipped tag, which is what turns the preamble
    /// from an opaque blob into a checkable manifest.
    pub fn declared_vs_actual(&self) -> Vec<(&'static str, u32, u32)> {
        PREAMBLE_TABLES
            .iter()
            .enumerate()
            .map(|(i, (name, width))| {
                let declared = self
                    .header_words
                    .get(Self::PREAMBLE_COUNTS + i)
                    .copied()
                    .unwrap_or(0);
                let actual = section::find(&self.sections, name)
                    .map(|s| if *width <= 1 { s.size } else { s.size / width })
                    .unwrap_or(0);
                (*name, declared, actual)
            })
            .collect()
    }

    /// Resolve a string-blob byte offset to its NUL-terminated string.
    ///
    /// Returns `Some("")` when the offset points directly at a NUL, which the
    /// shipped data uses for unnamed fields.
    pub fn string_at(&self, offset: u32) -> Option<&'a str> {
        let start = offset as usize;
        if start >= self.blob.len() {
            return None;
        }
        let end = self.blob[start..]
            .iter()
            .position(|b| *b == 0)
            .map(|p| start + p)
            .unwrap_or(self.blob.len());
        std::str::from_utf8(&self.blob[start..end]).ok()
    }

    /// Every string in the blob, paired with its byte offset.
    pub fn strings(&self) -> Vec<(u32, &'a str)> {
        let mut out = Vec::new();
        let mut off = 0usize;
        while off < self.blob.len() {
            let end = self.blob[off..]
                .iter()
                .position(|b| *b == 0)
                .map(|p| off + p)
                .unwrap_or(self.blob.len());
            if let Ok(s) = std::str::from_utf8(&self.blob[off..end]) {
                out.push((off as u32, s));
            }
            off = end + 1;
        }
        out
    }

    /// Resolve the option table to strings, in declaration order.
    pub fn options(&self) -> Vec<&'a str> {
        self.option_offsets
            .iter()
            .filter_map(|o| self.string_at(*o))
            .collect()
    }

    /// Resolve a field to `(field name, type name, type size)`.
    pub fn field_info(&self, field: &FieldEntry) -> (&'a str, &'a str, Option<u32>) {
        let name = self.string_at(field.name_offset).unwrap_or("");
        match self.types.get(field.type_index as usize) {
            Some(t) => (
                name,
                self.string_at(t.name_offset).unwrap_or(""),
                Some(t.size),
            ),
            None => (name, "", None),
        }
    }

    /// The type name of a field, or `""` if its type index is out of range.
    pub fn type_name_of(&self, field: &FieldEntry) -> &'a str {
        self.types
            .get(field.type_index as usize)
            .and_then(|t| self.string_at(t.name_offset))
            .unwrap_or("")
    }

    /// Is this field the `terminator X` that closes a struct's field run?
    pub fn is_terminator(&self, field: &FieldEntry) -> bool {
        self.type_name_of(field) == TERMINATOR
    }

    /// The `block` fields directly declared by one struct run, in order.
    pub fn block_fields(&self, run: usize) -> Vec<FieldEntry> {
        let Some(range) = self.struct_ranges().get(run).cloned() else {
            return Vec::new();
        };
        self.fields[range]
            .iter()
            .filter(|f| self.type_name_of(f) == BLOCK)
            .copied()
            .collect()
    }

    /// Field index ranges, one per struct, in declaration order.
    ///
    /// The field list is a flattened tree: each struct's fields are emitted
    /// contiguously and closed by a `terminator X`. Structs appear innermost
    /// first, so the last range is the group's root struct.
    pub fn struct_ranges(&self) -> &[Range<usize>] {
        self.runs.get_or_init(|| {
            let mut out = Vec::new();
            let mut start = 0usize;
            for (i, f) in self.fields.iter().enumerate() {
                if self.is_terminator(f) {
                    out.push(start..i);
                    start = i + 1;
                }
            }
            out
        })
    }

    /// Map a struct-table index to its terminator-delimited field run.
    ///
    /// `stv4[i].first_field` names the run's first `gras` index directly, so the
    /// mapping is a lookup rather than an inference.
    ///
    /// An earlier revision assumed `stv4` was ordered root first while the field
    /// runs were emitted innermost first, and reversed the index. That holds
    /// only for groups whose structs happen to be declared in nesting order. In
    /// `shield_impact` the real run starts are `{14, 4, 0, 9}`, which the
    /// reversal maps to `{3, 2, 1, 0}` — right for the root and wrong for the
    /// other three, producing false cycles that hit the recursion guard.
    pub fn struct_run(&self, struct_index: usize) -> Option<usize> {
        *self.struct_run_map().get(struct_index)?
    }

    /// Struct-table index to field run, one slot per `stv4` entry.
    pub fn struct_run_map(&self) -> &[Option<usize>] {
        self.runs_by_struct.get_or_init(|| {
            let ranges = self.struct_ranges();
            self.structs
                .iter()
                .map(|s| ranges.iter().position(|r| r.start == s.first_field as usize))
                .collect()
        })
    }

    /// On-disk size of one field.
    ///
    /// Most types take their width from the type table. The exceptions are
    /// driven by the field's `aux` word: `pad` is `aux` bytes wide, `struct`
    /// inlines the struct at index `aux`, and `array` repeats an element
    /// struct `count` times.
    pub fn field_size(&self, field: &FieldEntry) -> Option<u32> {
        self.field_size_inner(field, self.struct_ranges(), 0)
    }

    fn field_size_inner(
        &self,
        field: &FieldEntry,
        ranges: &[Range<usize>],
        depth: u32,
    ) -> Option<u32> {
        if depth > MAX_STRUCT_DEPTH {
            return None;
        }
        let t = self.types.get(field.type_index as usize)?;
        match self.string_at(t.name_offset)? {
            PAD => Some(field.aux),
            STRUCT => {
                let run = self.struct_run(field.aux as usize)?;
                self.struct_size_inner(run, ranges, depth + 1)
            }
            ARRAY => {
                let a = self.arrays.get(field.aux as usize)?;
                let run = self.struct_run(a.struct_index as usize)?;
                let element = self.struct_size_inner(run, ranges, depth + 1)?;
                a.count.checked_mul(element)
            }
            _ => Some(t.size),
        }
    }

    /// Option names for an enum or bitfield field, in declaration order.
    ///
    /// Enum and flag fields carry an index into the `sz[]` table in `aux`, and
    /// that entry names a contiguous run of the shared option table.
    pub fn field_options(&self, field: &FieldEntry) -> Vec<&'a str> {
        let Some(e) = self.enums.get(field.aux as usize) else {
            return Vec::new();
        };
        let start = e.first_option as usize;
        let end = start + e.option_count as usize;
        self.option_offsets
            .get(start..end)
            .unwrap_or(&[])
            .iter()
            .filter_map(|o| self.string_at(*o))
            .collect()
    }

    /// Does this field's type carry named options?
    pub fn has_options(&self, field: &FieldEntry) -> bool {
        let name = self.type_name_of(field);
        name.ends_with(" enum") || name.ends_with(" flags")
    }

    /// Total on-disk size of the struct at `index`, summing its field run.
    pub fn struct_size(&self, index: usize) -> Option<u32> {
        self.struct_size_inner(index, self.struct_ranges(), 0)
    }

    fn struct_size_inner(
        &self,
        index: usize,
        ranges: &[Range<usize>],
        depth: u32,
    ) -> Option<u32> {
        if depth > MAX_STRUCT_DEPTH {
            return None;
        }
        let range = ranges.get(index)?.clone();
        self.fields[range].iter().try_fold(0u32, |acc, f| {
            Some(acc + self.field_size_inner(f, ranges, depth)?)
        })
    }

    /// The group's root struct, which is the last field run.
    pub fn root_struct(&self) -> Option<usize> {
        self.struct_ranges().len().checked_sub(1)
    }

    /// Sum of every field's type size.
    ///
    /// Returns `None` if any field references a type outside the table. This is
    /// a flat sum over the whole field list and does not respect struct
    /// boundaries, so it is a diagnostic rather than a real struct size.
    pub fn flat_size(&self) -> Option<u32> {
        self.fields
            .iter()
            .try_fold(0u32, |acc, f| {
                self.types.get(f.type_index as usize).map(|t| acc + t.size)
            })
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    pub(crate) fn section_bytes(magic: &[u8; 4], version: u32, content: &[u8]) -> Vec<u8> {
        let mut out = Vec::new();
        out.extend_from_slice(magic);
        out.extend_from_slice(&version.to_le_bytes());
        out.extend_from_slice(&(content.len() as u32).to_le_bytes());
        out.extend_from_slice(content);
        out
    }

    pub(crate) fn words(vals: &[u32]) -> Vec<u8> {
        vals.iter().flat_map(|v| v.to_le_bytes()).collect()
    }

    /// One 28-byte `stv4` record: a 16-byte GUID, then name, first_field, aux.
    fn struct_record(tag: u8, name_offset: u32, first_field: u32) -> Vec<u8> {
        let mut out = vec![tag; 16];
        out.extend_from_slice(&name_offset.to_le_bytes());
        out.extend_from_slice(&first_field.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out
    }

    /// Mirrors the real camera_track layout: a control-points block holding a
    /// position and an orientation.
    pub(crate) fn synth_camera_track() -> Vec<u8> {
        let mut blob = Vec::new();
        for s in [
            "control points",
            "block",
            "position",
            "real vector 3d",
            "orientation",
            "real quaternion",
            "terminator X",
            "pad",
            "struct",
        ] {
            blob.extend_from_slice(s.as_bytes());
            blob.push(0);
        }
        // Offsets: control points 0, block 15, position 21, real vector 3d 30,
        // orientation 45, real quaternion 57, terminator X 73, pad 86,
        // struct 90.

        let mut tgly_content = section_bytes(b"*rts", 0, &blob);
        tgly_content.extend_from_slice(&section_bytes(b"sz+x", 0, &words(&[15, 21])));
        // Types: 0 block/12, 1 vector3d/12, 2 quaternion/16, 3 terminator/0,
        //        4 pad/0, 5 struct/0
        tgly_content.extend_from_slice(&section_bytes(
            b"tfgt",
            0,
            &words(&[
                15, 12, 1, 30, 12, 0, 57, 16, 0, 73, 0, 0, 86, 0, 0, 90, 0, 0,
            ]),
        ));
        // Fields: position(v3), orientation(quat), TERM,
        //         control points(block), TERM
        tgly_content.extend_from_slice(&section_bytes(
            b"sarg",
            0,
            &words(&[21, 1, 0, 45, 2, 0, 0, 3, 0, 0, 0, 0, 0, 3, 0]),
        ));
        tgly_content.extend_from_slice(&section_bytes(b"2vlb", 0, &words(&[0, 16, 1])));
        // stv4 is ordered root first: [0] is the root run starting at field 3,
        // [1] is the control point run starting at field 0.
        let mut stv4 = struct_record(0xA0, 0, 3);
        stv4.extend_from_slice(&struct_record(0xB0, 0, 0));
        tgly_content.extend_from_slice(&section_bytes(b"4vts", 0, &stv4));

        let mut blay_content = vec![0u8; BLAY_PREAMBLE];
        blay_content.extend_from_slice(&section_bytes(b"ylgt", 4, &tgly_content));
        section_bytes(b"yalb", 2, &blay_content)
    }

    #[test]
    fn parses_the_definition_tables() {
        let body = synth_camera_track();
        let l = Layout::parse(&body).unwrap();

        assert_eq!(l.version, 2);
        assert_eq!(l.strings().len(), 9);
        assert_eq!(l.options(), vec!["block", "position"]);

        assert_eq!(l.types.len(), 6);
        assert_eq!(l.string_at(l.types[0].name_offset), Some("block"));
        assert_eq!(l.types[0].size, 12);
        assert_eq!(l.types[2].size, 16);

        assert_eq!(l.fields.len(), 5);
        assert_eq!(l.blocks.len(), 1);
        assert_eq!(l.blocks[0].max_count, 16);
    }

    #[test]
    fn field_info_joins_names_to_the_type_table() {
        let body = synth_camera_track();
        let l = Layout::parse(&body).unwrap();

        assert_eq!(
            l.field_info(&l.fields[0]),
            ("position", "real vector 3d", Some(12))
        );
        assert_eq!(
            l.field_info(&l.fields[1]),
            ("orientation", "real quaternion", Some(16))
        );
    }

    #[test]
    fn terminators_split_the_field_list_into_structs() {
        let body = synth_camera_track();
        let l = Layout::parse(&body).unwrap();

        // position+orientation close at field 2; control points closes at 4.
        assert_eq!(l.struct_ranges(), [0..2, 3..4]);
        // The root is the last run, and structs are emitted innermost first.
        assert_eq!(l.root_struct(), Some(1));
    }

    #[test]
    fn struct_size_sums_its_own_field_run_only() {
        let body = synth_camera_track();
        let l = Layout::parse(&body).unwrap();

        // Control point struct: vector3d 12 + quaternion 16.
        assert_eq!(l.struct_size(0), Some(28));
        // Root: a single 12-byte block field, not the block's contents.
        assert_eq!(l.struct_size(1), Some(12));
        assert_eq!(l.struct_size(99), None);
    }

    #[test]
    fn pad_takes_its_width_from_aux() {
        let body = synth_camera_track();
        let l = Layout::parse(&body).unwrap();
        // Type 4 is `pad`, whose table size is 0.
        let pad = FieldEntry {
            name_offset: 0,
            type_index: 4,
            aux: 24,
        };
        assert_eq!(l.field_size(&pad), Some(24));
    }

    #[test]
    fn struct_field_inlines_the_referenced_struct() {
        let body = synth_camera_track();
        let l = Layout::parse(&body).unwrap();
        // Type 5 is `struct`. Struct-table index 1 maps to the first field run
        // (the control point struct), because stv4 is ordered root first.
        let nested = FieldEntry {
            name_offset: 0,
            type_index: 5,
            aux: 1,
        };
        assert_eq!(l.field_size(&nested), Some(28));
        // Index 0 is the root run, a single 12-byte block field.
        let root = FieldEntry {
            name_offset: 0,
            type_index: 5,
            aux: 0,
        };
        assert_eq!(l.field_size(&root), Some(12));
    }

    #[test]
    fn struct_run_comes_from_first_field() {
        let body = synth_camera_track();
        let l = Layout::parse(&body).unwrap();
        // stv4[0].first_field is 3, which starts the second run; stv4[1] is 0.
        assert_eq!(l.structs[0].first_field, 3);
        assert_eq!(l.struct_run(0), Some(1));
        assert_eq!(l.struct_run(1), Some(0));
        assert_eq!(l.struct_run(9), None);
    }

    /// Regression: the mapping used to be inferred by reversing the struct
    /// table index, which only holds when structs happen to be declared in
    /// nesting order. Here they are not, and only `first_field` gets it right.
    #[test]
    fn struct_run_ignores_struct_table_order() {
        let mut blob = Vec::new();
        for s in ["terminator X", "long integer", "real"] {
            blob.extend_from_slice(s.as_bytes());
            blob.push(0);
        }
        // Offsets: terminator X 0, long integer 13, real 26.

        let mut tgly_content = section_bytes(b"*rts", 0, &blob);
        // Types: 0 terminator/0, 1 long integer/4, 2 real/4
        tgly_content.extend_from_slice(&section_bytes(
            b"tfgt",
            0,
            &words(&[0, 0, 0, 13, 4, 0, 26, 4, 0]),
        ));
        // Three runs of one field each: 0..0, 2..2, 4..4.
        tgly_content.extend_from_slice(&section_bytes(
            b"sarg",
            0,
            &words(&[13, 1, 0, 0, 0, 0, 13, 1, 0, 0, 0, 0, 26, 2, 0, 0, 0, 0]),
        ));
        // Declared out of nesting order: run starts 2, 4, 0.
        let mut stv4 = struct_record(0xA0, 0, 2);
        stv4.extend_from_slice(&struct_record(0xB0, 0, 4));
        stv4.extend_from_slice(&struct_record(0xC0, 0, 0));
        tgly_content.extend_from_slice(&section_bytes(b"4vts", 0, &stv4));

        let mut blay_content = vec![0u8; BLAY_PREAMBLE];
        blay_content.extend_from_slice(&section_bytes(b"ylgt", 4, &tgly_content));
        let body = section_bytes(b"yalb", 2, &blay_content);

        let l = Layout::parse(&body).unwrap();
        assert_eq!(l.struct_ranges(), [0..1, 2..3, 4..5]);
        assert_eq!(l.struct_run(0), Some(1));
        assert_eq!(l.struct_run(1), Some(2));
        assert_eq!(l.struct_run(2), Some(0));
        // The old reversal would have produced 2, 1, 0.
        assert_ne!(l.struct_run(0), Some(2));
    }

    #[test]
    fn array_size_is_count_times_element_struct() {
        let mut blob = Vec::new();
        for s in [
            "array",
            "terminator X",
            "long integer",
            "occupancy",
            "bitvector array",
        ] {
            blob.extend_from_slice(s.as_bytes());
            blob.push(0);
        }
        // Offsets: array 0, terminator X 6, long integer 19, occupancy 32,
        // bitvector array 42.

        let mut tgly_content = section_bytes(b"*rts", 0, &blob);
        // Types: 0 array/0, 1 terminator/0, 2 long integer/4
        tgly_content.extend_from_slice(&section_bytes(
            b"tfgt",
            0,
            &words(&[0, 0, 0, 6, 0, 0, 19, 4, 0]),
        ));
        // Struct 0 is one long integer; struct 1 holds the array field.
        tgly_content.extend_from_slice(&section_bytes(
            b"sarg",
            0,
            &words(&[32, 2, 0, 0, 1, 0, 32, 0, 0, 0, 1, 0]),
        ));
        // arr![0] = 8 repetitions of struct 0.
        tgly_content.extend_from_slice(&section_bytes(b"!rra", 0, &words(&[42, 8, 1])));
        // [0] is the root run starting at field 2, [1] the element run at 0.
        let mut stv4 = struct_record(0xA0, 0, 2);
        stv4.extend_from_slice(&struct_record(0xB0, 32, 0));
        tgly_content.extend_from_slice(&section_bytes(b"4vts", 0, &stv4));

        let mut blay_content = vec![0u8; BLAY_PREAMBLE];
        blay_content.extend_from_slice(&section_bytes(b"ylgt", 4, &tgly_content));
        let body = section_bytes(b"yalb", 2, &blay_content);

        let l = Layout::parse(&body).unwrap();
        assert_eq!(l.arrays.len(), 1);
        assert_eq!(l.arrays[0].count, 8);
        // 8 elements of one 4-byte long integer. struct_index 1 maps to run 0.
        assert_eq!(l.field_size(&l.fields[2]), Some(32));
    }

    #[test]
    fn enum_options_come_from_a_run_of_the_shared_table() {
        let mut blob = Vec::new();
        for s in [
            "short enum",
            "terminator X",
            "never",
            "always",
            "blur",
            "mode",
            "mode_enum",
        ] {
            blob.extend_from_slice(s.as_bytes());
            blob.push(0);
        }
        // Offsets: short enum 0, terminator X 11, never 24, always 30,
        // blur 37, mode 42, mode_enum 47.

        let mut tgly_content = section_bytes(b"*rts", 0, &blob);
        tgly_content.extend_from_slice(&section_bytes(b"sz+x", 0, &words(&[24, 30, 37])));
        tgly_content.extend_from_slice(&section_bytes(b"tfgt", 0, &words(&[0, 2, 0, 11, 0, 0])));
        // One short enum field with aux 0, then a terminator.
        tgly_content.extend_from_slice(&section_bytes(b"sarg", 0, &words(&[42, 0, 0, 0, 1, 0])));
        // sz![0] = 3 options starting at index 0.
        tgly_content.extend_from_slice(&section_bytes(b"][zs", 0, &words(&[47, 3, 0])));

        let mut blay_content = vec![0u8; BLAY_PREAMBLE];
        blay_content.extend_from_slice(&section_bytes(b"ylgt", 4, &tgly_content));
        let body = section_bytes(b"yalb", 2, &blay_content);

        let l = Layout::parse(&body).unwrap();
        assert_eq!(l.enums.len(), 1);
        assert!(l.has_options(&l.fields[0]));
        assert_eq!(l.field_options(&l.fields[0]), vec!["never", "always", "blur"]);
    }

    #[test]
    fn unnamed_fields_resolve_to_an_empty_string() {
        let body = synth_camera_track();
        let l = Layout::parse(&body).unwrap();
        // Offset 14 is the NUL terminating "control points".
        assert_eq!(l.string_at(14), Some(""));
    }

    #[test]
    fn rejects_a_body_that_is_not_blay() {
        let mut body = synth_camera_track();
        body[0..4].copy_from_slice(b"zzzz");
        assert!(matches!(Layout::parse(&body), Err(Error::NotBlay(_))));
    }

    #[test]
    fn rejects_an_unsupported_version() {
        let mut body = synth_camera_track();
        body[4..8].copy_from_slice(&9u32.to_le_bytes());
        assert!(matches!(Layout::parse(&body), Err(Error::BadVersion(9))));
    }
}
