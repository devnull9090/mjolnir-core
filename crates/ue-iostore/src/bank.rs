//! Wwise banks a map pack carries.
//!
//! A hub archive never holds a `.pak`: one can hold any file in the game. A
//! vehicle's sounds travel as bare `.bnk` members, and whoever installs them
//! builds the `.pak` itself ([`bank_pak`]), so a bank can only ever land at
//! `Meteorite/Content/WwiseAudio/<id>.bnk`.
//!
//! The rules here are the ones `hub/src/lib/api/scan.ts` applies. A shipped
//! bank's id is refused because a map pack must not change the sound of a stock
//! vehicle on every other map.

use crate::pak::write_files;

/// Where the game reads banks from, by id, below the `.pak`'s mount.
pub const BANK_DIR: &str = "Meteorite/Content/WwiseAudio/";
/// The bank format this game reads.
const BANK_VERSION: u32 = 150;
/// Far above a vehicle's bank (an engine's four loops are 2.3 MB), to stop a
/// member being a way to carry something else.
pub const MAX_BANK_BYTES: usize = 16 * 1024 * 1024;
/// How many banks one release may carry.
pub const MAX_BANKS: usize = 32;
/// All of one release's banks: the hub holds them in memory to read them.
pub const MAX_ALL_BANKS_BYTES: usize = 48 * 1024 * 1024;

/// The ids of every bank the game ships (`pak_banks` writes the file).
const SHIPPED: &str = include_str!("../../../defs/hce/shipped_banks.json");

/// Whether `id` is a bank the game ships.
pub fn is_shipped(id: u32) -> bool {
    let want = id.to_string();
    SHIPPED
        .split(|c: char| !c.is_ascii_digit())
        .any(|n| n == want)
}

/// A bank member's container and id: `content/<container>/<id>.bnk`. The
/// container is a plain name and the id written as a number writes itself, so a
/// path can't climb out of the cache and two members can't be the same bank.
pub fn member(path: &str) -> Option<(&str, u32)> {
    let rest = path.strip_prefix("content/")?;
    let (container, name) = rest.split_once('/')?;
    let id: u32 = name.strip_suffix(".bnk")?.parse().ok()?;
    let plain = |c: u8| c.is_ascii_alphanumeric() || c == b'-' || c == b'_';
    if container.is_empty() || !container.bytes().all(plain) || name != format!("{id}.bnk") {
        return None;
    }
    Some((container, id))
}

fn u32_at(b: &[u8], at: usize) -> Option<u32> {
    Some(u32::from_le_bytes(b.get(at..at + 4)?.try_into().ok()?))
}

/// Refuse what isn't a bank of ours: every section in bounds and of a known
/// kind, the header's id `id`, every media entry inside DATA, and every HIRC
/// record inside HIRC. This keeps a member to being a bank; it is not a proof
/// that Wwise will read one safely.
pub fn check(id: u32, bank: &[u8]) -> Result<(), String> {
    if bank.len() > MAX_BANK_BYTES {
        return Err(format!("bank {id} is {} bytes; the cap is {MAX_BANK_BYTES}", bank.len()));
    }
    if is_shipped(id) {
        return Err(format!("bank {id} is one the game ships"));
    }
    let (mut at, mut data, mut index, mut hirc) = (0usize, None, None, None);
    while at < bank.len() {
        let magic = bank.get(at..at + 4).ok_or("a section is cut short")?;
        let size = u32_at(bank, at + 4).ok_or("a section is cut short")? as usize;
        let body = at + 8;
        let end = body.checked_add(size).filter(|e| *e <= bank.len());
        let end = end.ok_or("a section runs past the end")?;
        match magic {
            b"BKHD" if at == 0 => {
                if u32_at(bank, body).filter(|_| size >= 8) != Some(BANK_VERSION) {
                    return Err("not a version 150 bank".into());
                }
                if u32_at(bank, body + 4) != Some(id) {
                    return Err(format!("the header's id is not {id}"));
                }
            }
            b"DIDX" if index.is_none() => index = Some((body, size)),
            b"DATA" if data.is_none() => data = Some(size),
            b"HIRC" if hirc.is_none() => hirc = Some((body, end)),
            _ => return Err("a section of a kind banks here don't have, or a second one".into()),
        }
        at = end;
    }
    if !bank.starts_with(b"BKHD") {
        return Err("no BKHD".into());
    }
    if let Some((body, size)) = index {
        if size % 12 != 0 {
            return Err("DIDX is not whole entries".into());
        }
        let data = data.ok_or("DIDX with no DATA")?;
        for i in 0..size / 12 {
            let offset = u32_at(bank, body + 12 * i + 4).ok_or("DIDX is cut short")? as usize;
            let length = u32_at(bank, body + 12 * i + 8).ok_or("DIDX is cut short")? as usize;
            if offset.checked_add(length).is_none_or(|e| e > data) {
                return Err("a media entry runs past DATA".into());
            }
        }
    }
    let (body, end) = hirc.ok_or("no HIRC")?;
    let count = u32_at(bank, body).ok_or("HIRC is cut short")?;
    let mut at = body + 4;
    for _ in 0..count {
        let size = u32_at(bank, at + 1).ok_or("a HIRC record is cut short")? as usize;
        at = at
            .checked_add(5 + size)
            .filter(|e| *e <= end)
            .ok_or("a HIRC record runs past HIRC")?;
    }
    if at != end {
        return Err("HIRC has bytes past its records".into());
    }
    Ok(())
}

