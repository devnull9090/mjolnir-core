//! `mjolnir level` — validate, self-test, and bake `.level.json` files.
//!
//! A custom level is a **map variant** over a shipped campaign scenario
//! (docs/level_format.md): the canvas map's world and BSP stay, and the level's
//! solid half bakes into a scenario-tag override — player starts, vehicles,
//! weapons, equipment, and structures built from scenery/crate placements.
//! (The Blam sim ignores Unreal geometry entirely, so the `decor` section is
//! the runtime mod's business, not this command's.)
//!
//! New placements are clones of a shipped element re-pointed field by field
//! ([`blam_tag::blockedit`]), so no novel `string id` is introduced. Every bake
//! goes out through [`blam_pack::build_override`] and the same verification the
//! `pack` command uses.

use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result};
use clap::{Args, Subcommand};

use crate::index;
use crate::Source;
use blam_tag::blockedit::{self, Op};
use blam_tag::{Scalar, TagFile};
use std::collections::BTreeMap;

/// 1 Blam world unit in Unreal centimeters.
const WU_CM: f64 = 304.8;

/// Base for the `unique id` given to cloned placements. High byte spells "MJ".
const UNIQUE_ID_BASE: i64 = 0x4D4A_0000;

const PALETTE_MAP: &str = include_str!("../../../defs/level/palette-map.json");

#[derive(Args)]
pub struct LevelArgs {
    #[command(subcommand)]
    pub command: LevelCommand,
}

#[derive(Subcommand)]
pub enum LevelCommand {
    /// Check a level file: schema shape, palette names, capacities.
    Validate(ValidateArgs),
    /// Prove the block resizer is byte-exact: a no-op resize of every
    /// placement block of every shipped scenario must reproduce the tag.
    Selftest(SelftestArgs),
    /// Bake a level file into a scenario override container.
    Bake(BakeArgs),
    /// Export a shipped mission's Unreal geometry as glTF: one `.glb` per
    /// World Partition cell, every placed static mesh at its world
    /// transform, instanced components expanded, plus a manifest of what was
    /// placed and what was skipped.
    Export(ExportArgs),
    /// Convert a classic CE collision BSP (halo2ue's `collision_<N>.json`)
    /// into a canvas structure BSP the simulation walks on, and write the
    /// transform that places everything else on it.
    Collision(crate::level_collision::CollisionArgs),
    /// Re-solve a classic map's lightmaps (tool.exe's radiosity on every
    /// core) at a multiple of the shipped pages' size, for
    /// `ce_material_spec.py --lightmaps`.
    Lightmaps(crate::level_lightmaps::LightmapsArgs),
    /// Rebuild the registration container and the multiplayer menu's map list
    /// from every installed map: the map packs in `ue4ss/MJOLNIRMaps` and the
    /// maps installed by `bake --install-test` (docs/map_distribution.md).
    /// What the launcher runs after a map install or removal.
    Register(RegisterArgs),
}

#[derive(Args)]
pub struct RegisterArgs {
    #[command(flatten)]
    pub src: Source,
}

#[derive(Args)]
pub struct ExportArgs {
    #[command(flatten)]
    pub src: Source,
    /// The mission folder, e.g. `a30` or `e20`.
    #[arg(long)]
    pub mission: String,
    /// Only cells whose id contains this (case-insensitive).
    #[arg(long)]
    pub cell: Option<String>,
    /// Directory for the `.glb` files and `manifest.json`.
    #[arg(long, default_value = ".")]
    pub out: PathBuf,
    /// Use the full-detail Nanite geometry for each mesh instead of the
    /// classic fallback LOD. Files get much larger.
    #[arg(long)]
    pub nanite: bool,
    /// Place the hierarchical-LOD proxies as well as the real meshes.
    #[arg(long)]
    pub hlod: bool,
    /// Stop after this many cells.
    #[arg(long)]
    pub limit: Option<usize>,
    /// Read and report only; write no `.glb`.
    #[arg(long)]
    pub dry_run: bool,
}

#[derive(Args)]
pub struct ValidateArgs {
    /// The .level.json file.
    pub file: PathBuf,
}

#[derive(Args)]
pub struct SelftestArgs {
    #[command(flatten)]
    pub src: Source,
}

#[derive(Args)]
pub struct BakeArgs {
    /// The .level.json file.
    pub file: PathBuf,
    #[command(flatten)]
    pub src: Source,
    /// Directory to write the container into.
    #[arg(long, default_value = ".")]
    pub out_dir: PathBuf,
    /// Install straight into the game: the container plus its stub .pak go to
    /// the Paks folder, and the level file is copied to the loader's levels
    /// directory so decor arrives too.
    #[arg(long)]
    pub install_test: bool,
    /// Bake a STANDALONE map: instead of overriding the canvas scenario, ship
    /// the baked scenario as a brand-new tag package under this codename —
    /// exactly three characters (every shipped scenario's is three, and the
    /// package rename is same-length surgery). The canvas world and collision
    /// still host the level; the codename is a new launchable scenario name.
    #[arg(long, value_name = "CODE")]
    pub standalone: Option<String>,
    /// With `--standalone`: give structure BSP `INDEX` of the canvas
    /// scenario its own tag under the codename's folder, carrying `PAYLOAD`
    /// (a scenario_structure_bsp tag file, e.g. a collision transplant), and
    /// point the baked scenario at it. The canvas mission's own BSP is then
    /// untouched: no override container is needed for the geometry.
    /// Repeatable.
    #[arg(long = "bsp", value_name = "INDEX=PAYLOAD")]
    pub bsps: Vec<String>,
    /// With `--standalone`: a cooked world package (`.umap`, plus a `.ubulk`
    /// beside it when it has one) to ship as the map's own Unreal world,
    /// renamed from the canvas mission's path to the codename's (same-length
    /// surgery over every name, so a World Partition donor's cells point
    /// nowhere and never stream), with the registration row pointing at it.
    /// The canvas mission's own world is the donor that keeps the player
    /// alive: its persistent level carries the BlamWorldSettings, the
    /// BlamScenario actor and the player starts the game mode needs.
    #[arg(long, value_name = "FILE")]
    pub world: Option<PathBuf>,
    /// With `--standalone`: point the registration row's `UnrealLevel` at
    /// this shipped world instead (an object path such as
    /// `/Game/Levels/Test/Testing_Clouds/Testing_Clouds.Testing_Clouds`),
    /// without shipping a world package. A test-map world no mission uses
    /// keeps the canvas mission's world out of the map.
    #[arg(long, value_name = "OBJECT")]
    pub world_object: Option<String>,
    /// Also write the baked scenario tag payload here, for `mjolnir
    /// tag-file` to read.
    #[arg(long, value_name = "FILE")]
    pub write_tag: Option<PathBuf>,
}

pub fn run(a: LevelArgs) -> Result<()> {
    match a.command {
        LevelCommand::Validate(a) => validate_cmd(a),
        LevelCommand::Selftest(a) => selftest(a),
        LevelCommand::Bake(a) => bake(a),
        LevelCommand::Export(a) => export(a),
        LevelCommand::Collision(a) => crate::level_collision::run(a),
        LevelCommand::Lightmaps(a) => crate::level_lightmaps::run(a),
        LevelCommand::Register(a) => register(a),
    }
}

// -----------------------------------------------------------------------------
// The level file
// -----------------------------------------------------------------------------

#[derive(Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
#[allow(dead_code)] // several fields exist so files carrying them deserialize
pub struct LevelFile {
    pub schema_version: u32,
    pub name: String,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub author: Option<String>,
    #[serde(default)]
    pub description: Option<String>,
    pub canvas: Canvas,
    /// A multiplayer map: the runtime loader starts it under the simulation's
    /// Megalo engine instead of the campaign (docs/re/megalo_engine.md).
    /// Opaque to the bake.
    #[serde(default)]
    pub multiplayer: bool,
    /// The Megalo variant to run (`"slayer"`): MJOLNIRLevelLoader asks the
    /// simulation to load it from `mjolnir.mglo` (`mjolnir megalo write`).
    /// Opaque to the bake.
    #[serde(default)]
    pub variant: Option<String>,
    /// The game types the multiplayer menu offers for the map (`["slayer"]`),
    /// each a variant MJOLNIRLevelLoader has installed. Listed in the
    /// `maps.json` an install writes; otherwise opaque to the bake.
    #[serde(default)]
    pub modes: Vec<String>,
    /// Sky and lighting, consumed by the runtime loader; opaque to the bake.
    #[serde(default)]
    pub environment: Option<serde_json::Value>,
    #[serde(default)]
    pub blam: BlamSection,
    #[serde(default)]
    pub decor: Vec<serde_json::Value>,
    #[serde(default)]
    pub markers: Vec<serde_json::Value>,
    /// Capture the Flag's look (the flag mesh, its materials, the stands),
    /// consumed by the runtime loader; opaque to the bake.
    #[serde(default)]
    pub ctf: Option<serde_json::Value>,
    /// The CE health pack's look (mesh, transform, materials), which the
    /// loader puts on the pack's actor; opaque to the bake.
    #[serde(default)]
    pub health_pack: Option<serde_json::Value>,
}

#[derive(Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Canvas {
    pub scenario: String,
    pub origin: [f64; 3],
}

#[derive(Debug, Default, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BlamSection {
    #[serde(default)]
    pub clear: Clear,
    #[serde(default)]
    pub player_starts: Vec<PlayerStart>,
    #[serde(default)]
    pub vehicles: Vec<TypedPlacement>,
    #[serde(default)]
    pub weapons: Vec<TypedPlacement>,
    #[serde(default)]
    pub equipment: Vec<TypedPlacement>,
    #[serde(default)]
    pub objects: Vec<ObjectPlacement>,
    /// Widen a structure BSP's world box (Halo wu). The scenario's boxes tile
    /// the world and decide which BSP a point belongs to; transplanted terrain
    /// larger than its host BSP falls "outside the world" past the old edge.
    #[serde(default)]
    pub world_bounds: Vec<WorldBounds>,
    /// Any other scenario field, by its path in the tag layout, set to a
    /// value in the form the inspector prints — e.g. `"type": "multiplayer"`.
    /// Applied last.
    #[serde(default)]
    pub set: BTreeMap<String, String>,
    /// Give the scenario a map variant palette listing every weapon, vehicle
    /// and scenery tag the level places. Under a multiplayer (Megalo) engine
    /// the simulation builds its map variant from the scenario's placements
    /// and keeps only those whose object has multiplayer data AND whose tag
    /// is in a `map variant palettes` entry; everything else with multiplayer
    /// data is never created (docs/re/megalo_engine.md).
    #[serde(default)]
    pub map_variant: bool,
    /// Load only these structure BSPs (scenario indices) in the starting zone
    /// set. A standalone map built on its own BSP needs none of the canvas
    /// mission's others, and any that stay active claim their own space:
    /// their collision and their inside-the-world test apply wherever their
    /// boxes reach. The zone set's PVS keeps its entries for these BSPs only
    /// (they are stored one per BSP of the set, in index order).
    #[serde(default)]
    pub active_bsps: Vec<usize>,
    /// Make this structure BSP (a scenario index, the one `active_bsps`
    /// lists) the scenario's only one, at index 0, and drop the canvas
    /// mission's zone sets, designs, seams and other insertion points with
    /// the rest of its BSPs. Applied after `--bsp`, so `--bsp` and
    /// `world_bounds` still name the canvas index. The BSP's own tag must be
    /// built for index 0 (`level collision --bsp-index 0`).
    #[serde(default)]
    pub single_bsp: Option<usize>,
}

