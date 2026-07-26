//! Generic section walker.
//!
//! The whole tag file is built from one repeating shape: a 12-byte header of
//! `{magic: [u8; 4], version: u32, size: u32}` followed by `size` bytes of
//! content. `size` excludes the header. Sections chain as siblings and nest as
//! children, and the same shape is used at every level from the outermost
//! `blay` down to the individual definition tables.
//!
//! Magics are stored reversed, so `blay` appears on disk as the bytes `y a l b`.
//! [`Section::name`] reverses them back into reading order.

/// Bytes of a section header, excluding content.
pub const SECTION_HEADER: usize = 12;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Section<'a> {
    /// Raw on-disk magic bytes, in stored (reversed) order.
    pub magic: [u8; 4],
    pub version: u32,
    /// Content length in bytes, excluding the 12-byte header.
    pub size: u32,
    /// Offset of the section header within the buffer it was read from.
    pub at: usize,
    pub content: &'a [u8],
}

impl<'a> Section<'a> {
    /// The magic in reading order, e.g. `blay`.
    pub fn name(&self) -> String {
        self.magic
            .iter()
            .rev()
            .map(|b| {
                if (32..127).contains(b) {
                    *b as char
                } else {
                    '.'
                }
            })
            .collect()
    }

    /// Does this section's magic read as `want`?
    pub fn is(&self, want: &str) -> bool {
        self.name() == want
    }

    /// Total bytes occupied, header included.
    pub fn total(&self) -> usize {
        SECTION_HEADER + self.size as usize
    }

    /// Interpret the content as fixed-size records of `n` little-endian u32s.
    pub fn records<const N: usize>(&self) -> Vec<[u32; N]> {
        self.content
            .chunks_exact(N * 4)
            .map(|chunk| {
                let mut out = [0u32; N];
                for (i, slot) in out.iter_mut().enumerate() {
                    *slot = u32::from_le_bytes(chunk[i * 4..i * 4 + 4].try_into().unwrap());
                }
                out
            })
            .collect()
    }
}

/// Read a single section header at `off`, if one is present and in bounds.
pub fn read_at(buf: &[u8], off: usize) -> Option<Section<'_>> {
    let head = buf.get(off..off + SECTION_HEADER)?;
    let magic: [u8; 4] = head[0..4].try_into().unwrap();
    // A plausible magic is four printable bytes.
    if !magic.iter().all(|b| (32..127).contains(b)) {
        return None;
    }
    let version = u32::from_le_bytes(head[4..8].try_into().unwrap());
    let size = u32::from_le_bytes(head[8..12].try_into().unwrap());
    let start = off + SECTION_HEADER;
    let content = buf.get(start..start + size as usize)?;
    Some(Section {
        magic,
        version,
        size,
        at: off,
        content,
    })
}

/// Walk a chain of sibling sections starting at `off`, stopping at the first
/// position that is not a valid section header.
pub fn walk(buf: &[u8], off: usize) -> Vec<Section<'_>> {
    let mut out = Vec::new();
    let mut pos = off;
    while let Some(section) = read_at(buf, pos) {
        pos += section.total();
        out.push(section);
    }
    out
}

/// Find the first section in a chain whose magic reads as `name`.
pub fn find<'a>(sections: &[Section<'a>], name: &str) -> Option<Section<'a>> {
    sections.iter().find(|s| s.is(name)).copied()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn build(magic: &[u8; 4], version: u32, content: &[u8]) -> Vec<u8> {
        let mut out = Vec::new();
        out.extend_from_slice(magic);
        out.extend_from_slice(&version.to_le_bytes());
        out.extend_from_slice(&(content.len() as u32).to_le_bytes());
        out.extend_from_slice(content);
        out
    }

    #[test]
    fn name_reverses_the_stored_magic() {
        let buf = build(b"yalb", 2, &[]);
        let s = read_at(&buf, 0).unwrap();
        assert_eq!(s.name(), "blay");
        assert!(s.is("blay"));
    }

    #[test]
    fn size_excludes_the_header() {
        let buf = build(b"tfgt", 0, &[0u8; 48]);
        let s = read_at(&buf, 0).unwrap();
        assert_eq!(s.size, 48);
        assert_eq!(s.total(), 60);
        assert_eq!(s.content.len(), 48);
    }

    #[test]
    fn walks_a_sibling_chain() {
        let mut buf = build(b"tfgt", 0, &[0u8; 24]);
        buf.extend_from_slice(&build(b"sarg", 0, &[0u8; 12]));
        buf.extend_from_slice(&build(b"2vlb", 0, &[]));

        let sections = walk(&buf, 0);
        let names: Vec<String> = sections.iter().map(|s| s.name()).collect();
        assert_eq!(names, vec!["tgft", "gras", "blv2"]);
        assert_eq!(sections[0].at, 0);
        assert_eq!(sections[1].at, 36);
        assert!(find(&sections, "gras").is_some());
        assert!(find(&sections, "nope").is_none());
    }

    #[test]
    fn stops_on_a_truncated_section() {
        let mut buf = build(b"tfgt", 0, &[0u8; 8]);
        // Declares 999 bytes of content that are not present.
        buf.extend_from_slice(b"sarg");
        buf.extend_from_slice(&0u32.to_le_bytes());
        buf.extend_from_slice(&999u32.to_le_bytes());
        assert_eq!(walk(&buf, 0).len(), 1);
    }

    #[test]
    fn records_splits_content_into_fixed_tuples() {
        let mut content = Vec::new();
        for v in [15u32, 12, 1, 30, 12, 0] {
            content.extend_from_slice(&v.to_le_bytes());
        }
        let buf = build(b"tfgt", 0, &content);
        let s = read_at(&buf, 0).unwrap();
        assert_eq!(s.records::<3>(), vec![[15, 12, 1], [30, 12, 0]]);
    }
}
