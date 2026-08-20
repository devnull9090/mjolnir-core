//! Baking edited tags into IoStore override containers.
//!
//! This is the one implementation of "turn patched tag bytes into a `_P`
//! container the game will load", shared by the `mjolnir` CLI, the tag
//! editor and anything else that produces mods. The container reuses the
//! exact chunk IDs of the tags it overrides — read straight out of the
//! shipped index, never derived — so the loader finds the override instead
//! of the shipped chunk. See `docs/iostore_packaging.md`.
//!
//! The output file name must end in `_P` (a patch container) or the shipped
//! chunk wins; that convention is the caller's to honour, since only the
//! caller names files.

use std::path::{Path, PathBuf};

use ue_iostore::toc::{ChunkId, Toc};
use ue_iostore::{ChunkEntry, Container};

/// The container ID every MJOLNIR override container carries: `MJOLNIR\0`
/// as big-endian bytes. Distinct from every shipped container.
pub const CONTAINER_ID: u64 = 0x4D4A_4F4C_4E49_5200;

/// One chunk to replace: where it lives in the shipped container, and the
/// bytes it should become.
///
/// Usually a tag payload, but a texture swap replaces a `.ubulk` through the
/// same path — the container does not care what the bytes mean.
pub struct ChunkEdit {
    /// For error messages, e.g. `objects/weapons/pistol/pistol.weapon`.
    pub label: String,
    /// The chunk to override in the source container.
    pub chunk: ChunkEntry,
    /// Length of the shipped payload. When the patched payload differs, the
    /// package header's `BinaryBlobSize` is rewritten to match and packed
    /// alongside.
    pub original_len: usize,
    pub patched: Vec<u8>,
}

/// What one edit became in the container.
pub struct PackedEntry {
    pub label: String,
    pub id: ChunkId,
    /// A rewritten package header rode along because the payload resized.
    pub resized: bool,
}

/// A built override container, ready to write as `<name>_P.utoc`/`.ucas`.
pub struct Built {
    pub utoc: Vec<u8>,
    pub ucas: Vec<u8>,
    pub entries: Vec<PackedEntry>,
    /// Every chunk in the container with the exact bytes it holds, for
    /// read-back verification after the files are written.
    pub expect: Vec<(ChunkId, Vec<u8>)>,
}

impl Built {
    /// True when any payload changed length. Resized containers carry
    /// rewritten package headers; that path is packable but has not been
    /// proven in game yet, so callers surface it as a warning.
    pub fn resized(&self) -> bool {
        self.entries.iter().any(|e| e.resized)
    }
}

