//! The `ContainerHeader` (chunk type 6): the package-store registration a
//! container carries for the packages it introduces.
//!
//! Layout, established from the UE 5.5-staged MJOLNIRWORLD container and the
//! shipped headers (all of which round-trip byte-exact through this module):
//!
//! ```text
//! magic          4 bytes  6e 43 6f 49 ("IoCn" reversed)
//! version        u32      4 on this build
//! container id   u64      equals the type-6 chunk's own id
//! package ids    u32 count, then count × u64 (FPackageId, city::package_id)
//! store entries  u32 byte length, then that many bytes: one 16-byte
//!                FFilePackageStoreEntry per package — imported-packages
//!                carray (u32 count, u32 relative offset) and shader-map-hash
//!                carray (u32 count, u32 relative offset) — followed by any
//!                carray heap data. All zeros for a package with no package
//!                imports and no global shaders, which is exactly what a Blam
//!                tag package is.
//! tail           the remaining optional sections (optional-segment ids and
//!                entries, redirect name map, localized packages, redirects,
//!                soft references). Kept as raw bytes: every shipped header's
//!                tail is 24 zero bytes, and preserving unknown content beats
//!                misreading it.
//! ```

use crate::Error;

pub const MAGIC: [u8; 4] = [0x6e, 0x43, 0x6f, 0x49];

/// The empty tail every observed header carries: six zero u32 counts.
pub const EMPTY_TAIL: [u8; 24] = [0; 24];

#[derive(Debug, Clone)]
pub struct ContainerHeader {
    pub version: u32,
    pub container_id: u64,
    pub package_ids: Vec<u64>,
    /// The store-entry block, verbatim.
    pub store_entries: Vec<u8>,
    /// Everything after the store entries, verbatim.
    pub tail: Vec<u8>,
}

fn u32_at(b: &[u8], at: usize) -> Result<u32, Error> {
    b.get(at..at + 4)
        .map(|s| u32::from_le_bytes(s.try_into().unwrap()))
        .ok_or(Error::BadContainerHeader("truncated"))
}

fn u64_at(b: &[u8], at: usize) -> Result<u64, Error> {
    b.get(at..at + 8)
        .map(|s| u64::from_le_bytes(s.try_into().unwrap()))
        .ok_or(Error::BadContainerHeader("truncated"))
}

impl ContainerHeader {
    pub fn parse(b: &[u8]) -> Result<ContainerHeader, Error> {
        if b.len() < 8 || b[0..4] != MAGIC {
            return Err(Error::BadContainerHeader("bad magic"));
        }
        let version = u32_at(b, 4)?;
        let container_id = u64_at(b, 8)?;
        let count = u32_at(b, 16)? as usize;
        let mut at = 20;
        let mut package_ids = Vec::with_capacity(count);
        for _ in 0..count {
            package_ids.push(u64_at(b, at)?);
            at += 8;
        }
        let entries_len = u32_at(b, at)? as usize;
        at += 4;
        let store_entries = b
            .get(at..at + entries_len)
            .ok_or(Error::BadContainerHeader("truncated store entries"))?
            .to_vec();
        at += entries_len;
        let tail = b[at..].to_vec();
        Ok(ContainerHeader {
            version,
            container_id,
            package_ids,
            store_entries,
            tail,
        })
    }

    pub fn write(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(
            32 + self.package_ids.len() * 8 + self.store_entries.len() + self.tail.len(),
        );
        out.extend_from_slice(&MAGIC);
        out.extend_from_slice(&self.version.to_le_bytes());
        out.extend_from_slice(&self.container_id.to_le_bytes());
        out.extend_from_slice(&(self.package_ids.len() as u32).to_le_bytes());
        for id in &self.package_ids {
            out.extend_from_slice(&id.to_le_bytes());
        }
        out.extend_from_slice(&(self.store_entries.len() as u32).to_le_bytes());
        out.extend_from_slice(&self.store_entries);
        out.extend_from_slice(&self.tail);
        out
    }

    /// A header registering `package_ids` with empty store entries — right for
    /// packages with no package imports and no global shaders (Blam tags).
    pub fn for_new_packages(container_id: u64, package_ids: Vec<u64>) -> ContainerHeader {
        let store_entries = vec![0u8; package_ids.len() * 16];
        ContainerHeader {
            version: 4,
            container_id,
            package_ids,
            store_entries,
            tail: EMPTY_TAIL.to_vec(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_new_package_header_round_trips() {
        let h = ContainerHeader::for_new_packages(0x1122_3344, vec![0xAABB, 0xCCDD]);
        let bytes = h.write();
        let back = ContainerHeader::parse(&bytes).unwrap();
        assert_eq!(back.container_id, 0x1122_3344);
        assert_eq!(back.package_ids, vec![0xAABB, 0xCCDD]);
        assert_eq!(back.store_entries, vec![0u8; 32]);
        assert_eq!(back.write(), bytes);
    }

    #[test]
    fn parse_rejects_a_bad_magic() {
        assert!(ContainerHeader::parse(&[0u8; 48]).is_err());
    }
}
