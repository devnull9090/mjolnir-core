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
}

pub fn run(a: LevelArgs) -> Result<()> {
    match a.command {
        LevelCommand::Validate(a) => validate_cmd(a),
        LevelCommand::Selftest(a) => selftest(a),
        LevelCommand::Bake(a) => bake(a),
    }
}

// -----------------------------------------------------------------------------
// The level file
// -----------------------------------------------------------------------------

#[derive(Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
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
    #[serde(default)]
    pub blam: BlamSection,
    #[serde(default)]
    pub decor: Vec<serde_json::Value>,
    #[serde(default)]
    pub markers: Vec<serde_json::Value>,
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
}

#[derive(Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ObjectPlacement {
    pub tag: String,
    pub group: String,
    pub pos: [f64; 3],
    #[serde(default)]
    pub rot: [f64; 3],
    #[serde(default)]
    pub name: Option<String>,
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
    let raw = std::fs::read_to_string(path)
        .with_context(|| format!("reading {}", path.display()))?;
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
            bail!("objects[].group must be \"scenery\" or \"crates\", got {:?}", o.group);
        }
        if !o.tag.starts_with("objects\\") {
            bail!("objects[].tag must be a tag path under objects\\, got {:?}", o.tag);
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
        notes.push("clear.scripts is not implemented yet; the flag is ignored".to_string());
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

// -----------------------------------------------------------------------------
// Selftest: no-op resizes must be byte-exact on every shipped scenario
// -----------------------------------------------------------------------------

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
            println!("  ok  {:40} {:28} {} element(s)", entry.path, block, r.before);
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
}

impl Baker {
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
                &[Op::CloneAppend { donor, copies: extra }],
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
            apply_set(&mut self.file, &p("facing"), &format!("{}", ue_yaw_to_blam(start.yaw)))?;
            apply_set(&mut self.file, &p("pitch"), "0")?;
            apply_set(&mut self.file, &p("insertion point index"), "#0")?;
            apply_set(&mut self.file, &p("campaign player slot"), &format!("{}", j.min(3)))?;
            println!("  start   [{i}] <- ({x:.3}, {y:.3}, {z:.3}) wu, slot {}", j.min(3));
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
        if before == 0 {
            bail!("the canvas scenario's {block:?} block is empty — no donor to clone");
        }
        // Resolve every palette index before touching anything.
        let mut indices = Vec::new();
        for item in items {
            let tag_path = map
                .get(&item.kind)
                .with_context(|| format!("unknown type {:?}", item.kind))?;
            let idx = palette_index(&self.file, palette, tag_path)?
                .with_context(|| {
                    format!(
                        "{:?} ({tag_path}) is not in the canvas scenario's {palette:?} — \
                         v1 requires the palette to already carry it",
                        item.kind
                    )
                })?;
            indices.push(idx);
        }
        let (out, _) = blockedit::resize(
            &self.file,
            block,
            &[Op::CloneAppend { donor: 0, copies: items.len() }],
        )?;
        self.file = out;
        for (j, (item, palette_idx)) in items.iter().zip(&indices).enumerate() {
            let i = before + j;
            let (x, y, z) = ue_to_blam(abs_pos(self.origin, item.pos));
            let yaw = ue_yaw_to_blam(item.yaw);
            let uid = self.unique_id();
            let p = |f: &str| format!("{block}[{i}].{f}");
            apply_set(&mut self.file, &p("type"), &format!("#{palette_idx}"))?;
            apply_set(&mut self.file, &p("name"), "none")?;
            apply_set(&mut self.file, &p("object data.position"), &format!("({x}, {y}, {z})"))?;
            apply_set(&mut self.file, &p("object data.rotation"), &format!("({yaw}, 0, 0)"))?;
            // Bit 0 is "not automatically" (never spawns without a script);
            // bit 5 is "create at rest". Clones must actually spawn.
            apply_set(&mut self.file, &p("object data.placement flags"), "0x20")?;
            apply_set(&mut self.file, &p("object data.object id.unique id"), &format!("{uid}"))?;
            println!(
                "  {block:9} [{i}] {} at ({x:.3}, {y:.3}, {z:.3}) wu (palette #{palette_idx})",
                item.kind
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
                            &[Op::CloneAppend { donor: 0, copies: 1 }],
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
            let (out, _) = blockedit::resize(
                &self.file,
                block,
                &[Op::CloneAppend { donor: 0, copies: of_group.len() }],
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
                apply_set(&mut self.file, &p("object data.position"), &format!("({x}, {y}, {z})"))?;
                apply_set(&mut self.file, &p("object data.rotation"), &format!("({yaw}, 0, 0)"))?;
                apply_set(&mut self.file, &p("object data.placement flags"), "0x20")?;
                apply_set(&mut self.file, &p("object data.object id.unique id"), &format!("{uid}"))?;
                println!("  {block:9} [{i}] {} at ({x:.3}, {y:.3}, {z:.3}) wu", o.tag);
            }
        }
        Ok(())
    }