/// Build one override container for edits whose tags all live in `source`.
///
/// Edits spanning several shipped containers become several override
/// containers: group them by source container and call this per group.
pub fn build_override(
    source: &Container,
    oodle: &[PathBuf],
    edits: &[ChunkEdit],
) -> Result<Built, String> {
    if edits.is_empty() {
        return Err("nothing to pack".into());
    }
    let source_toc =
        Toc::read(&source.utoc_path).map_err(|e| format!("{}: {e}", source.utoc_path.display()))?;

    let mut chunks: Vec<ue_iostore::pack::Entry> = Vec::new();
    let mut entries = Vec::new();
    for edit in edits {
        // The chunk ID is read straight out of the shipped index, so the
        // override addresses exactly the chunk the game already asks for.
        let slot = source_toc
            .chunk_ids
            .iter()
            .position(|c| {
                c.id == edit.chunk.chunk_id
                    && c.index == edit.chunk.chunk_index
                    && c.kind == edit.chunk.chunk_type
            })
            .ok_or_else(|| format!("{}: chunk not found in its container index", edit.label))?;
        let id = source_toc.chunk_ids[slot];
        chunks.push(ue_iostore::pack::Entry {
            id,
            data: edit.patched.clone(),
            meta: source_toc.meta(slot).unwrap_or(&[]).to_vec(),
        });

        // The package header carries `BinaryBlobSize`, which the runtime
        // exposes as a property. If the payload changed length, that copy has
        // to change with it or the tag is self-inconsistent.
        let resized = edit.patched.len() != edit.original_len;
        if resized {
            let pkg_slot = source_toc
                .chunk_ids
                .iter()
                .position(|c| c.id == id.id && c.kind == 1)
                .ok_or_else(|| format!("{}: no package chunk beside the payload", edit.label))?;
            let pkg_id = source_toc.chunk_ids[pkg_slot];
            let pkg_entry = source
                .chunks
                .iter()
                .find(|c| c.chunk_id == pkg_id.id && c.chunk_type == 1)
                .ok_or_else(|| {
                    format!("{}: package chunk missing from the container", edit.label)
                })?;
            let mut pkg = ue_iostore::read_chunk(source, pkg_entry, None, oodle)
                .map_err(|e| format!("{}: {e}", edit.label))?;

            let needle = (edit.original_len as u32).to_le_bytes();
            let at: Vec<usize> = pkg
                .windows(4)
                .enumerate()
                .filter(|(_, w)| *w == needle)
                .map(|(i, _)| i)
                .collect();
            if at.len() != 1 {
                return Err(format!(
                    "{}: expected exactly one copy of the blob size in the package \
                     header, found {}",
                    edit.label,
                    at.len()
                ));
            }
            pkg[at[0]..at[0] + 4].copy_from_slice(&(edit.patched.len() as u32).to_le_bytes());
            chunks.push(ue_iostore::pack::Entry {
                id: pkg_id,
                data: pkg,
                meta: source_toc.meta(pkg_slot).unwrap_or(&[]).to_vec(),
            });
        }

        entries.push(PackedEntry {
            label: edit.label.clone(),
            id,
            resized,
        });
    }

    let built = ue_iostore::pack::build(&source_toc, CONTAINER_ID, &chunks);
    let expect = chunks.into_iter().map(|c| (c.id, c.data)).collect();
    Ok(Built {
        utoc: built.utoc,
        ucas: built.ucas,
        entries,
        expect,
    })
}

/// A brand-new package to put in front of the game: the loader has never seen
/// its id, so the container must also register it in the package store via a
/// `ContainerHeader` chunk.
pub struct NewPackage {
    /// UE package name, e.g. `/Game/Tags/.../PG1-scenario`. The chunk ids are
    /// derived from it.
    pub package_name: String,
    /// The cooked zen package (type-1 chunk content).
    pub uasset: Vec<u8>,
    /// The bulk payload (type-2 chunk content).
    pub ubulk: Vec<u8>,
    /// Package ids this package imports, for its store entry.
    pub imported_package_ids: Vec<u64>,
    /// Chunk meta records copied from the donor package's chunks.
    pub uasset_meta: Vec<u8>,
    pub ubulk_meta: Vec<u8>,
}

