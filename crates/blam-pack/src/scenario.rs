//! Registering a scenario codename the way the game's own are registered.
//!
//! The simulation learns which campaign maps exist at boot, from the tables
//! `BuiltInMapInfoData` points at (`CampaignMapInfoTables` = `DT_Scenarios`,
//! `DT_Test_Scenarios`). A row added at runtime is visible to the menu flow —
//! `StartScenario` reads the table then — but not to the map registry the
//! simulation built earlier, which is the state the 2026-09-03 `PG1` stall
//! sat in: a shipped codename in a new row started fine, a new codename never
//! did. Cooked into the table, a new codename starts (verified 2026-09-11,
//! `docs/new_scenario_loading.md`).
//!
//! So a codename needs two edits, packed here as one override container:
//! a `DT_Scenarios` row cloned from a donor mission with `ScenarioName` set
//! to the codename, and a `ScenarioList` handle on the campaign asset so
//! MISSION SELECT lists it. The scenario tag package itself is
//! [`build_addition`](crate::build_addition)'s job.

use std::path::PathBuf;

use ue_asset::props::{Name, Val};
use ue_asset::zen::ScriptObjects;
use ue_asset::Usmap;
use ue_iostore::{ChunkEntry, Container};

use crate::{build_override, Built, ChunkEdit};

pub const TABLE: &str = "/Game/Blueprints/Campaign/DT_Scenarios";
pub const CAMPAIGN: &str = "/Game/Blueprints/Campaign/DA_FirstPlayableCampaign";
const ROW_STRUCT: &str = "BlamScenarioDataTableRow";

/// What to register.
pub struct Registration {
    /// Three-character codename, e.g. `PG1`.
    pub code: String,
    /// The shipped mission whose row is cloned (its world, preview image,
    /// insertion points and unlock tag carry over).
    pub from: String,
    /// Menu title; the donor's when `None`.
    pub title: Option<String>,
    /// Menu description; the donor's when `None`.
    pub description: Option<String>,
    /// The world the row's `UnrealLevel` points at, as an object path
    /// (`/Game/Levels/Halo1/Solo/BGL/BGL.BGL`); the donor's when `None`.
    pub world: Option<String>,
}

/// An `FText` that carries its own string: flags `CultureInvariant`, history
/// `None`, has-invariant-string, then the string. The shipped rows use
/// string-table entries instead (history 11), which a mod cannot add to.
pub fn invariant_text(s: &str) -> Vec<u8> {
    let mut out = Vec::new();
    out.extend_from_slice(&2u32.to_le_bytes()); // ETextFlag::CultureInvariant
    out.push(0xff); // ETextHistoryType::None
    out.extend_from_slice(&1u32.to_le_bytes()); // bHasCultureInvariantString
                                                // FString: ASCII when it fits, else UTF-16 with a negative length.
    if s.is_ascii() {
        out.extend_from_slice(&((s.len() + 1) as i32).to_le_bytes());
        out.extend_from_slice(s.as_bytes());
        out.push(0);
    } else {
        let units: Vec<u16> = s.encode_utf16().chain(std::iter::once(0)).collect();
        out.extend_from_slice(&(-(units.len() as i32)).to_le_bytes());
        for u in units {
            out.extend_from_slice(&u.to_le_bytes());
        }
    }
    out
}

fn find_slot(usmap: &Usmap, class: &str, want: &str) -> Result<u16, String> {
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
    Err(format!("{class} has no property {want}"))
}

/// A shipped package by its `/Game` path: container index, chunk, bytes.
fn locate(
    containers: &[Container],
    oodle: &[PathBuf],
    path: &str,
) -> Result<(usize, ChunkEntry, Vec<u8>), String> {
    let rel = format!("{}.uasset", path.trim_start_matches("/Game/"));
    for (ci, c) in containers.iter().enumerate() {
        if let Some((_, i)) = c.files.iter().find(|(p, _)| p.ends_with(&rel)) {
            let chunk = c.chunks[*i].clone();
            let data = ue_iostore::read_chunk(c, &chunk, None, oodle).map_err(|e| e.to_string())?;
            return Ok((ci, chunk, data));
        }
    }
    Err(format!("{path} is not in any container"))
}

