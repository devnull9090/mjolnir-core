//! `mjolnir cache` — read another Halo game's `.map` cache files: which game
//! and build a map is from, its tags, and the staging directory the
//! conversion pipeline (tools/level/convert_ce_map.sh) builds a Campaign
//! Evolved map from.
//!
//! The pipeline branches on `cache info --field stager`: `halo2ue` for the
//! Halo 1 PC and Custom Edition builds (HalcyonRing's exporter, unchanged),
//! `blam-cache` for MCC's Halo 2 (`cache stage`). Every other game is
//! identified and refused with its name, so a Halo 3 map fails early and says
//! why rather than half-converting.

use std::io::Read;
use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result};
use blam_cache::detect::{self, Identity, HEADER_PROBE};
use blam_cache::h2;
use clap::{Args, Subcommand, ValueEnum};

#[derive(Args)]
pub struct CacheArgs {
    #[command(subcommand)]
    pub command: CacheCommand,
}

#[derive(Clone, Copy, ValueEnum)]
pub enum Field {
    /// `halo1`, `halo2`, `halo3`, `halo3odst`, `haloreach`, `halo4`, `halo2a`.
    Game,
    /// `xbox`, `pc`, `ce`, `classic`, `mcc`.
    Build,
    /// `halo2ue`, `blam-cache`, or `none`.
    Stager,
    Name,
}

#[derive(Subcommand)]
pub enum CacheCommand {
    /// Identify a cache file: game, build, engine version, map name.
    Info {
        /// The `.map` file.
        file: PathBuf,
        /// Print one field alone (for scripts).
        #[arg(long, value_enum)]
        field: Option<Field>,
        /// Print the identity as JSON.
        #[arg(long)]
        json: bool,
    },
    /// List an MCC Halo 2 map's tags (those with data in the map, and with
    /// `--all` the index's placeholders for tags in shared.map).
    Tags {
        file: PathBuf,
        /// Only this group (`sbsp`, `scnr`, `shad`, ...).
        #[arg(long)]
        group: Option<String>,
        #[arg(long)]
        all: bool,
    },
    /// Stage an MCC Halo 2 map for conversion: collision, render geometry,
    /// materials, textures and placements in the layout halo2ue writes for
    /// Halo 1 (docs/h2_map_conversion.md).
    Stage {
        /// The scenario `.map` (`halo2/h2_maps_win64_dx11/lockout.map`).
        map: PathBuf,
        /// Where to write the staging (created; must not exist yet).
        #[arg(long)]
        out: PathBuf,
        /// The folder holding `shared.map` and `textures.dat` (default: the
        /// map's own).
        #[arg(long)]
        resources: Option<PathBuf>,
        /// Replace `--out` when it is an earlier Halo 2 staging (its
        /// manifest says so); any other existing folder is still refused.
        #[arg(long)]
        replace: bool,
    },
}

pub fn run(a: CacheArgs) -> Result<()> {
    match a.command {
        CacheCommand::Info { file, field, json } => info(&file, field, json),
        CacheCommand::Tags { file, group, all } => tags(&file, group.as_deref(), all),
        CacheCommand::Stage { map, out, resources, replace } => stage(&map, &out, resources.as_deref(), replace),
    }
}

/// Identify `file` from its header.
pub fn identify(file: &Path) -> Result<Identity> {
    let len = std::fs::metadata(file).with_context(|| format!("reading {}", file.display()))?.len();
    let mut head = Vec::with_capacity(HEADER_PROBE);
    std::fs::File::open(file)
        .with_context(|| format!("opening {}", file.display()))?
        .take(HEADER_PROBE as u64)
        .read_to_end(&mut head)?;
    detect::identify(&head, len).map_err(|e| anyhow::anyhow!("{}: {e}", file.display()))
}

