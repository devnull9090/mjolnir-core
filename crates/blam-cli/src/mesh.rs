//! `mjolnir mesh` — catalog the shipped meshes for the Blender asset library.
//!
//! The level exporter places bounding-box proxies for shipped meshes and
//! stores the UE object path in a custom property (docs/level_format.md). This
//! command produces that library: every `SM_` package's object path and local
//! AABB. The bounds come from the classic vertex buffers (`ExtendedBounds` is
//! zeroed in this cook, and the render-data bounds sit behind the undecoded
//! Nanite blob), so a mesh whose every LOD was cooked out for Nanite is
//! reported without bounds rather than guessed.

use std::collections::BTreeMap;
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::{Args, Subcommand};
use ue_asset::unversioned::Ctx;

use crate::Source;

#[derive(Args)]
pub struct MeshArgs {
    #[command(subcommand)]
    pub command: MeshCommand,
}

#[derive(Subcommand)]
pub enum MeshCommand {
    /// List shipped static meshes with their local-space bounds, as JSON.
    List(ListArgs),
    /// Write one mesh as glTF binary (`.glb`): every LOD, a primitive per
    /// material slot, metres and +Y up. Skeletal meshes come out in their
    /// rest pose with the bones as nodes.
    Export(ExportArgs),
}

#[derive(Args)]
pub struct ExportArgs {
    #[command(flatten)]
    pub src: Source,
    /// Substring of the mesh's content path (`SM_` or `SK_` name); the first
    /// match is exported.
    #[arg(long)]
    pub asset: String,
    /// The `.glb` to write.
    #[arg(long)]
    pub out: PathBuf,
}

#[derive(Args)]
pub struct ListArgs {
    #[command(flatten)]
    pub src: Source,
    /// Only meshes whose path contains this, case-insensitively.
    #[arg(long)]
    pub filter: Option<String>,
    /// Write the JSON here instead of stdout.
    #[arg(long)]
    pub out: Option<PathBuf>,
    /// Include skeletal (`SK_`) meshes. Off by default: decor spawning uses
    /// StaticMeshActor, which cannot show one.
    #[arg(long)]
    pub skeletal: bool,
}

pub fn run(a: MeshArgs) -> Result<()> {
    match a.command {
        MeshCommand::List(a) => list(a),
        MeshCommand::Export(a) => export(a),
    }
}

/// Every `SM_`/`SK_` package by stem: the `.uasset` chunk and the `.ubulk`
/// sibling carrying any streamed LOD buffers.
type Sighting = (
    Option<(usize, ue_iostore::ChunkEntry)>,
    Option<(usize, ue_iostore::ChunkEntry)>,
);

fn mesh_candidates(
    containers: &[ue_iostore::Container],
    skeletal: bool,
) -> BTreeMap<String, Sighting> {
    let mut candidates: BTreeMap<String, Sighting> = BTreeMap::new();
    for (ci, c) in containers.iter().enumerate() {
        for (rel, chunk_index) in &c.files {
            let full = c.full_path(rel);
            if full.contains("/Engine/") || full.contains("/Tags/") {
                continue;
            }
            let leaf = full.rsplit('/').next().unwrap_or("");
            let is_mesh = leaf.starts_with("SM_") || (skeletal && leaf.starts_with("SK_"));
            if !is_mesh {
                continue;
            }
            let (stem, is_uasset) = if let Some(s) = full.strip_suffix(".uasset") {
                (s, true)
            } else if let Some(s) = full.strip_suffix(".ubulk") {
                (s, false)
            } else {
                continue;
            };
            let entry = candidates.entry(stem.to_string()).or_default();
            if is_uasset {
                entry.0 = Some((ci, c.chunks[*chunk_index]));
            } else {
                entry.1 = Some((ci, c.chunks[*chunk_index]));
            }
        }
    }
    candidates
}

pub(crate) fn script_objects(
    containers: &[ue_iostore::Container],
    oodle: &[PathBuf],
) -> Result<ue_asset::zen::ScriptObjects> {
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .context("no global.utoc")?;
    let script_chunk = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .context("global.utoc has no ScriptObjects chunk")?;
    let script_bytes = ue_iostore::read_chunk(global, script_chunk, None, oodle)?;
    Ok(ue_asset::zen::ScriptObjects::parse(&script_bytes)?)
}

