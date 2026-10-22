//! Stage an MCC Halo 2 map for the conversion pipeline: the same staging
//! directory halo2ue writes for a Halo 1 map (docs/ce_map_conversion.md), so
//! every step after it runs unchanged.
//!
//! What differs from Halo 1 is folded in here, not downstream:
//!
//! - **Collision** goes out in the CE element layout (`layout: "ce_pc_v7"`
//!   names the `.bin`'s encoding; [`super::collision`] widens Halo 2's
//!   16-bit tables). Instanced geometry, which CE never had, is baked into
//!   world space and appended as a tail of standalone surfaces with
//!   `scenery_surfaces` counting it, the route CE scenery already takes
//!   (`mjolnir level collision` links the tail into the tree).
//! - **Materials** carry `game_material`: Halo 2 shaders name a global
//!   material (`hard_terrain_concrete`), not CE's material type number, and
//!   the name maps onto the materials the game ships ([`game_material`]).
//! - **Placements** use halo2ue's vocabulary: netgame flag types by their CE
//!   names (`CtfFlag`, `OddballSpawn`, `HillFlag`, `TeleportFrom`...), game
//!   types as CE's enum strings, item collections resolved to their item.
//!   Halo 2's multiplayer pickups and vehicles all come from netgame
//!   equipment (item and vehicle collections); props are scenery and crates.
//! - `manifest.json` says `"source": "halo2_mcc"`, which the scripts branch on.

use std::collections::BTreeMap;
use std::path::Path;

use serde_json::{json, Value};

use crate::h2::collision::{self, Collision, ARRAY_ORDER, CE_SIZES, TWO_SIDED};
use crate::h2::render::Renderer;
use crate::h2::{Cache, Group, Struct, Tag};
use crate::Error;

/// The surface materials the game ships a `shaders\<name>` for (CU4,
/// 2026-10-21: `mjolnir list --group shader`, the top-level `shaders\`
/// tags). `mjolnir level collision` refuses any other name.
pub const GAME_MATERIALS: &[&str] = &[
    "brittle",
    "brittle_glass",
    "brittle_glass_for",
    "brittle_glass_reinforced",
    "default_material",
    "energy_hologram",
    "energy_shield_thick_cov_jackal",
    "energy_shield_thin_cov_elite",
    "hard_metal_solid",
    "hard_metal_thick",
    "hard_metal_thick_for",
    "hard_metal_thick_hum",
    "hard_metal_thin",
    "hard_terrain_ice",
    "hard_terrain_stone",
    "invalid",
    "liquid_thin_water",
    "soft_floodflesh",
    "soft_organic_cloth",
    "soft_organic_plant",
    "soft_terrain_snow",
    "tough_inorganic_rubber",
    "tough_organic_wood",
    "tough_terrain_dirt",
    "tough_terrain_grass",
    "tough_terrain_gravel",
    "tough_terrain_mud",
    "tough_terrain_sand",
    "tough_terrain_woodfloor",
];

/// Halo 2 material names (or name stems) with no namesake in the game.
const MATERIAL_ALIASES: &[(&str, &str)] = &[
    ("hard_terrain_concrete", "hard_terrain_stone"),
    ("hard_terrain_rock", "hard_terrain_stone"),
    ("hard_terrain_metal", "hard_metal_thick"),
    ("energy", "energy_hologram"),
    ("liquid_thin", "liquid_thin_water"),
    ("liquid", "liquid_thin_water"),
    ("soft_terrain", "soft_terrain_snow"),
    ("tough_terrain", "tough_terrain_dirt"),
    ("hard_metal", "hard_metal_thick"),
    ("brittle_glass_unbreakable", "brittle_glass_reinforced"),
];

/// The game material a Halo 2 global material name becomes: itself when the
/// game ships it, else an alias, else the name with its last `_word` cut
/// (`hard_metal_thin_hum_grating` -> `hard_metal_thin`), else
/// `default_material`. The flag says whether the name was the game's own.
pub fn game_material(h2: &str) -> (String, bool) {
    let known = |n: &str| GAME_MATERIALS.contains(&n);
    if known(h2) {
        return (h2.to_string(), true);
    }
    let mut name = h2;
    loop {
        if known(name) {
            return (name.to_string(), false);
        }
        if let Some((_, to)) = MATERIAL_ALIASES.iter().find(|(from, _)| *from == name) {
            return (to.to_string(), false);
        }
        match name.rfind('_') {
            Some(i) => name = &name[..i],
            None => return ("default_material".to_string(), false),
        }
    }
}

