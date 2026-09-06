//! `mjolnir new-tag`: put a brand-new tag package in front of the game.
//!
//! A tag is one UE package — a cooked `.uasset` wrapper plus the `.ubulk` tag
//! body — and its identity (the chunk ids the game addresses it by, the
//! package-store entry, the export hash) all derive from its name. The wrapper
//! is built from scratch for every group (`ue_asset::tagwrap`): its preload
//! list from the references the body actually carries, its Unreal binding
//! (`AssetReference`) and its model variants from the donor's wrapper unless
//! overridden. So the new path can be anything, and the body can be edited on
//! the way with `--set`.
//!
//! Measured 2026-09-05: a package built this way is registered by the mod
//! container's own `ContainerHeader`, resolved by name the moment a tag
//! references it, and loaded — with `cooked_header_size` left wrong on purpose
//! it still loaded, so that field is not consulted for tag packages.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use anyhow::{bail, ensure, Context, Result};
use blam_tag::TagFile;
use clap::Args;
use ue_asset::package::ZenPackage;
use ue_asset::tagwrap::{self, ImportTarget};

use crate::index;

#[derive(Args)]
pub struct NewTagArgs {
    #[command(flatten)]
    src: crate::Source,
    /// Group directory name of the donor and the new tag, e.g. `collision_model`.
    #[arg(long)]
    group: String,
    /// Substring of the donor tag's path. The donor supplies the body (edited
    /// by `--set`) and, for groups bound to Unreal, the binding.
    #[arg(long)]
    from: String,
    /// The new tag's path without group or extension, e.g.
    /// `objects\characters\marine\marine_clone`.
    #[arg(long)]
    to: String,
    /// A field to change in the new tag's body, as `path=value`. Repeatable.
    #[arg(long = "set")]
    sets: Vec<String>,
    /// The Unreal asset the new tag is bound to, as a package path
    /// (`/Game/Blueprints/.../BP_Thing`); default: the donor's. Object groups
    /// and `effect` bind to the Blueprint's class, sound-like groups to the
    /// asset itself.
    #[arg(long)]
    asset_reference: Option<String>,
    /// Directory to write the container triplet into. Default: the Paks folder
    /// itself when `--install-test` is given, else the current directory.
    #[arg(long)]
    out_dir: Option<PathBuf>,
    /// Container base name; `_P` and the extensions are appended. Default
    /// `pakchunk996-MJOLNIRNEW-<leaf>`.
    #[arg(long)]
    name: Option<String>,
    /// Write straight into the game's Paks folder with a stub `.pak` sibling,
    /// ready for the next launch.
    #[arg(long)]
    install_test: bool,
    /// Measurement aid: overwrite the wrapper's `cooked_header_size` with this
    /// value, to test whether the game reads it.
    #[arg(long, hide = true)]
    cooked_header_size: Option<u32>,
}

/// Groups whose `AssetReference` names a plain asset rather than a Blueprint
/// class.
const ASSET_BOUND_GROUPS: [&str; 5] = [
    "sound",
    "sound_looping",
    "sound_combiner",
    "cinematic",
    "damage_response_definition",
];