#[derive(Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorldBounds {
    pub bsp: usize,
    pub min: [f64; 3],
    pub max: [f64; 3],
}

#[derive(Debug, Default, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Clear {
    #[serde(default)]
    pub squads: bool,
    #[serde(default)]
    pub bipeds: bool,
    #[serde(default)]
    pub weapons: bool,
    #[serde(default)]
    pub vehicles: bool,
    #[serde(default)]
    pub equipment: bool,
    #[serde(default)]
    pub scripts: bool,
    /// Any other root block to empty, by its name in the tag layout, e.g.
    /// `"machines"` or `"scenario kill triggers"`. Named before the flags so a
    /// file can strip a mission down to bare geometry in one list.
    #[serde(default)]
    pub blocks: Vec<String>,
}

#[derive(Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlayerStart {
    pub pos: [f64; 3],
    #[serde(default)]
    pub yaw: f64,
}

#[derive(Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TypedPlacement {
    #[serde(rename = "type")]
    pub kind: String,
    pub pos: [f64; 3],
    #[serde(default)]
    pub yaw: f64,
    /// Further fields of the placement, relative to its element, e.g.
    /// `"permutation data.variant name": "rocket"` (the Warthog's rocket
    /// turret).
    #[serde(default)]
    pub set: BTreeMap<String, String>,
}

#[derive(Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
#[allow(dead_code)]
pub struct ObjectPlacement {
    pub tag: String,
    pub group: String,
    pub pos: [f64; 3],
    #[serde(default)]
    pub rot: [f64; 3],
    #[serde(default)]
    pub name: Option<String>,
    /// Further fields of the placement, relative to its element, e.g.
    /// `"multiplayer data.owner team": "neutral"`.
    #[serde(default)]
    pub set: BTreeMap<String, String>,
}

#[derive(Debug, serde::Deserialize)]
struct PaletteMap {
    vehicles: std::collections::BTreeMap<String, String>,
    weapons: std::collections::BTreeMap<String, String>,
    equipment: std::collections::BTreeMap<String, String>,
    #[allow(dead_code)]
    #[serde(flatten)]
    rest: serde_json::Value,
}

fn load_level(path: &Path) -> Result<LevelFile> {
    let raw =
        std::fs::read_to_string(path).with_context(|| format!("reading {}", path.display()))?;
    let level: LevelFile =
        serde_json::from_str(&raw).with_context(|| format!("parsing {}", path.display()))?;
    if level.schema_version != 1 {
        bail!("schema_version {} is not supported", level.schema_version);
    }
    Ok(level)
}

fn palette_map() -> Result<PaletteMap> {
    serde_json::from_str(PALETTE_MAP).context("parsing the built-in palette map")
}

const SCENARIOS: [&str; 13] = [
    "A15", "A30", "A50", "B30", "B40", "C10", "C20", "C45", "D20", "D40", "E10", "E20", "E30",
];

fn validate_level(level: &LevelFile) -> Result<Vec<String>> {
    let mut notes = Vec::new();
    let scen = level.canvas.scenario.to_uppercase();
    if !SCENARIOS.contains(&scen.as_str()) {
        bail!(
            "canvas.scenario {:?} is not one of the 13 launchable scenarios",
            level.canvas.scenario
        );
    }
    if !level
        .name
        .chars()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
        || level.name.is_empty()
    {
        bail!("name {:?} must be a [a-z0-9_]+ slug", level.name);
    }
    let map = palette_map()?;
    for v in &level.blam.vehicles {
        if !map.vehicles.contains_key(&v.kind) {
            bail!("unknown vehicle type {:?}", v.kind);
        }
    }
    for w in &level.blam.weapons {
        if !map.weapons.contains_key(&w.kind) {
            bail!("unknown weapon type {:?}", w.kind);
        }
    }
    for e in &level.blam.equipment {
        if !map.equipment.contains_key(&e.kind) {
            bail!("unknown equipment type {:?}", e.kind);
        }
    }
    for o in &level.blam.objects {
        if o.group != "scenery" && o.group != "crates" {
            bail!(
                "objects[].group must be \"scenery\" or \"crates\", got {:?}",
                o.group
            );
        }
        if !o.tag.starts_with("objects\\") {
            bail!(
                "objects[].tag must be a tag path under objects\\, got {:?}",
                o.tag
            );
        }
    }
    if level.blam.player_starts.len() == 1 {
        notes.push("only one player start: co-op needs at least two".to_string());
    }
    if level.blam.clear.squads || level.blam.clear.bipeds {
        notes.push(
            "clear.squads / clear.bipeds leave the mission's scripts pointing at \
             missing AI — experimental until script stubbing lands"
                .to_string(),
        );
    }
    if level.blam.clear.scripts {
        notes.push(
            "clear.scripts replaces the mission's script with one startup script that fades in and hands the camera and input to the player"
                .to_string(),
        );
    }
    Ok(notes)
}

fn validate_cmd(a: ValidateArgs) -> Result<()> {
    let level = load_level(&a.file)?;
    let notes = validate_level(&level)?;
    println!(
        "{}: level '{}' on {} — ok",
        a.file.display(),
        level.name,
        level.canvas.scenario
    );
    println!(
        "  {} start(s), {} vehicle(s), {} weapon(s), {} equipment, {} object(s), {} decor",
        level.blam.player_starts.len(),
        level.blam.vehicles.len(),
        level.blam.weapons.len(),
        level.blam.equipment.len(),
        level.blam.objects.len(),
        level.decor.len()
    );
    for n in notes {
        println!("  note: {n}");
    }
    Ok(())
}

// -----------------------------------------------------------------------------
// Coordinate conversion (docs/level_format.md — the one table)
// -----------------------------------------------------------------------------

/// UE cm (level origin already added) -> Blam world units. Y is negated.
fn ue_to_blam(pos: [f64; 3]) -> (f64, f64, f64) {
    (pos[0] / WU_CM, -pos[1] / WU_CM, pos[2] / WU_CM)
}

/// UE yaw in degrees -> Blam yaw in radians. UE's yaw sense flips with the Y
/// axis. Provisional until verified against a live spawn.
fn ue_yaw_to_blam(yaw_deg: f64) -> f64 {
    (-yaw_deg).to_radians()
}

fn abs_pos(origin: [f64; 3], rel: [f64; 3]) -> [f64; 3] {
    [origin[0] + rel[0], origin[1] + rel[1], origin[2] + rel[2]]
}

// -----------------------------------------------------------------------------
// Field patching on top of blockedit
// -----------------------------------------------------------------------------

/// The path a tag-reference field currently holds, without its group.
fn reference_path(
    l: &blam_tag::Layout,
    file: &[u8],
    block: &blam_tag::Block<'_>,
    path: &str,
) -> Result<String> {
    let target = blam_tag::patch::resolve(l, file, block, path)?;
    match &target.current {
        Scalar::Reference { path: p, .. } if !p.is_empty() => Ok(p.clone()),
        other => bail!("{path} is {} rather than a tag reference", other.display()),
    }
}

/// Parse-and-set one field by path, mirroring what `mjolnir pack --set` does.
fn apply_set(file: &mut Vec<u8>, path: &str, value: &str) -> Result<()> {
    let tag = TagFile::parse(file, Some(file.len()))?;
    let l = tag.layout()?;
    let block = tag.read_data(&l)?;
    let target = blam_tag::patch::resolve(&l, file, &block, path)?;
    let parsed: Scalar = match target.type_name.as_str() {
        "string id" => Scalar::Text(value.trim_matches('"').to_string()),
        "tag reference" => crate::parse_reference(value)?,
        _ => blam_tag::value::parse(&l, &target.field, value)?,
    };
    let (out, _) = if target.section.is_some() {
        blam_tag::patch::set_text(&l, file, &block, path, &parsed)?
    } else {
        blam_tag::patch::set(&l, file, &block, path, &parsed)?
    };
    *file = out;
    Ok(())
}

/// Read one field's current value.
fn read_value(file: &[u8], path: &str) -> Result<Scalar> {
    let tag = TagFile::parse(file, Some(file.len()))?;
    let l = tag.layout()?;
    let block = tag.read_data(&l)?;
    Ok(blam_tag::patch::resolve(&l, file, &block, path)?.current)
}

/// Read many fields from one parse (resolving re-walks nothing between paths).
fn read_many(file: &[u8], paths: &[String]) -> Result<Vec<Option<Scalar>>> {
    let tag = TagFile::parse(file, Some(file.len()))?;
    let l = tag.layout()?;
    let block = tag.read_data(&l)?;
    Ok(paths
        .iter()
        .map(|p| {
            blam_tag::patch::resolve(&l, file, &block, p)
                .ok()
                .map(|t| t.current)
        })
        .collect())
}

/// The placement element closest to the level origin, to clone from.
///
/// Placements spawn only while their `origin bsp index` is in the active zone
/// set (verified on B40: donors from BSPs outside the play area never spawn).
/// Cloning the *nearest* shipped placement inherits the BSP the level actually
/// sits in, along with every other locality-sensitive field.
fn nearest_donor(
    file: &[u8],
    block: &str,
    count: usize,
    origin_wu: (f64, f64, f64),
) -> Result<usize> {
    let paths: Vec<String> = (0..count)
        .map(|i| format!("{block}[{i}].object data.position"))
        .collect();
    let values = read_many(file, &paths)?;
    let mut best = 0usize;
    let mut best_d = f64::MAX;
    for (i, v) in values.iter().enumerate() {
        if let Some(Scalar::Reals(p)) = v {
            if p.len() >= 3 {
                let d = (p[0] as f64 - origin_wu.0).powi(2)
                    + (p[1] as f64 - origin_wu.1).powi(2)
                    + (p[2] as f64 - origin_wu.2).powi(2);
                if d < best_d {
                    best_d = d;
                    best = i;
                }
            }
        }
    }
    Ok(best)
}

/// Indexes of a palette's entries by tag path (case-insensitive).
fn palette_index(file: &[u8], palette_block: &str, tag_path: &str) -> Result<Option<usize>> {
    let want = tag_path.to_ascii_lowercase();
    for i in 0.. {
        let path = format!("{palette_block}[{i}].name");
        match read_value(file, &path) {
            Ok(Scalar::Reference { path, .. }) => {
                if path.to_ascii_lowercase() == want {
                    return Ok(Some(i));
                }
            }
            Ok(_) => {}
            Err(_) => return Ok(None), // ran off the end
        }
    }
    unreachable!()
}

fn block_count(file: &[u8], block: &str) -> Result<usize> {
    // A no-op resize reports the count without changing anything.
    let (_, r) = blockedit::resize(file, block, &[])?;
    Ok(r.before as usize)
}

/// The element count of the block at any path, nested ones included.
fn block_count_at(file: &[u8], path: &str) -> Result<usize> {
    let tag = TagFile::parse(file, Some(file.len()))?;
    let l = tag.layout()?;
    let root = tag.read_data(&l)?;
    Ok(blockedit::find_block(&l, file, &root, path)?.block.count as usize)
}