/// halo2ue's file-name rule: lowercase, anything outside `[a-z0-9-]` an
/// underscore, runs collapsed, ends trimmed (so `__` never occurs in a name
/// and can separate a suffix).
pub fn sanitize(name: &str) -> String {
    let mut out = String::new();
    for c in name.chars().flat_map(char::to_lowercase) {
        let c = if c.is_ascii_alphanumeric() || c == '-' { c } else { '_' };
        if c == '_' && out.ends_with('_') {
            continue;
        }
        out.push(c);
    }
    out.trim_matches('_').to_string()
}

/// Halo 2's game type enum (player starts, netgame equipment) in the names
/// halo2ue gives CE's.
fn game_type(v: i16) -> String {
    match v {
        0 => "None".into(),
        1 => "Ctf".into(),
        2 => "Slayer".into(),
        3 => "Oddball".into(),
        4 => "King".into(),
        5 => "Race".into(),
        12 => "AllGames".into(),
        13 => "AllGamesExceptCtf".into(),
        14 => "AllGamesExceptCtfAndRace".into(),
        n => format!("Unknown({n})"),
    }
}

/// A netgame flag's type in halo2ue's names where CE has the same thing;
/// Halo 2's own (assault, territories, headhunter) keep a name of their
/// own, which the tag map leaves unmapped.
fn flag_type(v: i16) -> String {
    match v {
        0 => "CtfFlag".into(),
        1 => "CtfFlagReturn".into(),
        2 => "AssaultBombSpawn".into(),
        3 => "AssaultBombReturn".into(),
        4 => "OddballSpawn".into(),
        6 => "RaceTrack".into(),
        7 => "TeleportFrom".into(),
        8 => "TeleportTo".into(),
        9 => "HeadhunterBin".into(),
        10 => "Territory".into(),
        11..=18 => "HillFlag".into(),
        n => format!("Unknown({n})"),
    }
}

/// What staging found and did, for the command to print.
#[derive(Debug, Default)]
pub struct Summary {
    pub notes: Vec<String>,
    pub bsp_surfaces: usize,
    pub instance_surfaces: usize,
    pub instances: usize,
    pub placements: BTreeMap<String, usize>,
}

/// The tag a reference names, or a note when it cannot be found.
fn follow<'a>(cache: &'a Cache, s: Struct<'a>, off: usize, notes: &mut Vec<String>) -> Option<Tag<'a>> {
    let r = s.tagref(off)?;
    let t = cache.follow(r);
    if t.is_none() {
        notes.push(format!("{} {} has no data in the open maps", r.group.name(), r.name()));
    }
    t
}

/// The global material name a `shad` tag gives (+0x08).
fn shader_material<'a>(shader: Option<Tag<'a>>) -> &'a str {
    shader.map(|t| t.root.sid(0x08)).unwrap_or("")
}

/// The sbsp's collision materials (20-byte elements: old shader ref, i16
/// global material index, i16 conveyor surface, shader ref) as staging
/// material records.
fn collision_materials(cache: &Cache, sbsp: &Tag<'_>, notes: &mut Vec<String>) -> Vec<Value> {
    let mut out = Vec::new();
    for (i, m) in sbsp.root.block(0x0C, 0x14).iter().enumerate() {
        let shader = follow(cache, m, 0x0C, notes).or_else(|| follow(cache, m, 0x00, notes));
        let path = shader.map(|t| t.name()).unwrap_or("");
        let h2 = shader_material(shader);
        let (game, exact) = game_material(h2);
        if !exact {
            notes.push(format!("material {i} ({path}): {h2:?} -> {game}"));
        }
        out.push(json!({
            "index": i,
            "shader_class": "shad",
            "shader_path": path,
            "datum": 4294967295u32,
            "material_type": Value::Null,
            "game_material": game,
            "h2_material": h2,
        }));
    }
    out
}

