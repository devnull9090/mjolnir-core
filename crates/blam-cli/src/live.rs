//! `mjolnir live`: what the running game has loaded, read from the
//! simulation's own tables rather than a memory sweep.
//!
//! The tag module keeps a table of every loaded tag and a registry of every
//! string id it knows (`blam_live::tagtable`, `blam_live::stringid`). Both are
//! reached from globals whose addresses depend on the build, so the module is
//! hashed first and an unknown build is refused with its hash — nothing is
//! read at a guessed address. Objects and players come from the simulation
//! thread's data arrays (`blam_live::gamestate`, `blam_live::world`), which are
//! found through the module's TLS directory and name themselves.

use std::collections::HashMap;
use std::path::PathBuf;

use anyhow::{Context, Result};
use blam_live::gamestate::GameState;
use blam_live::stringid::StringIds;
use blam_live::tagtable::{self, LiveTags, Segments, TagTable};
use blam_live::world;
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
    /// Every object in play: what it is, where, and how damaged.
    Objects {
        /// Only this tag group four-CC, e.g. `bipd`.
        #[arg(long)]
        group: Option<String>,
        /// Only definition paths containing this text.
        #[arg(long)]
        filter: Option<String>,
        /// Write every row as tab-separated text here instead of the console.
        #[arg(long)]
        tsv: Option<PathBuf>,
    },
    /// Every player and the unit each controls.
    Players,
    /// The simulation's data arrays: every table it keeps per game, with how full each is.
    Arrays,
    /// Which game engine the simulation is running: campaign, Megalo
    /// (multiplayer), Forge or Firefight (docs/re/megalo_engine.md). CU4 only.
    Engine {
        /// Patch which engine the next map load asks for (the one constant in
        /// the load-map handler that is always 3, campaign): 2 is Megalo, 3
        /// puts it back. In memory only; a restart undoes it. Apply at the
        /// menu, then start a mission.
        #[arg(long, value_parser = clap::value_parser!(u8).range(1..=4))]
        launch_engine: Option<u8>,
        /// The multiplayer session launch requires a map variant, which the
        /// campaign flow never provides, so a Megalo launch is abandoned
        /// with "no map selected". `skip` drops that requirement (and the
        /// options builder's matching check) on the multiplayer branches
        /// only; `keep` restores the shipped bytes. In memory only.
        #[arg(long, value_parser = ["skip", "keep"])]
        map_variant_gate: Option<String>,
        /// The game engine's zone-set handler deletes every map-variant object
        /// and resets the map variant to default, and nothing rebuilds it;
        /// a campaign-style launch switches zone sets right after the map
        /// loads, so a multiplayer map loses its weapons and spawn points.
        /// `skip` bypasses the reset (safe for single-BSP maps); `keep`
        /// restores the shipped bytes. In memory only.
        #[arg(long, value_parser = ["skip", "keep"])]
        map_variant_reset: Option<String>,
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
    // The data arrays name themselves, so listing them needs no build profile.
    if let LiveCommand::Arrays = a.cmd {
        return arrays(&process);
    }
    let attached = tagtable::attach(&process)?;
    match a.cmd {
        LiveCommand::Status => status(&process, attached),
        LiveCommand::Tags { group, filter, tsv } => tags(&process, attached, group, filter, tsv),
        LiveCommand::Objects { group, filter, tsv } => {
            objects(&process, attached, group, filter, tsv)
        }
        LiveCommand::Players => players(&process, attached),
        LiveCommand::Engine {
            launch_engine,
            map_variant_gate,
            map_variant_reset,
        } => engine(
            &process,
            attached,
            launch_engine,
            map_variant_gate.as_deref(),
            map_variant_reset.as_deref(),
        ),
        LiveCommand::Arrays => unreachable!("handled before attaching"),
        LiveCommand::StringIds { find, out } => string_ids(&process, attached, find, out),
    }
}

/// The loaded tags by handle, for naming what the object table points at.
fn tags_by_handle(
    process: &blam_live::Process,
    table: &TagTable,
) -> Result<HashMap<u32, tagtable::LiveTag>> {
    Ok(table
        .walk(process)?
        .into_iter()
        .map(|t| (t.handle(), t))
        .collect())
}

fn percent(fraction: Option<f32>, maximum: f32) -> String {
    match fraction {
        Some(f) if maximum > 0.0 => format!("{:.0}% of {maximum:.0}", f * 100.0),
        _ => "-".into(),
    }
}

