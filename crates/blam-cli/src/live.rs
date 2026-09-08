//! `mjolnir live`: what the running game has loaded, read from the
//! simulation's own tables rather than a memory sweep.
//!
//! The tag module keeps a table of every loaded tag and a registry of every
//! string id it knows (`blam_live::tagtable`, `blam_live::stringid`). Both are
//! reached from globals whose addresses depend on the build, so the module is
//! hashed first and an unknown build is refused with its hash — nothing is
//! read at a guessed address.

use std::path::PathBuf;

use anyhow::{Context, Result};
use blam_live::stringid::StringIds;
use blam_live::tagtable::{self, LiveTags, Segments, TagTable};
use clap::{Args, Subcommand};

#[derive(Args)]
pub struct LiveArgs {
    #[command(subcommand)]
    cmd: LiveCommand,
    /// Attach to this pid instead of finding the game automatically.
    #[arg(long, global = true)]
    pid: Option<u32>,
}

#[derive(Subcommand)]
enum LiveCommand {
    /// Which build is running, where its tag module sits, how much is loaded.
    Status,
    /// Every tag the simulation has loaded, with its handle and root address.
    Tags {
        /// Only this group four-CC, e.g. `weap`.
        #[arg(long)]
        group: Option<String>,
        /// Only paths containing this text.
        #[arg(long)]
        filter: Option<String>,
        /// Write every row as tab-separated text here instead of the console.
        #[arg(long)]
        tsv: Option<PathBuf>,
    },
    /// The string ids the running game has registered.
    StringIds {
        /// Look one name up (in any spelling the engine would accept).
        #[arg(long)]
        find: Option<String>,
        /// Write the whole registry as JSON here — the shape `defs/hce/string-ids.json` uses.
        #[arg(long)]
        out: Option<PathBuf>,
    },
}

/// A tag found in the table, with what a poke needs to reach its fields.
pub struct TableHit {
    /// Address of the root element's bytes.
    pub root: u64,
    pub handle: u32,
    pub segments: Segments,
    pub profile: &'static str,
}

/// Find a tag's root through the tag table.
///
/// `Ok(None)` means the table is not usable for this game — an unknown build
/// or no mission loaded — and the caller should fall back to the sweep. A tag
/// that is simply not loaded is `Ok(None)` too, with a note, since the sweep
/// cannot find it either but will say so in its own words.
pub fn locate_via_table(
    process: &blam_live::Process,
    group: [u8; 4],
    ubulk_path: &str,
) -> Result<Option<TableHit>> {
    let attached = match tagtable::attach(process) {
        Ok(a) => a,
        Err(blam_live::Error::UnknownBuild(sha)) => {
            println!("  table    not read: tag module {sha} has no profile; sweeping instead");
            return Ok(None);
        }
        Err(blam_live::Error::NoMission) => return Ok(None),
        Err(e) => return Err(e.into()),
    };
    let table = match TagTable::open(process, attached.base, attached.profile) {
        Ok(t) => t,
        Err(blam_live::Error::NoMission) => return Ok(None),
        Err(e) => return Err(e.into()),
    };
    let segments = Segments::read(process, attached.base, attached.profile)?;
    let tags = LiveTags::new(table.walk(process)?);
    let name = tagtable::from_ubulk_path(ubulk_path);
    let Some(tag) = tags.find(group, &name) else {
        println!(
            "  table    {} tags loaded, none is {} {name}; sweeping instead",
            tags.len(),
            String::from_utf8_lossy(&group)
        );
        return Ok(None);
    };
    let root = tag
        .root_address(&segments)
        .context("the tag is in the table but its root descriptor does not resolve")?;
    Ok(Some(TableHit {
        root,
        handle: tag.handle(),
        segments,
        profile: attached.profile.label,
    }))
}

pub fn run(a: LiveArgs) -> Result<()> {
    let process = match a.pid {
        Some(pid) => blam_live::Process::open(pid)?,
        None => blam_live::Process::attach()?,
    };
    let attached = tagtable::attach(&process)?;
    match a.cmd {
        LiveCommand::Status => status(&process, attached),
        LiveCommand::Tags { group, filter, tsv } => tags(&process, attached, group, filter, tsv),
        LiveCommand::StringIds { find, out } => string_ids(&process, attached, find, out),
    }
}

