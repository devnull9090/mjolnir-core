//! Blam tag container header and self-describing `blay` layout section reader.
//!
//! Format is documented in `docs/tag_body_format.md`. Everything here is driven
//! by data shipped inside the tag itself; there are no hardcoded per-group
//! offsets and no hand-written per-group parsers.

use blam_defs::FourCc;

pub mod data;
pub mod layout;
pub mod section;
pub mod write;

pub use data::{Block, Value};
pub use layout::{
    ArrayEntry, BlockEntry, EnumEntry, FieldEntry, Layout, StructEntry, TypeEntry,
};
pub use section::Section;
pub use write::write_block;

/// Size of the `.ubulk` container header that precedes the tag body.
pub const HEADER_SIZE: usize = 0x4C;

const OFF_GROUP: usize = 0x30;
const OFF_GROUP_VERSION: usize = 0x34;
const OFF_TAG_ID: usize = 0x38;
const OFF_BLAM: usize = 0x3C;
const OFF_TAG_BANG: usize = 0x40;
const OFF_PAYLOAD_SIZE: usize = 0x48;

/// On-disk signature bytes. Both are stored reversed relative to reading order,
/// so `BLAM` appears as `M A L B` and `tag!` as `! g a t`.
const SIG_BLAM: [u8; 4] = *b"MALB";
const SIG_TAG_BANG: [u8; 4] = *b"!gat";

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("payload is {0} bytes, shorter than the {HEADER_SIZE}-byte container header")]
    TooShort(usize),
    #[error("missing BLAM signature at 0x3C (found {0:?})")]
    NotBlam([u8; 4]),
    #[error("missing tag! signature at 0x40 (found {0:?})")]
    NotTagBang([u8; 4]),
    #[error("declared payload size {declared} does not match chunk size {actual}")]
    SizeMismatch { declared: usize, actual: usize },
    #[error("layout section: {0}")]
    Layout(#[from] layout::Error),
    #[error("data section: {0}")]
    Data(#[from] data::Error),
    #[error("tag has no bdat data section")]
    NoData,
}

fn u32_at(buf: &[u8], off: usize) -> u32 {
    u32::from_le_bytes(buf[off..off + 4].try_into().unwrap())
}

fn sig_at(buf: &[u8], off: usize) -> [u8; 4] {
    buf[off..off + 4].try_into().unwrap()
}

/// The `0x4C`-byte container header wrapping every shipped tag payload.
#[derive(Debug, Clone, Copy)]
pub struct TagHeader {
    pub group: FourCc,
    /// Per-group definition version. Stable within a group, varies between.
    pub group_version: u32,
    /// Per-tag 32-bit value; differs between tags of the same group.
    pub tag_id: u32,
    pub payload_size: u32,
}

impl TagHeader {
    /// Parse and validate the container header.
    ///
    /// `chunk_len` is the full chunk length from the IoStore index and is used
    /// to check the documented `header + payload_size == chunk_size` invariant.
    /// Pass `None` when only a prefix of the chunk has been read.
    pub fn parse(buf: &[u8], chunk_len: Option<usize>) -> Result<Self, Error> {
        if buf.len() < HEADER_SIZE {
            return Err(Error::TooShort(buf.len()));
        }
        let blam = sig_at(buf, OFF_BLAM);
        if blam != SIG_BLAM {
            return Err(Error::NotBlam(blam));
        }
        let tag_bang = sig_at(buf, OFF_TAG_BANG);
        if tag_bang != SIG_TAG_BANG {
            return Err(Error::NotTagBang(tag_bang));
        }

        let payload_size = u32_at(buf, OFF_PAYLOAD_SIZE);
        if let Some(len) = chunk_len {
            if payload_size as usize + HEADER_SIZE != len {
                return Err(Error::SizeMismatch {
                    declared: payload_size as usize + HEADER_SIZE,
                    actual: len,
                });
            }
        }

        Ok(TagHeader {
            group: FourCc::from_le_u32(u32_at(buf, OFF_GROUP)),
            group_version: u32_at(buf, OFF_GROUP_VERSION),
            tag_id: u32_at(buf, OFF_TAG_ID),
            payload_size,
        })
    }
}

/// A shipped tag payload: container header plus the body that follows it.
#[derive(Debug)]
pub struct TagFile<'a> {
    pub header: TagHeader,
    /// Everything after the `0x4C`-byte container header.
    pub body: &'a [u8],
}

