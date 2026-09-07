//! `mjolnir new-tag`: put a brand-new tag package in front of the game.
//!
//! The package itself is `blam_pack::newtag` — the wrapper built from scratch
//! for the group, the preload list from the body's own references, the Unreal
//! binding and model variants from the donor unless overridden. This command
//! finds the donor, applies `--set` edits to its body, resolves the body's
//! references against the installation, and writes the container triplet.
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
    let uasset_chunk = source
        .chunks
        .iter()
        .find(|c| c.chunk_id == donor_entry.chunk.chunk_id && c.chunk_type == 1)
        .context("the donor has no package chunk beside its payload")?;
    let donor_uasset = ue_iostore::read_chunk(source, uasset_chunk, None, &a.src.oodle_roots())?;
    let (uasset_meta, ubulk_meta) =
        blam_pack::newtag::donor_chunk_meta(source, donor_entry.chunk.chunk_id)
            .map_err(|e| anyhow::anyhow!(e))?;

    // Only the game's own containers count as "shipped": an earlier run of this
    // command leaves its own indexed container in the Paks folder.
    let to = blam_pack::newtag::normalize_path(&a.to).map_err(|e| anyhow::anyhow!(e))?;
    let new_leaf = format!("{}-{}", to.rsplit('/').next().unwrap_or(&to), a.group);
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
    // installation, by four-CC and path.
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
    let resolve = |cc: &str, path: &str| -> Option<String> {
        let group = cc_to_group.get(cc)?;
        let want = format!(
            "/game/tags/{}-{group}",
            path.replace('\\', "/").to_ascii_lowercase()
        );
        by_lower.get(&want).cloned()
    };

    let built_tag = blam_pack::newtag::build(
        &blam_pack::newtag::NewTag {
            group: &a.group,
            path: &to,
            body: &file,
            donor_uasset: &donor_uasset,
            asset_reference: a.asset_reference.as_deref(),
        },
        usmap,
        resolve,
    )
    .map_err(|e| anyhow::anyhow!(e))?;
    let new_pkg = built_tag.package_name.clone();
    let donor_pkg =
        ZenPackage::parse(&donor_uasset).map_err(|e| anyhow::anyhow!("donor package: {e}"))?;
    println!("package  {}\n      -> {new_pkg}", donor_pkg.name());
    println!(
        "  id     {:#018x}  preloads {} tag(s){}",
        ue_iostore::city::package_id(&new_pkg),
        built_tag.preloads,
        if built_tag.dangling > 0 {
            format!(
                ", {} reference(s) point at nothing shipped",
                built_tag.dangling
            )
        } else {
            String::new()
        }
    );
    if let Some(t) = &built_tag.bound {
        println!("  bound  {t}");
    }
    if built_tag.variants > 0 {
        println!("  variants {}", built_tag.variants);
    }

    let mut package = built_tag.package;
    package.uasset_meta = uasset_meta;
    package.ubulk_meta = ubulk_meta;
    if let Some(cooked) = a.cooked_header_size {
        let mut pkg = ZenPackage::parse(&package.uasset).map_err(|e| anyhow::anyhow!("{e}"))?;
        println!(
            "  cooked header size {} -> {cooked} (measurement)",
            pkg.cooked_header_size
        );
        pkg.cooked_header_size = cooked;
        package.uasset = pkg.write();
    }

    let base = a
        .name
        .clone()
        .unwrap_or_else(|| format!("pakchunk996-MJOLNIRNEW-{}", new_leaf.replace('-', "_")));
    let built = blam_pack::build_addition(source, &a.src.oodle_roots(), &base, &[package])
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
    std::fs::write(&pak, ue_iostore::pak::stub_for(&name))?;
    println!("  wrote  {} (stub)", pak.display());

    println!(
        "\n  Nothing references {new_leaf} yet. Repoint a shipped tag at `{}:{}` with\n  `mjolnir pack --set`, launch a mission that loads it, then run\n  `mjolnir live tags --filter {}` — the tag table lists it if the game did.",
        tag.header.group.as_str(),
        to.replace('/', "\\"),
        to.rsplit('/').next().unwrap_or(&to)
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