pub fn run(a: NewTagArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group
        .get(a.group.as_str())
        .with_context(|| format!("unknown group {:?}", a.group))?;
    let donor_entry = entries
        .iter()
        .find(|e| e.path.contains(&a.from))
        .copied()
        .with_context(|| format!("no {} tag matching {:?}", a.group, a.from))?;
    let usmap = crate::embedded_usmap()?;

    let original = idx.read(donor_entry, None, &a.src.oodle_roots())?;
    println!("donor    {}", donor_entry.path);
    println!("  body   {} bytes", original.len());

    let file = crate::apply_sets(&original, &a.sets)?;
    let tag = TagFile::parse(&file, Some(file.len()))?;
    let l = tag.layout()?;
    let block = tag.read_data(&l)?;
    let payload = tag.data().context("the tag has no bdat section")?;
    if block.consumed != payload.size as usize {
        bail!("the edited tag no longer walks exactly");
    }

    // The donor's wrapper: the Unreal-side facts a body cannot tell us.
    let source = &idx.containers[donor_entry.container];
    let toc = ue_iostore::toc::Toc::read(&source.utoc_path)
        .map_err(|e| anyhow::anyhow!("{}: {e}", source.utoc_path.display()))?;
    let uasset_chunk = source
        .chunks
        .iter()
        .find(|c| c.chunk_id == donor_entry.chunk.chunk_id && c.chunk_type == 1)
        .context("the donor has no package chunk beside its payload")?;
    let donor_uasset = ue_iostore::read_chunk(source, uasset_chunk, None, &a.src.oodle_roots())?;
    let meta_of = |kind: u8| -> Vec<u8> {
        toc.chunk_ids
            .iter()
            .position(|c| c.id == donor_entry.chunk.chunk_id && c.kind == kind)
            .and_then(|slot| toc.meta(slot))
            .map(<[u8]>::to_vec)
            .unwrap_or_default()
    };
    let donor_pkg =
        ZenPackage::parse(&donor_uasset).map_err(|e| anyhow::anyhow!("donor package: {e}"))?;
    let donor =
        tagwrap::read(&donor_pkg, usmap).map_err(|e| anyhow::anyhow!("donor wrapper: {e}"))?;

    // The new identity, spelled the way the cooker spells packages.
    let to = a.to.trim().replace('\\', "/");
    let to = to.trim_matches('/');
    let new_pkg = format!("/Game/Tags/{to}-{}", a.group);
    let new_leaf = new_pkg.rsplit('/').next().unwrap_or("").to_string();
    // Only the game's own containers count as "shipped": an earlier run of this
    // command leaves its own indexed container in the Paks folder.
    let shipped_has_leaf = entries.iter().any(|e| {
        let container = idx.containers[e.container]
            .utoc_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();
        !container.contains("MJOLNIR")
            && !container.to_ascii_lowercase().ends_with("_p.utoc")
            && e.path
                .to_ascii_lowercase()
                .contains(&format!("/{}.ubulk", new_leaf.to_ascii_lowercase()))
    });
    ensure!(
        !shipped_has_leaf,
        "a shipped tag already has the leaf {new_leaf:?}"
    );

    // The preload list: every tag the body references that exists in this
    // installation. Dangling references are ordinary (1,381 shipped instances
    // point at nothing) and are only reported.
    let cc_to_group = group_directories(&idx, &a.src.oodle_roots())?;
    let by_lower: HashMap<String, String> = idx
        .containers
        .iter()
        .flat_map(|c| c.files.keys())
        .filter(|p| p.ends_with(".ubulk"))
        .map(|p| {
            let full = p
                .trim_start_matches("../")
                .replace("Meteorite/Content/", "/Game/");
            let full = full.trim_end_matches(".ubulk").to_string();
            (full.to_ascii_lowercase(), full)
        })
        .collect();
    let mut cooked_refs: Vec<ImportTarget> = Vec::new();
    let mut dangling = 0usize;
    for (cc, path) in blam_tag::refs::tgrf_refs(&file, |cc| cc_to_group.contains_key(cc)) {
        let group = &cc_to_group[&cc];
        let want = format!(
            "/game/tags/{}-{group}",
            path.replace('\\', "/").to_ascii_lowercase()
        );
        match by_lower.get(&want) {
            Some(real) => {
                let target = ImportTarget::asset(real);
                if !cooked_refs.contains(&target) {
                    cooked_refs.push(target);
                }
            }
            None => dangling += 1,
        }
    }

    let asset_reference = match &a.asset_reference {
        Some(pkg) if ASSET_BOUND_GROUPS.contains(&a.group.as_str()) => {
            Some(ImportTarget::asset(pkg))
        }
        Some(pkg) => Some(ImportTarget::blueprint_class(pkg)),
        None => donor.spec.asset_reference.clone(),
    };
    let spec = tagwrap::WrapperSpec {
        group: a.group.clone(),
        package_path: new_pkg.clone(),
        ubulk_len: file.len() as u64,
        asset_reference,
        cooked_refs,
        spawn_per_instance: donor.spec.spawn_per_instance,
        model_region_string_table: donor.spec.model_region_string_table.clone(),
        runtime_variants: donor.spec.runtime_variants.clone(),
    };
    println!("package  {}\n      -> {new_pkg}", donor_pkg.name());
    println!(
        "  id     {:#018x}  preloads {} tag(s){}",
        ue_iostore::city::package_id(&new_pkg),
        spec.cooked_refs.len(),
        if dangling > 0 {
            format!(", {dangling} reference(s) point at nothing shipped")
        } else {
            String::new()
        }
    );
    if let Some(t) = &spec.asset_reference {
        println!("  bound  {}", t.package);
    }
    if !spec.runtime_variants.is_empty() {
        println!("  variants {}", spec.runtime_variants.len());
    }

    let mut built_pkg =
        tagwrap::build(&spec, usmap).map_err(|e| anyhow::anyhow!("wrapper: {e}"))?;
    if let Some(cooked) = a.cooked_header_size {
        println!(
            "  cooked header size {} -> {cooked} (measurement)",
            built_pkg.cooked_header_size
        );
        built_pkg.cooked_header_size = cooked;
    }
    let uasset = built_pkg.write();
    let imported: Vec<u64> = built_pkg
        .imported_package_names
        .names
        .iter()
        .zip(&built_pkg.imported_package_name_numbers)
        .map(|(base, n)| ue_iostore::city::package_id(&tagwrap::fname_join(base, *n)))
        .collect();

    let base = a
        .name
        .clone()
        .unwrap_or_else(|| format!("pakchunk996-MJOLNIRNEW-{}", new_leaf.replace('-', "_")));
    let built = blam_pack::build_addition(
        source,
        &a.src.oodle_roots(),
        &base,
        &[blam_pack::NewPackage {
            package_name: new_pkg.clone(),
            uasset,
            ubulk: file.clone(),
            imported_package_ids: imported,
            uasset_meta: meta_of(1),
            ubulk_meta: meta_of(2),
        }],
    )
    .map_err(|e| anyhow::anyhow!(e))?;

    let out_dir = match (&a.out_dir, a.install_test) {
        (Some(dir), _) => dir.clone(),
        (None, true) => a.src.paks.clone(),
        (None, false) => PathBuf::from("."),
    };
    std::fs::create_dir_all(&out_dir)?;
    let name = format!("{base}_P");
    let utoc = out_dir.join(format!("{name}.utoc"));
    let ucas = out_dir.join(format!("{name}.ucas"));
    let stage = |target: &Path, bytes: &[u8]| -> Result<()> {
        let tmp = target.with_extension("mjolnir-tmp");
        std::fs::write(&tmp, bytes)?;
        std::fs::rename(&tmp, target).with_context(|| {
            format!(
                "installing {} — if the game is running, quit it first",
                target.display()
            )
        })
    };
    stage(&utoc, &built.utoc)?;
    stage(&ucas, &built.ucas)?;
    blam_pack::verify_written(&utoc, &a.src.oodle_roots(), &built.expect)
        .map_err(|e| anyhow::anyhow!(e))?;
    println!("  wrote  {} ({} bytes)", utoc.display(), built.utoc.len());
    println!("  wrote  {} ({} bytes)", ucas.display(), built.ucas.len());
    // A .utoc/.ucas pair never mounts without a .pak sibling.
    let pak = out_dir.join(format!("{name}.pak"));
    std::fs::write(&pak, crate::level::stub_pak_bytes(&a.src.paks)?)?;
    println!("  wrote  {} (stub)", pak.display());

    println!(
        "\n  Nothing references {new_leaf} yet. Repoint a shipped tag at `{}:{}` with\n  `mjolnir pack --set`, launch a mission that loads it, then run\n  `mjolnir live tags --filter {}` — the tag table lists it if the game did.",
        tag.header.group.as_str(),
        to.replace('/', "\\"),
        to.rsplit('/').next().unwrap_or(to)
    );
    if !a.install_test {
        println!("  Install: copy all three files into the game's Paks folder.");
    }
    Ok(())
}

/// Four-CC → group directory name, from the header of the smallest tag of each
/// group the installation ships. Self-contained: no definition file needed.
fn group_directories(idx: &index::Index, oodle: &[PathBuf]) -> Result<HashMap<String, String>> {
    let mut out = HashMap::new();
    for (group, entries) in idx.by_group() {
        let Some(smallest) = entries.iter().min_by_key(|e| e.chunk.length) else {
            continue;
        };
        let Ok(bytes) = idx.read(smallest, None, oodle) else {
            continue;
        };
        if let Ok(tag) = TagFile::parse(&bytes, Some(bytes.len())) {
            out.insert(tag.header.group.as_str(), group.to_string());
        }
    }
    Ok(out)
}