fn objects(
    process: &blam_live::Process,
    attached: tagtable::Attached,
    group: Option<String>,
    filter: Option<String>,
    tsv: Option<PathBuf>,
) -> Result<()> {
    let gs = GameState::attach(process)?;
    let table = TagTable::open(process, attached.base, attached.profile)?;
    let segments = Segments::read(process, attached.base, attached.profile)?;
    let tags = tags_by_handle(process, &table)?;
    let objects = world::objects(process, &gs)?;
    let players: HashMap<u32, u32> = world::players(process, &gs)?
        .iter()
        .filter_map(|p| Some((p.unit?, p.index)))
        .collect();
    let group = group.map(|g| g.to_ascii_lowercase());
    let filter = filter.map(|f| f.to_ascii_lowercase());
    let mut shields: HashMap<u32, Option<i16>> = HashMap::new();
    let mut unnamed = 0usize;
    let mut out = String::new();
    let mut rows = 0usize;
    for o in &objects {
        let tag = tags.get(&o.tag);
        if tag.is_none() {
            unnamed += 1;
        }
        let (grp, name) = tag
            .map(|t| (t.group_str(), t.name.clone()))
            .unwrap_or_else(|| ("?".into(), format!("tag 0x{:08X}", o.tag)));
        if group
            .as_deref()
            .is_some_and(|g| !grp.eq_ignore_ascii_case(g))
            || filter
                .as_deref()
                .is_some_and(|f| !name.to_ascii_lowercase().contains(f))
        {
            continue;
        }
        let shield = if o.max_shield > 0.0 {
            let section = match shields.get(&o.tag) {
                Some(s) => *s,
                None => {
                    let s = world::shield_section(process, &table, &segments, o.tag)?;
                    shields.insert(o.tag, s);
                    s
                }
            };
            o.shield(section)
        } else {
            None
        };
        let [x, y, z] = o.position;
        // Facing in degrees about z, from the forward vector (Blam axes).
        let yaw = o.forward[1].atan2(o.forward[0]).to_degrees();
        let parent = o
            .parent
            .map(|p| format!("0x{p:08X}"))
            .unwrap_or_else(|| "-".into());
        let player = players
            .get(&o.handle)
            .map(|i| format!("player {i}"))
            .unwrap_or_default();
        out.push_str(&format!(
            "{}\t0x{:08X}\t{}\t{grp}\t{name}\t{x:.2}\t{y:.2}\t{z:.2}\t{}\t{}\t{parent}\t{player}\t{yaw:.1}\t{:#x}\n",
            o.index,
            o.handle,
            o.kind.name(),
            percent(o.health(), o.max_body),
            percent(shield, o.max_shield),
            o.datum,
        ));
        rows += 1;
    }
    let summary = format!(
        "{rows} of {} objects (thread {}, object array {} of {} slots)",
        objects.len(),
        gs.tid,
        objects.len(),
        gs.array(world::OBJECT_ARRAY).map_or(0, |a| a.maximum)
    );
    match tsv {
        Some(path) => {
            std::fs::write(&path, &out)?;
            println!("{summary} written to {}", path.display());
        }
        None => {
            print!("{out}");
            println!("{summary}");
        }
    }
    if unnamed > 0 {
        println!(
            "{unnamed} object(s) name a tag handle the tag table does not hold; \
             the object datum layout may have moved"
        );
    }
    Ok(())
}