// -----------------------------------------------------------------------------
// Selftest: no-op resizes must be byte-exact on every shipped scenario
// -----------------------------------------------------------------------------

/// Insertion points a single-BSP scenario keeps, all copies of its first: one
/// per game type MJOLNIRLobby can start (slot order in
/// mods/MJOLNIRLevelLoader `GAME_TYPE_SLOTS`).
const GAME_TYPE_SLOTS: usize = 8;

/// Root blocks of placed objects, each element with an `object data`.
const OBJECT_BLOCKS: [&str; 12] = [
    "scenery",
    "bipeds",
    "vehicles",
    "equipment",
    "weapons",
    "machines",
    "terminals",
    "controls",
    "sound scenery",
    "giants",
    "effect scenery",
    "crates",
];

const PLACEMENT_BLOCKS: [&str; 8] = [
    "player starting locations",
    "vehicles",
    "weapons",
    "equipment",
    "scenery",
    "crates",
    "bipeds",
    "squads",
];

fn selftest(a: SelftestArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group.get("scenario").context("no scenario tags")?;
    let mut checked = 0;
    for entry in entries {
        let file = idx.read(entry, None, &a.src.oodle_roots())?;
        for block in PLACEMENT_BLOCKS {
            let (out, r) = blockedit::resize(&file, block, &[])
                .with_context(|| format!("{}: {block}", entry.path))?;
            if out != file {
                bail!(
                    "{}: a no-op resize of {block:?} changed the bytes ({} vs {})",
                    entry.path,
                    out.len(),
                    file.len()
                );
            }
            checked += 1;
            println!(
                "  ok  {:40} {:28} {} element(s)",
                entry.path, block, r.before
            );
        }
    }
    println!("\n{checked} no-op resizes, all byte-exact.");
    Ok(())
}

// -----------------------------------------------------------------------------
// Bake
// -----------------------------------------------------------------------------

struct Baker {
    file: Vec<u8>,
    origin: [f64; 3],
    next_unique: i64,
    /// Elements this bake appended per block, so a clear keeps them.
    added: std::collections::BTreeMap<&'static str, usize>,
}

impl Baker {
    /// Append one default element to the block at `path`, returning its index.
    fn add_element(&mut self, path: &str) -> Result<usize> {
        let tag = TagFile::parse(&self.file, Some(self.file.len()))?;
        let l = tag.layout()?;
        let block = tag.read_data(&l)?;
        let (out, _) = blam_tag::patch::edit_elements(
            &l,
            &self.file,
            &block,
            path,
            blam_tag::patch::ElementOp::Add,
        )?;
        self.file = out;
        Ok(block_count_at(&self.file, path)? - 1)
    }

    /// One `map variant palettes` element whose entries name `tags`
    /// (`(group:path, model variant)`, how many are placed), one variant each.
    /// A model variant ("rocket" for the rocket Warthog) gets an entry of its
    /// own, or the map variant builds the tag's default.
    fn map_variant_palette(&mut self, tags: &[((String, String), usize)]) -> Result<()> {
        if tags.is_empty() {
            return Ok(());
        }
        let p = self.add_element("map variant palettes")?;
        for ((tag, variant), placed) in tags {
            let entries = format!("map variant palettes[{p}].entries");
            let e = self.add_element(&entries)?;
            let variants = format!("{entries}[{e}].variants");
            let v = self.add_element(&variants)?;
            apply_set(&mut self.file, &format!("{variants}[{v}].object"), tag)
                .with_context(|| format!("{variants}[{v}].object = {tag}"))?;
            if !variant.is_empty() {
                apply_set(
                    &mut self.file,
                    &format!("{variants}[{v}].variant name"),
                    variant,
                )
                .with_context(|| format!("{variants}[{v}].variant name = {variant}"))?;
            }
            apply_set(
                &mut self.file,
                &format!("{entries}[{e}].maximum allowed"),
                &format!("{}", (*placed).max(1)),
            )?;
            let shown = if variant.is_empty() {
                String::new()
            } else {
                format!(" variant {variant:?}")
            };
            println!("  mapvar  palette[{p}] entry {e}: {tag}{shown} (max {placed})");
        }
        Ok(())
    }

    /// Trim the starting zone set (zone set 0) to `keep`, and its PVS with it.
    fn active_bsps(&mut self, keep: &[usize]) -> Result<()> {
        let flags = |file: &[u8], path: &str| -> Result<u32> {
            match read_value(file, path)? {
                Scalar::Int(v) => Ok(v as u32),
                other => Ok(other
                    .display()
                    .rsplit_once("(0x")
                    .and_then(|(_, h)| u32::from_str_radix(h.trim_end_matches(')'), 16).ok())
                    .with_context(|| format!("{path} reads as {}", other.display()))?),
            }
        };
        let before = flags(&self.file, "zone sets[0].bsp zone flags")?;
        let mask: u32 = keep.iter().map(|b| 1u32 << b).sum();
        if before & mask != mask {
            bail!("zone set 0 ({before:#x}) does not load every BSP of {keep:?}");
        }
        let pvs = match read_value(&self.file, "zone sets[0].pvs index")? {
            Scalar::BlockIndex(i) => i as usize,
            other => bail!("zone sets[0].pvs index reads as {}", other.display()),
        };
        // The PVS stores one element per BSP of the set, in index order.
        let members: Vec<usize> = (0..32).filter(|b| before & (1 << b) != 0).collect();
        let slots: Vec<usize> = keep
            .iter()
            .map(|b| members.iter().position(|m| m == b).unwrap())
            .collect();
        let hex = format!("{mask:#x}");
        apply_set(&mut self.file, "zone sets[0].bsp zone flags", &hex)?;
        apply_set(&mut self.file, "zone sets[0].runtime bsp zone flags", &hex)?;
        apply_set(
            &mut self.file,
            &format!("zone set pvs[{pvs}].structure bsp mask"),
            &hex,
        )?;
        let mut edits = Vec::new();
        for block in ["bsp checksums", "structure bsp pvs"] {
            let path = format!("zone set pvs[{pvs}].{block}");
            let mut elements = Vec::new();
            let mut wrappers = Vec::new();
            for &slot in &slots {
                let (e, w) = blockedit::element_with_wrapper(&self.file, &path, slot)?;
                elements.extend_from_slice(&e);
                wrappers.push(w);
            }
            edits.push(blockedit::NestedReplace {
                path,
                count: slots.len() as u32,
                elements,
                wrappers: Some(wrappers),
            });
        }
        self.file = blockedit::replace_nested(&self.file, &edits)?;

        // Inside each kept BSP's PVS, every cluster holds one bit vector per
        // BSP of the set, and its seam cluster mappings name clusters of any
        // BSP of the set: keep the kept BSPs' only.
        let mut refs = Vec::new();
        let mut bits = Vec::new();
        {
            let tag = TagFile::parse(&self.file, Some(self.file.len()))?;
            let l = tag.layout()?;
            let root = tag.read_data(&l)?;
            let count = |path: &str| -> Result<usize> {
                Ok(blockedit::find_block(&l, &self.file, &root, path)?
                    .block
                    .count as usize)
            };
            for j in 0..slots.len() {
                let base = format!("zone set pvs[{pvs}].structure bsp pvs[{j}]");
                for which in ["cluster pvs", "cluster pvs doors closed"] {
                    for c in 0..count(&format!("{base}.{which}"))? {
                        let path = format!("{base}.{which}[{c}].cluster pvs bit vectors");
                        if count(&path)? == members.len() {
                            bits.push((path, slots.clone()));
                        }
                    }
                }
                let mappings = format!("{base}.bsp cluster mapings");
                for c in 0..count(&mappings)? {
                    for list in ["root clusters", "attached clusters", "connected clusters"] {
                        let path = format!("{mappings}[{c}].{list}");
                        let found = blockedit::find_block(&l, &self.file, &root, &path)?;
                        let mut elements = Vec::new();
                        let mut kept = 0u32;
                        for i in 0..found.block.count as usize {
                            let e = found.block.element(i).context("cluster reference")?;
                            // [bsp index (char), cluster index (byte)]
                            if keep.contains(&(e[0] as i8 as usize)) {
                                elements.extend_from_slice(e);
                                kept += 1;
                            }
                        }
                        refs.push(blockedit::NestedReplace {
                            path,
                            count: kept,
                            elements,
                            wrappers: None,
                        });
                    }
                }
            }
        }
        self.file = blockedit::replace_nested(&self.file, &refs)?;
        self.file = blockedit::select(&self.file, &bits)?;
        println!(
            "  zones   zone set 0 loads BSP(s) {keep:?} only ({before:#x} -> {mask:#x}); pvs[{pvs}] keeps slot(s) {slots:?} of {members:?} ({} cluster bit vector list(s), {} seam cluster list(s))",
            bits.len(),
            refs.len()
        );
        Ok(())
    }

