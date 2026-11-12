//! `mjolnir dev`: local builds that take precedence over hub content.
//!
//! A build installed here is written into Paks as
//! `pakchunk<N>-MJOLNIRDEV-<name>_<v>_P`, with `v` above every hub
//! container's and every earlier build's, and its shader library renamed to
//! its own chunk number `N` (`ue_iostore::paks`, docs/chunk_numbering.md).
//! The launcher never moves or renames these; it lists them.
//!
//! A plain `_P` copy dropped into Paks by hand loses to the hub copy of the
//! same thing, silently. `dev list` names every one that does.

use std::path::PathBuf;

use anyhow::{anyhow, Result};
use clap::{Args, Subcommand};
use ue_iostore::paks;

/// The project UE names shader libraries after.
const PROJECT: &str = "Meteorite";

#[derive(Args)]
pub struct DevArgs {
    #[command(subcommand)]
    pub command: DevCommand,
}

#[derive(Subcommand)]
pub enum DevCommand {
    /// Install a container as a local build that wins over hub content.
    Install(InstallArgs),
    /// Remove a local build.
    Remove(NamedArgs),
    /// List the local builds, and every loose container that loses to a hub
    /// copy.
    List(ListArgs),
}

#[derive(Args)]
pub struct PaksArg {
    /// The game's `Meteorite/Content/Paks` directory.
    #[arg(long, env = "HCE_PAKS")]
    paks: PathBuf,
}

#[derive(Args)]
pub struct InstallArgs {
    #[command(flatten)]
    paks: PaksArg,
    /// The container: its `.utoc`, or its path without an extension. A
    /// `.pak` beside it is copied too; without one an empty stub is written.
    container: PathBuf,
    /// The build's name: letters, digits and dashes. Installing under a name
    /// already in use replaces that build. Defaults to the container's own
    /// name after the chunk number (`pakchunk997-MJOLNIRMAP-BGL_P` →
    /// `MJOLNIRMAP-BGL`).
    #[arg(long)]
    name: Option<String>,
}

#[derive(Args)]
pub struct NamedArgs {
    #[command(flatten)]
    paks: PaksArg,
    /// The build's name, as `dev list` shows it.
    name: String,
}

#[derive(Args)]
pub struct ListArgs {
    #[command(flatten)]
    paks: PaksArg,
    /// Print JSON: `{"builds": [...], "shadowed": [...]}`.
    #[arg(long)]
    json: bool,
}

pub fn run(a: DevArgs) -> Result<()> {
    match a.command {
        DevCommand::Install(a) => install(a),
        DevCommand::Remove(a) => remove(a),
        DevCommand::List(a) => list(a),
    }
}

fn install(a: InstallArgs) -> Result<()> {
    let stem = a
        .container
        .file_name()
        .and_then(|s| s.to_str())
        .map(|s| s.trim_end_matches(".utoc").trim_end_matches(".ucas").trim_end_matches(".pak").to_string())
        .ok_or_else(|| anyhow!("{} is not a container path", a.container.display()))?;
    let name = match a.name {
        Some(name) => name,
        None => paks::default_dev_name(&stem).map_err(|e| anyhow!(e))?,
    };
    let done = paks::install_dev(&a.paks.paks, &a.container, &name, PROJECT).map_err(|e| anyhow!(e))?;
    for old in &done.replaced {
        println!("removed {old}");
    }
    print!("installed {}", done.installed.stem);
    if let Some((cooked, number)) = done.library {
        print!(" (shader library {cooked} -> {number})");
    }
    println!();
    println!(
        "  wins over every hub container. A package the hub copy has and this build does not \
         still loads from the hub."
    );
    report_shadowed(&a.paks.paks)
}

fn remove(a: NamedArgs) -> Result<()> {
    let removed = paks::remove_dev(&a.paks.paks, &a.name).map_err(|e| anyhow!(e))?;
    if removed.is_empty() {
        println!("no local build named {}", a.name);
    }
    for stem in removed {
        println!("removed {stem}");
    }
    Ok(())
}

fn list(a: ListArgs) -> Result<()> {
    let builds = paks::list_dev(&a.paks.paks).map_err(|e| anyhow!(e))?;
    if a.json {
        let shadowed = paks::shadowed_loose(&a.paks.paks).map_err(|e| anyhow!(e))?;
        let out = serde_json::json!({
            "builds": builds.iter().map(|d| serde_json::json!({
                "name": d.name, "stem": d.stem, "number": d.number, "suffix": d.suffix,
            })).collect::<Vec<_>>(),
            "shadowed": shadowed.iter().map(|s| serde_json::json!({
                "loser": s.loser, "winner": s.winner, "differing": s.differing, "identical": s.identical,
            })).collect::<Vec<_>>(),
        });
        println!("{}", serde_json::to_string_pretty(&out)?);
        return Ok(());
    }
    if builds.is_empty() {
        println!("no local builds");
    }
    for d in &builds {
        println!("{:<32} {}", d.name, d.stem);
    }
    report_shadowed(&a.paks.paks)
}

/// Every loose container that loses chunks with different bytes to a hub
/// copy or a local build: the edit in it never reaches the game.
fn report_shadowed(paks_dir: &std::path::Path) -> Result<()> {
    let shadowed = paks::shadowed_loose(paks_dir).map_err(|e| anyhow!(e))?;
    let losing: Vec<_> = shadowed.iter().filter(|s| s.differing > 0).collect();
    if losing.is_empty() {
        return Ok(());
    }
    println!();
    println!("These loose containers lose to a copy mounted above them; their versions never load:");
    for s in losing {
        println!("  {}: {} chunk(s) differ from {}", s.loser, s.differing, s.winner);
    }
    println!("Install one with `mjolnir dev install <container> --name <name>` to make it win.");
    Ok(())
}
