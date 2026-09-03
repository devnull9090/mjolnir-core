//! Same-length rename surgery on a cooked tag package (zen `.uasset`).
//!
//! A tag package's header holds exactly two strings — the asset leaf
//! ("B40-scenario") and the package path — plus derived hashes. Replacing them
//! with strings of the SAME byte length means no offset in the summary moves,
//! `CookedHeaderSize` stays true, and the surgery reduces to overwriting
//! string bytes and recomputing three hashes:
//!
//! - each renamed name-batch entry's hash: CityHash64 of the lowercase UTF-8
//! - the export's `PublicExportHash`: CityHash64 of the lowercase UTF-16LE
//!   leaf name
//!
//! (both formulas verified against the shipped `b40-scenario` package), plus
//! the `BinaryBlobSize` u32 in the export blob when the bulk payload resizes —
//! the same fix `blam-pack` applies to overrides. The same-length constraint
//! is why standalone map codenames are exactly three characters: every shipped
//! scenario's is.

use anyhow::{bail, ensure, Context, Result};
use ue_iostore::city;

fn u32_at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}

fn utf16le_lower(s: &str) -> Vec<u8> {
    let lower = s.to_lowercase();
    let mut out = Vec::with_capacity(lower.len() * 2);
    for u in lower.encode_utf16() {
        out.extend_from_slice(&u.to_le_bytes());
    }
    out
}

/// Clone a tag package's `.uasset` under new names.
///
/// `renames` pairs must be same-length; `old_blob`/`new_blob` are the bulk
/// payload sizes before and after (equal is fine — the size word is checked
/// either way).
pub fn clone_tag_uasset(
    donor: &[u8],
    renames: &[(String, String)],
    old_blob: usize,
    new_blob: usize,
) -> Result<Vec<u8>> {
    for (old, new) in renames {
        ensure!(
            old.len() == new.len(),
            "rename {old:?} -> {new:?} changes length ({} -> {}); the surgery is same-length only",
            old.len(),
            new.len()
        );
    }
    let mut out = donor.to_vec();
    let header_size = u32_at(donor, 4) as usize;
    let export_map_off = u32_at(donor, 32) as usize;
    let export_bundle_off = u32_at(donor, 36) as usize;

    // --- Name batch: count, byte size, hash version, hashes, headers, strings.
    let count = u32_at(donor, 52) as usize;
    let hashes_at = 52 + 8 + 8;
    let headers_at = hashes_at + count * 8;
    let mut string_at = headers_at + count * 2;
    let mut renamed = 0usize;
    for i in 0..count {
        let b0 = donor[headers_at + i * 2];
        let b1 = donor[headers_at + i * 2 + 1];
        let utf16 = b0 & 0x80 != 0;
        let len = (((b0 & 0x7F) as usize) << 8) | b1 as usize;
        let byte_len = if utf16 { len * 2 } else { len };
        let raw = &donor[string_at..string_at + byte_len];
        if !utf16 {
            let name = std::str::from_utf8(raw).unwrap_or("");
            if let Some((_, new)) = renames.iter().find(|(old, _)| old == name) {
                out[string_at..string_at + byte_len].copy_from_slice(new.as_bytes());
                let hash = city::city_hash64(new.to_lowercase().as_bytes());
                out[hashes_at + i * 8..hashes_at + i * 8 + 8]
                    .copy_from_slice(&hash.to_le_bytes());
                renamed += 1;
            }
        }
        string_at += byte_len;
    }
    ensure!(
        renamed == renames.len(),
        "only {renamed} of {} names were found in the donor's name batch",
        renames.len()
    );

    // --- Export public hashes: recompute for any export whose leaf name was
    // renamed, verifying the donor value matched the old formula first.
    const EXPORT_ENTRY: usize = 72;
    let mut at = export_map_off;
    while at + EXPORT_ENTRY <= export_bundle_off {
        let stored = u64::from_le_bytes(donor[at + 56..at + 64].try_into().unwrap());
        for (old, new) in renames {
            let old_hash = city::city_hash64(&utf16le_lower(old));
            if stored == old_hash {
                let new_hash = city::city_hash64(&utf16le_lower(new));
                out[at + 56..at + 64].copy_from_slice(&new_hash.to_le_bytes());
            }
        }
        at += EXPORT_ENTRY;
    }

    // --- The bulk payload's size word. It lives in the header's bulk-data
    // map, not the export blob, so the whole chunk is searched — the same
    // exactly-one-copy contract blam-pack's override path relies on.
    let _ = header_size;
    let needle = (old_blob as u32).to_le_bytes();
    let hits: Vec<usize> = donor
        .windows(4)
        .enumerate()
        .filter(|(_, w)| *w == needle)
        .map(|(i, _)| i)
        .collect();
    if hits.len() != 1 {
        bail!(
            "expected exactly one copy of the blob size in the package, found {}",
            hits.len()
        );
    }
    out[hits[0]..hits[0] + 4].copy_from_slice(&(new_blob as u32).to_le_bytes());

    // The result must still parse as the renamed package.
    let check = ue_asset::zen::Package::parse(&out).context("renamed package does not parse")?;
    for (old, new) in renames {
        ensure!(
            !check.name.contains(old.as_str()) || old == new,
            "renamed package still names {old:?}"
        );
        let _ = new;
    }
    Ok(out)
}