/// Where the game-engine layer keeps its state, on the CU4 tag module
/// (docs/re/megalo_engine.md). Static reading only until this command.
mod engine_cu4 {
    /// The sim thread's TLS block holds a pointer to the game-engine globals here.
    pub const TLS_ENGINE_GLOBALS: u64 = 0x38;
    /// The running engine's index in the globals.
    pub const ENGINE_INDEX: u64 = 0x846c;
    /// `game_engines[5]`: slot 0 empty, then one engine object per index.
    pub const ENGINE_TABLE: u64 = 0xbd5210;
    /// In the load-map handler (`0xf650`): `mov r8d, 3` feeding
    /// `0x21c4f0(&variant, has_campaign_variant ? 3 : 0)`. The immediate is
    /// at `+2`. The campaign fields are only copied in when the variant's
    /// engine is 3, and the game mode after it is derived from the engine, so
    /// this one constant is a self-consistent switch.
    pub const LAUNCH_ENGINE_MOV: u64 = 0xf6db;
    pub const LAUNCH_ENGINE_BYTES: [u8; 6] = [0x41, 0xb8, 0x03, 0x00, 0x00, 0x00];
    /// The map-variant gate on a multiplayer session launch: (RVA, shipped
    /// bytes, skipping bytes, what it is).
    pub const MAP_VARIANT_GATE: [(u64, &[u8], &[u8], &str); 3] = [
        // Session readiness (0x55a2a0), required-parameter mask for session
        // modes 3/4: `movabs rax, 0x8001813e0`; bit 20 is the map variant
        // ("no map selected"). 0x8000813e0 drops it and the map/game
        // compatibility checks behind it; the engine-matches-mode bit stays.
        (
            0x55af56,
            &[0x48, 0xb8, 0xe0, 0x13, 0x18, 0x00, 0x08, 0x00, 0x00, 0x00],
            &[0x48, 0xb8, 0xe0, 0x13, 0x08, 0x00, 0x08, 0x00, 0x00, 0x00],
            "session readiness: map variant not required",
        ),
        // Options from session (0x55e1c0): `je 0x55e8fa` clears the ok flag
        // when there is no map variant; `je 0x55e8fd` steps past the clear.
        (
            0x55e8c7,
            &[0x74, 0x31],
            &[0x74, 0x34],
            "options builder: no map variant is not a failure",
        ),
        // In-game session step (0x55c730) checks the required parameters again
        // through 0x45b160, with its own copy of the mask, before building the
        // options; the same bit-20 edit. The third copy (0x55d2ff) is a resync
        // that only runs once a game exists and fills the map variant in, so it
        // is left alone.
        (
            0x45b1a3,
            &[0x48, 0xb8, 0xe0, 0x13, 0x18, 0x00, 0x08, 0x00, 0x00, 0x00],
            &[0x48, 0xb8, 0xe0, 0x13, 0x08, 0x00, 0x08, 0x00, 0x00, 0x00],
            "in-game parameter check: map variant not required",
        ),
    ];
    /// The game engine's zone-set handler (`0x2ad2d0`): `je 0x2ad31a` skips
    /// the map-variant object delete (`0x32c820`) and reset
    /// (`0x32baf0(mv, -1)`) when there is no engine; `jmp` always skips them,
    /// keeping the handler's enter/exit counter balanced.
    pub const MAP_VARIANT_RESET: [(u64, &[u8], &[u8], &str); 1] = [(
        0x2ad2e2,
        &[0x74, 0x36],
        &[0xeb, 0x36],
        "zone-set switch: map variant kept",
    )];
    /// (index, name, engine object RVA, vtable RVA).
    pub const ENGINES: [(u32, &str, u64, u64); 4] = [
        (1, "sandbox (Forge)", 0xbd52d0, 0x85d740),
        (2, "Megalo (multiplayer)", 0xc7a7b8, 0x85dae8),
        (3, "campaign", 0x9cbdc0, 0x855b48),
        (4, "survival (Firefight)", 0x9b1f78, 0x845388),
    ];
}

