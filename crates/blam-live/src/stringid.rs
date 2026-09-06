//! The running game's `string_id` registry.
//!
//! A `string id` field holds a 32-bit id, and the engine resolves it against a
//! registry it builds at load: 2,678 built-in names the module ships, then
//! every name the loaded tags register, numbered sequentially from 1068. A
//! name the registry does not hold is what makes the native parser reject a
//! whole tag (`docs/iostore_packaging.md`, *a string-id hazard*) — so before a
//! string-id edit is poked or packed, this is where to ask whether the game
//! knows the word.
//!
//! The registry is a chained hash table whose nodes point into one storage
//! blob of NUL-terminated names. Its dimensions are fixed in the module and
//! checked here before a byte of it is trusted. Measured 2026-09-05 on CU4 in
//! A30: 64,293 names, every built-in id present, `fork_d = 0x1677`,
//! `warthog_d = 0x17D2`.

use std::collections::HashMap;

use crate::tagtable::{Memory, Profile};
use crate::{Error, Result};

const BUCKETS: u32 = 1_046_528;
const MAX_ENTRIES: u32 = 523_264;
const VALUE_SIZE: u64 = 4;
const HEADER: u64 = 0x38;
const NODE: usize = 0x1c;
const NODE_NEXT: usize = 0x10;
const NODE_OFFSET: usize = 0x18;
const BUILTIN_COUNT: usize = 2_678;
const BUILTIN_STRIDE: usize = 16;
/// Longest name the engine stores.
pub const MAX_NAME: usize = 127;
/// The id of the empty name.
pub const NONE: u32 = u32::MAX;

/// Every `(id, name)` the running game has registered.
pub struct StringIds {
    entries: Vec<(u32, String)>,
    by_name: HashMap<String, u32>,
    by_id: HashMap<u32, usize>,
}

/// The engine's spelling of a string id: ASCII lowercase, spaces and hyphens
/// as underscores. `None` when the name is too long to register.
pub fn normalize(name: &str) -> Option<String> {
    let n: String = name
        .trim()
        .chars()
        .map(|c| match c {
            ' ' | '-' => '_',
            c => c.to_ascii_lowercase(),
        })
        .collect();
    (n.len() <= MAX_NAME).then_some(n)
}

impl StringIds {
    /// Read the registry. Every dimension is checked against the measured
    /// layout, every node offset against the storage in use, and the number
    /// of names found against the engine's own count.
    pub fn read(m: &impl Memory, dll_base: u64, profile: &Profile) -> Result<StringIds> {
        let map = m.u64(dll_base + profile.string_id_map)?;
        let storage = m.u64(dll_base + profile.string_id_storage)?;
        let used = m.u64(dll_base + profile.string_id_used)?;
        let count = m.u64(dll_base + profile.string_id_count)?;
        if map == 0 || storage == 0 {
            return Err(Error::NoMission);
        }
        let h = m.read(map, HEADER as usize)?;
        let buckets = u32::from_le_bytes(h[0..4].try_into().unwrap());
        let max = u32::from_le_bytes(h[4..8].try_into().unwrap());
        let value = u64::from_le_bytes(h[8..16].try_into().unwrap());
        if buckets != BUCKETS || max != MAX_ENTRIES || value != VALUE_SIZE {
            return Err(Error::Layout {
                what: "string-id registry",
                detail: format!("buckets {buckets}, max {max}, value size {value}"),
            });
        }
        if count > u64::from(MAX_ENTRIES) || used > 64 << 20 {
            return Err(Error::Layout {
                what: "string-id registry",
                detail: format!("{count} names in {used} bytes"),
            });
        }
        let blob = m.read(storage, used as usize)?;
        let bucket_ptrs = m.read(map + HEADER, BUCKETS as usize * 8)?;
        let mut entries = Vec::with_capacity(count as usize);
        for b in 0..BUCKETS as usize {
            let mut node = u64::from_le_bytes(bucket_ptrs[b * 8..b * 8 + 8].try_into().unwrap());
            let mut hops = 0usize;
            while node != 0 {
                let n = m.read(node, NODE)?;
                let key = u64::from_le_bytes(n[0..8].try_into().unwrap());
                let next = u64::from_le_bytes(n[NODE_NEXT..NODE_NEXT + 8].try_into().unwrap());
                let off = u32::from_le_bytes(n[NODE_OFFSET..NODE_OFFSET + 4].try_into().unwrap())
                    as usize;
                let name = blob
                    .get(off..)
                    .and_then(|rest| {
                        let end = rest.iter().position(|c| *c == 0)?;
                        Some(String::from_utf8_lossy(&rest[..end]).into_owned())
                    })
                    .ok_or_else(|| Error::Layout {
                        what: "string-id registry",
                        detail: format!("node offset {off:#x} is past the {used} bytes in use"),
                    })?;
                let key = u32::try_from(key).map_err(|_| Error::Layout {
                    what: "string-id registry",
                    detail: format!("id {key:#x} does not fit 32 bits"),
                })?;
                entries.push((key, name));
                node = next;
                hops += 1;
                if hops > MAX_ENTRIES as usize {
                    return Err(Error::Layout {
                        what: "string-id registry",
                        detail: format!("bucket {b} chains without end"),
                    });
                }
            }
        }
        if entries.len() as u64 != count {
            return Err(Error::Layout {
                what: "string-id registry",
                detail: format!("walked {} names, the engine counts {count}", entries.len()),
            });
        }
        entries.sort();
        Ok(Self::from_entries(entries))
    }