    /// Make structure BSP `keep` the scenario's only one, at index 0: the
    /// map is new, not the canvas mission with BSPs switched off. Runs after
    /// [`Self::active_bsps`] has trimmed zone set 0 to `keep` and after the
    /// `--bsp` clones are pointed at, so every earlier step uses the canvas
    /// index.
    ///
    /// The per-BSP tables (`structure bsps`, `ai pathfinding data`,
    /// `scenario cluster data`, and each PVS's and audibility's per-BSP
    /// mappings) keep `keep`'s element; only zone set 0 and its PVS and
    /// audibility entries stay; every reference to a BSP by index or mask
    /// becomes 0; and the canvas's designs, soft ceilings, seams, other
    /// insertion points and their player starts go. The structure BSP itself
    /// must be built for index 0 (`level collision --bsp-index 0`).
    fn single_bsp(&mut self, keep: usize) -> Result<()> {
        let flags = |file: &[u8], path: &str| -> Result<u32> {
            match read_value(file, path)? {
                Scalar::Flags { raw, .. } => Ok(raw as u32),
                Scalar::Int(v) => Ok(v as u32),
                other => bail!("{path} reads as {}", other.display()),
            }
        };
        let index = |file: &[u8], path: &str| -> Result<i64> {
            match read_value(file, path)? {
                Scalar::BlockIndex(i) => Ok(i),
                other => bail!("{path} reads as {}", other.display()),
            }
        };
        let zones = flags(&self.file, "zone sets[0].bsp zone flags")?;
        if zones != 1 << keep {
            bail!("single_bsp {keep}: zone set 0 loads {zones:#x}; list only BSP {keep} in active_bsps");
        }
        let pvs = index(&self.file, "zone sets[0].pvs index")?;
        let audibility = index(&self.file, "zone sets[0].audibility index")?;
        if pvs < 0 {
            bail!("zone set 0 has no PVS");
        }
        let bsps = block_count(&self.file, "structure bsps")?;
        if keep >= bsps {
            bail!("single_bsp {keep}: the scenario has {bsps} structure BSP(s)");
        }
        let sbsp = {
            let tag = TagFile::parse(&self.file, Some(self.file.len()))?;
            let l = tag.layout()?;
            let block = tag.read_data(&l)?;
            reference_path(
                &l,
                &self.file,
                &block,
                &format!("structure bsps[{keep}].structure bsp"),
            )?
        };

        // Per-BSP tables, where they hold one element per structure BSP.
        let mut per_bsp: Vec<String> = vec![
            "structure bsps".into(),
            "ai pathfinding data".into(),
            "scenario cluster data".into(),
            format!("zone set pvs[{pvs}].portal=>device mapping"),
        ];
        if audibility >= 0 {
            per_bsp.push(format!(
                "zone set audibility[{audibility}].game portal to door occluder mapping"
            ));
            per_bsp.push(format!(
                "zone set audibility[{audibility}].bsp cluster to room bounds"
            ));
        }
        let mut select: Vec<(String, Vec<usize>)> = Vec::new();
        for path in per_bsp {
            match block_count_at(&self.file, &path)? {
                n if n == bsps => select.push((path, vec![keep])),
                0 => {}
                n => println!("  single  {path}: {n} element(s) for {bsps} BSP(s), left alone"),
            }
        }
        // The canvas mission's other insertion points, and the player starts
        // that belong to them.
        let starts = block_count(&self.file, "player starting locations")?;
        let paths: Vec<String> = (0..starts)
            .map(|i| format!("player starting locations[{i}].insertion point index"))
            .collect();
        let own: Vec<usize> = read_many(&self.file, &paths)?
            .iter()
            .enumerate()
            .filter(|(_, v)| matches!(v, Some(Scalar::BlockIndex(0))))
            .map(|(i, _)| i)
            .collect();
        let dropped_starts = starts - own.len();
        select.push(("player starting locations".into(), own));
        // The map's one insertion point, copied once per game type slot: the
        // insertion point index is the one number the host's travel carries
        // to fireteam clients (`?InsertionPointIndex=N`), so MJOLNIRLobby
        // starts game type N at insertion point N and every machine's loader
        // reads the game type from it (docs/multiplayer_menu.md).
        if block_count(&self.file, "insertion points")? > 0 {
            select.push(("insertion points".into(), vec![0; GAME_TYPE_SLOTS]));
        }
        for path in ["structure designs", "soft ceilings"] {
            select.push((path.into(), Vec::new()));
        }
        self.file = blockedit::select(&self.file, &select)?;
        // The zone set tables hold the per-BSP mappings above, so they go second.
        let mut zones = vec![
            ("zone sets".to_string(), vec![0]),
            ("zone set pvs".to_string(), vec![pvs as usize]),
        ];
        if audibility >= 0 {
            zones.push(("zone set audibility".to_string(), vec![audibility as usize]));
        }
        self.file = blockedit::select(&self.file, &zones)?;
        apply_set(&mut self.file, "zone sets[0].pvs index", "#0")?;
        if audibility >= 0 {
            apply_set(&mut self.file, "zone sets[0].audibility index", "#0")?;
        }
        for path in [
            "zone sets[0].bsp zone flags",
            "zone sets[0].runtime bsp zone flags",
            "zone set pvs[0].structure bsp mask",
        ] {
            apply_set(&mut self.file, path, "0x1")?;
        }
        for path in [
            "zone sets[0].structure design zone flags",
            "zone sets[0].sruntime tructure design zone flags",
        ] {
            apply_set(&mut self.file, path, "0x0")?;
        }
        apply_set(
            &mut self.file,
            "scenario cluster data[0].bsp",
            &format!("sbsp:{sbsp}"),
        )?;
        for path in ["structure seams", "local structure seams"] {
            apply_set(&mut self.file, path, "none")?;
        }

        // Seam cluster references in the kept PVS name the kept BSP only
        // (active_bsps); renumber them.
        let mut refs = Vec::new();
        {
            let tag = TagFile::parse(&self.file, Some(self.file.len()))?;
            let l = tag.layout()?;
            let root = tag.read_data(&l)?;
            let pvs_bsps = "zone set pvs[0].structure bsp pvs";
            let n = blockedit::find_block(&l, &self.file, &root, pvs_bsps)?
                .block
                .count;
            for j in 0..n {
                let mappings = format!("{pvs_bsps}[{j}].bsp cluster mapings");
                let m = blockedit::find_block(&l, &self.file, &root, &mappings)?
                    .block
                    .count;
                for c in 0..m {
                    for list in ["root clusters", "attached clusters", "connected clusters"] {
                        let path = format!("{mappings}[{c}].{list}");
                        let found = blockedit::find_block(&l, &self.file, &root, &path)?;
                        let mut elements = found.block.elements.to_vec();
                        for e in elements.chunks_mut(found.block.element_size as usize) {
                            if e[0] as usize == keep {
                                e[0] = 0;
                            }
                        }
                        refs.push(blockedit::NestedReplace {
                            path,
                            count: found.block.count,
                            elements,
                            wrappers: None,
                        });
                    }
                }
            }
        }
        self.file = blockedit::replace_nested(&self.file, &refs)?;

        // Every placement: its origin BSP is 0 and it may attach to BSP 0.
        let mut placed = 0;
        let mut writes: Vec<(usize, Vec<u8>)> = Vec::new();
        {
            let tag = TagFile::parse(&self.file, Some(self.file.len()))?;
            let l = tag.layout()?;
            let root = tag.read_data(&l)?;
            for block in OBJECT_BLOCKS {
                let Ok(found) = blockedit::find_block(&l, &self.file, &root, block) else {
                    continue;
                };
                for i in 0..found.block.count as usize {
                    let at = |f: &str| {
                        blam_tag::patch::resolve(
                            &l,
                            &self.file,
                            &root,
                            &format!("{block}[{i}].object data.{f}"),
                        )
                        .with_context(|| format!("{block}[{i}]"))
                    };
                    let origin = at("object id.origin bsp index")?;
                    writes.push((origin.file_offset, 0u16.to_le_bytes().to_vec()));
                    let attach = at("can attach to bsp flags")?;
                    let old = match attach.current {
                        Scalar::Flags { raw, .. } => raw as u32,
                        _ => 0,
                    };
                    writes.push((
                        attach.file_offset,
                        (1u32 | old & 0x8000_0000).to_le_bytes().to_vec(),
                    ));
                    let manual = at("manual bsp flags")?;
                    writes.push((manual.file_offset, 0u32.to_le_bytes().to_vec()));
                    placed += 1;
                }
            }
        }
        for (offset, bytes) in writes {
            self.file[offset..offset + bytes.len()].copy_from_slice(&bytes);
        }
        println!(
            "  single  structure BSP {keep} is now the only one (of {bsps}), at index 0: zone set 0, pvs[{pvs}] and audibility[{audibility}] kept; designs, soft ceilings and seams cleared; {} other insertion point start(s) dropped; {placed} placement(s) on BSP 0",
            dropped_starts
        );
        Ok(())
    }

    fn unique_id(&mut self) -> i64 {
        let id = self.next_unique;
        self.next_unique += 1;
        id
    }

    /// Rewrite mission-start player spawns: the elements with insertion point
    /// 0 are re-pointed in place, and extras are cloned as needed.
    fn player_starts(&mut self, starts: &[PlayerStart]) -> Result<()> {
        if starts.is_empty() {
            return Ok(());
        }
        let count = block_count(&self.file, "player starting locations")?;
        let mut mission_starts = Vec::new();
        for i in 0..count {
            let v = read_value(
                &self.file,
                &format!("player starting locations[{i}].insertion point index"),
            )?;
            if matches!(v, Scalar::BlockIndex(0)) {
                mission_starts.push(i);
            }
        }
        if mission_starts.is_empty() {
            bail!("the canvas scenario has no insertion-point-0 player starts to re-point");
        }
        if starts.len() > mission_starts.len() {
            let donor = mission_starts[0];
            let extra = starts.len() - mission_starts.len();
            let (out, _) = blockedit::resize(
                &self.file,
                "player starting locations",
                &[Op::CloneAppend {
                    donor,
                    copies: extra,
                }],
            )?;
            self.file = out;
            for k in 0..extra {
                mission_starts.push(count + k);
            }
        }
        for (j, start) in starts.iter().enumerate() {
            let i = mission_starts[j];
            let (x, y, z) = ue_to_blam(abs_pos(self.origin, start.pos));
            let p = |f: &str| format!("player starting locations[{i}].{f}");
            apply_set(&mut self.file, &p("position"), &format!("({x}, {y}, {z})"))?;
            apply_set(
                &mut self.file,
                &p("facing"),
                &format!("{}", ue_yaw_to_blam(start.yaw)),
            )?;
            apply_set(&mut self.file, &p("pitch"), "0")?;
            apply_set(&mut self.file, &p("insertion point index"), "#0")?;
            apply_set(
                &mut self.file,
                &p("campaign player slot"),
                &format!("{}", j.min(3)),
            )?;
            println!(
                "  start   [{i}] <- ({x:.3}, {y:.3}, {z:.3}) wu, slot {}",
                j.min(3)
            );
        }
        Ok(())
    }

    /// Append typed placements (vehicles / weapons / equipment) cloned from
    /// element 0 and re-pointed at the palette entry the type names.
    fn typed(
        &mut self,
        block: &str,
        palette: &str,
        items: &[TypedPlacement],
        map: &std::collections::BTreeMap<String, String>,
    ) -> Result<()> {
        if items.is_empty() {
            return Ok(());
        }
        let before = block_count(&self.file, block)?;
        let palette_before = block_count(&self.file, palette)?;
        if before == 0 || palette_before == 0 {
            bail!(
                "the canvas scenario's {block:?} block or its palette is empty — no donor to clone"
            );
        }
        let ref_group = match block {
            "vehicles" => "vehi",
            "weapons" => "weap",
            _ => "eqip",
        };
        // Resolve every palette index before touching anything. A type the
        // canvas palette does not carry (the shotgun, the fuel rod: B40 has
        // neither) gets an entry of its own, cloned from entry 0 and
        // re-pointed, as the structures lane does for scenery.
        let mut indices = Vec::new();
        let mut appended = 0usize;
        for item in items {
            let tag_path = map
                .get(&item.kind)
                .with_context(|| format!("unknown type {:?}", item.kind))?;
            let idx = match palette_index(&self.file, palette, tag_path)? {
                Some(i) => i,
                None => {
                    let (out, _) = blockedit::resize(
                        &self.file,
                        palette,
                        &[Op::CloneAppend {
                            donor: 0,
                            copies: 1,
                        }],
                    )?;
                    self.file = out;
                    let i = palette_before + appended;
                    apply_set(
                        &mut self.file,
                        &format!("{palette}[{i}].name"),
                        &format!("{ref_group}:{tag_path}"),
                    )?;
                    println!("  palette {palette}[{i}] <- {tag_path}");
                    appended += 1;
                    i
                }
            };
            indices.push(idx);
        }
        let donor = nearest_donor(&self.file, block, before, ue_to_blam(self.origin))?;
        println!("  {block:9} donor [{donor}] (nearest to the level origin)");
        let (out, _) = blockedit::resize(
            &self.file,
            block,
            &[Op::CloneAppend {
                donor,
                copies: items.len(),
            }],
        )?;
        self.file = out;
        *self
            .added
            .entry(match block {
                "vehicles" => "vehicles",
                "weapons" => "weapons",
                _ => "equipment",
            })
            .or_default() += items.len();
        for (j, (item, palette_idx)) in items.iter().zip(&indices).enumerate() {
            let i = before + j;
            let (x, y, z) = ue_to_blam(abs_pos(self.origin, item.pos));
            let yaw = ue_yaw_to_blam(item.yaw);
            let uid = self.unique_id();
            let p = |f: &str| format!("{block}[{i}].{f}");
            apply_set(&mut self.file, &p("type"), &format!("#{palette_idx}"))?;
            apply_set(&mut self.file, &p("name"), "none")?;
            apply_set(
                &mut self.file,
                &p("object data.position"),
                &format!("({x}, {y}, {z})"),
            )?;
            apply_set(
                &mut self.file,
                &p("object data.rotation"),
                &format!("({yaw}, 0, 0)"),
            )?;
            // Bit 0 is "not automatically" (never spawns without a script);
            // bit 5 is "create at rest". Clones must actually spawn.
            apply_set(&mut self.file, &p("object data.placement flags"), "0x20")?;
            apply_set(
                &mut self.file,
                &p("object data.object id.unique id"),
                &format!("{uid}"),
            )?;
            for (field, value) in &item.set {
                apply_set(&mut self.file, &p(field), value)
                    .with_context(|| format!("{block}[{i}].{field} = {value}"))?;
            }
            println!(
                "  {block:9} [{i}] {} at ({x:.3}, {y:.3}, {z:.3}) wu (palette #{palette_idx}){}",
                item.kind,
                if item.set.is_empty() {
                    String::new()
                } else {
                    format!(" {:?}", item.set)
                }
            );
        }
        Ok(())
    }