/// Instanced geometry, baked into world space onto the end of `col`:
/// each instance's definition collision, transformed by its scale and
/// forward/left/up/position frame (world = position + scale * (x F + y L +
/// z U)), every polygon fan-split into standalone triangles that keep its
/// material and its invisible/climbable/breakable flags and are marked two
/// sided, as CE scenery is.
fn add_instances(sbsp: &Tag<'_>, col: &mut Collision, summary: &mut Summary) {
    let defs: Vec<Collision> = sbsp.root.block(0x138, 0xC8).iter().map(|d| collision::read(d.at(0x70))).collect();
    let instances = sbsp.root.block(0x140, 0x58);
    for inst in instances.iter() {
        let scale = match inst.f32(0x00) {
            s if s == 0.0 => 1.0,
            s => s,
        };
        let (f, l, u, p) = (inst.vec3(0x04), inst.vec3(0x10), inst.vec3(0x1C), inst.vec3(0x28));
        let Some(def) = defs.get(inst.i16(0x34).max(0) as usize) else {
            summary.notes.push(format!("instance {} names a missing definition", inst.sid(0x50)));
            continue;
        };
        let world = |v: [f32; 3]| -> [f32; 3] {
            std::array::from_fn(|k| p[k] + scale * (v[0] * f[k] + v[1] * l[k] + v[2] * u[k]))
        };
        for s in 0..def.surfaces.len() {
            let pts: Vec<[f32; 3]> = def.polygon(s).into_iter().map(world).collect();
            let (_, _, flags, _, material) = def.surfaces[s];
            summary.instance_surfaces += col.push_standalone(&pts, (flags & 0x0E) | TWO_SIDED, material);
        }
        summary.instances += 1;
    }
}

fn write_json(path: &Path, v: &Value) -> Result<(), Error> {
    let text = serde_json::to_string_pretty(v).map_err(|e| Error::Format(e.to_string()))?;
    std::fs::write(path, text + "\n").map_err(|e| Error::Io(path.to_path_buf(), e))
}

/// Write `collision_0.json` and its `.bin`.
fn write_collision(dir: &Path, sbsp: &Tag<'_>, col: &Collision, materials: Vec<Value>, summary: &Summary) -> Result<Value, Error> {
    let bin = dir.join("bsp").join("collision_0.bin");
    std::fs::write(&bin, col.to_bin()).map_err(|e| Error::Io(bin.clone(), e))?;
    let (lo, hi) = col.bounds().unwrap_or(([0.0; 3], [0.0; 3]));
    let counts: serde_json::Map<String, Value> =
        ARRAY_ORDER.iter().zip(col.counts()).map(|(n, c)| (n.to_string(), json!(c))).collect();
    let sizes: serde_json::Map<String, Value> =
        ARRAY_ORDER.iter().zip(CE_SIZES).map(|(n, s)| (n.to_string(), json!(s))).collect();
    let meta = json!({
        "layout": "ce_pc_v7",
        "source_layout": "h2_mcc",
        "coordinate_space": "halo_wu",
        "tag_path": sbsp.name(),
        "bsp_index": 0,
        "bin": "bsp/collision_0.bin",
        "array_order": ARRAY_ORDER,
        "counts": counts,
        "element_sizes": sizes,
        "world_bounds": {"min": lo, "max": hi},
        "child_encoding": {"none": -1, "leaf_flag": "0x80000000", "surface_flag": "0x80000000"},
        "plane_encoding": {"flip_flag": "0x80000000", "applies_to": ["surfaces.plane", "bsp2d_references.plane"]},
        "surface_flag_bits": {"two_sided": 1, "invisible": 2, "climbable": 4, "breakable": 8},
        "materials": materials,
        "scenery_surfaces": {
            "objects": summary.instances,
            "surfaces": summary.instance_surfaces,
            "note": "Halo 2 instanced geometry baked to world space after the BSP's own surfaces; mjolnir level collision links them into the tree",
        },
    });
    write_json(&dir.join("bsp").join("collision_0.json"), &meta)?;
    Ok(json!({
        "collision": "bsp/collision_0.json",
        "collision_bin": "bsp/collision_0.bin",
        "collision_counts": counts,
        "collision_materials": summary_materials(&meta),
        "world_bounds": {"min": lo, "max": hi, "units": "halo_wu"},
    }))
}