    /// The built-in ids the module ships, for a cross-check against the
    /// registry: `(id, name)` for each of the 2,678 slots.
    pub fn builtins(
        m: &impl Memory,
        dll_base: u64,
        profile: &Profile,
    ) -> Result<Vec<(u32, String)>> {
        let t = m.read(
            dll_base + profile.string_id_builtin,
            BUILTIN_COUNT * BUILTIN_STRIDE,
        )?;
        let mut out = Vec::with_capacity(BUILTIN_COUNT);
        for i in 0..BUILTIN_COUNT {
            let e = &t[i * BUILTIN_STRIDE..(i + 1) * BUILTIN_STRIDE];
            let id = u32::from_le_bytes(e[0..4].try_into().unwrap());
            let ptr = u64::from_le_bytes(e[8..16].try_into().unwrap());
            let name = if ptr == 0 {
                String::new()
            } else {
                m.cstr(ptr, MAX_NAME + 1)?
            };
            out.push((id, name));
        }
        Ok(out)
    }

    pub fn from_entries(entries: Vec<(u32, String)>) -> StringIds {
        let by_name = entries.iter().map(|(k, n)| (n.clone(), *k)).collect();
        let by_id = entries
            .iter()
            .enumerate()
            .map(|(i, (k, _))| (*k, i))
            .collect();
        StringIds {
            entries,
            by_name,
            by_id,
        }
    }

    /// The id the game gives a name, in any spelling the engine would
    /// normalise. The empty name is [`NONE`].
    pub fn id(&self, name: &str) -> Option<u32> {
        let n = normalize(name)?;
        if n.is_empty() {
            return Some(NONE);
        }
        self.by_name.get(&n).copied()
    }

