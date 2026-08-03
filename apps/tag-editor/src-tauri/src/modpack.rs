//! Baking a mod project into containers, a `.mjolnir` archive, and a local
//! test install.
//!
//! The project itself stays a recipe; this module is where the recipe meets
//! the player's installation and becomes IoStore override containers. The
//! container work is `blam-pack` — the same code the `mjolnir` CLI uses —
//! and the archive layout is the hub's `.mjolnir` format
//! (`docs/mjolnir_format.md`): `mjolnir.json` at the root, containers under
//! `content/`, nothing else required.

use std::collections::BTreeMap;
use std::io::Write;
use std::path::{Path, PathBuf};

use serde::Serialize;

use crate::catalog::Catalog;
use crate::project::Meta;

/// Marker in every file a test install writes, so they can be found and
/// removed no matter which mod wrote them. Distinct from the launcher's
/// `MJOLNIRHUB` marker, which its own installer owns and cleans.
const TEST_MARKER: &str = "-MJOLNIRDEV-";

/// Test containers mount as `pakchunk999`, after every shipped container and
/// the launcher's hub installs (900+), so the mod under test wins.
const TEST_PREFIX: &str = "pakchunk999";

/// The hub rejects archives over this; warn before the upload fails.
pub const MAX_ARCHIVE_BYTES: u64 = 50 * 1024 * 1024;

/// One edit resolved against the open installation, ready to pack.
pub struct ResolvedEdit {
    /// `objects/weapons/pistol/pistol.weapon`, for messages.
    pub label: String,
    /// Which loaded container the tag lives in.
    pub container: usize,
    pub chunk: ue_iostore::ChunkEntry,
    pub original_len: usize,
    pub patched: Vec<u8>,
}

/// A built override container and the basename it ships under.
pub struct Baked {
    /// e.g. `faster-pistol_P` — the `_P` suffix is what makes it a patch
    /// container; without it the shipped chunk wins.
    pub basename: String,
    pub built: blam_pack::Built,
}

/// Bake resolved edits into override containers, one per source container.
pub fn bake(c: &Catalog, slug: &str, edits: Vec<ResolvedEdit>) -> Result<Vec<Baked>, String> {
    let mut by_source: BTreeMap<usize, Vec<blam_pack::TagEdit>> = BTreeMap::new();
    for e in edits {
        by_source
            .entry(e.container)
            .or_default()
            .push(blam_pack::TagEdit {
                label: e.label,
                chunk: e.chunk,
                original_len: e.original_len,
                patched: e.patched,
            });
    }

    let mut out = Vec::new();
    for (nth, (source_index, edits)) in by_source.into_iter().enumerate() {
        let source = c
            .container(source_index)
            .ok_or("source container index out of range")?;
        let built = blam_pack::build_override(source, c.oodle_paths(), &edits)?;
        // One container is the common case and keeps the plain name; only a
        // mod spanning several shipped containers numbers them.
        let basename = if nth == 0 {
            format!("{slug}_P")
        } else {
            format!("{slug}-{}_P", nth + 1)
        };
        out.push(Baked { basename, built });
    }
    Ok(out)
}

/// Write baked containers into `dir` and read each back through the ordinary
/// reader to prove the game could use them.
pub fn write_and_verify(dir: &Path, baked: &[Baked], oodle: &[PathBuf]) -> Result<(), String> {
    std::fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    for b in baked {
        let utoc = dir.join(format!("{}.utoc", b.basename));
        let ucas = dir.join(format!("{}.ucas", b.basename));
        std::fs::write(&utoc, &b.built.utoc).map_err(|e| format!("{}: {e}", utoc.display()))?;
        std::fs::write(&ucas, &b.built.ucas).map_err(|e| format!("{}: {e}", ucas.display()))?;
        blam_pack::verify_written(&utoc, oodle, &b.built.expect)?;
    }
    Ok(())
}

/// The `mjolnir.json` the hub validates, derived from the project metadata.
#[derive(Serialize)]
struct Manifest<'a> {
    schema_version: u32,
    name: &'a str,
    version: &'a str,
    #[serde(rename = "type")]
    kind: &'a str,
    #[serde(skip_serializing_if = "str::is_empty")]
    summary: &'a str,
}