fn summary_materials(meta: &Value) -> usize {
    meta["materials"].as_array().map(|a| a.len()).unwrap_or(0)
}

/// The item an item collection spawns: its heaviest permutation (16-byte
/// elements: f32 weight, item tag ref, variant string id).
fn collection_item<'a>(cache: &'a Cache, collection: &Tag<'a>, notes: &mut Vec<String>) -> Option<Tag<'a>> {
    let perms = collection.root.block(0x00, 0x10);
    let best = perms.iter().max_by(|a, b| a.f32(0).total_cmp(&b.f32(0)))?;
    follow(cache, best, 0x04, notes)
}

/// placement.json: player starts, netgame flags, netgame equipment (as
/// halo2ue's `netgame_equipment` and `vehicle` entries), scenery and crates.
fn placements<'c>(
    cache: &'c Cache,
    scnr: &Tag<'c>,
    dir: &Path,
    summary: &mut Summary,
    render: &mut Renderer<'c>,
) -> Result<Value, Error> {
    let root = scnr.root;
    let mut entries = Vec::new();
    let mut notes = Vec::new();
    let count = |summary: &mut Summary, kind: &str| *summary.placements.entry(kind.to_string()).or_default() += 1;
    // Halo 2 spawns by influence, so its starts carry no CTF side (all of
    // Lockout's are team 0), where halo2ue's carry CE's red or blue and the
    // level generator labels CTF spawns (and vehicle sets) by it. Starts and
    // vehicles take the side of the nearer CTF flag spawn (netgame flag type
    // 0, team 0 or 1) when the map has both; Halo 2's own designator stays
    // as `h2_team`.
    let flags = root.block(0x118, 0x20);
    let ctf: Vec<(i16, [f32; 3])> = flags
        .iter()
        .filter(|f| f.i16(0x10) == 0 && matches!(f.i16(0x12), 0 | 1))
        .map(|f| (f.i16(0x12), f.vec3(0x00)))
        .collect();
    let both_sides = ctf.iter().any(|f| f.0 == 0) && ctf.iter().any(|f| f.0 == 1);
    let side = |p: [f32; 3], own: i16| -> i16 {
        if !both_sides {
            return own;
        }
        let d = |q: [f32; 3]| (0..3).map(|k| (p[k] - q[k]).powi(2)).sum::<f32>();
        ctf.iter().min_by(|a, b| d(a.1).total_cmp(&d(b.1))).map_or(own, |f| f.0)
    };

    for e in root.block(0x120, 0x90).iter() {
        let Some(collection) = follow(cache, e, 0x58, &mut notes) else { continue };
        let game_types: Vec<String> = (0..4).map(|k| game_type(e.i16(0x04 + 2 * k))).collect();
        let (pos, rot) = (e.vec3(0x40), e.vec3(0x4C));
        let flags = e.u32(0x00);
        let Some(item) = collection_item(cache, &collection, &mut notes) else { continue };
        if collection.group() == Group::new(b"vehc") {
            // CE's vehicle spawn flags: bits 0-3 default in Slayer, CTF,
            // King and Oddball, bits 8-11 allowed there.
            let mask = (0..4).fold(0u16, |m, k| m | match e.i16(0x04 + 2 * k) {
                1 => 2,
                2 => 1,
                3 => 8,
                4 => 4,
                12 => 0x0F,
                13 | 14 => 0x0D,
                _ => 0,
            });
            entries.push(json!({
                "kind": "vehicle",
                "asset": item.name(),
                "tag_class": item.group().name(),
                "vehicle_collection": collection.name(),
                "model": Value::Null, "skeletal": false, "origin_offset": [0.0, 0.0, 0.0],
                "pos": pos, "rot": rot,
                "team": side(pos, e.i16(0x0C)), "h2_team": e.i16(0x0C), "spawn_flags": mask | mask << 8,
                "spawn_time": e.i16(0x0E), "game_types": game_types,
            }));
            count(summary, "vehicle");
        } else {
            entries.push(json!({
                "kind": "netgame_equipment",
                "asset": item.name(),
                "tag_class": item.group().name(),
                "item_collection": collection.name(),
                "model": Value::Null, "skeletal": false, "origin_offset": [0.0, 0.0, 0.0],
                "pos": pos, "rot": rot,
                "team": e.i16(0x0C), "levitate": flags & 1 != 0,
                "spawn_time": e.i16(0x0E),
                "collection_spawn_time": collection.root.i16(0x08),
                "classification": e.u8(0x14),
                "game_types": game_types,
            }));
            count(summary, "netgame_equipment");
        }
    }

    let mut skipped: BTreeMap<String, usize> = BTreeMap::new();
    // Scenery (0x5C) and crates (0x4C): props, each placed by its palette's
    // object, with the object's collision model staged in object space for
    // tools/level/merge_ce_collision.py to place.
    for (kind_block, palette_block, size, group) in [(0x50usize, 0x58usize, 0x5Cusize, "scen"), (0x328, 0x330, 0x4C, "bloc")] {
        let palette = root.block(palette_block, 0x28);
        for e in root.block(kind_block, size).iter() {
            let i = e.i16(0x00);
            if i < 0 {
                continue;
            }
            let Some(object) = palette.get(i as usize).and_then(|p| follow(cache, p, 0x00, &mut notes)) else { continue };
            // Scenery for some game types only (+0x5A, bit 1 Slayer): the
            // CTF and territory flag bases, which the level generator's own
            // CTF stands replace. Teleporter scenery is skipped as well: the
            // generator puts working pads on the teleporter flags.
            let games = if group == "scen" { e.u16(0x5A) } else { 0 };
            if games != 0 && games & 2 == 0 {
                *skipped.entry(format!("{} (game-type prop, flags {games:#x})", object.name())).or_default() += 1;
                continue;
            }
            if object.name().contains("teleporter") {
                *skipped.entry(format!("{} (the level's own teleporters replace it)", object.name())).or_default() += 1;
                continue;
            }
            let scale = e.f32(0x20);
            if scale != 0.0 && (scale - 1.0).abs() > 1e-4 {
                notes.push(format!("{} placed at scale {scale}: staged at 1", object.name()));
            }
            let collision = stage_object_collision(cache, &object, dir, &mut notes)?;
            let mut entry = json!({
                "kind": "scenery",
                "asset": object.name(),
                "tag_class": group,
                "model": Value::Null, "skeletal": false, "origin_offset": [0.0, 0.0, 0.0],
                "pos": e.vec3(0x08), "rot": e.vec3(0x14),
            });
            if let Some(c) = collision {
                entry["collision"] = json!(c);
            }
            if let Some(model) = object_model(cache, &object, &mut notes) {
                if let Some(record) = render.model(&model, object.name(), group)? {
                    entry["model"] = record["gltf"].clone();
                }
            }
            entries.push(entry);
            count(summary, if group == "scen" { "scenery" } else { "crate" });
        }
    }

    for (what, n) in skipped {
        notes.push(format!("{n} x {what} not placed"));
    }

    // The first sky, at the origin: tools/level/merge_ce_scene.py scales it
    // out around the map. (sky: render model ref at 0x00.)
    if let Some(sky) = root.block(0x08, 0x08).get(0).and_then(|s| follow(cache, s, 0x00, &mut notes)) {
        if let Some(model) = follow(cache, sky.root, 0x00, &mut notes) {
            if let Some(record) = render.model(&model, sky.name(), "sky")? {
                entries.push(json!({
                    "kind": "sky", "asset": sky.name(), "tag_class": "sky", "model": record["gltf"],
                    "skeletal": false, "origin_offset": [0.0, 0.0, 0.0], "pos": [0.0, 0.0, 0.0], "rot": [0.0, 0.0, 0.0],
                }));
                count(summary, "sky");
            }
        }
    }

    let player_starts: Vec<Value> = root
        .block(0x100, 0x34)
        .iter()
        .map(|s| {
            let pos = s.vec3(0x00);
            json!({
                "pos": pos, "facing": s.f32(0x0C), "team": side(pos, s.i16(0x10)), "h2_team": s.i16(0x10),
                "bsp_index": s.i16(0x12),
                "game_types": (0..4).map(|k| game_type(s.i16(0x14 + 2 * k))).collect::<Vec<_>>(),
            })
        })
        .collect();
    let netgame_flags: Vec<Value> = root
        .block(0x118, 0x20)
        .iter()
        .map(|f| {
            let t = f.i16(0x10);
            let mut v = json!({
                "pos": f.vec3(0x00), "facing": f.f32(0x0C), "type": flag_type(t), "h2_type": t,
                "team": f.i16(0x12), "identifier": f.i16(0x14), "weapon_group": 0,
            });
            match t {
                // Teleporters pair source and destination by identifier.
                7 | 8 => v["channel"] = json!(f.i16(0x14)),
                // A hill is the ring of flags of one type, 11 hill 0 to 18 hill 7;
                // halo2ue's hill flags carry the hill in `team` too, which the
                // level generator reads.
                11..=18 => {
                    v["hill_index"] = json!(t - 11);
                    v["team"] = json!(t - 11);
                }
                _ => {}
            }
            v
        })
        .collect();
    summary.notes.extend(notes);
    Ok(json!({
        "world_unit_meters": 3.048,
        "rotation_convention": "halo_yaw_pitch_roll_radians",
        "entries": entries,
        "player_starts": player_starts,
        "netgame_flags": netgame_flags,
        "decals": [],
    }))
}