/// A minimal well-formed bank: one media file and one HIRC record. For tests.
#[doc(hidden)]
pub fn sample(id: u32) -> Vec<u8> {
    let section = |tag: &[u8], body: &[u8]| {
        let mut s = tag.to_vec();
        s.extend_from_slice(&(body.len() as u32).to_le_bytes());
        s.extend_from_slice(body);
        s
    };
    let mut head = BANK_VERSION.to_le_bytes().to_vec();
    head.extend_from_slice(&id.to_le_bytes());
    head.extend_from_slice(&[0; 32]);
    let mut index = 7u32.to_le_bytes().to_vec();
    index.extend_from_slice(&0u32.to_le_bytes());
    index.extend_from_slice(&5u32.to_le_bytes());
    let mut hirc = 1u32.to_le_bytes().to_vec();
    hirc.push(2);
    hirc.extend_from_slice(&8u32.to_le_bytes());
    hirc.extend_from_slice(&11u32.to_le_bytes());
    hirc.extend_from_slice(b"body");
    [
        section(b"BKHD", &head),
        section(b"DIDX", &index),
        section(b"DATA", b"media"),
        section(b"HIRC", &hirc),
    ]
    .concat()
}

/// Wwise's id of a name, the seed the build step uses: 32-bit FNV-1 of its lower case.
fn fnv1(name: &str) -> u32 {
    name.to_lowercase().bytes().fold(2166136261u32, |h, c| h.wrapping_mul(16777619) ^ c as u32)
}

/// The `.pak` beside `container` that carries its banks, sorted by id. It must
/// keep `tools/level/wwise_bank.py`'s bytes: a test holds the two together.
pub fn bank_pak(container: &str, banks: &[(u32, Vec<u8>)]) -> Vec<u8> {
    let mut sorted: Vec<_> = banks.iter().collect();
    sorted.sort_by_key(|(id, _)| *id);
    let files: Vec<(String, &[u8])> = sorted
        .iter()
        .map(|(id, bytes)| (format!("{id}.bnk"), bytes.as_slice()))
        .collect();
    write_files(BANK_DIR, &files, fnv1(container) as u64)
}

#[cfg(test)]
mod tests {
    use super::*;

    use super::sample as bank;

    #[test]
    fn a_good_bank_passes() {
        assert_eq!(check(99, &bank(99)), Ok(()));
    }

    #[test]
    fn the_name_and_header_must_agree() {
        assert!(check(98, &bank(99)).unwrap_err().contains("header's id"));
    }

    #[test]
    fn a_shipped_bank_is_refused() {
        let id = 833622567; // the Warthog's
        assert!(check(id, &bank(id)).unwrap_err().contains("ships"));
    }

    #[test]
    fn anything_that_is_not_a_bank_is_refused() {
        assert!(check(99, b"not a bank at all").is_err());
        assert!(check(99, b"").is_err());
        let mut pak = crate::pak::stub_for("x");
        pak.extend_from_slice(&bank(99));
        assert!(check(99, &pak).is_err());
    }

    #[test]
    fn a_section_of_another_kind_is_refused() {
        let mut b = bank(99);
        b.extend_from_slice(b"FXPR\0\0\0\0");
        assert!(check(99, &b).unwrap_err().contains("kind"));
    }

