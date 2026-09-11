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

    /// Append one package (with its import list) to this header.
    ///
    /// Growing the fixed entry array moves the carray heap 16 bytes further
    /// out, and every offset is relative to its entry's own member position —
    /// so each existing non-empty carray offset is bumped to keep pointing at
    /// the same heap bytes. The new package's imports go at the heap's end.
    pub fn append_package(&mut self, package_id: u64, imports: &[u64]) {
        let n = self.package_ids.len();
        let fixed = n * 16;
        let (old_fixed, heap) = self.store_entries.split_at(fixed);
        let mut new_fixed = old_fixed.to_vec();
        for i in 0..n {
            for member in [0usize, 8] {
                let count_at = i * 16 + member;
                let off_at = count_at + 4;
                let count = u32::from_le_bytes(new_fixed[count_at..count_at + 4].try_into().unwrap());
                if count > 0 {
                    let off = u32::from_le_bytes(new_fixed[off_at..off_at + 4].try_into().unwrap());
                    new_fixed[off_at..off_at + 4].copy_from_slice(&(off + 16).to_le_bytes());
                }
            }
        }
        // The new entry: import view member sits at n*16; its data lands at
        // the end of the grown block.
        let mut entry = [0u8; 16];
        if !imports.is_empty() {
            let data_at = (n + 1) * 16 + heap.len();
            let rel = (data_at - n * 16) as u32;
            entry[0..4].copy_from_slice(&(imports.len() as u32).to_le_bytes());
            entry[4..8].copy_from_slice(&rel.to_le_bytes());
        }
        let mut out = Vec::with_capacity((n + 1) * 16 + heap.len() + imports.len() * 8);
        out.extend_from_slice(&new_fixed);
        out.extend_from_slice(&entry);
        out.extend_from_slice(heap);
        for id in imports {
            out.extend_from_slice(&id.to_le_bytes());
        }
        self.store_entries = out;
        self.package_ids.push(package_id);
    }

    /// A header registering packages together with their imported-package
    /// lists. Import carray offsets are relative to the carray view member's
    /// own position (the import view is the first member of its 16-byte
    /// entry), verified against `b40-scenario`'s shipped entry.
    pub fn with_import_lists(container_id: u64, packages: &[(u64, Vec<u64>)]) -> ContainerHeader {
        let fixed = packages.len() * 16;
        let mut entries = vec![0u8; fixed];
        let mut heap: Vec<u8> = Vec::new();
        for (i, (_, imports)) in packages.iter().enumerate() {
            if imports.is_empty() {
                continue;
            }
            let member_at = i * 16; // the import view is the entry's first member
            let data_at = fixed + heap.len();
            let rel = (data_at - member_at) as u32;
            entries[member_at..member_at + 4]
                .copy_from_slice(&(imports.len() as u32).to_le_bytes());
            entries[member_at + 4..member_at + 8].copy_from_slice(&rel.to_le_bytes());
            for id in imports {
                heap.extend_from_slice(&id.to_le_bytes());
            }
        }
        entries.extend_from_slice(&heap);
        ContainerHeader {
            version: 4,
            container_id,
            package_ids: packages.iter().map(|(id, _)| *id).collect(),
            store_entries: entries,
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
