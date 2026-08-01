//! Minimal cooked (zen) package header reading.
//!
//! Enough to pull the imported package names out of a `.uasset`, which is how
//! a tag package declares the Unreal assets and other tags it binds to.

/// Header field offsets, per `FZenPackageSummary`.
const OFF_IMPORTED_PKG_NAMES: usize = 48;
const OFF_HEADER_SIZE: usize = 4;
const NAME_BATCH_START: usize = 52;

/// Parse an Unreal name batch: `count`, byte size, hash version, hashes,
/// 2-byte headers, then the string data.
pub fn load_name_batch(buf: &[u8], mut pos: usize) -> Option<Vec<String>> {
    let count = i32::from_le_bytes(buf.get(pos..pos + 4)?.try_into().ok()?) as usize;
    pos += 8;
    if count == 0 || count > 4096 {
        return if count == 0 { Some(Vec::new()) } else { None };
    }
    pos += 8 + 8 * count;
    let mut headers = Vec::with_capacity(count);
    for _ in 0..count {
        let b0 = *buf.get(pos)?;
        let b1 = *buf.get(pos + 1)?;
        headers.push((b0 & 0x80 != 0, (((b0 & 0x7F) as usize) << 8) | b1 as usize));
        pos += 2;
    }
    let mut names = Vec::with_capacity(count);
    for (utf16, len) in headers {
        if utf16 {
            let raw = buf.get(pos..pos + len * 2)?;
            let units: Vec<u16> = raw
                .chunks_exact(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .collect();
            names.push(String::from_utf16_lossy(&units));
            pos += len * 2;
        } else {
            names.push(String::from_utf8_lossy(buf.get(pos..pos + len)?).into_owned());
            pos += len;
        }
    }
    Some(names)
}

/// The package's own name, from the summary name map.
pub fn package_name(uasset: &[u8]) -> Option<String> {
    let names = load_name_batch(uasset, NAME_BATCH_START)?;
    let idx = u32::from_le_bytes(uasset.get(8..12)?.try_into().ok()?) & ((1 << 30) - 1);
    names.into_iter().nth(idx as usize)
}

/// Names of the packages this package imports, e.g.
/// `/Game/Tags/objects/characters/elite/elite-model` or
/// `/Game/Blueprints/Synchronization/Characters/BP_EliteBipedActor`.
pub fn imported_package_names(uasset: &[u8]) -> Vec<String> {
    let Some(header_size) = uasset
        .get(OFF_HEADER_SIZE..OFF_HEADER_SIZE + 4)
        .map(|b| u32::from_le_bytes(b.try_into().unwrap()) as usize)
    else {
        return Vec::new();
    };
    let Some(off) = uasset
        .get(OFF_IMPORTED_PKG_NAMES..OFF_IMPORTED_PKG_NAMES + 4)
        .map(|b| i32::from_le_bytes(b.try_into().unwrap()))
    else {
        return Vec::new();
    };
    if off <= 0 || off as usize >= header_size {
        return Vec::new();
    }
    load_name_batch(uasset, off as usize).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_empty_batch_is_empty() {
        let mut buf = vec![0u8; 64];
        buf[52..56].copy_from_slice(&0i32.to_le_bytes());
        assert_eq!(load_name_batch(&buf, 52), Some(Vec::new()));
    }

    #[test]
    fn a_batch_with_one_utf8_name_parses() {
        let mut buf = Vec::new();
        buf.extend_from_slice(&1i32.to_le_bytes()); // count
        buf.extend_from_slice(&5i32.to_le_bytes()); // string bytes
        buf.extend_from_slice(&0u64.to_le_bytes()); // hash version
        buf.extend_from_slice(&0u64.to_le_bytes()); // one hash
        buf.push(0x00); // header: utf8, high length bits
        buf.push(5); // length
        buf.extend_from_slice(b"hello");
        assert_eq!(load_name_batch(&buf, 0), Some(vec!["hello".to_string()]));
    }
}
