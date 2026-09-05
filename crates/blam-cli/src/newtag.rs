//! `mjolnir new-tag`: put a brand-new tag package in front of the game.
//!
//! A tag is one UE package — a cooked `.uasset` wrapper plus the `.ubulk` tag
//! body — and its identity (the chunk ids the game addresses it by, the
//! package-store entry, the export hash) all derive from its name. Today the
//! wrapper is produced by **same-length rename surgery on a shipped donor of
//! the same group** (`crate::rename`): the donor's two strings are overwritten
//! and its hashes recomputed, so every offset in the summary stays true. That
//! is why the new path must have exactly the donor's length, segment for
//! segment. A wrapper *serializer* that lifts the constraint is the next step;
//! this command is the one that lets the load model be measured first — does
//! the game register and resolve a package it has never shipped?
//!
//! The readout is `mjolnir live tags --filter <leaf>` once a mission that
//! references the new tag is loaded: the simulation's own tag table either
//! lists it or does not.

use std::path::{Path, PathBuf};

use anyhow::{bail, ensure, Context, Result};
use blam_tag::TagFile;
use clap::Args;

use crate::index;

#[derive(Args)]
pub struct NewTagArgs {
    #[command(flatten)]
    src: crate::Source,
    /// Group directory name of the donor and the new tag, e.g. `collision_model`.
    #[arg(long)]
    group: String,
    /// Substring of the donor tag's path.
    #[arg(long)]
    from: String,
    /// The new tag's path without group or extension, e.g.
    /// `objects\characters\marinf\marinf`. Must be exactly as long as the
    /// donor's (same-length surgery; see the module doc).
    #[arg(long)]
    to: String,
    /// A field to change in the new tag's body, as `path=value`. Repeatable.
    #[arg(long = "set")]
    sets: Vec<String>,
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

    // The donor's wrapper and its chunk metas.
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
    let donor = ue_asset::zen::Package::parse(&donor_uasset)
        .map_err(|e| anyhow::anyhow!("donor package: {e}"))?;
    let old_pkg = donor.name.clone();
    let old_leaf = old_pkg
        .rsplit('/')
        .next()
        .context("donor package name has no leaf")?
        .to_string();

    // The new identity, spelled the way the cooker spells packages.
    let to = a.to.trim().replace('\\', "/");
    let to = to.trim_matches('/');
    let new_pkg = format!("/Game/Tags/{to}-{}", a.group);
    let new_leaf = new_pkg.rsplit('/').next().unwrap_or("").to_string();
    ensure!(
        old_pkg.len() == new_pkg.len(),
        "the new path must be exactly as long as the donor's (same-length surgery):\n  {old_pkg}\n  {new_pkg}"
    );
    ensure!(
        old_leaf.len() == new_leaf.len(),
        "the new leaf {new_leaf:?} must be as long as the donor's {old_leaf:?}"
    );
    ensure!(
        !idx.by_group()
            .get(a.group.as_str())
            .is_some_and(|es| es.iter().any(|e| e
                .path
                .to_ascii_lowercase()
                .contains(&format!("/{}.ubulk", new_leaf.to_ascii_lowercase())))),
        "a shipped tag already has the leaf {new_leaf:?}"
    );

    let imported: Vec<u64> = donor
        .imported_package_names
        .iter()
        .map(|n| ue_iostore::city::package_id(n))
        .collect();
    println!("package  {old_pkg}\n      -> {new_pkg}");
    println!(
        "  id     {:#018x}  imports {} package(s)",
        ue_iostore::city::package_id(&new_pkg),
        imported.len()
    );

    let uasset = crate::rename::clone_tag_uasset(
        &donor_uasset,
        &[(old_leaf, new_leaf.clone()), (old_pkg, new_pkg.clone())],
        original.len(),
        file.len(),
    )?;

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
        group_four_cc(&file).unwrap_or_default(),
        to.replace('/', "\\"),
        to.rsplit('/').next().unwrap_or(to)
    );
    if !a.install_test {
        println!("  Install: copy all three files into the game's Paks folder.");
    }
    Ok(())
}

fn group_four_cc(file: &[u8]) -> Option<String> {
    let tag = TagFile::parse(file, Some(file.len())).ok()?;
    Some(tag.header.group.as_str())
}
