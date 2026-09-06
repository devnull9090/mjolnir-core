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

/// One tag the mod adds, built against the open installation.
pub struct NewTagPackage {
    /// `objects/weapons/pistol/pistol_mk2.weapon`, for messages.
    pub label: String,
    /// The donor's container, whose index settings the addition copies.
    pub source: usize,
    pub package: blam_pack::NewPackage,
}

/// A built override container and the basename it ships under.
pub struct Baked {
    /// e.g. `faster-pistol_P` — the `_P` suffix is what makes it a patch
    /// container; without it the shipped chunk wins.
    pub basename: String,
    pub built: blam_pack::Built,
}

/// Bake resolved edits into override containers, one per source container,
/// and new tags into addition containers, one per package folder.
pub fn bake(
    c: &Catalog,
    slug: &str,
    edits: Vec<ResolvedEdit>,
    additions: Vec<NewTagPackage>,
) -> Result<Vec<Baked>, String> {
    let mut by_source: BTreeMap<usize, Vec<blam_pack::ChunkEdit>> = BTreeMap::new();
    for e in edits {
        by_source
            .entry(e.container)
            .or_default()
            .push(blam_pack::ChunkEdit {
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

    // New packages register through the container's own header and are
    // named in its directory index, which holds one folder — so one addition
    // container per folder the new tags land in.
    let mut by_dir: BTreeMap<String, Vec<NewTagPackage>> = BTreeMap::new();
    for a in additions {
        let dir = a
            .package
            .package_name
            .rsplit_once('/')
            .map(|(d, _)| d.to_string())
            .unwrap_or_default();
        by_dir.entry(dir).or_default().push(a);
    }
    for (nth, (_, group)) in by_dir.into_iter().enumerate() {
        let source = c
            .container(group[0].source)
            .ok_or("source container index out of range")?;
        let name = if nth == 0 {
            format!("{slug}-new")
        } else {
            format!("{slug}-new-{}", nth + 1)
        };
        let packages: Vec<blam_pack::NewPackage> = group.into_iter().map(|a| a.package).collect();
        let built = blam_pack::build_addition(source, c.oodle_paths(), &name, &packages)?;
        out.push(Baked {
            basename: format!("{name}_P"),
            built,
        });
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

/// One field edit as `changes.json` declares it to players.
#[derive(Serialize)]
pub struct DeclaredField {
    pub field: String,
    /// The shipped value at export time; absent only if it did not resolve.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub before: Option<String>,
    pub value: String,
}

/// Every declared edit to one tag.
#[derive(Serialize)]
pub struct DeclaredTag {
    pub group: String,
    pub tag: String,
    pub fields: Vec<DeclaredField>,
}

#[derive(Serialize)]
pub struct DeclaredTexture {
    pub path: String,
    /// Size of the replacement image, so the list hints at scope.
    pub bytes: usize,
}

#[derive(Serialize)]
pub struct DeclaredScript {
    pub group: String,
    pub tag: String,
}

/// One tag the mod adds, as `changes.json` declares it.
#[derive(Serialize)]
pub struct DeclaredNewTag {
    pub group: String,
    pub tag: String,
    /// The shipped tag it was cloned from.
    pub from: String,
}

/// The `changes.json` an archive carries: the recipe resolved against the
/// author's installation at export time, written for players rather than
/// for re-application. The hub and the launcher render it as "what this
/// mod does"; the containers remain the bytes that actually ship.
#[derive(Serialize)]
pub struct DeclaredChanges {
    pub schema_version: u32,
    pub tags: Vec<DeclaredTag>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub textures: Vec<DeclaredTexture>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub scripts: Vec<DeclaredScript>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub new_tags: Vec<DeclaredNewTag>,
}

/// The author identity an archive is signed with, when one exists.
pub struct SignContext<'a> {
    pub identity: &'a mjolnir_sign::SigningIdentity,
    /// The hub account, when known; signing works fully offline without it.
    pub author: Option<mjolnir_sign::Author>,
}

/// Write the `.mjolnir` archive: manifest and declared change list at the
/// root, containers under `content/`, the project README under `docs/`, and
/// — when a signer is given — a `signature.json` covering every other
/// member's digest, so anyone holding the archive can check exactly who
/// bundled exactly these bytes. Returns the archive size.
pub fn write_archive(
    dest: &Path,
    meta: &Meta,
    baked: &[Baked],
    readme: Option<&Path>,
    changes: Option<&str>,
    signer: Option<SignContext<'_>>,
) -> Result<u64, String> {
    let manifest = serde_json::to_string_pretty(&Manifest {
        schema_version: 1,
        name: &meta.name,
        version: &meta.version,
        kind: "content",
        summary: &meta.summary,
    })
    .map_err(|e| e.to_string())?;
    let manifest_bytes = manifest.into_bytes();
    let readme_bytes = readme.and_then(|p| std::fs::read(p).ok());

    // The member list is built once and both zipped and signed, so the
    // signature can never drift from what is written.
    let mut members: Vec<(String, &[u8])> = vec![("mjolnir.json".into(), &manifest_bytes)];
    if let Some(changes) = changes {
        members.push(("changes.json".into(), changes.as_bytes()));
    }
    for b in baked {
        members.push((format!("content/{}.utoc", b.basename), &b.built.utoc));
        members.push((format!("content/{}.ucas", b.basename), &b.built.ucas));
    }
    if let Some(bytes) = &readme_bytes {
        members.push(("docs/README.md".into(), bytes));
    }

    let signature = match signer {
        Some(s) => Some(s.identity.sign_members(
            &meta.slug,
            &meta.version,
            s.author,
            &humantime::format_rfc3339_seconds(std::time::SystemTime::now()).to_string(),
            &members,
        )?),
        None => None,
    };

    let file = std::fs::File::create(dest).map_err(|e| format!("{}: {e}", dest.display()))?;
    let mut zip = zip::ZipWriter::new(file);
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);
    let err = |e: zip::result::ZipError| format!("{}: {e}", dest.display());
    let io = |e: std::io::Error| format!("{}: {e}", dest.display());

    for (name, bytes) in &members {
        zip.start_file(name.clone(), options).map_err(err)?;
        zip.write_all(bytes).map_err(io)?;
    }
    if let Some(signature) = &signature {
        zip.start_file(mjolnir_sign::SIGNATURE_MEMBER, options)
            .map_err(err)?;
        zip.write_all(signature.as_bytes()).map_err(io)?;
    }
    zip.finish().map_err(err)?;

    std::fs::metadata(dest)
        .map(|m| m.len())
        .map_err(|e| format!("{}: {e}", dest.display()))
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
    let mut written = Vec::new();
    for b in baked {
        let base = format!("{TEST_PREFIX}{TEST_MARKER}{}", b.basename);
        let utoc = paks.join(format!("{base}.utoc"));
        // A container without a `.pak` sibling is never discovered, so an
        // empty one rides along.
        let stub = ue_iostore::pak::stub_for(&base);
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