fn export(a: ExportArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let usmap = usmap()?;
    let scripts = script_objects(&containers, &oodle)?;
    let candidates = mesh_candidates(&containers, true);
    let needle = a.asset.to_ascii_lowercase();
    // A leaf or path that matches exactly wins over a longer name that merely
    // contains it (`SK_AssaultRifle` over `SK_AssaultRifle_Translucent_Default`).
    let exact = |stem: &str| {
        let lower = stem.to_ascii_lowercase();
        lower.ends_with(&format!("/{needle}")) || lower == needle
    };
    let (stem, (uasset, ubulk)) = candidates
        .iter()
        .find(|(stem, (u, _))| u.is_some() && exact(stem))
        .or_else(|| {
            candidates
                .iter()
                .find(|(stem, (u, _))| u.is_some() && stem.to_ascii_lowercase().contains(&needle))
        })
        .with_context(|| format!("no mesh matching {:?}", a.asset))?;
    let (ci, chunk) = uasset.as_ref().unwrap();
    let short = stem.trim_start_matches("../../../Meteorite/Content/");
    let leaf = short.rsplit('/').next().unwrap_or(short);
    let skeletal = leaf.starts_with("SK_");
    let wanted_class = if skeletal {
        "SkeletalMesh"
    } else {
        "StaticMesh"
    };

    let data = ue_iostore::read_chunk(&containers[*ci], chunk, None, &oodle)?;
    let package = ue_asset::zen::Package::parse(&data)?;
    let export = package
        .exports
        .iter()
        .position(|e| scripts.leaf(e.class) == Some(wanted_class))
        .with_context(|| format!("{short} has no {wanted_class} export"))?;
    let bytes = package.export_data(&data, export)?;
    let ctx = Ctx {
        usmap: &usmap,
        names: &package.names,
    };
    let bulk = match ubulk {
        Some((bi, bchunk)) => Some(ue_iostore::read_chunk(
            &containers[*bi],
            bchunk,
            None,
            &oodle,
        )?),
        None => None,
    };
    let bulk_map = ue_asset::mesh::bulk_map_of(&data);
    let say_nanite = |report: Option<&ue_asset::nanite::Report>, note: Option<&String>| {
        if let Some(r) = report {
            println!(
                "  nanite: {} page(s), {} cluster(s), {} at full detail, {} triangles",
                r.pages, r.clusters, r.leaf_clusters, r.triangles
            );
        } else if let Some(note) = note {
            println!("  nanite: not decoded ({note})");
        }
    };
    let glb = if skeletal {
        let sk = ue_asset::mesh::parse_skeletal_mesh_with_bulk_map(
            &ctx,
            bytes,
            bulk.as_deref(),
            &bulk_map,
        )?;
        say_nanite(sk.nanite_report.as_ref(), sk.nanite_note.as_ref());
        let lods: Vec<ue_asset::mesh::Lod> = sk.export_lods().into_iter().cloned().collect();
        ue_asset::gltf::write_glb(&ue_asset::gltf::MeshExport {
            name: leaf,
            materials: &sk.materials,
            lods: &lods,
            bones: &sk.bones,
        })
    } else {
        let sm = ue_asset::mesh::parse_static_mesh_with_bulk_map(
            &ctx,
            bytes,
            bulk.as_deref(),
            &bulk_map,
        )?;
        say_nanite(sm.nanite_report.as_ref(), sm.nanite_note.as_ref());
        let lods: Vec<ue_asset::mesh::Lod> = sm.export_lods().into_iter().cloned().collect();
        ue_asset::gltf::write_glb(&ue_asset::gltf::MeshExport {
            name: leaf,
            materials: &sm.materials,
            lods: &lods,
            bones: &[],
        })
    }
    .map_err(|e| anyhow::anyhow!("{short}: {e}"))?;
    std::fs::write(&a.out, &glb).with_context(|| format!("cannot write {}", a.out.display()))?;
    println!("{short}\n  -> {} ({} bytes)", a.out.display(), glb.len());
    Ok(())
}

#[derive(serde::Serialize)]
struct MeshRow {
    /// Full UE object path, ready for a `decor[].mesh` value.
    path: String,
    /// AABB corners in the mesh's local space, UE cm. Absent for a mesh whose
    /// classic buffers were all cooked out (Nanite-only).
    #[serde(skip_serializing_if = "Option::is_none")]
    min: Option<[f32; 3]>,
    #[serde(skip_serializing_if = "Option::is_none")]
    max: Option<[f32; 3]>,
    /// Vertex count of the LOD the bounds came from.
    verts: u32,
    skeletal: bool,
}

pub(crate) fn usmap() -> Result<ue_asset::Usmap> {
    static BYTES: &[u8] = include_bytes!("../../../defs/ue/Meteorite-2607-CU3.usmap");
    ue_asset::Usmap::parse(BYTES).context("the bundled usmap does not parse")
}

/// AABB over the first LOD that carries positions.
fn aabb(lods: &[ue_asset::mesh::Lod]) -> (Option<[f32; 3]>, Option<[f32; 3]>, u32) {
    for lod in lods {
        if lod.positions.len() >= 3 {
            let mut min = [f32::MAX; 3];
            let mut max = [f32::MIN; 3];
            for p in lod.positions.chunks_exact(3) {
                for k in 0..3 {
                    min[k] = min[k].min(p[k]);
                    max[k] = max[k].max(p[k]);
                }
            }
            return (Some(min), Some(max), (lod.positions.len() / 3) as u32);
        }
    }
    (None, None, 0)
}