/// Build the registration container. Returns it with its container name
/// (`pakchunk996-MJOLNIRREG-<CODE>_P`) and a log of what changed.
pub fn register(
    containers: &[Container],
    oodle: &[PathBuf],
    usmap: &Usmap,
    scripts: &ScriptObjects,
    reg: &Registration,
) -> Result<(Built, String, Vec<String>), String> {
    let mut log = Vec::new();

    // ---- DT_Scenarios: clone the donor row under the new name ---------------
    let (ci_table, table_chunk, table_data) = locate(containers, oodle, TABLE)?;
    let mut zp = ue_asset::package::ZenPackage::parse(&table_data).map_err(|e| e.to_string())?;
    let edit = ue_asset::edit::open_export(&zp, usmap, scripts, 0)?;
    if edit.class != "DataTable" {
        return Err(format!("{TABLE} export 0 is a {}", edit.class));
    }
    let (mut rows, used) = ue_asset::datatable::decode(usmap, ROW_STRUCT, &edit.tail)?;
    let remainder = edit.tail[used..].to_vec();
    // The rows have to come back byte for byte before anything is changed.
    let again = ue_asset::datatable::encode(usmap, ROW_STRUCT, &rows)?;
    if again != edit.tail[..used] {
        return Err(format!("the row codec does not round-trip {TABLE}"));
    }
    let row_name =
        |r: &ue_asset::datatable::Row, names: &[String]| names[r.name.index as usize].clone();
    let names = zp.names.names.clone();
    if rows.iter().any(|r| row_name(r, &names) == reg.code) {
        return Err(format!("{TABLE} already has a row named {}", reg.code));
    }
    let donor = rows
        .iter()
        .find(|r| row_name(r, &names) == reg.from)
        .ok_or_else(|| format!("{TABLE} has no row named {}", reg.from))?
        .clone();
    let mut block = donor.block.clone();
    block.set(
        find_slot(usmap, ROW_STRUCT, "ScenarioName")?,
        Val::Str(reg.code.clone()),
    );
    if let Some(t) = &reg.title {
        block.set(
            find_slot(usmap, ROW_STRUCT, "MissionTitle")?,
            Val::Text(invariant_text(t)),
        );
    }
    if let Some(d) = &reg.description {
        block.set(
            find_slot(usmap, ROW_STRUCT, "MissionDescription")?,
            Val::Text(invariant_text(d)),
        );
    }
    if let Some(world) = &reg.world {
        let (package, asset) = world.rsplit_once('.').ok_or_else(|| {
            format!("world {world:?} is not an object path (/Game/Path/Leaf.Leaf)")
        })?;
        let package = zp.names.intern(package);
        let asset = zp.names.intern(asset);
        block.set(
            find_slot(usmap, ROW_STRUCT, "UnrealLevel")?,
            Val::SoftObject {
                package: Name {
                    index: package,
                    number: 0,
                },
                asset: Name {
                    index: asset,
                    number: 0,
                },
                sub: String::new(),
            },
        );
    }
    let index = zp.names.intern(&reg.code);
    rows.push(ue_asset::datatable::Row {
        name: Name { index, number: 0 },
        block,
    });
    let mut tail = ue_asset::datatable::encode(usmap, ROW_STRUCT, &rows)?;
    tail.extend_from_slice(&remainder);
    let mut bytes = edit
        .block
        .encode(usmap, &edit.class)
        .map_err(|e| e.to_string())?;
    bytes.extend_from_slice(&tail);
    zp.set_export_bytes(0, bytes).map_err(|e| e.to_string())?;
    let table_out = zp.write();
    log.push(format!(
        "row {} cloned from {} in {TABLE} ({} rows; {} -> {} bytes){}",
        reg.code,
        reg.from,
        rows.len(),
        table_data.len(),
        table_out.len(),
        reg.world
            .as_ref()
            .map(|w| format!(", UnrealLevel = {w}"))
            .unwrap_or_default()
    ));

    // ---- the campaign asset: one more ScenarioList handle ------------------
    let (ci_camp, camp_chunk, camp_data) = locate(containers, oodle, CAMPAIGN)?;
    if ci_camp != ci_table {
        return Err("the table and the campaign asset live in different containers".into());
    }
    let mut zp = ue_asset::package::ZenPackage::parse(&camp_data).map_err(|e| e.to_string())?;
    let mut edit = ue_asset::edit::open_export(&zp, usmap, scripts, 0)?;
    let list_slot = find_slot(usmap, &edit.class, "ScenarioList")?;
    let mut items = match edit.block.get(list_slot) {
        Some(Val::Array(items)) => items.clone(),
        other => return Err(format!("ScenarioList is {other:?}")),
    };
    let mut handle = match items.last().cloned() {
        Some(Val::Struct(b)) => b,
        other => return Err(format!("the last ScenarioList entry is {other:?}")),
    };
    let index = zp.names.intern(&reg.code);
    handle.set(
        find_slot(usmap, "DataTableRowHandle", "RowName")?,
        Val::Name(Name { index, number: 0 }),
    );
    items.push(Val::Struct(handle));
    let count = items.len();
    edit.block.set(list_slot, Val::Array(items));
    ue_asset::edit::write_export(&mut zp, usmap, &edit)?;
    let camp_out = zp.write();
    log.push(format!(
        "ScenarioList handle {{DT_Scenarios, {}}} on {CAMPAIGN} ({count} entries)",
        reg.code
    ));

    let built = build_override(
        &containers[ci_table],
        oodle,
        &[
            ChunkEdit {
                label: TABLE.into(),
                chunk: table_chunk,
                original_len: table_out.len(),
                patched: table_out,
            },
            ChunkEdit {
                label: CAMPAIGN.into(),
                chunk: camp_chunk,
                original_len: camp_out.len(),
                patched: camp_out,
            },
        ],
    )?;
    Ok((built, format!("pakchunk996-MJOLNIRREG-{}_P", reg.code), log))
}