fn info(file: &Path, field: Option<Field>, as_json: bool) -> Result<()> {
    let id = identify(file)?;
    let stager = id.stager().unwrap_or("none");
    if let Some(f) = field {
        println!(
            "{}",
            match f {
                Field::Game => id.game.slug().to_string(),
                Field::Build => id.build.slug().to_string(),
                Field::Stager => stager.to_string(),
                Field::Name => id.name.clone(),
            }
        );
        return Ok(());
    }
    if as_json {
        let v = serde_json::json!({
            "game": id.game.slug(), "title": id.game.title(), "build": id.build.slug(),
            "version": id.version, "header_size": id.header_size, "name": id.name,
            "scenario": id.scenario, "compressed": id.compressed, "stager": stager,
        });
        println!("{}", serde_json::to_string_pretty(&v)?);
        return Ok(());
    }
    println!("{}", file.display());
    println!("  game      {} ({})", id.game.title(), id.game.slug());
    println!("  build     {} (cache version {})", id.build.slug(), id.version);
    println!("  name      {}", id.name);
    if let Some(s) = &id.scenario {
        println!("  scenario  {s}");
    }
    println!("  header    {:#x} bytes{}", id.header_size, if id.compressed { ", body compressed" } else { "" });
    match id.stager() {
        Some(s) if id.game == detect::Game::Halo1 && id.build == detect::Build::Mcc => println!(
            "  converts  through {s} when padded to its tag base (HEK-built maps); a retail MCC map fails there"
        ),
        Some(s) => println!("  converts  yes, staged by {s}"),
        None => println!("  converts  not yet: no stager reads {} {} maps", id.game.title(), id.build.slug()),
    }
    Ok(())
}

fn require_h2_mcc(file: &Path) -> Result<Identity> {
    let id = identify(file)?;
    if id.game != detect::Game::Halo2 || id.build != detect::Build::Mcc {
        bail!(
            "{} is a {} {} map; this command reads MCC Halo 2 maps (Halo 1 stages through halo2ue)",
            file.display(),
            id.game.title(),
            id.build.slug()
        );
    }
    Ok(id)
}

fn tags(file: &Path, group: Option<&str>, all: bool) -> Result<()> {
    require_h2_mcc(file)?;
    let map = h2::CacheFile::open(file).map_err(|e| anyhow::anyhow!("{e}"))?;
    let mut shown = 0;
    for e in &map.tags {
        if e.datum == u32::MAX || (!all && e.address.is_none()) {
            continue;
        }
        if group.is_some_and(|g| e.group.name() != g) {
            continue;
        }
        let place = if e.address.is_some() { "" } else { "  (shared)" };
        println!("{:<4}  {:08x}  {:>8}  {}{place}", e.group.name(), e.datum, e.size, e.name);
        shown += 1;
    }
    println!("{shown} tag(s)");
    Ok(())
}

/// Whether `dir` is a staging this command wrote (its manifest's `source`).
fn is_h2_staging(dir: &Path) -> bool {
    std::fs::read(dir.join("manifest.json"))
        .ok()
        .and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok())
        .is_some_and(|m| m["source"] == "halo2_mcc")
}

fn stage(map: &Path, out: &Path, resources: Option<&Path>, replace: bool) -> Result<()> {
    require_h2_mcc(map)?;
    if out.exists() {
        // A fresh directory every time, so a bitmap renamed between runs
        // never leaves a stale file beside the new ones.
        if !(replace && is_h2_staging(out)) {
            bail!(
                "{} already exists; staging writes a fresh directory (--replace clears an earlier Halo 2 staging)",
                out.display()
            );
        }
        std::fs::remove_dir_all(out).with_context(|| format!("clearing {}", out.display()))?;
    }
    let cache = h2::Cache::open(map, resources).map_err(|e| anyhow::anyhow!("{e}"))?;
    if cache.shared.is_none() {
        println!("warning: no shared.map beside the map; weapons, vehicles and most shaders live there");
    }
    if cache.textures.is_none() {
        println!("warning: no textures.dat beside the map; bitmaps will be missing");
    }
    let s = h2::stage::stage(&cache, out).map_err(|e| anyhow::anyhow!("{e}"))?;
    println!("staged {} -> {}", cache.map.header.scenario, out.display());
    println!(
        "  collision  {} BSP surface(s), {} instance(s) adding {} surface(s)",
        s.bsp_surfaces, s.instances, s.instance_surfaces
    );
    let counts: Vec<String> = s.placements.iter().map(|(k, v)| format!("{v} {k}")).collect();
    println!("  placements {}", counts.join(", "));
    for n in &s.notes {
        println!("  note: {n}");
    }
    Ok(())
}
