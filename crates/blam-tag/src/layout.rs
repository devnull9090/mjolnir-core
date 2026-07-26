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

use crate::section::{self, Section};

/// Offset of the first child section within `blay`'s content.
///
/// `blay` carries a fixed preamble before its children: `0xFFFFFFFF`, the ASCII
/// fill constants `4444`/`CCCC`/`wwww`, a per-group constant, and a table of
/// counts whose meaning is still unresolved.
const BLAY_PREAMBLE: usize = 0x4C;

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
    pub aux: [u32; 2],
}

/// A parsed `blay` layout section borrowed from the tag body.
#[derive(Debug)]
pub struct Layout<'a> {
    pub version: u32,
    pub size: u32,
    /// The `blay` preamble words at body `0x0C`..`0x58`, still uninterpreted.
    pub header_words: [u32; 16],
    /// NUL-separated UTF-8 string blob.
    pub blob: &'a [u8],
    /// String-blob offsets for every enum and bitfield option, in order.
    pub option_offsets: Vec<u32>,
    pub types: Vec<TypeEntry>,
    pub fields: Vec<FieldEntry>,
    pub blocks: Vec<BlockEntry>,
    pub structs: Vec<StructEntry>,
    /// Every child section of `tgly`, including ones not yet interpreted.
    pub sections: Vec<Section<'a>>,
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

        let mut header_words = [0u32; 16];
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

        // The option table follows the string blob. Its magic varies between
        // groups, so it is located positionally rather than by name.
        let mut option_offsets = Vec::new();
        if let Some(opts) = sections
            .iter()
            .find(|s| s.at == blob_section.at + blob_section.total())
        {
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
                        aux: [
                            u32::from_le_bytes(c[20..24].try_into().unwrap()),
                            u32::from_le_bytes(c[24..28].try_into().unwrap()),
                        ],
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
            sections,
        })
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

    /// Sum of every field's type size.
    ///
    /// Returns `None` if any field references a type outside the table. This is
    /// a flat sum and does not descend into blocks, so it is a lower bound on
    /// the real struct size rather than a final answer.
    pub fn flat_size(&self) -> Option<u32> {
        self.fields
            .iter()
            .try_fold(0u32, |acc, f| {
                self.types.get(f.type_index as usize).map(|t| acc + t.size)
            })
    }
}

#[cfg(test)]
mod tests {
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

    /// Mirrors the real camera_track layout: a control-points block holding a
    /// position and an orientation.
    fn synth_camera_track() -> Vec<u8> {
        let mut blob = Vec::new();
        for s in [
            "control points",
            "block",
            "position",
            "real vector 3d",
            "orientation",
            "real quaternion",
        ] {
            blob.extend_from_slice(s.as_bytes());
            blob.push(0);
        }
        // Offsets: control points 0, block 15, position 21, real vector 3d 30,
        // orientation 45, real quaternion 57.

        let mut tgly_content = section_bytes(b"*rts", 0, &blob);
        tgly_content.extend_from_slice(&section_bytes(b"sz+x", 0, &words(&[15, 21])));
        tgly_content.extend_from_slice(&section_bytes(
            b"tfgt",
            0,
            &words(&[15, 12, 1, 30, 12, 0, 57, 16, 0]),
        ));
        tgly_content.extend_from_slice(&section_bytes(
            b"sarg",
            0,
            &words(&[21, 1, 0, 45, 2, 0, 0, 0, 0]),
        ));
        tgly_content.extend_from_slice(&section_bytes(b"2vlb", 0, &words(&[0, 16, 1])));

        let mut blay_content = vec![0u8; BLAY_PREAMBLE];
        blay_content.extend_from_slice(&section_bytes(b"ylgt", 4, &tgly_content));
        section_bytes(b"yalb", 2, &blay_content)
    }

    #[test]
    fn parses_the_definition_tables() {
        let body = synth_camera_track();
        let l = Layout::parse(&body).unwrap();

        assert_eq!(l.version, 2);
        assert_eq!(l.strings().len(), 6);
        assert_eq!(l.options(), vec!["block", "position"]);

        assert_eq!(l.types.len(), 3);
        assert_eq!(l.string_at(l.types[0].name_offset), Some("block"));
        assert_eq!(l.types[0].size, 12);
        assert_eq!(l.types[2].size, 16);

        assert_eq!(l.fields.len(), 3);
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
    fn flat_size_sums_field_type_sizes() {
        let body = synth_camera_track();
        let l = Layout::parse(&body).unwrap();
        // position 12 + orientation 16 + control points block 12
        assert_eq!(l.flat_size(), Some(40));
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