fn list(a: ListArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let usmap = usmap()?;

    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .context("no global.utoc")?;
    let script_chunk = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .context("global.utoc has no ScriptObjects chunk")?;
    let script_bytes = ue_iostore::read_chunk(global, script_chunk, None, &oodle)?;
    let scripts = ue_asset::zen::ScriptObjects::parse(&script_bytes)?;

    // One entry per package stem: the .uasset chunk, and the .ubulk sibling
    // carrying any streamed LOD buffers.
    type Sighting = (
        Option<(usize, ue_iostore::ChunkEntry)>,
        Option<(usize, ue_iostore::ChunkEntry)>,
    );
    let mut candidates: BTreeMap<String, Sighting> = BTreeMap::new();
    for (ci, c) in containers.iter().enumerate() {
        for (rel, chunk_index) in &c.files {
            let full = c.full_path(rel);
            if full.contains("/Engine/") || full.contains("/Tags/") {
                continue;
            }
            let leaf = full.rsplit('/').next().unwrap_or("");
            let is_mesh = leaf.starts_with("SM_") || (a.skeletal && leaf.starts_with("SK_"));
            if !is_mesh {
                continue;
            }
            let (stem, is_uasset) = if let Some(s) = full.strip_suffix(".uasset") {
                (s, true)
            } else if let Some(s) = full.strip_suffix(".ubulk") {
                (s, false)
            } else {
                continue;
            };
            let entry = candidates.entry(stem.to_string()).or_default();
            if is_uasset {
                entry.0 = Some((ci, c.chunks[*chunk_index]));
            } else {
                entry.1 = Some((ci, c.chunks[*chunk_index]));
            }
        }
    }

    let filter = a.filter.as_deref().map(str::to_ascii_lowercase);
    let mut rows = Vec::new();
    let mut failed = 0usize;
    for (stem, (uasset, ubulk)) in &candidates {
        let Some((ci, chunk)) = uasset else { continue };
        let short = stem.trim_start_matches("../../../Meteorite/Content/");
        if let Some(f) = &filter {
            if !short.to_ascii_lowercase().contains(f) {
                continue;
            }
        }
        let leaf = short.rsplit('/').next().unwrap_or(short);
        let skeletal = leaf.starts_with("SK_");
        let wanted_class = if skeletal {
            "SkeletalMesh"
        } else {
            "StaticMesh"
        };

        let parsed = (|| -> Result<Option<MeshRow>> {
            let data = ue_iostore::read_chunk(&containers[*ci], chunk, None, &oodle)?;
            let package = ue_asset::zen::Package::parse(&data)?;
            let Some(export) = package
                .exports
                .iter()
                .position(|e| scripts.leaf(e.class) == Some(wanted_class))
            else {
                return Ok(None); // an SM_-named package without a mesh export
            };
            let bytes = package.export_data(&data, export)?;
            let ctx = Ctx {
                usmap: &usmap,
                names: &package.names,
            };
            let bulk = match ubulk {
                Some((bi, bchunk)) => Some(ue_iostore::read_chunk(
                    &containers[*bi],
                    bchunk,
                    None,
                    &oodle,
                )?),
                None => None,
            };
            let bulk_map = ue_asset::mesh::bulk_map_of(&data);
            let lods: Vec<ue_asset::mesh::Lod> = if skeletal {
                let sk = ue_asset::mesh::parse_skeletal_mesh_with_bulk_map(
                    &ctx,
                    bytes,
                    bulk.as_deref(),
                    &bulk_map,
                )?;
                sk.export_lods().into_iter().cloned().collect()
            } else {
                let sm = ue_asset::mesh::parse_static_mesh_with_bulk_map(
                    &ctx,
                    bytes,
                    bulk.as_deref(),
                    &bulk_map,
                )?;
                sm.export_lods().into_iter().cloned().collect()
            };
            let (min, max, verts) = aabb(&lods);
            Ok(Some(MeshRow {
                path: format!("/Game/{short}.{leaf}"),
                min,
                max,
                verts,
                skeletal,
            }))
        })();
        match parsed {
            Ok(Some(row)) => rows.push(row),
            Ok(None) => {}
            Err(_) => failed += 1,
        }
    }

    let json = serde_json::to_string_pretty(&rows)?;
    match &a.out {
        Some(path) => {
            std::fs::write(path, &json)?;
            eprintln!(
                "{} mesh(es) written to {} ({} unreadable, skipped)",
                rows.len(),
                path.display(),
                failed
            );
        }
        None => println!("{json}"),
    }
    Ok(())
}