    /// The structures lane: scenery/crate placements, growing the palette when
    /// the tag is not in it yet (clone entry 0, re-point its reference).
    fn objects(&mut self, items: &[ObjectPlacement]) -> Result<()> {
        for group in ["scenery", "crates"] {
            let of_group: Vec<&ObjectPlacement> =
                items.iter().filter(|o| o.group == group).collect();
            if of_group.is_empty() {
                continue;
            }
            let (block, palette, ref_group) = match group {
                "scenery" => ("scenery", "scenery palette", "scen"),
                _ => ("crates", "crate palette", "bloc"),
            };
            let before = block_count(&self.file, block)?;
            let palette_before = block_count(&self.file, palette)?;
            if before == 0 || palette_before == 0 {
                bail!(
                    "the canvas scenario's {block:?} block or its palette is empty — \
                     no donor to clone"
                );
            }
            // Grow the palette first so placement indices are final.
            let mut indices = Vec::new();
            let mut appended = 0usize;
            for o in &of_group {
                match palette_index(&self.file, palette, &o.tag)? {
                    Some(i) => indices.push(i),
                    None => {
                        let (out, _) = blockedit::resize(
                            &self.file,
                            palette,
                            &[Op::CloneAppend {
                                donor: 0,
                                copies: 1,
                            }],
                        )?;
                        self.file = out;
                        let i = palette_before + appended;
                        apply_set(
                            &mut self.file,
                            &format!("{palette}[{i}].name"),
                            &format!("{ref_group}:{}", o.tag),
                        )?;
                        println!("  palette {palette}[{i}] <- {}", o.tag);
                        indices.push(i);
                        appended += 1;
                    }
                }
            }
            let donor = nearest_donor(&self.file, block, before, ue_to_blam(self.origin))?;
            println!("  {block:9} donor [{donor}] (nearest to the level origin)");
            let (out, _) = blockedit::resize(
                &self.file,
                block,
                &[Op::CloneAppend {
                    donor,
                    copies: of_group.len(),
                }],
            )?;
            self.file = out;
            for (j, (o, palette_idx)) in of_group.iter().zip(&indices).enumerate() {
                let i = before + j;
                let (x, y, z) = ue_to_blam(abs_pos(self.origin, o.pos));
                let yaw = ue_yaw_to_blam(o.rot[1]);
                let uid = self.unique_id();
                let p = |f: &str| format!("{block}[{i}].{f}");
                apply_set(&mut self.file, &p("type"), &format!("#{palette_idx}"))?;
                apply_set(&mut self.file, &p("name"), "none")?;
                apply_set(
                    &mut self.file,
                    &p("object data.position"),
                    &format!("({x}, {y}, {z})"),
                )?;
                apply_set(
                    &mut self.file,
                    &p("object data.rotation"),
                    &format!("({yaw}, 0, 0)"),
                )?;
                apply_set(&mut self.file, &p("object data.placement flags"), "0x20")?;
                apply_set(
                    &mut self.file,
                    &p("object data.object id.unique id"),
                    &format!("{uid}"),
                )?;
                for (field, value) in &o.set {
                    apply_set(&mut self.file, &p(field), value)
                        .with_context(|| format!("{block}[{i}].{field} = {value:?}"))?;
                }
                println!("  {block:9} [{i}] {} at ({x:.3}, {y:.3}, {z:.3}) wu", o.tag);
            }
            // So a clear of the canvas's own scenery keeps these, the way the
            // typed lanes' appends are kept.
            *self.added.entry(block).or_default() += of_group.len();
        }
        Ok(())
    }

    /// Replace the mission's whole script section with one startup script.
    ///
    /// Emptying the block would be simpler, but a Blam map boots with the
    /// screen faded out, the HUD hidden and every player input faded to
    /// nothing: the mission's own script is what hands those back. A map with
    /// no script at all therefore loads black and frozen, with a live
    /// simulation behind it — and `(player_enable_input true)` alone is not
    /// the key. This engine's missions enter gameplay through
    /// `f_insertion_fade_to_gameplay` (see any shipped scenario's
    /// `global_scripts`): wait for the players to be active, then
    /// `player_control_fade_in_all_input`, bring the HUD and screen back, and
    /// raise the weapon; an outro cinematic locks with `player_disable_movement`
    /// and `player_control_lock_gaze` as well, so those are released too. Without the input fade-in the player can look around
    /// but not move, shoot or switch weapons, exactly as a cutscene holds
    /// them. This writes the smallest script that does all of that. The wait
    /// is bounded, so a level never hangs on a predicate this build might
    /// never satisfy, and the weapon is lowered first the way the shipped
    /// helper does — which also makes a stalled script visible: a lowered
    /// weapon on a playable map means the wait never returned.
    fn stub_scripts(&mut self) -> Result<()> {
        const STUB: &str = "(script startup mjolnir_level_startup
  (begin
    (submit_incident_with_custom_string_id \"game_activity_begin\" \"mjolnir\")
    (unit_lower_weapon player0 1)
    (sleep_until (game_all_players_active) 1 (game_ticks_from_seconds 5.0))
    (sleep 1)
    (player_control_fade_in_all_input 1.0)
    (chud_cinematic_fade 1.0 30)
    (fade_in 0.0 0.0 0.0 30)
    (camera_control false)
    (player_enable_input true)
    (player_disable_movement false)
    (player_control_unlock_gaze player0)
    (unit_raise_weapon player0 30)))
";
        let corpus_path = crate::resolve_data_path(Path::new("defs/hce/scripting.json"));
        let corpus = blam_hsc::ScriptCorpus::load(&corpus_path).with_context(|| {
            format!(
                "clear.scripts needs the scripting corpus at {}; run `mjolnir scripting` first",
                corpus_path.display()
            )
        })?;

        let tag = TagFile::parse(&self.file, None)?;
        let layout = tag.layout()?;
        let block = tag.read_data(&layout)?;
        let original = blam_hsc::read::read(&layout, &block, &self.file)?;

        let compiled =
            blam_hsc::Compiler::from_corpus(&corpus).compile(&[("mjolnir_level_startup", STUB)]);
        if !compiled.ok() {
            let first = compiled
                .errors()
                .next()
                .map(|e| e.message.clone())
                .unwrap_or_default();
            bail!("the startup script did not compile: {first}");
        }

        let mut section = compiled.section;
        section.shapes = original.shapes;
        // The source text goes with it, so `mjolnir script --source` still
        // shows what the level runs.
        section.source_files = Vec::new();

        self.file = blam_hsc::emit::rewrite(&section, &self.file)
            .map_err(|e| anyhow::anyhow!("writing the startup script: {e}"))?;
        println!(
            "  clear   scripts: {} -> 1 script (startup: wait for players, fade input, HUD and screen in)",
            original.scripts.len()
        );
        Ok(())
    }

    /// Drop the host mission's own placements, keeping this bake's appends.
    /// Runs AFTER the placement passes so their donors still existed.
    fn clears(&mut self, clear: &Clear) -> Result<()> {
        let added = self.added.clone();
        let mut wipe = |name: &str| -> Result<()> {
            let keep = added.get(name).copied().unwrap_or(0);
            let op = if keep > 0 {
                Op::KeepLast { keep }
            } else {
                Op::Truncate { keep: 0 }
            };
            let (out, r) = blockedit::resize(&self.file, name, &[op])?;
            self.file = out;
            println!("  clear   {name}: {} -> {} element(s)", r.before, r.after);
            Ok(())
        };
        if clear.vehicles {
            wipe("vehicles")?;
        }
        if clear.weapons {
            wipe("weapons")?;
        }
        if clear.equipment {
            wipe("equipment")?;
        }
        if clear.bipeds {
            wipe("bipeds")?;
        }
        if clear.squads {
            wipe("squads")?;
        }
        for name in &clear.blocks {
            wipe(name)?;
        }
        drop(wipe);
        if clear.scripts {
            self.stub_scripts()?;
        }
        Ok(())
    }
}