    /// Truncate the host mission's own placements away.
    fn clears(&mut self, clear: &Clear) -> Result<()> {
        let mut wipe = |name: &str| -> Result<()> {
            let (out, r) = blockedit::resize(&self.file, name, &[Op::Truncate { keep: 0 }])?;
            self.file = out;
            println!("  clear   {name}: {} -> 0 element(s)", r.before);
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
        if clear.scripts {
            println!("  clear   scripts: not implemented yet, ignored");
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
    };

    // Order: clears first (so nothing edited below is truncated away), then
    // placements. Clears never touch player starts.
    baker.clears(&level.blam.clear)?;
    baker.player_starts(&level.blam.player_starts)?;
    baker.typed("vehicles", "vehicle palette", &level.blam.vehicles, &map.vehicles)?;
    baker.typed("weapons", "weapon palette", &level.blam.weapons, &map.weapons)?;
    baker.typed("equipment", "equipment palette", &level.blam.equipment, &map.equipment)?;
    baker.objects(&level.blam.objects)?;

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

    let source = &idx.containers[entry.container];
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

    let name = format!("pakchunk998-MJOLNIRLEVEL-{}_P", level.name);
    let out_dir = if a.install_test {
        a.src.paks.clone()
    } else {
        a.out_dir.clone()
    };
    std::fs::create_dir_all(&out_dir)?;
    let utoc = out_dir.join(format!("{name}.utoc"));
    let ucas = out_dir.join(format!("{name}.ucas"));
    std::fs::write(&utoc, &built.utoc)?;
    std::fs::write(&ucas, &built.ucas)?;
    blam_pack::verify_written(&utoc, &a.src.oodle_roots(), &built.expect)
        .map_err(|e| anyhow::anyhow!(e))?;
    println!("  wrote    {} ({} bytes)", utoc.display(), built.utoc.len());
    println!("  wrote    {} ({} bytes)", ucas.display(), built.ucas.len());

    if a.install_test {
        // A .utoc/.ucas pair never mounts without a .pak sibling
        // (docs/iostore_packaging.md).
        let stub = stub_pak_bytes(&a.src.paks)?;
        let pak = out_dir.join(format!("{name}.pak"));
        std::fs::write(&pak, &stub)?;
        println!("  wrote    {} (stub)", pak.display());

        if let Some(loader_levels) = loader_levels_dir(&a.src.paks) {
            std::fs::create_dir_all(&loader_levels)?;
            let dest = loader_levels.join(format!("{scen}.level.json"));
            std::fs::copy(&a.file, &dest)?;
            println!("  wrote    {} (decor for the loader)", dest.display());
        } else {
            println!("  note: UE4SS Mods directory not found; decor file not installed");
        }
        println!("\n  Launch {scen} through the game's own menu (mjolnir_mission does");
        println!("  not cold-start the simulation on current builds).");
        println!("  To undo: delete the three pakchunk998-MJOLNIRLEVEL-* files.");
    } else {
        println!("\n  Install: copy both files plus a stub .pak sibling into the game's");
        println!("  Paks folder, or re-run with --install-test.");
    }
    Ok(())
}

/// `<paks>/../../Binaries/Win64/ue4ss/Mods/MJOLNIRLevelLoader/levels`, if the
/// UE4SS mods tree exists.
fn loader_levels_dir(paks: &Path) -> Option<PathBuf> {
    let meteorite = paks.parent()?.parent()?;
    let mods = meteorite.join("Binaries").join("Win64").join("ue4ss").join("Mods");
    if mods.is_dir() {
        Some(mods.join("MJOLNIRLevelLoader").join("levels"))
    } else {
        None
    }
}

/// The smallest shipped .pak, copied as the mount stub (same trick the tag
/// editor's test install uses).
fn stub_pak_bytes(paks: &Path) -> Result<Vec<u8>> {
    let mut smallest: Option<(u64, PathBuf)> = None;
    for entry in std::fs::read_dir(paks)?.flatten() {
        let path = entry.path();
        let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
        if !name.ends_with(".pak") || name.contains("MJOLNIR") {
            continue;
        }
        let Ok(len) = entry.metadata().map(|m| m.len()) else {
            continue;
        };
        if smallest.as_ref().is_none_or(|(best, _)| len < *best) {
            smallest = Some((len, path));
        }
    }
    let (_, path) = smallest.context("no shipped .pak to copy a stub from")?;
    Ok(std::fs::read(&path)?)
}