impl<'a> TagFile<'a> {
    pub fn parse(buf: &'a [u8], chunk_len: Option<usize>) -> Result<Self, Error> {
        let header = TagHeader::parse(buf, chunk_len)?;
        Ok(TagFile {
            header,
            body: &buf[HEADER_SIZE..],
        })
    }

    /// Parse the embedded `blay` layout section.
    pub fn layout(&self) -> Result<Layout<'a>, Error> {
        Ok(Layout::parse(self.body)?)
    }

    /// Top-level sections of the tag body, normally `blay` then `bdat`.
    pub fn sections(&self) -> Vec<Section<'a>> {
        section::walk(self.body, 0)
    }

    /// The `bdat` data section holding the tag's actual field values.
    ///
    /// `bdat` wraps a single `tgbl` child, mirroring how `blay` wraps `tgly`.
    /// The returned slice is the `tgbl` content.
    pub fn data(&self) -> Option<Section<'a>> {
        let sections = self.sections();
        let bdat = section::find(&sections, "bdat")?;
        section::read_at(bdat.content, 0).filter(|s| s.is("tgbl"))
    }

    /// Decode the data payload into a tree of blocks.
    ///
    /// The outermost block holds one element, the group's root struct.
    pub fn read_data(&self, layout: &Layout<'a>) -> Result<data::Block<'a>, Error> {
        let payload = self.data().ok_or(Error::NoData)?;
        // The root struct is struct-table index 0.
        Ok(data::read_block(layout, payload.content, 0)?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn synth_header(group_le: u32, version: u32, payload: u32) -> Vec<u8> {
        let mut b = vec![0u8; HEADER_SIZE];
        b[0x24..0x28].copy_from_slice(&1u32.to_le_bytes());
        b[0x28..0x2C].copy_from_slice(&2u32.to_le_bytes());
        b[0x2C..0x30].copy_from_slice(&0xFFFF_FFFFu32.to_le_bytes());
        b[OFF_GROUP..OFF_GROUP + 4].copy_from_slice(&group_le.to_le_bytes());
        b[OFF_GROUP_VERSION..OFF_GROUP_VERSION + 4].copy_from_slice(&version.to_le_bytes());
        b[OFF_BLAM..OFF_BLAM + 4].copy_from_slice(&SIG_BLAM);
        b[OFF_TAG_BANG..OFF_TAG_BANG + 4].copy_from_slice(&SIG_TAG_BANG);
        b[OFF_PAYLOAD_SIZE..OFF_PAYLOAD_SIZE + 4].copy_from_slice(&payload.to_le_bytes());
        b
    }

    #[test]
    fn parses_a_valid_header() {
        let buf = synth_header(0x7765_6170, 2, 0);
        let h = TagHeader::parse(&buf, Some(HEADER_SIZE)).unwrap();
        assert_eq!(h.group.as_str(), "weap");
        assert_eq!(h.group_version, 2);
        assert_eq!(h.payload_size, 0);
    }

    #[test]
    fn rejects_a_missing_blam_signature() {
        let mut buf = synth_header(0x7765_6170, 2, 0);
        buf[OFF_BLAM..OFF_BLAM + 4].copy_from_slice(b"zzzz");
        assert!(matches!(
            TagHeader::parse(&buf, None),
            Err(Error::NotBlam(_))
        ));
    }

    #[test]
    fn rejects_a_size_mismatch() {
        let buf = synth_header(0x7765_6170, 2, 999);
        assert!(matches!(
            TagHeader::parse(&buf, Some(HEADER_SIZE)),
            Err(Error::SizeMismatch { .. })
        ));
    }

    #[test]
    fn rejects_a_truncated_buffer() {
        assert!(matches!(
            TagHeader::parse(&[0u8; 8], None),
            Err(Error::TooShort(8))
        ));
    }
}