fn bake(a: BakeArgs) -> Result<()> {
    let level = load_level(&a.file)?;
    for note in validate_level(&level)? {
        println!("note: {note}");
    }
    let map = palette_map()?;
    let scen = level.canvas.scenario.to_uppercase();

    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group.get("scenario").context("no scenario tags")?;
    let want = format!("{}-scenario", scen.to_lowercase());
    let entry = entries
        .iter()
        .find(|e| e.path.to_lowercase().contains(&want))
        .copied()
        .with_context(|| format!("no scenario tag for {scen}"))?;

    let original = idx.read(entry, None, &a.src.oodle_roots())?;
    println!("{}", entry.path);
    println!("  source   {} bytes", original.len());

    let mut baker = Baker {
        file: original.clone(),
        origin: level.canvas.origin,
        next_unique: UNIQUE_ID_BASE,
        added: Default::default(),
    };

    // Placements first — their donors are cloned from the shipped blocks —
    // then the clears, which keep only what this bake appended. Clears never
    // touch player starts or the structure blocks.
    baker.player_starts(&level.blam.player_starts)?;
    baker.typed(
        "vehicles",
        "vehicle palette",
        &level.blam.vehicles,
        &map.vehicles,
    )?;
    baker.typed(
        "weapons",
        "weapon palette",
        &level.blam.weapons,
        &map.weapons,
    )?;
    baker.typed(
        "equipment",
        "equipment palette",
        &level.blam.equipment,
        &map.equipment,
    )?;
    baker.objects(&level.blam.objects)?;
    baker.clears(&level.blam.clear)?;
    if level.blam.map_variant {
        let mut tags: BTreeMap<(String, String), usize> = BTreeMap::new();
        // Equipment too: grenades, the overshield and camouflage are created
        // only through the map variant as well (they never appeared on Blood
        // Gulch while the palette listed vehicles and weapons alone).
        for (items, table, group) in [
            (&level.blam.vehicles, &map.vehicles, "vehi"),
            (&level.blam.weapons, &map.weapons, "weap"),
            (&level.blam.equipment, &map.equipment, "eqip"),
        ] {
            for item in items {
                if let Some(path) = table.get(&item.kind) {
                    let variant = item
                        .set
                        .get("permutation data.variant name")
                        .cloned()
                        .unwrap_or_default();
                    *tags
                        .entry((format!("{group}:{path}"), variant))
                        .or_default() += 1;
                }
            }
        }
        for o in &level.blam.objects {
            let group = if o.group == "scenery" { "scen" } else { "bloc" };
            *tags
                .entry((format!("{group}:{}", o.tag), String::new()))
                .or_default() += 1;
        }
        let tags: Vec<((String, String), usize)> = tags.into_iter().collect();
        baker.map_variant_palette(&tags)?;
    }
    if !level.blam.active_bsps.is_empty() {
        baker.active_bsps(&level.blam.active_bsps)?;
    }
    for (path, value) in &level.blam.set {
        apply_set(&mut baker.file, path, value)
            .with_context(|| format!("blam.set {path:?} = {value:?}"))?;
        println!("  set     {path} = {value}");
    }
    for wb in &level.blam.world_bounds {
        for (axis, name) in ["x", "y", "z"].iter().enumerate() {
            apply_set(
                &mut baker.file,
                &format!("structure bsps[{}].world bounds {name}", wb.bsp),
                &format!("({}, {})", wb.min[axis], wb.max[axis]),
            )?;
        }
        println!(
            "  bounds  structure bsps[{}] -> ({:.2}, {:.2}, {:.2}) .. ({:.2}, {:.2}, {:.2}) wu",
            wb.bsp, wb.min[0], wb.min[1], wb.min[2], wb.max[0], wb.max[1], wb.max[2]
        );
    }

    // Structure BSPs of the standalone map's own: each `--bsp` clones the
    // referenced BSP tag and its lighting-info tag under the codename's
    // folder — the BSP with the given body, the lighting info as shipped —
    // and repoints the scenario's references. The clones are the shipped
    // wrappers with the codename swapped into the package path (same-length
    // surgery, like the scenario's own), which is what the simulation derives
    // the tag path from; a wrapper rebuilt from scratch for this group loads
    // but the map never starts. Ordinary new tags resolve by name the moment
    // a reference names them, so the scenario package needs no import.
    let mut extra_packages: Vec<blam_pack::NewPackage> = Vec::new();
    if !a.bsps.is_empty() {
        let code = a
            .standalone
            .as_deref()
            .context("--bsp needs --standalone: a canvas override keeps the canvas BSPs")?
            .to_uppercase();
        let oodle = a.src.oodle_roots();
        let old_seg = format!("\\{}\\", scen.to_lowercase());
        let new_seg = format!("\\{}\\", code.to_lowercase());
        ensure_same_len(&old_seg, &new_seg)?;
        for spec in &a.bsps {
            let (index, payload) = spec
                .split_once('=')
                .with_context(|| format!("--bsp takes INDEX=PAYLOAD, got {spec:?}"))?;
            let index: usize = index
                .parse()
                .with_context(|| format!("--bsp index {index:?}"))?;
            let new_body = std::fs::read(payload)
                .with_context(|| format!("cannot read BSP payload {payload}"))?;
            // (field, group directory, four-CC, replacement body)
            let parts: [(String, &str, &str, Option<&[u8]>); 2] = [
                (
                    format!("structure bsps[{index}].structure bsp"),
                    "scenario_structure_bsp",
                    "sbsp",
                    Some(&new_body),
                ),
                (
                    format!("structure bsps[{index}].structure lighting_info"),
                    "scenario_structure_lighting_info",
                    "stli",
                    None,
                ),
            ];
            for (field, group, cc, body) in parts {
                let current = {
                    let tag = TagFile::parse(&baker.file, Some(baker.file.len()))?;
                    let l = tag.layout()?;
                    let block = tag.read_data(&l)?;
                    reference_path(&l, &baker.file, &block, &field)?
                };
                let new_path = current.replace(&old_seg, &new_seg);
                if new_path == current {
                    bail!("{field} = {current:?} does not carry the canvas codename to replace");
                }
                let leaf = current.rsplit('\\').next().unwrap_or(&current).to_string();
                let want = format!("/{}/_generated_/{leaf}-{group}", scen.to_lowercase());
                let entries = by_group
                    .get(group)
                    .with_context(|| format!("no {group} tags"))?;
                let donor_entry = entries
                    .iter()
                    .find(|e| e.path.to_ascii_lowercase().contains(&want))
                    .copied()
                    .with_context(|| format!("no shipped {group} tag package for {current}"))?;
                let source = &idx.containers[donor_entry.container];
                let uasset_chunk = source
                    .chunks
                    .iter()
                    .find(|c| c.chunk_id == donor_entry.chunk.chunk_id && c.chunk_type == 1)
                    .context("the tag has no package chunk beside its payload")?;
                let donor_uasset = ue_iostore::read_chunk(source, uasset_chunk, None, &oodle)?;
                let donor_body = idx.read(donor_entry, None, &oodle)?;
                let body: Vec<u8> = body
                    .map(<[u8]>::to_vec)
                    .unwrap_or_else(|| donor_body.clone());
                let (uasset_meta, ubulk_meta) =
                    blam_pack::newtag::donor_chunk_meta(source, donor_entry.chunk.chunk_id)
                        .map_err(|e| anyhow::anyhow!(e))?;
                let donor_pkg = ue_asset::zen::Package::parse(&donor_uasset)
                    .map_err(|e| anyhow::anyhow!("{group} donor package: {e}"))?;
                let old_pkg = donor_pkg.name.clone();
                let new_pkg = old_pkg.replace(
                    &format!("/{}/", scen.to_uppercase()),
                    &format!("/{}/", code),
                );
                ensure_same_len(&old_pkg, &new_pkg)?;
                let uasset = crate::rename::clone_tag_uasset(
                    &donor_uasset,
                    &[(old_pkg.clone(), new_pkg.clone())],
                    donor_body.len(),
                    body.len(),
                )?;
                let imported: Vec<u64> = donor_pkg
                    .imported_package_names
                    .iter()
                    .map(|n| ue_iostore::city::package_id(n))
                    .collect();
                println!(
                    "  {cc}     [{index}] {current}\n        -> {new_path} ({} bytes)",
                    body.len()
                );
                apply_set(&mut baker.file, &field, &format!("{cc}:{new_path}"))?;
                extra_packages.push(blam_pack::NewPackage {
                    package_name: new_pkg,
                    uasset,
                    ubulk: body,
                    imported_package_ids: imported,
                    uasset_meta,
                    ubulk_meta,
                });
            }
        }
    }

    if let Some(keep) = level.blam.single_bsp {
        baker.single_bsp(keep)?;
    }

    // The map's own Unreal world, when one is given: the bare level renamed
    // under the codename (a world with no cells refers to itself by nothing
    // but its name) and added beside the scenario. The registration row then
    // points its `UnrealLevel` at it instead of the canvas mission's world.
    let mut world_object: Option<String> = a.world_object.clone();
    if world_object.is_some() && a.standalone.is_none() {
        bail!("--world-object needs --standalone");
    }
    if let Some(world_file) = &a.world {
        let code = a
            .standalone
            .as_deref()
            .context("--world needs --standalone: a canvas override keeps the canvas world")?
            .to_uppercase();
        let data = std::fs::read(world_file)
            .with_context(|| format!("cannot read world {}", world_file.display()))?;
        let mut zp = ue_asset::package::ZenPackage::parse(&data)
            .map_err(|e| anyhow::anyhow!("world package: {e}"))?;
        let old_pkg = zp.name();
        // A world named for a mission sits at `/<X>/<X>`: the canvas
        // mission's (a shipped donor) or an earlier map's (a bare world taken
        // back out of a standalone bake). Either renames to the codename.
        let (parent, leaf) = old_pkg.rsplit_once('/').unwrap_or(("", ""));
        let own = parent.rsplit('/').next().unwrap_or("");
        if leaf.is_empty() || !own.eq_ignore_ascii_case(leaf) {
            bail!("world {old_pkg} is not at a mission's /<X>/<X> path (canvas /{scen}/{scen})");
        }
        let new_pkg = format!("{}/{code}/{code}", &parent[..parent.len() - own.len() - 1]);
        ensure_same_len(&old_pkg, &new_pkg)?;
        if new_pkg != old_pkg {
            for line in zp
                .rename_world(&new_pkg)
                .map_err(|e| anyhow::anyhow!("world rename: {e}"))?
            {
                println!("  world    {line}");
            }
        } else {
            println!("  world    {old_pkg} already carries the codename");
        }
        for line in blam_world_settings(&mut zp, &idx.containers, &a.src.oodle_roots())? {
            println!("  world    {line}");
        }
        let imported: Vec<u64> = zp
            .imported_package_names
            .names
            .iter()
            .map(|n| ue_iostore::city::package_id(n))
            .collect();
        // A shipped world's bulk data (its textures) rides a `.ubulk` beside
        // the `.umap`; the bare MapKit world has none.
        let ubulk_file = world_file.with_extension("ubulk");
        let ubulk = if ubulk_file.is_file() {
            let b = std::fs::read(&ubulk_file)?;
            println!(
                "  world    bulk data {} ({} bytes)",
                ubulk_file.display(),
                b.len()
            );
            b
        } else {
            Vec::new()
        };
        extra_packages.push(blam_pack::NewPackage {
            package_name: new_pkg.clone(),
            uasset: zp.write(),
            ubulk,
            imported_package_ids: imported,
            uasset_meta: Vec::new(),
            ubulk_meta: Vec::new(),
        });
        world_object = Some(format!("{new_pkg}.{code}"));
    }

    let file = baker.file;

    // The same exactness gate `pack` applies before anything leaves the tool.
    let tag = TagFile::parse(&file, Some(file.len()))?;
    let l = tag.layout()?;
    let block = tag.read_data(&l)?;
    let payload = tag.data().context("baked tag has no bdat section")?;
    if block.consumed != payload.size as usize {
        bail!("the baked tag no longer walks exactly");
    }
    println!(
        "  payload  {} -> {} bytes, walks exactly",
        original.len(),
        file.len()
    );
    if let Some(p) = &a.write_tag {
        std::fs::write(p, &file).with_context(|| format!("writing {}", p.display()))?;
        println!("  tag      wrote {}", p.display());
    }

    let source = &idx.containers[entry.container];
    let (built, name) = if let Some(code) = &a.standalone {
        let code = code.to_uppercase();
        if code.len() != 3 || !code.chars().all(|c| c.is_ascii_alphanumeric()) {
            bail!("--standalone takes exactly three [A-Z0-9] characters, got {code:?}");
        }
        // The donor package: the canvas scenario's own .uasset, renamed.
        let toc = ue_iostore::toc::Toc::read(&source.utoc_path)
            .map_err(|e| anyhow::anyhow!("{}: {e}", source.utoc_path.display()))?;
        let uasset_chunk = source
            .chunks
            .iter()
            .find(|c| c.chunk_id == entry.chunk.chunk_id && c.chunk_type == 1)
            .context("the scenario has no package chunk beside its payload")?;
        let donor_uasset =
            ue_iostore::read_chunk(source, uasset_chunk, None, &a.src.oodle_roots())?;
        let meta_of = |kind: u8| -> Vec<u8> {
            toc.chunk_ids
                .iter()
                .position(|c| c.id == entry.chunk.chunk_id && c.kind == kind)
                .and_then(|slot| toc.meta(slot))
                .map(<[u8]>::to_vec)
                .unwrap_or_default()
        };

        let donor = ue_asset::zen::Package::parse(&donor_uasset)
            .map_err(|e| anyhow::anyhow!("donor package: {e}"))?;
        let old_pkg = donor.name.clone(); // "/Game/Tags/.../B40-scenario"
        let old_leaf = old_pkg
            .rsplit('/')
            .next()
            .context("donor package name has no leaf")?
            .to_string();
        let new_leaf = format!("{code}-scenario");
        ensure_same_len(&old_leaf, &new_leaf)?;
        // The campaign flow derives the scenario tag's package path from the
        // data-table row name — `.../Solo/<NAME>/_Generated_/<NAME>-scenario`
        // — so the new package must sit in a folder named after the codename,
        // not in the donor's. The folder segment is the donor's own codename
        // (same length), so the rename stays same-length surgery.
        let old_code = old_leaf.trim_end_matches("-scenario").to_string();
        let old_dir = old_pkg.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
        let new_dir = old_dir.replace(&format!("/{old_code}/"), &format!("/{code}/"));
        let new_pkg = format!("{new_dir}/{new_leaf}");
        ensure_same_len(&old_pkg, &new_pkg)?;
        let imported: Vec<u64> = donor
            .imported_package_names
            .iter()
            .map(|n| ue_iostore::city::package_id(n))
            .collect();
        println!(
            "  package  {old_pkg}\n        -> {new_pkg}\n  imports  {} package(s)",
            imported.len()
        );

        let uasset = crate::rename::clone_tag_uasset(
            &donor_uasset,
            &[
                (old_leaf.clone(), new_leaf.clone()),
                (old_pkg.clone(), new_pkg.clone()),
            ],
            original.len(),
            file.len(),
        )?;

        let container_name = format!("pakchunk997-MJOLNIRMAP-{code}");
        let mut packages = vec![blam_pack::NewPackage {
            package_name: new_pkg,
            uasset,
            ubulk: file.clone(),
            imported_package_ids: imported,
            uasset_meta: meta_of(1),
            ubulk_meta: meta_of(2),
        }];
        packages.append(&mut extra_packages);
        let built =
            blam_pack::build_addition(source, &a.src.oodle_roots(), &container_name, &packages)
                .map_err(|e| anyhow::anyhow!(e))?;
        (built, format!("{container_name}_P"))
    } else {
        let built = blam_pack::build_override(
            source,
            &a.src.oodle_roots(),
            &[blam_pack::ChunkEdit {
                label: entry.path.clone(),
                chunk: entry.chunk,
                original_len: original.len(),
                patched: file.clone(),
            }],
        )
        .map_err(|e| anyhow::anyhow!(e))?;
        (built, format!("pakchunk998-MJOLNIRLEVEL-{}_P", level.name))
    };
    let out_dir = if a.install_test {
        a.src.paks.clone()
    } else {
        a.out_dir.clone()
    };
    std::fs::create_dir_all(&out_dir)?;
    let utoc = out_dir.join(format!("{name}.utoc"));
    let ucas = out_dir.join(format!("{name}.ucas"));
    // Write to temp names and rename into place: a running game keeps the
    // mounted .ucas locked, and a direct write leaves a mismatched pair the
    // verifier then rejects. The rename either fully lands or fully fails.
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
    println!("  wrote    {} ({} bytes)", utoc.display(), built.utoc.len());
    println!("  wrote    {} ({} bytes)", ucas.display(), built.ucas.len());

    // A standalone codename also has to be registered: a cooked
    // `DT_Scenarios` row and a `ScenarioList` handle, which is what the
    // simulation's map registry is built from at boot
    // (`blam_pack::scenario`). The scenario package alone launches nothing.
    let mut undo = format!("the three {name}.* files");
    if let Some(code) = &a.standalone {
        let code = code.to_uppercase();
        let oodle = a.src.oodle_roots();
        let usmap = crate::mesh::usmap()?;
        let scripts = crate::mesh::script_objects(&idx.containers, &oodle)?;
        let reg = blam_pack::scenario::Registration {
            code: code.clone(),
            from: scen.to_uppercase(),
            title: level.title.clone(),
            description: level.description.clone(),
            world: world_object.clone(),
        };
        // The record also goes beside the bake's output: `mjolnir map pack`
        // ships it in the map's pack, and the launcher registers the map from
        // it (docs/map_distribution.md).
        if !a.install_test {
            let record = out_dir.join(format!("{code}.registration.json"));
            std::fs::write(&record, serde_json::to_vec_pretty(&reg)?)?;
            println!("  wrote    {}", record.display());
        }
        // Every installed map shares one registration container (the table
        // and the campaign asset are single shipped packages), so the
        // container is built from this map plus every map recorded beside the
        // loader: neither an install nor a bake copied in by hand unregisters
        // another map. Only an install records this one.
        let mut regs = vec![reg.clone()];
        if let Some(dir) = loader_registry_dir(&a.src.paks).filter(|d| a.install_test || d.is_dir())
        {
            if a.install_test {
                std::fs::create_dir_all(&dir)?;
                std::fs::write(
                    dir.join(format!("{code}.json")),
                    serde_json::to_vec_pretty(&reg)?,
                )?;
            }
            let mut files: Vec<PathBuf> = std::fs::read_dir(&dir)?
                .filter_map(|e| e.ok().map(|e| e.path()))
                .filter(|p| p.extension().map(|x| x == "json").unwrap_or(false))
                .collect();
            files.sort();
            for f in files {
                let r: blam_pack::scenario::Registration =
                    serde_json::from_slice(&std::fs::read(&f)?)
                        .with_context(|| format!("registration record {}", f.display()))?;
                if r.code != reg.code {
                    regs.push(r);
                }
            }
            regs.sort_by(|x, y| x.code.cmp(&y.code));
            println!(
                "  register {} map(s) recorded in {}: {}",
                regs.len(),
                dir.display(),
                regs.iter()
                    .map(|r| r.code.as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            );
            // Per-map registration containers from older bakes would
            // shadow the shared one.
            for e in std::fs::read_dir(&out_dir)?.filter_map(|e| e.ok()) {
                let n = e.file_name().to_string_lossy().to_string();
                if n.starts_with("pakchunk996-MJOLNIRREG-") {
                    std::fs::remove_file(e.path())?;
                    println!(
                        "  removed  {n} (superseded by {})",
                        blam_pack::scenario::CONTAINER
                    );
                }
            }
        }
        let (built, reg_name, log) =
            blam_pack::scenario::register(&idx.containers, &oodle, &usmap, &scripts, &regs)
                .map_err(|e| anyhow::anyhow!(e))?;
        for line in &log {
            println!("  register {line}");
        }
        let utoc = out_dir.join(format!("{reg_name}.utoc"));
        let ucas = out_dir.join(format!("{reg_name}.ucas"));
        stage(&utoc, &built.utoc)?;
        stage(&ucas, &built.ucas)?;
        blam_pack::verify_written(&utoc, &oodle, &built.expect).map_err(|e| anyhow::anyhow!(e))?;
        println!("  wrote    {} ({} bytes)", utoc.display(), built.utoc.len());
        println!("  wrote    {} ({} bytes)", ucas.display(), built.ucas.len());
        if a.install_test {
            let pak = out_dir.join(format!("{reg_name}.pak"));
            std::fs::write(&pak, ue_iostore::pak::stub_for(&reg_name))?;
            println!("  wrote    {} (stub)", pak.display());
        }
        undo = format!("the three {name}.* and three {reg_name}.* files");
    }

    if a.install_test {
        // A .utoc/.ucas pair never mounts without a .pak sibling
        // (docs/iostore_packaging.md).
        let pak = out_dir.join(format!("{name}.pak"));
        std::fs::write(&pak, ue_iostore::pak::stub_for(&name))?;
        println!("  wrote    {} (stub)", pak.display());

        // The loader keys a standalone map's decor by its codename, a
        // canvas override's by the canvas scenario.
        let file_key = a
            .standalone
            .as_ref()
            .map(|c| c.to_uppercase())
            .unwrap_or_else(|| scen.to_string());
        if let Some(loader_levels) = loader_levels_dir(&a.src.paks) {
            std::fs::create_dir_all(&loader_levels)?;
            let dest = loader_levels.join(format!("{file_key}.level.json"));
            std::fs::copy(&a.file, &dest)?;
            println!("  wrote    {} (decor for the loader)", dest.display());
            if a.standalone.is_some() {
                write_maps_index(&a.src.paks)?;
            }
        } else {
            println!("  note: UE4SS Mods directory not found; decor file not installed");
        }
        println!(
            "
  Launch {file_key} through the game's own menu (mjolnir_mission does"
        );
        println!("  not cold-start the simulation on current builds).");
        println!("  To undo: delete {undo}.");
    } else {
        println!("\n  Install: copy both files plus a stub .pak sibling into the game's");
        println!("  Paks folder, or re-run with --install-test.");
    }
    Ok(())
}

/// Every package in the containers by `/Game/...` name: the container and
/// chunk of its `.uasset`/`.umap`, and of its `.ubulk` when it has one. A
/// later container (an override) replaces an earlier one's entry.
/// Container and chunk index of a package's `.uasset`/`.umap`, and of its
/// `.ubulk` when it has one.
type PackageSlot = (usize, usize, Option<(usize, usize)>);

struct PackageIndex {
    entries: std::collections::HashMap<String, PackageSlot>,
}

impl PackageIndex {
    fn build(containers: &[ue_iostore::Container]) -> PackageIndex {
        let mut entries: std::collections::HashMap<String, PackageSlot> =
            std::collections::HashMap::new();
        for (ci, c) in containers.iter().enumerate() {
            for (rel, chunk_index) in &c.files {
                let full = c.full_path(rel);
                if full.ends_with(".uptnl") {
                    continue;
                }
                let Some(name) = ue_asset::level::package_name_of(&full) else {
                    continue;
                };
                let is_bulk = full.ends_with(".ubulk");
                let entry = entries.entry(name.to_ascii_lowercase()).or_insert((
                    usize::MAX,
                    usize::MAX,
                    None,
                ));
                if is_bulk {
                    entry.2 = Some((ci, *chunk_index));
                } else {
                    entry.0 = ci;
                    entry.1 = *chunk_index;
                }
            }
        }
        entries.retain(|_, e| e.0 != usize::MAX);
        PackageIndex { entries }
    }

    fn get(&self, name: &str) -> Option<&PackageSlot> {
        self.entries.get(&name.to_ascii_lowercase())
    }
}

fn export(a: ExportArgs) -> Result<()> {
    use ue_asset::level::{mission_cells, ExportOptions, Exporter};

    let containers = ue_iostore::load_all(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let index = PackageIndex::build(&containers);
    let usmap = crate::mesh::usmap()?;
    let scripts = crate::mesh::script_objects(&containers, &oodle)?;
    let read = |ci: usize, chunk: usize| -> Option<Vec<u8>> {
        ue_iostore::read_chunk(&containers[ci], &containers[ci].chunks[chunk], None, &oodle).ok()
    };
    let load_package = |name: &str| -> Option<Vec<u8>> {
        let (ci, chunk, _) = index.get(name)?;
        read(*ci, *chunk)
    };
    let load_bulk = |name: &str| -> Option<Vec<u8>> {
        let (_, _, bulk) = index.get(name)?;
        let (ci, chunk) = (*bulk)?;
        read(ci, chunk)
    };
    let mut exporter = Exporter::new(
        &usmap,
        &scripts,
        &load_package,
        &load_bulk,
        ExportOptions {
            nanite: a.nanite,
            include_hlod: a.hlod,
        },
    );

    let mut cells = mission_cells(index.entries.keys().map(|k| k.as_str()), &a.mission);
    if let Some(want) = &a.cell {
        let want = want.to_ascii_lowercase();
        cells.retain(|k| k.contains(&want));
    }
    if let Some(limit) = a.limit {
        cells.truncate(limit);
    }
    if cells.is_empty() {
        bail!("no level package for mission {:?}", a.mission);
    }
    std::fs::create_dir_all(&a.out)?;

    let mut manifest_cells: Vec<serde_json::Value> = Vec::new();
    let mut total_placements = 0usize;
    let mut total_instanced = 0usize;
    let mut total_skips: BTreeMap<String, usize> = BTreeMap::new();
    let mut files = 0usize;
    for key in &cells {
        let cell = match exporter.export_cell(key, !a.dry_run) {
            Ok(c) => c,
            Err(e) => {
                eprintln!("{e}");
                continue;
            }
        };
        total_placements += cell.placements;
        total_instanced += cell.instanced;
        for (k, v) in &cell.skips {
            *total_skips.entry(k.clone()).or_default() += v;
        }
        let skips: Vec<String> = cell.skips.iter().map(|(k, v)| format!("{v} {k}")).collect();
        println!(
            "{}: {} actors, {} placements ({} instanced) of {} meshes{}",
            cell.id,
            cell.actors,
            cell.placements,
            cell.instanced,
            cell.meshes,
            if skips.is_empty() {
                String::new()
            } else {
                format!("; skipped {}", skips.join(", "))
            }
        );
        let mut entry = serde_json::json!({
            "package": cell.package,
            "actors": cell.actors,
            "placements": cell.placements,
            "instanced": cell.instanced,
            "meshes": cell.meshes,
            "skips": cell.skips,
        });
        if !cell.missing.is_empty() {
            let list: Vec<String> = cell
                .missing
                .iter()
                .take(5)
                .map(|(k, v)| format!("{k} ×{v}"))
                .collect();
            println!(
                "  {} mesh(es) not readable, placements dropped: {}",
                cell.missing.len(),
                list.join(", ")
            );
            entry["missing_meshes"] = serde_json::json!(cell.missing);
        }
        if let Some(glb) = &cell.glb {
            let path = a.out.join(format!("{}.glb", cell.id));
            std::fs::write(&path, glb).with_context(|| format!("writing {}", path.display()))?;
            entry["file"] = serde_json::json!(path.file_name().unwrap().to_string_lossy());
            entry["bytes"] = serde_json::json!(glb.len());
            files += 1;
        }
        manifest_cells.push(entry);
    }
    let manifest = serde_json::json!({
        "mission": a.mission,
        "nanite": a.nanite,
        "hlod": a.hlod,
        "cells": manifest_cells,
        "totals": {
            "cells": cells.len(),
            "placements": total_placements,
            "instanced": total_instanced,
            "files": files,
            "skips": total_skips,
        },
    });
    if !a.dry_run {
        std::fs::write(
            a.out.join("manifest.json"),
            serde_json::to_string_pretty(&manifest)?,
        )?;
    }
    let skips: Vec<String> = total_skips
        .iter()
        .map(|(k, v)| format!("{v} {k}"))
        .collect();
    println!(
        "{} cells, {total_placements} placements ({total_instanced} instanced), {files} file(s){}",
        cells.len(),
        if skips.is_empty() {
            String::new()
        } else {
            format!("; skipped {}", skips.join(", "))
        }
    );
    Ok(())
}

fn ensure_same_len(old: &str, new: &str) -> Result<()> {
    anyhow::ensure!(
        old.len() == new.len(),
        "codename length mismatch: {old:?} vs {new:?}"
    );
    Ok(())
}

/// `<paks>/../../Binaries/Win64/ue4ss/Mods/MJOLNIRLevelLoader/levels`, if the
/// UE4SS mods tree exists.
/// Make the world's settings a `BlamWorldSettings`, as every shipped level's
/// are. The game creates some world subsystems only for a Blam world: on the
/// bare MapKit world (plain `WorldSettings`) `HaloMaterialResponseWorldSubsystem`
/// and `BlamMapGlueOuterSubsystem` never existed, and with them went bullet
/// impacts, tracers and surface-dependent footsteps (2026-10-01, compared
/// with B40's world). The export keeps its properties: unversioned slots
/// number a class's own properties first, so each moves up by the
/// subclass's count.
fn blam_world_settings(
    zp: &mut ue_asset::package::ZenPackage,
    containers: &[ue_iostore::Container],
    oodle: &[PathBuf],
) -> Result<Vec<String>> {
    use ue_asset::package::script_import_index;
    let plain = script_import_index("/Script/Engine.WorldSettings");
    let plain_cdo = script_import_index("/Script/Engine.Default__WorldSettings");
    let blam = script_import_index("/Script/BlamEngine.BlamWorldSettings");
    let blam_cdo = script_import_index("/Script/BlamEngine.Default__BlamWorldSettings");
    if zp.export_map.iter().any(|e| e.class == blam) {
        return Ok(vec!["settings are already BlamWorldSettings".into()]);
    }
    let Some(i) = zp.export_map.iter().position(|e| e.class == plain) else {
        return Ok(vec![
            "no WorldSettings export; settings left as they are".into()
        ]);
    };
    let usmap = crate::mesh::usmap()?;
    let scripts = crate::mesh::script_objects(containers, oodle)?;
    let mut edit =
        ue_asset::edit::open_export(zp, &usmap, &scripts, i).map_err(|e| anyhow::anyhow!(e))?;
    let shift = usmap.total_slots("BlamWorldSettings") - usmap.total_slots("WorldSettings");
    for (slot, _) in edit.block.values.iter_mut() {
        *slot += shift;
    }
    edit.class = "BlamWorldSettings".into();
    // The subsystems' gate (the glue engine subsystem's slot 93, CU4
    // +0x7b93a50) requires a BlamWorldSettings whose DefaultScenario path is
    // set; a shipped level points it at its BlamScenario actor. Ours names
    // one in the persistent level by the same convention.
    let world_pkg = zp.name();
    let world_leaf = world_pkg.rsplit('/').next().unwrap_or_default().to_string();
    let package = zp.names.intern(&world_pkg);
    let asset = zp.names.intern(&world_leaf);
    let default_scenario = slot_named(&usmap, "BlamWorldSettings", "DefaultScenario")?;
    edit.block.set(
        default_scenario,
        ue_asset::props::Val::SoftObject {
            package: ue_asset::props::Name {
                index: package,
                number: 0,
            },
            asset: ue_asset::props::Name {
                index: asset,
                number: 0,
            },
            sub: "PersistentLevel.BlamScenario".into(),
        },
    );
    let e = &mut zp.export_map[i];
    e.class = blam;
    if e.template == plain_cdo {
        e.template = blam_cdo;
    }
    for imp in zp.import_map.iter_mut() {
        if *imp == plain {
            *imp = blam;
        } else if *imp == plain_cdo {
            *imp = blam_cdo;
        }
    }
    ue_asset::edit::write_export(zp, &usmap, &edit).map_err(|e| anyhow::anyhow!(e))?;
    Ok(vec![format!(
        "settings export {i} is now BlamWorldSettings ({} propert(ies) moved {shift} slot(s))",
        edit.block.values.len()
    )])
}

fn register(a: RegisterArgs) -> Result<()> {
    let layout = blam_pack::maps::Layout::for_paks(&a.src.paks);
    let usmap = crate::mesh::usmap()?;
    let done = blam_pack::maps::rebuild(&layout, &a.src.oodle_roots(), &usmap)
        .map_err(|e| anyhow::anyhow!(e))?;
    for line in &done.log {
        println!("  {line}");
    }
    println!(
        "{} map(s) registered{}",
        done.maps.len(),
        if done.maps.is_empty() {
            String::new()
        } else {
            format!(": {}", done.maps.join(", "))
        }
    );
    Ok(())
}

/// The multiplayer menu's list of installed maps (MJOLNIRLobby reads it,
/// since Lua cannot list a directory): every registered map's code, title,
/// description and game types, the level file's `modes` or else its
/// `variant`. Written beside the loader's `levels` directory as `maps.json`.
fn write_maps_index(paks: &Path) -> Result<()> {
    let (Some(registry), Some(levels)) = (loader_registry_dir(paks), loader_levels_dir(paks))
    else {
        return Ok(());
    };
    if !registry.is_dir() {
        return Ok(());
    }
    let mut files: Vec<PathBuf> = std::fs::read_dir(&registry)?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().map(|x| x == "json").unwrap_or(false))
        .collect();
    files.sort();
    let mut maps = Vec::new();
    for f in files {
        let reg: blam_pack::scenario::Registration = serde_json::from_slice(&std::fs::read(&f)?)
            .with_context(|| format!("registration record {}", f.display()))?;
        let level: Option<serde_json::Value> =
            std::fs::read(levels.join(format!("{}.level.json", reg.code)))
                .ok()
                .and_then(|b| serde_json::from_slice(&b).ok());
        let modes = level
            .as_ref()
            .and_then(|l| l.get("modes").cloned())
            .or_else(|| {
                level
                    .as_ref()
                    .and_then(|l| l.get("variant"))
                    .map(|v| serde_json::json!([v]))
            })
            .unwrap_or_else(|| serde_json::json!(["slayer"]));
        maps.push(serde_json::json!({
            "code": reg.code,
            "title": reg.title,
            "description": reg.description,
            "modes": modes,
        }));
    }
    let dest = levels.with_file_name("maps.json");
    std::fs::write(&dest, serde_json::to_vec_pretty(&maps)?)?;
    println!(
        "  wrote    {} ({} map(s) for the multiplayer menu)",
        dest.display(),
        maps.len()
    );
    Ok(())
}

/// Where installed maps record their registrations (one JSON file each).
fn loader_registry_dir(paks: &Path) -> Option<PathBuf> {
    loader_levels_dir(paks).map(|l| l.with_file_name("registry"))
}

fn loader_levels_dir(paks: &Path) -> Option<PathBuf> {
    let meteorite = paks.parent()?.parent()?;
    let mods = meteorite
        .join("Binaries")
        .join("Win64")
        .join("ue4ss")
        .join("Mods");
    if mods.is_dir() {
        Some(mods.join("MJOLNIRLevelLoader").join("levels"))
    } else {
        None
    }
}

/// A property's unversioned slot in `class` (its own properties first, then
/// each super's), by name.
fn slot_named(usmap: &ue_asset::Usmap, class: &str, want: &str) -> Result<u16> {
    let total = usmap.total_slots(class);
    let mut slot = 0u16;
    while slot < total {
        if let Some((_, prop)) = usmap.resolve(class, slot) {
            if prop.name == want {
                return Ok(slot);
            }
            slot += prop.array_dim.max(1) as u16;
        } else {
            slot += 1;
        }
    }
    bail!("{class} has no property {want}")
}