    pub fn name(&self, id: u32) -> Option<&str> {
        if id == NONE {
            return Some("");
        }
        self.by_id.get(&id).map(|i| self.entries[*i].1.as_str())
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn iter(&self) -> impl Iterator<Item = (u32, &str)> {
        self.entries.iter().map(|(k, n)| (*k, n.as_str()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tagtable::testing::Mock;
    use crate::tagtable::CU4;

    const DLL: u64 = 0x7FF0_0000_0000;
    const MAP: u64 = 0x4000_0000;
    const STORAGE: u64 = 0x5000_0000;
    const NODES: u64 = 0x6000_0000;

    fn registry(names: &[(u32, &str)]) -> Mock {
        let mut m = Mock::default();
        let mut blob = Vec::new();
        let mut offsets = Vec::new();
        for (_, n) in names {
            offsets.push(blob.len() as u32);
            blob.extend_from_slice(n.as_bytes());
            blob.push(0);
        }
        m.put_u64(DLL + CU4.string_id_map, MAP);
        m.put_u64(DLL + CU4.string_id_storage, STORAGE);
        m.put_u64(DLL + CU4.string_id_used, blob.len() as u64);
        m.put_u64(DLL + CU4.string_id_count, names.len() as u64);
        m.put(STORAGE, &blob);
        let mut header = vec![0u8; HEADER as usize];
        header[0..4].copy_from_slice(&BUCKETS.to_le_bytes());
        header[4..8].copy_from_slice(&MAX_ENTRIES.to_le_bytes());
        header[8..16].copy_from_slice(&VALUE_SIZE.to_le_bytes());
        // Two names share bucket 0 (a chain), the rest sit alone.
        let mut buckets = vec![0u8; BUCKETS as usize * 8];
        let mut table = header;
        let mut nodes = vec![0u8; names.len() * NODE];
        for (i, (id, _)) in names.iter().enumerate() {
            let at = NODES + (i * NODE) as u64;
            nodes[i * NODE..i * NODE + 8].copy_from_slice(&u64::from(*id).to_le_bytes());
            nodes[i * NODE + NODE_OFFSET..i * NODE + NODE_OFFSET + 4]
                .copy_from_slice(&offsets[i].to_le_bytes());
            let bucket = if i < 2 { 0 } else { i };
            let slot = &mut buckets[bucket * 8..bucket * 8 + 8];
            let head = u64::from_le_bytes(slot.try_into().unwrap());
            if head != 0 {
                // Chain: the new node points at the old head.
                nodes[i * NODE + NODE_NEXT..i * NODE + NODE_NEXT + 8]
                    .copy_from_slice(&head.to_le_bytes());
            }
            slot.copy_from_slice(&at.to_le_bytes());
        }
        table.extend(buckets);
        m.put(MAP, &table);
        m.put(NODES, &nodes);
        m
    }

    #[test]
    fn normalisation_follows_the_engine() {
        assert_eq!(normalize("FORK-D").as_deref(), Some("fork_d"));
        assert_eq!(normalize("fork d").as_deref(), Some("fork_d"));
        assert_eq!(normalize("").as_deref(), Some(""));
        assert!(normalize(&"x".repeat(128)).is_none());
        assert_eq!(normalize(&"x".repeat(127)).map(|s| s.len()), Some(127));
    }

    #[test]
    fn the_registry_is_walked_and_indexed() {
        let m = registry(&[
            (1, "default"),
            (0x1677, "fork_d"),
            (0x17D2, "warthog_d"),
            (2, "reload_1"),
        ]);
        let ids = StringIds::read(&m, DLL, &CU4).unwrap();
        assert_eq!(ids.len(), 4);
        assert_eq!(ids.id("fork_d"), Some(0x1677));
        assert_eq!(ids.id("Warthog D"), Some(0x17D2));
        assert_eq!(ids.id(""), Some(NONE));
        assert_eq!(ids.id("not_registered"), None);
        assert_eq!(ids.name(2), Some("reload_1"));
        assert_eq!(ids.name(NONE), Some(""));
        assert_eq!(ids.iter().next(), Some((1, "default")));
    }

    #[test]
    fn a_count_mismatch_is_refused() {
        let mut m = registry(&[(1, "default"), (2, "reload_1")]);
        m.put_u64(DLL + CU4.string_id_count, 3);
        assert!(matches!(
            StringIds::read(&m, DLL, &CU4),
            Err(Error::Layout {
                what: "string-id registry",
                ..
            })
        ));
    }

    #[test]
    fn foreign_dimensions_are_refused() {
        let mut m = registry(&[(1, "default")]);
        let mut h = m.read(MAP, HEADER as usize).unwrap();
        h[0..4].copy_from_slice(&1u32.to_le_bytes());
        let mut table = m.read(MAP, HEADER as usize + BUCKETS as usize * 8).unwrap();
        table[..HEADER as usize].copy_from_slice(&h);
        m.put(MAP, &table);
        assert!(matches!(
            StringIds::read(&m, DLL, &CU4),
            Err(Error::Layout {
                what: "string-id registry",
                ..
            })
        ));
    }
}