/// Build a container that ADDS packages rather than overriding chunks.
///
/// The chunk ids here are **derived** from the package names
/// ([`ue_iostore::city::package_id`], validated against every shipped
/// package). Registration rides the shipped container's own `ContainerHeader`:
/// this container OVERRIDES the source's type-6 chunk with a copy that has the
/// new packages appended, because the package store provably consumes shipped
/// headers, while a mod container's own header may never be read.
pub fn build_addition(
    source: &Container,
    oodle: &[PathBuf],
    container_name: &str,
    packages: &[NewPackage],
) -> Result<Built, String> {
    if packages.is_empty() {
        return Err("nothing to pack".into());
    }
    let source_toc =
        Toc::read(&source.utoc_path).map_err(|e| format!("{}: {e}", source.utoc_path.display()))?;

    let _ = oodle;
    let container_id = ue_iostore::city::package_id(container_name);

    // The container's own header, read by the loader at mount from the chunk
    // named {container id, 0, type 6}. Its meta must be the real BLAKE3-160 of
    // its bytes — the packer computes every chunk's now; a copied hash is
    // exactly why earlier attempts were silently ignored at mount.
    let header = ue_iostore::container_header::ContainerHeader::with_import_lists(
        container_id,
        &packages
            .iter()
            .map(|p| {
                (
                    ue_iostore::city::package_id(&p.package_name),
                    p.imported_package_ids.clone(),
                )
            })
            .collect::<Vec<_>>(),
    );
    let mut chunks: Vec<ue_iostore::pack::Entry> = vec![ue_iostore::pack::Entry {
        id: ChunkId {
            id: container_id,
            index: 0,
            pad: 0,
            kind: 6,
        },
        data: header.write(),
        meta: Vec::new(),
    }];
    let mut entries = Vec::new();
    for p in packages {
        let id = ue_iostore::city::package_id(&p.package_name);
        chunks.push(ue_iostore::pack::Entry {
            id: ChunkId {
                id,
                index: 0,
                pad: 0,
                kind: 1,
            },
            data: p.uasset.clone(),
            meta: p.uasset_meta.clone(),
        });
        chunks.push(ue_iostore::pack::Entry {
            id: ChunkId {
                id,
                index: 0,
                pad: 0,
                kind: 2,
            },
            data: p.ubulk.clone(),
            meta: p.ubulk_meta.clone(),
        });
        entries.push(PackedEntry {
            label: p.package_name.clone(),
            id: ChunkId {
                id,
                index: 0,
                pad: 0,
                kind: 1,
            },
            resized: false,
        });
    }

    // Name the files in a real directory index, the way UE staging does.
    // One directory: all new packages must share it for now.
    let first = &packages[0].package_name;
    let dir = first.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
    let mount = format!(
        "../../../Meteorite/Content/{}/",
        dir.trim_start_matches("/Game/")
    );
    let mut files: Vec<(String, usize)> = Vec::new();
    for (i, p) in packages.iter().enumerate() {
        let leaf = p.package_name.rsplit('/').next().unwrap_or("");
        // Entry 0 is the header; each package contributes two chunks.
        files.push((format!("{leaf}.uasset"), 1 + i * 2));
        files.push((format!("{leaf}.ubulk"), 2 + i * 2));
    }
    let built =
        ue_iostore::pack::build_indexed(&source_toc, container_id, &chunks, Some((&mount, &files)));
    let expect = chunks.into_iter().map(|c| (c.id, c.data)).collect();
    Ok(Built {
        utoc: built.utoc,
        ucas: built.ucas,
        entries,
        expect,
    })
}

/// Read a written container back through the ordinary reader — the same path
/// the game takes — and require every packed chunk to yield exactly the
/// intended bytes. A container our own reader cannot use is not worth putting
/// in front of the game.
pub fn verify_written(
    utoc: &Path,
    oodle: &[PathBuf],
    expect: &[(ChunkId, Vec<u8>)],
) -> Result<(), String> {
    // Resolve every chunk through the perfect hash first, the way the game
    // finds it. `load_container` exposes the chunks as a list and searching
    // that list proves only that the bytes are present — a container whose
    // tables do not resolve reads perfectly here and is ignored in game,
    // silently falling back to the shipped tags.
    let toc = Toc::read(utoc).map_err(|e| format!("{}: {e}", utoc.display()))?;
    if toc.chunks_without_perfect_hash != 0 {
        return Err(format!(
            "{} chunk(s) landed in the overflow list; no shipped container uses it \
             and the game does not read it",
            toc.chunks_without_perfect_hash
        ));
    }
    for (id, _) in expect {
        toc.find_chunk_by_hash(id).ok_or_else(|| {
            format!(
                "chunk {:#018x} does not resolve through the perfect hash",
                id.id
            )
        })?;
    }

    let check = ue_iostore::load_container(utoc).map_err(|e| format!("{}: {e}", utoc.display()))?;
    for (id, want) in expect {
        let chunk = check
            .chunks
            .iter()
            .find(|c| c.chunk_id == id.id && c.chunk_index == id.index && c.chunk_type == id.kind)
            .ok_or_else(|| format!("chunk {:#018x} missing from the written container", id.id))?;
        let got = ue_iostore::read_chunk(&check, chunk, None, oodle)
            .map_err(|e| format!("{}: {e}", utoc.display()))?;
        if &got != want {
            return Err(format!(
                "chunk {:#018x} read back {} bytes that do not match the {} packed",
                id.id,
                got.len(),
                want.len()
            ));
        }
    }
    Ok(())
}