/// A placed object's render model: object +0x34 the model (`hlmt`), whose
/// +0x00 is the render model (`mode`).
fn object_model<'a>(cache: &'a Cache, object: &Tag<'a>, notes: &mut Vec<String>) -> Option<Tag<'a>> {
    let model = follow(cache, object.root, 0x34, notes)?;
    follow(cache, model.root, 0x00, notes)
}

/// A placed object's collision model as `collision/<name>.json`: every
/// region's first permutation, each BSP's polygons fan-split into a flat
/// triangle list (9 floats each, object space, world units). Only BSPs on
/// the root node are taken where the model has more than one node, since
/// node transforms are not applied (a note says so).
fn stage_object_collision(cache: &Cache, object: &Tag<'_>, dir: &Path, notes: &mut Vec<String>) -> Result<Option<String>, Error> {
    let Some(model) = follow(cache, object.root, 0x34, notes) else { return Ok(None) };
    let Some(coll) = model.root.tagref(0x08).and_then(|r| cache.follow(r)) else { return Ok(None) };
    let mut tris = Vec::new();
    let mut skipped = 0;
    for region in coll.root.block(0x1C, 0x0C).iter() {
        let Some(perm) = region.block(0x04, 0x14).get(0) else { continue };
        for bsp in perm.block(0x04, 0x44).iter() {
            if bsp.i16(0) > 0 {
                skipped += 1;
                continue;
            }
            let c = collision::read(bsp.at(0x04));
            for s in 0..c.surfaces.len() {
                let pts = c.polygon(s);
                for k in 1..pts.len().saturating_sub(1) {
                    for v in [pts[0], pts[k], pts[k + 1]] {
                        tris.extend_from_slice(&v);
                    }
                }
            }
        }
    }
    if skipped > 0 {
        notes.push(format!("{}: {skipped} collision BSP(s) on child nodes left out", coll.name()));
    }
    if tris.is_empty() {
        return Ok(None);
    }
    let rel = format!("collision/{}.json", sanitize(object.name()));
    write_json(&dir.join(&rel), &json!({"tag_path": object.name(), "units": "halo_wu", "triangles": tris}))?;
    Ok(Some(rel))
}