/// Write the `.mjolnir` archive: manifest at the root, containers under
/// `content/`, the project README under `docs/`. Returns the archive size.
pub fn write_archive(
    dest: &Path,
    meta: &Meta,
    baked: &[Baked],
    readme: Option<&Path>,
) -> Result<u64, String> {
    let manifest = serde_json::to_string_pretty(&Manifest {
        schema_version: 1,
        name: &meta.name,
        version: &meta.version,
        kind: "content",
        summary: &meta.summary,
    })
    .map_err(|e| e.to_string())?;

    let file = std::fs::File::create(dest).map_err(|e| format!("{}: {e}", dest.display()))?;
    let mut zip = zip::ZipWriter::new(file);
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);
    let err = |e: zip::result::ZipError| format!("{}: {e}", dest.display());
    let io = |e: std::io::Error| format!("{}: {e}", dest.display());

    zip.start_file("mjolnir.json", options).map_err(err)?;
    zip.write_all(manifest.as_bytes()).map_err(io)?;
    for b in baked {
        zip.start_file(format!("content/{}.utoc", b.basename), options)
            .map_err(err)?;
        zip.write_all(&b.built.utoc).map_err(io)?;
        zip.start_file(format!("content/{}.ucas", b.basename), options)
            .map_err(err)?;
        zip.write_all(&b.built.ucas).map_err(io)?;
    }
    if let Some(readme) = readme {
        if let Ok(text) = std::fs::read(readme) {
            zip.start_file("docs/README.md", options).map_err(err)?;
            zip.write_all(&text).map_err(io)?;
        }
    }
    zip.finish().map_err(err)?;

    std::fs::metadata(dest)
        .map(|m| m.len())
        .map_err(|e| format!("{}: {e}", dest.display()))
}

/// The stub `.pak` a container triple needs: containers without a `.pak`
/// sibling are never discovered, so a byte-copy of the smallest shipped one
/// rides along — the same trick the launcher uses on install.
fn stub_pak_bytes(paks: &Path) -> Result<Vec<u8>, String> {
    let mut smallest: Option<(u64, PathBuf)> = None;
    let entries = std::fs::read_dir(paks).map_err(|e| format!("{}: {e}", paks.display()))?;
    for entry in entries.flatten() {
        let path = entry.path();
        let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
        if !name.ends_with(".pak") || name.contains(TEST_MARKER) || name.contains("-MJOLNIRHUB-") {
            continue;
        }
        let Ok(len) = entry.metadata().map(|m| m.len()) else {
            continue;
        };
        if smallest.as_ref().is_none_or(|(best, _)| len < *best) {
            smallest = Some((len, path));
        }
    }
    let (_, path) = smallest.ok_or("no shipped .pak to copy a stub from")?;
    std::fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))
}

/// Files a test install would write or a previous one left behind.
pub fn test_files(paks: &Path) -> Vec<String> {
    let Ok(entries) = std::fs::read_dir(paks) else {
        return Vec::new();
    };
    let mut out: Vec<String> = entries
        .flatten()
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|name| name.contains(TEST_MARKER))
        .collect();
    out.sort();
    out
}

/// Install baked containers into the Paks folder for an in-game test.
///
/// Any previous test install is removed first, so the folder never holds two
/// generations of the mod. Returns the file names written.
pub fn install_test(
    paks: &Path,
    baked: &[Baked],
    oodle: &[PathBuf],
) -> Result<Vec<String>, String> {
    remove_test(paks)?;
    let stub = stub_pak_bytes(paks)?;
    let mut written = Vec::new();
    for b in baked {
        let base = format!("{TEST_PREFIX}{TEST_MARKER}{}", b.basename);
        let utoc = paks.join(format!("{base}.utoc"));
        for (ext, bytes) in [
            ("utoc", &b.built.utoc),
            ("ucas", &b.built.ucas),
            ("pak", &stub),
        ] {
            let path = paks.join(format!("{base}.{ext}"));
            std::fs::write(&path, bytes).map_err(|e| format!("{}: {e}", path.display()))?;
            written.push(format!("{base}.{ext}"));
        }
        blam_pack::verify_written(&utoc, oodle, &b.built.expect)?;
    }
    Ok(written)
}

/// Remove every file a test install wrote. Returns how many were removed.
pub fn remove_test(paks: &Path) -> Result<usize, String> {
    let mut removed = 0;
    for name in test_files(paks) {
        let path = paks.join(&name);
        std::fs::remove_file(&path).map_err(|e| {
            format!(
                "{}: {e} — if the game is running, close it and try again",
                path.display()
            )
        })?;
        removed += 1;
    }
    Ok(removed)
}