fn engine(
    process: &blam_live::Process,
    attached: tagtable::Attached,
    launch: Option<u8>,
    gate: Option<&str>,
    reset: Option<&str>,
) -> Result<()> {
    use blam_live::tagtable::Memory;
    use engine_cu4::*;
    if !attached.profile.label.contains("CU4") {
        anyhow::bail!(
            "the engine offsets are CU4's; this tag module is {}",
            attached.profile.label
        );
    }
    let base = attached.base;
    let mov = base + LAUNCH_ENGINE_MOV;
    let now = process.read(mov, 6)?;
    let mut expect = LAUNCH_ENGINE_BYTES;
    let launch_now = now[2];
    expect[2] = launch_now;
    if now != expect || !(1..=4).contains(&launch_now) {
        anyhow::bail!(
            "the load-map handler's bytes at +{LAUNCH_ENGINE_MOV:#x} are {} — not the CU4 `mov r8d, <engine>`",
            now.iter().map(|b| format!("{b:02x}")).collect::<Vec<_>>().join(" ")
        );
    }
    if let Some(n) = launch {
        process.write_code(mov + 2, &[n])?;
        println!("next map load asks for engine {n} (was {launch_now})");
    } else {
        println!(
            "next map load asks for engine {launch_now}{}",
            if launch_now == 3 {
                " (as shipped)"
            } else {
                " (PATCHED)"
            }
        );
    }
    let sets = [
        (&MAP_VARIANT_GATE[..], gate, "map-variant gate"),
        (&MAP_VARIANT_RESET[..], reset, "map-variant reset"),
    ];
    for (patches, choice, label) in sets {
        for (rva, shipped, skipping, what) in patches.iter().copied() {
            let now = process.read(base + rva, shipped.len())?;
            let state = if now == shipped {
                "kept (as shipped)"
            } else if now == skipping {
                "SKIPPED"
            } else {
                anyhow::bail!(
                    "bytes at +{rva:#x} are neither the shipped nor the patched form: {now:02x?}"
                );
            };
            match choice {
                Some("skip") if now != skipping => {
                    process.write_code(base + rva, skipping)?;
                    println!("{label} +{rva:#x}: skipped ({what})");
                }
                Some("keep") if now != shipped => {
                    process.write_code(base + rva, shipped)?;
                    println!("{label} +{rva:#x}: restored ({what})");
                }
                _ => println!("{label} +{rva:#x}: {state} ({what})"),
            }
        }
    }
    let gs = GameState::attach(process)?;
    println!("sim thread {} TLS block {:#x}", gs.tid, gs.block);
    // The table is static: check it first, so a wrong reading of the globals
    // cannot be mistaken for a wrong table.
    for (i, name, object, vtable) in ENGINES {
        let at = process.u64(base + ENGINE_TABLE + 8 * u64::from(i))?;
        let vt = process.u64(at).unwrap_or(0);
        println!(
            "  table[{i}] {:#x} (expect +{:#x}: {}), vtable +{:#x} (expect +{:#x}: {})  {name}",
            at.wrapping_sub(base),
            object,
            if at == base + object {
                "ok"
            } else {
                "MISMATCH"
            },
            vt.wrapping_sub(base),
            vtable,
            if vt == base + vtable {
                "ok"
            } else {
                "MISMATCH"
            },
        );
    }
    let globals = process.u64(gs.block + TLS_ENGINE_GLOBALS)?;
    println!("game engine globals {globals:#x}");
    if globals == 0 {
        println!("  none allocated (no game in progress)");
        return Ok(());
    }
    let index = process.u32(globals + ENGINE_INDEX)?;
    let name = ENGINES
        .iter()
        .find(|e| e.0 == index)
        .map_or("none", |e| e.1);
    println!("engine index {index}: {name}");
    if let Some(m) = gs.array("megalo_objects") {
        let m = gs.fresh(process, &m.name).unwrap_or_else(|_| m.clone());
        println!(
            "megalo_objects: valid {}, {} of {} in use",
            m.valid, m.used, m.maximum
        );
    }
    Ok(())
}

fn players(process: &blam_live::Process, attached: tagtable::Attached) -> Result<()> {
    let gs = GameState::attach(process)?;
    let table = TagTable::open(process, attached.base, attached.profile)?;
    let tags = tags_by_handle(process, &table)?;
    let objects: HashMap<u32, world::LiveObject> = world::objects(process, &gs)?
        .into_iter()
        .map(|o| (o.handle, o))
        .collect();
    let players = world::players(process, &gs)?;
    for p in &players {
        match p.unit.and_then(|u| objects.get(&u)) {
            Some(o) => {
                let name = tags.get(&o.tag).map_or("?", |t| t.name.as_str());
                let [x, y, z] = o.position;
                println!(
                    "player {}\t0x{:08X}\tteam {}\tunit 0x{:08X}\t{name}\t{x:.2}\t{y:.2}\t{z:.2}",
                    p.index, p.handle, p.team, o.handle
                );
            }
            None => println!(
                "player {}\t0x{:08X}\tteam {}\tno unit{}",
                p.index,
                p.handle,
                p.team,
                p.unit
                    .map(|u| format!(" (0x{u:08X} is not in play)"))
                    .unwrap_or_default()
            ),
        }
    }
    println!("{} player(s)", players.len());
    Ok(())
}

fn arrays(process: &blam_live::Process) -> Result<()> {
    let gs = GameState::attach(process)?;
    println!(
        "thread {}, TLS slot {}, block 0x{:X}",
        gs.tid, gs.tls_index, gs.block
    );
    for (offset, a) in &gs.arrays {
        println!(
            "+0x{offset:03X}\t{}\t{} of {}\t0x{:X} bytes each\t{}",
            a.name,
            a.used,
            a.maximum,
            a.element_size,
            if a.valid { "" } else { "not in a game" }
        );
    }
    println!("{} data arrays", gs.arrays.len());
    Ok(())
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
    // The game state is read without any build profile, so a failure here
    // says something about the running game rather than about this build.
    match GameState::attach(process) {
        Ok(gs) => {
            let object = gs.array(world::OBJECT_ARRAY);
            println!(
                "game state thread {}, {} data arrays; objects {}",
                gs.tid,
                gs.arrays.len(),
                match object {
                    Some(a) if a.valid => format!("{} of {}", a.used, a.maximum),
                    _ => "not in a game".into(),
                }
            );
        }
        Err(e) => println!("game state not found: {e}"),
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
