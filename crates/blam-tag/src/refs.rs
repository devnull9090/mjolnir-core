//! Finding tag references in raw tag bytes.
//!
//! A reference is a `tgrf` section — reversed magic, version, size, then a
//! reversed four-CC and a NUL-terminated path (see [`crate::value`]). Walking
//! sections properly needs the layout, because references sit inside the data
//! stream where block boundaries are layout-driven. A reverse-reference index
//! over every shipped tag cannot afford a layout walk per tag, and it does not
//! need one: a `tgrf` header is distinctive enough to find by scanning. The
//! magic must read `tgrf`, the version is always 0 in the shipped build
//! (23,950 sections say so — see [`crate::write`]), the size must fit the
//! buffer, and the content must decode as a known group four-CC plus a
//! printable path. A random byte run passing all four checks would also have
//! to sit inside a tag's data section to matter; in practice the false-positive
//! rate is zero. If a future build breaks that, the fallback is the full parse
//! per tag — slower, exact.

use crate::section::SECTION_HEADER;

/// `tgrf` as it appears on disk: magics are stored reversed.
const MAGIC: &[u8; 4] = b"frgt";

/// Every `(group four-CC, referenced path)` a buffer's `tgrf` sections name.
///
/// `is_known_cc` gates on the four-CCs the game actually ships, which is what
/// makes the scan trustworthy. References with an empty path — the serialized
/// form of "none" — are not returned; they reference nothing.
pub fn tgrf_refs(data: &[u8], is_known_cc: impl Fn(&str) -> bool) -> Vec<(String, String)> {
    let mut out = Vec::new();
    let mut i = 0;
    while i + SECTION_HEADER <= data.len() {
        if &data[i..i + 4] != MAGIC {
            i += 1;
            continue;
        }
        let version = u32::from_le_bytes(data[i + 4..i + 8].try_into().unwrap());
        let size = u32::from_le_bytes(data[i + 8..i + 12].try_into().unwrap()) as usize;
        let Some(content) = data.get(i + SECTION_HEADER..i + SECTION_HEADER + size) else {
            i += 1;
            continue;
        };
        if version != 0 {
            i += 1;
            continue;
        }
        // An empty or four-CC-only content is a set-to-nothing reference;
        // valid, but it points nowhere. The section is exactly its header
        // plus `size` bytes — an empty one is twelve bytes, and the section
        // that follows starts right there. (An earlier version stepped one
        // byte further and walked past every reference that directly
        // followed an empty one — found 2026-09-06 when a scenario's
        // lighting reference went unseen.)
        if content.len() < 5 {
            i += SECTION_HEADER + size;
            continue;
        }
        let cc: String = content[..4]
            .iter()
            .rev()
            .map(|c| {
                if (32..127).contains(c) {
                    *c as char
                } else {
                    '.'
                }
            })
            .collect();
        if cc.contains('.') || !is_known_cc(&cc) {
            i += 1;
            continue;
        }
        let rest = &content[4..];
        let end = rest.iter().position(|c| *c == 0).unwrap_or(rest.len());
        let path = &rest[..end];
        if path.is_empty() || !path.iter().all(|c| (32..127).contains(c)) {
            i += 1;
            continue;
        }
        out.push((cc, String::from_utf8_lossy(path).into_owned()));
        // A `tgrf` is a leaf — nothing nests inside it — so the whole section
        // can be skipped rather than re-scanned byte by byte.
        i += SECTION_HEADER + size;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tgrf(cc: &str, path: &str) -> Vec<u8> {
        let mut content: Vec<u8> = cc.bytes().rev().collect();
        content.extend_from_slice(path.as_bytes());
        content.push(0);
        let mut out = MAGIC.to_vec();
        out.extend_from_slice(&0u32.to_le_bytes());
        out.extend_from_slice(&(content.len() as u32).to_le_bytes());
        out.extend(content);
        out
    }

    #[test]
    fn references_are_found_and_nones_skipped() {
        let mut buf = vec![0xAAu8; 7];
        buf.extend(tgrf("coll", "objects\\characters\\marine\\marine"));
        buf.extend([0x11, 0x22]);
        buf.extend(tgrf("proj", ""));
        buf.extend(tgrf("zzzz", "not\\a\\group"));
        buf.extend(tgrf("skel", "objects\\characters\\marine\\marine"));
        let refs = tgrf_refs(&buf, |cc| matches!(cc, "coll" | "skel" | "proj"));
        assert_eq!(
            refs,
            vec![
                (
                    "coll".to_string(),
                    "objects\\characters\\marine\\marine".to_string()
                ),
                (
                    "skel".to_string(),
                    "objects\\characters\\marine\\marine".to_string()
                ),
            ]
        );
    }

    /// A reference set to nothing serializes as a twelve-byte section with no
    /// content; the reference right behind it must still be found.
    #[test]
    fn a_reference_directly_after_an_empty_one_is_found() {
        let mut buf = MAGIC.to_vec();
        buf.extend_from_slice(&0u32.to_le_bytes());
        buf.extend_from_slice(&0u32.to_le_bytes());
        buf.extend(tgrf("stli", "levels\\halo1\\solo\\a30\\landing_zone_p1"));
        let refs = tgrf_refs(&buf, |_| true);
        assert_eq!(
            refs,
            vec![(
                "stli".to_string(),
                "levels\\halo1\\solo\\a30\\landing_zone_p1".to_string()
            )]
        );
    }
}
