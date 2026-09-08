//! `mjolnir extract`: write tags out of the containers as files, in the layout
//! Blam tooling expects — `objects/weapons/rifle/assault_rifle.weapon` rather
//! than the cooked `assault_rifle-weapon.ubulk`.
//!
//! Mod-aware by default: when several containers carry the same tag, the one
//! mounted later wins, which is how an override reaches the game; so what comes
//! out is what the game would load, mods included. `--shipped-only` skips the
//! override containers and gives the game's own tags.
//!
//! The output is copyrighted game content. Keep it local; the repository does
//! not take tag data.

use std::collections::BTreeMap;
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Args;
use ue_iostore::Container;

use crate::index::{self, TagEntry};

#[derive(Args)]
pub struct ExtractArgs {
    #[command(flatten)]
    src: crate::Source,
    /// Output root. Required unless `--dry-run` is given.
    #[arg(long)]
    out: Option<PathBuf>,
    /// Case-insensitive substring of the tag path.
    #[arg(long)]
    filter: Option<String>,
    /// Restrict to these group directory names, e.g. `weapon`. Repeatable.
    #[arg(long = "group")]
    groups: Vec<String>,
    /// Stop after this many tags; 0 means no limit.
    #[arg(long, default_value_t = 0)]
    limit: usize,
    /// List what would be written and stop.
    #[arg(long)]
    dry_run: bool,
    /// Only the game's own containers: skip override (`_P`) and MJOLNIR
    /// containers, so a tag comes out as shipped rather than as a mod left it.
    #[arg(long)]
    shipped_only: bool,
    /// Write a tag only if it parses and its values walk exactly; report the
    /// rest rather than writing them.
    #[arg(long)]
    verify: bool,
}

/// Whether a container is a mod's rather than the game's own.
fn is_override(c: &Container) -> bool {
    let name = c
        .utoc_path
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default();
    name.contains("MJOLNIR") || name.to_ascii_lowercase().ends_with("_p.utoc")
}

/// The path a tag takes in a Blam kit: its folder below `Tags/`, then
/// `<name>.<group>`.
fn kit_path(rel: &str, group: &str) -> String {
    let (dir, file) = match rel.rsplit_once('/') {
        Some((d, f)) => (Some(d), f),
        None => (None, rel),
    };
    let stem = file.strip_suffix(".ubulk").unwrap_or(file);
    let suffix = format!("-{group}");
    let name = stem.strip_suffix(suffix.as_str()).unwrap_or(stem);
    match dir {
        Some(d) => format!("{d}/{name}.{group}"),
        None => format!("{name}.{group}"),
    }
}

/// A tag file must parse and its values must consume the payload exactly.
fn walks_exactly(data: &[u8]) -> Result<(), String> {
    let tag = blam_tag::TagFile::parse(data, Some(data.len())).map_err(|e| e.to_string())?;
    let layout = tag.layout().map_err(|e| e.to_string())?;
    let block = tag.read_data(&layout).map_err(|e| e.to_string())?;
    let payload = tag.data().map(|d| d.size as usize).unwrap_or(data.len());
    if block.consumed != payload {
        return Err(format!(
            "walked {} of {payload} payload bytes",
            block.consumed
        ));
    }
    Ok(())
}

pub fn run(a: ExtractArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let needle = a.filter.as_deref().map(str::to_ascii_lowercase);
    let groups: Vec<String> = a.groups.iter().map(|g| g.to_ascii_lowercase()).collect();

    // Later containers win the same path: that is how an override reaches the
    // game, so it is what comes out here.
    let mut chosen: BTreeMap<String, &TagEntry> = BTreeMap::new();
    for e in &idx.tags {
        if a.shipped_only && is_override(&idx.containers[e.container]) {
            continue;
        }
        let Some((_, rel)) = e.path.split_once("/Tags/") else {
            continue;
        };
        if let Some(n) = &needle {
            if !e.path.to_ascii_lowercase().contains(n) {
                continue;
            }
        }
        if !groups.is_empty() && !groups.contains(&e.group.to_ascii_lowercase()) {
            continue;
        }
        let out_rel = kit_path(rel, &e.group);
        let replace = chosen
            .get(&out_rel)
            .is_none_or(|prev| prev.container <= e.container);
        if replace {
            chosen.insert(out_rel, e);
        }
    }
    let mut targets: Vec<(String, &TagEntry)> = chosen.into_iter().collect();
    if a.limit > 0 {
        targets.truncate(a.limit);
    }
    let total: u64 = targets.iter().map(|(_, e)| e.chunk.length).sum();
    println!(
        "tags matched: {}  ({:.1} MiB)",
        targets.len(),
        total as f64 / (1024.0 * 1024.0)
    );

    if a.dry_run {
        for (rel, e) in targets.iter().take(50) {
            println!("  {rel}\t{}", e.chunk.length);
        }
        if targets.len() > 50 {
            println!("  ... {} more", targets.len() - 50);
        }
        return Ok(());
    }

    let out = a
        .out
        .as_ref()
        .context("--out is required unless --dry-run is set")?;
    let oodle = a.src.oodle_roots();
    let mut written = 0usize;
    let mut rejected = 0usize;
    for (rel, e) in &targets {
        let data = idx.read(e, None, &oodle)?;
        if a.verify {
            if let Err(why) = walks_exactly(&data) {
                rejected += 1;
                eprintln!("  [reject] {rel}: {why}");
                continue;
            }
        }
        let dest = out.join(rel);
        if let Some(parent) = dest.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("creating {}", parent.display()))?;
        }
        std::fs::write(&dest, &data).with_context(|| format!("writing {}", dest.display()))?;
        written += 1;
        if written.is_multiple_of(500) {
            println!("  ... {written}/{}", targets.len());
        }
    }
    println!(
        "wrote {written} tag(s) to {}{}",
        out.display(),
        if rejected > 0 {
            format!(", {rejected} rejected")
        } else {
            String::new()
        }
    );
    println!("  This is game content. Keep it local; the repository does not take tag data.");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn kit_paths_drop_the_group_suffix_and_extension() {
        assert_eq!(
            kit_path(
                "objects/weapons/Rifle/assault_rifle/assault_rifle-weapon.ubulk",
                "weapon"
            ),
            "objects/weapons/Rifle/assault_rifle/assault_rifle.weapon"
        );
        assert_eq!(
            kit_path(
                "Levels/Halo1/Solo/A30/_Generated_/a30-scenario.ubulk",
                "scenario"
            ),
            "Levels/Halo1/Solo/A30/_Generated_/a30.scenario"
        );
        assert_eq!(
            kit_path("globals-globals.ubulk", "globals"),
            "globals.globals"
        );
        // A name that does not end in the group suffix keeps its whole stem.
        assert_eq!(kit_path("x/odd.ubulk", "weapon"), "x/odd.weapon");
    }
}