/// Stage `cache`'s scenario into `dir`.
pub fn stage(cache: &Cache, dir: &Path) -> Result<Summary, Error> {
    for sub in ["bsp", "collision", "models", "textures"] {
        std::fs::create_dir_all(dir.join(sub)).map_err(|e| Error::Io(dir.join(sub), e))?;
    }
    let mut summary = Summary::default();
    let scnr = cache.scenario()?;
    let bsps = scnr.root.block(0x210, 0x44);
    if bsps.count > 1 {
        summary.notes.push(format!("{} structure BSPs; only BSP 0 is staged", bsps.count));
    }
    let first = bsps.get(0).ok_or_else(|| Error::Format("the scenario has no structure BSP".into()))?;
    let sbsp = first
        .tagref(0x10)
        .and_then(|r| cache.follow(r))
        .ok_or_else(|| Error::Format("structure BSP 0 has no sbsp data".into()))?;

    let mut notes = Vec::new();
    let materials = collision_materials(cache, &sbsp, &mut notes);
    summary.notes.extend(notes);
    let structure = sbsp.root.block(0x14, 0x40).get(0).ok_or_else(|| Error::Format("the sbsp has no collision BSP".into()))?;
    let mut col = collision::read(structure);
    summary.bsp_surfaces = col.surfaces.len();
    add_instances(&sbsp, &mut col, &mut summary);
    let collision_info = write_collision(dir, &sbsp, &col, materials, &summary)?;

    let mut renderer = Renderer::new(cache, dir);
    let render = renderer.bsp(&sbsp, first)?;
    let placement = placements(cache, &scnr, dir, &mut summary, &mut renderer)?;
    write_json(&dir.join("placement.json"), &placement)?;
    let models = renderer.finish(&mut summary)?;
    // One note per fact, not per placement of the same prop.
    let mut seen = std::collections::BTreeSet::new();
    summary.notes.retain(|n| seen.insert(n.clone()));

    let mut bsp = json!({
        "tag_path": sbsp.name(),
        "gltf": "bsp/bsp_0.gltf",
    });
    for (k, v) in render.as_object().into_iter().flatten().chain(collision_info.as_object().into_iter().flatten()) {
        bsp[k] = v.clone();
    }
    let counts: serde_json::Map<String, Value> = summary.placements.iter().map(|(k, v)| (k.clone(), json!(v))).collect();
    let manifest = json!({
        "generator": concat!("mjolnir cache stage (blam-cache ", env!("CARGO_PKG_VERSION"), ")"),
        "source": "halo2_mcc",
        "game": "halo2",
        "map_name": cache.map.header.name,
        "scenario": cache.map.header.scenario,
        "map_type": match scnr.root.i16(0x10) { 0 => "Campaign", 1 => "Multiplayer", 2 => "UI", _ => "Unknown" },
        "units": "meters",
        "world_unit_meters": 3.048,
        "gltf_up_axis": "Y",
        "coordinate_contract": {
            "halo_wu_to_gltf_m": "(x, z, -y) * 3.048",
            "halo_wu_to_ue_cm": "(x, -y, z) * 304.8",
            "yaw_ue_deg": "-degrees(yaw_halo)",
            "halo_wu_to_blam_wu": "identity",
        },
        "world_bounds": bsp["world_bounds"].clone(),
        "bsps": [bsp],
        "models": models,
        "placements": {
            "counts": counts,
            "player_starts": placement["player_starts"].as_array().map(|a| a.len()).unwrap_or(0),
            "netgame_flags": placement["netgame_flags"].as_array().map(|a| a.len()).unwrap_or(0),
            "decals": 0,
        },
        "notes": summary.notes,
    });
    write_json(&dir.join("manifest.json"), &manifest)?;
    Ok(summary)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Halo 2's names reach the game's: exact, shortened, aliased, or the
    /// default; never a name the game does not ship.
    #[test]
    fn halo_2_materials_map_onto_shipped_ones() {
        assert_eq!(game_material("hard_metal_thick_for"), ("hard_metal_thick_for".into(), true));
        assert_eq!(game_material("hard_metal_solid_for").0, "hard_metal_solid");
        assert_eq!(game_material("hard_metal_thin_hum_grating").0, "hard_metal_thin");
        assert_eq!(game_material("brittle_glass_for_unbreakable").0, "brittle_glass_for");
        assert_eq!(game_material("hard_terrain_concrete").0, "hard_terrain_stone");
        assert_eq!(game_material("energy").0, "energy_hologram");
        assert_eq!(game_material("").0, "default_material");
        assert_eq!(game_material("plasma_goo").0, "default_material");
        for name in ["soft_terrain_snow", "hard_metal_thin_cov", "tough_terrain_grass_tall"] {
            assert!(GAME_MATERIALS.contains(&game_material(name).0.as_str()));
        }
    }

    #[test]
    fn names_sanitize_as_halo2ue_does() {
        assert_eq!(sanitize("scenarios\\multi\\lockout\\Lift Tube"), "scenarios_multi_lockout_lift_tube");
        assert_eq!(sanitize("__a__b__"), "a_b");
    }
}
