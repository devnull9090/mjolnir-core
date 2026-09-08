//! Persisting the reverse-reference index between sessions.
//!
//! Building the index means reading and scanning every shipped tag — tens of
//! seconds, which the changelog could only soften to "once per session". The
//! result is a pure function of the tag chunks, so it is cached to disk and
//! reloaded while the installation is unchanged.
//!
//! Staleness is decided by a fingerprint over what the index was built from:
//! each container's `.utoc` path, size, modification time and id, and every
//! tag's `(group, short)` in catalog order. A game update, an installed mod
//! or a reordered catalog all change it; a fingerprint miss just means the
//! index is rebuilt and re-stored, so a wrong-but-matching clock is the only
//! way to be served a stale index. Best-effort throughout: a cache that
//! cannot be read or written costs the one-session scan it always cost.

use std::collections::BTreeMap;
use std::hash::Hasher;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// The on-disk shape: the fingerprint the entries were built under, and the
/// map flattened to rows because JSON keys cannot be tuples.
#[derive(Serialize, Deserialize)]
struct CacheFile {
    fingerprint: u64,
    /// `(group four-CC, normalized referenced path, referencing tag indices)`.
    refs: Vec<(String, String, Vec<u32>)>,
}

/// FNV-1a over everything the reverse index depends on.
pub struct Fingerprint(std::hash::DefaultHasher);

impl Fingerprint {
    pub fn new() -> Self {
        Self(std::hash::DefaultHasher::new())
    }

    pub fn container(&mut self, utoc: &Path, container_id: u64, chunks: usize) {
        self.0.write(utoc.to_string_lossy().as_bytes());
        self.0.write_u64(container_id);
        self.0.write_u64(chunks as u64);
        if let Ok(meta) = std::fs::metadata(utoc) {
            self.0.write_u64(meta.len());
            if let Ok(mtime) = meta.modified() {
                if let Ok(d) = mtime.duration_since(std::time::UNIX_EPOCH) {
                    self.0.write_u128(d.as_nanos());
                }
            }
        }
    }

    pub fn tag(&mut self, group: &str, short: &str) {
        self.0.write(group.as_bytes());
        self.0.write(short.as_bytes());
    }

    pub fn finish(self) -> u64 {
        self.0.finish()
    }
}

/// Where a per-installation cache file lives. The file is named by `stem` and
/// a hash of the Paks directory path, so two installations do not evict each
/// other. Shared with the census fingerprint cache (see `crate::census`).
pub(crate) fn cache_file(paks: &Path, stem: &str) -> Option<PathBuf> {
    let mut h = std::hash::DefaultHasher::new();
    h.write(paks.to_string_lossy().to_ascii_lowercase().as_bytes());
    Some(
        dirs::cache_dir()?
            .join("MJOLNIR")
            .join("tag-editor")
            .join(format!("{stem}-{:016x}.json", h.finish())),
    )
}

/// Where the reverse-reference index for one Paks directory lives.
fn cache_path(paks: &Path) -> Option<PathBuf> {
    cache_file(paks, "refs")
}

/// The cached index, if one exists and was built from this exact catalog.
pub fn load(paks: &Path, fingerprint: u64) -> Option<BTreeMap<(String, String), Vec<u32>>> {
    let text = std::fs::read_to_string(cache_path(paks)?).ok()?;
    let file: CacheFile = serde_json::from_str(&text).ok()?;
    if file.fingerprint != fingerprint {
        return None;
    }
    Some(
        file.refs
            .into_iter()
            .map(|(cc, path, tags)| ((cc, path), tags))
            .collect(),
    )
}

/// Write the freshly built index for the next session. Failure costs nothing
/// but that session's rebuild.
pub fn store(paks: &Path, fingerprint: u64, map: &BTreeMap<(String, String), Vec<u32>>) {
    let Some(path) = cache_path(paks) else {
        return;
    };
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let file = CacheFile {
        fingerprint,
        refs: map
            .iter()
            .map(|((cc, p), tags)| (cc.clone(), p.clone(), tags.clone()))
            .collect(),
    };
    if let Ok(text) = serde_json::to_string(&file) {
        // Write-then-rename, so a crash mid-write leaves no torn file to
        // half-parse next launch.
        let tmp = path.with_extension("json.tmp");
        if std::fs::write(&tmp, text).is_ok() {
            let _ = std::fs::rename(&tmp, &path);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrips_through_disk() {
        let dir = std::env::temp_dir().join("mjolnir-refcache-test");
        let _ = std::fs::create_dir_all(&dir);
        let mut map: BTreeMap<(String, String), Vec<u32>> = BTreeMap::new();
        map.insert(("snd!".into(), "weapons/x".into()), vec![3, 9]);
        map.insert(("bipd".into(), "characters/y".into()), vec![12]);
        store(&dir, 42, &map);
        assert_eq!(load(&dir, 42).as_ref(), Some(&map));
        // A different fingerprint is a miss, not a stale hit.
        assert_eq!(load(&dir, 43), None);
        if let Some(p) = cache_path(&dir) {
            let _ = std::fs::remove_file(p);
        }
    }
}