fn status(process: &blam_live::Process, attached: tagtable::Attached) -> Result<()> {
    println!("pid        {}", process.pid);
    println!("build      {}", attached.profile.label);
    println!("tag module {} at 0x{:X}", tagtable::TAG_DLL, attached.base);
    let segments = Segments::read(process, attached.base, attached.profile)?;
    for (i, b) in segments.bases.iter().enumerate() {
        if *b != 0 {
            println!("segment    [{i:2}] 0x{b:X}");
        }
    }
    match TagTable::open(process, attached.base, attached.profile) {
        Ok(table) => {
            let tags = table.walk(process)?;
            let resolved = tags
                .iter()
                .filter(|t| t.root_address(&segments).is_some())
                .count();
            println!(
                "tag table  0x{:X}: {} loaded of {} slots (high water {}), {resolved} with a root",
                table.address, table.used, table.maximum, table.high_water
            );
        }
        Err(blam_live::Error::NoMission) => println!("tag table  empty — no mission loaded"),
        Err(e) => return Err(e.into()),
    }
    match StringIds::read(process, attached.base, attached.profile) {
        Ok(ids) => println!("string ids {} registered", ids.len()),
        Err(blam_live::Error::NoMission) => println!("string ids registry not built yet"),
        Err(e) => return Err(e.into()),
    }
    Ok(())
}

fn tags(
    process: &blam_live::Process,
    attached: tagtable::Attached,
    group: Option<String>,
    filter: Option<String>,
    tsv: Option<PathBuf>,
) -> Result<()> {
    let table = TagTable::open(process, attached.base, attached.profile)?;
    let segments = Segments::read(process, attached.base, attached.profile)?;
    let tags = table.walk(process)?;
    let group = group.map(|g| g.to_ascii_lowercase());
    let filter = filter.map(|f| f.to_ascii_lowercase());
    let rows: Vec<_> = tags
        .iter()
        .filter(|t| {
            group
                .as_deref()
                .is_none_or(|g| t.group_str().eq_ignore_ascii_case(g))
        })
        .filter(|t| {
            filter
                .as_deref()
                .is_none_or(|f| t.name.to_ascii_lowercase().contains(f))
        })
        .collect();
    let mut out = String::new();
    for t in &rows {
        let root = t
            .root_address(&segments)
            .map(|a| format!("0x{a:X}"))
            .unwrap_or_else(|| "-".into());
        out.push_str(&format!(
            "{}\t0x{:08X}\t{}\t{}\t{root}\n",
            t.index,
            t.handle(),
            t.group_str(),
            t.name
        ));
    }
    match tsv {
        Some(path) => {
            std::fs::write(&path, &out)?;
            println!(
                "{} of {} loaded tags written to {}",
                rows.len(),
                tags.len(),
                path.display()
            );
        }
        None => {
            print!("{out}");
            println!("{} of {} loaded tags", rows.len(), tags.len());
        }
    }
    Ok(())
}

fn string_ids(
    process: &blam_live::Process,
    attached: tagtable::Attached,
    find: Option<String>,
    out: Option<PathBuf>,
) -> Result<()> {
    let ids = StringIds::read(process, attached.base, attached.profile)?;
    println!(
        "{} string ids registered ({})",
        ids.len(),
        attached.profile.label
    );
    if let Some(name) = find {
        match ids.id(&name) {
            Some(id) => println!("{name:?} = 0x{id:08X}"),
            None => println!("{name:?} is not registered in the running game"),
        }
    }
    if let Some(path) = out {
        let doc = serde_json::json!({
            "build": attached.profile.label,
            "measured": format!("live registry read from pid {}", process.pid),
            "note": "Live string_id registry of HaloSimulation_tag_release.dll. Entries are [id, name]; the 2,678 builtin ids carry set bits in the high half, every later registration is sequential from 1068. Names register as tags load, so one mission's set is a lower bound for another's.",
            "count": ids.len(),
            "ids": ids.iter().map(|(k, n)| serde_json::json!([k, n])).collect::<Vec<_>>(),
        });
        std::fs::write(&path, serde_json::to_string(&doc)?)?;
        println!("written to {}", path.display());
    }
    Ok(())
}
