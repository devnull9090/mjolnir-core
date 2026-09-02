//! Finding tag references in raw tag bytes.
//!
//! A reference is a `tgrf` section — reversed magic, version, size, then a
//! reversed four-CC and a NUL-terminated path (see `blam_tag::value::
//! reference`). Walking sections properly needs the layout, because references
//! sit inside the data stream where block boundaries are layout-driven. But a
//! reverse-reference index over every shipped tag cannot afford a layout walk
//! per tag, and it does not need one: a `tgrf` header is distinctive enough to
//! find by scanning. The magic must read `tgrf`, the version is always 0 in
//! the shipped build (23,950 sections say so — see `write.rs`), the size must
//! fit the buffer, and the content must decode as a known group four-CC plus a
//! printable path. A random byte run passing all four checks would also have
//! to sit inside a tag's data section to matter; in practice the false-positive
//! rate is zero. If a future build breaks that, the fallback is the full
//! `blam_tag` parse per tag — slower, exact.

use blam_tag::section::SECTION_HEADER;

/// `tgrf` as it appears on disk: magics are stored reversed.
const MAGIC: &[u8; 4] = b"frgt";

/// Every `(group four-CC, referenced path)` a buffer's `tgrf` sections name.
///
/// `is_known_cc` gates on the four-CCs the catalog actually ships, which is
/// what makes the scan trustworthy. References with an empty path — the
/// serialized form of "none" — are not returned; they reference nothing.
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
        // valid, but it points nowhere.
        if content.len() < 5 {
            i += SECTION_HEADER + size.max(1);
            continue;
        }
        let cc: String = content[..4]
            .iter()
            .rev()
            .map(|c| if (32..127).contains(c) { *c as char } else { '.' })
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
        let mut content = Vec::new();
        content.extend(cc.bytes().rev());
        content.extend(path.bytes());
        content.push(0);
        blam_tag::write::raw_section("tgrf", 0, &content)
    }

    fn known(cc: &str) -> bool {
        matches!(cc, "weap" | "bipd" | "effe")
    }

    #[test]
    fn finds_references_wherever_they_sit() {
        let mut buf = vec![0xAA; 17]; // arbitrary lead-in, unaligned on purpose
        buf.extend(tgrf("weap", "objects\\weapons\\rifle\\rifle"));
        buf.extend([0x00; 9]);
        buf.extend(tgrf("effe", "fx\\muzzle\\flash"));
        let found = tgrf_refs(&buf, known);
        assert_eq!(
            found,
            vec![
                ("weap".into(), "objects\\weapons\\rifle\\rifle".into()),
                ("effe".into(), "fx\\muzzle\\flash".into()),
            ]
        );
    }

    #[test]
    fn empty_references_are_skipped_not_reported() {
        // How the game serializes "no reference": an empty content.
        let buf = blam_tag::write::raw_section("tgrf", 0, &[]);
        assert!(tgrf_refs(&buf, known).is_empty());
    }

    #[test]
    fn an_unknown_four_cc_is_a_decoy_not_a_reference() {
        // The bytes shape-match a tgrf but the group does not exist, so a
        // catalog gate rejects it.
        let buf = tgrf("zzzz", "not\\a\\real\\tag");
        assert!(tgrf_refs(&buf, known).is_empty());
    }

    #[test]
    fn a_nonzero_version_is_not_a_reference() {
        // Every shipped tgrf is version 0; anything else is coincidence.
        let mut content = Vec::new();
        content.extend(b"paew");
        content.extend(b"objects\\weapons\\rifle\\rifle\0");
        let buf = blam_tag::write::raw_section("tgrf", 1, &content);
        assert!(tgrf_refs(&buf, known).is_empty());
    }

    #[test]
    fn a_truncated_header_at_the_tail_is_ignored() {
        let mut buf = tgrf("bipd", "objects\\characters\\elite\\elite");
        buf.extend(b"frgt"); // magic with no room for a header after it
        let found = tgrf_refs(&buf, known);
        assert_eq!(found.len(), 1);
    }

    #[test]
    fn unprintable_paths_are_rejected() {
        let mut content = Vec::new();
        content.extend(b"paew");
        content.extend([0x01, 0x02, 0x03, 0x00]);
        let buf = blam_tag::write::raw_section("tgrf", 0, &content);
        assert!(tgrf_refs(&buf, known).is_empty());
    }
}