    #[test]
    fn a_second_section_of_a_kind_is_refused() {
        // Only the last would be read here, and the first is what Wwise would meet.
        let mut b = bank(99);
        let hirc = b.windows(4).position(|w| w == b"HIRC").unwrap();
        let again = b[hirc..].to_vec();
        b.extend_from_slice(&again);
        assert!(check(99, &b).unwrap_err().contains("second"));
    }

    /// hub/scripts/test-scan.mts builds the same bytes, so the hub's rules and
    /// these are tried on one fixture.
    #[test]
    fn the_sample_is_the_hubs_sample() {
        use sha1::{Digest, Sha1};
        let hex: String = Sha1::digest(bank(99)).iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(hex, "b76d27ed276b91306dc5ebb6fd2b80e847f57d79");
    }

    #[test]
    fn a_size_past_the_end_is_refused() {
        let mut b = bank(99);
        let hirc = b.windows(4).position(|w| w == b"HIRC").unwrap();
        b[hirc + 4..hirc + 8].copy_from_slice(&u32::MAX.to_le_bytes());
        assert!(check(99, &b).is_err());
    }

    #[test]
    fn a_media_entry_past_data_is_refused() {
        let mut b = bank(99);
        let index = b.windows(4).position(|w| w == b"DIDX").unwrap();
        b[index + 16..index + 20].copy_from_slice(&6u32.to_le_bytes());
        assert!(check(99, &b).unwrap_err().contains("DATA"));
    }

    #[test]
    fn a_record_past_hirc_is_refused() {
        let mut b = bank(99);
        let hirc = b.windows(4).position(|w| w == b"HIRC").unwrap();
        // Past the section header, the record count and the record's kind.
        let at = hirc + 8 + 4 + 1;
        b[at..at + 4].copy_from_slice(&999u32.to_le_bytes());
        assert!(check(99, &b).unwrap_err().contains("HIRC"));
    }

    #[test]
    fn a_member_names_its_container_and_id() {
        assert_eq!(member("content/pakchunk996-MJOLNIRBANK-RWC_P/5.bnk"), Some(("pakchunk996-MJOLNIRBANK-RWC_P", 5)));
        for other in [
            "content/5.bnk",
            "content/x/name.bnk",
            "content/x/y/5.bnk",
            "content/x/5.wem",
            "map/x/5.bnk",
            "content//5.bnk",
            "content/x/99999999999.bnk",
            "content/../5.bnk",
            "content/a.b/5.bnk",
            "content/x/05.bnk",
            "content/x/+5.bnk",
            "content/x/5.BNK",
        ] {
            assert_eq!(member(other), None, "{other}");
        }
    }

    /// test_wwise_bank.py asserts the same hash, which holds this writer and
    /// `tools/level/wwise_bank.py`'s together.
    #[test]
    fn a_pak_matches_the_build_steps_bytes() {
        use sha1::{Digest, Sha1};
        let banks = [(6, b"second bank".to_vec()), (5, b"first".to_vec())];
        let hash = Sha1::digest(bank_pak("pakchunk996-MJOLNIRBANK-RWC_P", &banks));
        let hex: String = hash.iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(hex, "b7db7dc0eb5e7cd546a76ab228cc2670bc9e16a3");
    }

    #[test]
    fn a_pak_reads_back_with_its_banks_in_id_order() {
        let dir = std::env::temp_dir().join(format!("mjolnir-bank-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("test.pak");
        let (a, b) = (b"first".to_vec(), b"second bank".to_vec());
        std::fs::write(&path, bank_pak("c", &[(6, b.clone()), (5, a.clone())])).unwrap();
        let pak = crate::pak::load_pak(&path).unwrap();
        let names: Vec<_> = pak.files.keys().map(|k| pak.full_path(k)).collect();
        assert_eq!(
            names,
            [
                "../../../Meteorite/Content/WwiseAudio/5.bnk",
                "../../../Meteorite/Content/WwiseAudio/6.bnk"
            ]
        );
        let read = |k: &str| crate::pak::read_file(&pak, &pak.files[k], None, &[]).unwrap();
        let keys: Vec<_> = pak.files.keys().cloned().collect();
        assert_eq!(read(&keys[0]), a);
        assert_eq!(read(&keys[1]), b);
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
